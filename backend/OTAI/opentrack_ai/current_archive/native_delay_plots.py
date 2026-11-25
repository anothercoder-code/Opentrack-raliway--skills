"""Read and corroborate the original OpenTrack delay bar plots."""

from collections import Counter, defaultdict
import re
from statistics import NormalDist, fmean

from . import catalogs, native_evaluation_formats as fmt, writer
from .operating_plan_edit import text


PLOTS = ('delall', 'delallarr', 'delalldep', 'delbegin', 'delend', 'delavg', 'delmax', 'dellaststop', 'delact')
SAMPLE_PRECISION_S = .1
TT_AGREEMENT_S = 1.050001


def clock(value):
    match = re.fullmatch(r'(?:[0-9]{1,5}\s*/\s*)?([0-9]{2}:[0-9]{2}:[0-9]{2})', value, re.ASCII)
    fmt.require(match is not None and all(0 <= int(part) < bound
                    for part, bound in zip(match[1].split(':'), (24, 60, 60))),
                'Invalid original delay event clock')
    return match[1]


def parse_plot(raw, kind, scenario):
    fmt.require(kind in PLOTS, 'Unknown original delay plot')
    suffix = 'laststop' if kind == 'dellaststop' else kind[3:]
    fmt.headers(raw, 'OT_delay' + suffix)
    fmt.require(re.findall(r'^// Type[ \t]*:[ \t]*([^\r\n]+)\r?$', raw, re.M) == ['OT_BarYPlot']
                and re.findall(r'^// y-Legend[ \t]*:[ \t]*([^\r\n]+)\r?$', raw, re.M) == ['[s]'],
                'Original delay output must be the seconds bar plot')
    extracted = re.findall(r'^// Scenario: .*? / Delay: ([^/\r\n]+) / ', raw, re.M)
    accepted = {'0', 'none'} if scenario == 0 else {str(scenario)}
    fmt.require(len(extracted) == 1 and extracted[0].strip().casefold() in accepted,
                'Original plot did not identify the bound delay scenario')
    rows = []
    for row in fmt.data_rows(raw):
        size = 3 if kind == 'delavg' else 4
        fmt.require(len(row) == size and re.fullmatch(r'[+-]?[0-9]+\.[0-9]', row[1]) is not None,
                    'Original delay plot row lacks the one-decimal seconds value')
        delay = fmt.number(row[1])
        station = row[2]
        at = clock(row[3]) if size == 4 else None
        fmt.require(at is None or row[3] == at, 'Original delay plot clock must omit the day prefix')
        if kind == 'delavg':
            fmt.require(row[0] and not station, 'Original average delay row must contain only a Course and delay')
        elif kind == 'delact':
            fmt.require(row[0] == station == '' and at == '00:00:00' and delay == 0,
                        'Unsupported original current-delay placeholder')
        else:
            fmt.require(row[0] and station, 'Original delay event lacks a Course or station sign')
        rows.append((row[0], station, at, delay))
    fmt.require(all(a[-1] >= b[-1] for a, b in zip(rows, rows[1:])), 'Original delay plot is not sorted')
    fmt.require(kind != 'delact' or len(rows) == 1, 'Missing original current-delay placeholder')
    return rows


def ordered_bijection(values, events):
    """Equal printed clocks are only admissible when their values bind uniquely."""
    values = sorted(values)
    events = sorted(events, key=lambda row: (row['integer_delay_s'], row['event_index']))
    fmt.require(len(values) == len(events), 'Native delay rows do not cover all matching original .tt rows')
    deltas = [row['integer_delay_s'] for row in events]
    fmt.require(all(abs(sample - estimate) <= TT_AGREEMENT_S for sample, estimate in zip(values, deltas, strict=True)),
                'Original fractional delay or whole-second .tt time disagrees at a matching event')
    fmt.require(not any(a != b and abs(a - next_estimate) <= TT_AGREEMENT_S and abs(b - estimate) <= TT_AGREEMENT_S
                    for a, b, estimate, next_estimate in zip(values, values[1:], deltas, deltas[1:])),
                'Ambiguous fractional values at repeated Course, station and printed clock')
    return zip(events, values, strict=True)


def attach_rows(observed, expected):
    values = defaultdict(list)
    for course, station, at, delay in observed:
        values[course, station, at].append(delay)
    rows = defaultdict(list)
    for event in expected:
        rows[event['course_id'], event['station_sign'], event['clock']].append(event)
    fmt.require(values.keys() == rows.keys(), 'Original delay plot and .tt have different Course, station or clock identities')
    return [{**event, 'original_delay_s': delay}
            for key in values for event, delay in ordered_bijection(values[key], rows[key])]


def event_keys(evaluation, stations):
    labels = defaultdict(list)
    for sign, station in stations.items():
        labels[(text(station, 2) or '').strip()].append(sign)
    rows = []
    for course in evaluation['courses']:
        for index, event in enumerate(course['events']):
            if event.get('planned_s') is None:
                continue
            choices = labels[event['station']]
            fmt.require(len(choices) == 1, 'Cannot uniquely bind original .tt display label to a frozen station sign')
            rows.append({'course_id': course['course_id'], 'kind': event['kind'], 'event_index': index,
                         'station_sign': choices[0], 'clock': clock(event['clock']), 'time_s': event['time_s'],
                         'integer_delay_s': event['time_s'] - event['planned_s']})
    return rows


def plot_record(event):
    return (event['course_id'], event['station_sign'], event['clock'], event['original_delay_s'])


def verified_plots(files, evaluation, station_bytes, scenario):
    used = evaluation['protocol']['used_courses']
    courses = {row['course_id']: row for row in evaluation['courses']}
    fmt.require(len(used) == len(courses) and set(used) == courses.keys(),
                'Original delay plots require every Course used by native protocol')
    stations = catalogs.station_items(writer.load_next_compatible(station_bytes)[0])
    expected = event_keys(evaluation, stations)
    by_kind = defaultdict(list)
    for entry in expected:
        by_kind[entry['kind']].append(entry)
    plots = {}
    for kind in PLOTS:
        filename = f'OT_Delay.{kind}'
        fmt.require(filename in files.expected_hashes, f'Original launcher SHA-256 is missing for {filename}')
        plots[kind] = parse_plot(files.read(filename), kind, scenario)
    rest = Counter(plots['delall'])
    endpoints = Counter(plots['delallarr']) + Counter(plots['delalldep'])
    fmt.require(endpoints <= rest, 'Original arrival and departure points do not belong to the all-delays plot')
    records = (attach_rows(plots['delallarr'], by_kind['Arr.'])
               + attach_rows(plots['delalldep'], by_kind['Dep.'])
               + attach_rows((rest - endpoints).elements(), by_kind['Pass']))
    grouped = defaultdict(list)
    for record in records:
        grouped[record['course_id']].append(record)
    named = {}
    for kind in ('delbegin', 'delend', 'delavg', 'delmax', 'dellaststop'):
        named[kind] = {row[0]: row for row in plots[kind]}
        fmt.require(len(plots[kind]) == len(named[kind]) == len(courses) and named[kind].keys() == courses.keys(),
                    f'Original {kind} needs one row per used Course')
    summaries = []
    for course_id in sorted(courses):
        course = courses[course_id]
        ordered = sorted(grouped[course_id], key=lambda row: row['event_index'])
        stops = [row for row in ordered if row['kind'] in {'Arr.', 'Dep.'}]
        fmt.require(ordered and stops and ordered[0]['event_index'] == 0,
                    'Original named delays require an initial planned event and observed planned stops')
        for name, event in (('delbegin', ordered[0]), ('delend', ordered[-1]), ('dellaststop', stops[-1])):
            fmt.require(named[name][course_id] == plot_record(event), f'Original {name} differs from the matched event in {course_id}')
        mean_delay = named['delavg'][course_id][-1]
        fmt.require(abs(mean_delay - fmean(row['original_delay_s'] for row in stops)) <= .10001,
                    f'Original average differs from printed arrival/departure samples for {course_id}')
        maximum = max(0, max(row['original_delay_s'] for row in stops))
        maximum_row = named['delmax'][course_id]
        valid = {plot_record(event) for event in stops if event['original_delay_s'] == maximum}
        if maximum == 0:
            valid.add((course_id, '*', '00:00:00', 0))
        fmt.require(maximum_row in valid, f'Original maximum delay differs from its nonnegative arrival/departure maximum for {course_id}')
        last = ordered[-1]
        terminal = last if last['event_index'] == len(course['events']) - 1 else None
        summaries.append({'course_id': course_id, 'matched_planned_events': len(ordered),
                          'initial_event': ordered[0], 'last_planned_event': last, 'last_stop_event': stops[-1],
                          'terminal_event': terminal, 'mean_arrival_departure_delay_s': mean_delay,
                          'maximum_nonnegative_arrival_departure_delay_s': maximum})
    biggest = max((abs(row['original_delay_s'] - row['integer_delay_s']) for row in records), default=0)
    return {'verified': True, 'plot_record_counts': {kind: len(rows) for kind, rows in plots.items()},
            'matched_arrivals': len(by_kind['Arr.']), 'matched_departures': len(by_kind['Dep.']),
            'matched_passages': len(by_kind['Pass']), 'maximum_absolute_difference_from_integer_tt_s': round(biggest, 6),
            'current_delay_has_only_native_placeholder': True, 'courses': summaries}


def wilson(successes, samples, level):
    if samples == 0:
        return None
    p = successes / samples
    z2 = NormalDist().inv_cdf((1 + level) / 2)**2
    scale = 1 + z2 / samples
    centre = (p + z2 / (2 * samples)) / scale
    half = (z2 * (p * (1 - p) / samples + z2 / (4 * samples**2)))**.5 / scale
    return [round(max(0, centre - half), 8), round(min(1, centre + half), 8)]


def named_summary(observations, threshold, confidence_level, distribution):
    numbered = [row for row in observations if row['scenario'] > 0]
    matched = [row for row in numbered if row.get('original_delay_plots', {}).get('verified')]
    matched_numbers = {row['scenario'] for row in matched}
    course_samples = defaultdict(list)
    scenario_days, missing_terminal = [], []
    for row in matched:
        scenario = row['scenario']
        entries = row['original_delay_plots']['courses']
        for entry in entries:
            course_samples[entry['course_id']].append((scenario, entry))
        terminals = [entry['terminal_event'] for entry in entries]
        if all(sample is not None for sample in terminals):
            rounded = all(sample['integer_delay_s'] <= threshold for sample in terminals)
            printed = all(sample['original_delay_s'] <= threshold for sample in terminals)
            scenario_days.append({'scenario': scenario, 'all_terminal_delays_within_threshold': printed,
                                  'all_integer_tt_delays_within_threshold': rounded})
        else:
            missing_terminal.append(scenario)
    complete = len(scenario_days) == len(numbered)
    status = ('full_finite_scenario_enumeration' if complete and len(numbered) == 200
              else 'conditional_on_independent_representative_scenarios' if complete
              else 'unavailable_due_to_missing_scenarios_or_terminal_delays')
    confidence = status == 'conditional_on_independent_representative_scenarios'
    summed = []
    for course_id, entries in sorted(course_samples.items()):
        paired = [entry['terminal_event'] for _, entry in entries if entry['terminal_event'] is not None]
        values = [event['original_delay_s'] for event in paired]
        count = sum(value <= threshold for value in values)
        summed.append({'course_id': course_id, 'initial_delay_s': distribution([e['initial_event']['original_delay_s'] for _, e in entries]),
                       'mean_arrival_departure_delay_s': distribution([e['mean_arrival_departure_delay_s'] for _, e in entries]),
                       'terminal_delay_s': distribution(values), 'matched_terminal_scenarios': len(values),
                       'terminal_within_threshold_count': count,
                       'terminal_within_threshold_fraction': count / len(values) if values else None,
                       'conditional_wilson_interval': wilson(count, len(values), confidence_level) if confidence else None,
                       'integer_tt_and_named_threshold_disagreement_count': sum(
                           (event['integer_delay_s'] <= threshold) != (event['original_delay_s'] <= threshold) for event in paired
                       )})
    passes = sum(row['all_terminal_delays_within_threshold'] for row in scenario_days)
    return {'native_reported_resolution_s': SAMPLE_PRECISION_S, 'numbered_scenario_count': len(numbered),
            'matched_plot_scenarios': [row['scenario'] for row in matched],
            'excluded_from_terminal_comparison': sorted(({row['scenario'] for row in numbered} - matched_numbers)
                                                       | set(missing_terminal)),
            'scenario_results': scenario_days, 'courses': summed,
            'scenario_all_courses_within_threshold_count': passes,
            'scenario_all_courses_within_threshold_fraction': passes / len(scenario_days) if scenario_days else None,
            'integer_tt_all_courses_within_threshold_count': sum(row['all_integer_tt_delays_within_threshold'] for row in scenario_days),
            'confidence_level': confidence_level, 'confidence_status': status,
            'scenario_level_conditional_wilson_interval': wilson(passes, len(scenario_days), confidence_level) if confidence else None,
            'scenario_independence_verified': False}
