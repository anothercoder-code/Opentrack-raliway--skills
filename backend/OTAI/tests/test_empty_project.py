"""Blank original-format project publication and first geometry edits."""

import json
import os

import pytest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.empty_project_tools import EmptyCurrentProjectTools, InitializeEmptyCurrentProject
from opentrack_ai.current_archive.itinerary_edit_tools import run_infrastructure_paths
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.saved_geometry import project_from, transform
from opentrack_ai.current_archive.tools import ArchiveTools, sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native, topology
from opentrack_ai.current_archive.zero_generation.empty_project import build_empty_project
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import schematic_document
from test_saved_geometry import shapes_for


def sources(*, nonempty=False):
    drawn, _ = schematic_document(generate.spec(), [])
    root, version = writer.load_next_compatible(drawn)
    root.contents[19].value = native.string('Document import provenance')
    header = writer.dump_verified(root, version)
    proto, _ = writer.load_next_compatible(shapes_for(header))
    prototypes = [item for item in path_functions.mutable_array(proto) if writer.kind(item) != 'NSMutableDictionary']
    class_shapes = [
        native.obj([('NSMutableDictionary', 0), ('NSDictionary', 0), ('NSObject', 0)], [('i', [0])]),
        generate.wrapped('OTDestInfoList', []),
        native.obj([('OTCourseList', 3), ('OTMutableArray', 0), ('NSObject', 0)],
                   [('i', [17])] + [('@', [native.arr()]) for _ in range(4)]),
        native.obj([('OTTrainList', 3), ('OTMutableArray', 0), ('NSObject', 0)], [
            ('i', [17]), ('@', [native.arr()]), ('@', [native.arr([native.string('extra')]) if nonempty else native.arr()]),
            ('@', [native.arr()]),
        ]),
    ]
    shapes = writer.dump_verified(native.arr([*prototypes, *class_shapes]), version)
    return header, shapes


def spec(**changes):
    return {'document_names': ['Station', 'Link'], 'execution_root': 'D:/Test/StationStart',
            'run_filename': 'starter.run', 'train_types': ['instructional'], **changes}


@pytest.fixture
def stable_fixture_reads(monkeypatch):
    # These synthetic cases exercise archive contracts independently of Windows handle identity checks.
    monkeypatch.setattr(ArchiveTools, 'secure_bytes', lambda self, path: path.read_bytes())


def test_empty_project_enables_the_first_two_vertices_and_track():
    header, shapes = sources()
    files, saved = build_empty_project(header, shapes, **spec())
    assert len(files) == 9 and saved['validation']['no_service_catalogs']
    assert saved['worksheet_header_preserved'] and saved['source_graphics_excluded'] > 0
    paths = run_infrastructure_paths(files['starter.run'])
    docs = {name: files[f'OTDocuments/{name}.opentrack'] for name in paths}
    assert docs['Station'] == docs['Link']
    dest = files['OTData/empty.dest']
    blank = project_from(docs, paths, dest)
    assert not blank.models['Station'] and not blank.models['Link'] and not blank.dests
    assert writer.string(blank.roots['Station'].contents[19].value) == 'Document import provenance'
    ends = []
    for x, tag in ((30, 'West'), (250, 'East')):
        update, result = transform(docs, paths, dest, 'Station', {
            'action': 'insert_vertex', 'x': x, 'y': 20, 'orientation': 'horizontal', 'names': [tag + 'A', tag + 'B'],
        }, shapes=shapes)
        ends.append(result['added_vertex_end_ids'])
        docs.update(update)
    assert ends == [[0, 1], [4, 5]]
    update, edge = transform(docs, paths, dest, 'Station', {
        'action': 'insert_edge', 'end_ids': [1, 4], 'length_m': 350, 'radius_m': 0, 'gradient_per_mille': 0,
        'rack_rail': False, 'track_name': 'P9', 'line_name': 'Reading', 'remark': '', 'allow_safety_regroup': False,
        'speeds': [{'train_type': '0', 'speed12_kmh': 75, 'speed21_kmh': 60}],
    }, shapes=shapes)
    docs.update(update)
    cold = project_from(docs, paths, dest)
    edge_key = cold.edge_between(('Station', 0), ('Station', 4))
    assert edge_key == ('Station', edge['edge_id'])
    assert cold.model(edge_key).contents[9].values[1] == 350
    assert not cold.models['Link'] and not cold.dests


def test_rejects_case_aliased_documents_and_nonempty_shape_catalogues():
    header, shapes = sources()
    with pytest.raises(ValueError, match='distinct worksheet names'):
        build_empty_project(header, shapes, **spec(document_names=['Station', 'station']))
    _, populated = sources(nonempty=True)
    with pytest.raises(ValueError, match='Every no-service trains catalog array must be empty'):
        build_empty_project(header, populated, **spec())


def test_empty_project_serializes_the_reviewed_window_and_optional_position_output():
    header, shapes = sources()
    baseline, original = build_empty_project(header, shapes, **spec())
    window = {'start_day': 0, 'start_time': '10:20:00', 'stop_day': 0, 'stop_time': '10:45:00', 'step': '0.2'}
    configured, receipt = build_empty_project(
        header, shapes, **spec(), simulation=window, additional_outputs=['station_and_signal_positions'],
    )
    assert receipt['simulation_window']['start_seconds'] == 10 * 3600 + 20 * 60
    assert receipt['simulation_window']['stop_seconds'] == 10 * 3600 + 45 * 60
    assert original['simulation_window']['stop_seconds'] == 86400 and not original['additional_outputs']
    option = b'Output Station- & Signalpositions#1#\n'
    assert option not in baseline['starter.run'] and option in configured['starter.run']
    assert all(data == baseline[name] for name, data in configured.items() if name != 'starter.run')
    with pytest.raises(ValueError, match='stop > start'):
        build_empty_project(header, shapes, **spec(), simulation={**window, 'stop_time': '10:10:00'})


def test_registered_preview_verifies_source_hash_and_keeps_legacy_create_quarantined(tmp_path, stable_fixture_reads):
    from opentrack_ai.legacy_geometry_guard import BLOCKED_TOOLS
    from opentrack_ai.registry import Registry
    from opentrack_ai.service import Service

    inputs = tmp_path / 'OTProjects/Input'
    inputs.mkdir(parents=True)
    header, shapes = sources()
    (inputs / 'Header.opentrack').write_bytes(header)
    (inputs / 'native-shapes.archive').write_bytes(shapes)
    request = {**spec(), 'header_document': {'path': 'OTProjects/Input/Header.opentrack', 'sha256': sha(header)},
               'shape_archive': {'path': 'OTProjects/Input/native-shapes.archive', 'sha256': sha(shapes)}}
    registry = Registry(Service(tmp_path, False, False), profile='all')
    tool = registry.tools['opentrack_initialize_empty_current_project']
    result = tool.handler(tool.model.model_validate(request))
    assert not result['saved'] and len(result['output_files']) == 9
    assert not result['native_application_executed'] and 'opentrack_create_project' in BLOCKED_TOOLS
    old = registry.tools['opentrack_create_project']
    with pytest.raises(APIError) as blocked:
        old.handler(old.model.model_validate({'project_name': 'Station'}))
    assert blocked.value.code == 'LEGACY_GEOMETRY_DISABLED'
    request['header_document']['sha256'] = '0' * 64
    with pytest.raises(APIError) as denied:
        EmptyCurrentProjectTools(tmp_path).initialize(InitializeEmptyCurrentProject.model_validate(request))
    assert denied.value.code == 'SOURCE_CHANGED'
    assert sorted(path.name for path in inputs.iterdir()) == ['Header.opentrack', 'native-shapes.archive']


@pytest.mark.skipif(os.name != 'nt', reason='Reviewed candidate binding uses the actual native Windows execution path')
def test_complete_geometry_candidate_requires_exact_document_only_replacement(tmp_path, stable_fixture_reads):
    from opentrack_ai.registry import Registry
    from opentrack_ai.service import Service

    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(data)}

    source = tmp_path / 'OTProjects/StationStart'
    destination = 'OTProjects/StationNext'
    revisions = tmp_path / 'OTProjects/Increment'
    header, shapes = sources()
    files, _ = build_empty_project(header, shapes, **spec(execution_root=source.as_posix(), document_names=['Station']))
    members = {name: write(source / name, data) for name, data in files.items()}
    dependencies = [members[name] for name in ('starter.run', 'OTDocuments/Station.opentrack', 'OTData/empty.dest')]
    docs = {'Station': files['OTDocuments/Station.opentrack']}
    paths = run_infrastructure_paths(files['starter.run'])
    updated, _ = transform(docs, paths, files['OTData/empty.dest'], 'Station', {
        'action': 'insert_vertex', 'x': 30, 'y': 20, 'orientation': 'horizontal', 'names': ['WestA', 'WestB'],
    }, shapes=shapes)
    project = {'project_directory': source.relative_to(tmp_path).as_posix(), 'run_file': 'starter.run',
               'files': {name: item['sha256'] for name, item in members.items()}, 'complete_project_inventory': True,
               'execution_root': source.as_posix()}
    registry = Registry(Service(tmp_path, False, False), profile='all')
    tool = registry.tools['opentrack_prepare_geometry_edit_candidate']

    def preview(relative, data):
        name = relative.rsplit('/', 1)[1]
        write(revisions / name, data)
        sources = {item['path']: item['sha256'] for item in dependencies}
        manifest = {'format': 'opentrack-saved-geometry-v1', 'complete_relocated_project': False,
                    'sources': sources, 'replacement_for': {name: members[relative]['path']},
                    'files': {name: {'sha256': sha(data), 'bytes': len(data)}}}
        return tool.handler(tool.model.model_validate({
            'source_project': project, 'target_directory': destination,
            'bundle_manifest': write(revisions / 'bundle-manifest.json', json.dumps(manifest).encode()),
        }))

    good = preview('OTDocuments/Station.opentrack', updated['Station'])
    assert good['validation']['no_service_catalogs'] and not good['saved']
    assert not (tmp_path / destination).exists()
    header_changed, version = writer.load_next_compatible(updated['Station'])
    header_changed.contents[19].value = native.string('Different import provenance')
    with pytest.raises(APIError) as bad:
        preview('OTDocuments/Station.opentrack', writer.dump_verified(header_changed, version))
    assert bad.value.code == 'GEOMETRY_CANDIDATE_INVALID' and 'header fields' in bad.value.details
    with pytest.raises(APIError) as forbidden:
        preview('OTData/empty.dest', files['OTData/empty.dest'])
    assert forbidden.value.code == 'GEOMETRY_CANDIDATE_INVALID' and 'only explicitly bound worksheets' in forbidden.value.details
