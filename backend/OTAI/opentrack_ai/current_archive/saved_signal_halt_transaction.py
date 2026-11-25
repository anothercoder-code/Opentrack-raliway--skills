"""Compose one directional halt relocation and station-area main Route split."""

from .multi_document.core import ident, need
from .network_operating_plan import _platform_profile, route_trace
from .saved_cross_platform_halts import _guard_signal_incidents
from .saved_geometry import project_from
from .saved_halt_location import _stop_selection, relocate_station_halt_signal
from .saved_halt_relocation_review import review_halt_relocation
from .saved_main_signal_split import insert_signal_in_saved_route
from .saved_platform_block_safety import partition_platform_block_safety, verify_platform_block_safety
from .saved_station_areas import station_model


def _profiles(project, changed_ends):
    scope = changed_ends | {project.related(end) for end in changed_ends}
    profiles = {}
    for item in project.dests:
        if not scope.intersection(project.dest_view(item)[0]):
            continue
        name = ident(item)[0]
        need(name not in profiles, 'The compound station edit requires unique saved Itinerary names')
        try:
            profiles[name] = route_trace(project, item)
        except ValueError as exc:
            raise ValueError(f'Cannot review the compound station edit on Itinerary {name}: {exc}') from exc
    return profiles


def _marker_range_rows(markers):
    return [{'document': marker['end_key'][0], 'signal_id': marker['signal_id'],
             'end_id': marker['end_key'][1], 'signal_type': marker['signal_type']} for marker in markers]


def _expected_visit(before, old_end, new_end, signal, displacement):
    profile = before.get('halt_platform')
    if profile is None:
        return before, None
    marks = profile['markers']
    original = [mark for mark in marks if (mark['end_key'], mark['signal_id']) == (old_end, signal)]
    if not original:
        return before, None
    need(len(original) == 1, 'The revised directed stopping profile repeats the selected native halt marker')
    previous, = original
    indices = {}
    chainage = 0
    for index, segment in enumerate(profile['segments']):
        key = segment['from_end_key']
        need(key not in indices, 'The revised directed stopping profile repeats a native End')
        indices[key] = index, chainage
        chainage += segment['length_m']
    need(new_end in indices, 'An affected saved Itinerary would lose its original directional halt marker')
    _, offset = indices[new_end]
    need(offset - previous['platform_position_m'] == displacement,
         'The revised native halt marker shift differs for an affected saved Itinerary')
    moved = {**previous, 'end_key': new_end, 'platform_position_m': offset}
    revised = sorted((moved if mark is previous else mark for mark in marks),
                     key=lambda mark: indices[mark['end_key']][0])
    need(len({mark['end_key'] for mark in revised}) == len(revised),
         'The revised stopping profile has two halt markers on one native End')
    exit = profile['exit']
    _stop_selection(_marker_range_rows(marks), _marker_range_rows(revised), (exit['end_key'][0], exit['signal_id']))
    stop = _platform_profile(profile['segments'],
                            [(indices[mark['end_key']][0], (mark['signal_type'], mark['signal_id']))
                             for mark in revised],
                            (exit['signal_type'], exit['signal_id']), exit['end_key'],
                            profile['start_distance_m'], profile['start_elapsed_s'])
    return {**before, **stop}, {'before': previous, 'after': moved}


def _verify_profiles(before, after, old_end, new_end, signal, displacement):
    need(before.keys() == after.keys() and before, 'The native station edits changed which Itineraries use the station')
    revised = []
    for name, trace in before.items():
        expected = []
        for index, visit in enumerate(trace['visits']):
            target, marker = _expected_visit(visit, old_end, new_end, signal, displacement)
            expected.append(target)
            if marker is not None:
                revised.append({'itinerary': name, 'visit_index': index, 'reference_end': visit['end_key'], **marker})
        need(after[name] == {**trace, 'visits': expected},
             f'The compound station edit changes another native visit or movement of Itinerary {name}')
    need(revised, 'No saved directed station visit contains the reviewed halt marker')
    return revised


def insert_signal_and_relocate_halt(documents, document_paths, dest_blob, document, operation, courses, *,
                                   operating_banks=None, run_bytes=None):
    """Apply both typed operations in memory and verify the resulting native archives together."""
    split, halt = operation.get('split_route'), operation.get('halt_relocation')
    need(operation.get('action') == 'create_main_signal' and operation.get('main_role') == 'block'
         and isinstance(halt, dict) and isinstance(split, dict)
         and all(split.get(kind) is None for kind in ('terminal_overlap', 'occupied_entry', 'slow_zone', 'timing')),
         'Choose one ordinary saved Route split with a block signal and same-worksheet halt relocation')
    need(type(operating_banks) is dict and type(courses) is bytes and operating_banks.get('courses') == courses
         and type(run_bytes) is bytes, 'Bind the five original operating catalogs and native Project .run')
    before = project_from(documents, document_paths, dest_blob)
    station = station_model(before, document, halt['station_id'])
    old_end, new_end, block_end = [(document, number) for number in (
        halt['from_end_id'], halt['to_end_id'], operation['end_id'])]
    need(before.model(block_end).contents[12].value is station,
         'The new block signal and the halt relocation must use the same native StationModel')
    _guard_signal_incidents(courses, [(document, halt['signal_id'])])
    touched = {old_end, new_end, block_end}
    initial_profiles = _profiles(before, touched)
    safety = operation.get('vacated_block_safety')
    need(block_end != old_end or safety is not None,
         'Replacing the vacated halt by a block signal requires an exact native platform Safety partition')
    source_documents = documents
    safety_receipt = {}
    if safety is not None:
        content, safety_receipt = partition_platform_block_safety(
            before, documents, document_paths, dest_blob, document, station, operation, courses)
        source_documents = {**documents, document: content}
    move = {**halt, 'action': 'relocate_station_halt_signal'}
    moved, halt_receipt = relocate_station_halt_signal(
        source_documents, document_paths, dest_blob, document, move, platform_inputs=operating_banks, run_bytes=run_bytes)
    prepared = {**source_documents, **moved}
    main_signal = {name: value for name, value in operation.items() if name not in ('halt_relocation', 'vacated_block_safety')}
    relay, relay_receipt = insert_signal_in_saved_route(
        prepared, document_paths, dest_blob, document, main_signal, courses)
    changed = {**moved, **relay}
    final = project_from({**documents, **changed}, document_paths, dest_blob)
    if safety_receipt:
        verify_platform_block_safety(final, document, safety_receipt)
        need(relay_receipt['adjacent_safety_elements'] == [
            (document, safety_receipt[f'{side}_element_id']) for side in ('upstream', 'downstream')],
            'The split Route does not use the reviewed native safety groups at the vacated halt')
    final_profiles = _profiles(final, touched)
    updated = _verify_profiles(initial_profiles, final_profiles, old_end, new_end, halt['signal_id'],
                               halt['expected_stop_shift_m'])
    platform = [(document, edge) for edge in halt_receipt['platform_edge_ids']]
    verified = review_halt_relocation(
        before, final, terminal=(document, halt_receipt['station_reference_end_id']), platform=platform,
        platform_length=halt_receipt['platform_length_m'], affected_itineraries=set(final_profiles),
        operating_inputs=operating_banks, run_bytes=run_bytes, visit_reviews=halt['visit_reviews'])
    need(verified['verified_platform_visits'] == halt_receipt['verified_platform_visits'],
         'The final booked stopping locations differ from the reviewed halt relocation')
    saved_berths = relay_receipt['station_berths_preserved']
    need(saved_berths['station_id'] == halt_receipt['station_id']
         and saved_berths['station_sign'] == halt_receipt['station_sign'],
         'Cold read attached the new relay and moved halt to different station areas')
    return changed, {
        **relay_receipt, 'halt_relocation': halt_receipt, 'changed_documents': sorted(changed),
        **({'vacated_block_safety': safety_receipt} if safety_receipt else {}),
        'combined_station_readback': {
            'station_id': saved_berths['station_id'], 'station_sign': saved_berths['station_sign'],
            'all_reviewed_itineraries': sorted(final_profiles), 'halt_profile_changes': updated,
            'other_affected_visits_unchanged': True, **verified,
        },
    }
