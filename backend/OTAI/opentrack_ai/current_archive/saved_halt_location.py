"""Move an existing directional halt signal between Ends on one saved platform."""

from dataclasses import dataclass

from . import path_functions, route_factory, saved_station_areas, writer
from .graphic_alignment import signal_alignment_for_end
from .graph_references import incoming_counts
from .multi_document.core import need
from .native_platform_topology import station_turnout_kind, track_legs
from .route_discovery_tools import main_signal
from .saved_geometry import _movement_manifest, model_id, position, project_from
from .signal_type_workflow.core import STOP_LENGTHS, TYPES
from .zero_generation.topology import flt


HALT_TYPES = {value for label, value in TYPES.items() if label.startswith('stop_')}
GENERAL_STOPS = {TYPES['stop_head'], TYPES['stop_center'], TYPES['stop_tail']}
MOVABLE_STOPS = GENERAL_STOPS | STOP_LENGTHS.keys()
FORMATION_OFFSET_STOPS = {TYPES['stop_center'], TYPES['stop_tail']}


def _observed_markers(members):
    markers = []
    for end in members:
        signal = end.contents[11].value
        if signal is not None and signal.contents[8].values[0] in HALT_TYPES:
            markers.append({'signal_id': model_id(signal), 'end_id': model_id(end),
                            'signal_type': signal.contents[8].values[0]})
    return markers


def marker_identity(marker, field):
    return (marker['document'], marker[field]) if 'document' in marker else marker[field]


def _selected_marker(markers, length, exit_id):
    # Stock 0063f6f0 scans the directed station. The first eligible length
    # marker is selected unless a general head/centre/tail marker overwrites it.
    result = exit_id
    halt_selected = False
    for marker in markers:
        kind = marker['signal_type']
        if kind in GENERAL_STOPS or not halt_selected and length <= STOP_LENGTHS[kind]:
            result = marker_identity(marker, 'signal_id')
            halt_selected = True
    return result


def _stop_selection(before, after, exit_id, *, relocated_identity=None):
    limits = sorted({STOP_LENGTHS[row['signal_type']] for row in before if row['signal_type'] in STOP_LENGTHS})
    reports = []
    lower = 0
    for upper in [*limits, None]:
        witness = lower + 1 if upper is None else upper
        previous = _selected_marker(before, witness, exit_id)
        current = _selected_marker(after, witness, exit_id)
        analogous = relocated_identity.get(current, current) if relocated_identity else current
        need(previous == analogous, 'Moving the marker would change the selected native stop for a train-length range')
        reports.append({'length_gt_m': lower, 'length_lte_m': upper, 'signal_id': current})
        lower = upper
    return reports


def reviewed_platform(project, document, station, operation, minimum_members, *, allow_station_turnouts=False):
    reviewed = operation['arrival_route']
    owner = reviewed['document'], reviewed['start_id']
    identity = reviewed['name'], reviewed['array_id'], reviewed['start_id']
    route = project.owned(owner, 'OTRoute', identity)
    ends = project.route_view(route)
    terminal = project.model(ends[-1])
    need(ends[-1][0] == document and terminal.contents[12].value is station and terminal.contents[20].value == 2
         and main_signal(terminal) and terminal.contents[11].value.contents[8].values[1] == 4,
         'The reviewed arrival Route must end at this platform’s original main exit signal and station reference End')

    members = []
    for key in reversed(ends):
        end = project.model(key)
        if key[0] != document or end.contents[12].value is not station:
            break
        members.append(end)
    members.reverse()
    need(len(members) >= minimum_members and all(end.contents[20].value == 1 for end in members[:-1]),
         'Choose a continuous station approach with ordinary interior pairs and one reference End')
    pairs = [saved_station_areas.end_pair(project, document, end) for end in members]
    member_keys = [project.key(member) for member in members]
    need(all(all(len(track_legs(half)) == 1 for half in pair)
             or (allow_station_turnouts and station_turnout_kind(project, member_keys, index) == 'interior')
             for index, pair in enumerate(pairs[1:-1], start=1)),
         'The two locations must be on a nonbranching portion of one directed platform')
    edges = [project.edge_between(a, b) for a, b in zip(member_keys, member_keys[1:])]
    edge_ids = [edge[1] for edge in edges]
    need(edge_ids == operation['expected_platform_edge_ids'], 'Saved platform Edge sequence differs from the reviewed order')
    positions = {}
    metres = 0
    for end, edge in zip(members[:-1], edges, strict=True):
        positions[model_id(end)] = metres
        metres += project.model(edge).contents[9].values[1]
    return terminal, members, edge_ids, positions, metres


def reviewed_separate_exit(project, document, station, route, operation):
    from .network_operating_plan import _separate_platform_stop

    nodes = project.route_view(route)
    exit_end = project.model(nodes[-1])
    need(nodes[-1][0] == document and exit_end.contents[12].value is station and main_signal(exit_end)
         and exit_end.contents[11].value.contents[8].values[1] == 4,
         'The reviewed arrival Route must end at the selected station area and its main exit signal')
    references = [index for index, key in enumerate(nodes)
                  if key[0] == document and project.model(key).contents[12].value is station
                  and project.model(key).contents[20].value == 2]
    need(len(references) == 1 and 0 < references[0] < len(nodes) - 1,
         'Select one exact internal station reference before the main exit signal')
    ref_index, = references
    ref_node = project.model(nodes[ref_index])
    saved_station_areas.end_pair(project, document, ref_node)
    need(ref_node.contents[11].value is None, 'The separate station reference must have no saved signal')
    approach = [project.edge_between(a, b) for a, b in zip(nodes[:ref_index], nodes[1:ref_index + 1], strict=True)]
    metres = sum(project.model(edge).contents[9].values[1] for edge in approach)
    stop = _separate_platform_stop(project, nodes, ref_index, metres, 0, None, None)
    need('halt_stop_issue' not in stop and stop['default_stop']['end_key'] == nodes[-1],
         'The selected Route must lead from the separate reference to its one reviewed berth exit')
    edges = stop['stopping_area_edge_keys']
    keys = nodes[-len(edges) - 1:]
    need(all(key[0] == document for key in keys) and [edge[1] for edge in edges] == operation['expected_platform_edge_ids'],
         'Saved platform Edge sequence differs from the reviewed order')
    return nodes[ref_index], keys, edges, stop['stopping_area_length_m']


@dataclass
class HaltPlatform:
    reference: tuple[str, int]
    exit: writer.GenericArchivedObject
    members: list[writer.GenericArchivedObject]
    edge_ids: list[int]
    distances: dict[int, int]
    length: int
    targets: dict[int, writer.GenericArchivedObject]
    exact_movement: bool


def reviewed_halt_platform(project, document, station, operation, minimum_members):
    reviewed = operation['arrival_route']
    owner = reviewed['document'], reviewed['start_id']
    route = project.owned(owner, 'OTRoute', (reviewed['name'], reviewed['array_id'], reviewed['start_id']))
    nodes = project.route_view(route)
    exit_end = project.model(nodes[-1])
    reference = nodes[-1]
    if exit_end.contents[20].value == 2:
        exit_end, members, edge_ids, distances, length = reviewed_platform(
            project, document, station, operation, minimum_members, allow_station_turnouts=True)
    else:
        reference, keys, edges, length = reviewed_separate_exit(project, document, station, route, operation)
        need(len(keys) >= minimum_members, 'Choose a continuous station approach with enough interior Ends')
        members = [project.model(key) for key in keys]
        edge_ids = [key[1] for key in edges]
        distances = {}
        metres = 0
        for end, edge in zip(members[:-1], edges, strict=True):
            distances[model_id(end)] = metres
            metres += project.model(edge).contents[9].values[1]
    targets = {}
    first = nodes.index(project.key(members[0]))
    exact_movement = reference != nodes[-1] or station_turnout_kind(project, nodes, first) == 'entry'
    for end in members[1:-1]:
        pair = saved_station_areas.end_pair(project, document, end)
        if all(len(track_legs(half)) == 1 for half in pair) and end.contents[20].value == 1:
            targets[model_id(end)] = end
        else:
            exact_movement = True
    return HaltPlatform(reference, exit_end, members, edge_ids, distances, length, targets, exact_movement)


def _exact_platform_movements(manifest, marker_ends, platform):
    offsets = {key: index for index, key in enumerate(platform)}
    need(marker_ends <= offsets.keys(), 'Select distinct interior Ends on the reviewed directed platform')
    proof = []
    for (kind, owner, identity), (nodes, _, _) in manifest.items():
        visits = [index - offsets[key] for index, key in enumerate(nodes) if key in marker_ends]
        if visits:
            need(all(start >= 0 and nodes[start:start + len(platform)] == platform for start in visits),
                 f'A saved {kind} {identity!r} sees only part of the directed platform')
            proof.append({'kind': kind, 'owner': owner, 'identity': identity})
    need(proof, 'No saved operational movement uses the reviewed directed marker positions')
    return proof


def _platform(project, document, station, operation):
    platform = reviewed_halt_platform(project, document, station, operation, 4)
    positions = platform.distances
    first, last = operation['from_end_id'], operation['to_end_id']
    need(first != last and {first, last} <= platform.targets.keys(),
         'Select two different ordinary interior Ends facing the same directed station approach')
    markers = _observed_markers(platform.members[:-1])
    selected = [row for row in markers if row['end_id'] == first and row['signal_id'] == operation['signal_id']]
    need(len(selected) == 1, 'The reviewed old End does not carry this halt signal')
    reviewed = operation.get('expected_halt_signals')
    if reviewed is None:
        need(len(markers) == 1 and selected[0]['signal_type'] == TYPES['stop_head'],
             'Provide the exact ordered expected_halt_signals for multiple or formation-dependent markers')
    else:
        need(reviewed == markers, 'The directed platform halt signal order or identity differs from the review')
    moved_markers = [{**row, 'end_id': last} if row is selected[0] else row for row in markers]
    moved_markers.sort(key=lambda row: positions[row['end_id']])
    stop_selection = _stop_selection(markers, moved_markers, model_id(platform.exit.contents[11].value))
    need(positions[last] - positions[first] == operation['expected_stop_shift_m'],
         'Saved platform distances do not match the reviewed shift')
    return platform, positions[first], positions[last], markers, moved_markers, stop_selection


def _bindings(project, document, signal_id, old_key, new_key):
    old, new = (project.model((document, key)) for key in (old_key, new_key))
    signal = project.model((document, signal_id))
    route_factory.layout(signal, 'OTSignalModel', 11, route_factory.SIGNAL, graphic=True)
    need(signal.contents[8].values[0] in MOVABLE_STOPS and signal.contents[7].value is old and old.contents[11].value is signal
         and new.contents[11].value is None, 'Select an existing native halt signal and a free destination End')
    alignment = tuple(signal.contents[slot].value for slot in (4, 5))
    need(signal_alignment_for_end(old) == alignment == signal_alignment_for_end(new),
         'The old and new platform Ends must face the original signal direction')
    need(all(end.contents[13].value is None for end in (old, new)) and signal.contents[6].value is None,
         'An instrument or additional graphic reference shares one of the selected objects')
    counts = incoming_counts(project.roots[document])
    indications = route_factory.wrapper(signal.contents[10].value, 'OTSigIndList')
    need(counts[id(signal)] == 2 and counts[id(signal.contents[10].value)] == 1
         and counts[id(signal.contents[10].value.contents[0].value)] == 1,
         'The selected signal or its indication list has another saved observer')
    for indication in indications:
        route_factory.layout(indication, 'OTSigInd', 0, ['i', '@'])
        need(indication.contents[1].value is old and counts[id(indication)] == 1,
             'A saved halt indication is shared or refers to a different End')
    return signal, old, new, indications


def _attach(signal, old, new, indications, xy):
    old.contents[11].value = None
    new.contents[11].value = signal
    signal.contents[7].value = new
    signal.contents[2].value, signal.contents[3].value = xy
    for indication in indications:
        indication.contents[1].value = new


def relocate_station_halt_signal(documents, paths, dest, document, operation, *, platform_inputs=None, run_bytes=None):
    project = project_from(documents, paths, dest)
    station = saved_station_areas.station_model(project, document, operation['station_id'])
    platform, previous_m, next_m, markers, moved_markers, stop_selection = _platform(project, document, station, operation)
    source, target = operation['from_end_id'], operation['to_end_id']
    signal_id = operation['signal_id']
    signal, old, new, indications = _bindings(project, document, signal_id, source, target)
    signal_type = signal.contents[8].values[0]
    visit_reviews = operation.get('visit_reviews') or []
    operating_review = signal_type in FORMATION_OFFSET_STOPS or platform_inputs is not None or bool(visit_reviews)
    if operating_review:
        need(platform_inputs is not None and run_bytes is not None,
             'Moving this halt marker requires the reviewed original operating catalogs and run configuration')
    before = _movement_manifest(project)
    affected = []
    keys = {(document, source), (document, target)}
    if platform.exact_movement:
        affected = _exact_platform_movements(before, keys, [project.key(end) for end in platform.members])
    else:
        for (kind, owner, identity), (nodes, _, _) in before.items():
            used = keys.intersection(nodes)
            if used:
                need(used == keys, f'A saved {kind} {identity!r} would gain or lose a stop signal instead of moving it')
                need(all((document, row['end_id']) in nodes for row in markers),
                     f'A saved {kind} {identity!r} only sees part of the reviewed halt signal sequence')
                affected.append({'kind': kind, 'owner': owner, 'identity': identity})
        need(affected, 'No native movement traverses the two positions')
    prior_xy = position(signal)
    xy = [flt(value + new_pos - old_pos, 'Translated halt signal position')
          for value, new_pos, old_pos in zip(prior_xy, position(new), position(old), strict=True)]
    original_fingerprint = writer.fingerprint(project.roots[document])
    _attach(signal, old, new, indications, xy)
    content = writer.dump_verified(project.roots[document], project.versions[document])
    checked = project_from({**documents, document: content}, paths, dest)
    saved, after_end, before_end, saved_inds = _bindings(checked, document, signal_id, target, source)
    need(position(saved) == xy and _movement_manifest(checked) == before,
         'Native stop signal position or a saved movement differs after readback')
    reviewed_after = {**operation, 'from_end_id': target, 'to_end_id': source,
                      'expected_stop_shift_m': -operation['expected_stop_shift_m'], 'expected_halt_signals': moved_markers}
    fresh_station = saved_station_areas.station_model(checked, document, operation['station_id'])
    saved_platform, _, _, saved_markers, _, _ = _platform(checked, document, fresh_station, reviewed_after)
    need(saved_markers == moved_markers and saved_platform.reference == platform.reference
         and model_id(saved_platform.exit) == model_id(platform.exit),
         'The saved directed halt marker sequence differs after native readback')
    reviewed_visits = {}
    if operating_review:
        from .saved_halt_relocation_review import review_halt_relocation

        baseline = project_from(documents, paths, dest)
        reviewed_visits = review_halt_relocation(baseline, checked, terminal=platform.reference,
            platform=[(document, edge_id) for edge_id in platform.edge_ids], platform_length=platform.length,
            affected_itineraries={row['identity'][0] for row in affected if row['kind'] == 'itinerary'},
            operating_inputs=platform_inputs, run_bytes=run_bytes, visit_reviews=visit_reviews)
    _attach(saved, after_end, before_end, saved_inds, prior_xy)
    need(writer.fingerprint(checked.roots[document]) == original_fingerprint,
         'Something besides the halt signal attachment and drawing position changed')
    label = signal.contents[13].value
    return {document: content}, {
        'action': operation['action'], 'document': document, 'changed_documents': [document],
        'station_id': operation['station_id'], 'station_sign': path_functions.string(station.contents[7].value),
        'signal_id': signal_id, 'signal_name': path_functions.string(label) if label is not None else None,
        'signal_type': signal_type, 'halt_signals_before': markers, 'halt_signals_after': moved_markers,
        'stable_stop_signal_selection_by_train_length': stop_selection,
        'from_end_id': source, 'to_end_id': target, 'station_reference_end_id': platform.reference[1],
        'unchanged_exit_signal_id': model_id(platform.exit.contents[11].value),
        'platform_edge_ids': platform.edge_ids, 'before_graphic_xy': prior_xy, 'after_graphic_xy': xy, 'platform_length_m': platform.length,
        'position_from_platform_entry_before_m': previous_m, 'position_from_platform_entry_after_m': next_m,
        'affected_movements': affected, 'movement_count_checked': len(before), 'nonselected_graph_verified': True,
        'destination_catalog_unchanged': True, 'native_execution_tested': False, **reviewed_visits,
    }
