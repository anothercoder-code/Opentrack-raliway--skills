"""Read the original OpenTrack Protim version-1 PIF timetable records."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import re
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr, model_validator

from .bound_timetable_exchange import (
    SOURCE_LIMIT, BoundTimetableExchangeTools, BoundTimetableInput, apply_bound_visit,
    bind_rows, clock_fields, grouped_native_rows,
)
from .operating_plan_edit import need
from .operating_plan_edit_tools import Id


TIME = re.compile(r'([0-9]{2}):([0-5][0-9])(?::([0-5][0-9]))?')
EXTRA_RECORDS = {'TRF', 'TDT', 'REF', 'TLD', 'LOC', 'PLT', 'NWK', 'TLK', 'NTE'}
THD_WEEK_SLOTS = 7


class ImportProtimPIF(BoundTimetableInput):
    course_by_pif_id: Annotated[dict[Id, Id], Field(min_length=1, max_length=1000)]
    station_by_pif_sign: Annotated[dict[Id, Id], Field(max_length=10000)] = Field(default_factory=dict)
    source_encoding: Literal['windows-1252', 'utf-8'] = 'windows-1252'
    mirror_passage_arrivals_for_run: StrictBool = False
    thd_week_pattern: Annotated[StrictStr, Field(max_length=128, pattern=r'^[YyNn*?]*$')] | None = None

    @model_validator(mode='after')
    def exact_bindings(self):
        if len(set(self.course_by_pif_id.values())) != len(self.course_by_pif_id):
            raise ValueError('Each selected PIF service must target a different native Course')
        return self


@dataclass(frozen=True)
class Movement:
    line: int
    origin: str
    destination: str
    depart: int
    arrive: int
    stop_marker_line: int | None


@dataclass
class HeaderVariant:
    line: int
    pattern: str | None
    movements: list[Movement] = field(default_factory=list)


@dataclass(frozen=True)
class Visit:
    source_line: int
    station: str
    arrival: int | None
    departure: int | None
    stop: bool
    stop_marker_line: int | None

    def saved_fields(self):
        dwell = self.departure - self.arrival if self.arrival is not None and self.departure is not None else 0
        return {**clock_fields(self.arrival, self.departure), 'dwell_s': dwell, 'stop_at_station': self.stop}


def elapsed(value, line):
    match = TIME.fullmatch(value)
    need(match is not None, f'PIF movement clocks require HH:MM or HH:MM:SS at line {line}')
    hours, minutes, seconds = (int(item or 0) for item in match.groups())
    total = hours * 3600 + minutes * 60 + seconds
    need(total != 86400, f'PIF clock 24:00 is ambiguous in the original importer at line {line}; use an explicit native date edit')
    return total


def assemble(movements):
    last = None
    visits = []
    for movement in movements:
        if last is not None:
            need(last.destination == movement.origin, f'PIF movement chain is discontinuous at line {movement.line}')
            need(last.arrive <= movement.depart, f'PIF movement times go backwards at line {movement.line}')
        marker = movement.stop_marker_line if last is not None else None
        visits.append(Visit(movement.line, movement.origin, last.arrive if marker is not None else None,
                            movement.depart, marker is not None, marker))
        last = movement
    visits.append(Visit(last.line, last.destination, last.arrive, None, True, None))
    return tuple(visits)


def normalize_week_pattern(value):
    return ''.join(char.upper() if char in 'YyNn' else '*'
                   for char in value[:THD_WEEK_SLOTS].ljust(THD_WEEK_SLOTS, '*'))


def header_week_pattern(columns, course, codec, number):
    # The filtering menu uses strtok, while the version-1 movement importer
    # keeps empty columns. Check both source positions before combining them.
    tokens = ['THD', *(value for value in columns if value)]
    need(len(tokens) >= 8 and tokens[3] == course,
         f'PIF THD at line {number} requires the same fourth-column and fourth-token Course ID and an eighth token')
    prefix = tokens[7].encode(codec)[:THD_WEEK_SLOTS]
    need(len(prefix) == THD_WEEK_SLOTS, f'PIF THD at line {number} needs seven source week-pattern bytes')
    return normalize_week_pattern(prefix.decode('latin-1'))


def compatible_week_pattern(source, query):
    return all(a == b or '*' in (a, b) for a, b in zip(source, query, strict=True))


def select_variants(variants, week_pattern, selected_sources):
    query = normalize_week_pattern(week_pattern) if week_pattern is not None else None
    schedules, headers = {}, {}
    matched = 0
    for course, group in variants.items():
        matches = group if query is None else [item for item in group if compatible_week_pattern(item.pattern, query)]
        matched += len(matches)
        if selected_sources is not None and course not in selected_sources:
            continue
        if not matches and selected_sources is not None:
            raise ValueError(f'PIF Course {course!r} has no THD variant matching week pattern {query}')
        if not matches:
            continue
        need(len(matches) == 1,
             f'PIF Course {course!r} has multiple THD variants matching week pattern {query} at lines '
             f'{[item.line for item in matches[:12]]}')
        chosen = matches[0]
        schedules[course] = assemble(chosen.movements)
        if query is not None:
            headers[course] = {'source_thd_line': chosen.line, 'source_thd_week_pattern': chosen.pattern}
    report = None if query is None else {
        'requested_pattern': week_pattern, 'normalized_pattern': query,
        'matched_variants': matched, 'excluded_variants': sum(map(len, variants.values())) - matched,
        'selected_headers': headers,
    }
    return schedules, report


def parse_pif(raw, source_encoding='windows-1252', thd_week_pattern=None, *, selected_sources=None):
    need(isinstance(raw, bytes) and 0 < len(raw) <= SOURCE_LIMIT, 'Expected nonempty Protim PIF input up to 2 MB')
    codec = 'utf-8' if source_encoding == 'utf-8' else 'cp1252'
    content = raw.decode('utf-8-sig' if source_encoding == 'utf-8' else codec)
    content = content.replace('\r\n', '\n')
    need(re.search(r'[\x00-\x08\x0b-\x1f\x7f]', content) is None,
         'Protim PIF requires tab-delimited text with LF or CRLF lines')
    header, *rows = content.split('\n')
    need(header.startswith('PIF\t'), 'Expected the original tab-delimited Protim PIF header')
    need(len(header.encode(codec)) <= 4093, 'Protim PIF header exceeds the original input buffer')
    variants, counts = defaultdict(list), Counter()
    active = None
    latest_stop = None
    closed = False
    for number, line in enumerate(rows, 2):
        need(len(line.encode(codec)) <= 4093, f'Protim PIF line {number} exceeds the original input buffer')
        if not line:
            continue
        record, *columns = line.split('\t')
        need(not closed, f'Unexpected Protim PIF record after PIT trailer at line {number}')
        if record == 'THD':
            need(len(columns) >= 3 and columns[2], f'PIF THD requires a fourth-column Course ID at line {number}')
            course = columns[2]
            if thd_week_pattern is None:
                need(course not in variants, f'Duplicate PIF Course {course!r} at line {number}')
                pattern = None
            else:
                pattern = header_week_pattern(columns, course, codec, number)
                latest_stop = None
            active = HeaderVariant(number, pattern)
            variants[course].append(active)
        elif record == 'TMV':
            need(active is not None and len(columns) >= 8, f'PIF TMV requires at least nine columns in a Course at line {number}')
            origin, destination = columns[2], columns[3]
            need(origin and destination and origin != destination, f'PIF TMV requires distinct Station codes at line {number}')
            depart, arrive = elapsed(columns[5], number), elapsed(columns[6], number)
            need(arrive >= depart, f'PIF TMV arrives before it departs at line {number}')
            stop_line = latest_stop[1] if latest_stop is not None and latest_stop[0] == origin and columns[7] == '0' else None
            active.movements.append(Movement(number, origin, destination, depart, arrive, stop_line))
        elif record == 'TSP':
            need(active is not None and len(columns) >= 3 and columns[2], f'PIF TSP requires a fourth-column Station code at line {number}')
            latest_stop = columns[2], number
        elif record == 'PIT':
            closed = True
        else:
            need(record in EXTRA_RECORDS, f'Unsupported Protim PIF record {record!r} at line {number}')
        counts[record] += 1
    need(closed and variants and all(item.movements for group in variants.values() for item in group),
         'Protim version-1 PIF needs TMV records in each THD and a closing PIT')
    schedules, week_report = select_variants(variants, thd_week_pattern, selected_sources)
    return schedules, dict(counts), week_report


def import_pif(plan, schedules, source_counts, week_report, args):
    selection = args.course_by_pif_id
    references = bind_rows(plan, selection, schedules)
    aliases = args.station_by_pif_sign
    found = {visit.station for course in selection for visit in schedules[course]}
    need(aliases.keys() <= found and set(aliases.values()) <= plan.stations.keys(),
         'Station aliases must bind selected PIF codes to existing native Stations')
    by_course, _ = grouped_native_rows(plan)
    assembly = {}
    for source, course in selection.items():
        timetable = schedules[source]
        rows = sorted(by_course[course], key=lambda item: item.contents[3].value)
        need(len(rows) == len(timetable), f'PIF visit count differs from native Course {course!r}')
        report = []
        for index, (visit, row) in enumerate(zip(timetable, rows, strict=True)):
            station = aliases.get(visit.station, visit.station)
            need(station in plan.stations, f'No native Station for PIF code {visit.station!r}')
            fields = visit.saved_fields()
            has_passage = 0 < index < len(timetable) - 1 and not visit.stop
            mirrored_passage = has_passage and args.mirror_passage_arrivals_for_run
            if mirrored_passage:
                fields.update(arrival=fields['departure'], arrival_day_offset=fields['departure_day_offset'])
            entry = apply_bound_visit(row, references, course, station, index, visit.source_line,
                                      fields, args.endpoint_clocks, len(timetable) - 1)
            entry['source_line'] = visit.source_line
            if visit.stop_marker_line is not None:
                entry['stop_marker_line'] = visit.stop_marker_line
            if mirrored_passage:
                entry['mirrored_passage_arrival'] = True
            report.append(entry)
        assembly[source] = {'course_id': course, 'visits': report}
        plan.changed_course_visits.add(course)
    report = {'format': 'protim_pif_v1', 'source_encoding': args.source_encoding,
              'source_record_counts': source_counts, 'imported_rows': sum(len(item['visits']) for item in assembly.values()),
              'assembly': assembly}
    if week_report is not None:
        report['thd_week_filter'] = week_report
    return report


class ProtimPIFTools(BoundTimetableExchangeTools):
    def import_timetable(self, args):
        return self.publish_exchange(
            args, lambda raw: parse_pif(raw, args.source_encoding, args.thd_week_pattern,
                                        selected_sources=args.course_by_pif_id if args.thd_week_pattern is not None else None),
            import_pif, 'NATIVE_PROTIM_PIF_INVALID', 'Protim PIF')


def tool_definitions(root):
    service = ProtimPIFTools(root)
    return [('opentrack_import_native_protim_pif_timetable',
             'Import original Protim/PIF version-1 movement and stop records into explicitly mapped existing native Courses. '
             'Optionally select THD variants using an original seven-position week pattern. '
             'Publishes a validated native timetable increment with existing project references.',
             ImportProtimPIF, service.import_timetable, False, False)]
