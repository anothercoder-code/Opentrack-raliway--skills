"""Select complete Course schedules from an original native .timetable archive."""

from collections import Counter, defaultdict
from math import isfinite
from typing import Annotated, Literal

from pydantic import Field, StrictBool

from ..errors import APIError
from . import catalogs as c, course_factories as cf, named_distributions, writer
from .bundle_tools import Source
from .multi_document_tools import Inventory
from .native_connections import connection
from .operating_plan_edit import UNBOUND, dictionary_replace, need, row_key, set_sequence, text
from .operating_plan_edit_tools import Id, OperatingPlanEditTools, operating_candidate
from .project_candidate_publication import ProjectSave
from .tools import Input, sha


class CourseMapping(Input):
    source_course: Id
    target_course: Id


class TimetableCopySettings(Input):
    courses: Annotated[list[CourseMapping], Field(min_length=1, max_length=1000)]
    referenced_courses: Annotated[dict[Id, Id], Field(max_length=1000)] = Field(default_factory=dict)
    station_mapping: Annotated[dict[Id, Id], Field(max_length=10000)] = Field(default_factory=dict)
    existing: Literal['reject', 'replace'] = 'reject'
    import_actual_times: StrictBool = False


class ImportNativeTimetable(ProjectSave, TimetableCopySettings):
    source_project: Inventory
    donor_timetable: Source


def set_name(record, slot, value):
    if text(record, slot) != value:
        cf.settext(record, slot, value)


def validate_actual_times(row):
    for slot, day in zip((13, 14), row.contents[15].values[2:]):
        value = text(row, slot)
        if value in (None, '', 'HH:MM:SS'):
            need(day == 0, 'Missing actual time has a nonzero day offset')
        else:
            cf.clock(value)


def import_schedule(plan, donor, args):
    selected = {item.source_course: item.target_course for item in args.courses}
    bindings = {**selected, **args.referenced_courses}
    current = plan.courses()
    need(len(selected) == len(args.courses) and selected.keys().isdisjoint(args.referenced_courses)
         and len(set(bindings.values())) == len(bindings)
         and all(cid not in UNBOUND for cid in bindings)
         and set(bindings.values()) <= current.keys(),
         'Select distinct source and existing destination Courses, including any external reference bindings')

    source = defaultdict(list)
    for row in cf.timetable(donor).values():
        cid = text(row, 1)
        if cid in selected:
            source[cid].append(row)
    need(source.keys() == selected.keys(), 'Selected donor Course has no native timetable rows')

    old = plan.rows()
    targets = set(selected.values())
    replaced = [row for row in old.values() if text(row, 1) in targets]
    need(args.existing == 'replace' or not replaced,
         'Target Course already has rows. Choose replace to replace the entire schedule')
    pairs = [(key, row) for key, row in old.items() if text(row, 1) not in targets]
    distribution_names = None
    seen_stations = {}
    external_courses = set()

    def destination_station(old_sign):
        mapped = args.station_mapping.get(old_sign, old_sign)
        need(mapped in plan.stations, f'Station {old_sign!r} has no destination Station binding')
        need(seen_stations.setdefault(mapped, old_sign) == old_sign, 'Station bindings collapse distinct donor Stations')
        return mapped

    def destination_course(old_id):
        need(old_id in bindings, f'Referenced donor Course {old_id!r} requires an explicit binding')
        if old_id not in selected:
            external_courses.add(old_id)
        return bindings[old_id]

    imported = []
    for old_id, new_id in selected.items():
        ordered = sorted(source[old_id], key=lambda row: row.contents[3].value)
        need(all(row.contents[3].value == index and row.contents[4].value == len(ordered) - 1
                 for index, row in enumerate(ordered)), f'Donor Course {old_id} has an incomplete native index domain')
        for original in ordered:
            row = cf.clone(original)
            original_station = text(original, 5)
            station = destination_station(original_station)
            set_name(row, 1, new_id)
            set_name(row, 5, station)
            interval = text(row, 2)
            if interval not in UNBOUND:
                set_name(row, 2, destination_course(interval))
            need(all(isfinite(row.contents[slot].value) for slot in (11, 17)), 'Nonfinite native interval or mass')
            distribution = text(row, 16)
            if distribution not in UNBOUND:
                if distribution_names is None:
                    distribution_names = named_distributions.catalog(plan.catalog).keys()
                need(distribution in distribution_names, f'Delay distribution {distribution!r} is not in the destination catalog')
            if args.import_actual_times:
                validate_actual_times(row)
            else:
                for slot in (13, 14):
                    set_name(row, slot, 'HH:MM:SS')
                row.contents[15].values[2:] = [0, 0]

            records = []
            for item in c.array(original.contents[9].value):
                record = cf.clone(connection(item))
                need(text(record, 0) == old_id and text(record, 2) == original_station,
                     f'Donor Connection owner does not match {row_key(original)}')
                need(isfinite(record.contents[8].value), 'Nonfinite Connection dispatching distance')
                set_name(record, 0, new_id)
                set_name(record, 1, destination_course(text(record, 1)))
                set_name(record, 2, station)
                other_station = text(record, 6)
                if other_station:
                    set_name(record, 6, destination_station(other_station))
                records.append(record)
            if records:
                set_sequence(row, 9, records)
            imported.append(row)
            pairs.append((row_key(row), row))

    need(external_courses == args.referenced_courses.keys(), 'Unused external Course binding')
    need(args.station_mapping.keys() <= set(seen_stations.values()), 'Unused donor Station mapping')
    before = Counter((text(row, 1), text(row, 5)) for row in replaced)
    after = Counter((text(row, 1), text(row, 5)) for row in imported)
    for (cid, station), count in before.items():
        if count > 1 and count != after[cid, station]:
            plan.require_unambiguous_visit(cid, station)
    dictionary_replace(plan.table, pairs)
    for cid, station in after:
        if after[cid, station] > 1 and before[cid, station] != after[cid, station]:
            plan.require_unambiguous_visit(cid, station)
    verify_references(plan, imported)
    plan.changed_course_visits.update(targets)
    return {'course_mapping': selected, 'imported_rows': len(imported), 'replaced_rows': len(replaced),
            'referenced_courses': args.referenced_courses, 'station_mapping': args.station_mapping,
            'actual_times_imported': args.import_actual_times}


def verify_references(plan, imported):
    visits = defaultdict(list)
    for row in plan.rows().values():
        visits[text(row, 1), text(row, 5)].append(row)
    inspected = set()
    for row in imported:
        cid, station = text(row, 1), text(row, 5)
        for item in c.array(row.contents[9].value):
            target = text(item, 1), text(item, 6) or station
            need(len(visits[target]) == 1, f'Missing or ambiguous Connection target for {row_key(row)}')
        key = cid, station
        reference = text(row, 2)
        chain = {key}
        while reference not in UNBOUND:
            key = reference, station
            need(key not in chain and len(visits[key]) == 1, f'Cyclic or ambiguous native interval for {row_key(row)}')
            if key in inspected:
                break
            chain.add(key)
            reference = text(visits[key][0], 2)
        inspected.update(chain)


class NativeTimetableImport(OperatingPlanEditTools):
    def import_timetable(self, args):
        state = self.load_operating_project(args)
        source = self.path(args.donor_timetable.path)
        raw = self.secure_bytes(source)
        if source.suffix.lower() != '.timetable' or sha(raw) != args.donor_timetable.sha256:
            raise APIError('NATIVE_TIMETABLE_SOURCE', 'Use a native .timetable archive matching its supplied SHA-256')
        if source in state['inputs'] and raw != state['inputs'][source]:
            raise APIError('SOURCE_CHANGED', 'Timetable donor changed after its target project snapshot')
        try:
            donor = writer.load_next_compatible(raw)[0]
            changed, report = operating_candidate(
                state, args.source_project.run_file, lambda plan: import_schedule(plan, donor, args),
            )
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_TIMETABLE_IMPORT_INVALID', str(exc)[:700]) from exc
        state['inputs'][source] = raw
        report['donor_timetable'] = args.donor_timetable.model_dump()
        return self.publish_operating_increment(args, state, changed, report)


def tool_definitions(root):
    service = NativeTimetableImport(root)
    return [('opentrack_import_native_timetable_archive',
             'Select complete Course schedules from a SHA-bound original OTTimetable v9 archive. Bind them to '
             'existing destination Courses, Stations, Itineraries and referenced schedules. Preview or save a fresh '
             'native catalog increment, preserving the rest of the destination timetable.',
             ImportNativeTimetable, service.import_timetable, False, False)]
