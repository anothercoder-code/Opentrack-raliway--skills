"""Verify the saved rear berth and native birth Route of a reversed split child."""

from . import writer
from .multi_document.core import ref
from .native_link_start import _native_match, _route_occurrences
from .operating_plan_edit import need
from .saved_edge_exclusion import INCOMING, OUTGOING
from .signal_type_workflow.core import ROLES, TYPES


def reverse_origin_signal(project, key):
    """Recognize the ordinary, signalled first End evidenced by the native station list."""
    end = project.model(key)
    signal = end.contents[11].value
    station = end.contents[12].value
    need(writer.kind(end) == 'OTEndModel' and end.contents[20].value == 1
         and writer.kind(station) == 'OTStationModel' and signal is not None
         and signal.contents[7].value is end
         and signal.contents[8].values[:2] == [TYPES['main'], ROLES['block']]
         and end.contents[9].value is not None and end.contents[10].value is None,
         'A reviewed reverse split origin must be an ordinary station End with its own main block signal')
    return signal


def _body_edge(project, first, last, reviewed_id, length, station):
    edge_key = project.edge_between(first, last)
    edge = project.model(edge_key)
    a, b = [edge.contents[slot].value for slot in (7, 8)]
    resource = a.contents[7].value
    need(edge_key == (first[0], reviewed_id) and edge.contents[9].values[1] == length
         and all(writer.kind(end) == 'OTEndModel' and end.contents[12].value is station
                 and end.contents[10].value is None for end in (a, b))
         and resource is b.contents[7].value and writer.kind(resource) == 'OTElement'
         and set(writer.elements(resource.contents[7].value)) == {a, b},
         'The reviewed reverse split body Edge or its native Safety Element differs from the saved berth')
    return edge_key, project.key(resource)


def verify_reverse_split(project, event, parent, child, parent_trace, child_trace,
                         parent_stock, child_stock, index):
    from .network_composition_plan import itinerary_routes
    from .network_operating_plan import resolve_visit_stop

    review = event.reverse_split
    head, origin = review.parent_head_end, review.child_origin_end
    signal = reverse_origin_signal(project, origin)
    parent_visit, child_start = parent_trace['visits'][index], child_trace['visits'][0]
    station = project.model(head).contents[12].value
    need(parent_visit['end_key'] == head and child_start['end_key'] == origin and head[0] == origin[0]
         and parent_visit['station_sign'] == child_start['station_sign'] == event.station_sign
         and project.model(origin).contents[12].value is station
         and signal.contents[0].value == review.child_origin_signal_id,
         'The reviewed reverse split directions must bind the exact parent and child station Ends and signals')
    parent_vehicles, child_vehicles = parent_stock['formation'], child_stock['formation']
    need(len(parent_vehicles) == 2 and len(child_vehicles) == 1 and
         all(row['kind'] == 'engine' for row in [*parent_vehicles, *child_vehicles]) and
         parent_vehicles[-1]['name'] == child_vehicles[0]['name'],
         'A reviewed reverse split requires two powered units and the single exact rear unit as the child')
    arrival, detached = parent_stock['length_m'], child_stock['length_m']
    retained = arrival - detached
    need(0 < detached < arrival and parent_vehicles[0]['length_m'] == retained
         and parent_vehicles[1]['length_m'] == detached,
         'The native parent, detached and retained formation lengths must agree')
    point = resolve_visit_stop(parent_visit, arrival)
    head_signal = project.model(head).contents[11].value
    need(point is not None and not parent_visit.get('halt_stop_issue')
         and point['head_end_key'] == head and point['end_key'] == head
         and point['available_length_m'] >= arrival and head_signal is not None
         and head_signal.contents[8].values[:2] == [TYPES['main'], ROLES['exit']]
         and point['signal_id'] == head_signal.contents[0].value == review.parent_head_signal_id,
         'The complete arriving formation must fit at the exact parent main exit signal')
    nodes, distances = parent_trace['_directed_nodes'], parent_trace['_node_distances_m']
    need(nodes.count(head) == 1, 'The parent head must occur once on the reviewed Itinerary')
    terminal = nodes.index(head)
    need(3 <= terminal < len(nodes) - 1 and distances[terminal] == point['distance_m'],
         'The parent must stop at an interior point and remain able to continue in its saved direction')
    tail, coupling = nodes[terminal - 2:terminal]
    tail_m, coupling_m = distances[terminal - 2:terminal]
    head_m = distances[terminal]
    need(tail[0] == coupling[0] == head[0] and project.actual_related(tail) == origin
         and tail_m == head_m - arrival and coupling_m == head_m - retained,
         'The reverse child first End must be the paired End at the physical parent tail and the coupler must be an exact End')
    rear_edge, rear_element = _body_edge(project, tail, coupling, review.detached_edge_id, detached, station)
    front_edge, front_element = _body_edge(project, coupling, head, review.retained_edge_id, retained, station)
    need(rear_element != front_element and project.key(project.model(origin).contents[7].value) == rear_element
         and project.key(project.model(head).contents[7].value) == front_element
         and parent_visit['stopping_area_edge_keys'][-2:] == [rear_edge, front_edge],
         'Rear and retained bodies require separate Safety Elements on the continuous parent platform')
    child_routes = list(itinerary_routes(project, child))
    need(child_routes and project.owners[id(child_routes[0])] == origin
         and len(child_trace['_directed_nodes']) >= 2,
         'The reverse child must use its exact first ordinary native Route')
    child_next = child_trace['_directed_nodes'][1]
    need(project.edge_between(origin, child_next) == project.edge_between(nodes[terminal - 3], tail),
         'The reverse child must depart away from both bodies over the preceding approach Edge')
    departure = project.route_view(child_routes[0])
    departure_edges = [project.model(project.edge_between(a, b)) for a, b in zip(departure, departure[1:])]
    body_resources = {project.model(rear_element), project.model(front_element)}
    need(all(edge.contents[7].value.contents[7].value not in body_resources for edge in departure_edges),
         'The child first Route must not reuse either native body Safety Element')
    protected_edges = set(departure_edges) | {project.model(rear_edge), project.model(front_edge)}
    need(all(edge.contents[slot].value is None or (edge not in protected_edges
             and edge.contents[slot].value not in protected_edges)
             for models in project.models.values() for edge in models if writer.kind(edge) == 'OTEdgeModel'
             for slot in (OUTGOING, INCOMING)),
         'The reviewed body and child departure Edges require an exclusion-free native footprint')
    routes = _route_occurrences(project, parent, parent_trace)
    arrivals = [position for position, (_, _, ends) in enumerate(routes) if ends[-1] == head]
    need(len(arrivals) == 1 and arrivals[0] + 1 < len(routes),
         'The parent must have one exact native arrival Route and a continuing Route')
    i, = arrivals
    cases = ((i, i - 1), (i, i), (i + 1, i))
    matches = [_native_match(project, origin, routes, primary, fallback) for primary, fallback in cases]
    need(all(match == (i, tail, 'actual_related') for match in matches),
         'The child tail End must match the native arrival scan at both representations of the parent stop')
    return {
        'station_end': {'document': head[0], 'end_id': head[1]}, 'signal_id': point['signal_id'],
        'head_distance_m': head_m, 'available_length_m': point['available_length_m'],
        'reverse_head_distance_m': tail_m, 'reverse_tail_distance_m': coupling_m,
        'detached_body_edge_key': rear_edge, 'retained_body_edge_key': front_edge,
        'detached_safety_element_key': rear_element, 'retained_safety_element_key': front_element,
        'child_origin_signal_id': review.child_origin_signal_id,
        'child_first_route': {'document': origin[0], **ref(child_routes[0])},
        'native_birth': {'from_course': event.main_course, 'to_course': event.other_course, 'movement': 'reverse',
                         'from_visit_index': index, 'station_sign': event.station_sign,
                         'arrival_station_end_key': head, 'arrival_head_distance_m': head_m,
                         'arrival_marker_signal_id': point['signal_id'], 'matched_predecessor_route_index': i,
                         'matched_predecessor_end_key': tail, 'match': 'actual_related', 'birth_end_key': origin,
                         'birth_sim_position': {'dest_index': 0, 'route_index': 0, 'end_index': 0, 'offset_m': 0}},
    }
