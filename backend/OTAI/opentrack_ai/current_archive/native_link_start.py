"""Static native SimCourse split-style successor origin binding."""

from bisect import bisect_left

from .network_composition_plan import itinerary_routes
from .operating_plan_edit import need


def _route_occurrences(project, itinerary, trace):
    """Index the native Route sequence by occurrences of its directed edges."""
    nodes = trace['_directed_nodes']
    occurrences = []
    first = 0
    for route in itinerary_routes(project, itinerary):
        ends = project.route_view(route)
        last = first + len(ends) - 1
        need(ends == nodes[first:last + 1],
             'Linked Courses require an ordered ordinary Route sequence without a shunting leg')
        occurrences.append((first, last, ends))
        first = last
    need(occurrences and first == len(nodes) - 1,
         'Linked Courses require an ordered ordinary Route sequence without a shunting leg')
    return occurrences


def _native_match(project, origin, occurrences, primary, fallback):
    # splitFromSimCourse:… scans the primary Route backward and the fallback forward.
    for index, direction in ((primary, -1), (fallback, 1)):
        if index < 0:
            continue
        for end in occurrences[index][2][::direction]:
            if end == origin:
                return index, end, 'exact'
            if project.actual_related(end) == origin:
                return index, end, 'actual_related'
    return None


def successor_start(project, previous_route, next_route, previous_trace, next_trace,
                    stop, origin, movement, course_pair):
    """Bind one inactive successor with one explicit ordinary Itinerary preference."""
    before, after = course_pair
    link = f'{before} → {after}'
    reference = stop['end_key']
    start = origin['end_key']
    need(stop['station_sign'] == origin['station_sign'],
         f'{link}: linked Courses require one common native Station sign')
    required = reference if movement == 'continue' else project.actual_related(reference)
    need(start == required,
         f'{link}: paired terminal/starting Ends are required for reversal, or one identical End when continuing')
    previous = _route_occurrences(project, previous_route, previous_trace)
    first_successor = _route_occurrences(project, next_route, next_trace)[0][2][0]
    need(start == first_successor,
         f'{link}: the linked station must be the successor Itinerary first directed End')
    stopping_point = stop['stopping_point']
    need(stopping_point is not None, f'{link}: a linked Course requires an exact native arrival head point')
    distances = previous_trace['_node_distances_m']
    distance = stopping_point['distance_m']
    need(0 < distance <= distances[-1], f'{link}: linked arrival head point is outside its saved Itinerary')
    # At an exact node, the incoming edge representation selects the arriving Route.
    # The equivalent next-Route start selects that same primary Route but can change fallback.
    edge = bisect_left(distances, distance) - 1
    route_index, (route_start, route_end, _) = next(
        (index, item) for index, item in enumerate(previous) if item[0] <= edge < item[1]
    )
    match = _native_match(project, start, previous, route_index, route_index - 1)
    if edge + 1 == route_end and distance == distances[route_end] and route_index + 1 < len(previous):
        boundary_match = _native_match(project, start, previous, route_index, route_index)
        need(boundary_match == match, f'{link}: successor matching is ambiguous at a shared native Route boundary')
    need(match is not None,
         f'{link}: successor Itinerary first End is absent from the arrival head Route and native fallback')
    expected_match = 'exact' if movement == 'continue' else 'actual_related'
    need(match[1:] == (reference, expected_match),
         f'{link}: native arrival scan matches a different directed station End or movement')
    return {
        'from_course': before, 'to_course': after, 'movement': movement,
        'from_visit_index': stop['visit_index'], 'station_sign': stop['station_sign'],
        'arrival_station_end_key': reference, 'arrival_head_distance_m': distance,
        'arrival_marker_signal_id': stopping_point['signal_id'],
        'arrival_approach': {'route_index': route_index, 'end_index': edge - route_start,
                             'offset_m': distance - distances[edge]},
        'matched_predecessor_route_index': match[0], 'matched_predecessor_end_key': match[1],
        'match': match[2], 'birth_end_key': start,
        'birth_sim_position': {'dest_index': 0, 'route_index': 0, 'end_index': 0, 'offset_m': 0},
    }
