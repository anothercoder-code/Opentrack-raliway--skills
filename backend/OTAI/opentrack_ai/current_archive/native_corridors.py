"""Project actual OpenTrack collector records onto explicit native edge alignments."""

from bisect import bisect_left
from copy import deepcopy
import math

from . import writer as w
from .native_evaluation_formats import require, series
from .zero_generation import native_signal_routes as ns


def shape(obj, kind, encodings):
    require(w.kind(obj) == kind and [''.join(c.decode() for c in group.encodings)
                                   for group in obj.contents] == encodings,
            f'Unsupported {kind} native archive layout')


def text(obj):
    return None if obj is None else w.string(obj)


def mapping(obj):
    require(w.kind(obj) == 'NSMutableDictionary' and len(obj.contents) == 1 + 2 * obj.contents[0].value,
            'Malformed native dictionary')
    result = {text(obj.contents[i].value): obj.contents[i+1].value for i in range(1, len(obj.contents), 2)}
    require(len(result) == obj.contents[0].value, 'Duplicate native dictionary key')
    return result


def items(obj):
    require(w.kind(obj) in {'NSMutableArray', 'NSArray'} and len(obj.contents) == 1 + obj.contents[0].value,
            'Malformed native array')
    return [group.value for group in obj.contents[1:]]


def array(values):
    return ns.obj([('NSMutableArray', 0), ('NSArray', 0), ('NSObject', 0)],
                  [('i', [len(values)])] + [('@', [value]) for value in values])


def dictionary(values):
    return ns.obj([('NSMutableDictionary', 0), ('NSDictionary', 0), ('NSObject', 0)],
                  [('i', [len(values)])] + [('@', [obj]) for key, val in values.items()
                                           for obj in (ns.string(key), val)])


def object_id(obj):
    return text(obj) if w.kind(obj) in {'NSString', 'NSMutableString'} else text(obj.contents[0].value)


class NativeNetwork:
    def __init__(self, raw):
        self.root, self.version = w.load(raw)
        shape(self.root, 'OTSimDocument', ['@', '@', '@', '@', '@', '@', '@', 'i', 'ff', '@', '@'])
        require(self.root.clazz.version == 2, 'Only native OTSimDocument2 is supported')
        sim, topo = (self.root.contents[index].value for index in (0, 1))
        shape(sim, 'OTTSimController', ['@'] * 3)
        shape(topo, 'OTTDocTopoController', ['@'] * 4)
        self.position_events, self.reservations, self.releases = [mapping(group.value) for group in sim.contents]
        natives, edges, stations, self.stations = [mapping(group.value) for group in topo.contents]
        require(natives and edges and self.position_events, 'Empty native capture seed contains no actual topology')
        self.related = {}
        for key, end in natives.items():
            require(w.kind(end) in {'OTTEndModel', 'OTTStationEndModel'}
                    and len(end.contents) in {5, 6} and object_id(end) == key, 'Malformed native End')
            self.related[key] = text(end.contents[1].value)
        self.edges = {}
        self.edge_by_ends = {}
        for key, edge in edges.items():
            shape(edge, 'OTTEdgeModel', ['@', '@', '@', '@', 'i'])
            first, last = (text(edge.contents[index].value) for index in (1, 2))
            length = edge.contents[3].value
            require(object_id(edge) == key and first in self.related and last in self.related and first != last
                    and w.kind(length) == 'NSNumber', 'Malformed native Edge')
            meters = float(length.contents[-1].value)
            require(math.isfinite(meters) and meters > 0 and meters.is_integer(), 'Native Edge must have positive integral metres')
            self.edges[key] = (first, last, int(meters))
            pair = self.vertex_pair(first, last)
            self.edge_by_ends.setdefault(pair, []).append(key)
        self.station_ends = {station: {object_id(obj) for obj in items(ends)} for station, ends in stations.items()}
        require(set(self.station_ends) == set(self.stations), 'Native station identities do not close')

    def vertex(self, key):
        require(key in self.related, f'Unknown native End {key}')
        related = self.related[key]
        return min(key, related) if related in self.related and self.related[related] == key else key

    def vertex_pair(self, first, last):
        return frozenset((self.vertex(first), self.vertex(last)))

    def events(self, course, bank=0):
        dictionary = (self.position_events, self.reservations, self.releases)[bank]
        if course not in dictionary:
            return
        last_time = -1
        for index, event in enumerate(items(dictionary[course])):
            shape(event, 'OTSimEvent', ['@', '@', '@', 'f', 'f', 'i'])
            token, first, last = (text(event.contents[number].value) for number in range(3))
            instant, factor = (float(event.contents[number].value) for number in (3, 4))
            kind = event.contents[5].value
            require(token == course and math.isfinite(instant) and instant >= 0
                    and math.isfinite(factor), 'Malformed native Course event')
            if kind == 0:
                require(instant >= last_time, 'Native position events are not chronological')
                last_time = instant
            yield {'index': index, 'kind': kind, 'from_end': first, 'to_end': last,
                   'time_s': instant, 'factor': factor}

    def derive_alignment(self, course):
        """Provide the consecutive uniquely resolved edges observed in one course."""
        path = []
        last_vertex = None
        last_edge = None
        for event in self.events(course):
            first, last = event['from_end'], event['to_end']
            if event['kind'] != 0 or last is None:
                continue
            pair = self.vertex_pair(first, last)
            if len(pair) == 1:
                continue
            edges = self.edge_by_ends.get(pair, [])
            require(len(edges) == 1, 'Observed position event does not identify one native Edge')
            edge = edges[0]
            first_v, last_v = self.vertex(first), self.vertex(last)
            if last_edge == (edge, first_v):
                continue
            require(last_vertex is None or last_vertex == first_v,
                    'Observed edge sequence has a gap; provide exact alignment manually')
            path.append({'edge_id': edge, 'from_end': first})
            last_vertex = last_v
            last_edge = (edge, first_v)
        require(path, 'No finite actual edge chain found for this Course')
        return path

    def reverse_alignment(self, path):
        result = []
        for item in reversed(path):
            a, b, _ = self.edges[item['edge_id']]
            start = self.vertex(item['from_end'])
            require(start in {self.vertex(a), self.vertex(b)}, 'Start is not an endpoint of the native Edge')
            result.append({'edge_id': item['edge_id'], 'from_end': b if start == self.vertex(a) else a})
        return result

    def inventory(self, course=None):
        return {'courses': sorted(self.position_events), 'edge_count': len(self.edges),
                'station_end_ids': {name: sorted(ends) for name, ends in sorted(self.station_ends.items())},
                'observed_alignment': self.derive_alignment(course) if course is not None else None,
                'native_positions': sum(obj.contents[0].value for obj in self.position_events.values()),
                'native_reservations': sum(obj.contents[0].value for obj in self.reservations.values()),
                'native_releases': sum(obj.contents[0].value for obj in self.releases.values())}


class Alignment:
    def __init__(self, network, paths, stations):
        self.network = network
        self.coordinates = {}
        self.hotspots = {}
        self.edge_pairs = set()
        self.length = 0
        require(1 <= len(paths) <= 128, 'Declare a bounded list of native alignment paths')
        for index, path in enumerate(paths):
            start = path.get('start_m', 0)
            require(type(start) is int and 0 <= start <= self.length and (index != 0 or start == 0),
                    'Invalid native alignment start position')
            previous = None
            position = start
            chain = path['edges']
            require(1 <= len(chain) <= 10000, 'Declare 1 to 10000 oriented native Edges')
            for edge in chain:
                a, b, length = network.edges[edge['edge_id']]
                starting_end = network.vertex(edge['from_end'])
                require(starting_end in {network.vertex(a), network.vertex(b)}
                        and (previous is None or previous == starting_end), 'Native corridor edges are not continuous')
                if starting_end == network.vertex(b):
                    a, b = b, a
                self.point(a, position, -1)
                position += length
                self.point(b, position, 1)
                previous = network.vertex(b)
                self.edge_pairs.add(network.vertex_pair(a, b))
            if index == 0:
                self.length = position
            require(position <= self.length, 'Alternative path exceeds the primary corridor length')
        require(2 <= len(stations) <= 80, 'Declare an ordered list of 2 to 80 station references')
        self.stations = []
        previous = -1
        for station in stations:
            name, end = station['station'], station['end_id']
            require(end in network.station_ends[name] and end in self.coordinates,
                    'Native station reference does not belong to this alignment')
            position = self.coordinates[end]
            require(position > previous, 'Station references are not in strict corridor order')
            self.stations.append((name, position))
            previous = position

    def point(self, end, position, direction):
        related = self.network.related[end]
        keys = [(end, direction)]
        if related in self.network.related and self.network.related[related] == end:
            keys.append((related, -direction))
        for key, sign in keys:
            require(self.coordinates.setdefault(key, position) == position,
                    'Native End is assigned two corridor positions; supply an unambiguous segment')
            require(self.hotspots.setdefault(key, position * sign) == position * sign,
                    'Native End direction is inconsistent across alignment paths')

    def position(self, event):
        a, b = event['from_end'], event['to_end']
        if a not in self.coordinates or (b is not None and b not in self.coordinates):
            return None
        left = self.coordinates[a]
        if b is None:
            return left
        pair = self.network.vertex_pair(a, b)
        if len(pair) != 1 and pair not in self.edge_pairs:
            return None
        factor = event['factor']
        require(0 <= factor <= 1, 'Native position factor outside [0,1]')
        return left + (self.coordinates[b] - left) * factor


def observed_segments(network, alignment, course):
    segments = []
    current = []
    direction = 0
    outside = 0
    for event in network.events(course):
        if event['kind'] != 0:
            continue
        pos = alignment.position(event)
        if pos is None:
            outside += 1
            if current:
                segments.append(current)
                current = []
                direction = 0
            continue
        record = {**event, 'distance_m': pos}
        if current:
            delta = pos - current[-1]['distance_m']
            sign = 0 if abs(delta) < .01 else 1 if delta > 0 else -1
            if sign and direction and sign != direction:
                segments.append(current)
                current = [current[-1]]
            direction = sign or direction
        current.append(record)
    if current:
        segments.append(current)
    usable = [segment for segment in segments if len(segment) >= 2 and
              abs(segment[-1]['distance_m'] - segment[0]['distance_m']) > .01]
    return usable, outside, sum(len(segment) for segment in segments if segment not in usable)


def compare(segment, reference):
    times = [row[0] for row in reference]
    direction = 1 if segment[-1]['distance_m'] > segment[0]['distance_m'] else -1

    def interpolate(time):
        index = bisect_left(times, time)
        if index == 0:
            require(abs(time - times[0]) <= .011, 'Collector event predates native .st1 reference')
            return reference[0][1]
        if index == len(times):
            require(abs(time - times[-1]) <= .011, 'Collector event follows native .st1 reference')
            return reference[-1][1]
        left, right = reference[index - 1], reference[index]
        return left[1] + (right[1] - left[1]) * (time - left[0]) / (right[0] - left[0])

    anchor = segment[0]
    origin = interpolate(anchor['time_s'])
    for point in segment:
        actual_dist = interpolate(point['time_s'])
        expected = anchor['distance_m'] + direction * (actual_dist - origin)
        point['st1_course_distance_m'] = actual_dist
        point['st1_delta_residual_m'] = point['distance_m'] - expected
    return max(abs(point['st1_delta_residual_m']) for point in segment)


def project(network, spec, st1_data, occupation_traces=None, conflict_messages=None):
    alignment = Alignment(network, spec['paths'], spec['stations'])
    courses = spec['courses']
    require(1 <= len(courses) <= 500 and len(set(courses)) == len(courses), 'Declare distinct Course IDs')
    require(set(courses) == set(st1_data), 'Each Course needs an independently bound original .st1 file')
    occupation_traces = occupation_traces or {}
    require(set(occupation_traces) <= set(courses), 'Occupation trace Course was not requested')
    independent_warnings = None
    if conflict_messages is not None:
        from .native_corridor_conflicts import route_conflicts, route_warnings

        independent_warnings = route_warnings(conflict_messages)
    reports = {}
    for cid in courses:
        segments, outside, isolated = observed_segments(network, alignment, cid)
        require(segments, f'{cid} has no moving actual segment on this alignment')
        native = series(st1_data[cid], 'st1', cid)
        factor = 1000 if native['units'][1] == 'km' else 1609.344
        reference = [(time, distance * factor) for time, distance in native['points']]
        require(len(reference) >= 2, 'Independent native distance trace is empty')
        residual = max(compare(segment, reference) for segment in segments)
        limit = float(spec.get('maximum_st1_delta_residual_m', 2.0))
        require(0 < limit <= 25 and residual <= limit, f'{cid} independent native distance residual {residual:.3f} m exceeds limit')
        reports[cid] = {'segments': segments, 'excluded_off_alignment_events': outside,
                        'excluded_isolated_events': isolated, 'max_st1_delta_residual_m': residual,
                        'reservation_events': len(list(network.events(cid, 1))),
                        'release_events': len(list(network.events(cid, 2)))}
        if cid in occupation_traces:
            from .native_corridor_occupations import project_occupations

            step1, step2 = occupation_traces[cid]
            reports[cid]['occupations'] = project_occupations(network, alignment, cid, segments,
                                                               st1_data[cid], step1, step2)
        if independent_warnings is not None:
            reports[cid]['conflicts'] = route_conflicts(network, cid, segments, independent_warnings)
    return alignment, reports


def corridor_document(network, alignment, reports, donor, target_path, title):
    root, version = w.load(donor)
    require(w.kind(root) == 'OTCorridorDocument' and root.clazz.version == 11 and len(root.contents) == 24,
            'Only the verified v11 Corridor donor shape can be written')
    require(alignment.length <= 32767, 'Verified Corridor donor uses signed 16-bit topology positions')
    controller, topo = (root.contents[index].value for index in (0, 1))
    shape(controller, 'OTTCorridorSimController', ['@'] * 4)
    shape(topo, 'OTTCorridorTopoController', ['@'] * 3)
    series_template = next(iter(mapping(controller.contents[1].value).values()))
    point_template = items(series_template.contents[0].value)[0]
    shape(point_template, 'OTCorridorSimEvent', ['f', 'f', 'i'])
    number_template = next(iter(mapping(topo.contents[1].value).values()))
    require(w.kind(number_template) == 'NSNumber' and number_template.contents[-1].encodings == [b's'],
            'Unsupported donor distance number shape')
    bank = {}
    reservation_bank = {}
    release_bank = {}
    conflict_bank = {}
    occupancy_times = []
    conflict_template = next(iter(mapping(controller.contents[0].value).values()))
    shape(conflict_template, 'OTConflict', ['@', 'i', 'f', 'i'])
    require(conflict_template.clazz.version == 1, 'Unverified conflict record version')

    def plot_point(time, distance, starts):
        entry = deepcopy(point_template)
        entry.contents[0].values = [ns.number(time, 0, 1e7)]
        entry.contents[1].values = [ns.number(distance, 0, 32767)]
        entry.contents[2].values = [int(starts)]
        return entry

    def populate_series(points, stations):
        out = deepcopy(series_template)
        out.contents[0].values = [array(points)]
        out.contents[1].values = [array([ns.string(name) for name in stations])]
        return out

    for cid, report in reports.items():
        plotted = []
        for segment in report['segments']:
            for index, point in enumerate(segment):
                plotted.append(plot_point(point['time_s'], point['distance_m'], index == 0))
        bank[cid] = populate_series(plotted, [name for name, _ in alignment.stations])
        occupancy = report.get('occupations', {})
        intervals = occupancy['intervals'] if occupancy.get('encoded') else []
        if intervals:
            for clock, storage in (('reserved_s', reservation_bank), ('released_s', release_bank)):
                points = []
                for interval in intervals:
                    instant = interval[clock]
                    occupancy_times.append(instant)
                    points.extend((plot_point(instant, interval['from_m'], True),
                                   plot_point(instant, interval['to_m'], False)))
                storage[cid] = populate_series(points, [])
        for event in report.get('conflicts', {}).get('events', []):
            node = deepcopy(conflict_template)
            node.contents[0].values = [ns.string(cid)]
            node.contents[1].values = [event['conflict_code']]
            node.contents[2].values = [ns.number(event['time_s'], 0, 86400)]
            node.contents[3].values = [event['conflict_tag']]
            require(event['key'] not in conflict_bank, 'Duplicate original conflict key')
            conflict_bank[event['key']] = node
    for index, value in enumerate((conflict_bank, bank, reservation_bank, release_bank)):
        controller.contents[index].values = [dictionary(value)]
    hotspots = {}
    for key, position in sorted(alignment.hotspots.items()):
        marker = deepcopy(number_template)
        marker.contents[-1].values = [position]
        hotspots[key] = marker
    for index, value in enumerate((array([]), dictionary(hotspots), dictionary({}))):
        topo.contents[index].values = [value]
    ordered = []
    station_template = items(root.contents[15].value)[0]
    last = 0
    for index, (name, position) in enumerate(alignment.stations):
        model = deepcopy(station_template)
        model.contents[0].values = [ns.string(name)]
        model.contents[1].values = [index, position, position - last, 0]
        neighbours = len(items(network.stations[name].contents[1].value))
        model.contents[2].values = [100, neighbours, 0, 1]
        ordered.append(model)
        last = position
    root.contents[2].values = [ns.string(target_path)]
    root.contents[3].values = [ns.string(title)]
    root.contents[4].values = [deepcopy(network.root.contents[4].value)]
    root.contents[5].values = [deepcopy(network.root.contents[6].value)]
    root.contents[6].values = [0]
    points = [point for report in reports.values() for segment in report['segments'] for point in segment]
    times = [point['time_s'] for point in points] + occupancy_times
    root.contents[7].values = [float(math.floor(min(times))), float(math.ceil(max(times)))]
    root.contents[13].values = [0x8508 | (0x4000 if reservation_bank else 0) | (4 if conflict_bank else 0)]
    root.contents[15].values = [array(ordered)]
    root.contents[16].values = [ns.string('Actual native position events')]
    root.contents[18].values = [ns.string(title)]
    for index in (19, 20, 23):
        root.contents[index].values = [array([])]
    root.contents[22].values = [0]
    payload = w.dump_verified(root, version)
    checked, _ = w.load(payload)
    saved_conflicts = mapping(checked.contents[0].value.contents[0].value)
    require(set(saved_conflicts) == set(conflict_bank), 'Fresh Corridor changed the original conflict keys')
    for key, obj in saved_conflicts.items():
        original = conflict_bank[key]
        require(text(obj.contents[0].value) == text(original.contents[0].value)
                and [x.value for x in obj.contents[1:]] == [x.value for x in original.contents[1:]],
                'Fresh Corridor changed a native conflict record')
    observed = mapping(checked.contents[0].value.contents[1].value)
    for cid, report in reports.items():
        expected = [int(index == 0) for segment in report['segments'] for index in range(len(segment))]
        require([event.contents[2].value for event in items(observed[cid].contents[0].value)] == expected,
                'Fresh Corridor readback changed native segment boundaries')
    for index, expected in ((2, reservation_bank), (3, release_bank)):
        observed = mapping(checked.contents[0].value.contents[index].value)
        require(set(expected) == set(observed), 'Fresh Corridor changed native occupation Courses')
        for cid, wrapper in observed.items():
            require(items(wrapper.contents[1].value) == [], 'Occupation arrays must have no station wrappers')
            actual_points = [tuple(group.value for group in event.contents)
                             for event in items(wrapper.contents[0].value)]
            expected_points = [tuple(group.value for group in event.contents)
                               for event in items(expected[cid].contents[0].value)]
            require(actual_points == expected_points, 'Fresh Corridor changed native occupation points or boundaries')
    return payload
