"""Audit the already independent fixed-speed predecessor of a reviewed occupied Route split."""

from . import catalogs, writer
from .catalog_batch_reuse.course_batch import course_record
from .multi_document.core import ident, need, ref
from .network_composition_plan import itinerary_routes
from .network_operating_plan import route_trace
from .saved_document_insertion import _route_profile
from .saved_occupied_signal_split import ORDINARY_ENTRY
from .saved_slow_zone_signal_split import review_slow_zone_split
from .saved_terminal_overlap import _edge_locking_resources, overlap_reference
from .saved_timing_signal_split import DEFAULT_ROUTE_TIMING, release_keys, stored_route_timing


def _locks(project, nodes):
    edges = [project.edge_between(a, b) for a, b in zip(nodes, nodes[1:])]
    elements, exclusions = _edge_locking_resources(project, edges)
    return elements, exclusions


def _reference(row):
    return row['name'], row['array_id'], row['start_id']


def _ordinary_fixed_predecessor(project, review):
    reference = review['route']
    owner = reference['document'], reference['start_id']
    preceding = project.owned(owner, 'OTRoute', _reference(reference))
    movement = project.route_view(preceding)
    fragment = None
    remote_owner = None
    if movement[-1][0] != owner[0]:
        rows = [row for row in project.continuations if row['source_document'] == owner[0]
                and row['route'] == ref(preceding)]
        need(len(rows) == 1, 'Review one exact receiving fragment of the existing slow predecessor')
        row, = rows
        remote_owner = row['target_document'], row['target_connector']
        fragment = project.owned(remote_owner, 'OTRoute', _reference(reference))
    parts = [preceding] if fragment is None else [preceding, fragment]
    need(all(tuple(part.contents[6].values) == ORDINARY_ENTRY and part.contents[11].value == 0
             and stored_route_timing(part) == DEFAULT_ROUTE_TIMING and overlap_reference(part) == ('', -1)
             for part in parts),
         'The fixed slow predecessor must be independently reserved and retain default timing without occupied entry or overlap')
    slow = review_slow_zone_split(project, preceding, fragment, movement, movement[-1], review['zone'])
    need(slow['position'] == 'upstream' and not slow['head_only'],
         'The existing fixed slow predecessor must have a finite whole-train speed zone')
    signal = project.model(owner).contents[11].value
    signature = {'identity': reference, 'parts': [
        {'owner': project.owners[id(part)], 'release_anchors': release_keys(project, part), 'profile': _route_profile(part)}
        for part in parts],
        'directed_nodes': movement, 'slow_zone': slow, 'signal_id': signal.contents[0].value,
        'signal_profile': list(signal.contents[9].values)}
    return preceding, movement, signature


def _attachment(project, protected_routes, relay):
    sequences = [project.route_view(item) for item in protected_routes]
    need(len(sequences) in (1, 2) and all(seq for seq in sequences)
         and (len(sequences) == 1 or sequences[0][-1] == sequences[1][0] == relay),
         'The original occupied entry and its successor must use the same directed relay')
    continued = sequences[0] if len(sequences) == 1 else [*sequences[0], *sequences[1][1:]]
    need(relay in continued[1:-1], 'The reviewed cut must be strictly interior to the occupied movement')
    return continued


def audit_preceding_slow_occupied_split(project, protected_routes, relay, occupancy, review, banks):
    """Read native placement, active itinerary adjacency, berth and precise resource closure."""
    preceding, approach, signature = _ordinary_fixed_predecessor(project, review)
    protected = _attachment(project, protected_routes, relay)
    need(all(preceding is not route for route in protected_routes) and approach[-1] == protected[0],
         'Select an independently saved Route immediately before the original occupied entry')
    preceding_elements, preceding_exclusions = _locks(project, approach)
    occupied_elements, occupied_exclusions = _locks(project, protected)
    need(not (preceding_elements | preceding_exclusions) & (occupied_elements | occupied_exclusions),
         'The fixed slow predecessor shares an occupied-movement Safety Element or Edge exclusion')
    root, _ = writer.load_next_compatible(banks['courses'])
    participants = {occupancy['receiver_course']: occupancy['receiver_length_m'],
                    occupancy['donor_course']: occupancy['donor_length_m']}
    active = {row['course_id']: row for item in catalogs.course_items(root)
              if (row := course_record(item))['enabled'] and row['course_id'] in participants}
    need(active.keys() == participants.keys(), 'The exact two occupied-entry Courses must be enabled')
    itineraries = {ident(item)[0]: item for item in project.dests}
    course_proofs = {}
    zone = signature['slow_zone']
    start, finish = zone['original_effective_zone_anchors']
    for course_id, length in participants.items():
        course = active[course_id]
        need(course['spacing_mode_code'] == 0 and len(course['itineraries']) == 1,
             'Review two fixed-block Courses with a single existing approach Itinerary each')
        itinerary = itineraries[course['itineraries'][0]]
        chain = list(itinerary_routes(project, itinerary))
        match = [i for i, route in enumerate(chain) if route is preceding]
        following = chain[match[0] + 1:match[0] + 1 + len(protected_routes)] if match else []
        need(len(match) == 1 and all(sum(item is route for item in chain) == 1 for route in protected_routes)
             and len(following) == len(protected_routes)
             and all(actual is expected for actual, expected in zip(following, protected_routes)),
             'Both reviewed Courses must use the fixed slow predecessor and occupied movement consecutively once')
        trace = route_trace(project, itinerary)
        nodes, distances = trace['_directed_nodes'], trace['_node_distances_m']
        keys = start, finish, protected[0], relay
        need(all(nodes.count(node) == 1 for node in keys),
             'The fixed slow and occupied entry boundary must be unique on both Course axes')
        zone_start, zone_finish, old_entry, new_entry = (distances[nodes.index(key)] for key in keys)
        contact = occupancy['berth']['donor_contact_distance_m']
        need(zone_start < zone_finish < zone_finish + length < old_entry < new_entry < contact,
             'Both trains must clear the fixed slow zone before the original entry and the separated contact')
        course_proofs[course_id] = {'itinerary': course['itineraries'][0], 'train_length_m': length,
                                    'slow_zone_course_m': [zone_start, zone_finish],
                                    'tail_clearance_head_m': zone_finish + length,
                                    'original_occupied_entry_m': old_entry, 'relay_m': new_entry,
                                    'clearance_before_original_occupied_entry_m': old_entry - (zone_finish + length)}
    return {'preceding': signature, 'occupied_directed_nodes': protected,
            'ordinary_resources': {'safety_elements': sorted(preceding_elements), 'exclusions': sorted(preceding_exclusions)},
            'occupied_resources': {'safety_elements': sorted(occupied_elements), 'exclusions': sorted(occupied_exclusions)},
            'course_axes': course_proofs, 'donor_contact_m': occupancy['berth']['donor_contact_distance_m']}


def check_preceding_slow_occupied_split(project, upstream, downstream, relay, occupancy, review, banks, before):
    after = audit_preceding_slow_occupied_split(project, [upstream, downstream], relay, occupancy, review, banks)
    need(after == before, 'The separately saved slow predecessor or reviewed occupation geometry changed after reload')
    return {**after, 'preceding_profile_and_resources_preserved': True, 'native_archive_readback_verified': True}

