"""Write an original occupied-entry speed or timed stop on an exact Route."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator

from ..errors import APIError
from . import writer
from .itinerary_edit_tools import EditableItineraryProject
from .multi_document_tools import Inventory
from .network_composition_plan import _entry_signal, occupied_entry_route_parts
from .operation_tools import Name, RouteSelector
from .operating_plan_edit import need
from .operating_plan_edit_tools import OperatingPlanEditTools
from .prepare_contract import preflight
from .project_candidate_publication import ProjectSave, project_target, publish_candidate, require_external_target
from .project_workflow.relocation import relocate_project
from .route_edit_tools import Seconds, Speed
from .saved_geometry import project_from
from .tools import Input, sha
from .zero_generation.topology import flt


class OccupiedEntryFields(Input):
    flags: Annotated[StrictInt, Field(ge=0, le=15)]
    speed_kmh: Speed
    wait_s: Seconds


class RestrictSpeed(Input):
    mode: Literal['restricted_speed']
    speed_kmh: Speed

    @model_validator(mode='after')
    def above_stop_threshold(self):
        if self.speed_kmh < 1:
            raise ValueError('Use at least 1 km/h for speed-restricted entry, or select stop_and_wait')
        return self


class StopAndWait(Input):
    mode: Literal['stop_and_wait']
    wait_s: Annotated[StrictInt, Field(gt=0, le=86400)]


class ReviewedNativeJoinEntryMode(Input):
    document: Name
    route: RouteSelector
    expected_signal_id: Annotated[StrictInt, Field(ge=0)]
    expected_primary: OccupiedEntryFields
    expected_continuation: OccupiedEntryFields | None = None
    setting: Annotated[RestrictSpeed | StopAndWait, Field(discriminator='mode')]


class EditNativeJoinEntryMode(ProjectSave, ReviewedNativeJoinEntryMode):
    source_project: Inventory


def reviewed_entry_mode_changes(project, request):
    owner = request.document, request.route.start_id
    identity = request.route.name, request.route.array_id, request.route.start_id
    primary = project.owned(owner, 'OTRoute', identity)
    route_parts = occupied_entry_route_parts(project, primary)
    _, signal = _entry_signal(project, primary)
    need(signal.contents[0].value == request.expected_signal_id and signal.contents[9].values[2] & 1,
         'The reviewed entrance signal must already allow occupied entry')
    need((len(route_parts) > 1) == (request.expected_continuation is not None),
         'Review the receiving fragment when the selected Route crosses a document boundary')
    reviews = [request.expected_primary]
    if request.expected_continuation is not None:
        reviews.append(request.expected_continuation)

    changes = []
    setting = request.setting
    for (route_owner, route), reviewed in zip(route_parts, reviews, strict=True):
        group = route.contents[6]
        before = list(group.values)
        need(before == [reviewed.flags, reviewed.speed_kmh, reviewed.wait_s],
             f'Saved occupied-entry settings do not match the reviewed tuple at {route_owner}')
        existing = before[0] & ~7
        if isinstance(setting, StopAndWait):
            after = [existing | 7, 0.0, float(setting.wait_s)]
        else:
            after = [existing | 3, flt(setting.speed_kmh, 'Occupied-entry speed'), 0.0]
        changes.append((route_owner, group, before, after))
    return changes


def set_entry_mode(project, request):
    changes = reviewed_entry_mode_changes(project, request)
    need(any(before != after for _, _, before, after in changes), 'The reviewed settings already match the request')
    documents = {owner[0] for owner, _, _, _ in changes}
    fingerprints = {name: writer.fingerprint(project.roots[name]) for name in documents}
    try:
        for _, group, _, after in changes:
            group.values[:] = after
        output = {name: writer.dump_verified(project.roots[name], project.versions[name]) for name in sorted(documents)}
    finally:
        for _, group, before, _ in changes:
            group.values[:] = before
    need(all(writer.fingerprint(project.roots[name]) == prior for name, prior in fingerprints.items()),
         'Another saved field changed while editing the occupied-entry settings')
    return output, [(owner, after) for owner, _, _, after in changes]


class NativeJoinEntryModeTools(OperatingPlanEditTools):
    def edit(self, args):
        target = project_target(self, args)
        state = self.load_operating_project(args)
        require_external_target(target, state['base'])
        try:
            dest = state['files'][state['roles']['dest']]
            project = project_from(state['documents'], state['document_paths'], dest)
            changes, reviewed = set_entry_mode(project, args)
            candidates = {**state['documents'], **changes}
            checked = project_from(candidates, state['document_paths'], dest)
            identity = args.route.name, args.route.array_id, args.route.start_id
            for owner, values in reviewed:
                route = checked.owned(owner, 'OTRoute', identity)
                need(route.contents[6].values == values, 'Fresh native occupied-entry settings differ from the request')
            files = {name: state['files'][name] for name in state['selected']}
            files.update({state['document_members'][name]: raw for name, raw in changes.items()})
            run = args.source_project.run_file
            if target is not None:
                files, _ = relocate_project(files, source_root=state['root'], target_root=target.as_posix(),
                                            run_file=run, expected_hashes={name: sha(raw) for name, raw in files.items()},
                                            project_type=EditableItineraryProject)
            root = state['root'] if target is None else target.as_posix()
            prefix = root + '/'
            cold = preflight.check(files[run], lambda member: files[member.removeprefix(prefix)])
            need(cold['passed_static_subset'], f'Static simulation preflight failed: {cold["errors"]}')
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_JOIN_ENTRY_MODE', str(exc)[:600]) from exc
        result = {
            'preview_only': args.preview_only, 'saved': False, 'route': args.route.model_dump(),
            'entry_signal_id': args.expected_signal_id, 'mode': args.setting.mode,
            'route_fragments': [{'owner': owner, 'flags': values[0], 'speed_kmh': values[1], 'wait_s': values[2]}
                                for owner, values in reviewed],
            'member_sha256': {name: sha(raw) for name, raw in files.items()},
            'structural_readback_verified': True, 'static_simulation_preflight': True, 'native_execution': False,
        }
        self.recheck(state)
        if args.preview_only:
            return result
        return publish_candidate(self, target, files, result, lambda: self.recheck(state))


def tool_definitions(root):
    return [('opentrack_edit_native_join_entry_mode',
             'Save speed-restricted occupied entry or a zero-speed timed stop on an exact signalled Route. '
             'Updates the primary and receiving fragment together and preserves all course and timetable bytes.',
             EditNativeJoinEntryMode, NativeJoinEntryModeTools(root).edit, False, False)]
