"""Write reviewed native halt signals on a platform approaching a physical buffer."""

from . import path_functions, route_factory, saved_station_areas, writer
from .multi_document.core import need
from .saved_geometry import _movement_manifest, model_id, position, project_from
from .saved_halt_creation import _donor_profile, _install_markers, _selection, _verify_install
from .saved_halt_location import (FORMATION_OFFSET_STOPS, _attach, _bindings, _exact_platform_movements,
                                  _observed_markers, _stop_selection)
from .zero_generation.topology import flt


def _platform(project, document, operation):
    reference_id = operation['station_reference_end_id']
    expected_signal = operation['expected_buffer_signal_id']
    need(reference_id is not None or expected_signal is None,
         'A signalized buffer platform requires its reviewed internal station reference')
    station = saved_station_areas.station_model(project, document, operation['station_id'], require_reference=reference_id is not None)
    arrival = operation['arrival_route']
    owner = arrival['document'], arrival['start_id']
    route = project.owned(owner, 'OTRoute', (arrival['name'], arrival['array_id'], arrival['start_id']))
    nodes = project.route_view(route)
    entry = document, operation['platform_entry_end_id']
    reference = None if reference_id is None else (document, reference_id)
    terminal = document, operation['expected_buffer_end_id']
    need(nodes[-1] == terminal and entry in nodes and nodes.index(entry) < len(nodes) - 2,
         'The reviewed platform entry must lead to the arrival Route buffer End through an internal End')
    members = nodes[nodes.index(entry):]
    need(reference is None or reference in members[1:-1], 'The reviewed station reference must be inside the buffer platform')
    bumper = project.model(terminal)
    other = project.related(terminal)
    paired = project.model(other)
    signal = bumper.contents[11].value
    need(other[0] == document and route_factory.physical_buffer(bumper, paired),
         'The arrival Route must end at the reviewed physical buffer')
    if expected_signal is None:
        need(signal is None, 'The reviewed physical buffer must have no terminal signal')
    else:
        need(signal is not None and model_id(signal) == expected_signal and signal.contents[8].values[:2] == [1, 4],
             'The reviewed physical buffer must retain its existing type-1 exit signal')
    for key in members:
        need(key[0] == document, 'The reviewed buffer platform must be contained in its worksheet')
        pair = saved_station_areas.end_pair(project, document, project.model(key))
        need(all(end.contents[12].value is station and end.contents[20].value == (2 if key == reference else 1)
                 for end in pair), 'The buffer platform must match the reviewed station reference state and one StationModel')
        need(all(end.contents[10].value is None for end in pair) and pair[0].contents[9].value is not None
             and (key == terminal or pair[1].contents[9].value is not None),
             'A reviewed buffer platform must be an uninterrupted ordinary single track')
    upstream_station = []
    station_sign = path_functions.string(station.contents[7].value)
    for key in reversed(nodes[:nodes.index(entry)]):
        end = project.model(key)
        area = end.contents[12].value
        if area is None or path_functions.string(area.contents[7].value) != station_sign:
            break
        upstream_station.append(end)
    need(not _observed_markers(upstream_station), 'Review the existing same-direction halt markers upstream of the selected platform')
    edges = [project.edge_between(a, b)[1] for a, b in zip(members, members[1:])]
    need(edges == operation['expected_platform_edge_ids'], 'The ordered buffer platform Edge sequence differs from the review')
    positions = {}
    length = 0
    for key, edge in zip(members[:-1], edges, strict=True):
        positions[key[1]] = length
        length += project.model((document, edge)).contents[9].values[1]
    return members, positions, length, expected_signal, station_sign


def create_terminal_station_halt_signals(documents, paths, dest, document, operation, shapes):
    donor = _donor_profile(shapes, operation['donor_signal_id'])
    project = project_from(documents, paths, dest)
    members, positions, length, signal_id, station_sign = reviewed = _platform(project, document, operation)
    ends = [project.model(key) for key in members[:-1]]
    before = _observed_markers(ends)
    need(before == operation['expected_halt_signals'], 'The original terminal platform halt sequence differs from the review')
    requests = operation['markers']
    candidates = {model_id(end): end for end in ends[1:]}
    need(all(row['end_id'] in candidates for row in requests), 'New halt markers require unoccupied internal directional platform Ends')
    expected = _movement_manifest(project)
    edited = {(document, row['end_id']) for row in requests}
    affected = _exact_platform_movements(expected, edited, members)
    created, fingerprint = _install_markers(project, document, requests, candidates, positions, donor)
    after = _observed_markers(ends)
    limit = 'physical buffer' if signal_id is None else 'existing exit signal'
    selection = _selection(before, after, positions, signal_id, length, operation.get('maximum_train_length_m'), limit=limit)
    output = writer.dump_verified(project.roots[document], project.versions[document])
    fresh = project_from({**documents, document: output}, paths, dest)
    need(_movement_manifest(fresh) == expected, 'A native movement changed during terminal halt marker editing')
    need(_platform(fresh, document, operation) == reviewed and _observed_markers([fresh.model(key) for key in members[:-1]]) == after,
         'The saved buffer platform, exit signal, or halt marker sequence differs after readback')
    _verify_install(fresh, document, created, donor, fingerprint)
    return {document: output}, {'action': operation['action'], 'document': document, 'changed_documents': [document],
        'station_id': operation['station_id'], 'station_sign': station_sign,
        'station_reference_end_id': operation['station_reference_end_id'],
        'arrival_route': operation['arrival_route'], 'buffer_end_id': operation['expected_buffer_end_id'],
        'platform_edge_ids': operation['expected_platform_edge_ids'], 'platform_length_m': length,
        'unchanged_exit_signal_id': signal_id, 'terminal_has_signal': signal_id is not None,
        'unsigned_buffer_fallback_is_geometry_only': signal_id is None,
        'added_signal_ids': [model_id(signal) for signal in created],
        'halt_signals_before': before, 'halt_signals_after': after, 'stop_selection_by_train_length': selection,
        'donor': donor, 'affected_movements': affected, 'movement_count_checked': len(expected),
        'nonselected_graph_verified': True, 'destination_catalog_unchanged': True, 'native_execution_tested': False}


def relocate_terminal_station_halt_signal(documents, paths, dest, document, operation, *,
                                          platform_inputs=None, run_bytes=None):
    project = project_from(documents, paths, dest)
    members, positions, length, signal_id, station_sign = reviewed = _platform(project, document, operation)
    first, last = ((document, operation[name]) for name in ('from_end_id', 'to_end_id'))
    need(first != last and {first, last} <= set(members[1:-1]),
         'Select two distinct ordinary interior Ends before the reviewed buffer')
    ends = [project.model(key) for key in members[:-1]]
    before = _observed_markers(ends)
    need(before == operation['expected_halt_signals'], 'The original terminal platform halt sequence differs from the review')
    marker_id = operation['signal_id']
    matching = [row for row in before if row['end_id'] == first[1] and row['signal_id'] == marker_id]
    need(len(matching) == 1, 'The reviewed source End does not carry this halt marker')
    old_position, new_position = positions[first[1]], positions[last[1]]
    need(new_position - old_position == operation['expected_stop_shift_m'], 'Saved buffer platform distances differ from the reviewed shift')
    after = [{**row, 'end_id': last[1]} if row is matching[0] else row for row in before]
    after.sort(key=lambda row: positions[row['end_id']])
    selection = _stop_selection(before, after, signal_id)
    signal, old, new, indications = _bindings(project, document, marker_id, first[1], last[1])
    signal_type = signal.contents[8].values[0]
    visits = operation.get('visit_reviews')
    review_bookings = signal_type in FORMATION_OFFSET_STOPS or platform_inputs is not None or visits is not None
    if review_bookings:
        need(platform_inputs is not None and isinstance(run_bytes, bytes) and isinstance(visits, (list, tuple)),
             'Moving this marker needs the run-bound operating catalogs and every affected booked stop review')
    manifest = _movement_manifest(project)
    affected = _exact_platform_movements(manifest, {first, last}, members)
    original_xy = position(signal)
    xy = [flt(base + target - source, 'Translated halt signal position')
          for base, source, target in zip(original_xy, position(old), position(new), strict=True)]
    root = project.roots[document]
    fingerprint = writer.fingerprint(root)
    _attach(signal, old, new, indications, xy)
    output = writer.dump_verified(root, project.versions[document])
    fresh = project_from({**documents, document: output}, paths, dest)
    saved, saved_target, saved_source, saved_indications = _bindings(fresh, document, marker_id, last[1], first[1])
    need(position(saved) == xy and _movement_manifest(fresh) == manifest and _platform(fresh, document, operation) == reviewed
         and _observed_markers([fresh.model(key) for key in members[:-1]]) == after,
         'The moved marker, saved buffer platform or native movements differ after readback')
    booking_proof = {}
    reference_id = operation['station_reference_end_id']
    if review_bookings:
        from .saved_halt_relocation_review import review_halt_relocation

        baseline = project_from(documents, paths, dest)
        reference = members[-1] if reference_id is None else (document, reference_id)
        booking_proof = review_halt_relocation(baseline, fresh, terminal=reference,
            platform=[(document, edge) for edge in operation['expected_platform_edge_ids']], platform_length=length,
            affected_itineraries={row['identity'][0] for row in affected if row['kind'] == 'itinerary'},
            operating_inputs=platform_inputs, run_bytes=run_bytes, visit_reviews=visits)
    _attach(saved, saved_target, saved_source, saved_indications, original_xy)
    need(writer.fingerprint(fresh.roots[document]) == fingerprint,
         'Something besides the halt signal attachment and drawing position changed')
    return {document: output}, {'action': operation['action'], 'document': document, 'changed_documents': [document],
        'station_id': operation['station_id'], 'station_sign': station_sign, 'station_reference_end_id': reference_id,
        'buffer_end_id': members[-1][1], 'unchanged_exit_signal_id': signal_id, 'terminal_has_signal': signal_id is not None,
        'signal_id': marker_id, 'signal_type': signal_type, 'from_end_id': first[1], 'to_end_id': last[1],
        'platform_edge_ids': operation['expected_platform_edge_ids'], 'platform_length_m': length,
        'position_from_platform_entry_before_m': old_position, 'position_from_platform_entry_after_m': new_position,
        'before_graphic_xy': original_xy, 'after_graphic_xy': xy, 'halt_signals_before': before, 'halt_signals_after': after,
        'stable_stop_signal_selection_by_train_length': selection, 'affected_movements': affected,
        'movement_count_checked': len(manifest), 'nonselected_graph_verified': True,
        'destination_catalog_unchanged': True, 'native_execution_tested': False, **booking_proof}
