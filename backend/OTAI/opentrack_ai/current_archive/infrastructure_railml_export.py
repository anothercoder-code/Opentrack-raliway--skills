"""Compose RailML 2.2 geometry with the reviewed facility subset from a native sheet."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from xml.etree import ElementTree as ET

from . import catalogs, route_factory, writer
from .graphic_alignment import validate_generated_signal_alignment
from .infrastructure_railml import MAX_MEMBER_BYTES, railml_inventory, railml_path as tag, railml_tracks, railml_tree
from .infrastructure_railml_areas import area_details, area_entries, area_snapshot, area_stop, platform_spans
from .infrastructure_railml_facilities import (
    KINDS, NATIVE_SIGNAL_ROLES, NATIVE_SIGNAL_TYPES, apply_facilities, check_rewrite_namespaces, is_platform_exit,
    measurement, position_sheet, require, selected, signal_fields, station_groups, text, unique_nodes, xy,
)
from .multi_document.generate import placement
from .zero_generation import native_signal_routes as native


BEFORE = {
    'operationControlPoints': ('controllers', 'speedProfiles'),
    'trackElements': ('ocsElements',), 'crossSections': ('borders',), 'platformEdges': ('serviceSections',),
    'signals': ('trainDetectionElements', 'balises', 'trainProtectionElements', 'stopPosts', 'derailers'),
    'stopPosts': ('derailers',),
}
EMPTY_CONTAINERS = {tag(name) for name in (*BEFORE, 'ocsElements')}


def container(parent, name):
    matches = parent.findall(tag(name))
    require(len(matches) <= 1, f'Duplicate RailML {name} container')
    if matches:
        return matches[0]
    new = ET.Element(tag(name))
    before = {tag(item) for item in BEFORE.get(name, ())}
    index = next((i for i, child in enumerate(parent) if child.tag in before), len(parent))
    parent.insert(index, new)
    return new


def tree_signature(node, ignored):
    """Compare unselected document content while allowing new facility containers."""
    if node.get('id') in ignored:
        return None
    children = tuple(item for child in node if (item := tree_signature(child, ignored)) is not None)
    attrs, content = tuple(sorted(node.attrib.items())), (node.text or '').strip()
    if node.tag in EMPTY_CONTAINERS and not children and not attrs and not content:
        return None
    return node.tag, attrs, content, (node.tail or '').strip(), children


def mapped_positions(spans, direction, byid):
    result = defaultdict(list)
    if direction == 'up':
        first = spans[0]
        result[byid[first.start].contents[8].value].append(first.low)
        for span in spans:
            result[span.finish].append(span.high)
    else:
        for span in spans:
            result[span.start].append(span.low)
        last = spans[-1]
        result[byid[last.finish].contents[8].value].append(last.high)
    return result


def verify_direct_connections(tracks, traces, byid):
    """Validate reciprocal track-boundary links with both sides in the mapping."""
    connections = {}
    for track_id, spans in traces.items():
        for boundary, end in (('trackBegin', spans[0].start), ('trackEnd', spans[-1].finish)):
            links = tracks[track_id].findall(tag('trackTopology', boundary, 'connection'))
            require(len(links) <= 1, f'Multiple RailML connections on {track_id!r} {boundary}')
            if links:
                link = links[0]
                name, ref = link.get('id'), link.get('ref')
                require(name and ref and name != ref and name not in connections, 'Duplicate or invalid RailML boundary link')
                connections[name] = (ref, end)
    checked = set()
    for name, (ref, end) in connections.items():
        if ref not in connections or name in checked:
            continue
        following, peer = connections[ref]
        require(following == name and byid[end].contents[8].value == peer,
                f'RailML boundary link {name!r} differs from the native reciprocal End connection')
        checked.update((name, ref))
    return len(checked) // 2


class Composer:
    def __init__(self, railml, bindings, byid):
        self.root = railml_tree(railml)
        self.infra, tracks = railml_tracks(self.root)
        check_rewrite_namespaces(self.root)
        self.tracks = unique_nodes(tracks)
        self.traces = position_sheet(self.tracks, bindings, byid)
        self.direct_connections = verify_direct_connections(self.tracks, self.traces, byid)
        self.positions = {(key, direction): mapped_positions(spans, direction, byid)
                          for key, spans in self.traces.items() for direction in ('up', 'down')}
        self.baseline = railml_tree(railml)
        self.ids = defaultdict(list)
        for node in self.root.iter():
            if 'id' in node.attrib:
                self.ids[node.get('id')].append(node)
        self.visual_refs = {node.get('ref') for name in ('trackElementVis', 'ocpVis') for node in self.root.iter(tag(name))}
        self.used = set()

    def position(self, track_id, direction, end_ids):
        allowed = selected(self.positions, (track_id, direction), 'mapped track/direction')
        candidates = [(end, pos) for end in end_ids for pos in allowed.get(end, ())]
        require(len(candidates) == 1, f'Expected one mapped boundary for native Ends {end_ids} on {track_id!r}')
        return candidates[0]

    def write(self, identity, kind, attrs, track_id=None):
        require(identity not in self.used, f'Duplicate selected output facility ID {identity!r}')
        self.used.add(identity)
        if kind == 'ocp':
            parent = container(self.infra, 'operationControlPoints')
        else:
            track = self.tracks[track_id]
            branch, nest = KINDS[kind]
            parent = container(container(track, branch), nest)
        matches = self.ids.get(identity, [])
        if matches:
            require(len(matches) == 1 and matches[0] in parent and matches[0].tag == tag(kind),
                    f'Existing RailML ID {identity!r} belongs to another path, type or record')
            node = matches[0]
            if 'pos' in attrs and (identity in self.visual_refs or any(key in node.attrib for key in ('absPos', 'absPosOffset'))):
                require(measurement(node, 'pos') == attrs['pos'], f'Relocated facility {identity!r} needs an updated position template')
        else:
            node = ET.SubElement(parent, tag(kind), {'id': identity})
            self.ids[identity] = [node]
        for key, value in attrs.items():
            node.set(key, format(value, 'f') if isinstance(value, Decimal) else str(value))
        return node

    def finish(self):
        result = ET.tostring(self.root, encoding='utf-8', xml_declaration=True)
        require(len(result) <= MAX_MEMBER_BYTES, 'Generated RailML XML exceeds 20 MiB')
        require(tree_signature(railml_tree(result), self.used) == tree_signature(self.baseline, self.used),
                'Unselected RailML branch or geometry changed')
        return result


def model_id(model):
    return model.contents[0].value


def native_station_members(models):
    member_by_station = defaultdict(list)
    stations = {}
    for model in models:
        if writer.kind(model) == 'OTStationModel':
            sign = text(catalogs.text(model.contents[7].value))
            require(sign not in stations, f'Duplicate native station sign {sign!r}')
            stations[sign] = model
        if writer.kind(model) == 'OTEndModel' and model.contents[12].value is not None:
            member_by_station[model.contents[12].value].append(model)
    return stations, member_by_station


def read_signal(binding, composer, byid):
    _, pos = composer.position(binding.track_id, binding.direction, [binding.end_id])
    end = byid[binding.end_id]
    signal = end.contents[11].value
    require(signal is not None and writer.kind(signal) == 'OTSignalModel', f'No native signal at End {binding.end_id}')
    validate_generated_signal_alignment(signal)
    native_type, role, location = signal.contents[8].values
    _, sight, flags, _ = signal.contents[9].values
    virtual = bool(flags & 2)
    require(native_type in NATIVE_SIGNAL_TYPES
            and (role in NATIVE_SIGNAL_ROLES if native_type in (1, 2) else role == 1),
            f'Native signal at End {binding.end_id} has an unsupported type or function')
    inds = route_factory.wrapper(signal.contents[10].value, 'OTSigIndList')
    require(signal.contents[1].value == 0 and xy(signal) == xy(end) and signal.contents[6].value is None and
            location == 2 and signal.contents[9].values == [2, sight, 644 | (2 if virtual else 0), 0] and
            type(sight) is int and 1 <= sight <= 100000 and len(inds) == 1 and inds[0].contents[0].value == 0 and
            signal.contents[11].value == 0 and signal.contents[12].value == 7 and signal.contents[16].value == 0 and
            all(not catalogs.array(signal.contents[slot].value) for slot in (14, 15)),
            f'Native signal at End {binding.end_id} differs from the reimportable RailML signal profile')
    name = text(catalogs.text(signal.contents[13].value))
    fields = signal_fields(native_type, role, virtual)
    attrs = {'pos': pos, 'dir': binding.direction, 'name': name, 'type': fields['type'],
             'sight': sight, 'virtual': 'true' if virtual else 'false'}
    if fields['function'] is not None:
        attrs['function'] = fields['function']
    node = composer.write(binding.signal_id, 'signal', attrs, binding.track_id)
    if fields['function'] is None:
        node.attrib.pop('function', None)
    return {'model_id': model_id(signal), 'end_id': binding.end_id, 'name': name, 'sight_m': sight,
            'track_id': binding.track_id, 'direction': binding.direction, **fields}


def read_station(binding, composer, byid, stations, members, catalog, signal_rows):
    sign, tid, direction = binding.station_sign, binding.track_id, binding.direction
    model = selected(stations, sign, 'native StationModel')
    station = selected(catalog, sign, 'native station catalog row')
    ends = members[model]
    refs = [model_id(end) for end in ends if end.contents[20].value == 2]
    ordinary = [model_id(end) for end in ends if end.contents[20].value == 1]
    require(len(refs) >= 2 and len(refs) % 2 == 0 and len(ends) == len(refs) + len(ordinary) and len(ordinary) % 2 == 0,
            f'Station {sign!r} must have complete reference and ordinary pairs')
    ref, pos = composer.position(tid, direction, refs)
    spans = composer.traces[tid]
    positions = selected(composer.positions, (tid, direction), 'mapped track/direction')
    mapped = sorted(((point, end) for end in ordinary for point in positions.get(end, ())),
                    reverse=direction == 'down')
    require(bool(mapped) == (binding.platform_edge_id is not None),
            f'Station {sign!r} and platform request disagree on track {tid!r}')
    name = text(catalogs.text(station.contents[2].value))
    require(model.contents[1].value == 0 and model.contents[6].value is None and
            [model.contents[i].value for i in (4, 5)] == [0, 0], f'Station {sign!r} placement differs from the reviewed profile')
    composer.write(binding.cross_section_id, 'crossSection', {'pos': pos, 'ocpRef': binding.ocp_id}, tid)
    row = {'ocp_id': binding.ocp_id, 'sign': sign, 'name': name, 'reference_end_id': ref,
           'track_id': tid, 'direction': direction}
    spec = {'sign': sign, 'name': name, 'reference_end_id': ref, 'ordinary_end_ids': [], 'placement': placement(*xy(byid[ref])),
            'station_type_raw': 2, 'interlock_type_raw': 4, 'icon_show_type_raw': 1, 'timing_point': True, 'stop': None}
    if mapped:
        require(len({point for point, _ in mapped}) == len(mapped),
                'Every native ordinary platform pair must map to one distinct directed track boundary')
        origin = mapped[0][0]
        require((origin < pos) == (direction == 'up') and origin != pos,
                'Native platform entry and reference oppose the directed RailML track mapping')
        area = platform_spans(spans, origin, pos, direction)
        entry_ids = area_entries(area, direction, byid)
        require(entry_ids == [end for _, end in mapped],
                'Native platform members must follow every complete RailML-mapped Edge in the selected direction')
        exit_signal = selected(signal_rows, binding.exit_signal_id, 'exported exit signal')
        require(is_platform_exit(exit_signal), 'The platform stopping signal must be a physical main or combined exit signal')
        require((exit_signal['track_id'], exit_signal['direction'], exit_signal['end_id']) == (tid, direction, ref),
                'Station exit signal differs from the physical platform reference End')
        stop = area_stop(entry_ids, ref, area, exit_signal)
        length = stop['length_m']
        composer.write(binding.platform_edge_id, 'platformEdge', {'pos': origin, 'dir': direction, 'length': length,
                                                                 'ocpRef': binding.ocp_id}, tid)
        if binding.stop_post_id is not None:
            post = composer.write(binding.stop_post_id, 'stopPost', {'pos': pos, 'dir': direction, 'virtual': 'false',
                                  'ocpRef': binding.ocp_id, 'platformEdgeRef': binding.platform_edge_id}, tid)
            refs = post.findall(tag('signalRef'))
            if refs:
                require(len(refs) == 1 and refs[0].get('ref') == binding.exit_signal_id,
                        'Existing RailML stop post refers to a different exit signal')
            else:
                ET.SubElement(post, tag('signalRef'), {'ref': binding.exit_signal_id})
        spec.update(ordinary_end_ids=entry_ids, stop=stop)
        row.update(**area_details(entry_ids, stop, byid), stop_post_id=binding.stop_post_id,
                   platform_edge_id=binding.platform_edge_id, exit_signal_id=binding.exit_signal_id)
    return row, spec


@dataclass(frozen=True)
class ReplaySignal:
    signal_id: str
    fallback_sight_m: int | None = None


def verify_reimport(document, result, track_bindings, signal_bindings, station_bindings, root, version, models,
                    station_rows, signal_rows, catalog):
    removed = {row['model_id'] for row in signal_rows.values()}
    keep = [model for model in models if model_id(model) not in removed and writer.kind(model) != 'OTStationModel']
    for model in keep:
        if writer.kind(model) == 'OTEndModel':
            model.contents[12].value = None
            model.contents[20].value = 1
            owner = model.contents[11].value
            if owner is not None and model_id(owner) in removed:
                model.contents[11].value = None
    writer.set_elements(root.contents[2].value, keep)
    require(all(writer.kind(model) != 'OTStationModel' and
                (writer.kind(model) != 'OTSignalModel' or model_id(model) not in removed) for model in writer.objects(root)),
            'Other native references still own selected facility objects')
    baseline = writer.dump_verified(root, version)
    replay_signals = [ReplaySignal(binding.signal_id) for binding in signal_bindings]
    restored, catalog_blob, report = apply_facilities(result, baseline, track_bindings, replay_signals, station_bindings)
    for actual, field in ((station_rows, 'source_station_cross_sections'), (signal_rows, 'source_signals')):
        for key, row in actual.items():
            legacy = selected(report[field], key, 'reimported facility')
            require(all(legacy.get(field) == value for field, value in row.items() if field != 'model_id'),
                    f'Native identity or operating position differs on reimport of {key!r}')
    if catalog_blob is not None:
        rows = catalogs.station_items(writer.load_next_compatible(catalog_blob)[0])
        for sign, row in rows.items():
            require(writer.dump_verified(row) == writer.dump_verified(catalog[sign]),
                    f'Station catalog row {sign!r} differs from the exact reimportable native profile')
    return {'verified': True, 'byte_identical_worksheet': restored == document,
            'native_base_worksheet_sha256': sha256(baseline).hexdigest()}


def export_facilities(railml, document, stations, track_bindings, signal_bindings, station_bindings):
    root, version, models, byid = native.document(document)
    native.validate_topology(root)
    composer = Composer(railml, track_bindings, byid)
    station_models, members = native_station_members(models)
    catalog = catalogs.station_items(writer.load_next_compatible(stations)[0]) if stations is not None else {}
    selected_signs = {binding.station_sign for binding in station_bindings}
    require(selected_signs == set(station_models),
            'Export requires one binding for every station graphic on the selected worksheet')
    require(len({binding.end_id for binding in signal_bindings}) == len(signal_bindings), 'Duplicate selected native signal End')
    signal_rows = {binding.signal_id: read_signal(binding, composer, byid) for binding in signal_bindings}
    station_rows, specs = {}, []
    for binding in station_bindings:
        row, spec = read_station(binding, composer, byid, station_models, members, catalog, signal_rows)
        station_rows[binding.cross_section_id] = row
        specs.append(spec)
    groups, anchors = station_groups(station_bindings, station_rows)
    for sign, group in groups.items():
        require(xy(station_models[sign]) == xy(byid[anchors[sign]]),
                f'Station {sign!r} graphic does not match the selected station anchor')
        composer.write(group['ocp_id'], 'ocp', {'code': sign, 'name': text(catalogs.text(catalog[sign].contents[2].value))})
    if specs:
        area_snapshot(document, specs, anchors)
    exported_signal_ids = {row['model_id'] for row in signal_rows.values()}
    unselected_signals = sorted(model_id(model) for model in models if writer.kind(model) == 'OTSignalModel'
                                and model_id(model) not in exported_signal_ids)
    result = composer.finish()
    replay = verify_reimport(document, result, track_bindings, signal_bindings, station_bindings, root, version, models,
                             station_rows, signal_rows, catalog)
    return result, {'reimport': replay, 'geometry_template_preserved': True, 'verified_native_track_count': len(composer.traces),
                    'verified_direct_native_connection_count': composer.direct_connections,
                    'output_inventory': railml_inventory(result), 'source_station_cross_sections': station_rows,
                    'native_station_groups': groups,
                    'source_signals': signal_rows, 'unselected_native_signal_model_ids': unselected_signals,
                    'unselected_catalog_stations': sorted(set(catalog) - selected_signs)[:100]}
