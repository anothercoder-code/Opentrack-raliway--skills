"""Cross-check collector reservation and release layers against native step files."""

from bisect import bisect_left
from collections import Counter
from itertools import groupby

from .native_evaluation_formats import require, series


# Native files print absolute times to 0.01 s and km positions to 0.1 m.
# An independent .st1 anchor is sampled and rounded at the start of a segment.
TIME_PRECISION_S = .015
COURSE_DISTANCE_TOLERANCE_M = .45


def scenario_header(raw):
    matches = [line.strip() for line in raw.splitlines() if line.startswith('// Scenario:')]
    require(len(matches) == 1, 'Missing exact native output scenario header')
    return matches[0]


class MotionSegment:
    def __init__(self, points, network):
        self.direction = 1 if points[-1]['distance_m'] > points[0]['distance_m'] else -1
        self.origin = points[0]['distance_m']
        self.course_origin = points[0]['st1_course_distance_m']
        self.low, self.high = sorted((points[0]['distance_m'], points[-1]['distance_m']))
        self.vertices = set()
        self.edges = set()
        for event in points:
            a, b = event['from_end'], event['to_end']
            self.vertices.add(network.vertex(a))
            if b is not None:
                self.vertices.add(network.vertex(b))
                self.edges.add(network.vertex_pair(a, b))

    def course_position(self, physical):
        return self.course_origin + self.direction * (physical - self.origin)

    def contains(self, network, event, position):
        if not self.low - .01 <= position <= self.high + .01:
            return False
        a, b = event['from_end'], event['to_end']
        if b is None:
            return network.vertex(a) in self.vertices
        return network.vertex_pair(a, b) in self.edges


def step_windows(raw, course, bank):
    native = series(raw, f'step{bank}', course)
    multiplier = 1000 if native['units'][1] == 'km' else 1609.344
    windows = []
    for instant, rows in groupby(native['points'], key=lambda row: row[0]):
        values = [point[1] * multiplier for point in rows]
        windows.append((instant, min(values), max(values)))
    return windows


def matching_window(windows, times, instant):
    index = bisect_left(times, instant)
    options = [windows[i] for i in (index - 1, index)
               if 0 <= i < len(times) and abs(times[i] - instant) <= TIME_PRECISION_S]
    # Two distinct published clocks this close would make the correspondence ambiguous.
    return options[0] if len(options) == 1 else None


def verified_groups(network, alignment, course, segments, file, bank):
    windows = step_windows(file, course, bank)
    times = [window[0] for window in windows]
    groups = []
    excluded = Counter()
    total = 0
    for clock, events in groupby(network.events(course, bank), key=lambda row: row['time_s']):
        rows = list(events)
        total += len(rows)
        window = matching_window(windows, times, clock)
        if window is None or window[2] <= window[1]:
            excluded['no_independent_nonzero_step'] += len(rows)
            continue
        per_segment = {}
        for event in rows:
            position = alignment.position(event) if event['kind'] == 0 else None
            if position is None:
                excluded['off_alignment_or_nonposition'] += 1
                continue
            possible = [index for index, segment in enumerate(segments)
                        if segment.contains(network, event, position)
                        and window[1] - COURSE_DISTANCE_TOLERANCE_M
                        <= segment.course_position(position)
                        <= window[2] + COURSE_DISTANCE_TOLERANCE_M]
            if len(possible) != 1:
                excluded['not_unique_travelled_path_or_step_position'] += 1
                continue
            per_segment.setdefault(possible[0], {}).setdefault(round(position, 2), event)
        for index, points in per_segment.items():
            if len(points) < 2:
                excluded['isolated_confirmed_point'] += len(points)
                continue
            low, high = min(points), max(points)
            stationing = sorted(segments[index].course_position(boundary) for boundary in (low, high))
            # Between projected landmarks we can claim the part of this independent
            # spatial step that is bounded by actual collector End positions.
            if stationing[0] < window[1] - COURSE_DISTANCE_TOLERANCE_M or \
                    stationing[1] > window[2] + COURSE_DISTANCE_TOLERANCE_M:
                excluded['projected_bounds_differ'] += len(points)
                continue
            groups.append({'motion_segment': index, 'time_s': clock, 'source_step_time_s': window[0],
                           'source_step_course_span_m': [window[1], window[2]],
                           'positions': points, 'low_m': low, 'high_m': high})
    return groups, {'raw_records': total, 'supported_groups': len(groups), 'excluded_counts': dict(excluded)}


def supported_intervals(reservations, releases, segments):
    """Use only common, actual endpoints with an unambiguous acquisition/release pair."""
    result = []
    for index, segment in enumerate(segments):
        reserves = [group for group in reservations if group['motion_segment'] == index]
        frees = [group for group in releases if group['motion_segment'] == index]
        reserve_positions = {pos for group in reserves for pos in group['positions']}
        release_positions = {pos for group in frees for pos in group['positions']}
        boundaries = sorted(reserve_positions & release_positions, reverse=segment.direction < 0)
        for a, b in zip(boundaries, boundaries[1:]):
            first = [group for group in reserves if a in group['positions'] and b in group['positions']]
            last = [group for group in frees if a in group['positions'] and b in group['positions']]
            if len(first) != 1 or len(last) != 1 or first[0]['time_s'] >= last[0]['time_s']:
                continue
            take, release = first[0], last[0]
            result.append({'motion_segment': index, 'direction': segment.direction,
                           'from_m': a, 'to_m': b, 'reserved_s': take['time_s'],
                           'released_s': release['time_s'],
                           'reservation_event_indices': [take['positions'][pos]['index'] for pos in (a, b)],
                           'release_event_indices': [release['positions'][pos]['index'] for pos in (a, b)],
                           'independent_step_clock_s': [take['source_step_time_s'], release['source_step_time_s']]})
    return result


def project_occupations(network, alignment, course, tracks, native_st1, reservation, release):
    require(scenario_header(native_st1) == scenario_header(reservation) == scenario_header(release),
            'Independent .st1 and route steps have different native scenarios')
    segments = [MotionSegment(points, network) for points in tracks]
    reservations, reservation_evidence = verified_groups(network, alignment, course, segments, reservation, 1)
    releases, release_evidence = verified_groups(network, alignment, course, segments, release, 2)
    intervals = supported_intervals(reservations, releases, segments)
    same_clock_order = all(a[key] <= b[key] for a, b in zip(intervals, intervals[1:])
                           for key in ('reserved_s', 'released_s'))
    return {'intervals': intervals, 'recorded_interval_distance_m': sum(abs(row['to_m'] - row['from_m'])
                                                                          for row in intervals),
            'reservation': reservation_evidence, 'release': release_evidence,
            'encoded': bool(intervals) and same_clock_order,
            'shared_native_bank_order': same_clock_order,
            'full_motion_alignment_covered': all(
                abs(sum(abs(row['to_m'] - row['from_m']) for row in intervals if row['motion_segment'] == index)
                    - (segment.high - segment.low)) <= .02 for index, segment in enumerate(segments)),
            'scope': 'Independently corroborated native route-reservation time intervals on the travelled alignment.'}
