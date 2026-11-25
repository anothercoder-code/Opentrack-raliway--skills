"""Read the evidenced single-day SIMU VII running-time timetable form."""

from dataclasses import dataclass
import re
from typing import Annotated

from pydantic import Field, StrictBool, model_validator

from .bound_timetable_exchange import (
    SECONDS_PER_DAY, SOURCE_LIMIT, BoundTimetableExchangeTools, BoundTimetableInput,
    apply_bound_visit, bind_rows, clock_fields, grouped_native_rows,
)
from .operating_plan_edit import need
from .operating_plan_edit_tools import Id


CLOCK = re.compile(r'([01][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])')
DURATION = re.compile(r'[0-9]{1,5}(?:\.0+)?')
IGNORED_RECORDS = {'0', '99999'}
STATION_SUFFIXES = {'H1', 'K1'}


class ImportSimuVII(BoundTimetableInput):
    course_by_simu_id: Annotated[dict[Id, Id], Field(min_length=1, max_length=1000)]
    station_by_simu_sign: Annotated[dict[Id, Id], Field(max_length=10000)] = Field(default_factory=dict)
    derive_arrivals_for_run: StrictBool = False

    @model_validator(mode='after')
    def exact_courses(self):
        if len(set(self.course_by_simu_id.values())) != len(self.course_by_simu_id):
            raise ValueError('Each selected SIMU VII service must target a different native Course')
        return self


@dataclass(frozen=True)
class Visit:
    line: int
    station: str
    arrival: int | None
    departure: int
    source_dwell: int
    run_seconds: int | None

    def timetable_fields(self, derive_arrival):
        arrival = self.departure - self.source_dwell if derive_arrival else self.arrival
        fields = clock_fields(arrival, self.departure)
        dwell = self.source_dwell if self.run_seconds is not None else 0
        return {**fields, 'stop_at_station': self.source_dwell > 0, 'dwell_s': dwell}


def duration(value, line):
    need(DURATION.fullmatch(value) is not None, f'Expected an integer SIMU VII duration at line {line}')
    seconds = int(value.split('.', 1)[0])
    need(seconds < SECONDS_PER_DAY, f'SIMU VII duration exceeds one day at line {line}')
    return seconds


def first_visit(tokens, line):
    station, start, *tail = tokens
    if start == 'B':
        need(len(tail) >= 2, f'SIMU VII split B start clock requires a dwell column at line {line}')
        start, *tail = tail
    elif start.startswith('B'):
        start = start[1:]
    need(tail and CLOCK.fullmatch(start) is not None, f'SIMU VII starting clock requires HH:MM:SS and a dwell at line {line}')
    hours, minutes, seconds = map(int, start.split(':'))
    departure = hours * 3600 + minutes * 60 + seconds
    dwell = duration(tail[0], line)
    need(dwell <= departure, f'SIMU VII first stop extends before the selected operating day at line {line}')
    return Visit(line, station, departure - dwell if dwell else None, departure, dwell, None)


def following_visit(tokens, line, previous):
    station, *fields = tokens
    if fields[0] in STATION_SUFFIXES:
        station += ' ' + fields.pop(0)
    need(len(fields) >= 2, f'SIMU VII running record needs a dwell and running time at line {line}')
    dwell = duration(fields[0], line)
    run_index = 2 if dwell > 0 else 1
    need(len(fields) > run_index, f'SIMU VII positive dwell needs the intervening field at line {line}')
    run = duration(fields[run_index], line)
    need(run > 0, f'SIMU VII running interval must be positive at line {line}')
    depart = previous.departure + run + dwell
    need(depart < SECONDS_PER_DAY, f'SIMU VII cumulative time exceeds the supported single day at line {line}')
    need(station != previous.station, f'SIMU VII adjacent rows need distinct Station codes at line {line}')
    return Visit(line, station, None, depart, dwell, run)


def parse_simu(raw):
    need(isinstance(raw, bytes) and 0 < len(raw) <= SOURCE_LIMIT, 'Expected nonempty SIMU VII input up to 2 MB')
    content = raw.decode('ascii').replace('\r\n', '\n')
    need(re.search(r'[^ -~\t\n]', content) is None, 'SIMU VII requires ASCII space or tab-delimited text')
    line0, *lines = content.split('\n')
    need(line0.split() and line0.split()[0] == 'FAHRPLAN', 'Expected SIMU VII FAHRPLAN header')
    need(len(line0) <= 4093, 'SIMU VII header exceeds the original input buffer')
    schedule = {}
    active = None
    waiting_for_course = False
    closed = False
    for number, line in enumerate(lines, 2):
        need(len(line) <= 4093, f'SIMU VII line {number} exceeds the original input buffer')
        tokens = line.split()
        if not tokens:
            continue
        token = tokens[0]
        need(not closed, f'Unexpected SIMU VII input after END at line {number}')
        if waiting_for_course:
            need(token not in {'FAHRPLAN', 'ZUG', 'END', *IGNORED_RECORDS} and 'BED' not in token,
                 f'SIMU VII train marker has no following Course ID at line {number}')
            need(token not in schedule, f'Duplicate SIMU VII Course ID {token!r}')
            active = token
            schedule[active] = []
            waiting_for_course = False
        elif token == 'ZUG' or 'BED' in token:
            waiting_for_course = True
        elif token == 'END':
            closed = True
        elif token not in IGNORED_RECORDS:
            need(active is not None and 3 <= len(tokens) <= 9, f'Invalid SIMU VII Station record at line {number}')
            visits = schedule[active]
            visit = following_visit(tokens, number, visits[-1]) if visits else first_visit(tokens, number)
            visits.append(visit)
    need(closed and schedule and all(len(visits) >= 2 for visits in schedule.values()),
         'SIMU VII input requires END and at least two Station rows per Course')
    return (schedule,)


def import_simu(plan, schedule, args):
    selection = args.course_by_simu_id
    references = bind_rows(plan, selection, schedule)
    aliases = args.station_by_simu_sign
    selected_signs = {visit.station for course in selection for visit in schedule[course]}
    need(aliases.keys() <= selected_signs and set(aliases.values()) <= plan.stations.keys(),
         'Station aliases must bind selected SIMU VII codes to existing native Stations')
    by_course, _ = grouped_native_rows(plan)
    assembly = {}
    for source, course in selection.items():
        visits = schedule[source]
        rows = sorted(by_course[course], key=lambda row: row.contents[3].value)
        need(len(rows) == len(visits), f'SIMU VII visit count differs from native Course {course!r}')
        report = []
        for index, (visit, row) in enumerate(zip(visits, rows, strict=True)):
            station = aliases.get(visit.station, visit.station)
            need(station in plan.stations, f'No native Station for SIMU VII code {visit.station!r}')
            derived = args.derive_arrivals_for_run and visit.run_seconds is not None
            fields = visit.timetable_fields(derived)
            item = apply_bound_visit(row, references, course, station, index, visit.line, fields,
                                     args.endpoint_clocks, len(visits) - 1)
            item.update(source_line=visit.line, source_dwell_s=visit.source_dwell,
                        source_running_time_s=visit.run_seconds)
            if derived:
                item['derived_arrival_for_run'] = True
            report.append(item)
        assembly[source] = {'course_id': course, 'visits': report}
        plan.changed_course_visits.add(course)
    return {'format': 'simu_vii', 'source_services': len(schedule),
            'imported_rows': sum(len(item['visits']) for item in assembly.values()), 'assembly': assembly}


class SimuVIITools(BoundTimetableExchangeTools):
    def import_timetable(self, args):
        return self.publish_exchange(args, parse_simu, import_simu, 'NATIVE_SIMU_VII_INVALID', 'SIMU VII')


def tool_definitions(root):
    service = SimuVIITools(root)
    return [('opentrack_import_native_simu_vii_timetable',
             'Import a single-day SIMU VII FAHRPLAN into explicitly mapped existing native Courses. '
             'Writes original relative clocks and stop fields with an explicit arrival derivation option for run preparation.',
             ImportSimuVII, service.import_timetable, False, False)]
