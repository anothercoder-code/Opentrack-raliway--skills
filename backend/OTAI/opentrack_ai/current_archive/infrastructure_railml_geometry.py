"""Export explicitly oriented ordinary Document4 topology as fresh RailML 2.2."""

from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from xml.etree import ElementTree as ET

from . import course_factories, writer
from .infrastructure_railml import railml_inventory, railml_path as tag
from .infrastructure_railml_facilities import require, xy


SCHEMA_LOCATION = '{http://www.w3.org/2001/XMLSchema-instance}schemaLocation'
RAILML_SCHEMA = 'http://www.railml.org/schemas/2013 http://schemas.railml.org/2013/railML-2.2/railML.xsd'
BOUNDARY = ('trackBegin', 'trackEnd')


def node(parent, element, **attributes):
    return ET.SubElement(parent, tag(element), {key: str(value) for key, value in attributes.items()})


def identity(obj):
    return obj.contents[0].value


def clean_decimal(value):
    number = Decimal(str(value))
    require(number.is_finite(), 'Nonfinite native engineering value')
    return format(number.normalize(), 'f')


@dataclass(frozen=True)
class Segment:
    document: str
    edge_id: int
    start: int
    end: int
    low: int
    high: int
    up: tuple[int, ...]
    down: tuple[int, ...]
    slope: float
    radius: float


@dataclass(frozen=True)
class Trace:
    identity: str
    document: str
    name: str
    line: str
    segments: tuple


class Geometry:
    def __init__(self, by_document, tracks, speed_train_type, linked_pairs=(), *, speed_profiles=None):
        self.documents = by_document
        self.traces = {}
        self.used = set()
        self.vertices = defaultdict(list)
        self.speed_train_type = speed_train_type
        self.speed_profiles = speed_profiles or {}
        self.speed_train_types = tuple(self.speed_profiles) or (speed_train_type,)
        self.connections = []
        self.turnouts = []
        self.cross_document = []
        self.embedded_connector_count = 0
        self.omissions = defaultdict(set)
        for document, binding in tracks:
            self.add_track(document, binding)
        expected = {(document, identity(obj)) for document, byid in by_document.items()
                    for obj in byid.values() if writer.kind(obj) == 'OTEdgeModel'}
        require(self.used == expected, 'Tracks must cover each physical native Edge exactly once')
        for ends, entries in self.vertices.items():
            self.classify_vertex(ends, entries)
        for left, right in linked_pairs:
            self.link_documents(left, right)

    def vertex(self, document, end):
        byid = self.documents[document]
        model = byid[end]
        peer = byid.get(model.contents[8].value)
        require(peer is not None and peer.contents[8].value == end and xy(model) == xy(peer),
                'Local native Ends require reciprocal identity and identical chart coordinates')
        return (document, *sorted((end, identity(peer))))

    def add_track(self, document, binding):
        track_id = binding.track_id
        require(track_id not in self.traces, f'Duplicate RailML track ID {track_id!r}')
        require(not track_id.startswith('OTX_'), 'Track IDs beginning with OTX_ are reserved for generated XML records')
        byid = self.documents[document]
        cursor = 0
        segments, names, lines = [], set(), set()
        for link in binding.edges:
            edge = byid.get(link.edge_id)
            key = (document, link.edge_id)
            require(edge is not None and writer.kind(edge) == 'OTEdgeModel' and key not in self.used,
                    f'Unknown or repeated native Edge {document}:{link.edge_id}')
            first, second = (identity(edge.contents[slot].value) for slot in (7, 8))
            start = link.start_end_id
            require(start in (first, second), f'Start End {start} does not belong to Edge {key}')
            forward = start == first
            end = second if forward else first
            require(not segments or byid[segments[-1].end].contents[8].value == start, f'Discontinuous RailML track {track_id}')
            require(self.vertex(document, start) != self.vertex(document, end) and xy(byid[start]) != xy(byid[end]),
                    f'Coincident endpoints on native Edge {key}')
            category, length, radius, slope, loop, dlink = edge.contents[9].values
            require(length > 0 and abs(slope) <= 1000 and abs(radius) <= 10000000, f'Invalid native engineering values for {key}')
            self.record_omissions(document, edge, category, loop, dlink)
            name, line = (writer.string(edge.contents[index].value) or '' for index in (19, 20))
            names.add(name)
            lines.add(line)
            speeds = course_factories.dictionary(edge.contents[16].value)
            missing = set(self.speed_train_types) - speeds.keys()
            require(not missing, f'Edge {key} has no speed category {sorted(missing)!r}')
            slots = (1, 2) if forward else (2, 1)
            up, down = [tuple(speeds[name].contents[slot].value for name in self.speed_train_types) for slot in slots]
            require(all(0 <= value <= 1000 for value in (*up, *down)), f'Invalid selected directional speed at {key}')
            self.omissions['unselected_speed_categories'].update(set(speeds) - set(self.speed_train_types))
            segments.append(Segment(document, link.edge_id, start, end, cursor, cursor + length, up, down,
                                    slope if forward else -slope, radius if forward else -radius))
            self.used.add(key)
            cursor += length
        require(len(names) == len(lines) == 1, f'Native track or line name changes inside {track_id!r}; split at that boundary')
        self.traces[track_id] = Trace(track_id, document, names.pop(), lines.pop(), tuple(segments))
        visits = set()
        for index, segment in enumerate(segments):
            vertex = self.vertex(document, segment.start)
            require(vertex not in visits, f'RailML track {track_id!r} visits a vertex twice; split its track trace')
            visits.add(vertex)
            self.vertices[vertex].append((track_id, index))
        last = self.vertex(document, segments[-1].end)
        require(last not in visits, f'RailML track {track_id!r} closes into itself; split its track trace')
        self.vertices[last].append((track_id, len(segments)))

    def record_omissions(self, document, edge, category, loop, dlink):
        label = f'{document}:{identity(edge)}'
        if [category, loop, dlink] != [1, 1, 1]:
            self.omissions['native_track_type_flags'].add(label)
        if edge.contents[11].value != 0 or edge.contents[10].values != [100.0, 40.0]:
            self.omissions['native_edge_flags_or_sections'].add(label)
        if any(edge.contents[i].value is not None for i in (6, 13, 14, 17, 18)) or writer.string(edge.contents[12].value):
            self.omissions['native_edge_graphics_equipment_or_remarks'].add(label)
        for end in (edge.contents[7].value, edge.contents[8].value):
            if writer.string(end.contents[18].value) or end.contents[13].value is not None or end.contents[23].values != [0, 0]:
                self.omissions['native_end_names_or_devices'].add(f'{document}:{identity(end)}')

    def at(self, track_id, index):
        trace = self.traces[track_id]
        if index == 0:
            return trace.segments[0].start, 0
        previous = trace.segments[index - 1]
        return previous.end, previous.high

    def boundary(self, track_id, index):
        return index in (0, len(self.traces[track_id].segments))

    def classify_vertex(self, vertex, entries):
        if len(entries) == 1:
            return
        require(len(entries) == 2, 'RailML supports a local boundary pair or a simple first-slot trunk / second-slot branch here')
        a, b = entries
        a_boundary, b_boundary = (self.boundary(*entry) for entry in entries)
        if a_boundary and b_boundary:
            require(self.at(*a)[0] != self.at(*b)[0], 'One native turnout side cannot be encoded as an ordinary reciprocal link')
            self.connections.append((a, b))
            return
        require(a_boundary != b_boundary, 'Unreviewed four-leg topology or two overlapping through tracks')
        through, branch = (b, a) if a_boundary else (a, b)
        trace = self.traces[through[0]]
        index = through[1]
        prior, following = trace.segments[index - 1:index + 1]
        byid = self.documents[trace.document]
        branch_end = self.at(*branch)[0]
        require(branch_end in (prior.end, following.start), 'Branch does not meet a native trunk End')
        switch = byid[branch_end]
        primary_edge = prior.edge_id if branch_end == prior.end else following.edge_id
        branch_trace = self.traces[branch[0]]
        branch_edge = branch_trace.segments[0 if branch[1] == 0 else -1].edge_id
        require(switch.contents[9].value is byid[primary_edge] and switch.contents[10].value is byid[branch_edge]
                and switch.contents[21].value == 0 and switch.contents[22].value == 0,
                'Through track must use the native first branch, and the turnout must have default timing and position')
        require(branch_end == following.start and branch[1] == 0,
                'Orient the RailML track and branch away from the native facing junction')
        self.turnouts.append((through, branch))

    def link_documents(self, left, right):
        a = self.vertices.get(self.vertex(*left), [])
        b = self.vertices.get(self.vertex(*right), [])
        require(len(a) == len(b) == 1 and self.boundary(*a[0]) and self.boundary(*b[0]) and
                self.at(*a[0])[0] == left[1] and self.at(*b[0])[0] == right[1],
                'Each reciprocal native connector must join two uniquely mapped track boundaries')
        self.connections.append((a[0], b[0]))
        def detail(key, boundary):
            document, end = key
            connector = self.documents[document][end].contents[8].value
            return {'document': document, 'end_id': end, 'connector_id': connector, 'track_id': boundary[0]}

        self.cross_document.append({'first': detail(left, a[0]), 'second': detail(right, b[0])})

    def position(self, trace, index, offsets):
        end, _ = self.at(trace.identity, index)
        document = trace.segments[index - 1 if index else 0].document
        x, y = xy(self.documents[document][end])
        dx, dy = offsets[document]
        return (x + dx, y + dy)

    def join_document_track(self, track_id):
        traces = list(self.traces.values())
        require(len(traces) >= 2 and len(self.connections) == len(self.cross_document) == len(traces) - 1
                and not self.turnouts, 'The selected corridor requires one ordered chain of reciprocal native connectors')
        require(not track_id.startswith('OTX_'), 'Track IDs beginning with OTX_ are reserved for generated XML records')
        first = traces[0]
        require(all((trace.name, trace.line) == (first.name, first.line) for trace in traces),
                'All worksheets must use the same native track and line names on the exported corridor')
        records = {frozenset(connection): row for connection, row in zip(self.connections, self.cross_document, strict=True)}
        joined, connectors, offset = [], [], 0
        for index, trace in enumerate(traces):
            if index:
                prior = traces[index - 1]
                expected = frozenset(((prior.identity, len(prior.segments)), (trace.identity, 0)))
                require(expected in records, 'The selected corridor must traverse each native connector in order')
                actual = records.pop(expected)
                source, target = actual['first'], actual['second']
                if source['track_id'] != prior.identity:
                    source, target = target, source
                connectors.append({'first': {**source, 'track_id': track_id}, 'second': {**target, 'track_id': track_id},
                                   'embedded_position_m': offset})
            joined.extend(replace(span, low=span.low + offset, high=span.high + offset) for span in trace.segments)
            offset += trace.segments[-1].high
        self.traces = {track_id: Trace(track_id, first.document, first.name, first.line, tuple(joined))}
        self.connections.clear()
        self.cross_document = connectors
        self.embedded_connector_count = len(connectors)

    def render(self):
        root = ET.Element(tag('railml'), {'version': '2.2', SCHEMA_LOCATION: RAILML_SCHEMA})
        infrastructure = node(root, 'infrastructure', id='OTX_infrastructure')
        if not self.speed_profiles:
            attributes = node(infrastructure, 'infraAttrGroups')
            speeds = {speed for trace in self.traces.values() for span in trace.segments for speed in (span.up[0], span.down[0])}
            for speed in sorted(speeds):
                group = node(attributes, 'infraAttributes', id=f'OTX_speed{speed}')
                node(node(group, 'speeds'), 'speed', etcsTrainCategory=self.speed_train_type, vMax=speed)
        tracks = node(infrastructure, 'tracks')
        groups = node(infrastructure, 'trackGroups')
        visualization = node(node(root, 'infrastructureVisualizations'), 'visualization', id='OTX_viz',
                             version='2.2', infrastructureRef='OTX_infrastructure')
        lines, boundaries, visuals, topology = {}, {}, {}, {}
        offsets = self.document_offsets()
        for serial, trace in enumerate(self.traces.values()):
            prefix = f'OTX_t{serial}'
            track = node(tracks, 'track', id=trace.identity, **({'name': trace.name} if trace.name else {}))
            line_key = trace.line
            if line_key not in lines:
                line_id = f'OTX_line{len(lines)}'
                line = node(groups, 'line', id=line_id, **({'name': line_key} if line_key else {}))
                lines[line_key] = line, node(visualization, 'lineVis', ref=line_id)
            line, line_vis = lines[line_key]
            node(line, 'trackRef', ref=trace.identity)
            vis = node(line_vis, 'trackVis', ref=trace.identity)
            visuals[trace.identity] = vis
            topo = node(track, 'trackTopology')
            topology[trace.identity] = topo
            for index, label, suffix in ((0, 'trackBegin', 'begin'), (len(trace.segments), 'trackEnd', 'end')):
                ident = prefix + '_' + suffix
                item = node(topo, label, id=ident, pos=self.at(trace.identity, index)[1])
                boundaries[(trace.identity, index)] = (item, self.position(trace, index, offsets))
                visualize(vis, ident, self.position(trace, index, offsets))
            self.engineering(track, vis, trace, prefix, offsets)
        for serial, (through, branch) in enumerate(self.turnouts):
            track, index = through
            switch_id, primary, secondary = (f'OTX_s{serial}_{suffix}' for suffix in ('switch', 'through', 'branch'))
            parent = topology[track]
            container = parent.find(tag('connections'))
            if container is None:
                container = node(parent, 'connections')
            switch = node(container, 'switch', id=switch_id, pos=self.at(*through)[1])
            node(switch, 'connection', id=primary, ref=secondary, orientation='outgoing')
            branch_boundary, _ = boundaries[branch]
            node(branch_boundary, 'connection', id=secondary, ref=primary)
            visualize(visuals[track], switch_id, self.position(self.traces[track], index, offsets))
        for serial, (a, b) in enumerate(self.connections):
            first, second = f'OTX_c{serial}_a', f'OTX_c{serial}_b'
            node(boundaries[a][0], 'connection', id=first, ref=second)
            node(boundaries[b][0], 'connection', id=second, ref=first)
        for (track, _), (boundary, point) in boundaries.items():
            if len(boundary):
                continue
            ident = boundary.get('id') + '_open'
            node(boundary, 'openEnd', id=ident)
            visualize(visuals[track], ident, point)
        result = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        inventory = railml_inventory(result)
        require(inventory['unmatched_connection_count'] == 0 and
                inventory['reciprocal_connection_pairs'] == len(self.connections) + len(self.turnouts)
                and inventory['switch_count'] == len(self.turnouts), 'Fresh RailML connection readback differs')
        return result, {'output_inventory': inventory, 'native_edge_count': len(self.used),
                        'native_ordinary_connection_count': len(self.connections) - len(self.cross_document) + self.embedded_connector_count,
                        'native_cross_document_connector_pairs': self.cross_document,
                        'translated_document_coordinates': offsets, 'native_turnout_count': len(self.turnouts),
                        'omitted_native_fields': {key: {'count': len(values), 'sample': sorted(values)[:100]}
                                                  for key, values in sorted(self.omissions.items()) if values}}

    def document_offsets(self):
        # Original worksheets use local coordinates. One translatable chart
        # origin per connected worksheet keeps linked boundaries coincident.
        adjacency = defaultdict(list)
        for pair in self.cross_document:
            left, right = (pair[key] for key in ('first', 'second'))
            a, b = (self.documents[row['document']][row['end_id']] for row in (left, right))
            point_a, point_b = xy(a), xy(b)
            delta_x, delta_y = (p - q for p, q in zip(point_a, point_b))
            ldoc, rdoc = left['document'], right['document']
            adjacency[ldoc].append((rdoc, (delta_x, delta_y)))
            adjacency[rdoc].append((ldoc, (-delta_x, -delta_y)))
        offsets = {}
        for document in self.documents:
            if document in offsets:
                continue
            offsets[document] = (0.0, 0.0)
            queue = [document]
            for current in queue:
                for peer, delta in adjacency[current]:
                    expected = tuple(a + b for a, b in zip(offsets[current], delta))
                    if peer not in offsets:
                        offsets[peer] = expected
                        queue.append(peer)
                    else:
                        require(offsets[peer] == expected,
                                'Linked worksheets require inconsistent chart translations; adjust source worksheet coordinates')
        return offsets

    def engineering(self, track, vis, trace, prefix, offsets):
        elements = node(track, 'trackElements')
        speeds = node(elements, 'speedChanges')
        slopes = node(elements, 'gradientChanges')
        radii = node(elements, 'radiusChanges')
        for index, span in enumerate(trace.segments):
            for direction, i, limits in (('up', index, span.up), ('down', index + 1, span.down)):
                for name, speed in zip(self.speed_train_types, limits):
                    ident = f'{prefix}_{direction}{index}'
                    if self.speed_profiles:
                        code = self.speed_profiles[name]
                        ident += f'_etcs{code}'
                        attrs = {'etcsTrainCategory': code}
                    else:
                        attrs = {'profileRef': f'OTX_speed{speed}'}
                    node(speeds, 'speedChange', id=ident, pos=self.at(trace.identity, i)[1],
                         dir=direction, **attrs, vMax=speed)
                    visualize(vis, ident, self.position(trace, i, offsets))
            for suffix, section, name, i, attrs in (
                ('slope', slopes, 'gradientChange', index, {'slope': clean_decimal(span.slope)}),
                ('radius', radii, 'radiusChange', index, {'radius': clean_decimal(span.radius)}),
            ):
                ident = f'{prefix}_{suffix}{index}'
                node(section, name, id=ident, pos=self.at(trace.identity, i)[1], **attrs)
                visualize(vis, ident, self.position(trace, i, offsets))
        node(track, 'ocsElements')


def visualize(parent, ident, point):
    node(node(parent, 'trackElementVis', ref=ident), 'position', x=clean_decimal(point[0]), y=clean_decimal(point[1]))


def export_geometry(documents, document_paths, bindings, speed_train_type, *, speed_profiles=None):
    from .multi_document.core import Project, sha

    project = Project(documents, document_paths=document_paths,
                      expected_hashes={name: sha(blob) for name, blob in documents.items()},
                      complete_document_set=True, validate_operations=False)
    pairs = []
    for document in documents:
        for end in project.ends(document):
            if writer.kind(end) != 'OTConnModel':
                continue
            key = project.key(end)
            peer = project.block_end(key)
            if key < peer:
                pairs.append((project.related(key), project.related(peer)))
    geometry, report = Geometry(project.byid, bindings, speed_train_type, pairs, speed_profiles=speed_profiles).render()
    omitted = defaultdict(int)
    for models in project.models.values():
        for model in models:
            kind = writer.kind(model)
            if kind not in ('OTEdgeModel', 'OTEndModel', 'OTConnModel', 'OTElement'):
                omitted[kind] += 1
    speed_report = {'selected_speed_profiles': speed_profiles} if speed_profiles else {'selected_speed_category': speed_train_type}
    return geometry, {**report, **speed_report, 'source_document_count': len(documents),
                      'geometry_template_required': False, 'preserves_native_document_boundaries': False,
                      'native_operations_exported': False, 'geometry_only_native_graphic_counts': dict(sorted(omitted.items()))}

