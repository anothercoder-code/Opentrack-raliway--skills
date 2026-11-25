"""Write one whole-Edge RailML platform across an ordered native worksheet chain."""

from dataclasses import dataclass

from . import catalogs, path_functions, route_factory, writer
from .infrastructure_railml import railml_path as tag, railml_tracks, railml_tree
from .infrastructure_railml_areas import platform_spans
from .infrastructure_railml_facilities import fields, measurement, require, selected, text, unique_nodes, xy
from .itinerary_edit_tools import EditableItineraryProject
from .multi_document.core import Project, sha
from .native_connected_platform import is_main_role, through_route
from .zero_operations import station_binding as sb


@dataclass(frozen=True)
class Segment:
    edge: tuple
    start: tuple
    end: tuple
    low: int
    high: int


def worksheet_order(project, binding):
    ordered = []
    for edge in binding.edges:
        if not ordered or ordered[-1] != edge.document:
            ordered.append(edge.document)
    require(len(ordered) >= 2 and len(ordered) == len(set(ordered)) and set(ordered) == set(project.roots),
            'Map every supplied worksheet in one ordered native corridor without revisiting a worksheet')
    return ordered


def span_track(project, rail_track, binding):
    ends = [rail_track.findall(tag('trackTopology', key)) for key in ('trackBegin', 'trackEnd')]
    require(all(len(nodes) == 1 for nodes in ends), 'RailML track requires exact beginning and end')
    first, limit = (measurement(nodes[0], 'pos') for nodes in ends)
    used, segments, at = set(), [], first
    for row in binding.edges:
        key = (row.document, row.edge_id)
        edge = project.model(key)
        require(writer.kind(edge) == 'OTEdgeModel' and key not in used, 'Mapped native Edge is unknown or repeated')
        termini = {project.key(edge.contents[slot].value) for slot in (7, 8)}
        start = (row.document, row.start_end_id)
        require(start in termini, 'Mapped start End does not belong to its native Edge')
        if segments:
            prior = segments[-1].end
            require(project.actual_related(prior) == start, 'RailML track is not a continuous directed native Edge chain')
        end, = termini - {start}
        name = writer.string(edge.contents[19].value)
        require(not name or not rail_track.get('name') or rail_track.get('name') == name,
                'Mapped native Edge has a different track name from RailML')
        high = at + edge.contents[9].values[1]
        require(high > at, 'Mapped native Edge does not have positive physical length')
        segments.append(Segment(key, start, end, at, high))
        used.add(key)
        at = high
    require(at == limit, 'Mapped native lengths differ from the complete RailML track')
    worksheet_order(project, binding)
    return segments


def platform_source(raw, track_binding, station):
    infra, tracks = railml_tracks(railml_tree(raw))
    track = selected(unique_nodes(tracks), track_binding.track_id, 'track')
    cross = selected(unique_nodes(track.findall(tag('trackTopology', 'crossSections', 'crossSection'))),
                     station.cross_section_id, 'crossSection')
    platform = selected(unique_nodes(track.findall(tag('trackElements', 'platformEdges', 'platformEdge'))),
                        station.platform_edge_id, 'platformEdge')
    signal = selected(unique_nodes(track.findall(tag('ocsElements', 'signals', 'signal'))), station.exit_signal_id, 'signal')
    fields(cross, {'ocpRef', 'dir'})
    fields(platform, {'ocpRef', 'dir', 'length', 'side', 'height'})
    fields(signal, {'dir', 'type', 'function', 'sight', 'virtual'})
    direction = station.direction
    ocp_id = cross.get('ocpRef')
    require(ocp_id and platform.get('ocpRef') == ocp_id and platform.get('dir', direction) == direction
            and cross.get('dir', direction) == direction, 'Mapped cross section and platform must agree on OCP and direction')
    origin, length = measurement(platform, 'pos'), measurement(platform, 'length')
    finish = origin + length if direction == 'up' else origin - length
    require(length > 0 and finish == measurement(cross, 'pos') == measurement(signal, 'pos')
            and signal.get('dir') == direction and signal.get('type') == 'main'
            and signal.get('function') == 'exit' and signal.get('virtual','false') in ('false','0'),
            'Platform end, reference, and one physical directional exit signal must coincide')
    if station.stop_post_id is not None:
        post = selected(unique_nodes(track.findall(tag('ocsElements', 'stopPosts', 'stopPost'))),
                        station.stop_post_id, 'stopPost')
        fields(post, {'dir', 'platformEdgeRef', 'ocpRef', 'virtual'}, (tag('signalRef'),))
        refs = post.findall(tag('signalRef'))
        require(measurement(post, 'pos') == finish and post.get('dir') == direction
                and post.get('platformEdgeRef') == station.platform_edge_id and post.get('ocpRef', ocp_id) == ocp_id
                and post.get('virtual', 'false') in ('false', '0')
                and all(not len(ref) and ref.attrib == {'ref': station.exit_signal_id} for ref in refs)
                and len(refs) <= 1, 'Stop post differs from the selected physical platform and signal')
    ocp = selected(unique_nodes(infra.findall(tag('operationControlPoints', 'ocp'))), ocp_id, 'OCP')
    return track, origin, finish, {'ocp_id': ocp_id, 'sign': text(ocp.get('code') or ocp_id),
                                   'name': text(ocp.get('name') or ocp_id),
                                   'signal_name': text(signal.get('name') or station.exit_signal_id),
                                   'sight_m': measurement(signal, 'sight') if 'sight' in signal.attrib else None}


def area_layout(project, area, direction, signature):
    directed = [(span.start, span.end) if direction == 'up' else (span.end, span.start) for span in area]
    before, reference = directed[0][0], directed[-1][1]
    reference_peer = project.related(reference)
    anchors, members = {}, {}
    boundaries, blocks = [], []
    arrivals = {last: index for index, (_, last) in enumerate(directed[:-1])}
    for start, finish in directed:
        for key in (start, finish):
            home = project.model(key)
            mate_key = project.related(key)
            mate = project.model(mate_key)
            require(writer.kind(home) == 'OTEndModel' and
                    sum(home.contents[slot].value is not None for slot in (9, 10)) == 1,
                    'Station platform approach must be unbranched at every physical End')
            if writer.kind(mate) == 'OTConnModel':
                require(key not in (before, reference), 'Connector must lie inside the platform, outside both end pairs')
                remote = project.block_end(mate_key)
                require(project.block_end(remote) == mate_key, 'A platform boundary connector is not reciprocal')
                boundaries.append((mate_key, remote))
                pairs = (key,)
            else:
                require(writer.kind(mate) == 'OTEndModel' and
                        sum(mate.contents[slot].value is not None for slot in (9, 10)) == 1,
                        'Station platform ordinary pairs must be unbranched')
                pairs = (key, mate_key)
            for item in pairs:
                end_type = 2 if item in (reference, reference_peer) else 1
                members[item] = end_type
                end = project.model(item)
                if item != reference and end.contents[11].value is not None:
                    require(item in arrivals and is_main_role(project, item, 3) and writer.kind(mate) == 'OTEndModel',
                            'An additional platform signal creates a competing stopping position')
                    if item not in blocks:
                        blocks.append(item)
        anchors.setdefault(start[0], start)
    anchors[reference[0]] = reference
    connections = boundaries[::2]
    require(len(anchors) >= 2 and len(boundaries) == 2 * (len(anchors) - 1) and
            all(a == b[::-1] for a, b in zip(connections, boundaries[1::2], strict=True)),
            'The selected platform must traverse an ordered chain of reciprocal worksheet connectors')
    included = {span.edge for span in area}
    for document, models in project.models.items():
        for edge in models:
            if writer.kind(edge) != 'OTEdgeModel' or project.key(edge) in included:
                continue
            require(not all(project.key(edge.contents[slot].value) in members for slot in (7, 8)),
                    f'An unmapped Edge on {document!r} would become part of the shared station area')
    signal = project.model(reference).contents[11].value
    require(signal is not None and writer.kind(signal) == 'OTSignalModel' and signal.contents[7].value is project.model(reference)
            and signal.contents[8].values[:2] == [1, 4]
            and catalogs.text(signal.contents[13].value) == signature['signal_name']
            and (signature['sight_m'] is None or signal.contents[9].values[1] == signature['sight_m']),
            'RailML stop requires its existing exact native directional main exit signal and sight')
    declared = []
    if blocks:
        require(len(connections) >= 2, 'Interior through blocks require a reviewed multi-connector station area')
        track_names = {writer.string(project.model(span.edge).contents[19].value) for span in area}
        require(len(track_names) == 1 and all(track_names), 'Interior through blocks require one exact native track name throughout the berth')
        operational = EditableItineraryProject(project.blobs, document_paths=project.paths,
                                               expected_hashes={key: sha(data) for key, data in project.blobs.items()},
                                               complete_document_set=True)
        path = [project.related(before), *(last for _, last in directed)]
        ordered = sorted(arrivals[key] + 1 for key in blocks)
        for start, last in zip(ordered, [*ordered[1:], len(path) - 1], strict=True):
            require(through_route(operational, path[start:last + 1]),
                    'An interior block needs one exact advanced-reservation Route to the next platform block or exit')
            end = project.model(path[start])
            interior = end.contents[11].value
            span = area[start - 1]
            declared.append({'end': list(path[start]), 'position': span.high if direction == 'up' else span.low,
                             'signal_name': text(catalogs.text(interior.contents[13].value)),
                             'sight_m': interior.contents[9].values[1]})
    return reference, connections, anchors, members, declared


def reviewed_blocks(track, direction, origin, finish, blocks):
    """Match the original `blocking` RailML function at the same physical Ends."""
    low, high = sorted((origin, finish))
    candidates = [signal for signal in unique_nodes(track.findall(tag('ocsElements', 'signals', 'signal'))).values()
                  if signal.get('dir') == direction and low < measurement(signal, 'pos') < high]
    by_position = {measurement(signal, 'pos'): signal for signal in candidates}
    require(len(candidates) == len(by_position) == len(blocks), 'RailML interior signals differ from the native through blocks')
    result = []
    for block in blocks:
        signal = by_position.get(block['position'])
        require(signal is not None, 'A native through block is absent at its exact RailML position')
        fields(signal, {'dir', 'type', 'function', 'sight', 'virtual'})
        require(signal.get('type') == 'main' and signal.get('function') == 'blocking'
                and signal.get('virtual', 'false') in ('false', '0') and signal.get('name') == block['signal_name']
                and ('sight' not in signal.attrib or measurement(signal, 'sight') == block['sight_m']),
                'RailML interior through block name, role, direction or sight differs from the exact native signal')
        position = block['position']
        exact_position = int(position) if position == int(position) else float(position)
        result.append({**block, 'position': exact_position, 'railml_signal_id': signal.get('id')})
    return result


def station_model(model_id, sign, anchor):
    x, y = xy(anchor)
    return sb.obj([('OTStationModel',1),('OTGraphicModel',1),('NSObject',0)], [
        ('i',[model_id]),('f',[0.0]),('f',[sb.number(x)]),('f',[sb.number(y)]),('i',[0]),('i',[0]),('@',[None]),
        ('@',[sb.string(sign)]),('ii',[2,4]),('ii',[1,0]),
    ])


def native_catalog(blob, sign, name):
    root, version = writer.load_next_compatible(blob)
    rows = catalogs.station_items(root)
    if sign in rows:
        row = rows[sign]
        require(catalogs.text(row.contents[2].value) == name and row.contents[7].value == 1,
                'Existing station catalog row disagrees on the selected RailML sign, name, or timing flag')
        return blob, False
    row = sb.obj([('OTStation',3),('NSObject',0)], [
        ('i',[17]),('@',[sb.string(sign)]),('@',[sb.string(name)]),('i',[0]),('iii',[0,0,0]),('ii',[0,0]),
        ('@',[sb.string('')]),('i',[1]),('@',[sb.string('')]),('@',[sb.string('')]),
    ])
    root.contents[0].value += 1
    root.contents += [writer.TypedValue(b'@', sb.string(sign)), writer.TypedValue(b'@', row)]
    candidate = writer.dump_verified(root, version)
    parsed, parsed_version = writer.load_next_compatible(candidate)
    checked = catalogs.station_items(parsed)
    require(set(checked) == set(rows) | {sign} and catalogs.text(checked[sign].contents[2].value) == name,
            'Cross-platform catalog row failed readback')
    parsed.contents[0].value -= 1
    parsed.contents = parsed.contents[:-2]
    original, original_version = writer.load_next_compatible(blob)
    require(writer.dump_verified(parsed, parsed_version) == writer.dump_verified(original, original_version),
            'Catalog update changed an unselected native row')
    return candidate, True


def open_project(documents, paths):
    return Project(documents, document_paths=paths, expected_hashes={key: sha(value) for key, value in documents.items()},
                   complete_document_set=True, validate_operations=False)


def apply_cross_platform(railml, documents, paths, catalog, track_binding, station_binding):
    track, origin, finish, source = platform_source(railml, track_binding, station_binding)
    project = open_project(documents, paths)
    spans = platform_spans(span_track(project, track, track_binding), origin, finish, station_binding.direction)
    reference, connections, anchors, members, blocks = area_layout(project, spans, station_binding.direction, source)
    interior = reviewed_blocks(track, station_binding.direction, origin, finish, blocks) if len(connections) > 1 else []
    sign, name = source['sign'], source['name']
    owned, output = {}, dict(documents)
    for document, root in project.roots.items():
        require(not any(writer.kind(obj) == 'OTStationModel' and catalogs.text(obj.contents[7].value) == sign
                        for obj in writer.objects(root)), 'This station sign already has an infrastructure graphic in the supplied worksheets')
        if document not in anchors:
            continue
        model_id = max(project.byid[document]) + 1
        sb.integer(model_id)
        owned[document] = station_model(model_id, sign, project.model(anchors[document]))
        writer.set_elements(root.contents[2].value, [*project.models[document], owned[document]])
    for key, end_type in members.items():
        end = project.model(key)
        require(end.contents[12].value is None and end.contents[20].value == 1,
                'A selected platform End already belongs to another station or reference')
        path_functions.guard_counter_references(project.roots[key[0]], end, allow_local_shunting=True)
        end.contents[12].value = owned[key[0]]
        end.contents[20].value = end_type
    for document in owned:
        output[document] = writer.dump_verified(project.roots[document], project.versions[document])

    readback = open_project(output, paths)
    for document, root in readback.roots.items():
        if document not in owned:
            require(output[document] == documents[document], 'A non-platform worksheet changed during facility import')
            continue
        model = readback.model((document, owned[document].contents[0].value))
        route_factory.layout(model, 'OTStationModel', 1, sb.MODEL, graphic=True)
        require(catalogs.text(model.contents[7].value) == sign and model.contents[8].values == [2,4]
                and model.contents[9].values == [1,0] and xy(model) == xy(readback.model(anchors[document])),
                'The local StationModel copy failed exact readback')
        require({readback.key(end) for end in readback.ends(document) if end.contents[12].value is model}
                == {key for key in members if key[0] == document}, 'Unexpected shared station association after reload')
        for key, kind in members.items():
            if key[0] != document:
                continue
            end = readback.model(key)
            require(end.contents[20].value == kind and end.contents[12].value is model,
                    'Shared station member or stop reference failed readback')
            end.contents[12].value = None
            end.contents[20].value = 1
        writer.set_elements(root.contents[2].value, [obj for obj in readback.models[document] if obj is not model])
        original, version = writer.load_next_compatible(documents[document])
        require(writer.dump_verified(root, readback.versions[document]) == writer.dump_verified(original, version),
                'Cross-worksheet platform changed an unselected native field')

    verified = area_layout(open_project(output, paths), spans, station_binding.direction, source)
    require(verified == (reference, connections, anchors, members, blocks),
            'The native platform direction, connector order or through-signal ownership changed after readback')
    station_data, added = native_catalog(catalog, sign, name)
    return output, station_data, {
        **source, 'sight_m': int(source['sight_m']) if source['sight_m'] is not None else None,
        'platform_edge_id': station_binding.platform_edge_id, 'stop_post_id': station_binding.stop_post_id,
        'area_length_m': int(abs(finish-origin)), 'stopping_edge': list(spans[-1].edge),
        'area_edges': [{'document': span.edge[0], 'edge_id': span.edge[1], 'length_m': int(span.high-span.low)}
                       for span in spans],
        'reference_end': list(reference), 'direction': station_binding.direction,
        'reciprocal_connectors': [list(key) for pair in connections for key in pair],
        'reciprocal_connector_pairs': [[list(key) for key in pair] for pair in connections],
        'interior_block_signals': interior,
        'ordinary_members': [list(key) for key in sorted(members) if members[key] == 1],
        'reference_members': [list(key) for key in sorted(members) if members[key] == 2],
        'local_station_model_ids': {key: model.contents[0].value for key, model in owned.items()},
        'single_catalog_identity': True, 'station_catalog_row_added': added, 'native_graph_readback_verified': True,
    }
