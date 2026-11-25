"""Bind continuous RailML platform extents to native station-member pairs."""

from . import catalogs, path_functions, route_factory, writer
from .zero_generation import native_signal_routes as native
from .zero_operations import station_binding
from .zero_terminal import terminal_areas


def require(condition, message):
    if not condition:
        raise ValueError(message)


def platform_spans(spans, origin, finish, direction):
    low, high = sorted((origin, finish))
    area = [span for span in spans if low <= span.low and span.high <= high]
    require(area and area[0].low == low and area[-1].high == high,
            'Selected platform must cover complete contiguous native Edges')
    return area if direction == 'up' else area[::-1]


def area_entries(spans, direction, byid):
    # Route End identity is the facing half at each travel-side boundary.
    return [byid[span.start if direction == 'up' else span.finish].contents[8].value for span in spans]


def area_stop(entry_ids, reference, spans, signal):
    last = spans[-1]
    return {'entry_end_id': entry_ids[0], 'exit_end_id': reference, 'area_edge_id': last.edge,
            'area_edge_ids': [span.edge for span in spans], 'length_m': int(sum(span.high - span.low for span in spans)),
            'exit_signal_name': signal['name'], 'direction': 'forward_only'}


def area_details(entry_ids, stop, byid):
    return {key: stop[key] for key in ('area_edge_id', 'area_edge_ids', 'entry_end_id', 'length_m')} | {
        'ordinary_end_ids': entry_ids, 'stopping_edge_id': stop['area_edge_id'],
        'native_track_name': writer.string(byid[stop['area_edge_id']].contents[19].value)}


def connected_area(byid, spec):
    """Check every directed whole Edge and ensure a single stopping candidate."""
    stop = spec['stop']
    members = spec['ordinary_end_ids']
    ends = [*members, spec['reference_end_id']]
    edge_ids = stop['area_edge_ids']
    require(members and len(members) == len(edge_ids) and len(set(edge_ids)) == len(edge_ids)
            and stop['entry_end_id'] == members[0] and stop['exit_end_id'] == ends[-1]
            and stop['area_edge_id'] == edge_ids[-1], 'Platform approach and exact stopping Edge are inconsistent')
    length_m, pairs = 0, []
    for end_id in ends:
        end = byid.get(end_id)
        require(end is not None and writer.kind(end) == 'OTEndModel', 'Unknown platform End')
        pair = byid.get(end.contents[8].value)
        require(pair is not None and writer.kind(pair) == 'OTEndModel' and pair.contents[8].value == end_id,
                'Platform has an unresolved native End pair')
        halves = end, pair
        require(all(sum(half.contents[slot].value is not None for slot in (9, 10)) == 1 for half in halves),
                'Platform area must be unbranched at each native boundary')
        pairs.append(halves)
    require(len({half.contents[0].value for pair in pairs for half in pair}) == 2 * len(pairs),
            'Platform area must not visit a native double vertex twice')
    for edge_id, (_, start), (finish, _) in zip(edge_ids, pairs, pairs[1:]):
        edge = byid.get(edge_id)
        require(edge is not None and writer.kind(edge) == 'OTEdgeModel'
                and {edge.contents[s].value for s in (7, 8)} == {start, finish},
                'Platform approach does not follow the ordered native Edge chain')
        length_m += edge.contents[9].values[1]
    require(length_m == stop['length_m'], 'Native platform extent does not equal the RailML length')
    require(all(half.contents[11].value is None for pair in pairs[:-1] for half in pair),
            'Additional signals inside the platform approach require an explicit stopping-candidate contract')
    return pairs


def narrow_areas(byid, specs):
    """Reduce to the last known stopping Edge for the existing native binder."""
    single_edge_specs, extras = [], []
    used = set()
    for spec in specs:
        ref = byid.get(spec['reference_end_id'])
        require(ref is not None and writer.kind(ref) == 'OTEndModel', 'Station reference End missing')
        stop = spec['stop']
        if stop is None:
            require(not spec['ordinary_end_ids'], 'Point station cannot own ordinary platform vertices')
            pairs = [(ref, byid[ref.contents[8].value])]
            single_edge_specs.append(spec)
        else:
            pairs = connected_area(byid, spec)
            extras.extend((ref, member) for pair in pairs[:-2] for member in pair)
            terminal_entry = spec['ordinary_end_ids'][-1]
            terminal_edge = byid[stop['area_edge_id']]
            last = {key: value for key, value in stop.items() if key != 'area_edge_ids'}
            last.update(entry_end_id=terminal_entry, length_m=terminal_edge.contents[9].values[1])
            single_edge_specs.append({**spec, 'ordinary_end_ids': [terminal_entry], 'stop': last})
        for pair in pairs:
            for end in pair:
                require(end not in used, 'Overlapping logical station pairs')
                used.add(end)
    return single_edge_specs, extras


def area_snapshot(document, specs, anchors=None):
    if len({spec['sign'] for spec in specs}) != len(specs):
        return read_grouped_areas(document, specs, anchors)
    root, version, _, byid = native.document(document)
    native.validate_topology(root)
    narrow, extras = narrow_areas(byid, specs)
    for reference, member in extras:
        station = reference.contents[12].value
        require(station is not None and writer.kind(station) == 'OTStationModel'
                and member.contents[12].value is station and member.contents[20].value == 1,
                'Native ordinary paired platform membership or End type failed readback')
        member.contents[12].value = None
    narrowed = writer.dump_verified(root, version) if extras else document
    terminal_areas.read_document(narrowed, narrow)
    return narrowed


def bind_areas(document, specs, anchors=None):
    if len({spec['sign'] for spec in specs}) != len(specs):
        return bind_grouped_areas(document, specs, anchors)
    _, _, _, byid = native.document(document)
    narrow, _ = narrow_areas(byid, specs)
    base, stations, report, _ = terminal_areas.bind_areas(document, narrow)
    root, version, _, byid = native.document(base)
    _, extras = narrow_areas(byid, specs)
    if not extras:
        return base, stations, report
    for reference, member in extras:
        path_functions.guard_counter_references(root, member)
        require(member.contents[12].value is None and member.contents[20].value == 1,
                'Interior platform pair is already bound or uses an unsupported End type')
        member.contents[12].value = reference.contents[12].value
    expanded = writer.dump_verified(root, version)
    require(area_snapshot(expanded, specs) == base, 'Multi-edge station binding changed non-target native archive fields')
    return expanded, stations, {**report, 'output_sha256': terminal_areas.sha(expanded),
                                'profile': 'directed contiguous unbranched Edges grouped with one native StationModel and exit',
                                'multi_edge_platform_count': sum(len(spec['ordinary_end_ids']) > 1 for spec in specs)}


def grouped_layout(byid, specs, anchors):
    groups, layout = {}, {}
    edge_ids = set()
    for spec in specs:
        sign, reference, stop = spec['sign'], spec['reference_end_id'], spec['stop']
        group = groups.setdefault(sign, [])
        require(not group or group[0]['name'] == spec['name'], 'Shared station approaches disagree on their station name')
        group.append(spec)
        if stop is None:
            require(not spec['ordinary_end_ids'], 'Point station cannot own ordinary platform vertices')
            end = byid[reference]
            pairs = [(end, byid[end.contents[8].value])]
        else:
            pairs = connected_area(byid, spec)
            end, peer = pairs[-1]
            signal = end.contents[11].value
            require(signal is not None and writer.kind(signal) == 'OTSignalModel' and signal.contents[7].value is end
                    and signal.contents[8].values[0] in (1, 2) and signal.contents[8].values[1] == 4
                    and not signal.contents[9].values[2] & 2 and
                    catalogs.text(signal.contents[13].value) == stop['exit_signal_name'] and peer.contents[11].value is None,
                    'Grouped platform needs the exact directional physical exit signal without a competing reverse signal')
            edge_ids.update(stop['area_edge_ids'])
        for position, pair in enumerate(pairs):
            end_type = 2 if position == len(pairs) - 1 else 1
            for end in pair:
                require(end not in layout, 'Overlapping logical station pairs')
                layout[end] = sign, end_type
    for edge_id, edge in byid.items():
        if writer.kind(edge) != 'OTEdgeModel' or edge_id in edge_ids:
            continue
        first, last = (layout.get(edge.contents[i].value) for i in (7, 8))
        require(not (first and last and first[0] == last[0]),
                'An unmapped Edge would become part of the shared native station area')
    point_specs = []
    for sign, group in groups.items():
        primary = anchors.get(sign, group[0]['reference_end_id']) if anchors else group[0]['reference_end_id']
        matches = [spec for spec in group if spec['reference_end_id'] == primary]
        require(len(matches) == 1, f'Station {sign!r} anchor must be a selected directed reference')
        point_specs.append({key: value for key, value in matches[0].items()
                            if key not in ('reference_end_id', 'ordinary_end_ids', 'stop')} |
                           {'end_ids': [spec['reference_end_id'] for spec in group]})
    return point_specs, layout


def read_grouped_areas(document, specs, anchors):
    root, version, models, byid = native.document(document)
    native.validate_topology(root)
    point_specs, layout = grouped_layout(byid, specs, anchors)
    graphics = [model for model in models if writer.kind(model) == 'OTStationModel']
    point_by_sign = {point['sign']: point for point in point_specs}
    stations = {}
    for model in graphics:
        route_factory.layout(model, 'OTStationModel', 1, station_binding.MODEL, graphic=True)
        sign = catalogs.text(model.contents[7].value)
        require(sign in point_by_sign and sign not in stations and model.contents[8].values == [2, 4]
                and model.contents[9].values == [1, 0] and model.contents[6].value is None,
                'Unexpected or duplicate native StationModel in shared platform readback')
        point = point_by_sign[sign]['placement']
        require([model.contents[i].value for i in range(1, 6)] ==
                [point[key] for key in ('angle', 'x', 'y', 'alignment_x', 'alignment_y')],
                'Shared StationModel failed anchor placement readback')
        stations[sign] = model
    require(set(stations) == set(point_by_sign) and
            all(model in graphics for model in writer.objects(root) if writer.kind(model) == 'OTStationModel'),
            'Missing or hidden native station graphic')
    for model in models:
        if writer.kind(model) != 'OTEndModel':
            continue
        owner, kind = layout.get(model, (None, 1))
        require(model.contents[12].value is stations.get(owner) and model.contents[20].value == kind,
                'Native shared station member or reference identity failed readback')
        if owner is not None:
            model.contents[12].value = None
            model.contents[20].value = 1
    writer.set_elements(root.contents[2].value, [model for model in models if model not in graphics])
    return writer.dump_verified(root, version)


def bind_grouped_areas(document, specs, anchors):
    _, _, _, byid = native.document(document)
    points, _ = grouped_layout(byid, specs, anchors)
    base, stations, point_report = station_binding.bind_stations(document, points)
    root, version, _, byid = native.document(base)
    _, layout = grouped_layout(byid, specs, anchors)
    for member, (sign, end_type) in layout.items():
        station = byid[point_report['model_ids'][sign]]
        if end_type == 1:
            path_functions.guard_counter_references(root, member)
            require(member.contents[12].value is None and member.contents[20].value == 1,
                    'Ordinary platform member overlaps another saved station')
            member.contents[12].value = station
    output = writer.dump_verified(root, version)
    original, original_version, _, _ = native.document(document)
    require(read_grouped_areas(output, specs, anchors) == writer.dump_verified(original, original_version),
            'Shared station binding changed non-target native archive fields')
    return output, stations, {'source_sha256': terminal_areas.sha(document), 'output_sha256': terminal_areas.sha(output),
                              'stations_sha256': terminal_areas.sha(stations), 'station_count': len(points),
                              'stop_area_count': sum(spec['stop'] is not None for spec in specs),
                              'multi_platform_station_count': sum(len(point['end_ids']) > 1 for point in points),
                              'multi_edge_platform_count': sum(len(spec['ordinary_end_ids']) > 1 for spec in specs),
                              'point_binding_receipt': point_report, 'restored_whole_original_graph': True,
                              'profile': 'distinct directed platform approaches with paired references sharing one StationModel',
                              'native_simulation_executed': False}
