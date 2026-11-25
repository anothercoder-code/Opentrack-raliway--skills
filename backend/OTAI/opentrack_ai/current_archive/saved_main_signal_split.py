"""Insert one block signal and split a local or single-continuation Route."""

from collections import defaultdict

from . import catalogs, path_functions, route_factory, writer
from .catalog_batch_reuse.course_batch import course_record
from .graphic_alignment import validate_generated_signal_alignment
from .graph_references import incoming_counts
from .multi_document.core import ident, need, ref
from .multi_document.generate import inf, route as native_route
from .path_lifecycle_tools import Changes, _incident_bindings
from .route_edit_tools import _protection_values, _route_shape, _select_route
from .route_lifecycle_tools import _dependent_paths, _guard_identity, _guard_incidents, _owner_array
from .saved_cross_platform_halts import _guard_signal_incidents
from .saved_document_insertion import _route_profile
from .saved_geometry import _movement_geometry, _movement_manifest, model_id, project_from
from .saved_occupied_signal_split import ORDINARY_ENTRY, occupied_entry_values, verify_occupied_signal_split
from .saved_occupied_timing_signal_split import check_occupied_release_delay, plan_occupied_release_delay
from .saved_parallel_overlap_preparation import check_parallel_overlap_preparation, plan_parallel_overlap_preparation
from .saved_signal_path_incident import preserve_route_speed_incident
from .saved_signal_span_incidents import rebind_signal_route_incidents
from .saved_overlap_timing_signal_split import check_overlap_release_delay, plan_overlap_release_delay
from .saved_preceding_slow_occupied_split import audit_preceding_slow_occupied_split, check_preceding_slow_occupied_split
from .saved_slow_overlap_signal_split import check_slow_zone_overlap, plan_slow_zone_overlap
from .saved_slow_timing_signal_split import plan_slow_zone_timing
from .saved_slow_zone_signal_split import check_slow_section, extend_relay_indications, raw_zone_pointers, review_slow_zone_split
from .saved_station_areas import station_model
from .saved_terminal_overlap import overlap_reference, set_overlap_reference, split_terminal_overlap
from .saved_timing_signal_split import (
    DEFAULT_ROUTE_TIMING, check_timing_split, plan_timing_split, reviewed_route_timing, stored_route_timing, timing_groups,
)
from .signal_type_workflow.core import ROLES
from .zero_generation.native_signal_routes import main_signal_model


def _ordinary_route(route, slots, nodes, counts, *, continuation=-1, part='local', reviewed_overlap=False,
                    expected_entry=ORDINARY_ENTRY, slow_review=None, timing_review=None):
    protection = _protection_values(route, slots)
    releases = protection['release_group_end_ids']
    order = [model_id(node) for node in nodes]
    if part == 'local' and timing_review is None:
        valid_releases = releases == [order[0], order[-1]]
    else:
        valid_releases = releases == [number for number in order if number in releases]
        if part != 'receiving':
            valid_releases = valid_releases and bool(releases) and releases[0] == order[0]
        if part == 'local':
            valid_releases = valid_releases and releases[-1:] == order[-1:]
    aspect = slow_review['expected_native_aspect_code'] if slow_review is not None else 0
    head_only = slow_review is not None and slow_review['expected_head_only'] and part != 'receiving'
    timing = DEFAULT_ROUTE_TIMING if timing_review is None or part == 'receiving' else timing_review
    need(slots == 11 and counts[id(route.contents[0].value)] == counts[id(route.contents[12].values[0])] == 1
         and route.contents[5].values[4:] == [continuation, 0] and stored_route_timing(route) == timing
         and tuple(route.contents[6].values) == expected_entry
         and (expected_entry == ORDINARY_ENTRY or path_functions.string(route.contents[3].value) == '')
         and (reviewed_overlap or overlap_reference(route) == ('', -1))
         and route.contents[11].value == (2 if head_only else 0)
         and (slow_review is not None or route.contents[12].values[1:] == [None, None])
         and protection['signal_aspects'] == ([] if part == 'receiving' else [aspect]) and valid_releases,
         'The reviewed Route requires default reservation or the exact reviewed timing, the explicitly reviewed terminal '
         'overlap, occupied entry or slow-zone fields where present, and its ordered native release groups')


def _select_parts(project, owner, document, reference, counts, *, reviewed_overlap=False,
                  expected_entry=ORDINARY_ENTRY, slow_review=None, timing_review=None):
    sending = owner[0]
    records = [row for row in project.continuations if row['source_document'] == sending and row['route'] == reference]
    if sending == document and not records:
        route, slots, nodes, _, _, _ = _select_route(project.roots[document], reference)
        _ordinary_route(route, slots, nodes, counts[document], reviewed_overlap=reviewed_overlap,
                        expected_entry=expected_entry, slow_review=slow_review, timing_review=timing_review)
        return route, None, None, nodes
    route = project.owned(owner, 'OTRoute', (reference['name'], reference['array_id'], reference['start_id']))
    need(writer.kind(project.model(owner)) == 'OTEndModel', 'Select the sending main signal owner for the original Route')
    need(len(records) == 1 and document in (sending, records[0]['target_document']),
         'The split worksheet must be the exact sending or single receiving document of the selected Route')
    record, = records
    receiver = record['target_document'], record['target_connector']
    fragment = project.owned(receiver, 'OTRoute', ident(route))
    _owner_array(project, owner, counts)
    _owner_array(project, receiver, counts)
    local = path_functions.mutable_array(route.contents[0].value)
    remote = path_functions.mutable_array(fragment.contents[0].value)
    _ordinary_route(route, _route_shape(route), local, counts[sending], continuation=len(local),
                    part='primary', reviewed_overlap=reviewed_overlap, expected_entry=expected_entry,
                    slow_review=slow_review, timing_review=timing_review)
    _ordinary_route(fragment, _route_shape(fragment), remote, counts[receiver[0]],
                    part='receiving', expected_entry=expected_entry, slow_review=slow_review)
    need(counts[receiver[0]][id(fragment)] == 1, 'The receiving Route fragment has other direct saved owners')
    return route, fragment, record, local if sending == document else remote


def _plain_boundary(project, split, nodes, index):
    end = project.model(split)
    related = project.model(project.related(split))
    need(all(writer.kind(half) == 'OTEndModel' and half.contents[20].value == 1
             and all(half.contents[slot].value is None for slot in (10, 11, 13))
             and half.contents[9].value is not None for half in (end, related)),
         'Select a free, nonbranching ordinary paired End without a measuring instrument')
    station = end.contents[12].value
    need(related.contents[12].value is station, 'The two halves of the split vertex must have the same native station membership')
    if station is not None:
        need(station is station_model(project, split[0], model_id(station), require_reference=False),
             'The split vertex requires an exact native StationModel in its worksheet')
    need(all(not route_factory.wrapper(end.contents[slot].value, kind) for slot, kind in (
        (15, 'OTRouteList'), (16, 'OTShuntingList'), (17, 'OTPathList'))),
         'The split End must have empty native Route, Shunting and Path ownership lists')
    before, after = (project.model(project.edge_between(a, b)) for a, b in (
        (nodes[index - 1], split), (split, nodes[index + 1])))
    elements = [[edge.contents[slot].value.contents[7].value for slot in (7, 8)] for edge in (before, after)]
    need(all(first is second and writer.kind(first) == 'OTElement' for first, second in elements)
         and elements[0][0] is not elements[1][0],
         'The adjacent approach and departure Edges must already use distinct native Safety Elements')
    return end, [project.key(owners[0]) for owners in elements], station


def _station_profiles(project, split):
    from .network_operating_plan import route_trace

    paired_ends = {split, project.related(split)}
    profiles = {}
    for itinerary in project.dests:
        if not paired_ends.intersection(project.dest_view(itinerary)[0]):
            continue
        name = ident(itinerary)[0]
        try:
            profiles[name] = route_trace(project, itinerary)
        except ValueError as error:
            raise ValueError(f'Cannot prove the native station profile of affected Itinerary {name}: {error}') from error
    need(profiles, 'A station-area split requires a saved Itinerary to prove its complete stopping profile')
    return profiles


def _new_signal(project, root, end, document, operation):
    name = operation['signal_name']
    need(operation['main_role'] == 'block' and type(name) is str and bool(name.strip()),
         'A local Route split needs a named block signal')
    need(all(writer.string(item.contents[13].value).casefold() != name.casefold()
             for item in project.models[document] if writer.kind(item) == 'OTSignalModel' and item.contents[13].value),
         'A Signal with this name already exists on the reviewed worksheet')
    identifier = max(project.byid[document]) + 1
    need(identifier < 2 ** 31, 'The native Signal model ID space is exhausted')
    signal = main_signal_model(end, name=name, model_id=identifier, placement=operation['placement'],
        sight_m=operation['sight_m'], delay_s=operation['delay_s'], show_symbol=operation['show_symbol'],
        show_icon=operation['show_icon'])
    signal.contents[8].values[1] = ROLES['block']
    collection = root.contents[2].value
    return signal, collection


def _prepare_paths(project, original_route, owner, dependencies, continued, target_document, courses, counts):
    grouped = defaultdict(list)
    for document, path, index, row in dependencies:
        grouped[id(path)].append((document, path, index, row))
    need(grouped, 'At least one saved Path must use the selected original Route')
    edits = []
    for found in grouped.values():
        need(len(found) == 1, 'A dependent Path repeats the selected Route')
        document, path, index, previous = found[0]
        array = path.contents[4].value
        values = path_functions.mutable_array(array)
        references = project.path_view(path)[1]
        need(counts[document][id(array)] == 1 and len(values) == len(references) and values[index] is previous,
             'The affected Path needs an unshared exact Route-reference array')
        identity = {'document': document, **ref(path)}
        _incident_bindings(courses, project, identity)
        need(references[index] == (owner[0], ref(original_route)), 'The dependent Path does not resolve the reviewed Route')
        key = 'path', project.owners[id(path)], ident(path)
        values = [*values[:index + 1], inf(continued), *values[index + 1:]]
        references = [*references[:index + 1], (target_document, ref(continued)), *references[index + 1:]]
        edits.append((key, array, values, references))
    return edits


def _affected_itineraries(project, affected_paths, course_items):
    covered = {(owner[0], identity) for _, owner, identity in affected_paths}
    labels = sorted(ident(dest)[0] for dest in project.dests
                    if any((doc, (row['name'], row['array_id'], row['start_id'])) in covered
                           for doc, row in project.dest_view(dest)[1]))
    running = sorted(item['course_id'] for item in map(course_record, course_items)
                     if item['enabled'] and any(name in labels for name in item['itineraries']))
    return labels, running


def _saved_part(project, route):
    return {'identity': ident(route), 'nodes': [project.key(item) for item in path_functions.mutable_array(route.contents[0].value)],
            'continuation_index': route.contents[5].values[4], 'profile': _route_profile(route)}


def _without_overlap(part):
    return {**part, 'profile': {**part['profile'], 'overlap': ['', -1]}}


def _without_occupied_entry(part):
    return {**part, 'profile': {**part['profile'], 'occupied_entry': list(ORDINARY_ENTRY),
                                'allow_occupied_entry': False, 'occupied_entry_use_speed': False,
                                'occupied_entry_use_time': False, 'occupied_entry_speed_kmh': ORDINARY_ENTRY[1],
                                'occupied_entry_wait_s': ORDINARY_ENTRY[2]}}


def _with_slow_zone(part, section, document, *, receiving=False):
    bounds = section['raw_zone_anchors'][document]
    return {**part, 'profile': {
        **part['profile'],
        'route_flags': 2 if section['head_only'] and not receiving else 0,
        'slow_speed_only_for_head': section['head_only'] and not receiving,
        'slow_speed_zone_end_ids': [key[1] for key in bounds] if all(bounds) else None,
        'signal_aspects': [] if receiving else [section['aspect_code']],
    }}


def _with_updated_timing(part, route, review):
    groups = timing_groups(route, review)
    profile = {'timing': [*groups[5][:4], groups[5][5]], 'approach': groups[8], 'distance_flags': groups[10]}
    return {**part, 'profile': {**part['profile'], **profile}}


def _set_slow_zone(changes, project, route, document, section, counts, *, groups=None, receiving=False):
    root = project.roots[document]
    pointers = raw_zone_pointers(project, section, document)
    anchors = route.contents[12]
    updated = [anchors.values[0] if groups is None else groups, *pointers]
    if updated != anchors.values:
        changes.group(root, anchors, updated)
    if receiving:
        return
    flags = 2 if section['head_only'] else 0
    if route.contents[11].value != flags:
        changes.group(root, route.contents[11], [flags])
    holder = route.contents[4].value
    indication, = route_factory.wrapper(holder, 'OTSigIndList')
    if indication.contents[0].value != section['aspect_code']:
        need(all(counts[id(obj)] == 1 for obj in (holder, holder.contents[0].value, indication)),
             'The original Route aspect must have exclusive saved ownership')
        changes.group(root, indication.contents[0], [section['aspect_code']])


def _check_cross_readback(saved, owner, target_document, original, original_record, receiver_state, end_ids, releases):
    seed = saved.owned(owner, 'OTRoute', original['identity'])
    receiver = saved.owned((target_document, original_record['target_connector']), 'OTRoute', original['identity'])
    need(_saved_part(saved, seed) == original, 'The sending primary Route changed during the receiving split')
    records = [row for row in saved.continuations if row['source_document'] == owner[0] and row['route'] == ref(seed)]
    needed_record = {key: value for key, value in original_record.items() if key != 'fragment_object'}
    needed_record['remote_end_ids'] = end_ids
    need(len(records) == 1 and {key: value for key, value in records[0].items() if key != 'fragment_object'} == needed_record,
         'The receiving split changed the original continuation owner, connector or save index')
    expected = {**receiver_state, 'nodes': [(target_document, number) for number in end_ids],
                'profile': {**receiver_state['profile'], 'release_group_end_ids': releases}}
    need(_saved_part(saved, receiver) == expected, 'The shortened receiving fragment differs after native readback')


def _check_sending_readback(saved, owner, split, original, crossing, receiver_before, continuation, prefix, releases):
    old_route = saved.owned(owner, 'OTRoute', original['identity'])
    expected_old = {**original, 'nodes': prefix, 'continuation_index': -1,
                    'profile': {**original['profile'], 'release_group_end_ids': releases}}
    need(_saved_part(saved, old_route) == expected_old, 'The shortened sending Route differs after native readback')
    new_identity = continuation['identity']
    new_main = saved.owned(split, 'OTRoute', new_identity)
    receiver = saved.owned((crossing['target_document'], crossing['target_connector']), 'OTRoute', new_identity)
    need(_saved_part(saved, new_main) == continuation
         and _saved_part(saved, receiver) == {**receiver_before, 'identity': new_identity},
         'The new sending Route or rebound receiving fragment differs after native readback')
    selected_refs = (ref(old_route), ref(new_main))
    records = [row for row in saved.continuations if row['source_document'] == owner[0] and row['route'] in selected_refs]
    expected_record = {**crossing, 'route': ref(new_main), 'local_end_ids': [number for _, number in continuation['nodes']],
                       'saved_continuation_index': continuation['continuation_index'], 'fragment_object': id(receiver)}
    need(records == [expected_record], 'The original connector pair does not uniquely host the new continuation')

def insert_signal_in_saved_route(documents, document_paths, dest_blob, document, operation, courses, *,
                                 operating_banks=None, run_bytes=None):
    """Return native worksheet changes and any explicitly reviewed Incident catalogue update."""
    need(type(courses) is bytes, 'A frozen native CourseList is required for Route and Signal incident checks')
    course_root, _ = writer.load_next_compatible(courses)
    items = catalogs.course_items(course_root)
    plan = operation['split_route']
    requested = plan['route']
    need(requested['document'] in documents and document in documents and type(plan['reserve_with_previous']) is bool,
         'Review the exact native Route documents and an explicit downstream reservation choice')
    continued_name = plan['continued_name']
    need(type(continued_name) is str and bool(continued_name.strip()), 'The downstream Route needs a distinct name')
    project = project_from(documents, document_paths, dest_blob)
    root = project.roots[document]
    reference = {key: requested[key] for key in ('name', 'array_id', 'start_id')}
    owner, split = (requested['document'], reference['start_id']), (document, operation['end_id'])
    all_counts = {name: incoming_counts(graph) for name, graph in project.roots.items()}
    counts = all_counts[document]
    overlap_review = plan.get('terminal_overlap')
    entry_review = plan.get('occupied_entry')
    slow_review = plan.get('slow_zone')
    preceding_zone_review = plan.get('preceding_fixed_slow_zone')
    timing_review = plan.get('timing')
    delayed_retry = False if timing_review is None else timing_review.get('allow_delayed_prefix_retry', False)
    parallel_overlap = False if timing_review is None else timing_review.get('parallel_overlap_preparation', False)
    entry_approach = False if timing_review is None else timing_review.get('preserve_occupied_terminal_approach', False)
    need(not delayed_retry or slow_review is not None,
         'Delayed prefix retry review requires a saved slow-zone and timing split')
    protections = {name for name, review in (('terminal_overlap', overlap_review), ('occupied_entry', entry_review),
                                             ('slow_zone', slow_review), ('timing', timing_review))
                   if review is not None}
    need(len(protections) <= 1 or protections in ({'slow_zone', 'timing'}, {'terminal_overlap', 'timing'},
                                                  {'slow_zone', 'terminal_overlap'}, {'occupied_entry', 'timing'}),
         'Select one protection or a supported pair of protections when splitting an existing Route')
    need(not parallel_overlap or (protections == {'terminal_overlap', 'timing'} and not delayed_retry
         and type(operating_banks) is dict and operating_banks.get('courses') == courses),
         'Parallel overlap preparation needs only the terminal overlap, timing and matching operating archives')
    need(not entry_approach or protections == {'occupied_entry', 'timing'},
         'The reviewed terminal approach requires the occupied-entry timing combination')
    need(preceding_zone_review is None or (entry_review is not None and slow_review is None and overlap_review is None
         and not plan['reserve_with_previous']),
         'A fixed slow predecessor needs a distinct independently reserved occupied entry')
    incident_reviews = plan.get('route_span_incident_rebindings', [])
    route_speed_review = plan.get('route_speed_incident_to_path')
    need(not incident_reviews or (not protections and plan['reserve_with_previous']),
         'Preserving a Route-span Incident requires ordinary synchronized reservation and default Route protection')
    need(not incident_reviews or operation['delay_s'] == 0,
         'Preserving a Route-span Incident requires no additional relay delay')
    need(route_speed_review is None or (not incident_reviews and not protections
         and plan['reserve_with_previous'] and operation['delay_s'] == 0),
         'Preserving an entire Route-speed Incident requires ordinary synchronized reservation and no other protection')
    expected_entry = ORDINARY_ENTRY
    if entry_review is not None:
        need(overlap_review is None and not plan['reserve_with_previous'],
             'Occupied entry requires independent reservation and cannot include terminal overlap')
        need(type(operating_banks) is dict and operating_banks.get('courses') == courses,
             'Use the same bound CourseList for incident review and the occupied-entry join')
        expected_entry = occupied_entry_values(entry_review)
    route, fragment, crossing, models = _select_parts(
        project, owner, document, reference, all_counts, reviewed_overlap=overlap_review is not None,
        expected_entry=expected_entry, slow_review=slow_review,
        timing_review=reviewed_route_timing(timing_review) if timing_review is not None else None)
    splits_sending = crossing is not None and document == owner[0]
    need(entry_review is None or not splits_sending,
         'Occupied entry must become a local suffix on the terminal worksheet')
    sequence = project.route_view(route)
    need(len(sequence) >= 3 and sequence.count(split) == 1 and split in sequence[1:-1]
         and split in [project.key(node) for node in models[:-1]],
         'The free split End must be strictly internal to the original movement and have a downstream local Edge')
    index = sequence.index(split)
    edge_sequence = [project.edge_between(a, b)[1] for a, b in zip(sequence, sequence[1:])]
    need(edge_sequence[:index] == plan['expected_upstream_edge_ids']
         and edge_sequence[index:] == plan['expected_downstream_edge_ids'],
         'The two ordered directed Edge sequences differ from the reviewed Route split')
    overlap = None
    if overlap_review is not None:
        need(plan['reserve_with_previous'], 'Preserving a terminal overlap requires synchronized downstream reservation')
        overlap = split_terminal_overlap(project, route, overlap_review, sequence)
        overlap_binding = overlap_reference(route)
    entry = None if entry_review is None else verify_occupied_signal_split(
        project, route, sequence, split, entry_review, operating_banks, run_bytes)
    preceding_zone = None if preceding_zone_review is None else audit_preceding_slow_occupied_split(
        project, [route], split, entry, preceding_zone_review, operating_banks)
    slow = None if slow_review is None else review_slow_zone_split(project, route, fragment, sequence, split, slow_review)
    timing_plan = None if timing_review is None else plan_timing_split(
        project, route, fragment, sequence, index, timing_review, reserve_with_previous=plan['reserve_with_previous'])
    slow_timing = None if slow is None or timing_plan is None else plan_slow_zone_timing(
        slow, timing_plan, reserve_with_previous=plan['reserve_with_previous'],
        allow_delayed_prefix_retry=delayed_retry, project=project, route=route, sequence=sequence,
        course_items=items, run_bytes=run_bytes)
    parallel_plan = None
    if parallel_overlap:
        timing_plan, parallel_plan = plan_parallel_overlap_preparation(
            project, route, sequence, timing_plan, overlap, course_root, operating_banks, run_bytes,
            reserve_with_previous=plan['reserve_with_previous'], signal_delay_s=operation['delay_s'])
    overlap_timing = None if parallel_overlap or overlap is None or timing_plan is None else plan_overlap_release_delay(
        overlap, timing_plan, reserve_with_previous=plan['reserve_with_previous'])
    occupied_timing = None if entry is None or timing_plan is None else plan_occupied_release_delay(
        entry, timing_plan, reserve_with_previous=plan['reserve_with_previous'],
        preserve_terminal_approach=entry_approach)
    slow_overlap = None if slow is None or overlap is None else plan_slow_zone_overlap(
        project, route, sequence, split, slow, overlap, reserve_with_previous=plan['reserve_with_previous'])
    end, elements, station = _plain_boundary(project, split, sequence, index)
    station_profiles = None if station is None else _station_profiles(project, split)
    terminals = [project.model(key).contents[11].value for key in (sequence[0], sequence[-1])]
    need(all(main is not None for main in terminals),
         'Both original Route terminal signals must remain present')
    before = _movement_manifest(project)
    original_key = 'route', owner, ident(route)
    need({key for key, (nodes, _, _) in before.items() if split in nodes and key[0] in ('route', 'shunting')}
         == {original_key}, 'Another saved Route or Shunting also uses the reviewed signal direction')

    dependencies = _dependent_paths(project, owner, reference, route, all_counts)
    if fragment is not None:
        need(all_counts[owner[0]][id(route)] == 2 + sum(position == 0 for _, _, position, _ in dependencies),
             'The sending primary Route has unknown direct saved owners')
    zone_owners = tuple(part for part in (route, fragment) if part is not None) if slow is not None else ()
    path_functions.guard_counter_references(root, end, reviewed_zone_owners=zone_owners)
    high = end.contents[19].value
    need(type(high) is int and -1 <= high < 2 ** 31 - 1, 'The downstream native Route ID space is exhausted')
    new_id = high + 1
    _guard_identity(project, owner, reference, dependencies, continued_name, split, new_id)
    incident_keys = {(owner[0].casefold(), owner[1], reference['array_id']), (document.casefold(), split[1], new_id)}
    if crossing is not None:
        receiver_document = crossing['target_document']
        incident_keys.update((receiver_document.casefold(), related, reference['array_id'])
                             for related in (owner[1], crossing['target_connector']))
        if splits_sending:
            receiver_owner = receiver_document, crossing['target_connector']
            existing = path_functions.mutable_array(_owner_array(project, receiver_owner, all_counts))
            need(all(ident(item)[1:] != (new_id, split[1]) for item in existing),
                 'The receiving connector already has the new Route ID and start End')
            _guard_identity(project, (receiver_document, owner[1]), reference, dependencies,
                            continued_name, (receiver_document, split[1]), new_id)
            incident_keys.update((receiver_document.casefold(), related, new_id)
                                 for related in (split[1], crossing['target_connector']))
    _guard_incidents(courses, incident_keys if route_speed_review is None else (),
                     () if incident_reviews else {reference['name'], continued_name})

    signal, collection = _new_signal(project, root, end, document, operation)
    if entry is not None:
        signal.contents[9].values[2] |= 1
    if slow is not None:
        extend_relay_indications(signal, end, slow['downstream'])
    need(counts[id(collection)] == 1, 'The source worksheet graphic collection is shared')
    _guard_signal_incidents(courses, [*[project.key(item) for item in terminals], (document, model_id(signal))])
    local_index = models.index(end)
    upstream, downstream = models[:local_index + 1], models[local_index:]
    if fragment is None:
        cut = route
        prefix_groups, suffix_groups = [upstream[0], upstream[-1]], [downstream[0], downstream[-1]]
        if timing_plan is not None:
            anchors = path_functions.mutable_array(route.contents[12].values[0])
            prefix_groups = [*[item for item in anchors if item in upstream[:-1]], end]
            suffix_groups = [end, *[item for item in anchors if item in downstream[1:]]]
    else:
        cut = route if splits_sending else fragment
        sender_before = original_sender = _saved_part(project, route)
        original_receiver = _saved_part(project, fragment)
        anchors = path_functions.mutable_array(cut.contents[12].values[0])
        if splits_sending:
            prefix_groups = [*[item for item in anchors if item in upstream[:-1]], end]
            suffix_groups = [end, *[item for item in anchors if item in downstream[1:]]]
        else:
            prefix_groups = [item for item in anchors if item in upstream]
            suffix_groups = [end, *[item for item in anchors if item in downstream[1:-1]], downstream[-1]]
        if overlap is not None:
            original_sender = _without_overlap(original_sender)
        if entry is not None:
            original_sender = _without_occupied_entry(original_sender)
            original_receiver = _without_occupied_entry(original_receiver)
        if slow is not None:
            original_sender = _with_slow_zone(original_sender, slow['upstream'], owner[0])
            fragment_section = slow['downstream' if splits_sending else 'upstream']
            original_receiver = _with_slow_zone(original_receiver, fragment_section, receiver_document, receiving=True)
        if timing_plan is not None:
            original_sender = _with_updated_timing(original_sender, route, timing_plan['upstream'])
    continuation_index = len(downstream) if splits_sending else -1
    continuation = native_route(continued_name, new_id, split[1], downstream, continuation_index)
    continuation.contents[11].value = int(plan['reserve_with_previous'])
    continuation.contents[12].values[0] = path_functions.array_like(continuation.contents[12].values[0], suffix_groups)
    if slow is not None:
        section = slow['downstream']
        continuation.contents[12].values[1:] = raw_zone_pointers(project, section, document)
        continuation.contents[11].value |= 2 if section['head_only'] else 0
        downstream_aspect, = route_factory.wrapper(continuation.contents[4].value, 'OTSigIndList')
        downstream_aspect.contents[0].value = section['aspect_code']
    path_edits = _prepare_paths(project, route, owner, dependencies, continuation, document, courses, all_counts)
    labels, running = _affected_itineraries(project, [edit[0] for edit in path_edits], items)
    downstream_key = 'route', split, ident(continuation)
    expected = dict(before)
    for key, nodes in ((original_key, sequence[:index + 1]), (downstream_key, sequence[index:])):
        expected[key] = nodes, None, _movement_geometry(project, nodes, True)

    fingerprints = {name: writer.fingerprint(graph) for name, graph in project.roots.items()}
    changes = Changes()
    if timing_plan is not None:
        for slot, values in timing_groups(continuation, timing_plan['downstream']).items():
            continuation.contents[slot].values[:] = values
        for slot, values in timing_groups(route, timing_plan['upstream']).items():
            if route.contents[slot].values != values:
                changes.group(project.roots[owner[0]], route.contents[slot], values)
    if overlap is not None:
        set_overlap_reference(continuation, overlap_binding)
        set_overlap_reference(route, ('', -1), changes=changes, root=project.roots[owner[0]])
    if entry is not None:
        continuation.contents[6].values[:] = entry['values']
        changes.group(project.roots[owner[0]], route.contents[6], list(ORDINARY_ENTRY))
        if fragment is not None:
            changes.group(root, fragment.contents[6], list(ORDINARY_ENTRY))
    changes.group(root, end.contents[11], [signal])
    changes.contents(root, collection, [*project.models[document], signal])
    changes.group(root, cut.contents[0], [path_functions.array_like(cut.contents[0].value, upstream)])
    prefix_array = path_functions.array_like(cut.contents[12].values[0], prefix_groups)
    if slow is None:
        changes.group(root, cut.contents[12], [prefix_array, None, None])
    else:
        _set_slow_zone(changes, project, route, owner[0], slow['upstream'], all_counts[owner[0]],
                       groups=prefix_array if cut is route else None)
        if fragment is not None:
            _set_slow_zone(changes, project, fragment, receiver_document, fragment_section, all_counts[receiver_document],
                           groups=prefix_array if cut is fragment else None, receiving=True)
    if splits_sending:
        timing = list(route.contents[5].values)
        timing[4] = -1
        changes.group(root, route.contents[5], timing)
        receiver_root = project.roots[receiver_document]
        changes.group(receiver_root, fragment.contents[1], [path_functions.fresh_string(fragment.contents[1].value, continued_name)])
        changes.group(receiver_root, fragment.contents[2], [new_id, split[1]])
    changes.contents(root, _owner_array(project, split, all_counts), [continuation])
    changes.group(root, end.contents[19], [new_id])
    for key, array, values, references in path_edits:
        path_document = key[1][0]
        changes.contents(project.roots[path_document], array, values)
        nodes, _, geometry = before[key]
        expected[key] = nodes, references, geometry

    output = {name: writer.dump_verified(graph, project.versions[name]) for name, graph in project.roots.items()
              if id(graph) in changes.touched}
    saved = project_from({**documents, **output}, document_paths, dest_blob)
    saved_end = saved.model(split)
    saved_signal = saved.model((document, model_id(signal)))
    validate_generated_signal_alignment(saved_signal)
    indicators = route_factory.wrapper(saved_signal.contents[10].value, 'OTSigIndList')
    saved_continuation = saved.owned(split, 'OTRoute', ident(continuation))
    saved_upstream = saved.owned(owner, 'OTRoute', ident(route))
    overlap_receipt = {}
    if overlap is not None:
        complete_movement = [*saved.route_view(saved_upstream), *saved.route_view(saved_continuation)[1:]]
        need(overlap_reference(saved_upstream) == ('', -1)
             and overlap_reference(saved_continuation) == overlap_binding
             and saved_continuation.contents[11].value & 1
             and complete_movement == sequence
             and split_terminal_overlap(saved, saved_continuation, overlap_review, complete_movement) == overlap,
             'The terminal overlap transfer or its complete locking profile differs in the native cold read')
        overlap_receipt['terminal_overlap_transfer'] = {
            **overlap, 'stored_reference': list(overlap_binding),
            'upstream_reference_cleared': True, 'synchronized_reservation': True,
        }
    entry_receipt = {}
    if entry is not None:
        complete_movement = [*saved.route_view(saved_upstream), *saved.route_view(saved_continuation)[1:]]
        new_entry = verify_occupied_signal_split(
            saved, saved_continuation, complete_movement, split, entry_review, operating_banks, run_bytes)
        old_signal = saved.model(owner).contents[11].value
        need(complete_movement == sequence and tuple(saved_upstream.contents[6].values) == ORDINARY_ENTRY
             and old_signal.contents[0].value == entry['signal_id'] and old_signal.contents[9].values == entry['signal_flags']
             and new_entry == {**entry, 'signal_id': model_id(signal), 'signal_flags': signal.contents[9].values}
             and saved_continuation.contents[11].value == 0,
             'The occupied-entry handoff or physical join berth differs in the native cold read')
        entry_receipt['occupied_entry_transfer'] = {**new_entry, 'original_signal_id': entry['signal_id'],
                                                  'upstream_reset': True, 'independent_reservation': True}
        if preceding_zone is not None:
            entry_receipt['preceding_fixed_slow_zone'] = check_preceding_slow_occupied_split(
                saved, saved_upstream, saved_continuation, split, new_entry,
                preceding_zone_review, operating_banks, preceding_zone)
    slow_receipt = {}
    if slow is not None:
        upstream_zone = check_slow_section(saved, saved_upstream, slow['upstream'], reserve_with_previous=False,
                                           expected_signal_codes=slow['original_signal_aspect_codes'])
        downstream_zone = check_slow_section(saved, saved_continuation, slow['downstream'],
                                             reserve_with_previous=plan['reserve_with_previous'])
        rebuilt = [*saved.route_view(saved_upstream), *saved.route_view(saved_continuation)[1:]]
        need(upstream_zone + downstream_zone == slow['original_zone_edges'] and rebuilt == sequence,
             'The native readback changes the original routed slow-speed interval')
        slow_receipt['slow_zone_split'] = slow
    if slow_overlap is not None:
        slow_receipt['slow_zone_overlap_split'] = check_slow_zone_overlap(
            saved, saved_upstream, saved_continuation, split, slow_overlap, slow,
            overlap_receipt['terminal_overlap_transfer'])
    timing_receipt = {}
    if timing_plan is not None:
        groups = check_timing_split(saved, saved_upstream, saved_continuation, timing_plan)
        timing_receipt['timing_split'] = {**timing_plan, 'saved_release_group_starts': groups,
                                         'new_independent_route_terminal': True,
                                         'cut_already_a_group_anchor': split in timing_plan['original_release_group_starts']}
    if slow_timing is not None:
        delayed = slow_timing.get('delayed_prefix_reservation')
        if delayed is not None:
            need(delayed['itinerary'] in labels and running == [delayed['course_id']],
                 'The delayed prefix review does not match the complete saved Itinerary update')
            delayed['native_archive_readback_verified'] = True
        timing_receipt['slow_zone_timing_split'] = slow_timing
    if overlap_timing is not None:
        timing_receipt['overlap_release_delay_split'] = check_overlap_release_delay(
            overlap_timing, overlap_receipt['terminal_overlap_transfer'], timing_receipt['timing_split'])
    if parallel_plan is not None:
        timing_receipt['parallel_overlap_preparation'] = check_parallel_overlap_preparation(
            saved, saved_upstream, saved_continuation, timing_receipt['timing_split'],
            overlap_receipt['terminal_overlap_transfer'], parallel_plan, labels, running)
    if occupied_timing is not None:
        timing_receipt['occupied_entry_release_delay_split'] = check_occupied_release_delay(
            occupied_timing, entry_receipt['occupied_entry_transfer'], timing_receipt['timing_split'])
    routes_to_check = [(saved_continuation, downstream, suffix_groups, plan['reserve_with_previous'])]
    crossed = {}
    downstream_release = list(map(model_id, suffix_groups))
    if splits_sending:
        prefix_release = list(map(model_id, prefix_groups))
        _check_sending_readback(saved, owner, split, original_sender, crossing, original_receiver,
                                _saved_part(project, continuation), sequence[:index + 1], prefix_release)
        routes_to_check = [(saved_upstream, upstream, prefix_groups, False)]
        receiver_release = original_receiver['profile']['release_group_end_ids']
        crossed['sending_fragment'] = {'previous_continuation_index': crossing['saved_continuation_index'],
            'upstream_continuation_index': -1, 'downstream_continuation_index': continuation_index,
            'source_connector_end_id': crossing['source_connector'],
            'receiving_document': receiver_document, 'receiving_connector_end_id': crossing['target_connector'],
            'receiving_end_ids': crossing['remote_end_ids'], 'receiving_release_group_end_ids': receiver_release,
            'previous_receiving_route': reference, 'replacement_receiving_route': ref(continuation)}
        downstream_release = [*downstream_release, *receiver_release]
    elif fragment is None:
        routes_to_check.append((saved_upstream, upstream, prefix_groups, False))
        prefix_release = list(map(model_id, prefix_groups))
    else:
        edited_nodes = list(map(model_id, upstream))
        edited_releases = list(map(model_id, prefix_groups))
        _check_cross_readback(saved, owner, document, original_sender, crossing, original_receiver, edited_nodes, edited_releases)
        prefix_release = [*original_sender['profile']['release_group_end_ids'], *edited_releases]
        crossed['receiving_fragment'] = {'document': document, 'owner_end_id': crossing['target_connector'],
            'source_connector_end_id': crossing['source_connector'], 'continuation_index': crossing['saved_continuation_index'],
            'old_end_ids': crossing['remote_end_ids'], 'new_end_ids': edited_nodes,
            'previous_release_group_end_ids': original_receiver['profile']['release_group_end_ids'],
            'remaining_release_group_end_ids': edited_releases,
            'sending_primary_preserved': _saved_part(saved, saved_upstream) == sender_before and (
                slow is None or slow['upstream']['raw_zone_anchors'][owner[0]]
                == list(slow['original_raw_zone_anchors'][owner[0]]))}
    for obj, values, groups, reserve in routes_to_check:
        ids = [model_id(item) for item in values]
        zone = None if slow is None else slow['downstream' if obj is saved_continuation else 'upstream']
        has_zone = zone is not None and zone['aspect_code'] != 0
        route_factory.validate_chain(saved.roots[document], obj, ids,
                                     allow_terminal_overlap=overlap is not None and obj is saved_continuation,
                                     allow_speed_occupied_entry=expected_entry[0] == 3 and obj is saved_continuation,
                                     allow_wait_occupied_entry=expected_entry[0] == 7 and obj is saved_continuation,
                                     allow_slow_zone=has_zone)
        release = _protection_values(obj, _route_shape(obj))['release_group_end_ids']
        expected_flags = int(reserve) | (2 if has_zone and zone['head_only'] else 0)
        need(release == list(map(model_id, groups)) and obj.contents[11].value == expected_flags,
             'The saved Route does not match the reviewed release bounds or reservation mode')
    expected_signal_aspects = [0]
    if slow is not None and slow['downstream']['aspect_code']:
        expected_signal_aspects.append(slow['downstream']['aspect_code'])
    need(saved_end.contents[11].value is saved_signal and saved_signal.contents[7].value is saved_end
         and saved_signal.contents[8].values == signal.contents[8].values
         and [indicator.contents[0].value for indicator in indicators] == expected_signal_aspects
         and all(indicator.contents[1].value is saved_end for indicator in indicators)
         and saved_end.contents[19].value == new_id and _movement_manifest(saved) == expected,
         'The new Signal, Route split or complete movements differ in the native cold read')
    station_receipt = {}
    if station_profiles is not None:
        fresh_profiles = _station_profiles(saved, split)
        need(station_profiles.keys() == fresh_profiles.keys(), 'The station area lost an affected saved Itinerary')
        for name, profile in station_profiles.items():
            need(fresh_profiles[name] == profile,
                 f'The new block changes a native station visit, halt marker or stopping profile in Itinerary {name}')
        station_receipt['station_berths_preserved'] = {
            'station_id': model_id(station), 'station_sign': writer.string(station.contents[7].value),
            'itineraries': sorted(station_profiles), 'both_directions_checked': True,
        }
    changes.restore()
    need(all(writer.fingerprint(graph) == fingerprints[name] for name, graph in project.roots.items()),
         'The native update touched a field outside the audited signal and movement edits')
    incident_receipt = {}
    if incident_reviews:
        adjusted, incident_receipt['route_span_incident_rebindings'] = rebind_signal_route_incidents(
            courses, project, saved, incident_reviews, sequence=sequence, split=split,
            old_name=reference['name'], suffix_name=continued_name)
        output['$course_catalog'] = adjusted
    if route_speed_review is not None:
        adjusted, incident_receipt['route_speed_incident_to_path'] = preserve_route_speed_incident(
            courses, project, saved, route_speed_review,
            upstream={'document': owner[0], **reference},
            downstream={'document': document, **ref(saved_continuation)},
            incident_keys=incident_keys,
        )
        output['$course_catalog'] = adjusted
    return output, {'action': operation['action'], 'document': document, 'end_id': split[1],
        'signal_id': model_id(signal), 'signal_name': operation['signal_name'], 'main_role': operation['main_role'],
        'upstream_route': {'document': owner[0], **ref(route)}, 'downstream_route': {'document': document, **ref(continuation)},
        'upstream_edge_ids': edge_sequence[:index], 'downstream_edge_ids': edge_sequence[index:],
        'release_group_end_ids': {'upstream': prefix_release, 'downstream': downstream_release},
        'adjacent_safety_elements': elements, 'reserve_with_previous': plan['reserve_with_previous'],
        'updated_paths': [{'document': key[1][0], **dict(zip(('name', 'array_id', 'start_id'), key[2], strict=True))}
                          for key, *_ in path_edits],
        'affected_itineraries': labels, 'active_courses': running, 'destination_catalog_unchanged': True,
        'native_movement_readback_verified': True, 'nonselected_graph_verified': True, 'native_execution_tested': False,
        **station_receipt, **crossed, **overlap_receipt, **entry_receipt, **slow_receipt, **timing_receipt, **incident_receipt}
