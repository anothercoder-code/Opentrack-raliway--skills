"""Preserve ordinary station admission outside an explicitly reviewed reverse split."""

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.multi_document import operations
from opentrack_ai.current_archive.multi_document.core import ident, sha
from opentrack_ai.current_archive.native_reverse_split import _body_edge
from opentrack_ai.current_archive.network_operating_plan import CompositionEvent, route_trace
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_main_signal_split import insert_signal_in_saved_route
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_lifecycle import course_archive
from test_saved_main_signal_split import sending_corridor


def station(name):
    return native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [1000]), ('f', [0.0]), ('f', [20.0]), ('f', [10.0]), ('i', [0]), ('i', [0]),
        ('@', [None]), ('@', [native.string(name)]), ('ii', [2, 4]), ('ii', [1, 0]),
    ])


def test_ordinary_station_origin_requires_exact_review_and_own_block_signal(sending_corridor):
    documents, paths, dest, _, op = sending_corridor
    changes, result = insert_signal_in_saved_route(documents, paths, dest, 'A', op, course_archive(C01=['I:A-B']))
    documents = {**documents, **changes}

    def scope():
        return {'document_paths': paths, 'complete_document_set': True,
                'expected_hashes': {**{name: sha(blob) for name, blob in documents.items()}, '$dest_catalog': sha(dest)}}

    documents, path = operations.create_path(documents, dest, name='Child path', routes=[result['downstream_route']],
                                             **scope())
    saved, _ = operations.create_itinerary(documents, dest, name='Child', paths=[path['created']], **scope())
    dest, documents = saved['catalog'], saved['documents']
    project = project_from(documents, paths, dest)
    draft = next(item for item in project.dests if ident(item)[0] == 'Child')
    nodes, _ = project.dest_view(draft)
    start, finish = nodes[0], nodes[-1]
    for key, label in ((start, 'P'), (finish, 'F')):
        station_model = station(label)
        for half in (key, project.related(key)):
            end = project.model(half)
            end.contents[12].value = station_model
            end.contents[20].value = 1 if label == 'P' else 2
        collection = project.roots[key[0]].contents[2].value
        writer.set_elements(collection, [*writer.elements(collection), station_model])
    cold = project_from({name: writer.dump_verified(root, project.versions[name])
                         for name, root in project.roots.items()}, paths, dest)
    itinerary = next(item for item in cold.dests if ident(item)[0] == 'Child')
    with pytest.raises(ValueError, match='must begin at a native station reference'):
        route_trace(cold, itinerary)
    with pytest.raises(ValueError, match='not the Itinerary first End'):
        route_trace(cold, itinerary, reviewed_reverse_origin=cold.related(start))
    trace = route_trace(cold, itinerary, reviewed_reverse_origin=start)
    origin, terminal = trace['visits']
    assert (origin['station_sign'], origin['end_key'], origin['distance_m']) == ('P', start, 0)
    assert origin['stop_edge_key'] is None and terminal['end_key'] == finish
    cold.model(start).contents[11].value.contents[8].values[1] = 4
    with pytest.raises(ValueError, match='own main block signal'):
        route_trace(cold, itinerary, reviewed_reverse_origin=start)


def test_reverse_split_body_edge_requires_its_complete_safety_membership(sending_corridor):
    documents, paths, dest, _, _ = sending_corridor
    project = project_from(documents, paths, dest)
    route = next(item for item in project.routes if project.owners[id(item)][0] == 'A')
    first, last = project.route_view(route)[:2]
    edge_key = project.edge_between(first, last)
    edge = project.model(edge_key)
    a, b = [edge.contents[slot].value for slot in (7, 8)]
    owner = station('P')
    a.contents[12].value = b.contents[12].value = owner
    length = edge.contents[9].values[1]
    resource = a.contents[7].value
    assert _body_edge(project, first, last, edge_key[1], length, owner) == (edge_key, project.key(resource))
    other = project.model(first)
    writer.set_elements(resource.contents[7].value, [a, b, other])
    try:
        with pytest.raises(ValueError, match='native Safety Element differs'):
            _body_edge(project, first, last, edge_key[1], length, owner)
    finally:
        writer.set_elements(resource.contents[7].value, [a, b])


@pytest.mark.parametrize(('kind', 'index'), [('join', 1), ('split', None)])
def test_reverse_split_requested_only_for_an_explicit_intermediate_split(kind, index):
    with pytest.raises(ValueError, match='explicitly selected intermediate split visit'):
        CompositionEvent.model_validate({'kind': kind, 'main_course': 'A', 'other_course': 'B', 'station_sign': 'P',
            'main_visit_index': index, 'reverse_split': {'parent_head_end': ['RDG', 8], 'parent_head_signal_id': 24,
            'child_origin_end': ['RDG', 29], 'child_origin_signal_id': 40, 'detached_edge_id': 32, 'retained_edge_id': 37}})
