"""Saved Course11, Timetable9, Connection6 and associated lifecycle edits."""

from collections import Counter
from pathlib import PurePosixPath
import re
import struct

from . import catalogs as c, course_factories as cf, writer as w
from .graph_references import incoming_counts
from .incident_operations import SCHEMA as INCIDENT_LAYOUT
from .incident_source import validate_set_graph
from .native_connections import connection
from .saved_reference_updates import reject_unclassified_literals


UNBOUND = (None, '', '0', '-1')
ROW_FLAGS = {'stop_at_station': 1, 'timing_station': 2}
ROW_TEXT = {'track_id': 18, 'distribution_name': 16}
ROW_SECONDS = {'dwell_s': 8, 'mean_delay_s': 12}
ROW_INDEX = {'arrival': 6, 'departure': 7}
ROW_CLOCK_FIELDS = ROW_INDEX.keys() | {f'{event}_day_offset' for event in ROW_INDEX}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def text(obj, index):
    value = obj.contents[index].value
    return c.text(value) if value is not None else None


def set_sequence(owner, slot, values):
    saved = owner.contents[slot].value
    if saved is None:
        from .zero_generation.native_signal_routes import arr
        cf.put(owner, slot, arr(values))
        return
    array = cf.clone(saved)
    w.set_elements(array, values)
    cf.put(owner, slot, array)


def dictionary_replace(dictionary, pairs):
    previous = {}
    for i in range(1, len(dictionary.contents), 2):
        key, row = dictionary.contents[i:i + 2]
        previous[c.text(key.value)] = (key.value, row.value)
    need(len(pairs) == len({key for key, _ in pairs}), 'Duplicate native dictionary key')
    if list(previous) == [key for key, _ in pairs] and all(previous[key][1] is row for key, row in pairs):
        return
    exemplar = next(iter(previous.values()))[0] if previous else None
    groups = [w.TypedValue(b'i', len(pairs))]
    for key, item in pairs:
        key_object = previous[key][0] if key in previous else cf.string(exemplar, key)
        groups.extend((w.TypedValue(b'@', key_object), w.TypedValue(b'@', item)))
    dictionary.contents = groups


def row_key(row):
    return f'{text(row, 1)}#{row.contents[3].value}'


def timetable_time(row, field):
    value = text(row, ROW_INDEX[field])
    offset = row.contents[15].values[ROW_INDEX[field] - 6]
    if value in (None, '', 'HH:MM:SS'):
        need(offset == 0, f'Undefined {field} of {row_key(row)} requires zero day offset')
        return None
    return cf.clock(value) + 86400 * offset


def apply_row_fields(row, changes):
    flags = row.contents[10].value
    for field, bit in ROW_FLAGS.items():
        if field in changes:
            flags = (flags | bit) if changes[field] else (flags & ~bit)
    cf.put(row, 10, flags)
    for field, slot in ROW_TEXT.items():
        if field in changes:
            cf.settext(row, slot, changes[field])
    for field, slot in ROW_SECONDS.items():
        if field in changes:
            cf.settext(row, slot, format(changes[field], '.9g'))
    for field, slot in ROW_INDEX.items():
        if field in changes:
            value = changes[field]
            if value not in (None, 'HH:MM:SS'):
                cf.clock(value)
            cf.settext(row, slot, 'HH:MM:SS' if value is None else value)
        day = field + '_day_offset'
        if day in changes:
            row.contents[15].values[slot - 6] = changes[day]
    if 'delta_mass_t' in changes:
        cf.put(row, 17, float(changes['delta_mass_t']))
    if 'interval_reference_course_id' in changes:
        reference = changes['interval_reference_course_id']
        cf.settext(row, 2, reference or '0')
        if reference in UNBOUND:
            cf.put(row, 11, 0.0)
    if 'interval_offset_s' in changes:
        cf.put(row, 11, float(changes['interval_offset_s']))


def next_interval_id(course_id, step, position):
    blocks = list(re.finditer(r'[0-9]+', course_id))
    if position >= len(blocks):
        value = f'{course_id}.{step}'
    else:
        block = blocks[position]
        value = int(block.group()) + step
        need(0 <= value < 2 ** 31 and int(block.group()) < 2 ** 31, 'Interval number exceeds the native integer range')
        digits = str(value)
        if block.group().startswith('0'):
            digits = digits.zfill(len(block.group()))
        value = course_id[:block.start()] + digits + course_id[block.end():]
    need(cf.name(value) not in UNBOUND, 'Interval numbering produced a reserved Course ID')
    return value


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def shift_planned(row, seconds):
    for field, index in ROW_INDEX.items():
        current = timetable_time(row, field)
        if current is None or current < 0:
            continue
        shifted = int(f32(f32(current) + seconds))
        if shifted < 0:
            cf.settext(row, index, 'HH:MM:SS')
            row.contents[15].values[index - 6] = 0
        else:
            day, left = divmod(shifted, 86400)
            cf.settext(row, index, f'{left // 3600:02}:{left // 60 % 60:02}:{left % 60:02}')
            row.contents[15].values[index - 6] = day


def _clock_fields(event, time_s):
    if time_s is None:
        return {event: None, f'{event}_day_offset': 0}
    need(0 <= time_s < 367 * 86400, 'The propagated native timetable time is outside the supported day range')
    day, seconds = divmod(time_s, 86400)
    return {event: f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}',
            f'{event}_day_offset': day}


class OperatingPlan:
    """Own freshly decoded candidate roots. Authorization and publication are caller-owned."""

    def __init__(self, roots, roles, itineraries, train_types):
        self.roots = roots
        self.roles = roles
        self.catalog = roots[roles['courses']]
        self.table = roots[roles['timetable']]
        need(incoming_counts(self.catalog)[id(c.course_array(self.catalog))] == 1,
             'The Course array must have exclusive catalog ownership')
        need(not incoming_counts(self.table).get(id(self.table)), 'Timetable dictionary cannot have another owner')
        self.trains = {text(train, 0) for train in c.train_items(roots[roles['trains']])}
        self.stations = c.station_items(roots[roles['stations']])
        self.itineraries = itineraries
        self.train_types = {value.casefold() for value in train_types}
        self.removed_incidents = set()
        self.changed_course_visits = set()
        self.interval_rows_created = 0

    def courses(self):
        return {text(course, 0): course for course in c.course_items(self.catalog)}

    def course(self, course_id):
        return self.courses()[course_id]

    def rows(self):
        return cf.timetable(self.table)

    def course_rows(self, course_id):
        return sorted((row for row in self.rows().values() if text(row, 1) == course_id),
                      key=lambda row: row.contents[3].value)

    def row(self, course_id, index):
        return self.rows()[f'{course_id}#{index}']

    def exclusive(self, root, obj):
        need(incoming_counts(root).get(id(obj), 0) == 1,
             f'Shared or unbound {w.kind(obj)} owner is outside the edit contract')

    def update_course(self, op):
        course = self.course(op['course_id'])
        self.exclusive(self.catalog, course)
        if 'train' in op:
            need(op['train'] in self.trains, 'Unknown native Train')
            cf.settext(course, 3, op['train'])
        if 'itineraries' in op:
            names = op['itineraries']
            need(len(set(names)) == len(names) and set(names) <= self.itineraries.keys(),
                 'Ordered Itineraries must be distinct, existing native definitions')
            set_sequence(course, 2, [cf.string(course, name) for name in names])
            self.changed_course_visits.add(op['course_id'])
        fields = op.get('fields', {})
        if 'speed_type' in fields:
            need(fields['speed_type'].casefold() in self.train_types, 'Speed type has no explicit TrainType binding')
        cf.apply_course_fields(course, fields)
        return {'course_id': op['course_id'], 'fields': sorted(fields), 'changed_bindings': [k for k in ('train', 'itineraries') if k in op]}

    def reset_course_itineraries(self, op):
        report = {}
        for course_id in op['course_ids']:
            course = self.course(course_id)
            arr = course.contents[2].value
            values = c.array(arr) if arr is not None else []
            kept = [value for value in values if c.text(value) in self.itineraries]
            if len(kept) != len(values):
                self.exclusive(self.catalog, course)
                set_sequence(course, 2, kept)
                report[course_id] = [c.text(value) for value in values if value not in kept]
        return {'removed_by_course': report}

    def update_timetable_row(self, op):
        if op.get('propagate_interval', False):
            return self._update_interval_clocks(op)
        row = self.row(op['course_id'], op['index'])
        self.exclusive(self.table, row)
        if 'station_sign' in op:
            station = op['station_sign']
            need(station in self.stations, 'Unknown Station')
            need(not c.array(row.contents[9].value) or station == text(row, 5),
                 'Remapping a row with outgoing Connections requires explicit connection changes')
            if station != text(row, 5):
                self.require_unambiguous_visit(op['course_id'], text(row, 5))
                self.require_unambiguous_visit(op['course_id'], station, adding=True)
            cf.settext(row, 5, station)
        apply_row_fields(row, op.get('fields', {}))
        if 'station_sign' in op or set(op.get('fields', {})) & ROW_CLOCK_FIELDS:
            self.changed_course_visits.add(op['course_id'])
        return {'row': row_key(row), 'fields': sorted(op.get('fields', {})), 'station_sign': text(row, 5)}

    def _update_interval_clocks(self, op):
        from .native_station_rebind import grouped_rows
        from .timetable_intervals import family_timing, reference_families

        cid, index = op['course_id'], op['index']
        fields = op.get('fields', {})
        events = [event for event in ROW_INDEX if {event, f'{event}_day_offset'} & fields.keys()]
        need(events and 'station_sign' not in op
             and not {'interval_reference_course_id', 'interval_offset_s'} & fields.keys(),
             'An interval time edit needs planned times and preserves the station and interval bindings')
        seed = self.row(cid, index)
        table = grouped_rows(self.rows())
        families = list(reference_families(table, {cid}))
        need(families, 'The selected Course does not belong to a saved interval family')
        (root, members, parents), = families
        need(set(members) <= self.courses().keys(), 'An interval timetable family contains an unknown Course')
        stations, offsets = family_timing(table, root, members, parents)
        changed = dict(fields)
        for event in events:
            if event in changed and changed[event] in (None, 'HH:MM:SS'):
                changed.setdefault(f'{event}_day_offset', 0)
        committed = cf.clone(seed)
        apply_row_fields(committed, changed)
        times = {event: timetable_time(committed, event) for event in events}
        owners = incoming_counts(self.table)
        updates = []
        for course in members:
            row = table[course][index]
            need(owners.get(id(row), 0) == 1, f'Shared timetable row {row_key(row)} cannot be updated')
            relative = offsets[course] - offsets[cid]
            scheduled = {}
            for event, selected in times.items():
                scheduled.update(_clock_fields(event, None if selected is None else selected + relative))
            updates.append((row, {**changed, **scheduled} if row is seed else scheduled))
        for row, fields_to_write in updates:
            apply_row_fields(row, fields_to_write)
        self.changed_course_visits.update(members)
        return {'row': row_key(seed), 'fields': sorted(fields), 'station_sign': stations[index],
                'interval_root_course_id': root, 'interval_rows_updated': [row_key(row) for row, _ in updates]}

    def require_unambiguous_visit(self, cid, station, *, adding=False):
        rows = self.rows().values()
        if sum(text(row, 1) == cid and text(row, 5) == station for row in rows) + int(adding) <= 1:
            return
        for row in rows:
            target_station = text(row, 5)
            need(not (text(row, 2) == cid and target_station == station), 'Repeated Station participates in an interval reference')
            for item in c.array(row.contents[9].value):
                need(not (text(item, 1) == cid and (text(item, 6) or target_station) == station),
                     'Repeated Station is the ambiguous target of a Connection')

    def reindex(self, course_id, replacement):
        rows = self.rows()
        old = self.course_rows(course_id)
        counts = incoming_counts(self.table)
        need(all(counts[id(row)] == 1 for row in old), 'Shared Timetable rows cannot be reindexed')
        for index, row in enumerate(replacement):
            cf.put(row, 3, index)
            cf.put(row, 4, len(replacement) - 1)
        pairs = []
        remaining = [(row_key(row), row) for row in replacement]
        for key, row in rows.items():
            if text(row, 1) == course_id:
                pairs.extend(remaining)
                remaining.clear()
            else:
                pairs.append((key, row))
        dictionary_replace(self.table, pairs + remaining)
        self.changed_course_visits.add(course_id)

    def insert_timetable_row(self, op):
        cid, index = op['course_id'], op['index']
        self.course(cid)
        existing = self.course_rows(cid)
        need(index <= len(existing) and op['station_sign'] in self.stations, 'Invalid row insertion index or Station')
        self.require_unambiguous_visit(cid, op['station_sign'], adding=True)
        template = self.row(op['template_course_id'], op['template_index'])
        row = cf.clone(template)
        set_sequence(row, 9, [])
        cf.settext(row, 1, cid)
        cf.settext(row, 2, '0')
        cf.put(row, 11, 0.0)
        cf.settext(row, 5, op['station_sign'])
        cf.settext(row, 13, 'HH:MM:SS')
        cf.settext(row, 14, 'HH:MM:SS')
        row.contents[15].values[2:] = [0, 0]
        apply_row_fields(row, {'mean_delay_s': 0, 'track_id': '', 'distribution_name': '', 'delta_mass_t': 0, **op['fields']})
        existing.insert(index, row)
        self.reindex(cid, existing)
        return {'row_inserted': f'{cid}#{index}', 'station_sign': op['station_sign']}

    def delete_timetable_row(self, op):
        cid, index = op['course_id'], op['index']
        row = self.row(cid, index)
        existing = self.course_rows(cid)
        need(len(existing) > 1, 'Deleting the sole row requires an explicit Course delete')
        need(not c.array(row.contents[9].value), 'The row has outgoing Connections; detach or rebind them first')
        station = text(row, 5)
        self.require_unambiguous_visit(cid, station)
        replacement = [item for item in existing if item is not row]
        self.reindex(cid, replacement)
        return {'row_deleted': f'{cid}#{index}', 'station_sign': station}

    def generate_interval_courses(self, op):
        source = op['course_id']
        course = self.course(source)
        rows = self.course_rows(source)
        step, position = op['number_step'], op['number_position']
        seconds = op['interval_s']
        count = op['count']
        self.interval_rows_created += len(rows) * count
        need(rows and self.interval_rows_created <= 10000, 'Source rows required and at most 10000 new timetable rows allowed')
        reference = text(rows[0], 2)
        if reference in UNBOUND:
            reference = source
        need(all((text(row, 2) in UNBOUND if reference == source else text(row, 2) == reference) for row in rows),
             'Interval source rows must belong to one reference family')
        known = self.courses()
        created, timetable = [], []
        for _ in range(count):
            cid = next_interval_id(text(course, 0), step, position)
            need(cid not in known and cid not in created, f'Interval destination already exists: {cid}')
            course = cf.clone(course)
            cf.settext(course, 0, cid)
            created.append(cid)
            known[cid] = course
            next_rows = []
            for prior in rows:
                row = cf.clone(prior)
                cf.settext(row, 1, cid)
                cf.settext(row, 2, reference)
                cf.put(row, 11, f32(prior.contents[11].value + seconds))
                shift_planned(row, seconds)
                # Native actual-result validity is transient. New planned rows start clean.
                cf.settext(row, 13, 'HH:MM:SS')
                cf.settext(row, 14, 'HH:MM:SS')
                row.contents[15].values[2:] = [0, 0]
                connections = []
                for item in c.array(prior.contents[9].value):
                    copied = cf.clone(connection(item))
                    cf.settext(copied, 0, cid)
                    cf.settext(copied, 1, next_interval_id(text(item, 1), step, position))
                    connections.append(copied)
                set_sequence(row, 9, connections)
                next_rows.append(row)
                timetable.append((row_key(row), row))
            rows = next_rows
        set_sequence(self.catalog, 4, list(known.values()))
        dictionary_replace(self.table, [*self.rows().items(), *timetable])
        self.changed_course_visits.update(created)
        return {'source_course_id': source, 'generated_course_ids': created,
                'interval_reference_course_id': reference, 'interval_s': seconds, 'rows_added': len(timetable)}

    def update_connection(self, op):
        row = self.row(op['course_id'], op['index'])
        obj = connection(c.array(row.contents[9].value)[op['connection_index']])
        self.exclusive(self.table, obj)
        fields = op['fields']
        for key, slot in [('target_course_id', 1), ('target_station_sign', 6)]:
            if key in fields:
                cf.settext(obj, slot, fields[key])
        for key, slot in [('minimum_wait', 3), ('maximum_wait', 5)]:
            if key in fields:
                value = fields[key]
                if value is not None:
                    cf.clock(value)
                cf.settext(obj, slot, 'HH:MM:SS' if value is None else value)
        flags = obj.contents[4].value
        for key, bit in [('join', 1), ('split', 2)]:
            if key in fields:
                flags = flags | bit if fields[key] else flags & ~bit
        if 'location' in fields:
            flags = (flags & ~12) | {'exit': 0, 'entry': 4, 'dispo': 8}[fields['location']]
        cf.put(obj, 4, flags)
        if 'time_reference' in fields:
            cf.put(obj, 7, int(fields['time_reference'] == 'departure'))
        if 'dispatching_distance_km' in fields:
            cf.put(obj, 8, float(fields['dispatching_distance_km']))
        propagated = []
        if op.get('propagate_interval'):
            cid, station = text(row, 1), text(row, 5)
            reference = text(row, 2)
            for other in self.rows().values():
                if other is row or other.contents[3].value != row.contents[3].value or text(other, 5) != station:
                    continue
                owner, family = text(other, 1), text(other, 2)
                related = family == cid or (reference not in UNBOUND and (family == reference or (family in UNBOUND and owner == reference)))
                if not related:
                    continue
                items = c.array(other.contents[9].value)
                index = op['connection_index']
                if index >= len(items):
                    continue
                sibling = connection(items[index])
                self.exclusive(self.table, sibling)
                for slot in (3, 5, 6):
                    cf.settext(sibling, slot, text(obj, slot))
                cf.put(sibling, 4, (sibling.contents[4].value & ~15) | (obj.contents[4].value & 15))
                cf.put(sibling, 7, obj.contents[7].value)
                propagated.append(row_key(other))
        return {'row': row_key(row), 'connection_index': op['connection_index'], 'fields': sorted(fields),
                'interval_rows_propagated': propagated}

    def references(self):
        """Typed names and diagram keys whose owner/target is a Course ID."""
        slots, dictionaries = {}, []
        for member, root in self.roots.items():
            counts = incoming_counts(root)
            for obj in w.objects(root):
                kind = w.kind(obj)
                indexes = ()
                if kind == 'OTCourse':
                    c.record(obj, kind)
                    indexes = (0,)
                elif kind == 'OTTimetable':
                    c.shape(obj, kind, 9, cf.TT)
                    indexes = (1, 2)
                elif kind == 'OTConnection':
                    connection(obj)
                    indexes = (0, 1)
                elif kind == 'OTIncident':
                    c.shape(obj, kind, 12, INCIDENT_LAYOUT)
                    indexes = (1,)
                elif kind == 'OTConflict':
                    layout = ['@', '@', '@'] if obj.clazz.version == 0 else ['@', '@', '@', 'i']
                    need(obj.clazz.version in (0, 1) and len(obj.contents) == len(layout) and obj.contents[0].encodings == [b'@'],
                         'Unsupported diagram conflict layout')
                    need(PurePosixPath(member).suffix == '.otsimcor', 'Conflict owner is not a selected Train Diagram')
                    indexes = (0,)
                elif kind == 'OTTCorridorSimController':
                    need(obj.clazz.version in (0, 1, 2) and len(obj.contents) == (5 if obj.clazz.version == 2 else 4)
                         and all(group.encodings == [b'@'] for group in obj.contents)
                         and PurePosixPath(member).suffix == '.otsimcor', 'Unsupported Train Diagram membership layout')
                    for index, group in enumerate(obj.contents):
                        if group.value is not None:
                            need(counts[id(group.value)] == 1, 'Shared Train Diagram dictionary')
                            dictionaries.append((member, group.value, index == 0))
                if indexes:
                    need(counts[id(obj)] >= 1, f'Orphan {kind} reference owner')
                if kind in ('OTCourse', 'OTTimetable', 'OTConnection') and indexes:
                    need(counts[id(obj)] == 1, f'Unexpected shared native {kind} reference owner')
                slots.setdefault(member, []).extend((obj, index) for index in indexes)
        return slots, dictionaries

    def check_reference_names(self, names, slots, diagrams):
        reviewed = {member: Counter(id(obj.contents[i].value) for obj, i in items if text(obj, i) in names)
                    for member, items in slots.items()}
        for member, diagram, conflict in diagrams:
            if not conflict:
                for index, key in enumerate(cf.dictionary(diagram)):
                    if key not in names:
                        continue
                    reviewed[member][id(diagram.contents[1 + 2 * index].value)] += 1
        # Exact old Course literals in unknown encodings would defeat semantic reference mapping.
        for member, root in self.roots.items():
            objects = tuple(w.objects(root))
            counts = incoming_counts(root)
            for old in names:
                reject_unclassified_literals(objects, old)
            for obj in objects:
                if w.kind(obj) == 'OTCourse':
                    # Displayed number, description, comments and course type are independent labels.
                    for slot in (10, 11, 13, 14):
                        if text(obj, slot) in names:
                            reviewed[member][id(obj.contents[slot].value)] += 1
            for obj in objects:
                if w.kind(obj) == 'NSString' and c.text(obj) in names:
                    need(reviewed[member][id(obj)] == counts[id(obj)], f'Unclassified Course reference in {member}')

    def rename_courses(self, op):
        mapping = {item['course_id']: item['new_id'] for item in op['renames']}
        current = self.courses()
        need(len(mapping) == len(op['renames']) and len(mapping) == len(set(mapping.values())),
             'Rename sources and destinations must be unique')
        need(mapping.keys() <= current.keys() and not set(mapping.values()) & (current.keys() - mapping.keys()),
             'Unknown Course or rename destination collision')
        for value in [*mapping, *mapping.values()]:
            need(cf.name(value) not in UNBOUND, 'Reserved Course ID')
        slots, diagrams = self.references()
        self.check_reference_names(mapping.keys(), slots, diagrams)
        table = [(f"{mapping.get(text(row, 1), text(row, 1))}#{row.contents[3].value}", row)
                 for row in self.rows().values()]
        diagram_edits = []
        for _, diagram, conflict in diagrams:
            pairs = []
            for key, item in cf.dictionary(diagram).items():
                if conflict:
                    need(w.kind(item) == 'OTConflict', 'Unknown conflict dictionary value')
                    old = text(item, 0)
                    if old in mapping:
                        need(key.endswith('#' + old), 'Conflict dictionary key does not match its Course ID')
                        key = key[:-len(old)] + mapping[old]
                else:
                    key = mapping.get(key, key)
                pairs.append((key, item))
            diagram_edits.append((diagram, pairs))
        for member, items in slots.items():
            for obj, index in items:
                old = text(obj, index)
                if old in mapping and mapping[old] != old:
                    cf.settext(obj, index, mapping[old])
        for diagram, pairs in diagram_edits:
            dictionary_replace(diagram, pairs)
        dictionary_replace(self.table, table)
        self.changed_course_visits = {mapping.get(cid, cid) for cid in self.changed_course_visits}
        return {'renamed': mapping}

    def delete_courses(self, op):
        ids = set(op['course_ids'])
        current = self.courses()
        need(ids <= current.keys() and not ids.intersection(UNBOUND), 'Missing or reserved Course IDs')
        slots, diagrams = self.references()
        self.check_reference_names(ids, slots, diagrams)
        rows = [(key, row) for key, row in self.rows().items() if text(row, 1) not in ids]
        intervals = [row for _, row in rows if text(row, 2) in ids]
        inbound = [(row, item) for _, row in rows for item in c.array(row.contents[9].value)
                   if text(item, 1) in ids]
        incidents = [obj for items in slots.values() for obj, index in items
                     if w.kind(obj) == 'OTIncident' and index == 1 and text(obj, index) in ids]
        diagram_edits = []
        for _, diagram, conflicts in diagrams:
            before = list(cf.dictionary(diagram).items())
            after = [(key, value) for key, value in before
                     if (text(value, 0) if conflicts else key) not in ids]
            if before != after:
                diagram_edits.append((diagram, after))
        dependencies = {'interval_rows': len(intervals), 'connections': len(inbound), 'incidents': len(incidents),
                        'diagram_dictionaries': len(diagram_edits)}
        need(op['reference_policy'] == 'detach' or not any(dependencies.values()),
             f'Course deletion requires explicit detach for dependencies: {dependencies}')
        for row in intervals:
            cf.settext(row, 2, '0')
            cf.put(row, 11, 0.0)
        for row in {id(row): row for row, _ in inbound}.values():
            set_sequence(row, 9, [obj for obj in c.array(row.contents[9].value) if text(obj, 1) not in ids])
        if incidents:
            events, sets = validate_set_graph(self.catalog)
            dead = {id(obj) for obj in incidents}
            need(dead <= {id(obj) for obj in events}, 'Dependent Incident is outside the CourseList event inventory')
            self.removed_incidents.update(text(obj, 0) for obj in incidents)
            for group in sets.values():
                original = c.array(group.contents[0].value)
                remaining = [obj for obj in original if id(obj) not in dead]
                if len(remaining) != len(original):
                    set_sequence(group, 0, remaining)
            set_sequence(self.catalog, 1, [obj for obj in events if id(obj) not in dead])
        for diagram, pairs in diagram_edits:
            dictionary_replace(diagram, pairs)
        set_sequence(self.catalog, 4, [course for cid, course in current.items() if cid not in ids])
        dictionary_replace(self.table, rows)
        self.changed_course_visits -= ids
        return {'deleted': sorted(ids), 'detached': dependencies}

    def validate(self):
        current = self.courses()
        for cid, course in current.items():
            choices = course.contents[2].value
            itineraries = [c.text(value) for value in c.array(choices)] if choices is not None else []
            need(set(itineraries) <= self.itineraries.keys(), f'Unresolved Itinerary in Course {cid}')
            if not itineraries:
                need(not course.contents[5].value, f'Enabled Course {cid} requires an available Itinerary')
        groups = {}
        for row in self.rows().values():
            cid, station = text(row, 1), text(row, 5)
            need(cid in current and station in self.stations, f'Unknown Course/Station on {row_key(row)}')
            groups.setdefault(cid, []).append(row)
        present = Counter((text(row, 1), text(row, 5)) for rows in groups.values() for row in rows)
        for cid, rows in groups.items():
            rows.sort(key=lambda row: row.contents[3].value)
            need(all(row.contents[3].value == i and row.contents[4].value == len(rows) - 1 for i, row in enumerate(rows)),
                 f'Incomplete Timetable row index domain for {cid}')
            prior = None
            for row in rows:
                station, reference = text(row, 5), text(row, 2)
                if reference in UNBOUND:
                    need(row.contents[11].value == 0, f'Unbound interval requires zero offset at {row_key(row)}')
                else:
                    need(reference != cid and present[reference, station] > 0, f'Unresolved interval reference at {row_key(row)}')
                if cid in self.changed_course_visits:
                    for key in ROW_INDEX:
                        value = timetable_time(row, key)
                        if value is not None:
                            need(prior is None or prior <= value, f'Nonchronological timetable at {row_key(row)}')
                            prior = value
                for item in c.array(row.contents[9].value):
                    connection(item)
                    need(text(item, 0) == cid and text(item, 2) == station, f'Connection owner mismatch at {row_key(row)}')
                    target_station = text(item, 6) or station
                    need(present[text(item, 1), target_station] > 0, f'Unresolved Connection target at {row_key(row)}')
                    minimum, maximum = text(item, 3), text(item, 5)
                    if minimum not in (None, '', 'HH:MM:SS') and maximum not in (None, '', 'HH:MM:SS'):
                        need(cf.clock(minimum) <= cf.clock(maximum), f'Inverted Connection wait at {row_key(row)}')
            if cid in self.changed_course_visits:
                course = current[cid]
                wanted = [text(row, 5) for row in rows]
                routes = [self.itineraries.get(c.text(value), ()) for value in c.array(course.contents[2].value)]
                need(all(_subsequence(wanted, route) for route in routes) and bool(routes),
                     f'Timetable Stations do not follow each chosen Itinerary for {cid}')


def _subsequence(wanted, route):
    steps = iter(route)
    return all(any(value == candidate for candidate in steps) for value in wanted)

