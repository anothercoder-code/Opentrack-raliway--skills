"""Compile a measured linear RailML corridor into newly allocated native worksheets."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from types import SimpleNamespace

from . import course_factories, writer
from .infrastructure_railml import railml_path as tag, railml_tracks, railml_tree
from .infrastructure_railml_cross_platform import apply_cross_platform, open_project, platform_source, span_track
from .infrastructure_railml_facilities import fields, measurement, require, text, unique_nodes, xy
from .pre_service_project import validate_pre_service_project
from .route_fetch_tools import SelectedRoute, fetch_routes
from .saved_geometry import replace_connectors
from .tools import sha
from .zero_generation import native_signal_routes as native, topology
from .zero_generation.empty_project import build_empty_project, worksheet_header_fingerprint


@dataclass(frozen=True)
class Profile:
    start: int
    end: int
    slope: float
    radius: float
    speeds: tuple


def _metres(node, attribute='pos'):
    raw = measurement(node, attribute)
    require(raw == int(raw) and 0 <= raw <= 2147483647,
            'New native corridor boundaries require explicit whole-number metre positions')
    return int(raw)


def _scope(raw, specification):
    root = railml_tree(raw)
    infra, tracks = railml_tracks(root)
    require(len(tracks) == 1 and tracks[0].get('id') == specification.track_id,
            'Select one complete linear RailML track with the exact requested track ID')
    track, = tracks
    topo, = track.findall(tag('trackTopology'))
    require(all(child.tag in (tag('trackBegin'), tag('trackEnd'), tag('crossSections')) for child in topo),
            'RailML corridor rebuilding requires a linear track without branches or external connection references')
    begin, = topo.findall(tag('trackBegin'))
    end, = topo.findall(tag('trackEnd'))
    require(all(all(child.tag == tag('openEnd') for child in node) and len(node) <= 1 for node in (begin, end)),
            'The corridor must end at two explicit open RailML boundaries')
    low, high = _metres(begin), _metres(end)
    worksheets = specification.worksheets
    starts = [row.start_position_m for row in worksheets]
    limits = [row.end_position_m for row in worksheets]
    require(low < high and starts[0] == low and limits[-1] == high and starts[1:] == limits[:-1]
            and all(start < limit for start, limit in zip(starts, limits, strict=True)),
            'Worksheet partitions must cover the complete RailML extent once in chainage order')
    require(len({row.document.casefold() for row in worksheets}) == len(worksheets),
            'Worksheet partition names must be distinct, including under case folding')
    lines = [line for line in infra.findall(tag('trackGroups', 'line'))
             if any(ref.get('ref') == specification.track_id for ref in line.findall(tag('trackRef')))]
    require(len(lines) <= 1, 'A rebuilt corridor must have no ambiguous RailML line name')
    line = text(lines[0].get('name', '')) if lines else ''
    return infra, track, low, high, line


def _engineering(infra, track, low, high, categories, forced_positions):
    profiles = unique_nodes(infra.findall(tag('infraAttrGroups', 'infraAttributes')))
    speed = defaultdict(dict)
    positions = set(forced_positions) | {low, high}
    engineering, = track.findall(tag('trackElements'))
    require(all(child.tag in (tag('speedChanges'), tag('gradientChanges'), tag('radiusChanges'), tag('platformEdges'))
                for child in engineering), 'Unrepresented RailML track elements are outside corridor rebuilding')
    for change in unique_nodes(engineering.findall(tag('speedChanges', 'speedChange'))).values():
        fields(change, {'dir', 'vMax', 'profileRef', 'etcsTrainCategory'})
        direction = change.get('dir')
        pos, limit = _metres(change), _metres(change, 'vMax')
        require(direction in ('up', 'down') and 1 <= limit <= 1000, 'Native speeds require positive directional kilometre-per-hour values')
        category = change.get('etcsTrainCategory')
        if change.get('profileRef') is not None:
            shape = profiles.get(change.get('profileRef'))
            require(shape is not None, 'RailML speedChange names an unresolved profile')
            rows = shape.findall(tag('speeds', 'speed'))
            require(len(rows) == 1 and _metres(rows[0], 'vMax') == limit,
                    'RailML speed profile must contain its exact explicit speed and ETCS category')
            inherited = rows[0].get('etcsTrainCategory')
            require(inherited is not None and category in (None, inherited), 'RailML speed category disagrees with the profile')
            category = inherited
        require(category in categories.values() and pos not in speed[direction, category],
                'RailML speeds must map each declared category and direction once at a chainage')
        speed[direction, category][pos] = limit
        positions.add(pos)

    scalar_events = {}
    for section, element, key in (('gradientChanges', 'gradientChange', 'slope'), ('radiusChanges', 'radiusChange', 'radius')):
        events = {}
        for row in unique_nodes(engineering.findall(tag(section, element))).values():
            fields(row, {key})
            pos, value = _metres(row), measurement(row, key)
            require(pos not in events, f'Duplicate RailML {key} value at one chainage')
            limit = 1000 if key == 'slope' else 10000000
            require(abs(value) <= limit, f'RailML {key} exceeds the supported native profile')
            events[pos] = float(topology.flt(float(value), f'RailML {key}'))
            positions.add(pos)
        require(low in events and all(pos < high for pos in events), f'RailML {key} requires an explicit start and in-track changes')
        scalar_events[key] = (sorted(events), events)
    require(all(low <= pos <= high for pos in positions) and len(positions) <= 1001,
            'RailML chainage lies outside the track or exceeds the bounded native Edge count')
    orders = {}
    for category in categories.values():
        up, down = speed['up', category], speed['down', category]
        require(low in up and high in down and high not in up and low not in down,
                'Every speed category must explicitly cover both complete track directions')
        orders[category] = sorted(up), sorted(down)

    def scalar(name, pos):
        keys, values = scalar_events[name]
        return values[keys[bisect_right(keys, pos) - 1]]

    result = []
    ordered = sorted(positions)
    for start, end in zip(ordered, ordered[1:]):
        values = []
        for key, category in categories.items():
            up, down = orders[category]
            values.append((key, speed['up', category][up[bisect_right(up, start) - 1]],
                           speed['down', category][down[bisect_left(down, end)]]))
        result.append(Profile(start, end, scalar('slope', start), scalar('radius', start), tuple(values)))
    return result


def _signals(track, low, high, partition_boundaries):
    result, occupied = [], set()
    ocs, = track.findall(tag('ocsElements'))
    require(all(child.tag in (tag('signals'), tag('stopPosts')) for child in ocs),
            'Unrepresented RailML signalling objects are outside native corridor rebuilding')
    for row in unique_nodes(ocs.findall(tag('signals', 'signal'))).values():
        fields(row, {'dir', 'type', 'function', 'sight', 'virtual'})
        role = {'home': 2, 'blocking': 3, 'exit': 4}.get(row.get('function'))
        position, direction = _metres(row), row.get('dir')
        require(role is not None and row.get('type') == 'main' and row.get('virtual', 'false') in ('false', '0')
                and direction in ('up', 'down'), 'Every rebuilt signal needs an explicit supported physical main role and direction')
        require(low <= position <= high and position not in partition_boundaries and (position, direction) not in occupied,
                'Every signal requires a unique directional End away from the native connector seam')
        sight = _metres(row, 'sight')
        require(1 <= sight <= 100000, 'A physical RailML main signal requires explicit native sight distance')
        occupied.add((position, direction))
        result.append({'railml_signal_id': row.get('id'), 'signal_name': text(row.get('name') or row.get('id')),
                       'position_m': position, 'direction': direction, 'native_role': role, 'sight_m': sight})
    return result


def _worksheet(blank, shapes, profiles, signals, track_name, line):
    positions = [profiles[0].start, *(row.end for row in profiles)]
    keys = {position: f'M_{position}' for position in positions}
    vertices = [{'key': key, 'x': 40 + index * 80, 'y': 60, 'orientation': 'horizontal',
                 'names': ['', ''], 'insulated_joint': [False, False], 'axle_counter': [False, False]}
                for index, key in enumerate(keys.values())]
    edges = [{'key': keys[row.start], 'from': [keys[row.start], 1], 'to': [keys[row.end], 0],
              'length_m': row.end - row.start, 'radius_m': row.radius, 'gradient_per_mille': row.slope,
              'track_type': 1, 'loop_type': 1, 'dlink_type': 1, 'rack_rail': False,
              'equal_speed': all(up == down for _, up, down in row.speeds), 'remark': '',
              'track_name': track_name, 'line_name': line,
              'speeds': [{'train_type': key, 'speed12_kmh': up, 'speed21_kmh': down} for key, up, down in row.speeds]}
             for row in profiles]
    output, report = topology.generate_network(blank, shapes, {'vertices': vertices, 'edges': edges})
    by_position = {position: report['vertex_end_ids'][key] for position, key in keys.items()}
    for signal in signals:
        key = by_position[signal['position_m']][0 if signal['direction'] == 'up' else 1]
        _, _, _, indexed = native.document(output)
        end = indexed[key]
        x, y = xy(end)
        output, saved = native.build_signal(
            output, end_id=key, name=signal['signal_name'], model_id=max(indexed) + 1,
            placement={'x': float(x), 'y': float(y), 'angle': float(end.contents[1].value),
                       'alignment_x': end.contents[4].value, 'alignment_y': end.contents[5].value},
            sight_m=signal['sight_m'], delay_s=0, show_symbol=True, show_icon=True,
            signal_type=1, main_type=signal['native_role'], virtual=False,
        )
        signal.update(end_id=key, model_id=saved['model_id'])
    return output, by_position


def _join_worksheets(documents, paths, boundary_links):
    project = open_project(documents, paths)
    links = [{'a': {'document': former[0], 'end_id': former[1]}, 'b': {'document': latter[0], 'end_id': latter[1]}}
             for former, latter in boundary_links]
    affected, _ = replace_connectors(project, {'link': links, 'unlink': []})
    result = {**documents, **{name: writer.dump_verified(project.roots[name], project.versions[name]) for name in affected}}
    checked = open_project(result, paths)
    require(all(checked.block_end(a) == b and checked.block_end(b) == a for a, b in boundary_links),
            'Cold read changed a newly generated reciprocal native connector')
    return result


def _build_through_routes(documents, paths, dest, spans, signals, origin, finish, direction):
    up = direction == 'up'
    lower, upper = sorted((origin, finish))
    travel = sorted((row for row in signals if row['direction'] == direction and lower < row['position_m'] < upper),
                    key=lambda row: row['position_m'], reverse=not up)
    if not travel:
        return documents, []
    edge_order = spans if up else spans[::-1]
    require(all(row['native_role'] == 3 for row in travel), 'Only physical through blocks may lie inside a rebuilt stopping area')
    requests = []
    for index, (block, following) in enumerate(zip(travel, [*travel[1:], {'position_m': finish}], strict=True), 1):
        a, b = sorted((block['position_m'], following['position_m']))
        footprint = [span for span in edge_order if a <= span.low and span.high <= b]
        nodes = [(block['document'], block['end_id']), *((span.end if up else span.start) for span in footprint)]
        require(footprint and sum(x[0] != y[0] for x, y in zip(nodes, nodes[1:])) == 1,
                'Each interior through block must reach its next stopping reference or block over one verified native connector')
        label = f"RailML through {index} {block['signal_name']}"
        request = SelectedRoute(name=label if len(label) <= 200 else f'RailML through block {index}',
                                candidate={'end_sequence': nodes, 'edge_sequence': [span.edge for span in footprint],
                                           'distance_m': int(b - a)}, reserve_previous=True)
        requests.append(request.model_dump())
    changed, report = fetch_routes(documents, paths, dest, requests)
    return {**documents, **changed}, report['created_routes']


def rebuild_corridor(raw, header, shapes, args, speed_profiles):
    infra, track, low, high, line = _scope(raw, args)
    binding = SimpleNamespace(track_id=args.track_id)
    _, origin, finish, _ = platform_source(raw, binding, args.station)
    require(origin == int(origin) and finish == int(finish) and low <= min(origin, finish) < max(origin, finish) <= high,
            'A rebuilt platform must have explicit whole-metre boundaries within its corridor')
    for section, query, selected_id in (('cross section', tag('trackTopology', 'crossSections', 'crossSection'), args.station.cross_section_id),
                                        ('platform', tag('trackElements', 'platformEdges', 'platformEdge'), args.station.platform_edge_id),
                                        ('stop post', tag('ocsElements', 'stopPosts', 'stopPost'), args.station.stop_post_id)):
        require(set(unique_nodes(track.findall(query))) == ({selected_id} if selected_id is not None else set()),
                f'The rebuilt corridor requires an exact selected {section} inventory')
    names = [row.document for row in args.worksheets]
    profiles = speed_profiles or {'0': 0}
    require(set(profiles) == {str(index) for index in range(len(args.train_types))},
            'The RailML speed category map must cover the explicit native .run TrainType indexes')
    categories = {key: str(value) for key, value in profiles.items()}
    boundaries = {row.end_position_m for row in args.worksheets[:-1]}
    signals = _signals(track, low, high, boundaries)
    positions = boundaries | {int(origin), int(finish)} | {row['position_m'] for row in signals}
    engineering = _engineering(infra, track, low, high, categories, positions)
    files, creation = build_empty_project(
        header, shapes, document_names=names, execution_root=args.execution_root, run_filename=args.run_filename,
        train_types=args.train_types, simulation=None if args.simulation is None else args.simulation.model_dump(),
        additional_outputs=args.additional_outputs,
    )
    members = dict(zip(names, creation['document_members'], strict=True))
    paths = {name: f'{args.execution_root}/{member}' for name, member in members.items()}
    original_header, _ = writer.load_next_compatible(header)
    track_name = text(track.get('name', ''))
    documents, vertices, planned, consumed = {}, {}, [], []
    for sheet in args.worksheets:
        name, start, end = sheet.document, sheet.start_position_m, sheet.end_position_m
        local = [row for row in engineering if start <= row.start < row.end <= end]
        require(local and local[0].start == start and local[-1].end == end,
                'Each generated worksheet must own a contiguous, nonempty partition of physical Edges')
        consumed.extend(local)
        selected = [row for row in signals if start <= row['position_m'] <= end]
        documents[name], by_position = _worksheet(files[members[name]], shapes, local, selected, track_name, line)
        for row in selected:
            row['document'] = name
        vertices[name] = [{'position_m': pos, 'end_ids': ends} for pos, ends in by_position.items()]
        project_root, _, _, indexed = native.document(documents[name])
        require(worksheet_header_fingerprint(project_root) == worksheet_header_fingerprint(original_header),
                'A generated worksheet changed the reviewed original-format header')
        for row in local:
            departure = by_position[row.start][1]
            edge = indexed[departure].contents[9].value
            require(edge.contents[8].value is indexed[by_position[row.end][0]], 'A newly generated Edge reaches the wrong partition End')
            planned.append({'document': name, 'edge_id': edge.contents[0].value, 'start_end_id': departure})
    require(consumed == engineering and len({(row['document'], row['edge_id']) for row in planned}) == len(engineering),
            'Every native physical Edge must have exactly one owner across the reviewed partition boundaries')
    pairs = [((left, vertices[left][-1]['end_ids'][1]), (right, vertices[right][0]['end_ids'][0]))
             for left, right in zip(names, names[1:])]
    documents = _join_worksheets(documents, paths, pairs)
    binding.edges = [SimpleNamespace(**row) for row in planned]
    spans = span_track(open_project(documents, paths), track, binding)
    roles = creation['catalog_members']
    documents, routes = _build_through_routes(documents, paths, files[roles['dest']], spans, signals,
                                               origin, finish, args.station.direction)
    documents, stations, facility = apply_cross_platform(raw, documents, paths, files[roles['stations']], binding, args.station)
    readback = open_project(documents, paths)
    spans = span_track(readback, track, binding)
    observed_eng = []
    for span, authored in zip(spans, engineering, strict=True):
        edge = readback.model(span.edge)
        metric = edge.contents[9].values
        speeds = course_factories.dictionary(edge.contents[16].value)
        require((span.low, span.high, metric[2], metric[3]) == (authored.start, authored.end, authored.radius, authored.slope)
                and {key: (value.contents[1].value, value.contents[2].value) for key, value in speeds.items()}
                == {key: (up, down) for key, up, down in authored.speeds},
                'Cold read changed a native segment metric, gradient, radius or directional speed')
        observed_eng.append({'document': span.edge[0], 'edge_id': span.edge[1], 'start_position_m': authored.start,
                             'end_position_m': authored.end, 'length_m': metric[1], 'radius_m': float(metric[2]),
                             'gradient_per_mille': float(metric[3]),
                             'directional_speeds_kmh': {key: {'up': up, 'down': down} for key, up, down in authored.speeds}})
    for name, blob in documents.items():
        files[members[name]] = blob
    files[roles['stations']] = stations
    closure = validate_pre_service_project(files, run_file=args.run_filename, execution_root=args.execution_root)
    require(closure['station_catalog_signs'] == [facility['sign']] and closure['destination_count'] == 0,
            'Generated project unexpectedly contains unrepresented station or itinerary definitions')
    return files, {'receipt': creation, 'vertices_by_document': vertices, 'track_edge_bindings': planned,
                   'engineering_segments': observed_eng,
                   'reciprocal_connector_pairs': [[list(a), list(b)] for a, b in pairs], 'native_signals': signals,
                   'through_routes': routes, 'platform': facility, 'validation': closure,
                   'source_track_id': args.track_id, 'source_train_type_categories': profiles,
                   'native_worksheet_geometry_copied': False, 'native_operations_template_copied': False,
                   'generated_local_chart_spacing': True, 'engineering_readback_verified': True,
                   'member_sha256': {name: sha(blob) for name, blob in files.items()}}
