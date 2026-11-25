"""Retain terminal approach and release timing on a reviewed inserted occupied-entry Route."""

from . import catalogs, path_functions, writer
from .catalog_batch_reuse.course_batch import course_record
from .multi_document.core import need
from .saved_occupied_timing_signal_split import _disjoint_terminal_approach
from .saved_timing_signal_split import DEFAULT_ROUTE_TIMING, release_keys, stored_route_timing


def _terminal_approach(project, route, occupied, timing):
    nodes = project.route_view(route)
    edges = [project.edge_between(a, b) for a, b in zip(nodes, nodes[1:])]
    lengths = [project.model(edge).contents[9].values[1] for edge in edges]
    need(lengths and all(type(value) is int and value > 0 for value in lengths),
         'Inserted occupied-entry timing needs exact positive native Edge lengths')
    terminal_m = sum(lengths)
    return _disjoint_terminal_approach(occupied, {
        'original': timing,
        'terminal_m_from_original_route_origin': terminal_m,
        'terminal_approach_m_from_original_route_origin': [terminal_m - timing['approach_length_m'], terminal_m],
        'cut_m_from_original_route_origin': 0, 'terminal_release_boundary': nodes[-1],
    })


def _zero_switch_times(project, nodes):
    scope = {key for end in nodes for key in (end, project.related(end))}
    bound_connectors = [key for key in scope if writer.kind(project.model(key)) == 'OTConnModel'
                        and path_functions.string(project.model(key).contents[25].value)]
    for connector in bound_connectors:
        remote = project.block_end(connector)
        scope.update((remote, project.related(remote)))
    need(all(project.model(key).contents[21].value == 0 for key in scope),
         'Inserted occupied-entry timing requires zero saved switch preparation on the effective Route and inserted Ends')


def plan_inserted_occupied_timing(project, primary, fragment, before_berth, review, operating_banks, inserted_nodes):
    """Require the original published timing and one explicitly reviewed two-Course berth."""
    release = review['release_time_s']
    expected = {**DEFAULT_ROUTE_TIMING, 'release_time_s': release,
                'approach_length_m': review['approach_length_m'], 'approach_speed_kmh': review['approach_speed_kmh']}
    need(type(release) is int and 0 < release <= 86400 and release != DEFAULT_ROUTE_TIMING['release_time_s']
         and stored_route_timing(primary) == expected and stored_route_timing(fragment) == DEFAULT_ROUTE_TIMING
         and primary.contents[11].value == fragment.contents[11].value == 0,
         'Match the positive original release and approach with independent reservation and default preparation/distance')
    nodes = project.route_view(primary)
    need(release_keys(project, primary) == nodes[:1] and not release_keys(project, fragment),
         'Inserted occupied-entry timing requires the original implicit terminal release and a single original start anchor')
    course_root, _ = writer.load_next_compatible(operating_banks['courses'])
    ids = {before_berth['receiver_course'], before_berth['donor_course']}
    scope = [row for item in catalogs.course_items(course_root) if (row := course_record(item))['course_id'] in ids]
    need(len(scope) == 2 and all(row['additional_reservation_time_s'] == row['additional_release_time_s'] == 0
                                for row in scope),
         'Inserted occupied-entry timing requires zero additional Course preparation and release delays')
    _zero_switch_times(project, [*nodes, *inserted_nodes])
    return {'timing': expected, 'source_approach': _terminal_approach(project, primary, before_berth, expected)}


def apply_inserted_occupied_timing(front, successor, timing):
    front.contents[8].values[:] = [0.0, 0.0]
    successor.contents[5].values[2] = timing['release_time_s']
    successor.contents[8].values[:] = [timing['approach_length_m'], timing['approach_speed_kmh']]


def check_inserted_occupied_timing(project, front, front_fragment, successor, terminal_fragment, handoff, plan):
    """Cold-read both effective Routes, both inactive fragments, and the projected berth."""
    timing = plan['timing']
    front_timing = {**DEFAULT_ROUTE_TIMING, 'release_time_s': timing['release_time_s']}
    need(stored_route_timing(front) == front_timing and stored_route_timing(successor) == timing
         and all(stored_route_timing(fragment) == DEFAULT_ROUTE_TIMING for fragment in (front_fragment, terminal_fragment)),
         'The saved release or approach leaked to a wrong Route or receiving fragment')
    front_nodes, successor_nodes = project.route_view(front), project.route_view(successor)
    need(release_keys(project, front) == front_nodes[:1] and release_keys(project, successor) == successor_nodes[:1]
         and all(not release_keys(project, fragment) for fragment in (front_fragment, terminal_fragment)),
         'The new Routes must use exactly their own start anchor and implicit terminal release')
    _zero_switch_times(project, [*front_nodes, *successor_nodes])
    old = plan['source_approach']
    new = _terminal_approach(project, successor, handoff['after'], timing)
    distance_key = 'distance_m_from_original_route_origin'
    need(new == {**old, distance_key: new[distance_key]},
         'Inserted occupied-entry approach must preserve the exact original stop-edge contact clearance and terminal')
    added_length = handoff['inserted_length_m']
    before_stop = handoff['before']['berth']['head_distance_m']
    after_stop = handoff['after']['berth']['head_distance_m']
    length = timing['approach_length_m']
    need(after_stop - before_stop == added_length,
         'Original and replacement approach course coordinates do not differ by exactly the inserted length')
    return {'original_approach': old, 'successor_approach': new,
            'original_approach_course_m': [before_stop - length, before_stop],
            'successor_approach_course_m': [after_stop - length, after_stop],
            'release_time_s': timing['release_time_s'], 'prefix_release_end': front_nodes[-1],
            'terminal_release_end': successor_nodes[-1], 'independent_reservation': True,
            'saved_preparation_s': 0, 'native_timing_readback_verified': True}

