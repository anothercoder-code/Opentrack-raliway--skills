"""Map original RailML 1.00 timetable rows into existing native owners."""

from collections import defaultdict
from decimal import Decimal
from hashlib import sha256

from .. import railml_timetable_v100 as legacy
from . import catalogs, timetable_setters, writer
from .course_factories import timetable
from .graph_references import incoming_counts
from .native_connections import connection
from .operating_plan_edit import apply_row_fields, timetable_time, text


ENTRY_SLOTS = {'stop_at_station': (10, 0), 'track_id': (18, 0), 'dwell_s': (8, 0), 'mean_delay_s': (12, 0)}


def connection_identity(saved):
    connection(saved)
    target = text(saved, 1)
    minimum = max(0, legacy.wait_seconds(text(saved, 3)))
    maximum = legacy.wait_seconds(text(saved, 5))
    flags = saved.contents[4].value
    role = ('none', 'join', 'split', 'meet')[flags & 3]
    return target, role, wait_clock(minimum), wait_clock(maximum) if maximum > 0 else 'HH:MM:SS'


def wait_clock(seconds):
    value = int(seconds)
    legacy.need(value == seconds and 0 <= value < 86400, 'Legacy connection duration must be canonical whole seconds')
    return f'{value//3600:02}:{value//60%60:02}:{value%60:02}'


def check_associations(node, row, course, position, course_mapping):
    expected_train = text(course, 3)
    compositions = node.findall('composition')
    legacy.need(len(compositions) <= 1, f'Multiple source formations at {position}')
    for composition in compositions:
        legacy.need(composition.get('compID') == expected_train and len(composition.findall('service')) == len(composition),
                    f'Legacy composition differs from saved Course Train at {position}')
    source = []
    for ref in node.findall('connection'):
        target, operation = ref.get('trainID'), ref.get('connOperation', 'none')
        legacy.need(target and operation in ('none', 'join', 'split', 'meet') and not len(ref),
                    f'Unsupported legacy connection descriptor at {position}')
        low = legacy.duration(ref.get('minConnTime'), 'minimum connection time')
        high = legacy.duration(ref.get('maxConnTime'), 'maximum connection time') if 'maxConnTime' in ref.attrib else None
        source.append((course_mapping.get(target, target), operation, wait_clock(low),
                       wait_clock(high) if high is not None else 'HH:MM:SS'))
    if source:
        actual = [connection_identity(item) for item in catalogs.array(row.contents[9].value)]
        legacy.need(source == actual, f'Legacy connection targets, waits or operations differ from saved records at {position}')


def ordered_rows(sequence, saved, calculated):
    if not calculated or len(sequence) == len(saved):
        legacy.need(sequence == saved, 'Legacy stop sequence differs from the native timetable')
        return list(range(len(saved)))

    def find(values, pool):
        indices = []
        cursor = 0
        for station in values:
            while cursor < len(pool) and pool[cursor] != station:
                cursor += 1
            legacy.need(cursor < len(pool), 'Calculated RailML rows are not an ordered native timetable subsequence')
            indices.append(cursor)
            cursor += 1
        return indices

    left = find(sequence, saved)
    right = [len(saved)-index-1 for index in reversed(find(sequence[::-1], saved[::-1]))]
    legacy.need(left == right, 'Calculated RailML station sequence has more than one native row mapping')
    return left


def entry_fields(node, position):
    fields = {}
    if 'type' in node.attrib:
        fields['stop_at_station'] = node.get('type') == 'stop'
    track = node.get('trackInfo', node.get('trackID'))
    if track is not None:
        legacy.need(node.get('trackID', track) == track, f'Conflicting trackInfo/trackID at {position}')
        legacy.need(len(track) <= 200 and all(' ' <= char <= '~' and char != '#' for char in track),
                    f'Unsupported native track identity at {position}')
        fields['track_id'] = track
    for label, field in (('minStopTime', 'dwell_s'), ('meanDelayDeparture', 'mean_delay_s')):
        if label in node.attrib:
            fields[field] = legacy.duration(node.get(label), label)
    return fields


def native_entry_fields(row):
    return {'stop_at_station': bool(row.contents[10].value & 1), 'track_id': text(row, 18) or '',
            'dwell_s': text(row, 8) or '0', 'mean_delay_s': text(row, 12) or '0'}


def field_match(field, values, expected):
    if field in ('dwell_s', 'mean_delay_s'):
        try:
            return Decimal(values[field]) == expected
        except ArithmeticError:
            return False
    return values[field] == expected


def patch_entry_fields(blob, changes):
    if not changes:
        return blob
    root, version = writer.load_next_compatible(blob)
    rows = timetable(root)
    selected = [(rows[key], fields) for key, fields in changes.items()]
    counts = incoming_counts(root)
    legacy.need(not counts[id(root)] and all(counts[id(row)] == 1 for row, _ in selected),
                'Shared native timetable owner cannot be changed')
    original_graph = timetable_setters.protected_graph(root, selected, ENTRY_SLOTS)
    untouched_flags = {key: rows[key].contents[10].value & ~1 for key in changes}
    for row, fields in selected:
        apply_row_fields(row, {key: float(value) if isinstance(value, Decimal) else value for key, value in fields.items()})
    output = writer.dump_verified(root, version)
    fresh, _ = writer.load_next_compatible(output)
    restored = timetable(fresh)
    reread = [(restored[key], fields) for key, fields in changes.items()]
    legacy.need(timetable_setters.protected_graph(fresh, reread, ENTRY_SLOTS) == original_graph,
                'Unrelated native timetable graph changed during legacy import')
    for row, fields in reread:
        stored = native_entry_fields(row)
        legacy.need(all(field_match(key, stored, value) for key, value in fields.items()), 'Legacy native field precision lost on save')
    legacy.need(all((restored[key].contents[10].value & ~1) == flags for key, flags in untouched_flags.items()),
                'Legacy entry edit changed unrelated native row flags')
    return output


def verify_planned_clocks(blob, courses):
    rows = timetable(writer.load_next_compatible(blob)[0])
    by_course = defaultdict(list)
    for row in rows.values():
        cid = text(row, 1)
        if cid in courses:
            by_course[cid].append(row)
    for group in by_course.values():
        previous = None
        for row in sorted(group, key=lambda item: item.contents[3].value):
            arrival, departure = (timetable_time(row, kind) for kind in legacy.ENTRY_CLOCKS)
            for stamp in (arrival, departure):
                if stamp is not None:
                    legacy.need(previous is None or stamp >= previous, 'Merged legacy planned clocks go backwards')
                    previous = stamp
            fields = native_entry_fields(row)
            if fields['stop_at_station'] and arrival is not None and departure is not None:
                try:
                    dwell = Decimal(fields['dwell_s'])
                except ArithmeticError as error:
                    raise ValueError('Invalid saved minimum dwell') from error
                legacy.need(dwell.is_finite() and 0 <= dwell <= departure - arrival,
                            'Legacy minimum dwell exceeds planned stop duration')


def changed_clock_fields(rows, clock_edits):
    changed = {}
    for key, edits in clock_edits.items():
        row = rows[key]
        fields = {}
        for field, value in edits.items():
            group, slot, encoding, *_ = timetable_setters.FIELDS[field]
            saved = row.contents[group].values[slot]
            if (writer.string(saved) if encoding == '@' else saved) != value:
                fields[field] = value
        if fields:
            changed[key] = fields
    return changed


def mapped_legacy_import(original, xml, rows, courses, args):
    table, recovered = legacy.legacy_tree(xml, recover_original_footer=args.legacy_recover_footer)
    trains = legacy.train_index(table)
    rows_by_course = defaultdict(list)
    for key, row in rows.items():
        rows_by_course[text(row, 1)].append((key, row))
    calculated = args.time_scope == 'calculated'
    scope = 'calculated' if calculated else 'planned'
    clock_edits, entry_edits, assembly = {}, {}, {}
    for source_id, course_id in args.course_by_train_id.items():
        selected = trains.get((source_id, scope), ())
        legacy.need(len(selected) == 1 and course_id in courses,
                    f'Expected one exact {scope} train and existing Course for {source_id!r} → {course_id!r}')
        course = courses[course_id]
        nodes = legacy.entries(selected[0])
        target = sorted(rows_by_course[course_id], key=lambda entry: entry[1].contents[3].value)
        legacy.need(all(row.contents[3].value == index and row.contents[4].value == len(target) - 1
                        for index, (_, row) in enumerate(target)), 'Native timetable row indices are inconsistent')
        source = [args.station_by_pos_id.get(node.get('posID'), node.get('posID')) for node in nodes]
        expected = [text(row, 5) for _, row in target]
        indices = ordered_rows(source, expected, calculated)
        previous = None
        count = 0
        for node, index in zip(nodes, indices, strict=True):
            key, row = target[index]
            change = {}
            for field in legacy.ENTRY_CLOCKS:
                value = legacy.clock(node.attrib, field, scope=args.time_scope)
                if value is None:
                    continue
                stamp, day, seconds = value
                if seconds is not None:
                    legacy.need(previous is None or seconds >= previous, f'Legacy RailML clocks go backwards at {key}')
                    previous = seconds
                named = 'actual_' + field if calculated else field
                change[named], change[named + '_day_offset'] = stamp, day
            if change:
                clock_edits[key] = change
                count += 1
            check_associations(node, row, course, key, args.course_by_train_id)
            fields = entry_fields(node, key)
            saved = native_entry_fields(row)
            differences = {field: value for field, value in fields.items() if not field_match(field, saved, value)}
            if differences and args.legacy_entry_fields == 'update':
                entry_edits[key] = differences
            else:
                legacy.need(not differences, f'Legacy stop/track/dwell/delay differs from saved fields at {key}')
        legacy.need(count > 0 and previous is not None, f'No actual {args.time_scope} clock selected for {source_id!r}')
        assembly[source_id] = {'course_id': course_id, 'aligned_row_indices': indices, 'time_scope': args.time_scope,
                               'updated_clock_rows': count, 'legacy_interval_group_id': selected[0].get('intervalGroupID')}
    changed = changed_clock_fields(rows, clock_edits)
    if changed:
        output, report = timetable_setters.patch_rows(original, changed)
    else:
        output = original
        report = {'rows': {}, 'time_mode': 'strict', 'fresh_reload_verified': True,
                  'protected_graph_verified': True, 'input_sha256': sha256(original).hexdigest(),
                  'native_application_tested': False, 'interval_reference_and_offset_untouched': True,
                  'runtime_cache_serialized': False}
    output = patch_entry_fields(output, entry_edits)
    if not calculated:
        verify_planned_clocks(output, set(args.course_by_train_id.values()))
    report['output_sha256'] = sha256(output).hexdigest()
    return output, {'assembly': assembly, 'row_count': len(clock_edits), 'rows_with_clock_changes': len(changed),
                    'entry_rows_updated': len(entry_edits),
                    'original_xml_footer_completed': recovered, 'report': report}
