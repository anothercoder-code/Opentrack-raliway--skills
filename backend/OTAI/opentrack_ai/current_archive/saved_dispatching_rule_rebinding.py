"""Review external native OTD Route bindings across two saved project graphs."""

from collections import Counter
import math
import re
from xml.etree import ElementTree as xml
from xml.parsers import expat
from xml.sax.saxutils import escape

from . import path_functions, writer
from .dispatching_rules_otd import PROLOGUE, XML_LIMIT, route_ids
from .multi_document.core import ident, need


ROUTE_FIELDS = ('document', 'start_end_id', 'route_name', 'array_id')
REFERENCE_ATTRIBUTES = {'route': 'id', 'routeExclusionCondition': 'routeID'}
CONDITION_FIELDS = {'routeID', 'routeReservationState', 'minimalLength', 'stopCode', 'extendedDwellTime'}
ATTRIBUTE = re.compile(rb'''[\t\r\n ]+([A-Za-z][A-Za-z0-9]*)[\t\r\n ]*=[\t\r\n ]*(?:"([^"]*)"|'([^']*)')''')
DECIMAL = re.compile(r'[0-9]+(?:\.[0-9]+)?(?:[Ee][+-]?[0-9]+)?')


def _printable(value):
    return bool(value) and value.isascii() and value.isprintable()


def _shape(node, tag, attributes=()):
    need(node.tag == tag and set(node.attrib) == set(attributes)
         and not (node.text or '').strip() and not (node.tail or '').strip(),
         f'Unsupported OTD {tag} element or attributes')


def _integer(value, maximum):
    return value.isascii() and value.isdecimal() and len(value) <= 6 and int(value) <= maximum


def _condition(node, capacity):
    fields = node.attrib
    _shape(node, 'routeExclusionCondition', fields)
    need(not len(node) and 'routeID' in fields and fields.keys() <= CONDITION_FIELDS,
         'Unsupported OTD exclusion condition')
    if capacity:
        need(set(fields) == {'routeID'}, 'A native OTD capacity condition must be a Route reference')
        return
    need(sum(key in fields for key in ('routeReservationState', 'minimalLength', 'stopCode')) <= 1,
         'An OTD condition must use one supported predicate mode')
    if 'routeReservationState' in fields:
        need(fields['routeReservationState'] in ('reserved', 'free'), 'Unsupported OTD reservation state')
    if 'minimalLength' in fields:
        need(_integer(fields['minimalLength'], 100000), 'Unsupported OTD minimum train length')
    stop = fields.get('stopCode')
    need(stop in (None, 'unplannedStop', 'extendedDwell')
         and (stop == 'extendedDwell') == ('extendedDwellTime' in fields), 'Unsupported OTD stop condition')
    if stop == 'extendedDwell':
        dwell = fields['extendedDwellTime']
        need(len(dwell) <= 40 and DECIMAL.fullmatch(dwell), 'Invalid OTD extended dwell in seconds')
        seconds = float(dwell)
        need(math.isfinite(seconds) and 0 < seconds <= 604800, 'Invalid OTD extended dwell in seconds')


def _references(root):
    _shape(root, 'otd')
    need([node.tag for node in root] == ['routeRuleSets', 'routes'],
         'OTD requires ruleset definitions before Route assignments')
    definitions, routes = root
    _shape(definitions, 'routeRuleSets')
    _shape(routes, 'routes')
    names, assigned_sets, assigned_routes = set(), set(), set()
    references = []
    need(1 <= len(definitions) <= 128, 'OTD requires a supported number of rulesets')
    for definition in definitions:
        _shape(definition, 'routeRuleSet', ('id',))
        name = definition.attrib['id']
        need(_printable(name) and name not in names and 1 <= len(definition) <= 128,
             f'Duplicate or unsupported OTD ruleset: {name}')
        names.add(name)
        for rule in definition:
            capacity = 'maximalNumberOfTrains' in rule.attrib
            _shape(rule, 'routeExclusionRule', ('maximalNumberOfTrains',) if capacity else ())
            need(not capacity or _integer(rule.attrib['maximalNumberOfTrains'], 10000),
                 'Unsupported OTD counted train limit')
            need(1 <= len(rule) <= 256, 'OTD requires a supported number of exclusion conditions')
            seen = set()
            for condition in rule:
                _condition(condition, capacity)
                row = frozenset(condition.attrib.items())
                need(row not in seen, 'Duplicate condition in one OTD exclusion rule')
                seen.add(row)
                references.append((condition, 'routeID'))
    need(len(references) <= 16000, 'OTD exceeds the supported condition budget')
    for route in routes:
        _shape(route, 'route', ('id', 'routeRuleSetID'))
        route_id, ruleset = route.attrib['id'], route.attrib['routeRuleSetID']
        need(not len(route) and ruleset in names, f'Unresolved OTD Route ruleset assignment: {ruleset}')
        need(route_id not in assigned_routes, f'The Route can belong to only one OTD ruleset: {route_id}')
        assigned_routes.add(route_id)
        assigned_sets.add(ruleset)
        references.append((route, 'id'))
    need(assigned_sets == names, 'Each supported OTD ruleset must have a Route assignment')
    need(all(_printable(node.attrib[attr]) for node, attr in references), 'OTD requires printable ASCII Route IDs')
    return references


def _read(blob):
    need(type(blob) is bytes and 0 < len(blob) <= XML_LIMIT, 'Explicit bounded OTD XML bytes required')
    windows_prologue = PROLOGUE.replace(b'\n', b'\r\n')
    prefix = windows_prologue if blob.startswith(windows_prologue) else PROLOGUE
    need(blob.startswith(prefix), 'Expected native ISO-8859-1 OTD declaration and otd.dtd prologue')
    body = blob[len(prefix):]
    need(b'<!DOCTYPE' not in body and b'<!ENTITY' not in body,
         'An OTD XML body may not load a document type or entities')
    try:
        root = xml.fromstring(body.decode('iso-8859-1'))
    except xml.ParseError as exc:
        raise ValueError('Malformed OTD XML body') from exc
    return prefix, body, root, _references(root)


def _identity(document, route):
    name, array_id, start = ident(route)
    return document, start, name, array_id


def _identity_dict(identity):
    return dict(zip(ROUTE_FIELDS, identity, strict=True))


def _review_identity(value):
    need(type(value) is dict and set(value) == set(ROUTE_FIELDS), 'Expected an exact four-field main Route identity')
    need(all(type(value[key]) is str and _printable(value[key]) for key in ('document', 'route_name'))
         and all(type(value[key]) is int and 0 <= value[key] <= 2147483647
                 for key in ('start_end_id', 'array_id')), 'Invalid native main Route identity')
    return tuple(value[key] for key in ROUTE_FIELDS)


def _main_routes(project, mode):
    external = route_ids(project, mode)
    result = {}
    for route in project.routes:
        owner = project.owners[id(route)]
        if writer.kind(project.model(owner)) == 'OTEndModel':
            identity = _identity(owner[0], route)
            result[external[identity[:3]]] = (identity, route)
    return result


def _edge_exclusion(project, edge, slot, reverse_slot):
    other = edge.contents[slot].value
    if other is None:
        return None
    key = project.key(other)
    need(writer.kind(other) == 'OTEdgeModel' and key[0] == project.key(edge)[0] and other is not edge
         and other.contents[reverse_slot].value is edge, 'Nonlocal or nonreciprocal OTD track exclusion')
    end = other.contents[7].value
    return {'edge': key, 'safety_element': project.key(end.contents[7].value)}


def _turnout(project, key, edge):
    end = project.model(key)
    if end.contents[10].value is None:
        return None
    legs = tuple(project.key(end.contents[slot].value) for slot in (9, 10))
    default = end.contents[22].value
    seconds = end.contents[21].value
    need(edge in legs and default in (0, 1) and math.isfinite(seconds) and seconds >= 0,
         f'Invalid saved turnout on OTD Route: {key}')
    return {'end': key, 'ordered_legs': legs, 'selected_edge': edge, 'default_edge': legs[default],
            'switch_time_s': seconds}


def _movement(project, keys):
    legs = []
    observed_ends = set(keys)
    for start, finish in zip(keys, keys[1:]):
        local = project.related(start)
        actual = project.actual_related(start)
        paired = ()
        if writer.kind(project.model(local)) == 'OTConnModel':
            paired = (local, project.block_end(local))
        edge = project.edge_between(start, finish)
        stored = project.model(edge)
        ends = tuple(project.key(stored.contents[slot].value) for slot in (7, 8))
        observed_ends.update((*paired, actual))
        legs.append({'edge': edge, 'edge_ends': ends, 'related': actual, 'connectors': paired,
                     'length_m': stored.contents[9].values[1],
                     'exclusion_target': _edge_exclusion(project, stored, 13, 14),
                     'exclusion_source': _edge_exclusion(project, stored, 14, 13),
                     'departure_turnout': _turnout(project, actual, edge),
                     'arrival_turnout': _turnout(project, finish, edge)})
    resources = {}
    signals = []
    for end in sorted(observed_ends):
        model = project.model(end)
        safety = model.contents[7].value
        key = project.key(safety)
        members = path_functions.mutable_array(safety.contents[7].value)
        resources[key] = tuple(sorted(project.key(item) for item in members))
        signal = model.contents[11].value
        if signal is not None:
            signals.append((end, project.key(signal)))
    return {'ends': tuple(keys), 'legs': legs, 'signals': signals,
            'safety_elements': [(key, resources[key]) for key in sorted(resources)]}


def _route_part(project, part, final_end):
    # Complete Project._rsp has already validated the current OTSecurityArray 6 shape.
    owner = project.owners[id(part)]
    release, *zone = part.contents[12].values
    name = path_functions.string(part.contents[7].value)
    overlap_start = part.contents[9].value
    overlap = None
    if name:
        start = final_end if overlap_start == -1 else (final_end[0], overlap_start)
        keys = project.shunting_movements[(start, name)]
        overlap = {'name': name, 'start': start, 'movement': _movement(project, keys)}
    return {'owner': owner, 'route_flags': tuple(part.contents[5].values),
            'occupied_entry': tuple(part.contents[6].values), 'approach': tuple(part.contents[8].values),
            'reservation_and_release_distance': tuple(part.contents[10].values),
            'route_protection_flags': part.contents[11].value,
            'release_ends': tuple(project.key(item) for item in path_functions.mutable_array(release)),
            'slow_zone_ends': tuple(None if item is None else project.key(item) for item in zone), 'overlap': overlap}


def _footprint(project, route):
    keys = project.route_view(route)
    parts = [_route_part(project, route, keys[-1])]
    route_owner = project.owners[id(route)]
    continuation = next((entry for entry in project.continuations
                         if (entry['source_document'], entry['route']['start_id']) == route_owner
                         and entry['route']['array_id'] == ident(route)[1]), None)
    if continuation is not None:
        fragment_owner = continuation['target_document'], continuation['target_connector']
        fragment = project.owned(fragment_owner, 'OTRoute', ident(route))
        parts.append(_route_part(project, fragment, keys[-1]))
    return {'movement': _movement(project, keys), 'parts': parts}


def _usage(references):
    return Counter((node.attrib[attr], attr) for node, attr in references)


def dispatching_rule_route_bindings(blob, project, mode):
    """Read the active main identities, usage counts and saved resource attachments."""
    need(mode in ('compound', 'route_name'), 'Explicit native OTD Route ID mode required')
    _, _, _, references = _read(blob)
    authoritative = _main_routes(project, mode)
    usage = _usage(references)
    rows = []
    for route_id in dict.fromkeys(identifier for identifier, _ in usage):
        need(route_id in authoritative, f'OTD references an unresolved saved main Route: {route_id}')
        route, obj = authoritative[route_id]
        rows.append({'route_id': route_id, 'route': _identity_dict(route), 'assignments': usage[route_id, 'id'],
                     'conditions': usage[route_id, 'routeID'], 'footprint': _footprint(project, obj)})
    return rows


def _rewrite(body, replacements):
    if not replacements:
        return body
    parser = expat.ParserCreate('ISO-8859-1')
    changes = []

    def start(tag, attributes):
        attribute = REFERENCE_ATTRIBUTES.get(tag)
        old = attributes.get(attribute)
        if old not in replacements:
            return
        cursor = parser.CurrentByteIndex + len(tag) + 1
        while match := ATTRIBUTE.match(body, cursor):
            if match[1].decode('ascii') == attribute:
                index = 2 if match[2] is not None else 3
                begin, end = match.span(index)
                encoded = escape(replacements[old], {'"': '&quot;', "'": '&apos;'})
                changes.append((begin, end, encoded.encode('ascii')))
                return
            cursor = match.end()
        raise ValueError('Could not locate exact OTD Route attribute bytes')

    parser.StartElementHandler = start
    parser.Parse(body, True)
    output = []
    cursor = 0
    for begin, end, value in changes:
        output.extend((body[cursor:begin], value))
        cursor = end
    output.append(body[cursor:])
    return b''.join(output)


def rebind_dispatching_rule_routes(blob: bytes, original_project, updated_project, mode: str,
                                    reviews: list[dict]) -> tuple[bytes, list[dict]]:
    """Apply explicit main Route reviews and cold-check the complete native XML file."""
    need(mode in ('compound', 'route_name'), 'Explicit native OTD Route ID mode required')
    need(type(reviews) is list, 'Explicit OTD Route review list required')
    prefix, body, root, references = _read(blob)
    usage = _usage(references)
    used = dict.fromkeys(identifier for identifier, _ in usage)
    original = _main_routes(original_project, mode)
    updated = _main_routes(updated_project, mode)
    old_ids = {identity: route_id for route_id, (identity, _) in original.items() if route_id in used}
    new_ids = {identity: route_id for route_id, (identity, _) in updated.items()}
    selected, targets = {}, set()
    for review in reviews:
        need(type(review) is dict and set(review) == {'old', 'new'}, 'Expected explicit old and new OTD Route identities')
        old, new = _review_identity(review['old']), _review_identity(review['new'])
        need(old in old_ids, f'Review source does not match a referenced original main Route: {old}')
        need(new in new_ids, f'Review target does not match a revised main Route: {new}')
        need(old not in selected and new not in targets, 'Duplicate source or collapsed target in OTD Route reviews')
        selected[old] = new
        targets.add(new)
    replacements, results, retained = {}, [], set()
    for route_id in used:
        need(route_id in original, f'OTD references an unresolved original main Route: {route_id}')
        old, old_object = original[route_id]
        new = selected.get(old, old)
        need(new in new_ids, f'OTD Route requires an explicit identity review: {route_id}')
        new_id = new_ids[new]
        need(_printable(new_id), f'Revised OTD Route ID requires printable ASCII: {new_id}')
        need(new_id not in retained, f'Distinct original OTD Route references collapse to one revised Route: {new_id}')
        retained.add(new_id)
        old_footprint = _footprint(original_project, old_object)
        new_footprint = _footprint(updated_project, updated[new_id][1])
        changed = old_footprint != new_footprint
        need(not changed or old in selected, f'OTD Route retains its ID but requires an explicit resource review: {route_id}')
        if old in selected:
            need(old != new or changed, f'OTD Route review does not change its identity or resources: {route_id}')
            results.append({'old': _identity_dict(old), 'new': _identity_dict(new),
                            'before_route_id': route_id, 'after_route_id': new_id,
                            'assignments': usage[route_id, 'id'], 'conditions': usage[route_id, 'routeID'],
                            'footprint_changed': changed, 'before_footprint': old_footprint, 'after_footprint': new_footprint})
        if new_id != route_id:
            replacements[route_id] = new_id
    for node, attr in references:
        node.attrib[attr] = replacements.get(node.attrib[attr], node.attrib[attr])
    _references(root)
    output = prefix + _rewrite(body, replacements)
    _, _, fresh, fresh_refs = _read(output)
    need(xml.tostring(fresh) == xml.tostring(root)
         and all(node.attrib[attr] in updated for node, attr in fresh_refs), 'OTD Route rebinding failed exact XML readback')
    return output, results
