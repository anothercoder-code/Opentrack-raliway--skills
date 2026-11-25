"""Location Incident readback, geometry comparison and exact native selector edits."""

import pytest

from opentrack_ai.current_archive import catalogs, incident_operations, writer
from opentrack_ai.current_archive.incident_set_workflow.core import make_set
from opentrack_ai.current_archive.infrastructure_incidents import core, spans
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_span_incident_rebinding import (
    has_span_incidents, rebind_span_incidents, span_incident_bindings,
)

from test_cross_document_route_native_edit import fixture
from test_itinerary_lifecycle import course_archive
from test_itinerary_native_edit import fixture as local_routes
from test_saved_cross_document_reroute import crossing
from test_saved_geometry import apply
from test_saved_track_topology import save_project


def archived_incidents(items, *, course=None):
    choices = {} if course is None else {'T01': course}
    root, version = writer.load_next_compatible(course_archive(**choices))
    for row in catalogs.course_items(root):
        row.contents[5].value = 1
    array = root.contents[1].value
    rows = [core.create({'name': name, 'type': kind, 'begin_time': '08:00:00', 'end_time': '08:03:00',
                         'begin_day': 0, 'end_day': 0, 'enabled': False, 'probability_percentage': 54,
                         'comment': 'Retain original metadata', **selector}, array)
            for name, kind, selector in items]
    for row in rows:
        if row.contents[5].values[2] in spans.TRACK_TYPES:
            row.contents[11].value = row.contents[10].value
    writer.set_elements(array, rows)
    if rows:
        members = make_set(root, 'Original set', list(reversed(rows)))
        members.contents[3].value = incident_operations.string('Original set note')
        writer.set_elements(root.contents[2].value, [members])
    return writer.dump_verified(root, version)


def review(before, after, *, replacement_selector=None):
    return {'name': before['name'], 'expected_selector': before['selector'], 'expected_edge_refs': before['edge_refs'],
            'replacement_selector': after['selector'] if replacement_selector is None else replacement_selector,
            'replacement_edge_refs': after['edge_refs']}


def test_kilometre_location_rebinding_updates_every_selected_incident_and_preserves_aliases():
    documents, catalog = fixture()
    paths = {name: f'{name}.opentrack' for name in documents}
    original, _ = apply(documents, catalog, {'action': 'calculate_kilometre_points', 'direction': 'increasing',
        'itinerary': 'I:A-B', 'end_sequence': None, 'start_km': 50, 'replace_conflicting': False})
    previous = save_project(original)
    old_selector = {'line_id': 'A-B', 'track_id': '1', 'begin_km': '50.65', 'end_km': '50.8'}
    new_selector = {**old_selector, 'track_id': 'Alternative'}
    reverse = {**old_selector, 'begin_km': old_selector['end_km'], 'end_km': old_selector['begin_km']}
    specifications = [('Slow', 'position_speed', old_selector), ('Block', 'position_blockage', old_selector),
                      ('Hold', 'position_stop_wait', reverse)]
    source = archived_incidents(specifications)
    assert has_span_incidents(source) and not has_span_incidents(archived_incidents([]))
    unrelated, version = writer.load_next_compatible(archived_incidents([]))
    unrelated.contents[0].value = 16
    assert not has_span_incidents(writer.dump_verified(unrelated, version))
    before = span_incident_bindings(source, original)
    modified = project_from(previous, paths, catalog)
    for edge in {tuple(ref.values()) for row in before for ref in row['edge_refs']}:
        modified.model(edge).contents[19].value = incident_operations.string('Alternative')
    candidate = project_from(save_project(modified), paths, catalog)
    revised = archived_incidents(
        [(name, kind, {**selector, 'track_id': 'Alternative'}) for name, kind, selector in specifications])
    expected = span_incident_bindings(revised, candidate)
    reviews = [review(a, b) for a, b in zip(before, expected, strict=True)]
    with pytest.raises(ValueError, match='No original edge'):
        rebind_span_incidents(source, original, candidate, reviews[:-1])
    with pytest.raises(ValueError, match='Original Incident Edge references'):
        rebind_span_incidents(source, original, candidate, [{**reviews[0], 'expected_edge_refs': []}, *reviews[1:]])
    output, receipts = rebind_span_incidents(source, original, candidate, reviews)
    assert [receipt['type'] for receipt in receipts] == [6, 7, 8]
    assert span_incident_bindings(output, candidate) == expected
    assert expected[2]['attachment']['direction'] == 'decreasing'
    source_graph, _ = writer.load_next_compatible(source)
    result, _ = writer.load_next_compatible(output)
    for prior, saved in zip(catalogs.array(source_graph.contents[1].value), catalogs.array(result.contents[1].value)):
        assert saved.contents[10].value is saved.contents[11].value
        assert catalogs.text(saved.contents[10].value) == new_selector['track_id']
        for slot in (10, 11):
            saved.contents[slot].value = prior.contents[slot].value
    assert writer.fingerprint(result) == writer.fingerprint(source_graph)


def test_unchanged_selector_requires_review_when_same_route_id_moves_to_different_edges(crossing):
    documents, catalog, operation = crossing
    paths = {name: f'{name}.opentrack' for name in documents}
    original = project_from(documents, paths, catalog)
    candidate, _ = apply(documents, catalog, operation)
    selector = {'begin_route': 'R:A-B', 'end_route': 'R:A-B',
                'begin_offset_km': '0.2', 'end_offset_km': '0.7'}
    courses = archived_incidents([('Route', 'route_span_speed', selector)])
    before, = span_incident_bindings(courses, original)
    after, = span_incident_bindings(courses, candidate)
    assert before['attachment']['routes'] == after['attachment']['routes']
    assert before['edge_refs'] != after['edge_refs']
    assert after['attachment']['begin']['edge_offset_m'] == spans.metres('0.2')
    with pytest.raises(ValueError, match='needs explicit review'):
        rebind_span_incidents(courses, original, candidate, [])
    with pytest.raises(ValueError, match='Replacement Incident Edge references'):
        rebind_span_incidents(courses, original, candidate, [
            {**review(before, after), 'replacement_edge_refs': before['edge_refs']}])
    output, receipts = rebind_span_incidents(courses, original, candidate, [review(before, after)])
    assert output == courses
    assert receipts == [{'name': 'Route', 'type': 13, 'incident_index': 0, 'before': before, 'after': after}]
    assert rebind_span_incidents(courses, original, original, []) == (courses, [])


def test_distinct_route_spans_require_a_unique_ordered_native_course_itinerary():
    documents, catalog, paths, _ = local_routes('Line.opentrack')
    graph = project_from(documents, paths, catalog)
    selector = {'begin_route': 'R0', 'end_route': 'R1', 'begin_offset_km': '0.02',
                'end_offset_km': '0.06', 'course_id': 'T01'}
    courses = archived_incidents([('Route', 'route_span_speed', selector)], course=['Service'])
    binding, = span_incident_bindings(courses, graph)
    span = binding['attachment']
    assert span['itinerary'] == 'Service'
    assert [ref['name'] for ref in span['routes']] == ['R0', 'R1']
    assert len(binding['edge_refs']) == 2
    assert span['edges'][0]['edge_interval_m'][0] == spans.metres('0.02')
    assert span['edges'][1]['edge_interval_m'][1] == spans.metres('0.06')
    revised = {**binding['selector'], 'end_offset_km': '0.065'}
    updated, result = rebind_span_incidents(courses, graph, graph, [review(binding, binding, replacement_selector=revised)])
    cold, = span_incident_bindings(updated, graph)
    assert cold['selector'] == revised and result[0]['after'] == cold
    assert cold['attachment']['end']['edge_offset_m'] == spans.metres('0.065')
    backward = {**selector, 'begin_route': 'R1', 'end_route': 'R0'}
    with pytest.raises(ValueError, match='forward order'):
        span_incident_bindings(archived_incidents([('Backwards', 'route_span_speed', backward)], course=['Service']), graph)
    with pytest.raises(ValueError, match='one saved Itinerary'):
        span_incident_bindings(archived_incidents([('Choice', 'route_span_speed', selector)], course=['Service', 'Service']), graph)
