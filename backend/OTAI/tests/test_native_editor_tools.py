"""Check persistent native revisions and their secure Windows publication."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from opentrack_ai.current_archive.itinerary_edit_tools import _project, run_infrastructure_paths
from opentrack_ai.current_archive.native_editor_tools import (
    EditNativeEditor, EditorLocation, NativeEditorTools, PublishNativeEditor, StartNativeEditor,
)
from opentrack_ai.current_archive.saved_geometry_tools import EditGeometry, SavedGeometryTools
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation.empty_project import build_empty_project
from opentrack_ai.errors import APIError

from test_empty_project import sources


def binding(root, path):
    return {'path': path.relative_to(root).as_posix(), 'sha256': sha(path.read_bytes())}


def expected(state):
    return {'session_directory': state['session_directory'], 'expected_revision': state['revision'],
            'expected_event_sha256': state['event_sha256']}


def setup_project(root):
    project = root / 'OTAI/workspaces/original'
    project.mkdir(parents=True)
    header, shapes = sources()
    files, _ = build_empty_project(header, shapes, document_names=['Station', 'Link'], execution_root=project.as_posix(),
                                   run_filename='start.run', train_types=['instructional'])
    for name, data in files.items():
        member = project / name
        member.parent.mkdir(parents=True, exist_ok=True)
        member.write_bytes(data)
    donor = root / 'OTAI/workspaces/donor.archive'
    donor.write_bytes(shapes)
    inventory = {'project_directory': project.relative_to(root).as_posix(),
                 'files': {name: sha(data) for name, data in files.items()},
                 'complete_project_inventory': True, 'run_file': 'start.run', 'execution_root': project.as_posix()}
    return project, files, donor, inventory


def geometry(root, state, donor, name, position):
    source = root / state['current_project']['project_directory']
    target = root / 'OTAI/workspaces' / name
    result = SavedGeometryTools(root).edit(EditGeometry.model_validate({
        'project_run': binding(root, source / 'start.run'),
        'dest_catalog': binding(root, source / 'OTData/empty.dest'),
        'documents': {sheet: binding(root, source / 'OTDocuments' / f'{sheet}.opentrack') for sheet in ('Station', 'Link')},
        'target_document': 'Station', 'target_directory': target.relative_to(root).as_posix(), 'preview_only': False,
        'operation': {'action': 'insert_vertex', 'x': position, 'y': 40, 'orientation': 'horizontal',
                      'names': ['X left', 'X right'], 'shapes': binding(root, donor)},
    }))
    assert result['saved']
    return binding(root, target / 'bundle-manifest.json')


def native_vertex(root, inventory):
    project = root / inventory['project_directory']
    files = {name: (project / name).read_bytes() for name in inventory['files']}
    assert {name: sha(data) for name, data in files.items()} == inventory['files']
    saved = _project({sheet: files[f'OTDocuments/{sheet}.opentrack'] for sheet in ('Station', 'Link')},
                     run_infrastructure_paths(files['start.run']), files['OTData/empty.dest'])
    return [end.contents[2].value for end in saved.ends('Station')]


@pytest.mark.skipif(os.name != 'nt', reason='Actual editor publication is a Windows NTFS operation')
def test_native_editor_branches_and_publishes_old_snapshot(tmp_path):
    if not tmp_path.as_posix().isascii():
        pytest.skip('Windows native publication requires an ASCII --basetemp')
    original, original_files, donor, inventory = setup_project(tmp_path)
    session = 'OTAI/workspaces/editor'
    tool = NativeEditorTools(tmp_path)
    origin = tool.start(StartNativeEditor(session_directory=session, source_project=inventory, preview_only=False))
    stage_one = geometry(tmp_path, origin, donor, 'first-edit', 110)
    stage_two = geometry(tmp_path, origin, donor, 'other-edit', 205)

    def edit(state, action, *bundles):
        return tool.edit(EditNativeEditor(**expected(state), action=action, preview_only=False, bundle_manifests=list(bundles)))

    first = edit(origin, 'stage', stage_one)
    assert first['publication']['post_commit_verified'] and first['snapshot_revision'] == 1
    assert native_vertex(tmp_path, first['current_project']) == [110, 110]
    with pytest.raises(APIError) as stale:
        edit(origin, 'stage', stage_two)
    assert stale.value.code == 'NATIVE_EDITOR_REVISION_CONFLICT'
    undone = edit(first, 'undo')
    assert undone['snapshot_revision'] == 0 and undone['redo_available'] and not native_vertex(tmp_path, undone['current_project'])
    redone = edit(undone, 'redo')
    assert redone['snapshot_revision'] == 1 and native_vertex(tmp_path, redone['current_project']) == [110, 110]
    restored = edit(redone, 'undo')
    with pytest.raises(APIError, match='single replacement per member'):
        edit(restored, 'stage', stage_one, stage_two)
    assert tool.read(EditorLocation(session_directory=session))['revision'] == restored['revision']
    reused_original = edit(restored, 'stage', stage_two)
    assert reused_original['active_history'] == [0, 5] and reused_original['preserved_snapshot_revisions'] == [0, 1, 5]
    assert not reused_original['redo_available'] and native_vertex(tmp_path, reused_original['current_project']) == [205, 205]
    saved = tool.publish(PublishNativeEditor(**expected(reused_original), snapshot_revision=1,
        target_directory='OTAI/workspaces/published', preview_only=False))
    assert saved['saved'] and native_vertex(tmp_path, saved['candidate_project']) == [110, 110]
    assert all((original / member).read_bytes() == data for member, data in original_files.items())

    event = tmp_path / session / 'history/0002/event.json'
    event.write_bytes(event.read_bytes() + b'\n')
    with pytest.raises(APIError, match='fingerprint chain differs'):
        tool.read(EditorLocation(session_directory=session))


@pytest.mark.skipif(os.name != 'nt', reason='Actual editor publication is a Windows NTFS operation')
def test_concurrent_editor_commits_select_only_one_revision(tmp_path):
    if not tmp_path.as_posix().isascii():
        pytest.skip('Windows native publication requires an ASCII --basetemp')
    _, _, donor, inventory = setup_project(tmp_path)
    session = 'OTAI/workspaces/editor'
    tool = NativeEditorTools(tmp_path)
    base = tool.start(StartNativeEditor(session_directory=session, source_project=inventory, preview_only=False))
    edits = [geometry(tmp_path, base, donor, name, x) for name, x in (('a', 130), ('b', 200))]
    barrier = Barrier(2)

    def stage(source):
        barrier.wait(timeout=15)
        try:
            return tool.edit(EditNativeEditor(**expected(base), action='stage', preview_only=False,
                                              bundle_manifests=[source]))
        except APIError as error:
            return error

    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(stage, edits))
    committed = [result for result in results if isinstance(result, dict)]
    rejected = [result for result in results if isinstance(result, APIError)]
    assert len(committed) == len(rejected) == 1, [(item.code, item.message) for item in rejected]
    assert rejected[0].code in {'NATIVE_EDITOR_BUSY', 'NATIVE_EDITOR_REVISION_CONFLICT'}
    current = tool.read(EditorLocation(session_directory=session))
    assert current['revision'] == committed[0]['revision'] == 1
    assert current['event_sha256'] == committed[0]['event_sha256']
    assert native_vertex(tmp_path, current['current_project']) in ([130, 130], [200, 200])
