"""Publish mapped native station facilities inside one complete pre-service project."""

from ..errors import APIError
from . import writer
from .itinerary_edit_tools import EditableItineraryProject
from .multi_document.core import need
from .multi_document_tools import MultiDocumentTools
from .pre_service_project import validate_pre_service_project
from .project_candidate_publication import publish_candidate
from .project_workflow.relocation import relocate_project
from .station_exchange import import_station_objects, read_catalog
from .tools import sha
from .zero_generation.empty_project import worksheet_header_fingerprint


def _merge_catalog(original, incoming):
    if incoming is None:
        return original, []
    _, _, saved, _ = read_catalog(original, mutable=True)
    _, _, additions, _ = read_catalog(incoming, mutable=True)
    need(all(record.clazz.version == 3 for record in saved.values()),
         'Existing Station records must use the current layout for preservation in a facility project')
    spellings = [sign.casefold() for sign in (*saved, *additions)]
    need(len(spellings) == len(set(spellings)),
         'An imported RailML station sign conflicts with an existing native StationFile sign')
    combined, _ = import_station_objects(original, incoming, list(additions), 'reject')
    _, _, observed, _ = read_catalog(combined, mutable=True)
    expected = {**saved, **additions}
    need(list(observed) == list(expected) and all(
        writer.fingerprint(observed[sign]) == writer.fingerprint(record) for sign, record in expected.items()),
        'Native StationFile readback differs from its existing and newly mapped Station records')
    return combined, list(additions)


def publish_facility_project(tools, args, target, worksheet_path, worksheet_data, revised_sheet, new_catalog, result,
                             recheck_facility):
    project_tools = MultiDocumentTools(tools.root)
    state = project_tools.load_project(args.source_project, minimum_documents=1)
    if state['base'].as_posix() != state['root']:
        raise APIError('RAILML_FACILITY_PROJECT', 'Use the construction project at its actual native execution root')
    if target is not None and (target.is_relative_to(state['base']) or state['base'].is_relative_to(target)):
        raise APIError('RAILML_FACILITY_PROJECT', 'Use a fresh destination outside the existing project inventory')
    matches = [member for member in state['document_members'].values() if state['base'] / member == worksheet_path]
    if len(matches) != 1 or state['files'][matches[0]] != worksheet_data:
        raise APIError('RAILML_FACILITY_PROJECT', 'The selected worksheet must be an exact member bound by this .run')
    worksheet, = matches
    run = args.source_project.run_file
    original = state['files']
    catalog = state['roles']['stations']
    protected = {member: sha(original[member]) for role, member in state['roles'].items()
                 if role in ('courses', 'timetable', 'trains', 'depot')}
    execution_root = state['root'] if target is None else target.as_posix()
    try:
        validate_pre_service_project(original, run_file=run, execution_root=state['root'])
        before, _ = writer.load_next_compatible(worksheet_data)
        after, _ = writer.load_next_compatible(revised_sheet)
        need(worksheet_header_fingerprint(before) == worksheet_header_fingerprint(after),
             'Mapped RailML facilities changed the native protected worksheet header')
        new_stations, created = _merge_catalog(original[catalog], new_catalog)
        members = {**original, worksheet: revised_sheet, catalog: new_stations}
        relocation = None
        if target is not None:
            members, relocation = relocate_project(
                members, source_root=state['root'], target_root=execution_root, run_file=run,
                expected_hashes={name: sha(data) for name, data in members.items()}, project_type=EditableItineraryProject,
            )
        verification = validate_pre_service_project(members, run_file=run, execution_root=execution_root)
        need(all(sha(members[name]) == digest for name, digest in protected.items()),
             'Facilities publication altered an operating archive')
        document = next(label for label, member in state['document_members'].items() if member == worksheet)
        observed = {row['station_sign'] for row in verification['station_model_bindings'] if row['document'] == document}
        need(set(created) == observed, 'New StationFile records and worksheet StationModels differ')
    except (ValueError, KeyError, IndexError, TypeError, OverflowError) as exc:
        raise APIError('RAILML_FACILITY_PROJECT', str(exc)[:600]) from exc

    report = {
        **result, 'members': {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in members.items()},
        'source_project': project_tools.source_receipt(args, state), 'source_project_modified': False,
        'run_member': run, 'worksheet_member': worksheet, 'station_catalog_member': catalog,
        'inserted_station_signs': created, 'preserved_operating_catalogue_sha256': protected,
        'complete_project_validation': verification, 'relocation': relocation,
        'native_runtime_ready': False,
    }

    def recheck():
        project_tools.recheck(state)
        recheck_facility()

    recheck()
    return report if args.preview_only else publish_candidate(tools, target, members, report, recheck)
