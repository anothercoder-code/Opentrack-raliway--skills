"""Direct standard and OTT RailML 1.00 export from current typed archives."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..errors import APIError
from ..models import RailMLTimetableOptions
from ..railml_timetable_v100 import legacy_tree, train_index
from ..railml_timetable_v100_export import render_legacy_railml
from . import catalogs, writer
from .bundle_tools import Source
from .course_factories import timetable
from .native_connections import connection
from .next_tools import NextFunctions, Save
from .operating_plan_edit import text
from .operation_tools import Name
from .station_exchange import read_catalog
from .tools import sha


class ExportRailML100(Save):
    timetable: Source
    courses: Source
    stations_catalog: Source | None = None
    course_ids: Annotated[list[Name], Field(max_length=1000)] = Field(default_factory=list)
    railml: RailMLTimetableOptions | None = None
    saved_actual: Literal['omit', 'as_valid'] = 'omit'
    variant: Literal['standard', 'ott'] = Field(
        default='standard',
        description='OTT keeps the operating date without a time and defaults to 2007-01-01 for calculated trains.',
    )

    @model_validator(mode='after')
    def requirements(self):
        if self.saved_actual == 'as_valid' and not (self.railml and self.railml.calculated):
            raise ValueError('Saved actual-clock export requires railml.calculated=true')
        if self.railml and self.railml.existing_stations_only and self.stations_catalog is None:
            raise ValueError('Existing stations filtering requires the native station catalog')
        if self.railml and self.railml.connection_ocp_reference != 'original':
            raise ValueError('connection_ocp_reference applies only to RailML 2.2')
        if self.variant == 'ott' and self.railml and self.railml.calculated and self.railml.metadata_date:
            operating_date = self.railml.metadata_date.rstrip(' ')
            try:
                if date.fromisoformat(operating_date).isoformat() != operating_date:
                    raise ValueError
            except ValueError as exc:
                raise ValueError('OTT calculated metadata_date must be an operating date YYYY-MM-DD') from exc
        return self


def extract_course(row):
    fields = {name: text(row, slot) for name, slot in (('train', 3), ('comment', 11), ('description', 10),
              ('train_number', 13), ('course_type', 14))}
    return {**fields, 'enabled': bool(row.contents[5].value)}


def extract_row(key, row):
    fields = {name: text(row, slot) for name, slot in (('course_id', 1), ('station_sign', 5), ('arrival', 6),
              ('departure', 7), ('dwell_raw', 8), ('mean_delay_raw', 12), ('actual_arrival', 13),
              ('actual_departure', 14), ('interval_reference_course_id', 2), ('track_id', 18))}
    fields.update(zip(('arrival_day_offset', 'departure_day_offset', 'actual_arrival_day_offset', 'actual_departure_day_offset'),
                      row.contents[15].values, strict=True))
    refs = []
    connections = row.contents[9].value
    for item in catalogs.array(connections) if connections is not None else ():
        connection(item)
        flags = item.contents[4].value
        refs.append({'target_course_id': text(item, 1), 'minimum_wait': text(item, 3), 'maximum_wait': text(item, 5),
                     'station_sign': text(item, 2), 'target_station_sign': text(item, 6),
                     'maximum_wait_is_nil': item.contents[5].value is None,
                     'join': bool(flags & 1), 'split': bool(flags & 2)})
    return {**fields, 'key': key, 'index': row.contents[3].value, 'last_index': row.contents[4].value,
            'stop_at_station': bool(row.contents[10].value & 1), 'connections': refs}


def verify_output(raw):
    root, _ = legacy_tree(raw)
    if len(root):
        train_index(root)


class NativeRailML100Export(NextFunctions):
    def export_timetable(self, args):
        table_path, table_blob, table, _ = self.checked(args.timetable)
        course_path, course_blob, course, _ = self.checked(args.courses)
        if table_path.suffix != '.timetable' or course_path.suffix != '.courses' or table_path.parent != course_path.parent:
            raise APIError('RAILML_TIMETABLE_SCOPE', 'Use native timetable and Course files from one saved catalog directory')
        target = self.path(args.target_path) if args.target_path is not None else None
        if target is not None and target.suffix.casefold() not in ('.xml', '.railml'):
            raise APIError('RAILML_TIMETABLE_SCOPE', 'Use a new XML or RailML target')
        station_rows = {}
        sources = {course_path: course_blob}
        try:
            if args.stations_catalog is not None:
                stations = self.path(args.stations_catalog.path)
                raw = self.secure_bytes(stations)
                if stations.suffix != '.stations' or sha(raw) != args.stations_catalog.sha256:
                    raise ValueError('Native station catalog path or checksum does not match')
                sources[stations] = raw
                station_rows = read_catalog(raw)[3]
            services = {text(row, 0): extract_course(row) for row in catalogs.course_items(course)}
            rows = [extract_row(key, row) for key, row in timetable(table).items()]
            wanted = set(args.course_ids)
            if len(wanted) != len(args.course_ids) or wanted - {row['course_id'] for row in rows}:
                raise ValueError('Select distinct saved Courses with existing timetable rows')
            rows = sorted((row for row in rows if not wanted or row['course_id'] in wanted),
                          key=lambda row: (row['course_id'], row['index']))
            content, warnings, report = render_legacy_railml(rows, services, station_rows.keys(), args, ott=args.variant == 'ott')
            output = content.encode('utf-8')
        except (ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
            raise APIError('RAILML_TIMETABLE_100_EXPORT', str(exc)[:500]) from exc
        result = {'saved': False, 'preview_only': args.preview_only, 'format': 'railml_1_00', 'variant': args.variant,
                  'source_sha256': sha(table_blob), 'output_sha256': sha(output), 'output_bytes': len(output),
                  'warnings': warnings[:100], 'warning_count': len(warnings), 'native_application_started': False, **report}
        if args.preview_only:
            if any(self.secure_bytes(path) != blob for path, blob in {table_path: table_blob, **sources}.items()):
                raise APIError('SOURCE_CHANGED', 'An export input changed during preparation')
            return result
        return self.save_copy(table_path, table_blob, output, result, args.target_path,
                              additional_inputs=sources, validate_output=verify_output)


def tool_definitions(root):
    return [('opentrack_export_native_railml_100_timetable',
             'Export standard or original OTT RailML 1.00 train and entry records from exact native timetable and Course archives. '
             'Use scheduled/published or saved calculated clock scopes with explicit filters and no original launch.',
             ExportRailML100, NativeRailML100Export(root).export_timetable, False, False)]
