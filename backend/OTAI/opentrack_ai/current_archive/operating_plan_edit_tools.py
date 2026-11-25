"""Typed tool for atomically publishing current Course/Timetable increments."""

from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from ..errors import APIError
from . import defined_delay, runfile_parameters, writer
from .bundle_tools import CourseFields, Num
from .movement_edits import _movement_project
from .multi_document_tools import Inventory, MultiDocumentTools
from .operating_plan_edit import OperatingPlan, need
from .prepare_contract import auxiliary, preflight
from .project_candidate_publication import ProjectSave
from .tools import Input, sha


Id = Annotated[StrictStr, Field(min_length=1, max_length=200, pattern=r'^[\x20-\x22\x24-\x7E]+$')]
Index = Annotated[StrictInt, Field(ge=0, le=100000)]
Day = Annotated[StrictInt, Field(ge=-366, le=366)]
Seconds = Annotated[Num, Field(ge=0, le=86400)]
Selection = Annotated[list[Id], Field(min_length=1, max_length=1000)]


class UpdateCourse(Input):
    action: Literal['update_course']
    course_id: Id
    train: Id | None = None
    itineraries: Selection | None = None
    fields: CourseFields = Field(default_factory=CourseFields)

    @model_validator(mode='after')
    def changed_fields(self):
        if self.train is None and self.itineraries is None and not self.fields.model_fields_set:
            raise ValueError('Select at least one Course field or binding')
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Omit unsupplied Course fields')
        return self


class CourseIdentity(Input):
    course_id: Id
    new_id: Id


class RenameCourses(Input):
    action: Literal['rename_courses']
    renames: Annotated[list[CourseIdentity], Field(min_length=1, max_length=1000)]


class DeleteCourses(Input):
    action: Literal['delete_courses']
    course_ids: Selection
    reference_policy: Literal['reject', 'detach'] = 'reject'


class ResetItineraries(Input):
    action: Literal['reset_course_itineraries']
    course_ids: Selection


class TimetableFields(Input):
    arrival: StrictStr | None = None
    departure: StrictStr | None = None
    arrival_day_offset: Day | None = None
    departure_day_offset: Day | None = None
    stop_at_station: StrictBool | None = None
    timing_station: StrictBool | None = None
    dwell_s: Seconds | None = None
    mean_delay_s: Seconds | None = None
    track_id: StrictStr | None = None
    distribution_name: StrictStr | None = None
    delta_mass_t: Annotated[Num, Field(ge=-1000000, le=1000000)] | None = None
    interval_reference_course_id: Id | None = None
    interval_offset_s: Annotated[Num, Field(ge=-31622400, le=31622400)] | None = None

    @model_validator(mode='after')
    def explicit_nulls(self):
        nullable = {'arrival', 'departure', 'interval_reference_course_id'}
        if any(getattr(self, key) is None for key in self.model_fields_set - nullable):
            raise ValueError('Omit untouched fields; only times and interval reference may be explicitly null')
        return self


class InsertFields(TimetableFields):
    arrival: StrictStr | None
    departure: StrictStr | None
    arrival_day_offset: Day
    departure_day_offset: Day
    stop_at_station: StrictBool
    timing_station: StrictBool
    dwell_s: Seconds


class UpdateTimetableRow(Input):
    action: Literal['update_timetable_row']
    course_id: Id
    index: Index
    station_sign: Id | None = None
    fields: TimetableFields = Field(default_factory=TimetableFields)
    propagate_interval: StrictBool = False

    @model_validator(mode='after')
    def changed_fields(self):
        if self.station_sign is None and not self.fields.model_fields_set:
            raise ValueError('Select at least one timetable field or station')
        if 'station_sign' in self.model_fields_set and self.station_sign is None:
            raise ValueError('An explicit station sign may not be null')
        return self


class InsertTimetableRow(Input):
    action: Literal['insert_timetable_row']
    course_id: Id
    index: Index
    template_course_id: Id
    template_index: Index
    station_sign: Id
    fields: InsertFields


class DeleteTimetableRow(Input):
    action: Literal['delete_timetable_row']
    course_id: Id
    index: Index


class GenerateIntervals(Input):
    action: Literal['generate_interval_courses']
    course_id: Id
    count: Annotated[StrictInt, Field(ge=1, le=500)]
    interval_s: Annotated[StrictInt, Field(ge=-604800, le=604800)]
    number_step: Annotated[StrictInt, Field(ge=1, le=1000000)] = 1
    number_position: Annotated[StrictInt, Field(ge=0, le=199)] = 0


class ConnectionFields(Input):
    target_course_id: Id | None = None
    target_station_sign: Id | None = None
    minimum_wait: StrictStr | None = None
    maximum_wait: StrictStr | None = None
    join: StrictBool | None = None
    split: StrictBool | None = None
    location: Literal['entry', 'dispo', 'exit'] | None = None
    time_reference: Literal['arrival_or_pass', 'departure'] | None = None
    dispatching_distance_km: Annotated[Num, Field(ge=0, le=100000)] | None = None

    @model_validator(mode='after')
    def changed_fields(self):
        nullable = {'minimum_wait', 'maximum_wait'}
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set - nullable):
            raise ValueError('Explicit connection changes are required; only wait times may be unset')
        return self


class UpdateConnection(Input):
    action: Literal['update_connection']
    course_id: Id
    index: Index
    connection_index: Index
    propagate_interval: StrictBool = False
    fields: ConnectionFields


Operation = Annotated[
    UpdateCourse | RenameCourses | DeleteCourses | ResetItineraries |
    UpdateTimetableRow | InsertTimetableRow | DeleteTimetableRow | UpdateConnection | GenerateIntervals,
    Field(discriminator='action'),
]


class DefinedDelayVisit(Input):
    course_id: Id
    index: Index
    station_sign: Id
    delay_s: Annotated[StrictInt, Field(ge=0, le=86400)]
    clear_distribution: StrictBool = False


class DefinedDelay(Input):
    global_mean_delay_s: Annotated[StrictInt, Field(ge=0, le=86400)] = 0
    visits: Annotated[list[DefinedDelayVisit], Field(max_length=1000)] = Field(default_factory=list)


class EditOperatingPlan(ProjectSave):
    source_project: Inventory
    operations: Annotated[list[Operation], Field(max_length=100)] = Field(default_factory=list)
    defined_delay: DefinedDelay | None = None

    @model_validator(mode='after')
    def has_changes(self):
        if not self.operations and self.defined_delay is None:
            raise ValueError('Select an operating action or configure Defined delays')
        return self


def _selected_paths(state, run_rows):
    output, = [value for key, value, _ in run_rows if key == 'OutputPath']
    need(output.startswith(state['root'] + '/'), 'Output path is outside the selected project')
    rel_output = output[len(state['root']) + 1:]
    # A prepared station candidate carries its own receipt at the project root; OpenTrack never reads it.
    extras = set(state['files']) - set(state['selected']) - {'station-candidate.json'}
    need(all(path.startswith(rel_output + '/') for path in extras),
         'Unbound project members outside the declared application output directory prevent a closed edit')


def _itineraries(state):
    project = _movement_project(state['documents'], state['document_paths'],
                                state['files'][state['roles']['dest']])
    result = {}
    for dest in project.dests:
        visits = []
        for key in project.dest_view(dest)[0]:
            end = project.model(key)
            station = end.contents[12].value
            if station is not None and end.contents[20].value == 2:
                visits.append(writer.string(station.contents[7].value))
        result[writer.string(dest.contents[1].value)] = tuple(visits)
    return result


def operating_candidate(state, run_name, transform, *, defined=None):
    """Return a hashed-source candidate without writing or launching OpenTrack."""
    run = state['run']
    rows = auxiliary.records(run)
    _selected_paths(state, rows)
    input_archives = {name: state['files'][name] for name in state['selected'] if name != run_name}
    decoded = {name: writer.load_next_compatible(blob) for name, blob in input_archives.items()}
    roots = {name: obj for name, (obj, _) in decoded.items()}
    before = {name: writer.fingerprint(obj) for name, obj in roots.items()}
    itineraries = _itineraries(state)
    types = [value for key, value, _ in rows if key == 'TrainType']
    plan = OperatingPlan(roots, state['roles'], itineraries, types)
    report = transform(plan)
    if defined is not None:
        report['defined_delay_visits'] = defined_delay.update_visits(plan, defined['visits'])
    plan.validate()
    changed = {
        name: writer.dump_verified(obj, decoded[name][1]) for name, obj in roots.items()
        if writer.fingerprint(obj) != before[name]
    }
    if plan.removed_incidents:
        cleaned = b''.join(raw for key, value, raw in rows
                           if key != 'Incident' or value not in plan.removed_incidents)
        if cleaned != run:
            changed[run_name] = cleaned
    if defined is not None:
        selected = runfile_parameters.edit_runfile(changed.get(run_name, run), {
            b'Delay Scenario': b'-1', b'Mean Delay': str(defined['global_mean_delay_s']).encode('ascii'),
        })
        if selected != run:
            changed[run_name] = selected
    files = {**state['files'], **changed}
    selected_run = files[run_name]
    selected_rows = auxiliary.records(selected_run)
    incident_names = [value for key, value, _ in selected_rows if key == 'Incident']
    auxiliary.incident_bindings(files[state['roles']['courses']], incident_names)
    fresh = {name: writer.load_next_compatible(files[name])[0] for name in roots}
    reread = OperatingPlan(fresh, state['roles'], itineraries, types)
    reread.changed_course_visits = set(plan.changed_course_visits)
    reread.validate()

    def read_bound(path):
        need(path.startswith(state['root'] + '/'), 'Run dependency is outside the source project binding')
        return files[path[len(state['root']) + 1:]]

    after_check = preflight.check(selected_run, read_bound)
    if defined is not None:
        need(after_check['passed_static_subset'], f'Defined delay project did not pass static preflight: {after_check["errors"]}')
        report['defined_delay'] = after_check['checks']['defined_delay']
    return changed, {
        **report,
        'structural_readback_verified': True,
        'static_simulation_preflight': {
            'passed': after_check['passed_static_subset'], 'errors': after_check['errors'],
        },
        'native_execution': False,
    }


def edit_operating_plan(state, run_name, operations, *, defined=None):
    def apply_operations(plan):
        receipts = []
        for op in operations:
            action = op['action']
            if action in ('delete_courses', 'reset_course_itineraries'):
                need(len(op['course_ids']) == len(set(op['course_ids'])), 'Course selection contains duplicates')
            if action == 'delete_courses':
                op.setdefault('reference_policy', 'reject')
            elif action == 'generate_interval_courses':
                op.setdefault('number_step', 1)
                op.setdefault('number_position', 0)
            receipts.append({'action': action, **getattr(plan, action)(op)})
        return {'operations': receipts}

    return operating_candidate(state, run_name, apply_operations, defined=defined)


class OperatingPlanEditTools(MultiDocumentTools):
    def load_operating_project(self, args):
        state = self.load_project(args.source_project, minimum_documents=1)
        if not args.preview_only:
            target = self.path(args.target_directory)
            if target.is_relative_to(state['base']) or state['base'].is_relative_to(target):
                raise APIError('OPERATING_PLAN_TARGET', 'Use a fresh target outside and separate from the source project')
        return state

    def edit(self, args):
        state = self.load_operating_project(args)
        run_name = args.source_project.run_file
        try:
            defined = args.defined_delay.model_dump() if args.defined_delay is not None else None
            changed, report = edit_operating_plan(state, run_name, [op.model_dump(exclude_unset=True) for op in args.operations],
                                                  defined=defined)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('OPERATING_PLAN_INVALID', str(exc)[:700]) from exc
        return self.publish_operating_increment(args, state, changed, report)

    def publish_operating_increment(self, args, state, changed, report):
        files = {}
        replacements = {}
        members = {}
        for path, blob in changed.items():
            name = PurePosixPath(path).name
            if name.casefold() in {member.casefold() for member in members}:
                raise APIError('OPERATING_PLAN_TARGET', 'Changed members have colliding archive basenames')
            members[name] = blob
            replacements[name] = (state['base'] / path).relative_to(self.root).as_posix()
            files[name] = {'sha256': sha(blob), 'bytes': len(blob), 'before_sha256': sha(state['files'][path]), 'changed': True}
        manifest = {'format': 'opentrack-operating-plan-increment-v1', 'replacement_for': replacements,
                    'files': files, 'complete_relocated_project': False}
        result = {**report, 'preview_only': args.preview_only, 'saved': False, 'manifest': manifest,
                  'bundle_type': 'selected-run operating archive increment', 'no_changes': not members}
        if not members:
            self.recheck(state)
            return result
        run_name = args.source_project.run_file
        validators = {PurePosixPath(run_name).name: auxiliary.records} if run_name in changed else {}
        return self.publish_bundle(inputs=state['inputs'], members=members, manifest=manifest, result=result,
                                   target_directory=args.target_directory, scope_check=state['scope_check'],
                                   member_validators=validators, windows_publication=True)


def tool_definitions(root):
    service = OperatingPlanEditTools(root)
    return [('opentrack_edit_current_operating_plan',
             'Edit existing Course11 controls, identities and Itinerary priorities, Timetable9 row fields and order, '
             'and Connection6 references and waits. Write original Defined delays as paired run/timetable edits. '
             'Review a whole SHA-bound run or save an atomic native increment. '
             'Supports one or multiple current documents. Reports static readback and preflight separately from original simulation.',
             EditOperatingPlan, service.edit, False, False)]

