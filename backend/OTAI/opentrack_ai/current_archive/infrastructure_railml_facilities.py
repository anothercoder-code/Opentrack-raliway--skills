"""Map selected RailML 2.2 facility records to a fresh ordinary native sheet."""

from dataclasses import dataclass
from decimal import Decimal
import re
from xml.etree import ElementTree

from . import catalogs, writer
from .infrastructure_railml import RAILML_NAMESPACE, railml_path as tag, railml_tracks, railml_tree
from .infrastructure_railml_areas import area_details, area_entries, area_stop, bind_areas, platform_spans
from .multi_document.generate import placement, signal_placement
from .zero_generation import native_signal_routes as signals
from .zero_operations.station_binding import read_document as read_empty_sheet, text


KINDS = {
    'crossSection': ('trackTopology', 'crossSections'),
    'platformEdge': ('trackElements', 'platformEdges'),
    'signal': ('ocsElements', 'signals'),
    'stopPost': ('ocsElements', 'stopPosts'),
}
POSITION = re.compile(r'[+-]?(?:[0-9]{1,10}(?:\.[0-9]{0,12})?|\.[0-9]{1,12})')
COMMON = {'id', 'name', 'pos', 'absPos', 'absPosOffset', 'description'}
REPORT_SAMPLE = 100
RAILML_SIGNAL_TYPES = {'main': 1, 'combined': 2, 'distant': 3, 'shunting': 4}
RAILML_SIGNAL_ROLES = {'home': 2, 'blocking': 3, 'exit': 4}
NATIVE_SIGNAL_TYPES = {code: name for name, code in RAILML_SIGNAL_TYPES.items()}
NATIVE_SIGNAL_ROLES = {code: name for name, code in RAILML_SIGNAL_ROLES.items()}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def measurement(element, attr):
    value = element.get(attr, '')
    if POSITION.fullmatch(value) is None:
        raise ValueError(f'{element.get("id")!r} requires a bounded decimal {attr}')
    return Decimal(value)


def unique_nodes(nodes):
    indexed = {}
    for node in nodes:
        identity = node.get('id')
        require(identity and len(identity) <= 200 and identity not in indexed,
                f'Missing, oversized or duplicate RailML facility ID {str(identity)[:200]!r}')
        indexed[identity] = node
    return indexed


def selected(nodes, identity, kind):
    require(identity in nodes, f'Unknown RailML {kind} ID {identity!r}')
    return nodes[identity]


def fields(node, supported, child_tags=()):
    extra = sorted(set(node.attrib) - COMMON - supported)
    require(not extra and all(child.tag in child_tags for child in node),
            f'Unsupported selected facility fields at {node.get("id")!r}: {extra or "nested elements"}')


def check_rewrite_namespaces(root):
    # Projection rewrites XML namespace prefixes. Do not rewrite QName-valued or
    # extension content whose reference syntax is outside the bridge contract.
    allowed_ns = {RAILML_NAMESPACE, 'http://purl.org/dc/elements/1.1/'}
    allowed_attrs = {'{http://www.w3.org/2001/XMLSchema-instance}schemaLocation'}
    require(all(node.tag.split('}')[0][1:] in allowed_ns and
                all(not key.startswith('{') or key in allowed_attrs for key in node.attrib)
                for node in root.iter()), 'RailML rewrite requires original metadata without extension elements/attributes')


def project_geometry(railml):
    """Create a temporary geometry-only bridge view of one original source."""
    root = railml_tree(railml)
    infra, tracks = railml_tracks(root)
    check_rewrite_namespaces(root)
    removed = {}

    def detach(parent, container, child):
        matches = parent.findall(tag(container))
        require(len(matches) <= 1, f'Duplicate RailML {container} container')
        if not matches:
            return
        section = matches[0]
        require(not section.attrib and all(node.tag == tag(child) for node in section),
                f'Unsupported content in projected {container} container')
        identities = unique_nodes(section)
        overlap = set(identities) & removed.keys()
        require(not overlap, f'A projected RailML facility ID is aliased: {sorted(overlap)}')
        removed.update(dict.fromkeys(identities, child))
        parent.remove(section)

    detach(infra, 'operationControlPoints', 'ocp')
    for track in tracks:
        for child, (parent_name, container) in KINDS.items():
            for parent in track.findall(tag(parent_name)):
                detach(parent, container, child)

    visualizations = root.find(tag('infrastructureVisualizations'))
    if visualizations is not None:
        for parent in visualizations.iter():
            for node in list(parent):
                if node.tag in (tag('trackElementVis'), tag('ocpVis')) and node.get('ref') in removed:
                    parent.remove(node)
    for node in root.iter():
        for key, value in node.attrib.items():
            if key in ('ref', 'id') or key.endswith('Ref'):
                require(value not in removed, f'Other RailML data still uses projected facility {value!r}')

    output = ElementTree.tostring(root, encoding='utf-8', xml_declaration=True)
    rows = {key: sorted(ident for ident, kind in removed.items() if kind == key) for key in ('ocp', *KINDS)}
    return output, {'removed_facility_counts': {key: len(values) for key, values in rows.items()},
                    'removed_facility_ids': {key: values[:REPORT_SAMPLE] for key, values in rows.items()}}


@dataclass(frozen=True)
class Span:
    low: Decimal
    high: Decimal
    edge: int
    start: int
    finish: int


def position_sheet(tracks, bindings, byid, track_extents=None):
    """Bind an ordered measured trace, or one reviewed worksheet partition of it."""
    result, used = {}, set()
    for binding in bindings:
        track_id = binding.track_id
        track = selected(tracks, track_id, 'track')
        require(track_id not in result, f'Multiple native traces for RailML track {track_id!r}')
        begin, end = (track.findall(tag('trackTopology', node)) for node in ('trackBegin', 'trackEnd'))
        require(len(begin) == len(end) == 1, f'Track {track_id!r} requires one begin and end')
        cursor, limit = measurement(begin[0], 'pos'), measurement(end[0], 'pos')
        if track_extents is not None:
            start, finish = selected(track_extents, track_id, 'reviewed worksheet track extent')
            require(cursor <= start < finish <= limit, 'Reviewed worksheet trace lies outside the source RailML track')
            cursor, limit = start, finish
        spans = []
        for link in binding.edges:
            edge = byid.get(link.edge_id)
            require(edge is not None and writer.kind(edge) == 'OTEdgeModel' and link.edge_id not in used,
                    f'Unknown or reused native Edge {link.edge_id}')
            ends = {edge.contents[i].value.contents[0].value for i in (7, 8)}
            require(link.start_end_id in ends, f'Edge {link.edge_id} has no specified start End {link.start_end_id}')
            start, finish = link.start_end_id, next(iter(ends - {link.start_end_id}))
            require(not spans or byid[spans[-1].finish].contents[8].value == start,
                    f'Native trace for RailML track {track_id!r} is disconnected at Edge {link.edge_id}')
            track_name = writer.string(edge.contents[19].value)
            require(not track_name or not track.get('name') or track_name == track.get('name'),
                    f'Native Edge {link.edge_id} track name differs from RailML track {track_id!r}')
            length = edge.contents[9].values[1]
            spans.append(Span(cursor, cursor + length, link.edge_id, start, finish))
            cursor += length
            used.add(link.edge_id)
        require(cursor == limit, f'Native trace length differs from RailML track {track_id!r}')
        result[track_id] = spans
    return result


def facing_end(spans, position, direction, byid):
    # A native boundary has two reciprocal halves. Select the arrival-side half.
    for span in spans:
        if position == span.low:
            return byid[span.start].contents[8].value if direction == 'up' else span.start
        if position == span.high:
            return span.finish if direction == 'up' else byid[span.finish].contents[8].value
    raise ValueError(f'RailML position {position} is not a mapped native Edge boundary')


def xy(end):
    return float(end.contents[2].value), float(end.contents[3].value)


def mapped_stop(station, track_id, cross, reference, spans, nodes, signal_rows, byid):
    platform_track, platform = selected(nodes['platformEdge'], station.platform_edge_id, 'platformEdge')
    fields(platform, {'ocpRef', 'dir', 'length', 'side', 'height'})
    direction = station.direction
    require(platform_track == track_id and platform.get('ocpRef') == cross.get('ocpRef') and
            platform.get('dir', direction) == direction,
            'The platform and cross section must share a RailML track/OCP and agree with the mapped direction')
    length = measurement(platform, 'length')
    origin = measurement(platform, 'pos')
    finish = origin + length if direction == 'up' else origin - length
    require(length > 0 and finish == measurement(cross, 'pos'),
            'Platform length and direction must terminate exactly at the cross section')
    area = platform_spans(spans, origin, finish, direction)
    entries = area_entries(area, direction, byid)
    signal = selected(signal_rows, station.exit_signal_id, 'selected exit signal')
    require(is_platform_exit(signal), 'The platform stopping signal must be a physical main or combined exit signal')
    require((signal['track_id'], signal['direction'], signal['end_id']) == (track_id, direction, reference),
            'Selected platform exit signal must be at the exact cross-section position and direction')
    if station.stop_post_id is not None:
        post_track, post = selected(nodes['stopPost'], station.stop_post_id, 'stopPost')
        fields(post, {'dir', 'platformEdgeRef', 'ocpRef', 'virtual'}, (tag('signalRef'),))
        signal_refs = post.findall(tag('signalRef'))
        require(all(set(row.attrib) == {'ref'} and not len(row) for row in signal_refs),
                'Unsupported selected stop-post signal reference fields')
        require(post_track == track_id and post.get('platformEdgeRef') == station.platform_edge_id and
                post.get('ocpRef', cross.get('ocpRef')) == cross.get('ocpRef') and
                post.get('dir') == direction and post.get('virtual', 'false') in ('false', '0') and
                measurement(post, 'pos') == finish and
                (not signal_refs or [row.get('ref') for row in signal_refs] == [station.exit_signal_id]),
                'Selected stop post must refer to this platform and its single physical exit position')
    stop = area_stop(entries, reference, area, signal)
    details = {'platform_edge_id': station.platform_edge_id, 'stop_post_id': station.stop_post_id,
               'exit_signal_id': station.exit_signal_id, 'railml_side': platform.get('side'),
               'railml_height_mm': platform.get('height'), **area_details(entries, stop, byid)}
    return entries, stop, details


def station_groups(station_bindings, rows):
    groups, explicit = {}, set()
    for binding in station_bindings:
        row = rows[binding.cross_section_id]
        sign, track = row['sign'], row['track_id']
        group = groups.setdefault(sign, {'ocp_id': row['ocp_id'], 'anchor_reference_end_id': row['reference_end_id'],
                                         'tracks': [], 'references': [], 'platform_track_names': []})
        require(group['ocp_id'] == row['ocp_id'], f'RailML OCP IDs sharing native station sign {sign!r} must be identical')
        require(track not in group['tracks'], f'Shared station {sign!r} requires distinct mapped physical tracks')
        group['tracks'].append(track)
        group['references'].append(row['reference_end_id'])
        if binding.platform_edge_id is not None:
            group['platform_track_names'].append(row['native_track_name'])
        if binding.station_anchor:
            require(sign not in explicit, f'Shared station {sign!r} has more than one explicit anchor')
            explicit.add(sign)
            group['anchor_reference_end_id'] = row['reference_end_id']
    for sign, group in groups.items():
        labels = group['platform_track_names']
        require(len(labels) < 2 or (all(labels) and len(set(labels)) == len(labels)),
                f'Shared station {sign!r} requires distinct saved native platform track names')
    return groups, {sign: group['anchor_reference_end_id'] for sign, group in groups.items()}


def decode_signal_profile(source):
    signal_type = source.get('type')
    if signal_type == 'repeater':
        signal_type = 'distant'  # The original importer writes the same native type for both.
    require(signal_type in RAILML_SIGNAL_TYPES, 'Unsupported selected RailML signal type')
    native_type = RAILML_SIGNAL_TYPES[signal_type]
    function = source.get('function')
    if native_type in (1, 2):
        require(function in RAILML_SIGNAL_ROLES, 'Main and combined signals require home, blocking or exit function')
        native_role = RAILML_SIGNAL_ROLES[function]
    else:
        require(function is None, 'Distant and shunting signals have no mapped RailML main signal function')
        native_role = 1
    virtual = source.get('virtual', 'false')
    require(virtual in ('false', 'true', '0', '1'), 'RailML virtual flag must be a boolean')
    return native_type, native_role, virtual in ('true', '1')


def signal_fields(native_type, native_role, virtual):
    return {'type': NATIVE_SIGNAL_TYPES[native_type], 'function': NATIVE_SIGNAL_ROLES.get(native_role),
            'virtual': virtual}


def is_platform_exit(signal_row):
    return signal_row['type'] in ('main', 'combined') and signal_row['function'] == 'exit' and not signal_row['virtual']


def checked_signal(byid, end_id, model_id, name, sight, profile):
    end = byid[end_id]
    signal = byid.get(model_id)
    signal_type, role, virtual = profile
    require(signal is not None and writer.kind(signal) == 'OTSignalModel'
            and signal.contents[8].values[:2] == [signal_type, role]
            and bool(signal.contents[9].values[2] & 2) == virtual
            and end.contents[11].value is signal and signal.contents[7].value is end
            and catalogs.text(signal.contents[13].value) == name and signal.contents[9].values[1] == sight,
            'The existing native signal must match the exact End, name, sight, type, role and virtual flag')


def apply_facilities(railml, document, track_bindings, signal_bindings, station_bindings, *, track_extents=None):
    infra, tracks = railml_tracks(railml_tree(railml))
    ocps = unique_nodes(infra.findall(tag('operationControlPoints', 'ocp')))
    nodes = {}
    for kind, path in KINDS.items():
        owner = {node: track.get('id') for track in tracks for node in track.findall(tag(*path, kind))}
        nodes[kind] = {identity: (owner[node], node) for identity, node in unique_nodes(owner).items()}
    root, _, _, byid = read_empty_sheet(document)
    signals.validate_topology(root)
    traces = position_sheet(unique_nodes(tracks), track_bindings, byid, track_extents)
    present = set()
    signal_rows = {}
    signal_profiles = {}
    selected_signal_ends = set()
    result_doc, next_id = document, max(byid) + 1
    for binding in signal_bindings:
        track_id, source = selected(nodes['signal'], binding.signal_id, 'signal')
        require(binding.signal_id not in signal_rows, f'Duplicate selected signal {binding.signal_id!r}')
        fields(source, {'dir', 'type', 'function', 'sight', 'virtual'})
        profile = decode_signal_profile(source)
        native_type, role, virtual = profile
        direction = source.get('dir')
        require(direction in ('up', 'down'), 'Selected RailML signal needs one exact direction')
        spans = selected(traces, track_id, 'mapped track')
        end = facing_end(spans, measurement(source, 'pos'), direction, byid)
        require(end not in selected_signal_ends, 'Two selected RailML signals map to the same directional End')
        selected_signal_ends.add(end)
        name = text(source.get('name') or binding.signal_id)
        sight = measurement(source, 'sight') if 'sight' in source.attrib else binding.fallback_sight_m
        require(sight is not None and int(sight) == sight and 1 <= sight <= 100000,
                'Signal sight must use whole meters in 1..100000, with an explicit fallback when absent')
        reused_id = getattr(binding, 'existing_model_id', None)
        if reused_id is None:
            model_id = next_id
            next_id += 1
            result_doc, _ = signals.build_signal(
                result_doc, end_id=end, name=name, model_id=model_id,
                placement=signal_placement(byid[end], *xy(byid[end])), sight_m=int(sight),
                delay_s=0, show_symbol=True, show_icon=True,
                signal_type=native_type, main_type=role, virtual=virtual,
            )
        else:
            model_id = reused_id
            checked_signal(byid, end, model_id, name, int(sight), profile)
        signal_profiles[binding.signal_id] = profile
        signal_rows[binding.signal_id] = {'track_id': track_id, 'direction': direction, 'end_id': end,
                                         'model_id': model_id, 'name': name, 'sight_m': int(sight),
                                         **signal_fields(*profile),
                                         'source_railml_type': source.get('type'),
                                         'sight_source': 'railml' if 'sight' in source.attrib else 'explicit_fallback'}
        if reused_id is not None:
            signal_rows[binding.signal_id]['reused_existing_model'] = True
    specs, station_rows = [], {}
    for station in station_bindings:
        track_id, cross = selected(nodes['crossSection'], station.cross_section_id, 'crossSection')
        require(station.cross_section_id not in station_rows, f'Duplicate selected cross section {station.cross_section_id!r}')
        fields(cross, {'ocpRef', 'dir'})
        require(cross.get('dir', station.direction) == station.direction, 'Cross-section direction conflicts with its native mapping')
        ocp_id = cross.get('ocpRef')
        ocp = selected(ocps, ocp_id, 'OCP')
        sign, name = text(ocp.get('code') or ocp_id), text(ocp.get('name') or ocp_id)
        spans = selected(traces, track_id, 'mapped track')
        reference = facing_end(spans, measurement(cross, 'pos'), station.direction, byid)
        spec = {'sign': sign, 'name': name, 'reference_end_id': reference, 'ordinary_end_ids': [],
                'placement': placement(*xy(byid[reference])), 'station_type_raw': 2, 'interlock_type_raw': 4,
                'icon_show_type_raw': 1, 'timing_point': True, 'stop': None}
        row = {'ocp_id': ocp_id, 'sign': sign, 'name': name, 'track_id': track_id,
               'direction': station.direction, 'reference_end_id': reference}
        if station.platform_edge_id is not None:
            require(station.platform_edge_id not in present, 'A RailML platform is selected by multiple stations')
            entries, stop, details = mapped_stop(station, track_id, cross, reference, spans, nodes, signal_rows, byid)
            spec.update(ordinary_end_ids=entries, stop=stop)
            row.update(details)
            present.add(station.platform_edge_id)
        specs.append(spec)
        station_rows[station.cross_section_id] = row
    groups, anchors = station_groups(station_bindings, station_rows)
    if specs:
        result_doc, station_catalog, check = bind_areas(result_doc, specs, anchors)
    else:
        station_catalog, check = None, None
    output, _, _, observed = signals.document(result_doc)
    signals.validate_topology(output)
    for signal_id, row in signal_rows.items():
        checked_signal(observed, row['end_id'], row['model_id'], row['name'], row['sight_m'], signal_profiles[signal_id])
    used_posts = {station.stop_post_id for station in station_bindings}
    unused = {'crossSection': set(nodes['crossSection']) - station_rows.keys(),
              'platformEdge': set(nodes['platformEdge']) - present,
              'signal': set(nodes['signal']) - signal_rows.keys(), 'stopPost': set(nodes['stopPost']) - used_posts}
    return result_doc, station_catalog, {'native_readback_verified': True, 'source_station_cross_sections': station_rows,
                                         'native_station_groups': groups,
                                         'source_signals': signal_rows, 'station_readback': check,
                                         'unselected_facility_counts': {key: len(values) for key, values in unused.items()},
                                         'unselected_facilities': {key: sorted(values)[:REPORT_SAMPLE]
                                                                   for key, values in unused.items()}}
