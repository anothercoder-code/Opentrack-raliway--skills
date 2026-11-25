import pytest

from opentrack_ai.current_archive.dispatching_rules_otd import RuleSet, dispatching_rules
from opentrack_ai.current_archive.native_otd_reservation_effect import (
    ReservationWitness, _compare_timing, _exact_advance, _isolate_policy, _preferences,
)
from opentrack_ai.current_archive.saved_geometry import project_from

from test_saved_multi_document_reroute import chain


def _observations(target, begins=32713.08, ends=32853.15):
    return ({'reservation_s': target, 'release_s': target + 200},
            {'reservation_s': begins, 'release_s': ends})


def test_timing_uses_control_overlap_unchanged_holder_and_enabled_handover():
    receipt = _compare_timing(_observations(32746.18), _observations(32853.35), 1)
    assert receipt['native_otd_reservation_effect_verified'] and all(receipt['checks'].values())
    assert receipt['observed_control_before_holder_release_s'] == 106.97
    assert receipt['enabled_release_to_target_reservation_s'] == 0.2
    assert receipt['target_reservation_delay_s'] == 107.17


@pytest.mark.parametrize(('before', 'after', 'failure'), [
    (_observations(32853.15), _observations(32900), 'control_authority_granted_during_holder_reservation'),
    (_observations(32746.18), _observations(32853.14), 'enabled_authority_granted_only_after_holder_release'),
    (_observations(32746.18), _observations(32853.35, ends=32852.9), 'holder_reservation_and_release_unchanged'),
    (_observations(32853.12), _observations(32853.15), 'enabled_authority_delayed'),
])
def test_both_verified_runs_without_controlled_timing_effect_do_not_pass(before, after, failure):
    receipt = _compare_timing(before, after, 1)
    assert not receipt['native_otd_reservation_effect_verified'] and not receipt['checks'][failure]


def test_full_native_stair_step_requires_both_exact_route_coordinates():
    points = [(1, 2900), (10, 2900), (10, 4550), (21, 4550), (21, 5300), (25, 5300)]
    assert _exact_advance(points, 2900, 4550, 'step1', 'H2W1') == {'time_s': 10, 'from_m': 2900, 'to_m': 4550}
    for start, end in ((2900, 4300), (3000, 4550), (2900, 5300)):
        with pytest.raises(ValueError, match='one exact'):
            _exact_advance(points, start, end, 'step1', 'H2W1')
    with pytest.raises(ValueError, match='staircase'):
        _exact_advance([(0, 2900), (10, 4550)], 2900, 4550, 'step2', 'H2W1')


def test_old_unhashed_preferences_report_the_limit_and_new_launches_require_equality():
    assert not _preferences({}, {})['same_frozen_preferences_verified']
    record = {'prefs_sha256_before': None, 'prefs_sha256_after': None}
    assert _preferences(record, record)['same_frozen_preferences_verified']
    with pytest.raises(ValueError, match='incomplete'):
        _preferences(record, {})
    with pytest.raises(ValueError, match='differs'):
        _preferences(record, {**record, 'prefs_sha256_before': 'a' * 64})


def _witness(course, document, end_id, name):
    return ReservationWitness.model_validate({'course_id': course, 'route': {
        'document': document, 'start_end_id': end_id, 'route_name': name, 'array_id': 0,
    }})


def test_enabled_xml_allows_only_the_reviewed_isolated_attachment_and_predicate(chain):
    docs, paths, catalog, _ = chain
    project = project_from(docs, paths, catalog)
    target = _witness('APPROACH', 'A', 8, 'R:A-B')
    holder = _witness('HOLDER', 'B', 8, 'R:B-C')
    target_ref = target.route.model_dump(exclude={'array_id'})
    holder_ref = holder.route.model_dump(exclude={'array_id'})
    rule = RuleSet.model_validate({'name': 'Only active holder', 'applies_to': [target_ref], 'rules': [
        {'kind': 'conditions', 'conditions': [{'route': holder_ref, 'reservation': 'reserved'}]},
    ]})
    original, _ = dispatching_rules(project, [rule], 'compound')
    assert _isolate_policy(original, project, 'compound', target, holder) == {
        'ruleset': 'Only active holder', 'applies_to': 'A-8-R:A-B', 'reserved_predicate_on': 'B-8-R:B-C',
    }
    with pytest.raises(ValueError, match='sole predicate'):
        _isolate_policy(original.replace(b'"reserved"', b'"free"'), project, 'compound', target, holder)
    with pytest.raises(ValueError, match='sole OTD'):
        _isolate_policy(original, project, 'compound', holder, target)
    second = rule.model_copy(update={'name': 'Also active', 'applies_to': [holder.route]})
    added, _ = dispatching_rules(project, [rule, second], 'compound')
    with pytest.raises(ValueError, match='exactly one OTD'):
        _isolate_policy(added, project, 'compound', target, holder)
