"""Author a native pre-service station with facing turnouts and same-main passing loops."""

from collections import defaultdict
from dataclasses import dataclass
from types import SimpleNamespace

from . import course_factories, writer
from .infrastructure_railml import railml_path as tag, railml_tracks, railml_tree
from .infrastructure_railml_cross_platform import open_project
from .infrastructure_railml_facilities import (
    KINDS, RAILML_SIGNAL_ROLES, RAILML_SIGNAL_TYPES, apply_facilities, check_rewrite_namespaces, checked_signal,
    fields, require, text, unique_nodes,
)
from .infrastructure_railml_project import _merge_catalog
from .infrastructure_railml_rebuild import _engineering, _join_worksheets, _metres
from .pre_service_project import validate_pre_service_project
from .tools import sha
from .zero_generation import native_signal_routes as native, topology
from .zero_generation.empty_project import build_empty_project, worksheet_header_fingerprint


@dataclass(frozen=True)
class Partition:
    document: str
    low: int
    high: int


@dataclass(frozen=True)
class Turnout:
    identity: str
    main_track: str
    position: int
    branch_track: str
    branch_position: int
    orientation: str


def _railml_topology(raw):
    root = railml_tree(raw)
    check_rewrite_namespaces(root)
    require(all(node.tag in (tag('infrastructure'), tag('infrastructureVisualizations')) for node in root),
            'Branched station rebuilding accepts infrastructure and its schematic visualizations')
    infra, source_tracks = railml_tracks(root)
    require(all(node.tag in tuple(tag(name) for name in (
        'infraAttrGroups', 'tracks', 'trackGroups', 'operationControlPoints',
    )) for node in infra), 'The RailML infrastructure includes objects outside branched station rebuilding')
    tracks = unique_nodes(source_tracks)
    extents, branches, turnouts = {}, {}, {}
    locations = set()
    for track_id, track in tracks.items():
        fields(track, set(), (tag('trackTopology'), tag('trackElements'), tag('ocsElements')))
        require(all(node.tag in (tag('trackTopology'), tag('trackElements'), tag('ocsElements')) for node in track),
                'The RailML track includes objects outside branched station rebuilding')
        structure, = track.findall(tag('trackTopology'))
        require(all(node.tag in tuple(tag(name) for name in (
            'trackBegin', 'trackEnd', 'crossSections', 'connections',
        )) for node in structure), 'Unrecognized RailML track topology in branched station rebuilding')
        begin, = structure.findall(tag('trackBegin'))
        end, = structure.findall(tag('trackEnd'))
        fields(begin, set(), (tag('openEnd'), tag('connection')))
        fields(end, set(), (tag('openEnd'), tag('connection')))
        low, high = _metres(begin), _metres(end)
        require(low < high, 'Each rebuilt track needs positive measured length')
        extents[track_id] = low, high
        for endpoint, position, orientation in ((begin, low, 'outgoing'), (end, high, 'incoming')):
            require(len(endpoint) == 1 and endpoint[0].tag in (tag('openEnd'), tag('connection')) and not len(endpoint[0]),
                    'Each rebuilt track boundary needs an explicit open end or reciprocal turnout branch')
            connection = endpoint[0]
            if connection.tag == tag('openEnd'):
                continue
            fields(connection, {'ref'})
            identity = connection.get('id')
            require(identity and identity not in branches and connection.get('ref'), 'Unique RailML branch connection ID required')
            branches[identity] = (track_id, position, connection.get('ref'), orientation)
        for group in structure.findall(tag('connections')):
            require(all(node.tag == tag('switch') for node in group),
                    'Only turnout switches are supported inside the rebuilt track')
            for switch in group:
                fields(switch, set(), (tag('connection'),))
                position = _metres(switch)
                require(switch.get('id') and low < position < high and (track_id, position) not in locations,
                        'Each turnout needs a unique interior RailML position')
                require(len(switch) == 1, 'A turnout requires exactly one branching connection')
                link = switch[0]
                fields(link, {'ref', 'orientation'})
                identity = link.get('id')
                orientation = link.get('orientation')
                require(identity and identity not in turnouts and link.get('ref') and orientation in ('incoming', 'outgoing'),
                        'A turnout requires one unique incoming or outgoing RailML connection')
                turnouts[identity] = (switch.get('id'), track_id, position, link.get('ref'), orientation)
                locations.add((track_id, position))
    require(turnouts and len(branches) == len(turnouts) and not (branches.keys() & turnouts.keys()),
            'Rebuilding requires a reciprocal RailML turnout and branch topology')
    require(len({item[0] for item in turnouts.values()}) == len(turnouts), 'RailML turnout IDs must be unique')
    paired = []
    for link_id, (identity, track, position, target_id, orientation) in turnouts.items():
        match = branches.get(target_id)
        require(match is not None and match[2] == link_id, 'A RailML turnout and branch connection must be reciprocal')
        branch, branch_position, _, endpoint_orientation = match
        require(orientation == endpoint_orientation,
                'An outgoing RailML connection must pair with trackBegin and an incoming connection with trackEnd')
        paired.append(Turnout(identity, track, position, branch, branch_position, orientation))
    departures = {row.branch_track: row for row in paired if row.orientation == 'outgoing'}
    arrivals = [row for row in paired if row.orientation == 'incoming']
    for row in arrivals:
        previous = departures.get(row.branch_track)
        require(previous is not None and previous.main_track == row.main_track and previous.position < row.position,
                'A passing loop must leave and rejoin the same RailML main track at increasing positions')
    children = defaultdict(list)
    for row in departures.values():
        children[row.main_track].append(row.branch_track)
    roots = set(tracks) - departures.keys()
    require(len(roots) == 1, 'Rebuilt RailML tracks require one connected facing-turnout tree')
    order = list(roots)
    seen = set(order)
    for parent in order:
        for child in children[parent]:
            require(child not in seen, 'Rebuilt RailML tracks cannot contain turnout loops')
            seen.add(child)
            order.append(child)
    require(seen == set(tracks), 'Rebuilt RailML tracks require one connected facing-turnout tree')
    return infra, tracks, extents, paired, order


def _partition(worksheets, extents, turnouts):
    by_track = defaultdict(list)
    names = [sheet.document for sheet in worksheets]
    require(len({name.casefold() for name in names}) == len(names), 'Worksheet names must be distinct under case folding')
    for sheet in worksheets:
        require(len({row.track_id for row in sheet.tracks}) == len(sheet.tracks),
                'A worksheet may own only one contiguous partition of each RailML track')
        for row in sheet.tracks:
            low, high = row.start_position_m, row.end_position_m
            require(row.track_id in extents and low < high, 'Worksheet partitions need known tracks and positive measured lengths')
            by_track[row.track_id].append(Partition(sheet.document, low, high))
    require(by_track.keys() == extents.keys(), 'Worksheet partitions must include all represented RailML tracks')
    for track, parts in by_track.items():
        parts.sort(key=lambda part: part.low)
        low, high = extents[track]
        require(parts[0].low == low and parts[-1].high == high and
                all(left.high == right.low for left, right in zip(parts, parts[1:])),
                'Worksheet partitions must cover each complete RailML track once with no gaps or overlap')
    for row in turnouts:
        owners = [part.document for part in by_track[row.main_track] if part.low < row.position < part.high]
        outer = by_track[row.branch_track][0 if row.orientation == 'outgoing' else -1]
        require(owners == [outer.document],
                'A turnout must lie inside one worksheet containing its reciprocal branch endpoint')
    return names, by_track


def _facilities(infra, tracks, parts, stations, turnouts):
    inventory = {}
    for kind, path in KINDS.items():
        rows = {node: track_id for track_id, track in tracks.items() for node in track.findall(tag(*path, kind))}
        inventory[kind] = {identity: (rows[node], node) for identity, node in unique_nodes(rows).items()}
    ocps = unique_nodes(infra.findall(tag('operationControlPoints', 'ocp')))
    forbidden = {track: {part.high for part in slices[:-1]} for track, slices in parts.items()}
    for row in turnouts:
        forbidden[row.main_track].add(row.position)
        forbidden[row.branch_track].add(row.branch_position)
    selected = {kind: set() for kind in inventory}
    selected_ocps, station_docs = set(), {}
    document_stations, document_signals = defaultdict(list), defaultdict(list)
    positions = {track: set() for track in tracks}
    for binding in stations:
        track = binding.track_id
        track_id, cross = inventory['crossSection'].get(binding.cross_section_id, (None, None))
        require(track == track_id and binding.cross_section_id not in selected['crossSection'],
                'Review each station cross section once on its exact RailML track')
        selected['crossSection'].add(binding.cross_section_id)
        finish = _metres(cross)
        start = finish
        ocp = cross.get('ocpRef')
        require(ocp in ocps, 'Station cross section references an unresolved RailML OCP')
        selected_ocps.add(ocp)
        if binding.platform_edge_id is not None:
            track_id, platform = inventory['platformEdge'].get(binding.platform_edge_id, (None, None))
            require(track == track_id and binding.platform_edge_id not in selected['platformEdge'],
                    'Review each RailML platform once on its exact track')
            selected['platformEdge'].add(binding.platform_edge_id)
            start, length = _metres(platform), _metres(platform, 'length')
            require(length > 0 and (finish - start if binding.direction == 'up' else start - finish) == length,
                    'RailML platform extent must end at the exact directed cross section')
        if binding.stop_post_id is not None:
            track_id, _ = inventory['stopPost'].get(binding.stop_post_id, (None, None))
            require(track == track_id and binding.stop_post_id not in selected['stopPost'],
                    'Review each RailML stop post once on its exact track')
            selected['stopPost'].add(binding.stop_post_id)
        low, high = sorted((start, finish))
        owners = [part.document for part in parts[track] if part.low <= low <= high <= part.high]
        require(len(owners) == 1 and all(not low <= pos <= high for pos in forbidden[track]),
                'Each selected platform or point must stay on a single worksheet away from turnout or connector seams')
        document, = owners
        require(station_docs.setdefault(ocp, document) == document,
                'All platform references of a shared OCP must be on the same worksheet')
        document_stations[document].append(binding)
        positions[track].update((start, finish))
    for identity, (track, signal) in inventory['signal'].items():
        position = _metres(signal)
        owners = [part.document for part in parts[track] if part.low <= position <= part.high]
        require(len(owners) == 1 and position not in forbidden[track],
                'Each source signal must have one native End away from turnout and connector seams')
        document_signals[owners[0]].append(SimpleNamespace(signal_id=identity, fallback_sight_m=None))
        positions[track].add(position)
        selected['signal'].add(identity)
    require(all(selected[kind] == rows.keys() for kind, rows in inventory.items()) and selected_ocps == ocps.keys(),
            'The station request must bind the exact source facility and OCP inventory')
    for track in tracks.values():
        ocs, = track.findall(tag('ocsElements'))
        require(all(node.tag in (tag('signals'), tag('stopPosts')) for node in ocs),
                'Unrepresented RailML signalling objects are outside branched station rebuilding')
    return document_stations, document_signals, positions


def _worksheet_geometry(blank, shapes, profiles, track_names, lines, joins, track_order):
    vertices, keys, edges, descriptors = [], {}, [], []
    vertices_by_key = {}
    for index, track_id in enumerate(track_order):
        segments = profiles[track_id]
        positions = [segments[0].start, *(segment.end for segment in segments)]
        start_anchor = joins.get((track_id, positions[0]))
        finish_anchor = joins.get((track_id, positions[-1]))
        x_start = vertices_by_key[keys[start_anchor]]['x'] if start_anchor is not None else 60
        x_finish = (vertices_by_key[keys[finish_anchor]]['x'] if finish_anchor is not None
                    else x_start + (len(positions) - 1) * 90)
        require(x_start < x_finish, 'Paired turnout placement must preserve increasing track direction')
        for column, position in enumerate(positions):
            source = track_id, position
            if source in joins:
                keys[source] = keys[joins[source]]
                continue
            key = f'V{len(vertices)}'
            keys[source] = key
            x = x_start + (x_finish - x_start) * column / (len(positions) - 1)
            vertices.append({'key': key, 'x': x, 'y': 80 + index * 170, 'orientation': 'horizontal',
                             'names': ['', ''], 'insulated_joint': [False, False], 'axle_counter': [False, False]})
            vertices_by_key[key] = vertices[-1]
        for segment in segments:
            key = f'E{len(edges)}'
            start, end = keys[track_id, segment.start], keys[track_id, segment.end]
            edges.append({'key': key, 'from': [start, 1], 'to': [end, 0],
                          'length_m': segment.end - segment.start, 'radius_m': segment.radius,
                          'gradient_per_mille': segment.slope, 'track_type': 1, 'loop_type': 1, 'dlink_type': 1,
                          'rack_rail': False, 'equal_speed': all(up == down for _, up, down in segment.speeds), 'remark': '',
                          'track_name': track_names[track_id], 'line_name': lines[track_id],
                          'speeds': [{'train_type': kind, 'speed12_kmh': up, 'speed21_kmh': down}
                                     for kind, up, down in segment.speeds]})
            descriptors.append((track_id, segment, key))
    output, report = topology.generate_network(blank, shapes, {'vertices': vertices, 'edges': edges})
    return output, {trace: report['vertex_end_ids'][key] for trace, key in keys.items()}, [
        (track, segment, report['edge_ids'][key]) for track, segment, key in descriptors
    ]


def _check_authoring(project, profiles, traces, vertices, turns, documents):
    for track, segments in profiles.items():
        rows = traces[track]
        require(len(rows) == len(segments), 'Native worksheet topology changed physical segment ownership')
        for row, segment in zip(rows, segments, strict=True):
            document, edge_id = row['document'], row['edge_id']
            edge = project.model((document, edge_id))
            metric = edge.contents[9].values
            speeds = course_factories.dictionary(edge.contents[16].value)
            require((metric[1], metric[2], metric[3]) == (segment.end - segment.start, segment.radius, segment.slope)
                    and {key: (obj.contents[1].value, obj.contents[2].value) for key, obj in speeds.items()}
                    == {key: (up, down) for key, up, down in segment.speeds}
                    and edge.contents[7].value.contents[0].value == row['start_end_id']
                    and edge.contents[8].value.contents[0].value == vertices[document][track, segment.end][0],
                    'Cold read changed a generated Edge endpoint, engineering metric or speed')
    require({(row['document'], row['edge_id']) for rows in traces.values() for row in rows} ==
            {(document, obj.contents[0].value) for document in documents for obj in project.models[document]
             if writer.kind(obj) == 'OTEdgeModel'}, 'Cold read contains an unowned physical Edge')
    for row in turns:
        document, end_id = row['document'], row['turnout_end_id']
        end = project.model((document, end_id))
        legs = [end.contents[index].value for index in (9, 10)]
        require([edge.contents[0].value if edge is not None else None for edge in legs]
                == [row['first_edge_id'], row['second_edge_id']]
                and end.contents[21].value == row['switch_time_s'] and end.contents[22].value == 0,
                'Cold read changed native turnout main and diverging legs, default or switch time')
    require({(row['document'], row['turnout_end_id']) for row in turns} ==
            {(name, end.contents[0].value) for name in documents for end in project.ends(name)
             if end.contents[10].value is not None}, 'Cold read contains an unrepresented native turnout')


def _check_stations(project, facilities, closure):
    expected = {}
    for document, result in facilities.items():
        for row in result['source_station_cross_sections'].values():
            members, references = expected.setdefault((document, row['sign']), (set(), set()))
            for member in row.get('ordinary_end_ids', []):
                members.update((member, project.related((document, member))[1]))
            reference = row['reference_end_id']
            references.update((reference, project.related((document, reference))[1]))
    observed = {(row['document'], row['station_sign']):
                (set(row['member_end_ids']), set(row['reference_end_ids']))
                for row in closure['station_model_bindings']}
    require(len(observed) == len(closure['station_model_bindings'])
            and observed == {key: (ordinary | refs, refs) for key, (ordinary, refs) in expected.items()},
            'Cold read changed the exact native station and platform membership')


def _passing_loops(turnout_rows):
    departures = {row['branch_track_id']: row for row in turnout_rows if row['orientation'] == 'outgoing'}
    loops = []
    for arrival in turnout_rows:
        if arrival['orientation'] != 'incoming':
            continue
        branch = arrival['branch_track_id']
        departure = departures[branch]
        loops.append({
            'main_track_id': arrival['main_track_id'], 'branch_track_id': branch,
            'main_departure_position_m': departure['position_m'], 'main_rejoin_position_m': arrival['position_m'],
            'departure_end': [departure['document'], departure['turnout_end_id']],
            'rejoin_end': [arrival['document'], arrival['turnout_end_id']],
        })
    return loops


def rebuild_station(raw, header, shapes, args, speed_profiles):
    infra, tracks, extents, turnouts, order = _railml_topology(raw)
    names, partitions = _partition(args.worksheets, extents, turnouts)
    facilities, signals, positions = _facilities(infra, tracks, partitions, args.stations, turnouts)
    categories = speed_profiles or {'0': 0}
    require(set(categories) == {str(index) for index in range(len(args.train_types))},
            'RailML speed categories must cover the explicit native .run TrainType indexes')
    profiles, lines = {}, {}
    category_names = {code: str(category) for code, category in categories.items()}
    track_names = {track_id: text(track.get('name') or track_id) for track_id, track in tracks.items()}
    groups = infra.findall(tag('trackGroups'))
    require(len(groups) <= 1 and all(node.tag == tag('line') for group in groups for node in group),
            'Each rebuilt RailML track group must be a represented line')
    source_lines = unique_nodes(infra.findall(tag('trackGroups', 'line')))
    for line in source_lines.values():
        refs = line.findall(tag('trackRef'))
        require(len(refs) == len(line) and len({ref.get('ref') for ref in refs}) == len(refs)
                and all(not len(ref) and set(ref.attrib) == {'ref'} and ref.get('ref') in tracks for ref in refs),
                'RailML line contains unrepresented, duplicate or unknown track references')
    for track_id, track in tracks.items():
        line_nodes = [line for line in source_lines.values()
                      if track_id in {node.get('ref') for node in line.findall(tag('trackRef'))}]
        require(len(line_nodes) <= 1, 'Each rebuilt track needs an unambiguous RailML line name')
        name = line_nodes[0].get('name') if line_nodes else None
        lines[track_id] = text(name) if name else ''
        track_positions = positions[track_id] | {part.high for part in partitions[track_id][:-1]}
        track_positions |= {row.position for row in turnouts if row.main_track == track_id}
        profiles[track_id] = _engineering(infra, track, *extents[track_id], category_names, track_positions)
    files, creation = build_empty_project(
        header, shapes, document_names=names, execution_root=args.execution_root, run_filename=args.run_filename,
        train_types=args.train_types, simulation=None if args.simulation is None else args.simulation.model_dump(),
        additional_outputs=args.additional_outputs,
    )
    members = dict(zip(names, creation['document_members'], strict=True))
    paths = {name: f'{args.execution_root}/{member}' for name, member in members.items()}
    original, _ = writer.load_next_compatible(header)
    header_mark = worksheet_header_fingerprint(original)
    station_file = creation['catalog_members']['stations']
    documents, vertices, facilities_report = {}, {}, {}
    track_edges, selected_signs = defaultdict(list), []
    for name in names:
        local = {track: part for track, parts in partitions.items() for part in parts if part.document == name}
        local_turnouts = [row for row in turnouts if row.main_track in local
                          and local[row.main_track].low < row.position < local[row.main_track].high]
        joins = {(row.branch_track, row.branch_position): (row.main_track, row.position) for row in local_turnouts}
        local_profiles = {track: [row for row in profiles[track] if part.low <= row.start < row.end <= part.high]
                          for track, part in local.items()}
        require(all(rows and rows[0].start == local[track].low and rows[-1].end == local[track].high
                    for track, rows in local_profiles.items()), 'Generated worksheet omits measured physical Edge coverage')
        document, vertices[name], rows = _worksheet_geometry(
            files[members[name]], shapes, local_profiles, track_names, lines, joins,
            [track for track in order if track in local],
        )
        local_edges = defaultdict(list)
        for track, segment, edge_id in rows:
            row = {'document': name, 'edge_id': edge_id, 'start_end_id': vertices[name][track, segment.start][1],
                   'start_position_m': segment.start, 'end_position_m': segment.end,
                   'length_m': segment.end - segment.start, 'radius_m': segment.radius,
                   'gradient_per_mille': segment.slope,
                   'directional_speeds_kmh': {key: {'up': up, 'down': down} for key, up, down in segment.speeds}}
            track_edges[track].append(row)
            local_edges[track].append(SimpleNamespace(**row))
        document, stations, facility = apply_facilities(
            raw, document, [SimpleNamespace(track_id=track, edges=edges) for track, edges in local_edges.items()],
            signals[name], facilities[name], track_extents={track: (part.low, part.high) for track, part in local.items()},
        )
        root, _, _, _ = native.document(document)
        require(worksheet_header_fingerprint(root) == header_mark, 'Generated map changed the bound original worksheet header')
        documents[name] = document
        facilities_report[name] = facility
        files[station_file], added = _merge_catalog(files[station_file], stations)
        selected_signs.extend(added)
    for rows in track_edges.values():
        rows.sort(key=lambda row: row['start_position_m'])
    pairs = [((left.document, vertices[left.document][track, left.high][1]),
              (right.document, vertices[right.document][track, right.low][0]))
             for track, parts in partitions.items() for left, right in zip(parts, parts[1:])]
    documents = _join_worksheets(documents, paths, pairs)
    turnout_rows = []
    for row in turnouts:
        outgoing = row.orientation == 'outgoing'
        position_key = 'start_position_m' if outgoing else 'end_position_m'
        main = next(edge for edge in track_edges[row.main_track] if edge[position_key] == row.position)
        branch = track_edges[row.branch_track][0 if outgoing else -1]
        document, half = main['document'], int(outgoing)
        junction_end = vertices[document][row.main_track, row.position][half]
        require(document == branch['document']
                and junction_end == vertices[document][row.branch_track, row.branch_position][half],
                'Generated through and branching turnout legs must share their exact directional native End')
        turnout_rows.append({'railml_switch_id': row.identity, 'main_track_id': row.main_track,
                             'branch_track_id': row.branch_track, 'position_m': row.position,
                             'branch_position_m': row.branch_position, 'orientation': row.orientation,
                             'document': document, 'turnout_end_id': junction_end,
                             'first_edge_id': main['edge_id'], 'second_edge_id': branch['edge_id'],
                             'default_leg': 'first', 'switch_time_s': 0})
    checked_project = open_project(documents, paths)
    _check_authoring(checked_project, profiles, track_edges, vertices, turnout_rows, names)
    for name, document in documents.items():
        root, _, _, byid = native.document(document)
        require(worksheet_header_fingerprint(root) == header_mark, 'Cold read changed the bound original worksheet header')
        for row in facilities_report[name]['source_signals'].values():
            checked_signal(byid, row['end_id'], row['model_id'], row['name'], row['sight_m'],
                           (RAILML_SIGNAL_TYPES[row['type']], RAILML_SIGNAL_ROLES.get(row['function'], 1), row['virtual']))
        files[members[name]] = document
    closure = validate_pre_service_project(files, run_file=args.run_filename, execution_root=args.execution_root)
    require(closure['station_catalog_signs'] == selected_signs and closure['destination_count'] == 0
            and closure['engine_count'] == closure['train_count'] == 0,
            'Generated native project closure contains unrepresented stations, rolling stock or Destinations')
    _check_stations(checked_project, facilities_report, closure)
    return files, {
        'receipt': creation, 'track_edge_bindings': dict(track_edges), 'native_turnouts': turnout_rows,
        'passing_loops': _passing_loops(turnout_rows),
        'vertices_by_track': {track: [
            {'document': part.document, 'position_m': position, 'end_ids': ends}
            for part in partitions[track] for (source_track, position), ends in vertices[part.document].items()
            if source_track == track
        ] for track in order},
        'native_signals': [dict(row, railml_signal_id=identity, document=name)
                           for name, facility in facilities_report.items()
                           for identity, row in facility['source_signals'].items()],
        'reciprocal_connector_pairs': [[list(a), list(b)] for a, b in pairs], 'facilities_by_document': facilities_report,
        'validation': closure, 'source_train_type_categories': categories,
        'native_worksheet_geometry_copied': False, 'native_operations_template_copied': False,
        'generated_local_chart_spacing': True, 'engineering_readback_verified': True,
        'member_sha256': {name: sha(blob) for name, blob in files.items()},
    }
