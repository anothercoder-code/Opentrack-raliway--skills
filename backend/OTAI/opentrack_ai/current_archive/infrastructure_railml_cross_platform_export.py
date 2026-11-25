"""Export one native corridor and its full cross-worksheet RailML platform."""

from types import SimpleNamespace
from xml.etree import ElementTree as ET

from . import catalogs, route_factory, writer
from .infrastructure_railml import MAX_MEMBER_BYTES, railml_inventory, railml_path as tag, railml_tracks, railml_tree
from .infrastructure_railml_cross_platform import (
    apply_cross_platform, area_layout, open_project, platform_source, span_track, station_model, worksheet_order,
)
from .infrastructure_railml_export import container
from .infrastructure_railml_facilities import require, selected, text
from .infrastructure_railml_geometry import Geometry, node
from .multi_document.core import sha
from .zero_operations import station_binding as sb


def corridor_geometry(project, binding, speed_train_type, speed_profiles):
    traces = {document: [] for document in worksheet_order(project, binding)}
    for link in binding.edges:
        traces[link.document].append(link)
    tracks = [(document, SimpleNamespace(track_id=f'SourceSheet{index}', edges=links))
              for index, (document, links) in enumerate(traces.items())]
    pairs = []
    for document in traces:
        for end in project.ends(document):
            if writer.kind(end) != 'OTConnModel':
                continue
            key = project.key(end)
            other = project.block_end(key)
            if key < other:
                pairs.append((project.related(key), project.related(other)))
    geometry = Geometry(project.byid, tracks, speed_train_type, pairs, speed_profiles=speed_profiles)
    geometry.join_document_track(binding.track_id)
    return geometry.render()


def read_selected_platform(project, spans, catalog, station):
    sign = station.station_sign
    owned, actual = {}, {}
    for document, root in project.roots.items():
        candidates = [model for model in writer.objects(root) if writer.kind(model) == 'OTStationModel'
                      and catalogs.text(model.contents[7].value) == sign]
        require(len(candidates) <= 1 and all(item in project.models[document] for item in candidates),
                'The station sign must name a unique, local StationModel in each participating worksheet')
        if not candidates:
            continue
        model = candidates[0]
        route_factory.layout(model, 'OTStationModel', 1, sb.MODEL, graphic=True)
        owned[document] = model
        for end in project.ends(document):
            if end.contents[12].value is model:
                actual[project.key(end)] = end.contents[20].value
    direction = station.direction
    up = direction == 'up'
    ordered = spans if up else spans[::-1]
    references = [index for index, span in enumerate(ordered) if actual.get(span.end if up else span.start) == 2]
    require(len(references) == 1, 'The selected corridor must approach one exact directed native stopping reference')
    idx = references[0]
    left = idx
    while left >= 0 and ordered[left].start in actual and ordered[left].end in actual:
        left -= 1
    area = ordered[left+1:idx+1]
    require(area, 'Selected native stopping reference has no platform approach')
    reference = area[-1].end if up else area[-1].start
    signal = project.model(reference).contents[11].value
    require(signal is not None and writer.kind(signal) == 'OTSignalModel', 'The native stopping reference needs its physical exit signal')
    catalog_root, _ = writer.load_next_compatible(catalog)
    record = selected(catalogs.station_items(catalog_root), sign, 'station catalog record')
    signal_data = {'signal_name': text(catalogs.text(signal.contents[13].value)), 'sight_m': signal.contents[9].values[1]}
    checked, connectors, anchors, members, blocks = area_layout(project, area, direction, signal_data)
    require(checked == reference and members == actual and set(anchors) == set(owned),
            'Selected scope does not cover all exact native station associations')
    for document, model in owned.items():
        checked_model = station_model(model.contents[0].value, sign, project.model(anchors[document]))
        require(writer.dump_verified(model) == writer.dump_verified(checked_model),
                'Native StationModel attributes or placement differ from the supported cross-worksheet profile')
    return (area[0].low if up else area[0].high, area[-1].high if up else area[-1].low,
            checked, connectors, owned, members, text(catalogs.text(record.contents[2].value)), signal_data, blocks)


def remove_platform(project, owned, members):
    for key in members:
        model = project.model(key)
        model.contents[12].value = None
        model.contents[20].value = 1
    baseline = dict(project.blobs)
    for document, station in owned.items():
        root = project.roots[document]
        writer.set_elements(root.contents[2].value, [model for model in project.models[document] if model is not station])
        require(station not in writer.objects(root), 'A native reference outside the selected platform still owns its StationModel')
        baseline[document] = writer.dump_verified(root, project.versions[document])
    return baseline


def export_cross_platform(documents, paths, catalog, track_binding, station, speed_train_type, *, speed_profiles=None):
    project = open_project(documents, paths)
    geometry, engineering = corridor_geometry(project, track_binding, speed_train_type, speed_profiles)
    root = railml_tree(geometry)
    infra, (track,) = railml_tracks(root)
    spans = span_track(project, track, track_binding)
    origin, finish, reference, connectors, owned, members, name, signal, blocks = read_selected_platform(project, spans, catalog, station)
    used = {item.get('id') for item in root.iter()}
    requested = [station.ocp_id, station.cross_section_id, station.platform_edge_id, station.exit_signal_id]
    if station.stop_post_id is not None:
        requested.append(station.stop_post_id)
    block_ids = [f'OTX_platform_block{index}' for index in range(len(blocks))]
    requested.extend(block_ids)
    require(len(set(requested)) == len(requested) and not (set(requested) & used), 'RailML facility ID is duplicated or already in the geometry')
    node(container(infra, 'operationControlPoints'), 'ocp', id=station.ocp_id, code=station.station_sign, name=name)
    node(container(container(track, 'trackTopology'), 'crossSections'), 'crossSection',
         id=station.cross_section_id, pos=finish, ocpRef=station.ocp_id)
    node(container(container(track, 'trackElements'), 'platformEdges'), 'platformEdge',
         id=station.platform_edge_id, pos=origin, length=abs(finish-origin), dir=station.direction, ocpRef=station.ocp_id)
    ocs = container(track, 'ocsElements')
    signals = container(ocs, 'signals')
    for block, block_id in zip(blocks, block_ids, strict=True):
        node(signals, 'signal', id=block_id, name=block['signal_name'], pos=block['position'], dir=station.direction,
             type='main', function='blocking', sight=block['sight_m'], virtual='false')
    node(signals, 'signal', id=station.exit_signal_id, name=signal['signal_name'], pos=finish,
         dir=station.direction, type='main', function='exit', sight=signal['sight_m'], virtual='false')
    if station.stop_post_id is not None:
        stop = node(container(ocs, 'stopPosts'), 'stopPost', id=station.stop_post_id, pos=finish, dir=station.direction,
                    platformEdgeRef=station.platform_edge_id, ocpRef=station.ocp_id, virtual='false')
        node(stop, 'signalRef', ref=station.exit_signal_id)
    exchange = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    require(len(exchange) <= MAX_MEMBER_BYTES, 'Generated cross-worksheet RailML exceeds 20 MiB')
    _, _, _, source = platform_source(exchange, track_binding, station)
    require(source['sign'] == station.station_sign and source['name'] == name, 'Exported RailML station identity differs at readback')
    baseline = remove_platform(project, owned, members)
    output, verified_catalog, facility = apply_cross_platform(exchange, baseline, paths, catalog, track_binding, station)
    require(facility['reference_end'] == list(reference)
            and facility['reciprocal_connector_pairs'] == [[list(key) for key in pair] for pair in connectors]
            and facility['interior_block_signals'] == [{**block, 'position': int(block['position']),
                 'railml_signal_id': block_id} for block, block_id in zip(blocks, block_ids, strict=True)]
            and facility['reference_members'] == [list(key) for key in sorted(members) if members[key] == 2]
            and facility['ordinary_members'] == [list(key) for key in sorted(members) if members[key] == 1]
            and catalog == verified_catalog, 'The exact directed native facility layout or station catalog was not recovered')
    return exchange, {
        'whole_native_worksheet_corridor_exported': True, 'original_connector_represented_as_internal_track_boundary': True,
        'geometry_template_required': False, 'output_inventory': railml_inventory(exchange), 'engineering': engineering,
        'selected_speed_profiles': speed_profiles or None, 'selected_speed_category': None if speed_profiles else speed_train_type,
        'source_facility': facility,
        'reimport': {'native_layout_verified': True, 'catalog_byte_identical': True,
                     'worksheet_bytes_match': {key: document == output[key] for key, document in documents.items()},
                     'worksheet_seed_sha256': {key: sha(document) for key, document in baseline.items()},
                     'worksheet_restored_sha256': {key: sha(document) for key, document in output.items()},
                     'native_catalog_sha256': sha(verified_catalog)},
    }
