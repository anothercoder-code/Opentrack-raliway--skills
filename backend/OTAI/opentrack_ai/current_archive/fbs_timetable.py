"""Import the tabular FBS timetable read by the original OpenTrack 1.7."""

from collections import defaultdict
from dataclasses import dataclass, field
import re
from typing import Annotated, Literal

from pydantic import Field, StrictStr, model_validator

from .bound_timetable_exchange import (
    SOURCE_LIMIT, BoundTimetableExchangeTools, BoundTimetableInput, apply_bound_visit,
    bind_rows, clock_fields, grouped_native_rows,
)
from .operating_plan_edit import need, text
from .operating_plan_edit_tools import Id


NAME = Annotated[StrictStr, Field(min_length=1, max_length=200, pattern=r'^[^\x00-\x1F\x7F]+$')]
TIMESTAMP = re.compile(r'([0-9]{1,2})[:.]([0-9]{1,2})(?:([:.,])([0-9]{1,2}))?')
MARKERS = {'an': 'arrival', 'ab': 'departure', 'an/ab': 'both', 'an ab': 'both', 'anab': 'both'}


class ImportFBS(BoundTimetableInput):
    course_by_fbs_id: Annotated[dict[Id, Id], Field(min_length=1, max_length=1000)]
    station_by_fbs_name: Annotated[dict[NAME, Id], Field(max_length=10000)] = Field(default_factory=dict)
    source_encoding: Literal['windows-1252', 'utf-8'] = 'windows-1252'

    @model_validator(mode='after')
    def exact_courses(self):
        if len(set(self.course_by_fbs_id.values())) != len(self.course_by_fbs_id):
            raise ValueError('Each selected FBS service must target a different native Course')
        return self


@dataclass(frozen=True)
class ClockEvent:
    clock_field: str
    seconds: int | None
    stop: bool


@dataclass(frozen=True)
class MatrixCell:
    line: int
    station_name: str
    events: tuple[ClockEvent, ...]


@dataclass
class Visit:
    station: str
    source_lines: list[int] = field(default_factory=list)
    arrival: int | None = None
    departure: int | None = None
    stop: bool = False

    def add(self, cell):
        self.source_lines.append(cell.line)
        for event in cell.events:
            if event.clock_field == 'arrival':
                self.arrival = event.seconds
            else:
                self.departure = event.seconds
            self.stop = event.stop

    def saved_fields(self):
        fields = clock_fields(self.arrival, self.departure)
        dwell = 0
        if self.arrival is not None and self.departure is not None:
            dwell = self.departure - self.arrival
            need(dwell >= 0, f'FBS departure precedes arrival at {self.station!r}; this format contract is same-day')
        return {**fields, 'dwell_s': dwell, 'stop_at_station': self.stop}


def time_value(value, line):
    value = value.strip()
    passing = value.startswith('(') and value.endswith(')')
    token = value[1:-1].strip() if passing else value
    if token == '|':
        return None, passing
    match = TIMESTAMP.fullmatch(token)
    if match is not None:
        hour, minute = map(int, match.groups()[:2])
        separator, third = match.groups()[2:]
        second = int(third or '0')
        if separator == ',':
            need(len(third) == 1, f'FBS decimal minutes require one tenth digit at line {line}')
            second *= 6
    else:
        need(re.fullmatch(r'[0-9]{1,6}', token) is not None, f'Invalid FBS clock {value!r} at line {line}')
        hour = int(token[:2])
        minute = int(token[2:4] or '0')
        second = int(token[4:] or '0')
    need(hour <= 23 and minute <= 59 and second <= 59, f'FBS clock must be within one day at line {line}')
    return hour * 3600 + minute * 60 + second, passing


def cell_events(cell, marker, line):
    cell = cell.strip()
    if not cell or (cell != '|' and re.search(r'[0-9:.,]', cell) is None):
        return ()
    need(marker is not None, f'FBS time data requires an/ab row markers at line {line}')
    pieces = cell.split('/')
    need(len(pieces) <= (2 if marker == 'both' else 1), f'Unexpected FBS slash clock at line {line}')
    first, passing = time_value(pieces[0], line)
    if marker == 'arrival':
        return (ClockEvent('arrival', first, True),)
    if marker == 'departure' or passing:
        events = [ClockEvent('departure', first, not passing)]
    else:
        events = [ClockEvent('arrival', first, True)]
    if len(pieces) == 2:
        second, passing = time_value(pieces[1], line)
        events.append(ClockEvent('departure', second, not passing))
    return tuple(events)


def parse_fbs(raw, source_encoding='windows-1252'):
    need(isinstance(raw, bytes) and 0 < len(raw) <= SOURCE_LIMIT, 'Expected nonempty FBS input up to 2 MB')
    codec = 'utf-8-sig' if source_encoding == 'utf-8' else 'cp1252'
    content = raw.decode(codec)
    need('\r' not in content.replace('\r\n', '') and re.search(r'[\x00-\x08\x0b-\x1f\x7f]', content.replace('\r\n', '\n')) is None,
         'FBS requires tab-delimited text with LF or CRLF lines')
    trains = ()
    parsed = {}
    station = ''
    separated = False
    footer = None
    for number, line in enumerate(content.split('\n'), 1):
        line = line.removesuffix('\r')
        need(len(line.encode('utf-8' if source_encoding == 'utf-8' else 'cp1252')) <= 4093,
             f'FBS line {number} exceeds the original input buffer')
        if len(line) < 2:
            separated = True
            continue
        if separated and line.startswith('Richtung '):
            footer = number
            break
        separated = False
        columns = line.split('\t')
        if not trains:
            if len(columns) <= 2:
                continue
            trains = tuple(item.strip() for item in columns[2:])
            need(all(trains) and len(trains) == len(set(trains)), f'FBS header requires distinct nonempty Course IDs at line {number}')
            parsed = {course: [] for course in trains}
            continue
        if len(columns) <= 2:
            continue
        need(len(columns) <= len(trains) + 2, f'FBS row has more cells than its header at line {number}')
        label, marker = columns[0].strip(), MARKERS.get(columns[1].strip())
        for course, cell in zip(trains, columns[2:]):
            events = cell_events(cell, marker, number)
            if events:
                station = label or station
                need(station, f'FBS line {number} has time data but no preceding Station name')
                parsed[course].append(MatrixCell(number, station, events))
    need(parsed and any(parsed.values()), 'No FBS timetable cells found')
    return parsed, footer


def resolve_station(value, stations, names, overrides):
    if value in overrides:
        return overrides[value]
    matches = names.get(value.upper(), [])
    need(len(matches) <= 1, f'Ambiguous native Station name {value!r}; use an explicit FBS mapping')
    if matches:
        return matches[0]
    need(value in stations, f'No native Station sign or name for FBS {value!r}')
    return value


def import_fbs(plan, parsed, footer, args):
    selection = args.course_by_fbs_id
    references = bind_rows(plan, selection, parsed)
    aliases = args.station_by_fbs_name
    selected_names = {cell.station_name for course in selection for cell in parsed[course]}
    need(aliases.keys() <= selected_names and set(aliases.values()) <= plan.stations.keys(),
         'Station aliases must bind selected FBS names to existing native Stations')
    names = defaultdict(list)
    for sign, station in plan.stations.items():
        name = text(station, 2)
        if name:
            names[name.upper()].append(sign)
    by_course, _ = grouped_native_rows(plan)
    assembly = {}
    for source, course in selection.items():
        visits = []
        for cell in parsed[source]:
            station = resolve_station(cell.station_name, plan.stations, names, aliases)
            if not visits or visits[-1].station != station:
                visits.append(Visit(station))
            visits[-1].add(cell)
        rows = sorted(by_course[course], key=lambda item: item.contents[3].value)
        need(visits and len(rows) == len(visits), f'FBS visit count differs from native Course {course!r}')
        report = []
        for index, (visit, row) in enumerate(zip(visits, rows, strict=True)):
            saved = apply_bound_visit(row, references, course, visit.station, index, visit.source_lines[0],
                                      visit.saved_fields(), args.endpoint_clocks, len(visits) - 1)
            report.append({**saved, 'source_lines': visit.source_lines})
        assembly[source] = {'course_id': course, 'visits': report}
        plan.changed_course_visits.add(course)
    return {'format': 'fbs', 'source_encoding': args.source_encoding, 'source_services': len(parsed),
            'next_direction_line': footer, 'imported_rows': sum(len(item['visits']) for item in assembly.values()),
            'assembly': assembly}


class FBSTools(BoundTimetableExchangeTools):
    def import_timetable(self, args):
        return self.publish_exchange(args, lambda raw: parse_fbs(raw, args.source_encoding),
                                     import_fbs, 'NATIVE_FBS_INVALID', 'FBS')


def tool_definitions(root):
    service = FBSTools(root)
    return [('opentrack_import_native_fbs_timetable',
             'Import the original FBS tabular planned timetable into explicitly mapped existing native Courses. '
             'Reads arrival, departure, pass and decimal-minute cells, and publishes a checked native timetable increment.',
             ImportFBS, service.import_timetable, False, False)]
