"""Bind original interlocking timing to the two effective Routes of a native signal split."""

from math import isfinite

from . import path_functions
from .multi_document.core import ident, need, ref
from .saved_terminal_overlap import _edge_locking_resources


DEFAULT_ROUTE_TIMING = {
    'release_distance_m': 0, 'announce_distance_m': 400, 'release_time_s': 5, 'reserve_time_s': 0,
    'approach_length_m': 0.0, 'approach_speed_kmh': 0.0, 'reservation_distance_m': 5000,
    'use_reservation_distance': False, 'use_release_distance': False,
}
_TIMING_FIELDS = ('release_distance_m', 'announce_distance_m', 'release_time_s', 'reserve_time_s')
_APPROACH_FIELDS = ('approach_length_m', 'approach_speed_kmh')
_DISTANCE_FIELDS = ('reservation_distance_m', 'use_reservation_distance', 'use_release_distance')


def stored_route_timing(route):
    release, announce, release_s, reserve_s = route.contents[5].values[:4]
    length, speed = route.contents[8].values
    reserve, use_reserve, use_release = route.contents[10].values
    need(all(type(value) is int and value in (0, 1) for value in (use_reserve, use_release)),
         'Expected the original explicit Route distance flag encoding')
    return dict(zip(DEFAULT_ROUTE_TIMING, (release, announce, release_s, reserve_s, length, speed,
                                           reserve, bool(use_reserve), bool(use_release)), strict=True))


def reviewed_route_timing(review):
    fields = {key: review[key] for key in DEFAULT_ROUTE_TIMING}
    need(all(type(fields[key]) is int and 0 <= fields[key] <= 2 ** 31 - 1
             for key in (*_TIMING_FIELDS, 'reservation_distance_m'))
         and max(fields['release_time_s'], fields['reserve_time_s']) <= 86400
         and fields['announce_distance_m'] == 400,
         'Use reviewed native nonnegative delays and distances with the default 400 m announce setting')
    length, speed = (fields[key] for key in _APPROACH_FIELDS)
    need(all(type(value) in (int, float) and isfinite(value) and value >= 0 for value in (length, speed))
         and length <= 10 ** 7 and speed <= 1000 and (length > 0) == (speed > 0),
         'Review the original finite approach length and speed together')
    need(all(type(fields[key]) is bool for key in _DISTANCE_FIELDS[1:])
         and (not fields['use_reservation_distance'] or fields['reservation_distance_m'] > 0)
         and (not fields['use_release_distance'] or fields['release_distance_m'] > 0),
         'An enabled original reservation or release distance requires a positive reviewed distance')
    need(fields != DEFAULT_ROUTE_TIMING, 'Select at least one original non-default interlocking timing field')
    return fields


def release_keys(project, route):
    return [project.key(node) for node in path_functions.mutable_array(route.contents[12].values[0])]


def plan_timing_split(project, route, fragment, sequence, cut, review, *, reserve_with_previous):
    original = reviewed_route_timing(review)
    need(stored_route_timing(route) == original, 'The reviewed timing differs from the original Route data')
    releases = release_keys(project, route)
    if fragment is not None:
        need(stored_route_timing(fragment) == DEFAULT_ROUTE_TIMING,
             'The receiving fragment must have its original default, inactive timing profile')
        releases += release_keys(project, fragment)
    expected = [(row['document'], row['end_id']) for row in review['release_group_starts']]
    old_anchors = set(releases)
    need(expected == releases and releases and releases[0] == sequence[0]
         and releases == [point for point in sequence if point in old_anchors],
         'Review the exact saved ordered release-group Ends of the original effective Route')

    distances = [0]
    edges = [project.edge_between(first, second) for first, second in zip(sequence, sequence[1:])]
    for key in edges:
        length = project.model(key).contents[9].values[1]
        need(type(length) is int and length > 0, 'Timing review needs the original persisted positive Edge lengths')
        distances.append(distances[-1] + length)
    left, left_exclusions = _edge_locking_resources(project, edges[:cut])
    right, right_exclusions = _edge_locking_resources(project, edges[cut:])
    need(not (left | left_exclusions) & (right | right_exclusions),
         'Timed Route sections may not share a Safety Element or Edge exclusion')
    cut_m = distances[cut]
    terminal_m = distances[-1]
    approach = original['approach_length_m']
    need(approach <= terminal_m - cut_m,
         'The original terminal approach section must fit entirely after the new main Signal')
    reservation = original['reserve_time_s'] or original['use_reservation_distance']
    need(not reservation or reserve_with_previous,
         'Preserving the original timed entry requires the downstream Route to reserve with the previous one')
    first, last = sequence[0], sequence[-1]
    return {
        'original': original,
        'upstream': {**original, 'release_distance_m': 0, 'use_release_distance': False,
                     'approach_length_m': 0.0, 'approach_speed_kmh': 0.0},
        'downstream': {**original, 'reserve_time_s': 0, 'reservation_distance_m': 5000,
                       'use_reservation_distance': False},
        'original_release_group_starts': releases,
        'reservation_origin': first, 'new_release_boundary': sequence[cut], 'terminal_release_boundary': last,
        'cut_m_from_original_route_origin': cut_m, 'terminal_m_from_original_route_origin': terminal_m,
        'terminal_approach_m_from_original_route_origin': [terminal_m - approach, terminal_m] if approach else None,
        'terminal_release_m_from_original_route_origin': terminal_m + (
            original['release_distance_m'] if original['use_release_distance'] else 0),
        'run_switch_and_reservation_time_required_for_delay': original['reserve_time_s'] > 0,
    }


def timing_groups(route, values):
    return {
        5: [*(values[key] for key in _TIMING_FIELDS), *route.contents[5].values[4:]],
        8: [values[key] for key in _APPROACH_FIELDS],
        10: [values['reservation_distance_m'], int(values['use_reservation_distance']),
             int(values['use_release_distance'])],
    }


def _effective_release_keys(project, route):
    rows = release_keys(project, route)
    if route.contents[5].values[4] >= 0:
        owner = project.owners[id(route)]
        records = [row for row in project.continuations if row['source_document'] == owner[0]
                   and row['route'] == ref(route)]
        need(len(records) == 1, 'The timed Route requires one exact archived receiving fragment')
        record, = records
        fragment = project.owned((record['target_document'], record['target_connector']), 'OTRoute', ident(route))
        need(stored_route_timing(fragment) == DEFAULT_ROUTE_TIMING,
             'A saved timing change leaked into the inactive receiving fragment')
        rows += release_keys(project, fragment)
    return rows


def check_timing_split(saved, upstream, downstream, review):
    front = saved.route_view(upstream)
    rear = saved.route_view(downstream)
    need((front[0], front[-1], rear[0], rear[-1]) == (
        review['reservation_origin'], review['new_release_boundary'], review['new_release_boundary'],
        review['terminal_release_boundary'])
         and stored_route_timing(upstream) == review['upstream']
         and stored_route_timing(downstream) == review['downstream'],
         'The original timing fields or their physical End assignments differ after native readback')
    front_anchors, rear_anchors = [_effective_release_keys(saved, route) for route in (upstream, downstream)]
    old = review['original_release_group_starts']
    ordered = list(dict.fromkeys(front_anchors + rear_anchors))
    allowed_additions = {review['new_release_boundary'], review['terminal_release_boundary']}
    need(front_anchors == [point for point in front if point in set(front_anchors)]
         and rear_anchors == [point for point in rear if point in set(rear_anchors)]
         and [point for point in ordered if point in old] == old
         and set(ordered).difference(old) <= allowed_additions,
         'The timed split changes the original native ordered release-group Ends')
    return {'upstream': front_anchors, 'downstream': rear_anchors}
