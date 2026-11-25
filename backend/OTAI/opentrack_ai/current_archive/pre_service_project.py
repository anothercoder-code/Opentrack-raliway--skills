"""Validate a bound native construction project before timetable entry."""

from collections import defaultdict

from . import catalogs, course_factories, runfile_parameters, writer
from .itinerary_edit_tools import EditableItineraryProject
from .multi_document.core import layout, need, stem
from .prepare_contract import auxiliary
from .saved_station_areas import station_model
from .tools import sha
from .zero_operations import run_bundle


def _station_bindings(project, catalog):
    models, references = {}, set()
    for document, graphics in project.models.items():
        local = [station_model(project, document, item.contents[0].value, require_reference=False)
                 for item in graphics if writer.kind(item) == 'OTStationModel']
        for station in local:
            sign = writer.string(station.contents[7].value)
            need(sign in catalog, 'Saved StationModel is absent from the run-bound StationFile')
            models[document, station.contents[0].value] = {'station_sign': sign, 'member_end_ids': [], 'reference_end_ids': []}
        for end in project.ends(document):
            station = end.contents[12].value
            kind = end.contents[20].value
            if station is None:
                need(kind != 2, 'Saved station reference End has no StationModel')
                continue
            need(station in local and kind in (1, 2), 'Unbound or unsupported saved station area End')
            end_key = project.key(end)
            paired = project.model(project.related(end_key))
            need((writer.kind(paired) == 'OTConnModel' and kind == 1)
                 or (paired.contents[12].value is station and paired.contents[20].value == kind),
                 'Saved station area membership or type differs between reciprocal directional Ends')
            binding = models[document, station.contents[0].value]
            binding['member_end_ids'].append(end_key[1])
            if kind == 2:
                binding['reference_end_ids'].append(end_key[1])
                references.add(binding['station_sign'])

    need(all(row['member_end_ids'] and row['station_sign'] in references for row in models.values()),
         'A saved StationModel lacks an attached End or its station sign lacks a native reference End')
    return [{'document': document, 'station_id': number, **row} for (document, number), row in models.items()]


def validate_pre_service_project(files, *, run_file, execution_root):
    """Read back complete immutable bytes, allowing stock and station areas with zero services."""
    source = run_bundle.root_path(execution_root, 'windows')
    need(source == execution_root, 'Use a canonical native project execution root')
    run_bundle.relative(run_file)
    need(run_file.endswith('.run'), 'Use an explicit original .run member')
    rows = auxiliary.records(files[run_file])
    selected = defaultdict(list)
    for key, value, _ in rows:
        selected[key].append(value)
    need(not selected['Incident'], 'The pre-service project cannot select a native incident')

    def member(declared):
        need(declared.startswith(source + '/'), 'Bound member is outside the exact native execution root')
        return run_bundle.relative(declared[len(source) + 1:])

    catalogs_by_role = {}
    for role, key in run_bundle.CATALOG_KEYS.items():
        need(len(selected[key]) == 1, 'Every native catalogue role requires one explicit binding')
        catalogs_by_role[role] = member(selected[key][0])
    document_paths = selected['Infrastructure Document']
    diagram_paths = selected['Train Diagram Document']
    need(len(selected['OutputPath']) == 1, 'A native output directory must be declared once')
    paths = [member(path) for path in document_paths]
    diagrams = [member(path) for path in diagram_paths]
    output = member(selected['OutputPath'][0])
    need(output.casefold() != run_file.casefold()
         and not run_file.casefold().startswith(output.casefold() + '/')
         and not output.casefold().startswith(run_file.casefold() + '/'), 'Native output directory overlaps the run file')
    run_bundle._layout({name: data for name, data in files.items() if name != run_file}, catalogs_by_role,
                       paths, diagrams, output)
    auxiliary.set_bindings(rows, set(document_paths + diagram_paths))
    need(runfile_parameters.inspect_runfile(auxiliary.core_bytes(rows))['editable'], 'Invalid native run time or step')
    types = selected['TrainType']
    need(types and len(types) == len({name.casefold() for name in types}), 'The run requires an explicit unique TrainType order')

    names = [stem(path) for path in paths]
    need(len({name.casefold() for name in names}) == len(names), 'Worksheet names must uniquely bind native document lookups')
    docs = {name: files[path] for name, path in zip(names, paths, strict=True)}
    keyed = dict(zip(names, document_paths, strict=True))
    project = EditableItineraryProject(docs, document_paths=keyed, complete_document_set=True,
                                       expected_hashes={name: sha(data) for name, data in docs.items()})
    project.check_dest_catalog(files[catalogs_by_role['dest']])

    def load(role):
        return writer.load_next_compatible(files[catalogs_by_role[role]])[0]

    course_root = load('courses')
    need(not catalogs.course_items(course_root) and course_root.contents[0].value == 17
         and not catalogs.array(course_root.contents[1].value),
         'The pre-service project requires zero saved Courses and incidents in the current archive')
    timetable = load('timetable')
    need(not course_factories.timetable(timetable), 'The pre-service project requires zero saved timetable rows')
    layout(timetable, [('NSMutableDictionary', 0), ('NSDictionary', 0), ('NSObject', 0)], ['i'])
    stations = catalogs.station_items(load('stations'))
    bindings = _station_bindings(project, stations)
    for relative, absolute in zip(diagrams, diagram_paths, strict=True):
        auxiliary.diagram_binding(files[relative], absolute, stations)
    train_root = load('trains')
    trains = catalogs.train_items(train_root)
    need(train_root.contents[0].value == 17, 'The pre-service project requires a current TrainList marker')
    return {'catalog_paths': catalogs_by_role, 'worksheet_members': paths, 'output_directory': output,
            'course_count': 0, 'timetable_count': 0, 'incident_count': 0, 'train_types': types,
            'engine_count': len(catalogs.engine_items(load('depot'))), 'train_count': len(trains),
            'station_catalog_signs': list(stations), 'station_model_bindings': bindings,
            'destination_count': len(project.dests), 'destination_bindings_verified': True,
            'native_runtime_ready': False}
