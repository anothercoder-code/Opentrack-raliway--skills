"""Keep a fixed Route speed zone and terminal Shunting overlap on distinct split sections."""

from itertools import combinations

from .multi_document.core import need
from .saved_terminal_overlap import _edge_locking_resources
from .saved_timing_signal_split import DEFAULT_ROUTE_TIMING, stored_route_timing


def plan_slow_zone_overlap(project, route, sequence, split, slow, overlap, *, reserve_with_previous):
    """Review a fixed metric prefix zone and independent synchronized terminal overlap."""
    need(reserve_with_previous is True and stored_route_timing(route) == DEFAULT_ROUTE_TIMING,
         'Fixed slow zone and terminal overlap require synchronized reservation and default Route timing')
    start, finish = slow['original_effective_zone_anchors']
    cut = sequence.index(split)
    need(0 <= sequence.index(start) < sequence.index(finish) < cut
         and slow['position'] == 'upstream'
         and slow['upstream']['zone_edges'] == slow['original_zone_edges']
         and not slow['downstream']['zone_edges'] and slow['downstream']['aspect_code'] == 0,
         'The entire fixed slow-speed zone must finish strictly before the new Signal')
    shunting = overlap['shunting']
    terminal = sequence[-1]
    need((shunting['document'], shunting['start_id']) == terminal and overlap['reservation_time_s'] == 0,
         'The overlap must start at the original terminal and have zero Shunting reservation delay')

    movement = [project.edge_between(first, second) for first, second in zip(sequence, sequence[1:])]
    shunting_edges = [(terminal[0], number) for number in overlap['edge_ids']]
    sections = {'upstream': movement[:cut], 'downstream': movement[cut:], 'terminal_overlap': shunting_edges}
    resources = {part: _edge_locking_resources(project, edges) for part, edges in sections.items()}
    for first, second in combinations(sections, 2):
        first_elements, first_exclusions = resources[first]
        second_elements, second_exclusions = resources[second]
        need(not set(sections[first]).intersection(sections[second])
             and not (first_elements | first_exclusions) & (second_elements | second_exclusions),
             'The two Route sections and overlap must have independent Edges, Safety Elements and Edge exclusions')

    return {
        'upstream_speed_zone': {'ends': [start, finish], 'edge_keys': slow['original_zone_edges'],
                                'chainage_m_from_route_origin': slow['original_zone_m_from_route_origin'],
                                'aspect_code': slow['aspect_code'], 'speed_kmh': slow['speed_kmh'],
                                'head_only': slow['head_only']},
        'relay_end': split,
        'downstream_aspect_code': 0,
        'terminal_overlap': {'shunting': shunting, 'edge_keys': shunting_edges,
                             'release_time_s': overlap['release_time_s'], 'reservation_time_s': 0},
        'default_route_timing': dict(DEFAULT_ROUTE_TIMING),
        'locking_resources': {part: {'safety_elements': sorted(elements), 'exclusion_elements': sorted(exclusions)}
                              for part, (elements, exclusions) in resources.items()},
        'linked_downstream_reservation_requested': True,
    }


def check_slow_zone_overlap(project, upstream, downstream, split, plan, slow, overlap):
    """Reconcile the independently cold-read speed, interlocking, and overlap fields."""
    sequence = [*project.route_view(upstream), *project.route_view(downstream)[1:]]
    observed = plan_slow_zone_overlap(project, upstream, sequence, split, slow, overlap,
                                      reserve_with_previous=overlap['synchronized_reservation'])
    need(observed == plan and overlap['upstream_reference_cleared']
         and stored_route_timing(downstream) == DEFAULT_ROUTE_TIMING,
         'The combined slow zone and terminal overlap differ after native cold read')
    return {**observed, 'native_joint_readback_verified': True}
