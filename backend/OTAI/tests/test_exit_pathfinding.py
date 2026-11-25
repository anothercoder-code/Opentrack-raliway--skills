"""Cover bounded R17.33 exit-to-exit Path search, naming and native publication."""

from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.movement_edits import _movement_project
from opentrack_ai.current_archive.pathfinding_tools import FindPaths, PathfindingTools, find_paths
from opentrack_ai.current_archive.route_fetch_tools import SelectedRoute, fetch_routes
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation.native_signal_routes import string
from opentrack_ai.errors import APIError

from test_itinerary_native_edit import fixture
from test_path_lifecycle_native import course_catalog, cross_project
from test_route_fetch import candidate


def spec(document='Line', **changes):
    return SimpleNamespace(**{'document': document, 'start_end_ids': [], 'max_paths': 100,
                              'max_expansions': 100, 'naming': 'standard', 'duplicate_policy': 'reuse', **changes})


def through_block():
    documents, catalog, names, _ = fixture('Line.opentrack')
    before = _movement_project(documents, names, catalog)
    first, middle, last = before.dest_view(before.dests[0])[0]
    before.model(middle).contents[11].value.contents[8].values[1] = 3
    for end, name in ((first, 'First'), (last, 'Last')):
        before.model(end).contents[18].value = string(name)
    documents['Line'] = writer.dump_verified(before.roots['Line'], before.versions['Line'])
    return documents, catalog, names, first, middle, last


def test_search_through_non_exit_main_signal_and_use_original_name_formats():
    documents, catalog, names, first, middle, last = through_block()
    old = _movement_project(documents, names, catalog)
    output, report = find_paths(documents, names, catalog, course_catalog(), spec())
    new, = report['paths']
    assert new['path']['name'] == 'P:First_S0-Last_S2'
    assert new['movement'] == (first, middle, last)
    assert [route['name'] for route in new['routes']] == ['R0', 'R1']
    assert report['eligible_starts'] == [first, last]
    fresh = _movement_project({'Line': output}, names, catalog)
    assert fresh.dest_view(fresh.dests[0]) == old.dest_view(old.dests[0])
    assert path_functions.info(fresh.dests[0]) == path_functions.info(old.dests[0])
    assert fresh.model(first).contents[19].value == old.model(first).contents[19].value + 1

    unchanged, rerun = find_paths({'Line': output}, names, catalog, course_catalog(), spec())
    assert unchanged == output and rerun['created_count'] == 0 and rerun['paths'][0]['result'] == 'reused'
    _, treno = find_paths({'Line': output}, names, catalog, course_catalog(), spec(naming='treno'))
    assert treno['paths'][0]['path']['name'] == 'P:First-Last'
    with pytest.raises(ValueError, match='must be an original exit signal'):
        find_paths(documents, names, catalog, course_catalog(), spec(start_end_ids=[middle[1]]))


def test_branch_same_terminal_uses_native_suffix_and_preserves_distinct_route_ids():
    documents, catalog, names, first, middle, _ = through_block()
    project = _movement_project(documents, names, catalog)
    review = SelectedRoute(name='Review R0 alternate', candidate=candidate(project, [first, middle]),
                           allow_duplicate_movement=True).model_dump()
    documents, _ = fetch_routes(documents, names, catalog, [review])
    output, report = find_paths(documents, names, catalog, course_catalog(), spec())
    one, two = report['paths']
    assert one['movement'] == two['movement']
    assert [one['routes'][0]['name'], two['routes'][0]['name']] == ['R0', 'Review R0 alternate']
    assert two['path']['name'] == one['path']['name'] + '.1'
    assert two['path']['array_id'] == one['path']['array_id'] + 1
    with pytest.raises(ValueError, match='result limit'):
        find_paths(documents, names, catalog, course_catalog(), spec(max_paths=1))
    with pytest.raises(ValueError, match='expansion limit'):
        find_paths(documents, names, catalog, course_catalog(), spec(max_expansions=1))
    changed, duplicated = find_paths({'Line': output}, names, catalog, course_catalog(),
                                    spec(duplicate_policy='append'))
    assert changed != output
    assert [row['path']['name'] for row in duplicated['paths']] == [
        one['path']['name'] + '.2', one['path']['name'] + '.3']


def test_pathfinder_blocks_dangling_incident_identity_capture():
    documents, catalog, names, first, _, _ = through_block()
    project = _movement_project(documents, names, catalog)
    counter = project.model(first).contents[19].value
    incident = {'document': 'Line', 'start_id': first[1], 'array_id': counter + 1}
    with pytest.raises(ValueError, match='Path-speed Incident'):
        find_paths(documents, names, catalog, course_catalog(incident), spec())


def test_normal_entrypoint_writes_only_owner_of_cross_document_path(tmp_path):
    documents, names, catalog, _, _ = cross_project()
    bound = tmp_path / 'OTProjects/Bound'
    target = tmp_path / 'OTAI/workspaces/TestPathfinding'
    bound.mkdir(parents=True)
    target.mkdir(parents=True)

    def bind(member, content):
        path = bound / member
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(content)}

    request = FindPaths(
        project_run=bind('line.run', b'Infrastructure Document#OTDocuments/A.opentrack#\n'
                         b'Infrastructure Document#OTDocuments/B.opentrack#\nDestInfoFile#line.dest#\n'
                         b'CourseFile#line.courses#\n'),
        documents={key: bind(name, documents[key]) for key, name in names.items()},
        dest_catalog=bind('line.dest', catalog),
        courses=bind('line.courses', course_catalog()),
        document='A',
        preview_only=False,
        target_directory=(target / 'Native').relative_to(tmp_path).as_posix(),
    )
    service = PathfindingTools(tmp_path)
    result = service.find(request)
    assert result['saved'] and result['atomic_directory_commit']
    assert set(result['manifest']['files']) == {'A.opentrack'}
    assert result['change_report']['paths'][0]['movement'] == [['A', 0], ['A', 4], ['B', 4]]
    assert all((bound / name).read_bytes() == documents[key] for key, name in names.items())
    assert (bound / 'line.dest').read_bytes() == catalog
    with pytest.raises(APIError) as collision:
        service.find(request)
    assert collision.value.code == 'TARGET_EXISTS'
