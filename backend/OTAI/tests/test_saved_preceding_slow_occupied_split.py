"""Guard adjacency and whole-train separation of the independent native predecessor."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import saved_preceding_slow_occupied_split as proof
from opentrack_ai.current_archive.saved_geometry_tools import MainSignalRouteSplit

from test_saved_main_signal_split import _join_split_source


def _end(i):
    return 'Line', i


@pytest.fixture(scope='module')
def stock():
    return _join_split_source()


def _review():
    return {
        'route': {'document': 'Line', 'name': 'Predecessor', 'array_id': 0, 'start_id': 1},
        'zone': {'start': {'document': 'Line', 'end_id': 1}, 'finish': {'document': 'Line', 'end_id': 2},
                 'expected_speed_kmh': 40, 'expected_native_aspect_code': 4, 'expected_head_only': False},
    }


def test_native_typed_entry_requires_separate_predecessor_and_independent_occ(stock):
    request = deepcopy(stock[-1]['split_route'])
    request['preceding_fixed_slow_zone'] = _review()
    assert MainSignalRouteSplit.model_validate(request).preceding_fixed_slow_zone.zone.expected_speed_kmh == 40
    for changes in ({'occupied_entry': None}, {'reserve_with_previous': True}):
        with pytest.raises(ValueError, match='distinct original Route'):
            MainSignalRouteSplit.model_validate({**request, **changes})
    request['preceding_fixed_slow_zone']['route'] = request['route']
    with pytest.raises(ValueError, match='distinct original Route'):
        MainSignalRouteSplit.model_validate(request)


@pytest.fixture
def model(stock, monkeypatch):
    before, old, front, rear, alternative = (object() for _ in range(5))
    movements = {before: [_end(1), _end(2), _end(3)], old: [_end(3), _end(4), _end(5)],
                 front: [_end(3), _end(4)], rear: [_end(4), _end(5)]}
    signature = {'identity': _review()['route'], 'slow_zone': {'original_effective_zone_anchors': (_end(1), _end(2))}}
    ordinary = {('Line', 11)}
    occupied = {('Line', 17)}
    locks = {'ordinary_exclusions': set(), 'occupied_exclusions': set()}
    distances = {'Through': [0, 50, 200, 300, 400], 'Join donor': [0, 50, 200, 300, 400]}
    sequences = {key: [before, old] for key in distances}
    graph = SimpleNamespace(route_view=movements.__getitem__, dests=list(distances))
    monkeypatch.setattr(proof, '_ordinary_fixed_predecessor', lambda *_: (before, movements[before], signature))
    monkeypatch.setattr(proof, '_locks', lambda project, nodes: (
        (ordinary, locks['ordinary_exclusions']) if nodes[0] == _end(1) else (occupied, locks['occupied_exclusions'])))
    monkeypatch.setattr(proof, 'ident', lambda itinerary: (itinerary,))
    monkeypatch.setattr(proof, 'itinerary_routes', lambda project, itinerary: iter(sequences[itinerary]))
    monkeypatch.setattr(proof, 'route_trace', lambda project, itinerary: {
        '_directed_nodes': [_end(i) for i in range(1, 6)], '_node_distances_m': distances[itinerary]})
    entry = {'receiver_course': 'A01', 'donor_course': 'A02', 'receiver_length_m': 22, 'donor_length_m': 22,
             'berth': {'donor_contact_distance_m': 378}}
    return SimpleNamespace(graph=graph, before=before, old=old, front=front, rear=rear, alternative=alternative,
                           entry=entry, locks=locks, distances=distances, sequences=sequences, banks=stock[3])


def _audit(model):
    return proof.audit_preceding_slow_occupied_split(model.graph, [model.old], _end(4), model.entry, _review(), model.banks)


def test_old_and_new_sequences_keep_the_exact_predecessor_and_locks(model):
    original = _audit(model)
    assert all(row['clearance_before_original_occupied_entry_m'] == 128 for row in original['course_axes'].values())
    for itinerary in model.sequences:
        model.sequences[itinerary] = [model.before, model.front, model.rear]
    saved = proof.check_preceding_slow_occupied_split(
        model.graph, model.front, model.rear, _end(4), model.entry, _review(), model.banks, original)
    assert saved['preceding_profile_and_resources_preserved']


def test_a_donor_bypassing_the_saved_predecessor_is_rejected(model):
    model.sequences['Join donor'] = [model.before, model.alternative, model.old]
    with pytest.raises(ValueError, match='consecutively once'):
        _audit(model)


def test_body_touching_predecessor_zone_and_shared_exclusion_are_rejected(model):
    model.distances['Join donor'][1] = 178
    with pytest.raises(ValueError, match='must clear the fixed slow zone'):
        _audit(model)
    model.distances['Join donor'][1] = 50
    model.locks['occupied_exclusions'].add(('Line', 11))
    with pytest.raises(ValueError, match='shares an occupied-movement'):
        _audit(model)

