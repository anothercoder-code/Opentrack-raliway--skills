"""Direct current-codec RailML 2.2 exchange export and SHA-bound publication."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..errors import APIError
from ..models import RailMLTimetableOptions
from ..railml_timetable import RailMLTimetableInventory
from ..timetable_railml_export import render_saved_timetable
from . import catalogs, course_factories
from .bundle_tools import Source
from .formation_operations import trailer
from .next_tools import NextFunctions, Save
from .operating_plan_edit import text
from .operation_tools import Name
from .railml_v100_timetable_tools import extract_course, extract_row
from .station_exchange import read_catalog
from .tools import sha


class ExportRailML220(Save):
    timetable: Source
    courses: Source
    stations: Source
    trains: Source
    depot: Source
    course_ids: Annotated[list[Name], Field(max_length=1000)] = Field(default_factory=list)
    railml: RailMLTimetableOptions | None = None
    saved_actual: Literal['omit', 'as_valid'] = 'omit'

    @model_validator(mode='after')
    def choices(self):
        if self.saved_actual == 'as_valid' and not (self.railml and self.railml.calculated):
            raise ValueError('Saved actual-clock export requires railml.calculated=true')
        return self


def dimensions(vehicle):
    return {'mass_t': vehicle.contents[2].values[1], 'length_m': vehicle.contents[2].values[2]}


def stock(train_root, depot_root):
    trains = [{'name': text(train, 0), 'engines': catalogs.bound_engine_names(train),
               'trailers': [dimensions(trailer(item)) for item in catalogs.array(train.contents[2].values[2])]}
              for train in catalogs.train_items(train_root)]
    engines = [{'name': text(engine, 1), **dimensions(engine)} for engine in catalogs.engine_items(depot_root)]
    known = {engine['name'] for engine in engines}
    missing = sorted({name for train in trains for name in train['engines'] if name not in known})
    if missing:
        raise ValueError(f'Supplied Depot does not contain saved formation Engines: {missing[:10]}')
    return trains, engines


class NativeRailML220Export(NextFunctions):
    def export_timetable(self, args):
        kinds = ('timetable', 'courses', 'stations', 'trains', 'depot')
        inputs = {kind: self.checked(getattr(args, kind)) for kind in kinds}
        source, raw, table, _ = inputs['timetable']
        if any(path.suffix.casefold() != '.' + kind for kind, (path, *_) in inputs.items()):
            raise APIError('RAILML_TIMETABLE_SCOPE', 'Use explicit current archive suffixes for the timetable and catalogs')
        if any(inputs[kind][0].parent != source.parent for kind in ('courses', 'stations', 'trains')):
            raise APIError('RAILML_TIMETABLE_SCOPE', 'Use timetable, Course, Station and Train catalogs from the same folder')
        if args.target_path is not None and self.path(args.target_path).suffix.casefold() not in ('.xml', '.railml'):
            raise APIError('RAILML_TIMETABLE_SCOPE', 'Use a new XML or RailML target')
        try:
            stations = read_catalog(inputs['stations'][1])[3]
            trains, engines = stock(inputs['trains'][2], inputs['depot'][2])
            courses = [{'course_id': text(row, 0), **extract_course(row)}
                       for row in catalogs.course_items(inputs['courses'][2])]
            all_rows = [extract_row(key, row) for key, row in course_factories.timetable(table).items()]
            selected = set(args.course_ids)
            if len(selected) != len(args.course_ids) or selected - {row['course_id'] for row in all_rows}:
                raise ValueError('Select distinct saved Courses with existing timetable rows')
            rows = sorted((row for row in all_rows if not selected or row['course_id'] in selected),
                          key=lambda row: (row['course_id'], row['index']))
            content, warnings, report = render_saved_timetable(
                rows, args, stations=stations, stock=trains, engine_records=engines, course_records=courses,
                all_rows=all_rows, dwell={row['key']: row['dwell_raw'] or '' for row in rows},
                project_name=source.stem)
            output = content.encode('ascii')
        except (ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
            raise APIError('RAILML_TIMETABLE_220_EXPORT', str(exc)[:500]) from exc

        def verify(blob):
            inventory = RailMLTimetableInventory().parse(blob, reject_doctype=True)
            if sum(map(len, inventory.connections.values())) != report['connections']:
                raise ValueError('RailML export connection count failed readback')

        verify(output)
        dependencies = {path: blob for kind, (path, blob, *_) in inputs.items() if kind != 'timetable'}
        result = {'saved': False, 'preview_only': args.preview_only, 'format': 'railml_2_2',
                  'source_sha256': sha(raw), 'output_sha256': sha(output), 'output_bytes': len(output),
                  'warnings': warnings[:100], 'warning_count': len(warnings), 'native_application_started': False,
                  **report}
        if args.preview_only:
            if any(self.secure_bytes(path) != blob for path, blob in {source: raw, **dependencies}.items()):
                raise APIError('SOURCE_CHANGED', 'A RailML export dependency changed during preview')
            return result
        return self.save_copy(source, raw, output, result, args.target_path,
                              additional_inputs=dependencies, validate_output=verify)


def tool_definitions(root):
    return [('opentrack_export_native_railml_220_timetable',
             'Export original RailML 2.2 from SHA-bound current timetable, Course, Station, Train and Depot archives. '
             'Supports clock scopes, formations, OCP and train references, and optional corrected cross-station Connection references.',
             ExportRailML220, NativeRailML220Export(root).export_timetable, False, False)]
