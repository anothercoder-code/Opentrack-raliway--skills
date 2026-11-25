"""Readback of native Path lifecycle and dependent Itinerary transactions."""
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.infrastructure_incidents import core as incidents
from opentrack_ai.current_archive.movement_edits import _movement_project
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.path_lifecycle_tools import EditPathLifecycle, PathLifecycleTools, edit_path_lifecycle
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation.native_signal_routes import arr, obj
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import fixture, schematic_document


def cross_project():
    names = {key: f'OTDocuments/{key}.opentrack' for key in 'AB'}
    documents, catalog, _ = generate.make_pair({
        'A': schematic_document(generate.spec(), [('left', 0), ('left', 1)])[0],
        'B': schematic_document(generate.spec(), [('right', 0), ('right', 1)])[0],
    }, names)
    project = _movement_project(documents, names, catalog)
    paths = {}
    routes = {}
    for path in project.paths_objects:
        document, _ = project.owners[id(path)]
        paths[document] = {'document': document, **generate.ref(path)}
        routes[document] = [{'document': name, **reference} for name, reference in project.path_view(path)[1]]
    return documents, names, catalog, paths, routes


def course_catalog(path=None):
    events = arr()
    if path is not None:
        event = incidents.create({'type': 'path_speed', 'name': 'Slow', 'document': path['document'],
                                  'start_end_id': path['start_id'], 'array_id': path['array_id'],
                                  'begin_time': '08:00:00', 'end_time': '08:30:00', 'begin_day': 0, 'end_day': 0,
                                  'enabled': True, 'probability_percentage': 100, 'reduced_speed_kmh': 40}, events)
        writer.set_elements(events, [event])
    root = obj([('OTCourseList', 3), ('OTMutableArray', 0), ('NSObject', 0)],
               [('i', [17]), ('@', [events]), *[('@', [arr()]) for _ in range(3)]])
    return writer.dump_verified(root)


def test_create_rename_delete_cross_document_path_and_repair_itinerary():
    documents, names, catalog, paths, routes = cross_project()
    expected = [('A', 0), ('A', 4), ('B', 4)]
    created, same_catalog, added = edit_path_lifecycle(
        documents, names, catalog, {'action': 'create', 'name': 'Alternative', 'description': 'Crosses A/B',
                                    'routes': routes['A']})
    assert same_catalog == catalog and created['B'] == documents['B']
    assert added['movement'] == expected
    assert added['path']['array_id'] == paths['A']['array_id'] + 1
    renamed, renamed_catalog, report = edit_path_lifecycle(
        created, names, catalog, {'action': 'rename', 'path': paths['A'], 'new_name': '\u8def\u5f84'})
    assert report['path'] == {**paths['A'], 'name': '\u8def\u5f84'}
    assert renamed_catalog != catalog and renamed['B'] == created['B']
    assert report['dependent_itineraries'] == ['I:A-B']

    deletion = {'action': 'delete', 'path': report['path'], 'repairs': []}
    with pytest.raises(ValueError, match='every dependent Itinerary'):
        edit_path_lifecycle(renamed, names, renamed_catalog, deletion, course_catalog())
    deletion['repairs'] = [{'name': 'I:A-B', 'paths': [added['path']]}]
    with pytest.raises(ValueError, match='Path-speed Incident'):
        edit_path_lifecycle(renamed, names, renamed_catalog, deletion, course_catalog(report['path']))
    saved, saved_catalog, report = edit_path_lifecycle(renamed, names, renamed_catalog, deletion, course_catalog())
    reloaded = _movement_project(saved, names, saved_catalog)
    itinerary = next(item for item in reloaded.dests if path_functions.info(item)['name'] == 'I:A-B')
    assert reloaded.dest_view(itinerary)[0] == expected
    assert path_functions.info(itinerary)['saved_references'] == [added['path']]
    assert saved['B'] == documents['B'] and report['running_time_revalidation_required']
    assert {generate.ref(item)['name'] for item in reloaded.paths_objects} == {'Alternative', paths['B']['name']}


def test_move_cross_document_path_to_another_owner():
    documents, names, catalog, _, routes = cross_project()
    documents, _, added = edit_path_lifecycle(
        documents, names, catalog, {'action': 'create', 'name': 'Movable', 'description': '', 'routes': routes['A']})
    saved, same_catalog, report = edit_path_lifecycle(
        documents, names, catalog,
        {'action': 'move', 'path': added['path'], 'routes': routes['B'], 'repairs': []}, course_catalog())
    assert all(saved[key] != documents[key] for key in documents)
    assert same_catalog == catalog
    assert report['path']['document'] == 'B' and report['path']['start_id'] != added['path']['start_id']
    assert report['movement'] == [('B', 5), ('B', 1), ('A', 1)]


def test_move_terminal_and_repair_itinerary_using_retained_path_identity():
    documents, catalog, names, paths = fixture('Line.opentrack')
    project = _movement_project(documents, names, catalog)
    through = next(path for path in project.paths_objects if generate.ref(path)['name'] == 'Through')
    routes = [{'document': document, **reference} for document, reference in project.path_view(through)[1]]
    saved, updated, report = edit_path_lifecycle(
        documents, names, catalog, {'action': 'move', 'path': paths[0], 'routes': routes,
                                    'repairs': [{'name': 'Service', 'paths': [{'use_moved_path': True}]}]},
        course_catalog())
    checked = _movement_project(saved, names, updated)
    assert report['path'] == paths[0] and report['dependent_itineraries'] == ['Service']
    assert checked.dest_view(checked.dests[0])[0] == project.dest_view(project.dests[0])[0]
    assert path_functions.info(checked.dests[0])['saved_references'] == paths[:1]


def test_move_with_fresh_owner_id_and_explicit_itinerary_repair():
    documents, catalog, names, paths = fixture('Line.opentrack')
    project = _movement_project(documents, names, catalog)
    first, last = (next(item for item in project.paths_objects if generate.ref(item)['name'] == path['name'])
                   for path in paths[:2])
    first_route = [{'document': document, **reference} for document, reference in project.path_view(first)[1]]
    last_route = [{'document': document, **reference} for document, reference in project.path_view(last)[1]]
    documents, catalog, prefix = edit_path_lifecycle(documents, names, catalog, {
        'action': 'create', 'name': 'Prefix', 'description': '', 'routes': first_route,
    })
    documents, updated, report = edit_path_lifecycle(
        documents, names, catalog, {'action': 'move', 'path': paths[0], 'routes': last_route,
                                    'repairs': [{'name': 'Service', 'paths': [prefix['path'], {'use_moved_path': True}]}]},
        course_catalog())
    checked = _movement_project(documents, names, updated)
    moved = report['path']
    assert moved == {**paths[0], 'start_id': paths[1]['start_id'], 'array_id': paths[1]['array_id'] + 1}
    assert path_functions.info(checked.dests[0])['saved_references'] == [prefix['path'], moved]
    assert checked.dest_view(checked.dests[0])[0] == project.dest_view(project.dests[0])[0]


def test_saved_linked_path_renames_both_archives_atomically():
    documents, names, catalog, paths, _ = cross_project()
    with TemporaryDirectory(dir=Path(__file__).resolve().parent) as temporary:
        root = Path(temporary)
        project = root / 'OTProjects' / 'Line'
        (project / 'OTDocuments').mkdir(parents=True)
        out = root / 'OTAI' / 'workspaces' / 'Output'
        out.mkdir(parents=True)
        inventory = {'Line.dest': catalog,
                     'Line.run': b'Infrastructure Document#OTDocuments/A.opentrack#\n'
                                 b'Infrastructure Document#OTDocuments/B.opentrack#\n'
                                 b'DestInfoFile#Line.dest#\n',
                     **{path: documents[name] for name, path in names.items()}}
        for name, content in inventory.items():
            (project / name).write_bytes(content)

        def source(name):
            return {'path': (project / name).relative_to(root).as_posix(), 'sha256': sha(inventory[name])}

        args = {'project_run': source('Line.run'), 'dest_catalog': source('Line.dest'),
                'documents': {name: source(path) for name, path in names.items()},
                'edit': {'action': 'rename', 'path': paths['A'], 'new_name': 'Renamed'}}
        service = PathLifecycleTools(root)
        preview = service.edit(EditPathLifecycle(**args))
        assert not preview['saved']
        assert set(preview['manifest']['files']) == {'A.opentrack', 'Line.dest'}
        target = out / 'renamed'
        save = EditPathLifecycle(**args, preview_only=False, target_directory=target.relative_to(root).as_posix())
        report = service.edit(save)
        assert report['saved'] and report['atomic_directory_commit']
        reloaded = _movement_project({**documents, 'A': (target / 'A.opentrack').read_bytes()}, names,
                                     (target / 'Line.dest').read_bytes())
        assert any(generate.ref(item)['name'] == 'Renamed' for item in reloaded.paths_objects)
        assert all((project / name).read_bytes() == content for name, content in inventory.items())
        with pytest.raises(APIError) as error:
            service.edit(save)
        assert error.value.code == 'TARGET_EXISTS'
