from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import native_throat_passage as passage


@pytest.fixture
def topology(monkeypatch):
    before, approach, middle, exit, after = ('EA', 8), ('EA', 27), ('RDG', 4), ('RDG', 16), ('WB', 4)
    path = [before, approach, middle, exit, after]
    edges = dict(zip(zip(path, path[1:]), [('EA', 31), ('RDG', 32), ('RDG', 23), ('WB', 20)], strict=True))
    connectors = {approach: ('EA', 20), exit: ('RDG', 17)}
    reciprocal = {('EA', 20): ('RDG', 25), ('RDG', 25): ('EA', 20),
                  ('RDG', 17): ('WB', 0), ('WB', 0): ('RDG', 17)}
    distances = {('EA', 31): 500, ('RDG', 32): 675, ('RDG', 23): 325, ('WB', 20): 600}
    project = SimpleNamespace(
        dests=[SimpleNamespace(contents=[None, SimpleNamespace(value='through')])],
        dest_view=lambda _: (path, None),
        edge_between=lambda a, b: edges[a, b],
        related=connectors.__getitem__, block_end=reciprocal.__getitem__,
        model=lambda edge: SimpleNamespace(contents=[None] * 9 + [SimpleNamespace(values=[None, distances[edge]])]),
        roots={'RDG': 'worksheet'},
    )
    monkeypatch.setattr(passage.catalogs, 'text', lambda value: value)
    monkeypatch.setattr(passage.groups, 'records', lambda *_: [
        {'name': 'Throat', 'saved_document': 'RDG', 'selected': True, 'edge_ids': [32, 23], 'unresolved_edge_ids': []}
    ])
    course = {'course_id': 'A', 'output_offset_m': 25.0, 'enabled': True, 'itineraries': ['through']}
    boundaries = [passage.WorksheetBoundary(from_document='EA', from_end_id=27, to_document='RDG', to_end_id=4),
                  passage.WorksheetBoundary(from_document='RDG', from_end_id=16, to_document='WB', to_end_id=4)]
    spec = passage.ThroatPassage(course_id='A', boundaries=boundaries,
                                 groups=[passage.GroupMembers(document='RDG', group='Throat', edge_ids=[23, 32])])
    return project, course, spec


def test_preflight_binds_directed_ends_reciprocal_connectors_and_exact_monitored_edges(topology):
    project, course, spec = topology
    result = passage.frozen_passage(project, course, spec)
    assert [(row['connectors'], row['distance_m']) for row in result['boundaries']] == [
        ([['EA', 20], ['RDG', 25]], 525.0), ([['RDG', 17], ['WB', 0]], 1525.0)]
    assert result['groups'][0]['spans'] == [{'from_m': 525.0, 'to_m': 1525.0, 'edge_ids': [32, 23]}]
    assert result['terminal_m'] == 2125.0
    spec.boundaries.reverse()
    with pytest.raises(ValueError, match='ordered directed'):
        passage.frozen_passage(project, course, spec)
    spec.boundaries.reverse()
    spec.groups[0].edge_ids = [20, 32]
    with pytest.raises(ValueError, match='Edge membership'):
        passage.frozen_passage(project, course, spec)


def test_sample_bracket_preserves_stationary_plateau_and_never_interpolates():
    points = [(3, 98), (3.2, 100), (20.5, 100), (20.7, 101)]
    positions = [98, 100, 100, 101]
    assert passage.crossing_samples(points, positions, 100) == [[3, 98], [20.7, 101]]
    with pytest.raises(ValueError, match='No original front movement bracket'):
        passage.crossing_samples(points, positions, 101)


@pytest.fixture
def partition():
    group = {'spans': [{'from_m': 100, 'to_m': 210, 'edge_ids': [32, 21]},
                       {'from_m': 260, 'to_m': 390, 'edge_ids': [23]}]}
    first = {'course_id': 'A', 'reservation_s': [10, 45], 'occupation_s': [12, 43]}
    second = {'course_id': 'A', 'reservation_s': [40, 60], 'occupation_s': [48, 55]}
    traces = {'step1': [(10, 0), (10, 210), (40, 210), (40, 510), (60, 510)],
              'step2': [(45, 0), (45, 210), (60, 210)],
              'st1': [(12, 99), (43, 245), (48, 258), (55, 470), (59, 510)]}
    return group, first, second, traces


def audit_cycles(group, cycles, traces):
    return passage.group_passage(group, cycles, traces, passage.advances(traces['step1']),
                                 passage.advances(traces['step2']), 5)


def test_disconnected_monitored_members_remain_separate_and_closing_clock_is_not_release_advance(partition):
    group, first, second, traces = partition
    result = audit_cycles(group, [first, second], traces)
    assert result['spans'] == group['spans']
    a, b = result['cycles']
    assert a['monitored_span_indices'] == [0] and b['monitored_span_indices'] == [1]
    assert a['native_release_advances'][0]['to_m'] == 210
    assert b['simulation_end_release_clock_only'] and not b['native_release_advances']
    with pytest.raises(ValueError, match='cover each frozen monitored span exactly once'):
        audit_cycles(group, [first], traces)
    with pytest.raises(ValueError, match='corresponding Route authority advance'):
        audit_cycles(group, [{**first, 'reservation_s': [9, 45]}, second], traces)


def test_rejects_unrelated_release_advance_even_at_matching_clock(partition):
    group, first, second, traces = partition
    unrelated_release = {**traces, 'step2': [(45, 0), (45, 210), (60, 450), (60, 500)]}
    with pytest.raises(ValueError, match='matching Route advance or simulation-end'):
        audit_cycles(group, [first, second], unrelated_release)
