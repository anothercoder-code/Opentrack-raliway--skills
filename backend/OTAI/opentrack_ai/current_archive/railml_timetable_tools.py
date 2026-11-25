"""Import mapped RailML clocks through the current timetable writer."""
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from ..errors import APIError
from ..railml_timetable import RailMLTimetableInventory
from . import catalogs, timetable_setters, writer
from .bundle_tools import Source
from .course_factories import timetable
from .next_tools import NextFunctions, Save
from .operation_tools import Name
from .tools import sha


CLOCKS = ('arrival', 'departure')


class ImportTimetable(Save):
    railml: Source
    timetable: Source
    courses: Source
    course_by_train_id: Annotated[dict[Name, Name], Field(min_length=1, max_length=1000)]
    station_by_ocp_id: Annotated[dict[Name, Name], Field(max_length=10000)] = Field(default_factory=dict)
    time_scope: Literal['scheduled', 'published', 'calculated'] = 'scheduled'
    format: Literal['railml_2_2', 'railml_1_00'] = 'railml_2_2'
    station_by_pos_id: Annotated[dict[Name, Name], Field(max_length=10000)] = Field(default_factory=dict)
    legacy_entry_fields: Literal['match', 'update'] = 'match'
    legacy_recover_footer: StrictBool = False
    connections: Literal['reject', 'match', 'merge'] = 'reject'

    @model_validator(mode='after')
    def version_options(self):
        if self.format == 'railml_2_2' and (self.station_by_pos_id or self.legacy_recover_footer or self.legacy_entry_fields != 'match'):
            raise ValueError('Legacy station and entry options require railml_1_00')
        if self.format == 'railml_1_00' and self.station_by_ocp_id:
            raise ValueError('RailML 1.00 uses station_by_pos_id')
        if self.connections != 'reject' and (self.format != 'railml_2_2' or self.time_scope != 'scheduled'):
            raise ValueError('Connection policies apply only to scheduled RailML 2.2')
        if self.time_scope != 'scheduled' and self.legacy_entry_fields == 'update':
            raise ValueError('Legacy entry fields can be written only with scheduled clocks')
        return self


@dataclass(frozen=True)
class PartRow:
    station: str
    stop: str | None
    times: dict[str, tuple[str, int, int | None]]
    connections: tuple[dict, ...] = ()


def clock(attributes, name):
    value = attributes.get(name)
    day = attributes.get(name + 'Day', '0')
    if re.fullmatch(r'[0-9]{1,3}', day) is None or int(day) > 366:
        raise ValueError(f'Unsupported RailML day offset for {name}')
    if value is None:
        if day != '0':
            raise ValueError(f'Undefined {name} has a day offset')
        return 'HH:MM:SS', 0, None
    match = re.fullmatch(r'([01][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])(?:\.0+)?', value)
    if match is None:
        raise ValueError(f'Unsupported RailML clock for {name}: {value!r}')
    hour, minute, second = map(int, match.groups())
    return value[:8], int(day), int(day) * 86400 + hour * 3600 + minute * 60 + second


def station_sign(inventory, ocp_id, mapping):
    kinds = inventory.ids.get(ocp_id, ())
    if len(kinds) != 1 or kinds[0][0] != 'stations':
        raise ValueError(f'RailML OCP {ocp_id!r} must have one exact definition')
    if ocp_id in mapping:
        return mapping[ocp_id]
    attrs = kinds[0][1]['attributes']
    return attrs.get('abbrevation', attrs.get('code', attrs.get('name', ocp_id)))


def ordered_part_ids(train, references):
    train_id = train['id']
    if not references:
        raise ValueError(f'RailML train {train_id!r} must reference at least one trainPart')
    if len(references) > 1:
        slots = [ref['sequence_index'] for ref in references]
        if train['part_sequence_count'] != len(references) or slots != list(range(len(references))):
            raise ValueError(f'RailML train {train_id!r} requires exactly one trainPartRef in each direct trainPartSequence')
        previous = 0
        for reference in references:
            value = reference['sequence']
            number = int(value) if value is not None and re.fullmatch(r'\+?[0-9]+', value) else 0
            if number <= previous:
                raise ValueError(f'RailML train {train_id!r} needs positive, increasing trainPartSequence numbers in XML order')
            previous = number
    return [ref['target_id'] for ref in references]


def read_part(inventory, part_id, raw_rows, times_by_row, args):
    plan = []
    for row in raw_rows:
        key = f'{part_id}#{row["index"]}'
        mapped = station_sign(inventory, row['ocp_ref'], args.station_by_ocp_id)
        stop = row['attributes'].get('ocpType')
        if stop not in (None, 'stop', 'pass'):
            raise ValueError(f'Unsupported RailML ocpType {stop!r} at {key}')
        if row['connection_count'] and args.connections == 'reject':
            raise ValueError(f'RailML connections require a separate reviewed mapping at {key}')
        connections = tuple(inventory.connections[row['part_order'], row['index']]) if row['connection_count'] else ()
        blocks = times_by_row[row['part_order'], row['index']]
        if len(blocks) != 1:
            raise ValueError(f'Expected one {args.time_scope!r} time block at {key}')
        plan.append(PartRow(mapped, stop, {name: clock(blocks[0], name) for name in CLOCKS}, connections))
    return plan


def join_boundary(left, right, train_id):
    if left.station != right.station:
        raise ValueError(f'RailML train {train_id!r} has a trainPart boundary mismatch: {left.station!r} → {right.station!r}')
    times = {}
    for name in CLOCKS:
        earlier, later = left.times[name], right.times[name]
        if earlier[2] is not None and later[2] is not None and earlier != later:
            raise ValueError(f'Conflicting RailML {name} at train {train_id!r} boundary {left.station!r}')
        times[name] = earlier if earlier[2] is not None else later
    stop = 'stop' if 'stop' in (left.stop, right.stop) else left.stop or right.stop
    return PartRow(left.station, stop, times, left.connections + right.connections)


def clock_edits(rows, courses, inventory, args):
    if len(set(args.course_by_train_id.values())) != len(args.course_by_train_id):
        raise ValueError('Each mapped train must target a different Course')
    rows_by_course, rows_by_part, times_by_row, parts_by_train = (defaultdict(list) for _ in range(4))
    for key, row in rows.items():
        rows_by_course[catalogs.text(row.contents[1].value)].append((key, row))
    for row in inventory.data['rows']:
        rows_by_part[row['part_order']].append(row)
    for block in inventory.data['times']:
        if block['scope'] == args.time_scope:
            times_by_row[block['part_order'], block['row_index']].append(block['attributes'])
    for reference in inventory.data['references']:
        if 'train_order' in reference and reference['target_kind'] == 'train_parts':
            parts_by_train[reference['train_order']].append(reference)
    edits = {}
    assembly = {}
    connections = {}
    for train_id, course in args.course_by_train_id.items():
        trains = inventory.ids.get(train_id, ())
        if len(trains) != 1 or trains[0][0] != 'trains' or courses.count(course) != 1:
            raise ValueError(f'Expected one exact RailML train and existing Course for {train_id!r} → {course!r}')
        train = trains[0][1]
        parts = ordered_part_ids(train, parts_by_train[train['document_order']])
        target_rows = sorted(rows_by_course[course], key=lambda entry: entry[1].contents[3].value)
        plan, boundaries = [], []
        for part_id in parts:
            part = inventory.ids.get(part_id, ())
            if len(part) != 1 or part[0][0] != 'train_parts':
                raise ValueError(f'Unresolved or ambiguous RailML trainPart {part_id!r}')
            raw_rows = rows_by_part[part[0][1]['document_order']]
            if not raw_rows:
                raise ValueError(f'RailML trainPart {part_id!r} contains no timetable rows')
            remaining_rows = len(target_rows) - len(plan) + bool(plan)
            if len(raw_rows) > remaining_rows:
                raise ValueError(f'Stop sequence length differs for Course {course!r}')
            segment = read_part(inventory, part_id, raw_rows, times_by_row, args)
            if plan:
                plan[-1] = join_boundary(plan[-1], segment[0], train_id)
                boundaries.append({'row_index': len(plan) - 1, 'station': plan[-1].station})
                segment = segment[1:]
            plan.extend(segment)
        if len(plan) != len(target_rows):
            raise ValueError(f'Stop sequence length differs for Course {course!r}')
        previous = None
        for index, (item, (key, row)) in enumerate(zip(plan, target_rows, strict=True)):
            if (row.contents[3].value != index or row.contents[4].value != len(plan) - 1
                    or item.station != catalogs.text(row.contents[5].value)):
                raise ValueError(f'Native station order or row index differs at {key}')
            if item.stop is not None and item.stop != ('stop' if row.contents[10].value & 1 else 'pass'):
                raise ValueError(f'Mapped stop/pass status differs at {key}')
            fields = {}
            for name, (value, day, seconds) in item.times.items():
                if seconds is not None:
                    if previous is not None and seconds < previous:
                        raise ValueError(f'RailML times go backwards at {key}')
                    previous = seconds
                field = 'actual_' + name if args.time_scope == 'calculated' else name
                fields[field], fields[field + '_day_offset'] = value, day
            edits[key] = fields
            if item.connections:
                connections[key] = item.connections
        assembly[train_id] = {'course_id': course, 'train_part_ids': parts, 'boundaries': boundaries}
    return edits, assembly, connections


class RailMLWriter(NextFunctions):
    def import_timetable(self, args):
        xml_path = self.path(args.railml.path)
        xml = self.secure_bytes(xml_path)
        if sha(xml) != args.railml.sha256:
            raise APIError('SOURCE_CHANGED', 'RailML source differs from the inspected SHA-256')
        source, original, root, _ = self.checked(args.timetable)
        course_path, course_bytes, course_root, _ = self.checked(args.courses)
        if (source.suffix != '.timetable' or course_path.suffix != '.courses'
                or source.parent != course_path.parent or xml_path.suffix.lower() not in {'.xml', '.railml'}
                or (not args.preview_only and self.path(args.target_path).suffix != '.timetable')):
            raise APIError('RAILML_TIMETABLE_SCOPE', 'Use explicit RailML and same-directory native timetable/Course files')
        try:
            courses = {catalogs.text(row.contents[0].value): row for row in catalogs.course_items(course_root)}
            if args.format == 'railml_1_00':
                from .railml_v100_timetable_import import mapped_legacy_import

                if len(set(args.course_by_train_id.values())) != len(args.course_by_train_id):
                    raise ValueError('Each mapped legacy train must target a different Course')
                output, details = mapped_legacy_import(original, xml, timetable(root), courses, args)
            else:
                inventory = RailMLTimetableInventory().parse(xml, reject_doctype=True)
                edits, assembly, batches = clock_edits(timetable(root), list(courses), inventory, args)
                output, report = timetable_setters.patch_rows(original, edits)
                details = {'row_count': len(edits), 'assembly': assembly, 'report': report}
                if args.connections != 'reject':
                    from .railml_connection_import import apply_connections

                    output, details['connections'] = apply_connections(
                        output, batches, assembly, inventory, args.connections,
                        lambda identifier: station_sign(inventory, identifier, args.station_by_ocp_id))
        except (ValueError, TypeError, IndexError, OverflowError) as exc:
            raise APIError('RAILML_TIMETABLE_IMPORT', str(exc)[:500]) from exc
        result = {'saved': False, 'preview_only': args.preview_only, 'time_scope': args.time_scope,
                  'format': args.format, 'source_sha256': sha(original), 'output_sha256': sha(output), **details}
        inputs = {course_path: course_bytes, xml_path: xml}
        if args.preview_only:
            if any(self.secure_bytes(path) != blob for path, blob in {source: original, **inputs}.items()):
                raise APIError('SOURCE_CHANGED', 'A timetable import dependency changed during preview')
            return result

        def verify(blob):
            timetable(writer.load_next_compatible(blob)[0])

        return self.save_copy(source, original, output, result, args.target_path,
                              additional_inputs=inputs, validate_output=verify)


def tool_definitions(root):
    from .railml_v100_timetable_tools import tool_definitions as native_legacy_export
    from .railml_v220_timetable_tools import tool_definitions as native_current_export

    service = RailMLWriter(root)
    return [('opentrack_import_railml_timetable',
             'Import explicitly mapped RailML 2.2 trainParts or RailML 1.00 direct train records into existing native timetable rows. '
             'Supports scheduled, published and calculated times, and optional declared 1.00 scheduled entry fields. '
             'Optionally match or merge explicitly bound scheduled RailML 2.2 connections. '
             'Preview or save a fresh timetable copy with existing Course owners preserved.',
             ImportTimetable, service.import_timetable, False, False),
            *native_legacy_export(root), *native_current_export(root)]
