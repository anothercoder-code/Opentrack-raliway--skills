"""Station and terminal event throughput from existing original output."""

from bisect import bisect_left
from collections import Counter, defaultdict
import re
from typing import Annotated

from pydantic import Field, StrictInt, model_validator

from ..errors import APIError
from . import catalogs, native_evaluation_formats as fmt, writer
from .native_interlocking import FrozenRailwayRun
from .native_result_tools import CourseOutcome, EvaluateNativeRunTools, Name
from .native_run_evaluation import read_receipts
from .operating_plan_edit import text
from .prepare_contract.auxiliary import records
from .runfile_parameters import time_seconds
from .tools import Input, PathText


EVENT_KIND = {'Arr.': 'arrivals', 'Dep.': 'departures', 'Pass': 'passes'}
TERMINAL_KIND = {'Arr.': 'terminal_arrivals', 'Pass': 'terminal_passes'}
QUANTITIES = (*EVENT_KIND.values(), 'station_events', 'origin_departures', *TERMINAL_KIND.values(),
              'terminal_completions')
AbsoluteSecond = Annotated[StrictInt, Field(ge=0, le=2**31 - 1)]


class ObservationWindow(Input):
    start_s: AbsoluteSecond
    stop_s: AbsoluteSecond

    @model_validator(mode='after')
    def ordered_window(self):
        if self.stop_s <= self.start_s:
            raise ValueError('Throughput window must increase')
        return self


class ThroughputCourse(CourseOutcome):
    origin_station: Name
    terminal_station: Name
    distance_m: Annotated[float, Field(gt=0, allow_inf_nan=False)]


class ThroughputStudy(Input):
    output_directory: PathText
    evidence_directory: PathText
    course_outcomes: Annotated[list[ThroughputCourse], Field(min_length=1, max_length=10000)]
    station_signs: Annotated[list[Name], Field(min_length=1, max_length=1000)]
    windows: Annotated[list[ObservationWindow], Field(max_length=24)] = Field(default_factory=list)
    peak_window_s: Annotated[StrictInt, Field(gt=0, le=604800)] | None = None


def configured_window(railway, evidence):
    members = [member for member in evidence['input_sha256'] if member.lower().endswith('.run')]
    fmt.require(len(members) == 1, 'Station throughput needs one frozen .run file')
    settings = records(railway.dependency(str(railway.settings['project_root'] / members[0])))
    keys = {key: [value for name, value, _ in settings if key == name]
            for key in ('Start Time', 'Start Day Offset', 'Stop Time', 'Stop Day Offset')}
    fmt.require(all(len(value) == 1 for value in keys.values()), 'Missing or ambiguous frozen simulation window')
    bound = [time_seconds(keys[edge + ' Time'][0].encode('ascii'), keys[edge + ' Day Offset'][0].encode('ascii'))
             for edge in ('Start', 'Stop')]
    shown = railway.receipt['protocol'].get('configured_window') or ''
    printed = []
    for token in shown.split(' - '):
        match = re.fullmatch(r'(?:(\d{1,5})\s*/\s*)?([0-9]{2}:[0-9]{2}:[0-9]{2})', token.strip(), re.ASCII)
        fmt.require(match is not None, 'Invalid original configured window display')
        day, clock = match.groups()
        printed.append(time_seconds(clock.encode('ascii'), (day or '0').encode('ascii')))
    fmt.require(printed == bound and bound[0] < bound[1], 'Original protocol and frozen configured window differ')
    return bound


def station_timelines(courses, station_names, origin, stop):
    labels = defaultdict(list)
    for sign, display in station_names.items():
        labels[display].append(sign)
    by_station = defaultdict(list)
    for course in courses:
        cid = course['course_id']
        events = course['events']
        origin_event = next((index for index, event in enumerate(events) if event['kind'] == 'Dep.'), None)
        terminal_index = len(events) - 1
        fmt.require(origin_event is not None and terminal_index > origin_event
                    and events[origin_event] == course['origin_event'] and events[-1] == course['last_observed_event']
                    and events[-1]['kind'] in TERMINAL_KIND,
                    f'Original verified origin or terminal event is inconsistent for {cid}')
        for index, event in enumerate(events):
            choices = labels[event['station']]
            fmt.require(len(choices) == 1, f'Missing or ambiguous frozen station label: {event["station"]}')
            clock = event['time_s']
            fmt.require(origin <= clock <= stop, f'Original {cid} station time is outside the configured window')
            by_station[choices[0]].append({
                'time_s': clock, 'course_id': cid, 'event_index': index, 'kind': event['kind'],
                'departure_from_course_origin': index == origin_event, 'course_terminal': index == terminal_index,
            })
    for timeline in by_station.values():
        timeline.sort(key=lambda event: (event['time_s'], event['course_id'], event['event_index']))
    return by_station


def reconcile_totals(statistics, timelines, stations):
    totals = {}
    zero = dict.fromkeys(EVENT_KIND.values(), 0)
    for row in statistics:
        sign = row['station']
        fmt.require(sign in stations and sign not in totals, f'Missing or duplicate frozen Station sign: {sign}')
        counts = {key: row[key] for key in zero}
        fmt.require(all(value >= 0 for value in counts.values()), f'Negative native Station Statistics: {sign}')
        totals[sign] = counts
    for sign in sorted(totals.keys() | timelines.keys()):
        events = Counter(EVENT_KIND[entry['kind']] for entry in timelines.get(sign, []))
        fmt.require({key: events[key] for key in zero} == totals.get(sign, zero),
                    f'Original Station Statistics disagree with complete .tt events at {sign}')
    return totals


def counts(timeline):
    by_quantity = {key: [] for key in QUANTITIES}
    for event in timeline:
        by_quantity[EVENT_KIND[event['kind']]].append(event)
        by_quantity['station_events'].append(event)
        if event['departure_from_course_origin']:
            by_quantity['origin_departures'].append(event)
        if event['course_terminal']:
            by_quantity[TERMINAL_KIND[event['kind']]].append(event)
            by_quantity['terminal_completions'].append(event)
    return by_quantity


def rolling_peak(events, start, stop, width):
    times = [entry['time_s'] for entry in events]
    # For integer-start, half-open windows, a count can rise only at an entry
    # at right edge. Include the parent start and choose the earliest tie.
    starts = sorted({start, *(time - width + 1 for time in times if start < time - width + 1 <= stop - width)})
    best = None
    for at in starts:
        first = bisect_left(times, at)
        last = bisect_left(times, at + width)
        if best is None or last - first > best['count']:
            best = {'start_s': at, 'stop_s': at + width, 'count': last - first,
                    'first_event': events[first] if first < last else None,
                    'last_event': events[last - 1] if first < last else None}
    return {**best, 'observed_events_per_hour': round(best['count'] * 3600 / width, 6)}


def summarize_window(timeline, start, stop, peak_width):
    rows = [entry for entry in timeline if start <= entry['time_s'] < stop]
    categories = counts(rows)
    quantities = {name: len(entries) for name, entries in categories.items()}
    return {'start_s': start, 'stop_s': stop, 'duration_s': stop - start,
            'event_counts': quantities, 'distinct_course_count': len({entry['course_id'] for entry in rows}),
            'observed_events_per_hour': {key: round(value * 3600 / (stop - start), 6)
                                         for key, value in quantities.items()},
            **({'rolling_peaks': {key: rolling_peak(value, start, stop, peak_width)
                                  for key, value in categories.items()}} if peak_width is not None else {})}


def measure(railway, evidence, request):
    outcomes = railway.receipt['courses']
    observed_ids = [row['course_id'] for row in outcomes]
    used = railway.receipt['protocol']['used_courses']
    fmt.require(observed_ids and len(used) == len(observed_ids) and set(used) == set(observed_ids),
                'Supply a complete distinct Course outcome for every used Course in the original protocol')
    raw = railway.dependency(railway.settings['paths']['StationFile'])
    station_bank = catalogs.station_items(writer.load_next_compatible(raw)[0])
    names = {sign: (text(station, 2) or '').strip() for sign, station in station_bank.items()}
    selected = request['station_signs']
    fmt.require(len(set(selected)) == len(selected) and set(selected) <= names.keys(),
                'Select distinct station signs from the frozen StationFile')
    start, stop = configured_window(railway, evidence)
    windows = [(row['start_s'], row['stop_s']) for row in request['windows']] or [(start, stop)]
    width = request['peak_window_s']
    fmt.require(len(set(windows)) == len(windows) and all(start <= a < b <= stop for a, b in windows),
                'Choose distinct half-open windows inside the original configured simulation window')
    fmt.require(width is None or all(width <= b - a for a, b in windows), 'Peak window must fit each observation window')
    timelines = station_timelines(outcomes, names, start, stop)
    source = 'OT_StationStatistics.txt'
    statistics = fmt.station_statistics(railway.original_text(source))['stations']
    original = reconcile_totals(statistics, timelines, names)
    return {'verified_native_station_totals': True, 'original_used_course_count': len(used),
            'reconciled_original_station_count': len(original), 'configured_window_s': [start, stop],
            'events_at_configured_stop_s': sum(entry['time_s'] == stop for rows in timelines.values() for entry in rows),
            'peak_window_s': width, 'observation_intervals': 'Half-open [start, stop) using absolute native seconds',
            'station_results': [
                {'station_sign': sign, 'display_name': names[sign], 'original_full_run_counts': original.get(sign),
                 'complete_timetable_counts': {key: len(values) for key, values in counts(timelines[sign]).items()},
                 'windows': [summarize_window(timelines[sign], a, b, width) for a, b in windows]}
                for sign in selected
            ],
            'provenance': railway.provenance,
            'original_output_sha256': {**railway.receipt['output_sha256'], **railway.files.hashes}}


class ThroughputTools(EvaluateNativeRunTools):
    def measure(self, args):
        try:
            evidence = read_receipts(self.directory(args.evidence_directory), secure_bytes=self.secure_bytes)
            output = self.directory(args.output_directory)
            outcomes = [course.model_dump(exclude_none=True) for course in args.course_outcomes]
            railway = FrozenRailwayRun(output, evidence, outcomes, self.secure_bytes)
            request = args.model_dump(exclude={'course_outcomes', 'output_directory', 'evidence_directory'})
            return measure(railway, evidence, request)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_STATION_THROUGHPUT_INVALID', 'Could not reconcile sealed original station throughput',
                           str(exc)[:600]) from exc
