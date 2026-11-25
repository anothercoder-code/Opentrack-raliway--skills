from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from opentrack_ai.current_archive import native_interlocking as audit
from opentrack_ai.current_archive.native_interlocking_tools import VerifyNativeInterlocking


def occupation(*rows):
    return '\n'.join((
        '// Produced by OpenTrack: Mon Nov 23 17:01:03 2026',
        '// Type    : OT_TimeXPlot',
        '// Desc.   : OT_occ',
        '// x-Legend: [s]',
        *rows,
    ))


def test_complete_native_cycles_are_grouped_by_course_in_file_order():
    text = occupation('20.00\tNear\tSR\tEast', '21.00\tNear\tSO\tEast',
                      '22.00\tNear\tEO\tEast', '23.00\tNear\tER\tEast',
                      '10.00\tNear\tSR\tWest', '-1\tNear\tSO\tWest',
                      '-1\tNear\tEO\tWest', '13.00\tNear\tER\tWest')
    assert audit.decode_cycles(text, 'Near') == [
        {'course_id': 'East', 'reservation_s': [20, 23], 'occupation_s': [21, 22]},
        {'course_id': 'West', 'reservation_s': [10, 13], 'occupation_s': [None, None]},
    ]
    with pytest.raises(ValueError, match='Invalid original occupation block'):
        audit.decode_cycles(text.replace('22.00\tNear\tEO\tEast', '22.00\tNear\tEO\tWest'), 'Near')
    with pytest.raises(ValueError, match='Expected seconds'):
        audit.decode_cycles(text.replace('[s]', '[km]'), 'Near')


def test_corroboration_rejects_matching_clocks_at_the_wrong_route_position():
    cycle = {'reservation_s': [10, 39], 'occupation_s': [17, 35]}
    span = {'from_m': 100, 'to_m': 200, 'route_edge_ids': [7]}
    traces = {'step1': [(10, 0), (10, 200)], 'step2': [(39, 100), (39, 200)],
              'st1': [(17, 98), (35, 210)]}
    assert audit.corroborate(cycle, span, traces, 5)['occupation_front_m'] == [98, 210]
    wrong_step = {**traces, 'step2': [(39, 500), (39, 600)]}
    with pytest.raises(ValueError, match='Native stair transition'):
        audit.corroborate(cycle, span, wrong_step, 5)
    wrong_front = {**traces, 'st1': [(17, 52), (35, 210)]}
    with pytest.raises(ValueError, match='front trajectory'):
        audit.corroborate(cycle, span, wrong_front, 5)
    interpolated_only = {**traces, 'st1': [(16, 97), (18, 99), (35, 210)]}
    with pytest.raises(ValueError, match='lacks an independent'):
        audit.corroborate(cycle, span, interpolated_only, 5)


def test_parallel_monitored_spans_and_full_itineraries_are_independent_checks():
    a = {'document': 'J1', 'safety_element_id': 1, 'occupation_s': [21, 35], 'reservation_s': [17, 40]}
    b = {'document': 'J1', 'safety_element_id': 2, 'occupation_s': [31, 55], 'reservation_s': [27, 60]}
    movements = {'East': a, 'West': b}
    data = SimpleNamespace(traversal=lambda course, *_: movements[course], routes={
        'East': {'spans': {('J1', 1): [], ('J2', 23): []}},
        'West': {'spans': {('J1', 2): [], ('J2', 23): []}},
    })
    specs = {side: {'course_id': course, 'resource': {}} for side, course in [('first', 'East'), ('second', 'West')]}
    result = audit.parallel_traversal(data, {**specs, 'scope': 'monitored_spans', 'minimum_overlap_s': 4}, 5)
    assert result['verified']
    assert result['occupation_overlap_s'] == 4
    assert result['reservation_overlap_s'] == 13
    assert result['shared_saved_itinerary_elements'] == [{'document': 'J2', 'safety_element_id': 23}]
    assert not audit.parallel_traversal(data, {**specs, 'scope': 'disjoint_itineraries', 'minimum_overlap_s': 4}, 5)['verified']
    assert not audit.parallel_traversal(data, {**specs, 'scope': 'monitored_spans', 'minimum_overlap_s': 5}, 5)['verified']


def test_release_must_follow_both_route_and_native_clock_order():
    first = {'from_m': 25, 'to_m': 50, 'reservation_s': [10, 19], 'occupation_s': [11, 15]}
    second = {'from_m': 75, 'to_m': 100, 'reservation_s': [15, 28], 'occupation_s': [20, 24]}
    data = SimpleNamespace(traversal=lambda _, resource, __: resource)
    request = {'course_id': 'East', 'resources': [first, second], 'minimum_release_gap_s': 9}
    assert audit.ordered_release(data, request, 5)['verified']
    with pytest.raises(ValueError, match='not ordered along'):
        audit.ordered_release(data, {**request, 'resources': [second, first]}, 5)
    assert not audit.ordered_release(data, {**request, 'minimum_release_gap_s': 9.1}, 5)['verified']


def test_handover_checks_adjacency_and_the_whole_original_authority_trace():
    a = {'resource': 'Cross', 'course_id': 'East', 'reservation_s': [17, 40]}
    b = {'resource': 'Cross', 'course_id': 'West', 'reservation_s': [45, 60]}
    rows = [a, b]
    data = SimpleNamespace(traversal=lambda course, *_: a if course == 'East' else b, resource=lambda _: ({}, rows))
    request = {'resource': {}, 'leading_course': 'East', 'following_course': 'West', 'minimum_gap_s': 5}
    assert audit.authority_handover(data, request, 5)['verified']
    intruder = {'resource': 'Cross', 'course_id': 'Extra', 'reservation_s': [20, 21]}
    rows.append(intruder)
    outcome = audit.authority_handover(data, request, 5)
    assert not outcome['consecutive_authorities']
    assert outcome['whole_trace_authority_exclusion']['overlapping_cycle_count'] == 1
    assert not outcome['verified']


def test_schema_requires_independent_terminal_outcome():
    with pytest.raises(ValidationError, match='terminal_station'):
        VerifyNativeInterlocking.model_validate({
            'output_directory': 'OTAI/workspaces/Run/project/output',
            'evidence_directory': 'OTAI/workspaces/Run/evidence',
            'course_outcomes': [{'course_id': 'East'}],
        })
