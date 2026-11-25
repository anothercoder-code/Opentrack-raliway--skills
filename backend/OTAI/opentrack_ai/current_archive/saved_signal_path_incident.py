"""Preserve a whole-Route speed Incident on the exact replacement native Path."""

from . import catalogs, writer
from .disturbance_tools import absolute
from .incident_operations import SCHEMA
from .incident_source import validate_set_graph
from .infrastructure_incidents.core import item_from_object
from .multi_document.core import ident, need, ref
from .saved_terminal_overlap import _edge_locking_resources


def _native_target(project, kind, binding):
    objects = project.paths_objects if kind == 'OTPath' else project.routes
    owner = binding['document'], binding['start_id']
    matches = [item for item in objects if project.owners[id(item)] == owner
               and ident(item)[1:] == (binding['array_id'], binding['start_id'])]
    need(len(matches) == 1 and ref(matches[0]) == {key: binding[key] for key in ('name', 'array_id', 'start_id')},
         f'Expected one exact original {kind} identity at its ordinary native owner')
    return matches[0]


def _path_from_incident(project, fields):
    owner = (fields['document'], fields['start_end_id'])
    matches = [item for item in project.paths_objects if project.owners[id(item)] == owner
               and ident(item)[1:] == (fields['array_id'], fields['start_end_id'])]
    need(len(matches) == 1, 'An enabled Path-speed Incident has an unresolved native Path target')
    return matches[0]


def _target_key(row):
    aid, start, _ = row.contents[5].values
    return catalogs.text(row.contents[2].value).casefold(), start, aid


def _reference(binding):
    return binding['document'], {key: binding[key] for key in ('name', 'array_id', 'start_id')}


def preserve_route_speed_incident(courses, original, saved, review, *, upstream, downstream, incident_keys):
    """Rebind an existing Incident4 to one exact Incident5 target, without splitting the event."""
    need(type(review) is dict and set(review) == {'name', 'path', 'expected_speed_kmh'},
         'Review one named Route-speed Incident, exact Path and saved speed')
    path = review['path']
    need(type(path) is dict and set(path) == {'document', 'name', 'start_id', 'array_id'},
         'The original single-Route Path needs its exact native identity')
    route = _native_target(original, 'OTRoute', upstream)
    prefix = _native_target(saved, 'OTRoute', upstream)
    suffix = _native_target(saved, 'OTRoute', downstream)
    before = _native_target(original, 'OTPath', path)
    after = _native_target(saved, 'OTPath', path)
    first, second = _reference(upstream), _reference(downstream)
    original_nodes, original_routes = original.path_view(before)
    saved_nodes, saved_routes = saved.path_view(after)
    need(original_routes == [first] and saved_routes == [first, second]
         and original_nodes == saved_nodes == original.route_view(route),
         'The reviewed original Path must cover only the old Route and both exact replacement sections')
    split = saved.route_view(prefix)[-1]
    cut = original_nodes.index(split)
    need(original_nodes[:cut + 1] == saved.route_view(prefix)
         and original_nodes[cut:] == saved.route_view(suffix),
         'The two native Path sections do not partition the original directed Route')
    edges = [original.edge_between(left, right) for left, right in zip(original_nodes, original_nodes[1:])]
    first_elements, first_exclusions = _edge_locking_resources(original, edges[:cut])
    last_elements, last_exclusions = _edge_locking_resources(original, edges[cut:])
    need(not (first_elements | first_exclusions) & (last_elements | last_exclusions),
         'The whole-Route Incident requires independent native Safety Elements and Edge exclusions')
    controlled = {key for end in original_nodes for key in (end, original.related(end), original.actual_related(end))}
    need(all(original.model(key).contents[21].value == 0 for key in controlled),
         'The reviewed Incident Route must have zero saved switch time at its direction Ends')

    root, version = writer.load_next_compatible(courses)
    incidents, _ = validate_set_graph(root)
    need(root.contents[0].value == 17, 'The current native CourseList marker 17 is required')
    for row in incidents:
        catalogs.shape(row, 'OTIncident', 12, SCHEMA)
    selected = [row for row in incidents if catalogs.text(row.contents[0].value) == review['name']]
    need(len(selected) == 1, 'The Route-speed review must select one exact saved Incident')
    incident, = selected
    old = item_from_object(incident)
    speed = review['expected_speed_kmh']
    need(old['type'] == 'route_speed' and type(speed) in (int, float) and 0 < speed <= 10000
         and old['reduced_speed_kmh'] == speed and old['enabled'] and old['probability_percentage'] == 100
         and not any(key in old for key in ('periodic', 'head_only', 'discrete_moving_block'))
         and not any(old.get(key) for key in ('begin_distribution', 'duration_distribution'))
         and absolute(old['begin_time'], old['begin_day']) < absolute(old['end_time'], old['end_day']),
         'Require the exact enabled deterministic positive Route-speed Incident with a nonempty interval')
    need(old['document'] == upstream['document'] and old['start_end_id'] == upstream['start_id']
         and old['array_id'] == upstream['array_id'],
         'The reviewed Incident must target the exact selected primary Route')
    for other in incidents:
        kind = other.contents[5].values[2]
        if kind == 4 and other is not incident:
            need(_target_key(other) not in incident_keys, 'Another saved Route-speed Incident targets a split Route')
        if kind == 5 and other.contents[7].value & 1:
            fields = item_from_object(other)
            old_other = _path_from_incident(original, fields)
            new_other = _path_from_incident(saved, fields)
            need(first not in original.path_view(old_other)[1]
                 and all(target not in saved.path_view(new_other)[1] for target in (first, second)),
                 'An enabled Path-speed Incident also controls a section of the split Route')

    baseline = writer.fingerprint(root)
    target_group = incident.contents[5]
    old_target = target_group.values[:]
    need(path['document'] == old['document'] and path['start_id'] == old['start_end_id'],
         'The original single-Route Path must keep the original Route document and owner')
    target_group.values[:] = [path['array_id'], path['start_id'], 5]
    output = writer.dump_verified(root, version)
    reopened, _ = writer.load_next_compatible(output)
    cold_incidents, _ = validate_set_graph(reopened)
    index = incidents.index(incident)
    cold = cold_incidents[index]
    expected = {**old, 'type': 'path_speed', 'array_id': path['array_id']}
    need(item_from_object(cold) == expected, 'The reopened native Incident differs from the reviewed Path and speed')
    cold.contents[5].values[:] = old_target
    need(writer.fingerprint(reopened) == baseline,
         'The event rewrite changed fields, original position or Incident set references')
    return output, {'name': review['name'], 'before': old, 'after': expected, 'native_path': path,
                    'native_path_routes': [upstream, downstream],
                    'directed_edge_refs': [{'document': label, 'edge_id': number} for label, number in edges],
                    'same_saved_incident_and_set_links': True}
