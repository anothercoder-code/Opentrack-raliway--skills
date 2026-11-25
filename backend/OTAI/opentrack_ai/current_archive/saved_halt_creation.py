"""Build trusted native halt markers for a reviewed directional station approach."""

from . import path_functions, route_factory, saved_station_areas, writer
from .graphic_alignment import signal_alignment_for_end, validate_generated_signal_alignment
from .graph_references import incoming_counts
from .multi_document.core import need
from .saved_geometry import _movement_manifest, model_id, position, project_from
from .saved_halt_location import (HALT_TYPES, _exact_platform_movements, _observed_markers, _selected_marker,
                                 marker_identity, reviewed_halt_platform)
from .signal_type_workflow.core import STOP_LENGTHS, TYPES
from .zero_generation import native_signal_routes as native
from .zero_generation.topology import flt


LENGTH_TYPES = {metres: code for code, metres in STOP_LENGTHS.items()}
HEAD_OFFSETS = {TYPES['stop_center']: 0.5, TYPES['stop_tail']: 1}
REVIEWED_INACTIVE_FLAGS = 1 | 4 | 8 | 128 | 512


def _donor_profile(data, donor_id):
    need(type(data) is bytes, 'Provide a checksummed original worksheet with a native halt marker')
    root, _ = writer.load_next_compatible(data)
    if root.clazz.version == 3:
        route_factory.layout(root, 'OTDocument', 3, ['i', 'i', '@', 'i', 'i', '@', '@', '@', 'ffff', 'ffff',
                                                     'ffff', 'f', '@', '@', 'ffff', 'iii', 'ff', '@', '@'])
        native_models = path_functions.mutable_array(root.contents[2].value)
        models = {model_id(obj): obj for obj in native_models}
        need(len(models) == len(native_models), 'Duplicate legacy donor graphic ID')
    else:
        _, models = route_factory.document(root)
    signal = models.get(donor_id)
    need(signal is not None and writer.kind(signal) == 'OTSignalModel', 'Choose the exact native donor signal ID')
    version = signal.clazz.version
    need(version in (8, 11), 'Only reviewed stock Signal8 and current Signal11 halt profiles can be used')
    route_factory.layout(signal, 'OTSignalModel', version, route_factory.SIGNAL if version == 11 else route_factory.SIGNAL[:-1],
                         graphic=True)
    signal_type, role, location = signal.contents[8].values
    need(signal_type in HALT_TYPES and role in (1, 2, 3, 4) and location in (0, 1, 2),
         'A verified donor must be a native halt marker with reviewed role and location')
    end = signal.contents[7].value
    need(writer.kind(end) == 'OTEndModel' and end.clazz.version in (6, 7) and models.get(model_id(end)) is end
         and end.contents[11].encodings == [b'@'] and end.contents[11].value is signal,
         'The native donor halt marker must have its original directional attachment')
    need(signal.contents[6].value is None and not route_factory.wrapper(signal.contents[10].value, 'OTSigIndList')
         and not any(path_functions.mutable_array(signal.contents[slot].value) for slot in (14, 15)),
         'Choose a simple halt-profile donor without auxiliary graphics, aspects, performance or coasting')
    show, sight, flags, release = signal.contents[9].values
    need(show in (1, 2) and 0 <= sight <= 100000 and flags & ~REVIEWED_INACTIVE_FLAGS == 0 and 0 <= release <= 1000,
         'The saved donor display, release or inactive flag profile is outside the reviewed scope')
    # Signal8 has no appended delay group. The stock Signal decoder defaults it to zero.
    delay = signal.contents[16].value if version == 11 else 0.0
    need(delay == 0, 'Choose a native halt-profile donor without additional braking delay')
    return {'type': signal_type, 'version': version, 'role': role, 'location': location,
            'display': [show, sight, flags, release], 'warning': signal.contents[11].value,
            'dispatching': signal.contents[12].value, 'delay': delay}


def _signal_type(request):
    reference = request['stop_reference']
    if reference == 'length':
        choice = request.get('maximum_length_for_marker_m')
        need(choice in LENGTH_TYPES, 'Select a native discrete train length for the halt marker')
        return LENGTH_TYPES[choice]
    need(reference in ('head', 'center', 'tail') and request.get('maximum_length_for_marker_m') is None,
         'Only a train-length marker accepts a length threshold')
    return TYPES[f'stop_{reference}']


def _new_signal(identifier, marker, end, donor):
    end_alignment = signal_alignment_for_end(end)
    coordinates = [flt(value + marker.get(f'graphic_offset_{axis}', 0), 'Halt marker drawing position')
                   for axis, value in zip(('x', 'y'), position(end), strict=True)]
    signal = native.obj([('OTSignalModel', 11), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [identifier]), ('f', [end.contents[1].value]), ('f', [coordinates[0]]), ('f', [coordinates[1]]),
        ('i', [end_alignment[0]]), ('i', [end_alignment[1]]), ('@', [None]), ('@', [end]),
        ('iii', [_signal_type(marker), donor['role'], donor['location']]), ('iiii', donor['display'][:]),
        ('@', [native.wrapped('OTSigIndList', [])]), ('i', [donor['warning']]), ('i', [donor['dispatching']]),
        ('@', [native.string(marker['signal_name'])]), ('@', [native.arr()]), ('@', [native.arr()]), ('f', [donor['delay']]),
    ])
    end.contents[11].value = signal
    validate_generated_signal_alignment(signal)
    return signal


def _selection(before, after, positions, exit_id, length, maximum=None, *, limit='existing exit signal',
               check_platform_entry=False):
    markers = {marker_identity(row, 'signal_id'): row for row in before + after}
    thresholds = sorted({STOP_LENGTHS[row['signal_type']] for row in markers.values() if row['signal_type'] in STOP_LENGTHS})
    results = []
    lower = 0
    for upper in [*thresholds, None]:
        if maximum is not None and lower >= maximum:
            break
        key = (maximum if maximum is not None else lower + 1) if upper is None else upper
        if maximum is not None:
            key = min(key, maximum)
        proof = {'length_gt_m': lower, 'length_lte_m': (key if maximum is not None or upper is not None else None)}
        for name, group in (('before', before), ('after', after)):
            selected = _selected_marker(group, key, exit_id)
            if selected == exit_id:
                at, factor = length, 0
            else:
                selected_marker = markers[selected]
                at = positions[marker_identity(selected_marker, 'end_id')]
                factor = HEAD_OFFSETS.get(selected_marker['signal_type'], 0)
            if name == 'after' and factor:
                need(maximum is not None and at + factor * key <= length,
                     f'The reviewed center/tail train would extend beyond the {limit}')
            if name == 'after' and check_platform_entry and maximum is not None:
                need(at + factor * key >= key, 'The reviewed train tail would extend before the platform entry')
            identifier = {'document': selected[0], 'signal_id': selected[1]} if isinstance(selected, tuple) else {'signal_id': selected}
            proof[name] = {**identifier, 'marker_position_m': at, 'head_offset_per_train_m': factor,
                           'example_train_length_m': key, 'example_head_position_m': at + factor * key}
        results.append(proof)
        lower = upper
    return results


def _affected_movements(manifest, target_keys, marker_keys, terminal):
    affected = []
    required = target_keys | marker_keys | {terminal}
    for (kind, owner, identity), (nodes, _, _) in manifest.items():
        if not target_keys.intersection(nodes):
            continue
        need(required.issubset(nodes), f'A saved {kind} {identity!r} sees only part of the directed platform stop sequence')
        affected.append({'kind': kind, 'owner': owner, 'identity': identity})
    need(affected, 'No saved operational movement uses the reviewed directed marker positions')
    return affected


def _install_markers(project, document, requests, candidates, distances, donor):
    root = project.roots[document]
    names = {path_functions.string(model.contents[13].value).casefold() for model in project.models[document]
             if writer.kind(model) == 'OTSignalModel' and model.contents[13].value is not None}
    high = max(project.byid[document])
    need(1 <= len(requests) <= 32 and high + len(requests) <= 2147483647, 'Select up to 32 new markers with available native IDs')
    chosen = {row['end_id'] for row in requests}
    need(len(chosen) == len(requests) and chosen <= candidates.keys(), 'Select distinct interior Ends on the reviewed directed platform')
    counts = incoming_counts(root)
    need(counts[id(root.contents[2].value)] == 1, 'The native worksheet graphic array has another owner')
    fingerprint = writer.fingerprint(root)
    created = []
    for ordinal, marker in enumerate(requests, high + 1):
        key = marker['end_id']
        end = candidates[key]
        name = marker['signal_name']
        need(name and name.casefold() not in names, 'Choose a unique nonempty native halt marker name')
        names.add(name.casefold())
        need(end.contents[11].value is None and end.contents[13].value is None,
             'A halt marker requires a free directional End without an attached instrument')
        need(distances[key] == marker['expected_position_from_entry_m'], 'The physical marker position differs from the review')
        created.append(_new_signal(ordinal, marker, end, donor))
    writer.set_elements(root.contents[2].value, [*project.models[document], *created])
    return created, fingerprint


def _verify_install(project, document, created, donor, fingerprint):
    root = project.roots[document]
    saved_objects = []
    for source in created:
        saved = project.model((document, model_id(source)))
        end = saved.contents[7].value
        validate_generated_signal_alignment(saved)
        need(position(saved) == position(source) and saved.contents[8].values == source.contents[8].values
             and saved.contents[9].values == donor['display'] and not route_factory.wrapper(saved.contents[10].value, 'OTSigIndList')
             and saved.contents[7].value.contents[0].value == source.contents[7].value.contents[0].value
             and path_functions.string(saved.contents[13].value) == path_functions.string(source.contents[13].value),
             'Saved halt signal type, drawing placement, directional End or display profile differs after native readback')
        saved_objects.append(saved)
        end.contents[11].value = None
    writer.set_elements(root.contents[2].value, [model for model in project.models[document] if model not in saved_objects])
    need(writer.fingerprint(root) == fingerprint, 'Something besides the new halt signals and their end references changed')


def create_station_halt_signals(documents, paths, dest, document, operation, shapes, *, platform_inputs=None, run_bytes=None):
    donor = _donor_profile(shapes, operation['donor_signal_id'])
    project = project_from(documents, paths, dest)
    root = project.roots[document]
    station = saved_station_areas.station_model(project, document, operation['station_id'])
    platform = reviewed_halt_platform(project, document, station, operation, 3)
    before = _observed_markers(platform.members[:-1])
    need(before == operation['expected_halt_signals'], 'The current directional halt marker order differs from the review')
    requests = operation['markers']
    expected = _movement_manifest(project)
    terminal_key = project.key(platform.exit)
    new_keys = {(document, row['end_id']) for row in requests}
    known_keys = {(document, row['end_id']) for row in before}
    if platform.exact_movement:
        affected = _exact_platform_movements(expected, new_keys, [project.key(end) for end in platform.members])
    else:
        affected = _affected_movements(expected, new_keys, known_keys, terminal_key)
    created, fingerprint = _install_markers(project, document, requests, platform.targets, platform.distances, donor)
    after = _observed_markers(platform.members[:-1])
    exit_id = model_id(platform.exit.contents[11].value)
    checked_selections = _selection(before, after, platform.distances, exit_id, platform.length,
                                    operation.get('maximum_train_length_m'), check_platform_entry=platform.exact_movement)
    output = writer.dump_verified(root, project.versions[document])
    checked = project_from({**documents, document: output}, paths, dest)
    need(_movement_manifest(checked) == expected, 'A saved movement changed after inserting a halt board')
    checked_station = saved_station_areas.station_model(checked, document, operation['station_id'])
    saved = reviewed_halt_platform(checked, document, checked_station, operation, 3)
    need(model_id(saved.exit.contents[11].value) == exit_id and saved.edge_ids == platform.edge_ids
         and saved.reference == platform.reference and _observed_markers(saved.members[:-1]) == after
         and saved.distances == platform.distances and saved.length == platform.length,
         'Native halt marker order, station lookup or track length changed after readback')
    reviewed_visits = {}
    visit_reviews = operation.get('visit_reviews')
    if platform_inputs is not None or visit_reviews is not None:
        from .saved_halt_relocation_review import review_halt_relocation

        review_source = project_from(documents, paths, dest)
        itinerary_names = {row['identity'][0] for row in affected if row['kind'] == 'itinerary'}
        reviewed_visits = review_halt_relocation(review_source, checked, terminal=platform.reference,
            platform=[(document, edge_id) for edge_id in platform.edge_ids], platform_length=platform.length,
            affected_itineraries=itinerary_names, operating_inputs=platform_inputs, run_bytes=run_bytes,
            visit_reviews=visit_reviews)
    _verify_install(checked, document, created, donor, fingerprint)
    return {document: output}, {'action': operation['action'], 'document': document, 'changed_documents': [document],
        'station_id': operation['station_id'], 'station_sign': path_functions.string(station.contents[7].value),
        'arrival_route': operation['arrival_route'], 'donor_signal_id': operation['donor_signal_id'], 'donor': donor,
        'added_signal_ids': [model_id(signal) for signal in created], 'halt_signals_before': before, 'halt_signals_after': after,
        'platform_edge_ids': platform.edge_ids, 'platform_length_m': platform.length, 'unchanged_exit_signal_id': exit_id,
        'station_reference_end_id': platform.reference[1],
        'maximum_reviewed_train_length_m': operation.get('maximum_train_length_m'), 'stop_selection_by_train_length': checked_selections,
        'affected_movements': affected, 'movement_count_checked': len(expected), 'nonselected_graph_verified': True,
        'destination_catalog_unchanged': True, 'native_execution_tested': False, **reviewed_visits}
