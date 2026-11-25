"""Project verified route-braking events from a native network collector."""

from collections import Counter, defaultdict
import re

from .native_evaluation_formats import data_rows, headers, require


TAG_REQUIRED = {18, 20, 53}
ROUTE_BRAKING = 4


def route_warnings(raw):
    headers(raw, 'OT_messages')
    times = defaultdict(list)
    for row in data_rows(raw):
        if len(row) not in {4, 5} or row[0] != 'WARNING':
            continue
        clock, course, message = row[1:4]
        if not course or not message.startswith(f'Course {course}: Braking for Route '):
            continue
        match = re.fullmatch(r'([01][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])', clock)
        require(match is not None, 'Unsupported native conflict warning clock')
        h, m, s = map(int, match.groups())
        times[course, 3600 * h + 60 * m + s].append(message)
    return times


def route_conflicts(network, course, motion, independent_messages):
    diagnostics = Counter()
    candidates = []
    for item in network.events(course):
        code = item['kind']
        if code in TAG_REQUIRED:
            diagnostics['native_types_requiring_unarchived_tag'] += 1
        if code != ROUTE_BRAKING:
            continue
        instant = item['time_s']
        if not 0 <= instant < 86400 or '#' in course:
            diagnostics['outside_native_single_day_key_contract'] += 1
            continue
        if sum(segment[0]['time_s'] <= instant <= segment[-1]['time_s'] for segment in motion) != 1:
            diagnostics['outside_unique_retained_motion_segment'] += 1
            continue
        tick = int(instant)
        rows = independent_messages.get((course, tick), [])
        if len(rows) != 1:
            diagnostics['missing_or_ambiguous_independent_warning'] += 1
            continue
        key = f'{tick // 3600:02}:{tick // 60 % 60:02}:{tick % 60:02}#{course}'
        candidates.append(dict(key=key, time_s=instant, conflict_code=code,
                               conflict_tag=0, event_index=item['index'], independent_warning=rows[0]))
    counts = Counter(event['key'] for event in candidates)
    diagnostics['duplicate_native_clock_key'] = sum(count for count in counts.values() if count > 1)
    return {'events': [event for event in candidates if counts[event['key']] == 1],
            'excluded_counts': dict(diagnostics)}
