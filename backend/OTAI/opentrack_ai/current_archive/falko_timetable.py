"""Read Falko input as consumed by OpenTrack 1.7 and update bound Timetable9 rows."""

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Annotated, Literal

from pydantic import Field, model_validator

from . import catalogs as c
from .bound_timetable_exchange import (
    SECONDS_PER_DAY, SOURCE_LIMIT, UNDEFINED, BoundTimetableExchangeTools, BoundTimetableInput,
    apply_bound_visit, bind_rows, clock_fields, grouped_native_rows,
)
from .native_connections import LAYOUT, record
from .operating_plan_edit import f32, need, set_sequence, text
from .operating_plan_edit_tools import Id
from .zero_generation.native_signal_routes import obj, string


ID_TOKEN = re.compile(r'[!-~]{1,200}')
NUMBER = re.compile(r'[+-]?[0-9]{1,9}(?:\.[0-9]{1,6})?')


class ImportFalko(BoundTimetableInput):
    course_by_falko_id: Annotated[dict[Id, Id], Field(min_length=1, max_length=1000)]
    station_by_falko_type: Annotated[dict[Id, Id], Field(max_length=10000)] = Field(default_factory=dict)
    connections: Literal['require_matching', 'add_transfer'] = 'require_matching'

    @model_validator(mode='after')
    def exact_bindings(self):
        if len(set(self.course_by_falko_id.values())) != len(self.course_by_falko_id):
            raise ValueError('Each selected Falko service must target a different native Course')
        if any(ID_TOKEN.fullmatch(value) is None for value in (*self.course_by_falko_id, *self.station_by_falko_type)):
            raise ValueError('Falko source identifiers must be single ASCII tokens')
        return self


@dataclass(frozen=True)
class Visit:
    source_line: int
    station_type: str
    arrival: int | None
    departure: int | None
    target: str | None

    def timetable_fields(self):
        fields = clock_fields(self.arrival, self.departure)
        dwell = self.departure - self.arrival if self.arrival is not None and self.departure is not None else 0
        fields.update(dwell_s=dwell, stop_at_station=self.arrival is not None and (self.departure is None or dwell > 0))
        return fields


def elapsed(token, line):
    need(NUMBER.fullmatch(token) is not None, f'Invalid Falko elapsed-second column at line {line}')
    seconds = f32(float(token))
    if seconds < 0:
        return None
    need(seconds.is_integer() and seconds < 367 * SECONDS_PER_DAY,
         f'Falko clock must be a whole elapsed second through day 366 at line {line}')
    return int(seconds)


def parse_falko(raw):
    need(isinstance(raw, bytes) and 0 < len(raw) <= SOURCE_LIMIT, 'Expected nonempty Falko input up to 2 MB')
    content = raw.decode('ascii')
    need(re.fullmatch(r'[ -~\r\n]*', content) is not None and '\r' not in content.replace('\r\n', ''),
         'Falko requires printable ASCII with LF or CRLF lines')
    grouped = {}
    active = None
    headers = 0
    for number, line in enumerate(content.splitlines(), 1):
        need(len(line) <= 4093, f'Falko line {number} exceeds the original input buffer')
        if not line:
            continue
        columns = line.rstrip(' ').split(' ')
        if len(columns) == 3:
            headers += 1
            continue
        need(len(columns) == 12 and all(columns), f'Expected 12 single-space Falko columns at line {number}')
        course, station, target = columns[0], columns[4], columns[11]
        need(ID_TOKEN.fullmatch(course) and ID_TOKEN.fullmatch(station) and ID_TOKEN.fullmatch(target),
             f'Invalid Falko identifier at line {number}')
        if course != active:
            need(course not in grouped, f'Noncontiguous Falko service {course!r} at line {number}')
            grouped[course] = []
            active = course
        arrival, departure = (elapsed(columns[index], number) for index in (9, 10))
        need(arrival is not None or departure is not None, f'Falko visit has no clock at line {number}')
        if arrival is not None and departure is not None:
            need(0 <= departure - arrival <= SECONDS_PER_DAY, f'Invalid Falko dwell at line {number}')
        grouped[course].append(Visit(number, station, arrival, departure, None if target.startswith(('-', '#')) else target))
    need(grouped, 'No Falko timetable visits found')
    return grouped, headers


def station_types(stations):
    types = defaultdict(list)
    for sign, station in stations.items():
        value = text(station, 6) if len(station.contents) > 6 else None
        if value:
            types[value.upper()].append(sign)
    return types


def mapped_station(value, stations, types, mapping):
    if value in mapping:
        return mapping[value]
    matches = types.get(value.upper(), [])
    need(len(matches) <= 1, f'Ambiguous native station type {value!r}; supply an explicit mapping')
    if matches:
        return matches[0]
    need(value in stations, f'No native Station sign or type for Falko {value!r}')
    return value


def bind_connection(plan, row, owner, target, station, splitting, rows_by_visit, policy):
    need(owner != target and rows_by_visit[target, station] == 1,
         f'Falko connection {owner!r} → {target!r} needs one distinct native visit at {station!r}')
    existing = c.array(row.contents[9].value)
    matches = [record(item) for item in existing if text(item, 1) == target and (text(item, 6) or station) == station]
    expected = {'course_id': owner, 'target_course_id': target, 'station_sign': station, 'target_station_sign': station,
                'minimum_wait': '00:00:00', 'maximum_wait': UNDEFINED, 'flags': 2 if splitting else 0,
                'time_reference_type': 0, 'dispatching_distance_km': 0.0}
    if matches:
        need(matches == [expected], f'Existing native Connection differs from the Falko declaration at {owner!r}/{station!r}')
        return 'matched'
    need(policy == 'add_transfer' and not splitting,
         f'Falko connection at {owner!r}/{station!r} requires an existing native record or an explicit ordinary transfer')
    values = [[string(owner)], [string(target)], [string(station)], [string('00:00:00')], [0],
              [string(UNDEFINED)], [string(station)], [0], [0.0]]
    link = obj([('OTConnection', 6), ('NSObject', 0)], list(zip(LAYOUT, values)))
    need(record(link) == expected, 'Native Falko Connection fields differ')
    set_sequence(row, 9, [*existing, link])
    return 'added'


def import_falko(plan, parsed, headers, args):
    selection = args.course_by_falko_id
    references = bind_rows(plan, selection, parsed)
    found_types = {visit.station_type for external in selection for visit in parsed[external]}
    need(args.station_by_falko_type.keys() <= found_types and set(args.station_by_falko_type.values()) <= plan.stations.keys(),
         'Station aliases must bind selected Falko identifiers to existing native Stations')
    types = station_types(plan.stations)
    by_course, by_visit = grouped_native_rows(plan)
    assembly = {}
    for external, course in selection.items():
        visits = parsed[external]
        rows = sorted(by_course[course], key=lambda item: item.contents[3].value)
        need(len(visits) == len(rows), f'Falko visit count differs from native Course {course!r}')
        prepared = []
        for index, (visit, row) in enumerate(zip(visits, rows, strict=True)):
            station = mapped_station(visit.station_type, plan.stations, types, args.station_by_falko_type)
            report = apply_bound_visit(row, references, course, station, index, visit.source_line,
                                       visit.timetable_fields(), args.endpoint_clocks, len(visits) - 1)
            report['source_line'] = visit.source_line
            if visit.target is not None:
                target = selection.get(visit.target, visit.target)
                splitting = index > 0 and visit.departure is None
                report['connection'] = {'target_course_id': target, 'split': splitting, 'action':
                    bind_connection(plan, row, course, target, station, splitting, by_visit, args.connections)}
            prepared.append(report)
        assembly[external] = {'course_id': course, 'visits': prepared}
        plan.changed_course_visits.add(course)
    return {'format': 'falko', 'source_three_column_headers': headers, 'source_services': len(parsed),
            'imported_rows': sum(len(item['visits']) for item in assembly.values()), 'assembly': assembly}


class FalkoTools(BoundTimetableExchangeTools):
    def import_timetable(self, args):
        return self.publish_exchange(args, parse_falko, import_falko, 'NATIVE_FALKO_INVALID', 'Falko')


def tool_definitions(root):
    service = FalkoTools(root)
    return [('opentrack_import_native_falko_timetable',
             'Import OpenTrack 1.7 Falko clocks, stops and dwell into explicitly mapped existing native Courses. '
             'Verify Station order and source connections, optionally add ordinary transfers, and save a native timetable increment.',
             ImportFalko, service.import_timetable, False, False)]
