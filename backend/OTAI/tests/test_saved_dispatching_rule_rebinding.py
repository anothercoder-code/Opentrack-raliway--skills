from xml.etree import ElementTree

import pytest

from opentrack_ai.current_archive.dispatching_rules_otd import RuleSet, dispatching_rules
from opentrack_ai.current_archive.route_lifecycle_tools import edit_route_lifecycle
from opentrack_ai.current_archive.saved_dispatching_rule_rebinding import (
    dispatching_rule_route_bindings, rebind_dispatching_rule_routes,
)
from opentrack_ai.current_archive.saved_geometry import project_from, transform

from test_dispatching_rules_otd import route, ruleset
from test_saved_multi_document_reroute import chain


def _bindings(blob, project, mode):
    return {row['route_id']: row for row in dispatching_rule_route_bindings(blob, project, mode)}


def _review(before, after):
    return {'old': before['route'], 'new': after['route']}


def _rename(docs, paths, catalog, identity, new_name):
    changed, receipt = edit_route_lifecycle(docs, paths, catalog, identity['document'],
        {'name': identity['route_name'], 'array_id': identity['array_id'], 'start_id': identity['start_end_id']},
        {'action': 'rename', 'new_name': new_name})
    return {**docs, **changed}, receipt['after']


def _one_rule(reference):
    return RuleSet.model_validate({'name': 'Retain Original Policy', 'applies_to': [reference], 'rules': [
        {'kind': 'conditions', 'conditions': [{'route': reference, 'stop_code': 'extendedDwell',
                                               'extended_dwell_s': 11.75}]},
    ]})


def test_cross_document_assignment_and_condition_rename_only_patch_value_bytes(chain):
    docs, paths, catalog, _ = chain
    original = project_from(docs, paths, catalog)
    blob, _ = dispatching_rules(original, [ruleset(conditions=[
        {'route': route('B', 8, 'R:B-C'), 'reservation': 'free'},
        {'route': route('B', 9, 'R:B-A'), 'minimum_length_m': 120},
        {'route': route('C', 9, 'R:C-B'), 'stop_code': 'extendedDwell', 'extended_dwell_s': 30.5},
    ])], 'compound')
    blob = blob.replace(b'<routes>', b'<routes>\n\t\t<!-- policy operator: keep this comment -->').replace(
        b'id="A-8-R:A-B"', b"id = 'A-8-R:A-B'").replace(b'\n', b'\r\n')
    old = _bindings(blob, original, 'compound')
    revised, assignment = _rename(docs, paths, catalog, old['A-8-R:A-B']['route'], 'R:A-B&west')
    revised, condition = _rename(revised, paths, catalog, old['B-8-R:B-C']['route'], 'R:"B-C"')
    updated = project_from(revised, paths, catalog)
    reviews = []
    for key, receipt in (('A-8-R:A-B', assignment), ('B-8-R:B-C', condition)):
        reviews.append({'old': old[key]['route'], 'new': route(receipt['document'], receipt['start_id'], receipt['name'])
                        | {'array_id': receipt['array_id']}})
    with pytest.raises(ValueError, match='identity review'):
        rebind_dispatching_rule_routes(blob, original, updated, 'compound', reviews[:1])
    saved, report = rebind_dispatching_rule_routes(blob, original, updated, 'compound', reviews)
    assert saved == blob.replace(b'id = \'A-8-R:A-B\'', b'id = \'A-8-R:A-B&amp;west\'').replace(
        b'routeID="B-8-R:B-C"', b'routeID="B-8-R:&quot;B-C&quot;"')
    migrated = {row['before_route_id']: row for row in report}
    assert [(migrated[key]['assignments'], migrated[key]['conditions'], migrated[key]['footprint_changed'])
            for key in ('A-8-R:A-B', 'B-8-R:B-C')] == [(1, 0, False), (0, 2, False)]
    after = _bindings(saved, updated, 'compound')
    assert after['B-9-R:B-A'] == old['B-9-R:B-A'] and after['C-9-R:C-B'] == old['C-9-R:C-B']
    assert ElementTree.fromstring(saved).find('.//routeExclusionRule[@maximalNumberOfTrains="2"]') is not None


def test_same_route_id_with_changed_crossing_requires_explicit_resource_review(chain):
    docs, paths, catalog, operation = chain
    original = project_from(docs, paths, catalog)
    blob, _ = dispatching_rules(original, [_one_rule(route('A', 8, 'R:A-B'))], 'compound')
    revised, _ = transform(docs, paths, catalog, 'A', operation)
    updated = project_from(revised, paths, catalog)
    before, = dispatching_rule_route_bindings(blob, original, 'compound')
    after, = dispatching_rule_route_bindings(blob, updated, 'compound')
    assert before['route'] == after['route'] and before['footprint'] != after['footprint']
    with pytest.raises(ValueError, match='explicit resource review'):
        rebind_dispatching_rule_routes(blob, original, updated, 'compound', [])
    saved, changes = rebind_dispatching_rule_routes(blob, original, updated, 'compound', [_review(before, after)])
    assert saved == blob
    change, = changes
    assert change['assignments'] == change['conditions'] == 1 and change['footprint_changed'] is True
    assert [leg['edge'] for leg in change['before_footprint']['movement']['legs']] != [
        leg['edge'] for leg in change['after_footprint']['movement']['legs']]
    assert change['before_footprint']['movement']['safety_elements'] != change['after_footprint']['movement']['safety_elements']


def test_same_text_name_mode_resolves_new_owner_only_with_review(chain):
    docs, paths, catalog, _ = chain
    original = project_from(docs, paths, catalog)
    blob, _ = dispatching_rules(original, [_one_rule(route('B', 8, 'R:B-C'))], 'route_name')
    before, = dispatching_rule_route_bindings(blob, original, 'route_name')
    reverse_source, _ = dispatching_rules(original, [_one_rule(route('B', 9, 'R:B-A'))], 'route_name')
    reverse, = dispatching_rule_route_bindings(reverse_source, original, 'route_name')
    revised, _ = _rename(docs, paths, catalog, before['route'], 'R:RetiredName')
    revised, _ = _rename(revised, paths, catalog, reverse['route'], 'R:B-C')
    updated = project_from(revised, paths, catalog)
    after, = dispatching_rule_route_bindings(blob, updated, 'route_name')
    assert before['route_id'] == after['route_id'] == 'R:B-C' and after['route']['start_end_id'] == 9
    with pytest.raises(ValueError, match='explicit identity review'):
        rebind_dispatching_rule_routes(blob, original, updated, 'route_name', [])
    saved, report = rebind_dispatching_rule_routes(blob, original, updated, 'route_name', [_review(before, after)])
    assert saved == blob and report[0]['old']['start_end_id'] == 8 and report[0]['new']['start_end_id'] == 9


def test_same_edge_exclusion_and_turnout_controls_require_resource_review(chain):
    docs, paths, catalog, _ = chain
    original = project_from(docs, paths, catalog)
    blob, _ = dispatching_rules(original, [_one_rule(route('A', 8, 'R:A-B'))], 'compound')
    revised, _ = transform(docs, paths, catalog, 'A', {'action': 'set_edge_exclusion', 'edge_id': 23,
        'target_edge_id': 20, 'expected_target_edge_id': None})
    switch, _ = transform({**docs, **revised}, paths, catalog, 'A', {'action': 'set_vertex_details', 'end_id': 13,
        'both_halves': False, 'changes': {'switch_time_s': 2.5, 'default_second_leg': True}})
    updated = project_from({**docs, **revised, **switch}, paths, catalog)
    before, = dispatching_rule_route_bindings(blob, original, 'compound')
    after, = dispatching_rule_route_bindings(blob, updated, 'compound')
    with pytest.raises(ValueError, match='explicit resource review'):
        rebind_dispatching_rule_routes(blob, original, updated, 'compound', [])
    saved, report = rebind_dispatching_rule_routes(blob, original, updated, 'compound', [_review(before, after)])
    assert saved == blob
    change, = report
    left, right = [next(leg for leg in change[key]['movement']['legs'] if leg['edge'] == ('A', 23))
                   for key in ('before_footprint', 'after_footprint')]
    assert left['exclusion_target'] is None
    assert right['exclusion_target'] == {'edge': ('A', 20), 'safety_element': ('A', 3)}
    turnout = right['departure_turnout']
    assert turnout == {**left['departure_turnout'], 'default_edge': ('A', 31), 'switch_time_s': 2.5}


def test_refuses_unresolved_wrong_native_array_id_and_rule_collision(chain):
    docs, paths, catalog, _ = chain
    project = project_from(docs, paths, catalog)
    references = route('A', 8, 'R:A-B'), route('B', 8, 'R:B-C')
    blob, _ = dispatching_rules(project, [ruleset(applies_to=references[0]),
        ruleset(applies_to=references[1], rule_name='Second')], 'compound')
    before = _bindings(blob, project, 'compound')
    a, b = before['A-8-R:A-B'], before['B-8-R:B-C']
    assert rebind_dispatching_rule_routes(blob, project, project, 'compound', []) == (blob, [])
    with pytest.raises(ValueError, match='does not change'):
        rebind_dispatching_rule_routes(blob, project, project, 'compound', [_review(a, a)])
    invalid = {'old': a['route'], 'new': {**b['route'], 'array_id': b['route']['array_id'] + 100}}
    with pytest.raises(ValueError, match='target does not match'):
        rebind_dispatching_rule_routes(blob, project, project, 'compound', [invalid])
    with pytest.raises(ValueError, match='collapse to one revised Route'):
        rebind_dispatching_rule_routes(blob, project, project, 'compound', [_review(a, b)])
    single_assignment, _ = dispatching_rules(project, [ruleset()], 'compound')
    with pytest.raises(ValueError, match='collapse to one revised Route'):
        rebind_dispatching_rule_routes(single_assignment, project, project, 'compound', [_review(a, b)])
    with pytest.raises(ValueError, match='unresolved original main Route'):
        rebind_dispatching_rule_routes(blob.replace(b'A-8-R:A-B', b'A-8-NOT-A-ROUTE'), project, project, 'compound', [])


def test_refuses_unsupported_xml_dtd_and_predicate_without_writing(chain):
    docs, paths, catalog, _ = chain
    project = project_from(docs, paths, catalog)
    blob, _ = dispatching_rules(project, [ruleset()], 'compound')
    with pytest.raises(ValueError, match='otd.dtd prologue'):
        rebind_dispatching_rule_routes(blob.replace(b'otd.dtd', b'https://invalid.example/otd.dtd'),
                                       project, project, 'compound', [])
    with pytest.raises(ValueError, match='Unsupported OTD exclusion condition'):
        rebind_dispatching_rule_routes(blob.replace(b'routeReservationState', b'comparePriority'),
                                       project, project, 'compound', [])
