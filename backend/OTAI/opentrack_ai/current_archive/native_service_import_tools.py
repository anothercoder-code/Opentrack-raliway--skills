"""Atomic import of a closed group of existing native Courses and their schedules."""

from copy import deepcopy
from typing import Annotated

from pydantic import Field, StrictBool

from ..errors import APIError
from . import catalogs, course_factories, named_distributions, writer
from .movement_edits import _movement_project
from .multi_document_tools import Inventory
from .native_connections import connection
from .native_rolling_stock_import_tools import categories
from .native_timetable_import_tools import CourseMapping, TimetableCopySettings, import_schedule, set_name
from .operating_plan_edit import UNBOUND, dictionary_replace, need, set_sequence, text
from .operating_plan_edit_tools import Id, OperatingPlanEditTools, operating_candidate
from .project_candidate_publication import ProjectSave
from .tools import sha
from .zero_operations.speed_preferences import read_train_types


class ImportNativeServices(ProjectSave):
    source_project: Inventory
    donor_project: Inventory
    courses: Annotated[list[CourseMapping], Field(min_length=1, max_length=1000)]
    train_mapping: Annotated[dict[Id, Id], Field(max_length=1000)] = Field(default_factory=dict)
    itinerary_mapping: Annotated[dict[Id, Id], Field(max_length=1000)] = Field(default_factory=dict)
    import_actual_times: StrictBool = False


def read_catalogs(state):
    roles = ('courses', 'timetable', 'trains', 'depot', 'stations')
    return {role: writer.load_next_compatible(state['files'][state['roles'][role]])[0] for role in roles}


def closed_references(table, selected):
    counts = {'connections': 0, 'interval_rows': 0}
    for row in table.values():
        owner = text(row, 1)
        interval = text(row, 2)
        targets = [] if interval in UNBOUND else [('interval_rows', interval)]
        targets.extend(('connections', text(connection(item), 1))
                       for item in catalogs.array(row.contents[9].value))
        for kind, target in targets:
            inside = owner in selected
            need(inside == (target in selected),
                 f'Native service selection must include both ends of {kind}: {owner!r} -> {target!r}')
            if inside:
                counts[kind] += 1
    return counts


def stock_bindings(source, target, trains):
    def objects(banks):
        return ({text(row, 0): row for row in catalogs.train_items(banks['trains'])},
                {text(row, 1): row for row in catalogs.engine_items(banks['depot'])},
                categories(banks['trains']))

    old_trains, old_engines, old_categories = objects(source)
    new_trains, new_engines, new_categories = objects(target)
    for old_name, new_name in trains.items():
        need(old_name in old_trains and new_name in new_trains,
             f'Train binding is missing: {old_name!r} -> {new_name!r}')
        original = old_trains[old_name]
        projected = original
        if old_name != new_name:
            projected = deepcopy(original)
            set_name(projected, 0, new_name)
        need(writer.fingerprint(projected) == writer.fingerprint(new_trains[new_name]),
             f'Target Train must have the exact donor formation, order and model: {new_name!r}')
        category = text(original, 3)
        need(category in old_categories and category in new_categories
             and writer.fingerprint(old_categories[category]) == writer.fingerprint(new_categories[category]),
             f'Target train Category differs or is missing: {category!r}')
        for engine in dict.fromkeys(catalogs.bound_engine_names(original)):
            need(engine in old_engines and engine in new_engines
                 and writer.fingerprint(old_engines[engine]) == writer.fingerprint(new_engines[engine]),
                 f'Target Engine definition differs or is missing: {engine!r}')


def movement_bindings(donor, target, itineraries):
    def context(state):
        project = _movement_project(state['documents'], state['document_paths'],
                                    state['files'][state['roles']['dest']])
        return project, {text(item, 1): item for item in project.dests}

    source_model, source_items = context(donor)
    target_model, target_items = context(target)
    used_documents = set()
    for old, new in itineraries.items():
        need(old in source_items and new in target_items, f'Missing bound Itinerary: {old!r} -> {new!r}')
        original, copied = source_items[old], target_items[new]
        left, right = source_model.dest_view(original), target_model.dest_view(copied)
        need(left == right, f'Target Itinerary differs in ordered directed Ends or saved Paths: {new!r}')
        need(original.contents[2].values == copied.contents[2].values
             and writer.fingerprint(original.contents[5].value) == writer.fingerprint(copied.contents[5].value),
             f'Target Itinerary settings or safety margins differ: {new!r}')
        used_documents.update(key[0] for key in left[0])
    for name in sorted(used_documents):
        need(donor['documents'][name] == target['documents'][name],
             f'Traversed worksheet differs: {name!r}; selected traffic requires the same saved infrastructure')
    return {name: sha(target['documents'][name]) for name in sorted(used_documents)}


def verify_preserved_members(changed, state, added):
    course_name, table_name = (state['roles'][role] for role in ('courses', 'timetable'))
    need(set(changed) == {course_name, table_name}, 'Expected one native Course and Timetable increment')
    for name in (course_name, table_name):
        original, _ = writer.load_next_compatible(state['files'][name])
        after, _ = writer.load_next_compatible(changed[name])
        if name == course_name:
            rows = [row for row in catalogs.course_items(after) if text(row, 0) not in added]
            writer.set_elements(catalogs.course_array(after), rows)
        else:
            dictionary_replace(after, [(key, row) for key, row in course_factories.timetable(after).items()
                                       if text(row, 1) not in added])
        need(writer.fingerprint(after) == writer.fingerprint(original),
             f'Unselected catalog content or aliasing changed: {name}')


def import_services(plan, donor_banks, donor_state, target_state, args):
    selected = {item.source_course: item.target_course for item in args.courses}
    current = plan.courses()
    source_courses = {text(row, 0): row for row in catalogs.course_items(donor_banks['courses'])}
    names = {name.casefold() for name in selected.values()}
    need(len(selected) == len(args.courses) == len(names) and selected.keys() <= source_courses.keys()
         and selected.keys().isdisjoint(UNBOUND) and set(selected.values()).isdisjoint(UNBOUND)
         and names.isdisjoint(name.casefold() for name in current),
         'Select distinct existing donor Courses and fresh destination Course IDs')
    plan.validate()
    table = course_factories.timetable(donor_banks['timetable'])
    references = closed_references(table, selected)
    stock, itineraries, speed_types = {}, {}, set()
    copied = []
    for old, new in selected.items():
        course = source_courses[old]
        train = text(course, 3)
        stock[train] = args.train_mapping.get(train, train)
        choices = [catalogs.text(item) for item in catalogs.array(course.contents[2].value)]
        need(choices and len(choices) == len(set(choices)), f'Course {old!r} needs distinct saved Itineraries')
        itineraries.update((name, args.itinerary_mapping.get(name, name)) for name in choices)
        new_choices = [itineraries[name] for name in choices]
        need(len(set(new_choices)) == len(choices), f'Itinerary bindings collapse Course {old!r} preferences')
        speed = text(course, 4)
        need(speed is not None, f'Missing native Course speed type for {old!r}')
        speed_types.add(speed.casefold())
        result = course_factories.clone(course)
        set_name(result, 0, new)
        set_name(result, 3, stock[train])
        if new_choices != choices:
            set_sequence(result, 2, [course_factories.string(course, name) for name in new_choices])
        copied.append(result)
    need(args.train_mapping.keys() <= stock.keys() and args.itinerary_mapping.keys() <= itineraries.keys(),
         'Unused donor Train or Itinerary mapping')
    old_types = [name.casefold() for name in read_train_types(donor_state['run'])]
    new_types = [name.casefold() for name in read_train_types(target_state['run'])]
    need(all(name in old_types and name in new_types and old_types.index(name) == new_types.index(name)
             for name in speed_types), 'Used native TrainType indexes must match in the two runs')
    stock_bindings(donor_banks, {role: plan.roots[plan.roles[role]] for role in ('trains', 'depot')}, stock)
    worksheets = movement_bindings(donor_state, target_state, itineraries)
    incoming = [row for row in table.values() if text(row, 1) in selected]
    station_names = {text(row, 5) for row in incoming}
    old_stations = catalogs.station_items(donor_banks['stations'])
    for name in sorted(station_names):
        need(name in old_stations and name in plan.stations
             and writer.fingerprint(old_stations[name]) == writer.fingerprint(plan.stations[name]),
             f'Target Station definition differs or is missing: {name!r}')
    distribution_names = {text(row, 16) for row in incoming} - set(UNBOUND)
    if distribution_names:
        source = named_distributions.catalog(donor_banks['courses'])
        destination = named_distributions.catalog(plan.catalog)
        for name in sorted(distribution_names):
            need(name in source and name in destination
                 and writer.fingerprint(source[name]) == writer.fingerprint(destination[name]),
                 f'Target delay distribution differs or is missing: {name!r}')
    set_sequence(plan.catalog, 4, [*current.values(), *copied])
    schedules = import_schedule(plan, donor_banks['timetable'], TimetableCopySettings(
        courses=args.courses, import_actual_times=args.import_actual_times,
    ))
    return {**schedules, 'imported_courses': len(copied), 'native_references': references,
            'train_bindings': stock, 'itinerary_bindings': itineraries, 'matched_worksheet_sha256': worksheets,
            'matched_stations': sorted(station_names), 'matched_distributions': sorted(distribution_names)}


class NativeServiceImport(OperatingPlanEditTools):
    def import_services(self, args):
        target = self.load_operating_project(args)
        donor = self.load_project(args.donor_project, minimum_documents=1)
        if not args.preview_only:
            output = self.path(args.target_directory)
            if output.is_relative_to(donor['base']) or donor['base'].is_relative_to(output):
                raise APIError('NATIVE_SERVICE_TARGET', 'Use a fresh target outside the donor and target inputs')
        try:
            banks = read_catalogs(donor)
            changed, report = operating_candidate(
                target, args.source_project.run_file,
                lambda plan: import_services(plan, banks, donor, target, args),
            )
            verify_preserved_members(changed, target, set(report['course_mapping'].values()))
            need(report['static_simulation_preflight']['passed'],
                 f'Destination static native preflight failed: {report["static_simulation_preflight"]["errors"]}')
            need(all(path not in target['inputs'] or blob == target['inputs'][path]
                     for path, blob in donor['inputs'].items()), 'A shared project member changed between snapshots')
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_SERVICE_IMPORT_INVALID', str(exc)[:800]) from exc

        target_scope = target['scope_check']

        def check_inventories():
            target_scope()
            donor['scope_check']()

        target['scope_check'] = check_inventories
        target['inputs'].update(donor['inputs'])
        result = {**report, 'unselected_catalog_graphs_preserved': True,
                  'donor_catalog_sha256': {role: sha(donor['files'][donor['roles'][role]])
                                          for role in banks}}
        return self.publish_operating_increment(args, target, changed, result)


def tool_definitions(root):
    service = NativeServiceImport(root)
    return [('opentrack_import_native_service_archives',
             'Select and add a closed group of original Course11, Timetable9 and Connection6 records to an '
             'existing project. Check exact target infrastructure and Train dependencies, then preview or '
             'atomically save both native catalog increments. No simulation.',
             ImportNativeServices, service.import_services, False, False)]
