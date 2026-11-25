"""Build a complete one-or-more worksheet native project with no railway objects."""

from .. import path_functions, route_factory, writer
from ..multi_document.bundle import validate_no_service_bundle
from ..tools import sha
from ..zero_operations import run_bundle
from . import topology


CATALOG_SHAPES = {
    'dest': 'OTDestInfoList', 'depot': 'NSMutableArray', 'trains': 'OTTrainList',
    'courses': 'OTCourseList', 'stations': 'NSMutableDictionary', 'timetable': 'NSMutableDictionary',
}
WORKSHEET_COLLECTIONS = (2, 5, 12)


def worksheet_header_fingerprint(root):
    fields = list(root.contents)
    for slot in WORKSHEET_COLLECTIONS:
        fields[slot] = writer.TypedValue(b'@', None)
    header = writer.GenericArchivedObject(root.clazz, contents=fields)
    return writer.fingerprint(header)


def build_empty_project(header_document, shape_archive, *, document_names, execution_root, run_filename, train_types,
                        simulation=None, additional_outputs=()):
    run_bundle.relative(run_filename)
    topology.need('/' not in run_filename and run_filename.endswith('.run'), 'A root-level native .run filename is required')
    topology.need(1 <= len(document_names) <= 100 and len({name.casefold() for name in document_names}) == len(document_names),
                  'Use one to 100 distinct worksheet names, including under case folding')
    source, _ = writer.load_next_compatible(header_document)
    builder = topology.Builder(shape_archive)
    blank, version, removed = topology.blank_container(header_document, builder)
    worksheet = writer.dump_verified(blank, version)
    saved, _ = writer.load_next_compatible(worksheet)
    topology.doc_layout(saved)
    topology.need(not path_functions.mutable_array(saved.contents[2].value)
                  and not path_functions.mutable_array(saved.contents[5].value.contents[0].value)
                  and not route_factory.wrapper(saved.contents[12].value, 'OTOccInfoList')
                  and worksheet_header_fingerprint(saved) == worksheet_header_fingerprint(source),
                  'Native blank worksheet readback must leave all three collections empty and retain the source header')

    documents = [run_bundle.relative(f'OTDocuments/{name}.opentrack') for name in document_names]
    catalog_paths = {role: f'OTData/empty.{role}' for role in CATALOG_SHAPES}
    files = dict.fromkeys(documents, worksheet)
    for role, shape in CATALOG_SHAPES.items():
        topology.need(shape in builder.protos, f'Missing verified native catalogue shape {shape}')
        files[catalog_paths[role]] = writer.dump_verified(builder.protos[shape], builder.stream_version)

    template = b''
    if additional_outputs:
        extra = [run_bundle.OPTIONAL_CONSTRUCTION_OUTPUTS[key] for key in additional_outputs]
        template = ''.join(f'{key}#{value}#\n' for key, value in (*run_bundle.FRESH_RUN_OPTIONS, *extra)).encode('ascii')
    files[run_filename], run = run_bundle.build_run(
        files, catalog_paths=catalog_paths, document_paths=documents, execution_root=execution_root,
        path_style='windows', train_types=train_types, template=template, **(simulation or {}),
    )
    inventory = {path: sha(data) for path, data in files.items()}
    verification = validate_no_service_bundle(files, run_file=run_filename, expected_hashes=inventory, complete_file_set=True)
    topology.need(verification['station_count'] == verification['destination_count'] == 0,
                  'The empty native project may not contain a station or itinerary definition')
    return files, {
        'source_sha256': {'header_document': sha(header_document), 'shape_archive': sha(shape_archive)},
        'source_graphics_excluded': removed, 'worksheet_header_preserved': True,
        'document_members': documents, 'catalog_members': catalog_paths, 'run_member': run_filename,
        'simulation_window': run['window'], 'additional_outputs': list(additional_outputs),
        'member_sha256': inventory, 'validation': verification,
    }
