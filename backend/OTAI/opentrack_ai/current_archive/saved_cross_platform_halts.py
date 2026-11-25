"""Write halt markers on either worksheet of one reviewed native platform."""

from collections import defaultdict
from pathlib import PureWindowsPath

from . import catalogs, incident_operations, path_functions, route_factory, saved_station_areas, writer
from .graph_references import incoming_counts
from .graphic_alignment import signal_alignment_for_end
from .infrastructure_incidents.core import number_value
from .multi_document.core import need
from .native_platform_topology import station_turnout_kind, track_legs
from .route_discovery_tools import main_signal
from .saved_geometry import _movement_manifest, model_id, position, project_from
from .saved_halt_creation import _donor_profile, _install_markers, _selection, _verify_install
from .saved_halt_location import GENERAL_STOPS, _attach, _exact_platform_movements, _observed_markers, _stop_selection
from .signal_type_workflow.core import TYPES
from .zero_generation.topology import flt


def _end_ref(reference):
    return reference['document'], reference['end_id']


def _stop_markers(project, keys):
    return [{'document': key[0], **row} for key in keys for row in _observed_markers([project.model(key)])]


def _station_areas(project, target, operation):
    bindings = {row['document']: row['station_id'] for row in operation['station_areas']}
    need(len(bindings) == len(operation['station_areas']) == 2 and target in bindings,
         'Select one local StationModel in each of the two distinct platform worksheets')
    areas = {name: saved_station_areas.station_model(project, name, key, require_reference=name == target)
             for name, key in bindings.items()}
    need(all(path_functions.string(area.contents[7].value) == operation['expected_station_sign'] for area in areas.values()),
         'Both local StationModels must resolve the same reviewed native station sign')
    return areas


def _platform(project, target, operation, *, allow_station_turnouts=False):
    areas = _station_areas(project, target, operation)
    arrival = operation['arrival_route']
    owner = arrival['document'], arrival['start_id']
    route = project.owned(owner, 'OTRoute', (arrival['name'], arrival['array_id'], arrival['start_id']))
    nodes = project.route_view(route)
    terminal = project.model(nodes[-1])
    need(nodes[-1][0] == target and terminal.contents[12].value is areas[target] and terminal.contents[20].value == 2
         and main_signal(terminal) and terminal.contents[11].value.contents[8].values[1] == 4,
         'The arrival must end at the reviewed station reference and its existing main exit in target_document')
    members = []
    for key in reversed(nodes):
        if key[0] not in areas or project.model(key).contents[12].value is not areas[key[0]]:
            break
        members.append(key)
    members.reverse()
    need(len(members) >= 3 and len(set(members)) == len(members) and {key[0] for key in members} == areas.keys()
         and all(project.model(key).contents[20].value == 1 for key in members[:-1]),
         'Confirm a contiguous directed station area across the boundary with one terminal reference')
    changes = [(a, b) for a, b in zip(members, members[1:]) if a[0] != b[0]]
    need(len(changes) == 1, 'The reviewed platform must cross one worksheet boundary')
    local_approach, remote_end = changes[0]
    sending = project.related(local_approach)
    receiving = project.block_end(sending)
    after_crossing = project.related(receiving)
    reviewed = operation['expected_connector_pair']
    need((sending, receiving) == (_end_ref(reviewed['a']), _end_ref(reviewed['b']))
         and receiving[0] == remote_end[0] and project.block_end(receiving) == sending,
         'The directed reciprocal native connector pair differs from the review')
    receive_half = project.model(after_crossing)
    need(writer.kind(receive_half) == 'OTEndModel' and receive_half.contents[12].value is areas[remote_end[0]]
         and receive_half.contents[20].value == 1,
         'The remote connector approach half must carry the same ordinary station membership')
    for index, key in enumerate(members[1:-1], start=1):
        with_turnout = allow_station_turnouts and station_turnout_kind(project, members, index) == 'interior'
        for ordinary in (key, project.actual_related(key)):
            end = project.model(ordinary)
            need(writer.kind(end) == 'OTEndModel' and (with_turnout or len(track_legs(end)) == 1)
                 and end.contents[12].value is areas[ordinary[0]] and end.contents[20].value == 1,
                 'Every interior platform half must follow the reviewed station track')
    edges = [project.edge_between(a, b) for a, b in zip(members, members[1:])]
    need(edges == [(row['document'], row['edge_id']) for row in operation['expected_platform_edge_ids']],
         'The ordered two-worksheet platform Edge sequence differs from the review')
    distances = {}
    total = 0
    for key, edge in zip(members[:-1], edges, strict=True):
        distances[key] = total
        total += project.model(edge).contents[9].values[1]
    return members, distances, total, (target, model_id(terminal.contents[11].value)), (sending, receiving)


def _marker_targets(project, members):
    for key in members[:-1]:
        first, other = (project.model(ref) for ref in (key, project.related(key)))
        if writer.kind(other) != 'OTEndModel':
            continue
        if all(end.contents[9].value is not None and end.contents[10].value is None
               and end.contents[20].value == 1 and end.contents[12].value is first.contents[12].value
               for end in (first, other)):
            yield key


def create_cross_document_station_halt_signals(documents, paths, dest, document, operation, shapes):
    donor = _donor_profile(shapes, operation['donor_signal_id'])
    project = project_from(documents, paths, dest)
    members, distances, length, exit_id, connector_pair = snapshot = _platform(
        project, document, operation, allow_station_turnouts=True)
    baseline = _stop_markers(project, members[:-1])
    need(baseline == operation['expected_halt_signals'], 'The original cross-document halt sequence differs from the review')
    changes = defaultdict(list)
    for marker in operation['markers']:
        changes[marker['document']].append(marker)
    new_keys = {_end_ref(marker) for marker in operation['markers']}
    need(1 <= len(operation['markers']) <= 32 and len(new_keys) == len(operation['markers'])
         and new_keys <= set(_marker_targets(project, members)),
         'Select distinct ordinary paired platform Ends without a turnout or connector half')
    expected = _movement_manifest(project)
    affected = _exact_platform_movements(expected, new_keys, members)
    installed, fingerprints, output = {}, {}, {}
    for worksheet, additions in sorted(changes.items()):
        local = {key[1]: project.model(key) for key in new_keys if key[0] == worksheet}
        metres = {key[1]: distances[key] for key in new_keys if key[0] == worksheet}
        installed[worksheet], fingerprints[worksheet] = _install_markers(project, worksheet, additions, local, metres, donor)
        output[worksheet] = writer.dump_verified(project.roots[worksheet], project.versions[worksheet])
    revised = _stop_markers(project, members[:-1])
    selection = _selection(baseline, revised, distances, exit_id, length, operation.get('maximum_train_length_m'))
    fresh = project_from({**documents, **output}, paths, dest)
    need(_movement_manifest(fresh) == expected, 'A bound native movement changed during cross-document halt editing')
    need(_platform(fresh, document, operation, allow_station_turnouts=True) == snapshot
         and _stop_markers(fresh, members[:-1]) == revised,
         'The saved cross-document platform scope, connector or halt marker order differs after readback')
    for worksheet, added in installed.items():
        _verify_install(fresh, worksheet, added, donor, fingerprints[worksheet])
    return output, {'action': operation['action'], 'document': document, 'changed_documents': sorted(output),
        'station_sign': operation['expected_station_sign'], 'station_areas': operation['station_areas'],
        'arrival_route': operation['arrival_route'], 'donor_signal_id': operation['donor_signal_id'], 'donor': donor,
        'directed_platform_ends': members, 'platform_length_m': length, 'connector_pair': connector_pair,
        'platform_edges': operation['expected_platform_edge_ids'], 'unchanged_exit_signal': exit_id,
        'added_signals': [{'document': name, 'signal_id': model_id(signal)} for name, added in installed.items() for signal in added],
        'halt_signals_before': baseline, 'halt_signals_after': revised, 'stop_selection_by_train_length': selection,
        'affected_movements': affected, 'movement_count_checked': len(expected), 'nonselected_graph_verified': True,
        'destination_catalog_unchanged': True, 'native_execution_tested': False}


def _private_marker(project, owner, end_key):
    root = project.roots[owner[0]]
    signal = project.model(owner)
    end = project.model(end_key)
    route_factory.layout(signal, 'OTSignalModel', 11, route_factory.SIGNAL, graphic=True)
    need(signal.contents[8].values[0] in GENERAL_STOPS and signal.contents[7].value is end
         and end.contents[11].value is signal and signal.contents[6].value is None,
         'Select an ordinary native head, center or tail halt marker with no label object')
    counts = incoming_counts(root)
    need(counts[id(signal)] == 2 and counts[id(root.contents[2].value)] == 1,
         'The signal or its graphic array has another native observer')
    wrapper = signal.contents[10].value
    indications = route_factory.wrapper(wrapper, 'OTSigIndList')
    need(counts[id(wrapper)] == counts[id(wrapper.contents[0].value)] == 1,
         'The saved signal indication wrapper has another native observer')
    for indication in indications:
        route_factory.layout(indication, 'OTSigInd', 0, ['i', '@'])
        need(indication.contents[1].value is end and counts[id(indication)] == 1,
             'The saved halt indication is shared or refers to another End')
    extras = [signal.contents[slot].value for slot in (14, 15)]
    need(all(counts[id(array)] == 1 and not path_functions.mutable_array(array) for array in extras),
         'Moving saved performance or coasting definitions between worksheets needs a separate review')
    name = signal.contents[13].value
    need(name is not None and counts[id(name)] == 1 and path_functions.string(name),
         'The halt marker must have a private nonempty native name')
    return signal, indications


def _guard_signal_incidents(courses, references):
    if courses is None:
        return
    root, _ = writer.load_next_compatible(courses)
    catalogs.course_items(root)
    observed = {(document.casefold(), number) for document, number in references}
    for incident in catalogs.array(root.contents[1].value):
        catalogs.shape(incident, 'OTIncident', 12, incident_operations.SCHEMA)
        _, model, kind = incident.contents[5].values
        if kind in (2, 10, 11):
            document = PureWindowsPath(catalogs.text(incident.contents[2].value)).name.casefold().removesuffix('.opentrack')
            identities = [number_value(row) for row in catalogs.array(incident.contents[20].value)] if kind == 10 else [model]
            need(all((document, number) not in observed for number in identities), 'A saved Incident observes this signal identity')


def _transfer(project, old, new, signal, indications, new_id, xy, index):
    source, target = project.key(old)[0], project.key(new)[0]
    _attach(signal, old, new, indications, xy)
    signal.contents[0].value = new_id
    existing = [obj for obj in project.models[source] if obj is not signal]
    destination = list(project.models[target])
    destination.insert(index, signal)
    writer.set_elements(project.roots[source].contents[2].value, existing)
    writer.set_elements(project.roots[target].contents[2].value, destination)


def relocate_cross_document_station_halt_signal(documents, paths, dest, document, operation, courses,
                                                *, platform_inputs=None, run_bytes=None):
    project = project_from(documents, paths, dest)
    members, distances, length, exit_id, connector = reviewed = _platform(
        project, document, operation, allow_station_turnouts=True)
    old_key, new_key = (_end_ref(operation[key]) for key in ('from_end', 'to_end'))
    need(old_key[0] != new_key[0] and {old_key, new_key} <= set(_marker_targets(project, members)),
         'Select two ordinary platform Ends on opposite sides of the reviewed connector')
    before = _stop_markers(project, members[:-1])
    need(before == operation['expected_halt_signals'], 'The original cross-document halt sequence differs from the review')
    source, target = old_key[0], new_key[0]
    old_id = source, operation['signal_id']
    signal, indications = _private_marker(project, old_id, old_key)
    signal_type = signal.contents[8].values[0]
    is_head = signal_type == TYPES['stop_head']
    visit_reviews = operation.get('visit_reviews')
    review_bookings = not is_head or platform_inputs is not None or visit_reviews is not None
    if review_bookings:
        need(isinstance(platform_inputs, dict) and 'courses' in platform_inputs
             and type(run_bytes) is bytes and isinstance(visit_reviews, (list, tuple)),
             'Center or tail halt relocation needs run-bound operating catalogs and a review of every affected booked visit')
        need(courses is None or courses == platform_inputs['courses'], 'The run-bound Course catalog differs from the Incident review')
        courses = platform_inputs['courses']
    old, new = project.model(old_key), project.model(new_key)
    need(new.contents[11].value is None and all(end.contents[13].value is None for end in (old, new)),
         'The destination must be free and both Ends must have no measuring instrument')
    alignment = tuple(signal.contents[index].value for index in (4, 5))
    need(signal_alignment_for_end(old) == alignment == signal_alignment_for_end(new)
         and old.contents[1].value == new.contents[1].value,
         'The two drawings must use the same reviewed directional alignment')
    name = path_functions.string(signal.contents[13].value)
    need(all(path_functions.string(other.contents[13].value).casefold() != name.casefold()
             for other in project.models[target] if writer.kind(other) == 'OTSignalModel' and other.contents[13].value is not None),
         'The destination worksheet already has this signal name')
    new_id = target, max(project.byid[target]) + 1
    need(new_id[1] <= 2147483647 and incoming_counts(project.roots[target])[id(project.roots[target].contents[2].value)] == 1,
         'The destination graphic collection is shared or its ID allocator is exhausted')
    _guard_signal_incidents(courses, (old_id, new_id))
    selected = [row for row in before if (row['document'], row['signal_id'], row['end_id']) == (*old_id, old_key[1])]
    need(len(selected) == 1, 'The reviewed source End does not carry this halt marker')
    after = [row if row is not selected[0] else {**row, 'document': target, 'end_id': new_key[1], 'signal_id': new_id[1]}
             for row in before]
    after.sort(key=lambda row: distances[(row['document'], row['end_id'])])
    selections = _stop_selection(before, after, exit_id, relocated_identity={new_id: old_id})
    shift = distances[new_key] - distances[old_key]
    need(shift == operation['expected_stop_shift_m'], 'The physical stop shift differs from the review')
    manifest = _movement_manifest(project)
    affected = _exact_platform_movements(manifest, {old_key, new_key}, members)
    before_xy = position(signal)
    xy = [flt(base + finish - start, 'Translated halt signal position')
          for base, start, finish in zip(before_xy, position(old), position(new), strict=True)]
    source_index = project.models[source].index(signal)
    fingerprints = {name: writer.fingerprint(project.roots[name]) for name in (source, target)}
    _transfer(project, old, new, signal, indications, new_id[1], xy, len(project.models[target]))
    output = {name: writer.dump_verified(project.roots[name], project.versions[name]) for name in fingerprints}
    fresh = project_from({**documents, **output}, paths, dest)
    saved, saved_indications = _private_marker(fresh, new_id, new_key)
    need(old_id[1] not in fresh.byid[source] and fresh.model(old_key).contents[11].value is None
         and position(saved) == xy and _movement_manifest(fresh) == manifest
         and _platform(fresh, document, operation, allow_station_turnouts=True) == reviewed
         and _stop_markers(fresh, members[:-1]) == after,
         'Moved signal identity, position, platform or saved movements differ after cold readback')
    booking_proof = {}
    if review_bookings:
        from .saved_halt_relocation_review import review_halt_relocation

        original = project_from(documents, paths, dest)
        platform_edges = [project.edge_between(a, b) for a, b in zip(members, members[1:])]
        itinerary_names = {entry['identity'][0] for entry in affected if entry['kind'] == 'itinerary'}
        booking_proof = review_halt_relocation(original, fresh, terminal=members[-1], platform=platform_edges,
            platform_length=length, affected_itineraries=itinerary_names, operating_inputs=platform_inputs,
            run_bytes=run_bytes, visit_reviews=visit_reviews)
    _transfer(fresh, fresh.model(new_key), fresh.model(old_key), saved, saved_indications, old_id[1], before_xy, source_index)
    need(all(writer.fingerprint(fresh.roots[name]) == expected for name, expected in fingerprints.items()),
         'Something besides the reviewed signal ownership, local ID and drawing position changed')
    head_positions = {'stop_before_m': distances[old_key], 'stop_after_m': distances[new_key]} if is_head else {}
    reference = {TYPES['stop_head']: 'head', TYPES['stop_center']: 'center', TYPES['stop_tail']: 'tail'}[signal_type]
    return output, {'action': operation['action'], 'document': document, 'changed_documents': sorted(output),
        'station_sign': operation['expected_station_sign'], 'connector_pair': connector, 'unchanged_exit_signal': exit_id,
        'platform_length_m': length, 'signal_name': name, 'from_signal': {'document': source, 'signal_id': old_id[1]},
        'to_signal': {'document': target, 'signal_id': new_id[1]}, 'from_end': old_key, 'to_end': new_key,
        'before_graphic_xy': before_xy, 'after_graphic_xy': xy, 'stop_reference': reference, 'signal_type': signal_type,
        'marker_before_m': distances[old_key], 'marker_after_m': distances[new_key], **head_positions,
        'stop_shift_m': shift, 'halt_signals_before': before, 'halt_signals_after': after,
        'stable_stop_signal_selection_by_train_length': selections, 'affected_movements': affected,
        'movement_count_checked': len(manifest), 'nonselected_graph_verified': True, 'destination_catalog_unchanged': True,
        'native_execution_tested': False, **booking_proof}
