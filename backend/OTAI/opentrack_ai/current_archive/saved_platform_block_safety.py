"""Partition the one platform-wide native Safety Element at a new block boundary."""

from pathlib import PureWindowsPath

from . import path_functions, writer
from .multi_document.core import need
from .operating_plan_edit import text
from .path_lifecycle_tools import Changes
from .saved_crossing_incidents import track_incident_bindings
from .saved_document_insertion import _route_profile
from .saved_edge_exclusion import _links
from .saved_geometry import _movement_manifest, _selected_elements, _set_element_members, model_id, project_from
from .saved_halt_location import reviewed_platform


def _edge_members(project, document, edge_ids):
    return {model_id(project.model((document, edge)).contents[slot].value) for edge in edge_ids for slot in (7, 8)}


def _review_other_users(project, movements, document, edge_ids, arrival, courses):
    selected = set(edge_ids)
    local = {model_id(edge): edge for edge in project.models[document] if writer.kind(edge) == 'OTEdgeModel'}
    need(all(first not in selected and second not in selected for first, second in _links(local).items()),
         'An incoming or outgoing native Edge exclusion uses the reviewed platform block')
    need(all(PureWindowsPath(item['document']).name.casefold().removesuffix('.opentrack') != document.casefold()
             or selected.isdisjoint(item['edge_ids']) for item in track_incident_bindings(courses)),
         'A saved track-blockage Incident uses the reviewed platform block')
    source = ((arrival['document'], arrival['start_id']), (arrival['name'], arrival['array_id'], arrival['start_id']))
    platform = [(document, edge) for edge in edge_ids]
    platform_set = set(platform)
    profiles = []
    for (kind, owner, identity), (nodes, _, _) in movements.items():
        traversed = [project.edge_between(a, b) for a, b in zip(nodes, nodes[1:])]
        index = [i for i, edge in enumerate(traversed) if edge in platform_set]
        if not index:
            continue
        span = traversed[index[0]:index[-1] + 1]
        need(kind != 'shunting' and span in (platform, platform[::-1]),
             f'A saved {kind} {identity[0]} uses only part of the platform block, repeats it or uses it for shunting')
        if kind == 'route' and (owner, identity) != source:
            route = project.owned(owner, 'OTRoute', identity)
            records = [(owner, route)]
            records.extend(((row['target_document'], row['target_connector']),
                            project.owned((row['target_document'], row['target_connector']), 'OTRoute', identity))
                           for row in project.continuations if row['source_document'] == owner[0]
                           and row['local_end_ids'][0] == owner[1] and row['route']['name'] == identity[0])
            for route_owner, item in records:
                profile = _route_profile(item)
                need(profile['overlap'] == ['', -1], 'Another platform Route uses a terminal overlap')
                profiles.append({'owner': route_owner, 'identity': identity, 'profile': profile})
    return profiles


def verify_platform_block_safety(project, document, receipt):
    group_ids = (receipt['upstream_element_id'], receipt['downstream_element_id'])
    for group_id, side in zip(group_ids, ('upstream', 'downstream'), strict=True):
        (group, members), = _selected_elements(project, document, [group_id])
        edges = receipt[f'{side}_edge_ids']
        need(sorted(map(model_id, members)) == receipt[f'{side}_member_end_ids']
             and _edge_members(project, document, edges) == set(map(model_id, members))
             and all(end.contents[7].value is group for end in members),
             'One native station block Safety Element has different members after cold read')
    for row in receipt['other_route_profiles']:
        route = project.owned(row['owner'], 'OTRoute', row['identity'])
        need(_route_profile(route) == row['profile'], 'Another platform Route has different saved locking or release settings')


def partition_platform_block_safety(project, documents, paths, dest, document, station, operation, courses):
    halt, split, safety = (operation[key] for key in ('halt_relocation', 'split_route', 'vacated_block_safety'))
    need(operation['end_id'] == halt['from_end_id'] and split['route'] == halt['arrival_route']
         and halt['expected_stop_shift_m'] > 0 and split.get('reserve_with_previous') is True,
         'A station block at the vacated marker must split the reviewed arrival Route with linked reservation and a downstream halt')
    _, ends, edge_ids, positions, _ = reviewed_platform(project, document, station, halt, 4)
    end_ids = list(map(model_id, ends))
    old_end, new_end = halt['from_end_id'], halt['to_end_id']
    need(old_end in end_ids[1:-1] and new_end in end_ids[1:-1] and positions[new_end] > positions[old_end],
         'The replacement halt must be downstream of the vacated marker within the reviewed platform')
    boundary = end_ids.index(old_end)
    upstream_edges, downstream_edges = edge_ids[:boundary], edge_ids[boundary:]
    tracks = {text(project.model((document, edge)), 19) for edge in edge_ids}
    need(len(tracks) == 1 and '' not in tracks, 'The station block requires a contiguous platform on one named track')
    upstream_set = _edge_members(project, document, upstream_edges)
    downstream_set = _edge_members(project, document, downstream_edges)
    group_id = safety['element_id']
    (original, members), = _selected_elements(project, document, [group_id])
    member_ids = list(map(model_id, members))
    need(safety['expected_member_end_ids'] == sorted(member_ids)
         and safety['upstream_member_end_ids'] == sorted(upstream_set)
         and safety['downstream_member_end_ids'] == sorted(downstream_set)
         and upstream_set.isdisjoint(downstream_set) and upstream_set | downstream_set == set(member_ids),
         'The exact source Safety Element and ordered upstream/downstream membership must match the two platform edge spans')

    root = project.roots[document]
    source_fingerprint = writer.fingerprint(root)
    before_movements = _movement_manifest(project, check_safety=False)
    other_profiles = _review_other_users(project, before_movements, document, edge_ids, halt['arrival_route'], courses)
    new_id = max(project.byid[document]) + 1
    need(new_id < 2147483647, 'Graphic ID exhausted before allocating the new platform block and signal')
    new = path_functions.clone(original)
    new.contents[0].value = new_id
    collection = root.contents[2]
    upstream = [end for end in members if model_id(end) in upstream_set]
    downstream = [end for end in members if model_id(end) in downstream_set]
    changes = Changes()
    try:
        changes.group(root, new.contents[7], [path_functions.array_like(original.contents[7].value, downstream)])
        changes.group(root, original.contents[7], [path_functions.array_like(original.contents[7].value, upstream)])
        for end in downstream:
            changes.group(root, end.contents[7], [new])
        changes.group(root, collection, [path_functions.array_like(collection.value, [*project.models[document], new])])
        content = writer.dump_verified(root, project.versions[document])
    finally:
        changes.restore()
    need(writer.fingerprint(root) == source_fingerprint, 'Platform Safety Element staging changed the source graph')

    checked = project_from({**documents, document: content}, paths, dest)
    receipt = {
        'source_element_id': group_id, 'source_member_end_ids': sorted(member_ids),
        'upstream_element_id': group_id, 'upstream_edge_ids': upstream_edges,
        'upstream_member_end_ids': sorted(upstream_set), 'downstream_element_id': new_id,
        'downstream_edge_ids': downstream_edges, 'downstream_member_end_ids': sorted(downstream_set),
        'other_route_profiles': other_profiles,
    }
    verify_platform_block_safety(checked, document, receipt)
    need(_movement_manifest(checked, check_safety=False) == before_movements,
         'The station block Safety partition changed a saved movement, physical length or reference')
    checked_root = checked.roots[document]
    checked_original = checked.model((document, group_id))
    _set_element_members(checked_original, [checked.model((document, end)) for end in member_ids])
    checked_collection = checked_root.contents[2]
    checked_collection.value = path_functions.array_like(checked_collection.value, [
        model for model in checked.models[document] if model_id(model) != new_id])
    need(writer.fingerprint(checked_root) == source_fingerprint,
         'Reversing the cold-read platform Safety partition did not exactly restore the original worksheet')
    return content, {**receipt, 'exact_inverse_verified': True, 'unchanged_physical_movements': len(before_movements)}
