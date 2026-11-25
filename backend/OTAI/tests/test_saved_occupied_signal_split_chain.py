"""Fail closed when the occupied-entry review omits part of its native stock chain."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive.saved_occupied_signal_split import _linked_join_event


def review():
    return {'receiver_course': 'Receiver', 'donor_course': 'Donor', 'station_sign': 'R4',
            'formation_events': [
                {'kind': 'split', 'main_course': 'Parent', 'other_course': 'Donor',
                 'station_sign': 'R2', 'main_visit_index': 1},
                {'kind': 'join', 'main_course': 'Receiver', 'other_course': 'Donor',
                 'station_sign': 'R4', 'main_visit_index': 1},
            ], 'turnrounds': [{'from_course': 'Parent', 'to_course': 'Receiver', 'movement': 'continue'}]}


@pytest.mark.parametrize('missing', ['formation_events', 'turnrounds'])
def test_occupied_split_requires_both_complete_chain_reviews(missing):
    entry = review()
    entry.pop(missing)
    with pytest.raises(ValueError, match='one preceding split, one occupied join'):
        _linked_join_event(None, {}, b'', entry)


@pytest.mark.parametrize(('group', 'index', 'field', 'changed'), [
    ('formation_events', 0, 'other_course', 'Extra'),
    ('formation_events', 1, 'station_sign', 'R3'),
    ('formation_events', 1, 'main_course', 'Parent'),
    ('turnrounds', 0, 'movement', 'reverse'),
])
def test_occupied_split_requires_exact_donor_receiver_and_continuation(group, index, field, changed):
    entry = review()
    entry[group][index][field] = changed
    with pytest.raises(ValueError, match='original donor and same-direction continuing receiver'):
        _linked_join_event(None, {}, b'', entry)


def test_occupied_split_does_not_accept_an_extra_formation_or_link():
    baseline = review()
    for group in ('formation_events', 'turnrounds'):
        entry = deepcopy(baseline)
        entry[group].append(entry[group][0])
        with pytest.raises(ValueError, match='one preceding split, one occupied join'):
            _linked_join_event(None, {}, b'', entry)
