"""Import scheduled RailML 2.2 row connections into checked OTConnection6 owners."""

import re
from collections import Counter, defaultdict

from ..railml_timetable_v100 import wait_seconds
from . import catalogs, course_factories, timetable_setters, writer
from .graph_references import incoming_counts
from .native_connections import record, wait
from .operating_plan_edit import set_sequence, text
from .timetable_exchange_import import _native_connection
from .zero_generation.native_signal_routes import string


ROLES = {'none': 0, 'join': 1, 'split': 2, 'meet': 3}
ATTRIBUTES = {'trainRef', 'trainPartRef', 'ocpRef', 'minConnTime', 'maxConnTime', 'connOperation', 'connType'}
ELAPSED = re.compile(r'PT(?:(\d{1,5})H)?(?:(\d{1,5})M)?(?:(\d{1,5})(?:\.0+)?S)?', re.ASCII)
ABSENT = 'HH:MM:SS'
MASK_CONNECTION_ARRAY = {'connections': (9, 0)}


def connection_wait(value, label, key):
    if value is None:
        return None
    parts = ELAPSED.fullmatch(value)
    if not parts or not any(parts.groups()):
        raise ValueError(f'{key}: {label} must express whole seconds using PT H/M/S')
    hours, minutes, seconds = (int(part or '0') for part in parts.groups())
    total = hours * 3600 + minutes * 60 + seconds
    if total >= 86400:
        raise ValueError(f'{key}: {label} does not fit a native connection clock')
    return total


def fields_for(descriptor, *, key, owner, station, train_map, station_for, native_visits, part_stations):
    attrs = descriptor['attributes']
    if descriptor['has_children'] or attrs.keys() - ATTRIBUTES or attrs.get('connType', 'operational') != 'operational':
        raise ValueError(f'{key}: a mapped native Connection needs an operational declaration with supported fields')
    target_id = attrs.get('trainRef')
    if target_id not in train_map:
        raise ValueError(f'{key}: connection trainRef {target_id!r} requires an explicit mapped target train')
    target = train_map[target_id]['course_id']
    if target == owner:
        raise ValueError(f'{key}: a Connection requires a different target Course')
    target_station = station_for(attrs['ocpRef']) if 'ocpRef' in attrs else station
    if native_visits[target, target_station] != 1:
        raise ValueError(f'{key}: target Course {target!r} needs one exact native visit at {target_station!r}')
    if 'trainPartRef' in attrs:
        part = attrs['trainPartRef']
        if part not in train_map[target_id]['train_part_ids'] or target_station not in part_stations[part]:
            raise ValueError(f'{key}: connection trainPartRef {part!r} must contain the target station on {target_id!r}')
    role = attrs.get('connOperation', 'none').lower()
    if role not in ROLES:
        raise ValueError(f'{key}: unsupported native connection operation {role!r}')
    minimum = connection_wait(attrs.get('minConnTime'), 'minConnTime', key)
    maximum = connection_wait(attrs.get('maxConnTime'), 'maxConnTime', key)
    if minimum is not None and maximum not in (None, 0) and minimum > maximum:
        raise ValueError(f'{key}: minimum connection wait exceeds maximum')
    return target, target_station, ROLES[role], minimum, maximum


def same_wait(saved, desired):
    return desired is None or max(0, wait_seconds(saved)) == desired


def merge_row(row, incoming, mode, key):
    container = row.contents[9].value
    original = list(catalogs.array(container)) if container is not None else []
    outgoing = original.copy()
    station, owner = text(row, 5), text(row, 1)
    by_target = defaultdict(list)
    for index, item in enumerate(original):
        saved = record(item)
        if (saved['course_id'], saved['station_sign']) != (owner, station):
            raise ValueError(f'{key}: mismatched existing native Connection owner')
        by_target[saved['target_course_id'], saved['target_station_sign'] or station].append((index, saved))
    added = updated = matched = 0
    for target, target_station, flags, minimum, maximum in incoming:
        existing = by_target[target, target_station]
        if len(existing) > 1:
            raise ValueError(f'{key}: several native Connections match {target!r} at {target_station!r}')
        if existing:
            index, saved = existing[0]
            if ((saved['flags'] & 3) == flags and same_wait(saved['minimum_wait'], minimum)
                    and same_wait(saved['maximum_wait'], maximum)):
                matched += 1
                continue
            if mode == 'match':
                raise ValueError(f'{key}: native connection waits or operation differ for {target!r}')
            minimum_value = wait_seconds(saved['minimum_wait']) if minimum is None else minimum
            maximum_value = wait_seconds(saved['maximum_wait']) if maximum is None else maximum
            if maximum_value > 0 and minimum_value > maximum_value:
                raise ValueError(f'{key}: merged minimum connection wait exceeds maximum')
            clone = course_factories.clone(original[index])
            course_factories.put(clone, 4, (saved['flags'] & ~3) | flags)
            for slot, field, desired in ((3, 'minimum_wait', minimum), (5, 'maximum_wait', maximum)):
                if not same_wait(saved[field], desired):
                    course_factories.put(clone, slot, string(wait(desired)))
            outgoing[index] = clone
            updated += 1
            continue
        if mode == 'match':
            raise ValueError(f'{key}: no matching native Connection to {target!r} at {target_station!r}')
        fields = {'target_course_id': target, 'target_station_sign': target_station, 'join': bool(flags & 1),
                  'split': bool(flags & 2), 'minimum_wait': ABSENT if minimum is None else wait(minimum),
                  'maximum_wait': ABSENT if maximum is None else wait(maximum), 'location': 0,
                  'time_reference_type': 0, 'dispatching_distance_km': 0}
        outgoing.append(_native_connection(owner, station, fields))
        added += 1
    return outgoing, {'created': added, 'updated': updated, 'matched': matched}


def apply_connections(blob, batches, train_map, inventory, mode, station_for):
    if not batches:
        return blob, {'policy': mode, 'created': 0, 'updated': 0, 'matched': 0, 'rows': {}}
    root, version = writer.load_next_compatible(blob)
    rows = course_factories.timetable(root)
    counts = incoming_counts(root)
    visits = Counter((text(row, 1), text(row, 5)) for row in rows.values())
    part_stations = defaultdict(set)
    needed_parts = {part for declarations in batches.values() for item in declarations
                    if (part := item['attributes'].get('trainPartRef')) is not None}
    for row in inventory.data['rows']:
        if row['part_id'] in needed_parts:
            part_stations[row['part_id']].add(station_for(row['ocp_ref']))
    planned, reports = {}, {}
    for key, declarations in batches.items():
        row = rows[key]
        identities = {}
        for descriptor in declarations:
            fields = fields_for(descriptor, key=key, owner=text(row, 1), station=text(row, 5),
                                train_map=train_map, station_for=station_for,
                                native_visits=visits, part_stations=part_stations)
            identity = fields[:2]
            if identity in identities:
                previous_fields, origins = identities[identity]
                if fields != previous_fields or descriptor['source_row'] in origins:
                    raise ValueError(f'{key}: duplicate or conflicting RailML Connection to {identity}')
                origins.add(descriptor['source_row'])
            else:
                identities[identity] = fields, {descriptor['source_row']}
        outgoing, reports[key] = merge_row(row, (value[0] for value in identities.values()), mode, key)
        if reports[key]['created'] or reports[key]['updated']:
            owned = row.contents[9].value
            if counts[id(root)] or counts[id(row)] != 1 or (owned is not None and counts[id(owned)] != 1):
                raise ValueError(f'{key}: shared native Connection array or row cannot be edited independently')
            planned[key] = outgoing
    output = blob
    if planned:
        protected = timetable_setters.protected_graph(root, [(rows[key], ('connections',)) for key in planned],
                                                      MASK_CONNECTION_ARRAY)
        for key, outgoing in planned.items():
            set_sequence(rows[key], 9, outgoing)
        output = writer.dump_verified(root, version)
        again, _ = writer.load_next_compatible(output)
        check = course_factories.timetable(again)
        if protected != timetable_setters.protected_graph(again, [(check[key], ('connections',)) for key in planned],
                                                          MASK_CONNECTION_ARRAY):
            raise ValueError('RailML Connection write changed protected native timetable data')
        for key, outgoing in planned.items():
            if list(map(record, outgoing)) != list(map(record, catalogs.array(check[key].contents[9].value))):
                raise ValueError(f'{key}: native Connection output failed record readback')
    totals = {field: sum(report[field] for report in reports.values()) for field in ('created', 'updated', 'matched')}
    return output, {'policy': mode, **totals, 'rows': reports}
