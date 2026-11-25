"""Review spatial changes to current native kilometre and Route-span Incidents."""

from . import catalogs, path_functions, writer
from .incident_operations import SCHEMA
from .infrastructure_incidents import spans
from .multi_document.core import ident, ref
from .network_composition_plan import itinerary_routes
from .operating_plan_edit import need


def _incident_rows(root):
    catalogs.course_items(root)
    need(root.contents[0].value == 17, 'Current CourseList marker 17 required for location Incidents')
    rows = catalogs.array(root.contents[1].value)
    need({id(obj) for obj in writer.objects(root) if writer.kind(obj) == 'OTIncident'} == {id(obj) for obj in rows},
         'A saved Incident is outside the native Incident list')
    names = set()
    for index, incident in enumerate(rows):
        catalogs.shape(incident, 'OTIncident', 12, SCHEMA)
        name = catalogs.text(incident.contents[0].value)
        need(name and name not in names, 'Expected unique saved Incident names')
        names.add(name)
        kind = incident.contents[5].values[2]
        if kind in spans.SPAN_TYPES:
            yield name, kind, index, incident


def has_span_incidents(courses: bytes) -> bool:
    """Detect current native location selectors, including disabled Incidents."""
    root, _ = writer.load_next_compatible(courses)
    catalogs.course_items(root)
    for incident in catalogs.array(root.contents[1].value):
        catalogs.shape(incident, 'OTIncident', 12, SCHEMA)
        if incident.contents[5].values[2] in spans.SPAN_TYPES:
            return True
    return False


def _edge_ref(key):
    return {'document': key[0], 'edge_id': key[1]}


def _stored_ends(project, edge):
    model = project.model(edge)
    return [list(project.key(model.contents[slot].value)) for slot in (7, 8)]


def _track_attachment(project, selector):
    selected = spans.track_edges(project, selector)
    for row in selected['edges']:
        row['stored_end_keys'] = _stored_ends(project, (row['document'], row['edge_id']))
    return selected


def _course_routes(root, project, course_id):
    matches = [course for course in catalogs.course_items(root) if catalogs.text(course.contents[0].value) == course_id]
    need(len(matches) == 1 and matches[0].contents[5].value == 1,
         f'Route-span Incident requires exactly one enabled native Course: {course_id}')
    names = [catalogs.text(item) for item in catalogs.array(matches[0].contents[2].value)]
    available = {path_functions.string(dest.contents[1].value): dest for dest in project.dests}
    need(names and all(name in available for name in names),
         f'Route-span Incident Course lacks its exact saved Itinerary: {course_id}')
    return [(name, available[name], list(itinerary_routes(project, available[name]))) for name in names]


def _route_history(root, project, course_id, begin, end):
    if begin is end:
        if course_id:
            need(any(begin in routes for _, _, routes in _course_routes(root, project, course_id)),
                 'Named native Course does not traverse this Route-span Incident Route')
        return None, [begin]
    need(bool(course_id), 'Distinct incident Routes require one named Course and an exact saved Route sequence')
    choices = _course_routes(root, project, course_id)
    need(len(choices) == 1, 'Distinct incident Routes require the named Course to have one saved Itinerary')
    name, dest, routes = choices[0]
    first = [index for index, route in enumerate(routes) if route is begin]
    last = [index for index, route in enumerate(routes) if route is end]
    need(len(first) == len(last) == 1 and first[0] < last[0],
         'Incident Routes must occur once in forward order on the Course Itinerary')
    active = routes[first[0]:last[0] + 1]
    connected = list(project.route_view(active[0]))
    for route in active[1:]:
        nodes = project.route_view(route)
        need(connected[-1] == nodes[0], 'Incident Routes have a nonordinary or disconnected intervening movement')
        connected.extend(nodes[1:])
    dest_nodes, _ = project.dest_view(dest)
    candidates = [index for index, key in enumerate(dest_nodes) if key == connected[0]]
    need(sum(dest_nodes[index:index + len(connected)] == connected for index in candidates) == 1,
         'Incident Routes must form one exact contiguous movement on the Course Itinerary')
    return name, active


def _route_segments(project, route):
    cursor = 0
    nodes = project.route_view(route)
    segments = []
    for first, last in zip(nodes, nodes[1:]):
        edge = project.edge_between(first, last)
        limit = cursor + project.model(edge).contents[9].values[1]
        need(limit > cursor, 'A Route-span Incident requires positive native Edge lengths')
        segments.append((edge, first, last, cursor, limit))
        cursor = limit
    need(bool(segments), 'A Route-span Incident requires a nonempty native Route')
    return segments


def _route_point(project, segments, position):
    edge, first, last, start, _ = next((row for row in segments if position < row[4]), segments[-1])
    return {**_edge_ref(edge), 'from_end': list(first), 'to_end': list(last),
            'stored_end_keys': _stored_ends(project, edge), 'edge_offset_m': position - start}


def _route_attachment(root, project, selector, course_id):
    bounds = spans.route_bounds(project, selector)
    anchors = [next(route for route in project.routes
                    if project.owners[id(route)] == (position['document'], position['start_end_id'])
                    and ident(route)[0] == position['route'])
               for position in bounds.values()]
    itinerary, routes = _route_history(root, project, course_id, *anchors)
    references, visited, points = [], [], {}
    for index, route in enumerate(routes):
        segments = _route_segments(project, route)
        owner = project.owners[id(route)]
        references.append({'document': owner[0], **ref(route)})
        lower = bounds['begin']['offset_m'] if index == 0 else 0
        upper = bounds['end']['offset_m'] if index == len(routes) - 1 else segments[-1][4]
        if index == 0:
            points['begin'] = _route_point(project, segments, lower)
        if index == len(routes) - 1:
            points['end'] = _route_point(project, segments, upper)
        for edge, first, last, start, limit in segments:
            low, high = max(start, lower), min(limit, upper)
            if low < high:
                visited.append({**_edge_ref(edge), 'from_end': list(first), 'to_end': list(last),
                                'stored_end_keys': _stored_ends(project, edge),
                                'edge_interval_m': [low - start, high - start]})
    if not visited:
        need(points['begin'] == points['end'], 'An empty Route interval across two Routes is ambiguous')
        point = points['begin']
        visited = [{**point, 'edge_interval_m': [point['edge_offset_m'], point['edge_offset_m']]}]
    return {'course_id': course_id, 'itinerary': itinerary, 'routes': references, **points, 'edges': visited}


def _binding(root, project, row, selector=None):
    name, kind, index, incident = row
    try:
        saved = spans.saved_fields(incident.contents, kind) if selector is None else selector
        if kind in spans.TRACK_TYPES:
            attachment = _track_attachment(project, saved)
        else:
            value = path_functions.string(incident.contents[1].value)
            attachment = _route_attachment(root, project, saved, value if value not in (None, '', '0') else None)
    except ValueError as error:
        raise ValueError(f'Location Incident {name!r}: {error}') from error
    return {'name': name, 'type': kind, 'incident_index': index, 'selector': saved,
            'edge_refs': [_edge_ref((edge['document'], edge['edge_id'])) for edge in attachment['edges']],
            'attachment': attachment}


def span_incident_bindings(courses: bytes, project) -> list[dict]:
    """Resolve all supported saved location Incident selectors against the full selected graph."""
    root, _ = writer.load_next_compatible(courses)
    return [_binding(root, project, row) for row in _incident_rows(root)]


def _check_refs(refs, actual, side):
    need(type(refs) is list and all(type(item) is dict and set(item) == {'document', 'edge_id'}
         and type(item['document']) is str and type(item['edge_id']) is int for item in refs)
         and refs == actual, f'{side} Incident Edge references differ from the complete resolved native order')


def rebind_span_incidents(courses: bytes, original_project, updated_project, reviews: list[dict]) -> tuple[bytes, list[dict]]:
    """Return native .courses bytes with the explicitly reviewed location fields rebound."""
    need(type(courses) is bytes and type(reviews) is list, 'Expected immutable native .courses and explicit Incident reviews')
    need(set(original_project.roots) == set(updated_project.roots),
         'Location Incident rebinding requires the same complete selected worksheet scope')
    root, version = writer.load_next_compatible(courses)
    rows = list(_incident_rows(root))
    names = {row[0] for row in rows}
    expected_fields = {'name', 'expected_selector', 'replacement_selector', 'expected_edge_refs', 'replacement_edge_refs'}
    by_name = {}
    for review in reviews:
        need(type(review) is dict and set(review) == expected_fields and type(review['name']) is str,
             'Expected name, original and replacement selectors, and both ordered Edge references')
        name = review['name']
        need(name in names and name not in by_name, 'Each review must select one distinct saved location Incident')
        by_name[name] = review
    receipts, planned, edits = [], [], []
    replacements = {}
    for row in rows:
        name, kind, _, incident = row
        before = _binding(root, original_project, row)
        review = by_name.get(name)
        if review is None:
            after = _binding(root, updated_project, row)
            need(after == before, f'Location Incident {name!r} changed its native attachment and needs explicit review')
        else:
            need(review['expected_selector'] == before['selector'],
                 f'Location Incident {name!r} expected selector differs from the native source')
            _check_refs(review['expected_edge_refs'], before['edge_refs'], 'Original')
            revised = review['replacement_selector']
            need(type(revised) is dict and set(revised) == set(before['selector'])
                 and all(type(value) is str for value in revised.values()),
                 f'Location Incident {name!r} requires all native selector fields as strings')
            after = _binding(root, updated_project, row, revised)
            _check_refs(review['replacement_edge_refs'], after['edge_refs'], 'Replacement')
            need(before != after, f'Location Incident {name!r} selector and attachment are unchanged')
            receipts.append({'name': name, 'type': kind, 'incident_index': row[2], 'before': before, 'after': after})
            fields = spans.TRACK_FIELDS if kind in spans.TRACK_TYPES else spans.ROUTE_FIELDS
            for slot, field in enumerate(fields, 8):
                if field is None or revised[field] == before['selector'][field]:
                    continue
                cell = incident.contents[slot]
                key = id(cell.value), revised[field]
                if key not in replacements:
                    replacements[key] = path_functions.fresh_string(cell.value, revised[field])
                edits.append((cell, cell.value, replacements[key]))
        planned.append(after)
    if not edits:
        return courses, receipts
    baseline = writer.fingerprint(root)
    for cell, _, replacement in edits:
        cell.value = replacement
    output = writer.dump_verified(root, version)
    need(span_incident_bindings(output, updated_project) == planned, 'Native location Incident cold read differs from the reviewed selectors')
    for cell, old, _ in edits:
        cell.value = old
    need(writer.fingerprint(root) == baseline, 'Native Incident graph changed outside reviewed location fields')
    return output, receipts
