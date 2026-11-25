"""Dependency checks for the native worksheet Exclusion Link editor."""

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.saved_edge_exclusion import set_edge_exclusion
from opentrack_ai.current_archive.saved_geometry import model_id, project_from
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_native_edit import fixture, schematic_document


@pytest.fixture
def sheet():
    diagram = generate.spec()
    diagram['vertices'] = [generate.vertex(label, index * 100) for index, label in enumerate('ABCDEFGHI')]
    edge, = diagram['edges']
    diagram['edges'] = [{**edge, 'key': a + b, 'from': [a, 1], 'to': [b, 0]}
                        for a, b in ('AB', 'BC', 'DE', 'FG', 'HI')]
    doc, nodes = schematic_document(diagram, [('A', 0), ('C', 0)])
    doc, _ = native.build_route(doc, name='Active', end_ids=[nodes[label][0] for label in 'ABC'],
                                description='', release_groups='global', reserve_previous=False)
    docs = {'Line': doc}
    paths = {'Line': 'Line.opentrack'}
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
    seed = project_from(docs, paths, catalog)
    edge_ids = [model_id(obj) for obj in seed.models['Line'] if writer.kind(obj) == 'OTEdgeModel']

    def edit(source, target, expected=None, inbound=None, inputs=None):
        operation = {'action': 'set_edge_exclusion', 'edge_id': source, 'target_edge_id': target,
                     'expected_target_edge_id': expected, 'expected_target_source_edge_id': inbound}
        output, report = set_edge_exclusion(inputs or docs, paths, catalog, 'Line', operation)
        return output, report, project_from(output, paths, catalog)

    return docs, edge_ids, edit


def test_create_replace_occupied_target_and_clear_native_link(sheet):
    docs, edge_ids, edit = sheet
    active, other, branch, target, _ = edge_ids
    first, report, _ = edit(active, branch)
    assert report['protected_movements'] == [{'kind': 'route', 'owner': ('Line', 0), 'identity': ('Active', 0, 0)}]
    second, _, _ = edit(other, target, inputs=first)
    with pytest.raises(ValueError, match='exact prior source'):
        edit(active, target, expected=branch, inputs=second)
    third, report, graph = edit(active, target, expected=branch, inbound=other, inputs=second)
    assert report['nonselected_graph_verified'] and report['removed_target_source_edge_id'] == other
    source, displaced, cleared, bound = [graph.model(('Line', eid)) for eid in (active, other, branch, target)]
    assert source.contents[13].value is bound and bound.contents[14].value is source
    assert displaced.contents[13].value is None and cleared.contents[14].value is None
    final, _, _ = edit(active, None, expected=target, inputs=third)
    baseline, _ = writer.load_next_compatible(docs['Line'])
    restored, _ = writer.load_next_compatible(final['Line'])
    assert writer.fingerprint(baseline) == writer.fingerprint(restored)


def test_rejects_cycles_stale_reviews_and_self_conflicting_saved_movements(sheet):
    _, edge_ids, edit = sheet
    first_active, second_active, a, b, c = edge_ids
    for source, target in ((first_active, second_active), (second_active, first_active)):
        with pytest.raises(ValueError, match='existing traversal resource'):
            edit(source, target)
    updated, _, _ = edit(a, b)
    with pytest.raises(ValueError, match='directed cycle'):
        edit(b, a, inputs=updated)
    with pytest.raises(ValueError, match='original target'):
        edit(a, c, inputs=updated)
    with pytest.raises(ValueError, match='separate current Edge IDs'):
        edit(c, c)
    chained, _, _ = edit(b, c, inputs=updated)
    with pytest.raises(ValueError, match='directed cycle'):
        edit(c, a, inputs=chained)


def test_refuses_a_link_that_would_conflict_across_successive_saved_routes():
    docs, catalog, paths, _ = fixture('Line.opentrack')
    graph = project_from(docs, paths, catalog)
    a, b = (graph.edge_between(*graph.route_view(route))[1] for route in graph.routes)
    for source, target in ((a, b), (b, a)):
        operation = {'action': 'set_edge_exclusion', 'edge_id': source, 'expected_target_edge_id': None,
                     'target_edge_id': target}
        with pytest.raises(ValueError, match='existing traversal resource of saved path'):
            set_edge_exclusion(docs, paths, catalog, 'Line', operation)
