"""Check reviewed Route fetch persistence and continuation identities."""

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.movement_edits import _movement_project
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.route_fetch_tools import RouteFetch, FetchRoutes, SelectedRoute, fetch_routes
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError

from test_cross_document_route_native_edit import NATIVE_PATHS, fixture
from test_itinerary_native_edit import schematic_document


def candidate(project, chain):
    edges = [project.edge_between(a, b) for a, b in zip(chain, chain[1:])]
    return {'end_sequence': [list(key) for key in chain], 'edge_sequence': [list(key) for key in edges],
            'distance_m': sum(project.model(edge).contents[9].values[1] for edge in edges),
            'document_boundaries': sum(a[0] != b[0] for a, b in zip(chain, chain[1:])),
            'one_route_storage_compatible': True, 'existing_route_names': []}


def test_save_local_new_routes_allocates_next_ids_without_changing_existing():
    document, _ = schematic_document(generate.spec(), [('left', 0), ('right', 0)])
    documents = {'A': document}
    paths = {'A': 'A.opentrack'}
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
    project = _movement_project(documents, paths, catalog)
    chain = [('A', 0), ('A', 4)]
    first = SelectedRoute(name='First native', candidate=candidate(project, chain), release_groups='each_end',
                          reserve_previous=True).model_dump()
    second = {**first, 'name': 'Separate Route', 'allow_duplicate_movement': True}
    output, report = fetch_routes(documents, paths, catalog, [first, second])
    assert report['unchanged_archive_graph_verified']
    assert [item['route']['array_id'] for item in report['created_routes']] == [0, 1]
    project = _movement_project(output, paths, catalog)
    route = project.owned(chain[0], 'OTRoute', ('First native', 0, 0))
    assert project.route_view(route) == chain
    assert route.contents[11].value == 1
    assert project.model(chain[0]).contents[19].value == 1


def test_fetch_alt_route_adds_companion_preserves_prior_primary_and_rejects_wrong_review():
    docs, catalog = fixture()
    project = _movement_project(docs, NATIVE_PATHS, catalog)
    chain = [('A', 0), ('A', 8), ('B', 4)]
    review = candidate(project, chain)
    requested = SelectedRoute(name='Alternate across boundary', candidate=review, release_groups='explicit',
                              release_end_sequence=chain).model_dump()
    output, report = fetch_routes(docs, NATIVE_PATHS, catalog, [requested])
    new = report['created_routes'][0]
    assert new['route']['array_id'] == 2
    assert new['fragments'] == [
        {'owner': ('A', 0), 'continuation_index': 2, 'end_sequence': chain[:2], 'release_end_sequence': chain[:2]},
        {'owner': ('B', 8), 'continuation_index': -1, 'end_sequence': chain[2:], 'release_end_sequence': chain[2:]},
    ]
    project = _movement_project(output, NATIVE_PATHS, catalog)
    original = project.owned(('A', 0), 'OTRoute', ('R:A-B', 0, 0))
    assert project.route_view(original) == [('A', 0), ('A', 4), ('B', 4)]
    with pytest.raises(ValueError, match='metre count differs'):
        fetch_routes(docs, NATIVE_PATHS, catalog,
                     [{**requested, 'candidate': {**review, 'distance_m': review['distance_m'] + 1}}])
    with pytest.raises(ValueError, match='Edge sequence differs'):
        fetch_routes(docs, NATIVE_PATHS, catalog,
                     [{**requested, 'candidate': {**review, 'edge_sequence': list(reversed(review['edge_sequence']))}}])


def test_publish_two_files_and_refuse_overwrite(tmp_path):
    docs, catalog = fixture()
    source = tmp_path / 'OTProjects/Bound'
    target = tmp_path / 'OTAI/workspaces/Fetch'
    source.mkdir(parents=True)
    target.mkdir(parents=True)

    def write(path, data):
        path.write_bytes(data)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(data)}

    project = _movement_project(docs, NATIVE_PATHS, catalog)
    planned = FetchRoutes(
        project_run=write(source / 'line.run',
                          b'Infrastructure Document#A.opentrack#\nInfrastructure Document#B.opentrack#\nDestInfoFile#line.dest#\n'),
        documents={name: write(source / filename, docs[name]) for name, filename in NATIVE_PATHS.items()},
        dest_catalog=write(source / 'line.dest', catalog),
        routes=[{'name': 'Alternative', 'candidate': candidate(project, [('A', 0), ('A', 8), ('B', 4)])}],
        preview_only=False, target_directory=(target / 'Native').relative_to(tmp_path).as_posix(),
    )
    service = RouteFetch(tmp_path)
    result = service.fetch(planned)
    assert result['saved'] and result['atomic_directory_commit']
    assert set(result['manifest']['files']) == {'A.opentrack', 'B.opentrack'}
    for name, filename in NATIVE_PATHS.items():
        assert (source / filename).read_bytes() == docs[name]
        assert sha((target / 'Native' / filename).read_bytes()) == result['manifest']['files'][filename]['sha256']
    with pytest.raises(APIError) as retry:
        service.fetch(planned)
    assert retry.value.code == 'TARGET_EXISTS'
