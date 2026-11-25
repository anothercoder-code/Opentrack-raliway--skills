"""Atomic native rebind of booked Course occurrences to reviewed platform alternatives."""

from functools import cache
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..errors import APIError
from . import catalogs, course_factories, native_connections, writer
from .consist_workflow.core import summary
from .course_formation_rebind import ExistingFormationMove, prepare_join_permissions, verify_formation_moves
from .itinerary_edit_tools import EditableItineraryProject
from .multi_document.core import ident
from .multi_document_tools import Inventory
from .native_station_rebind import grouped_rows, rewrite_station_occurrences
from .network_composition_plan import _arrival_route
from .network_operating_plan import DirectedStationEnd, _planned_rows, route_trace
from .operating_plan_edit import need, text, timetable_time
from .operating_plan_edit_tools import Id, Index, OperatingPlanEditTools, operating_candidate
from .prepare_contract import auxiliary, preflight
from .project_candidate_publication import ProjectSave, project_target, publish_candidate, require_external_target
from .project_workflow.relocation import relocate_project
from .runfile_parameters import inspect_runfile
from .saved_geometry import project_from
from .tools import Input, sha
from .zero_operations.speed_preferences import index_for_course


Itineraries = Annotated[list[Id], Field(min_length=1, max_length=32)]


class ReviewedPlatformVisit(Input):
    index: Index
    station_sign: Id
    target_station_sign: Id | None = None
    from_reference: DirectedStationEnd
    to_reference: DirectedStationEnd
    track: Literal['preserve_constraint', 'pin', 'unrestricted'] = 'preserve_constraint'


class CoursePlatforms(Input):
    course_id: Id
    expected_itineraries: Itineraries
    itineraries: Itineraries
    visits: Annotated[list[ReviewedPlatformVisit], Field(max_length=1000)] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_occurrences(self):
        if (len(set(self.itineraries)) != len(self.itineraries)
                or len(set(self.expected_itineraries)) != len(self.expected_itineraries)
                or len({item.index for item in self.visits}) != len(self.visits)):
            raise ValueError('Use distinct Itinerary preferences and unique timetable row indices')
        return self


class RebindCoursePlatforms(ProjectSave):
    source_project: Inventory
    courses: Annotated[list[CoursePlatforms], Field(min_length=1, max_length=1000)]
    composition_events: Annotated[list[ExistingFormationMove], Field(max_length=64)] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_courses(self):
        if len({item.course_id for item in self.courses}) != len(self.courses):
            raise ValueError('Select each Course once')
        return self


def itinerary_choice(course):
    return tuple(catalogs.text(item) for item in catalogs.array(course.contents[2].value))


def stop_anchor(visit, stop, index):
    if stop and index > 0:
        point = visit.get('head_stop') or visit.get('default_stop')
        if point is not None:
            return point['end_key']
    return visit['end_key']


def visit_track(project, trace, index, stop):
    if index == 0:
        return text(project.model(trace['edges'][0]), 19)
    visit = trace['visits'][index]
    return visit.get('stopping_track_id', visit['incoming_track_id']) if stop else visit['incoming_track_id']


def _new_track(original, targets, mode, context):
    if mode == 'unrestricted':
        return ''
    if mode == 'preserve_constraint' and not original:
        return original
    need(len(set(targets)) == 1 and targets[0], f'{context} alternatives require one common saved track or an unrestricted row')
    return targets[0]


def _visit_key(project, trace, index, row):
    visit = trace['visits'][index]
    stop = bool(row.contents[10].value & 1)
    return visit['end_key'], stop_anchor(visit, stop, index), visit_track(project, trace, index, stop)


def _review_choices(project, request, rows, old_traces, new_traces, stock, stations, bounds, *,
                    composed=False, split_child=False):
    cid = request.course_id
    review = {item.index: item for item in request.visits}
    need(review.keys() <= set(range(len(rows))), f'Unknown timetable occurrence for {cid!r}')
    old, new = old_traces[0], new_traces[0]
    signs = [text(row, 5) for row in rows]
    station_updates = {i: item.target_station_sign for i, item in review.items() if item.target_station_sign is not None}
    candidate_signs = [station_updates.get(i, sign) for i, sign in enumerate(signs)]
    need(all([visit['station_sign'] for visit in trace['visits']] == signs for trace in old_traces),
         f'Original Itinerary options of {cid!r} must follow the saved station row order')
    need(all([visit['station_sign'] for visit in trace['visits']] == candidate_signs for trace in new_traces),
         f'Target Itinerary options of {cid!r} must follow the reviewed station row order')
    need(split_child or all(trace['visits'][0]['end_key'] == new['visits'][0]['end_key'] for trace in new_traces),
         'Alternative platforms must depart from the same directed origin')
    planned, edits = [], []
    for i, row in enumerate(rows):
        old_ref, old_stop, old_track = _visit_key(project, old, i, row)
        new_ref, new_stop, new_track = _visit_key(project, new, i, row)
        changed = (old_ref, old_stop, old_track, signs[i]) != (new_ref, new_stop, new_track, candidate_signs[i])
        if changed:
            need(i in review, f'Review the changed directed platform occurrence at {cid}#{i}')
        if i in review:
            item = review[i]
            need((item.station_sign, item.from_reference, item.to_reference) == (signs[i], old_ref, new_ref),
                 f'Reviewed platform reference differs for {cid}#{i}')
        before_track = text(row, 18)
        stop = bool(row.contents[10].value & 1)
        target_tracks = [visit_track(project, trace, i, stop) for trace in new_traces]
        mode = review[i].track if i in review else 'preserve_constraint'
        track = _new_track(before_track, target_tracks, mode, f'{cid}#{i}')
        arrival, departure = (timetable_time(row, field) for field in ('arrival', 'departure'))
        need(arrival is not None and departure is not None, f'Course {cid}#{i} needs complete planned times')
        planned.append({'station_sign': candidate_signs[i], 'arrival_s': arrival, 'departure_s': departure,
                        'stop': stop, 'track_id': (track or '') if i > 0 else ''})
        if changed or track != before_track:
            point = new['visits'][i].get('head_stop') or new['visits'][i].get('default_stop')
            edits.append({
                'index': i, 'station_sign': signs[i], 'target_station_sign': candidate_signs[i],
                'from_end': old_ref, 'to_end': new_ref,
                'from_stop_end': old_stop if stop else None, 'to_stop_end': new_stop if stop else None,
                'old_track_id': before_track, 'new_track_id': track, 'physical_track_id': new_track,
                'available_stop_length_m': point['available_length_m'] if point else new['visits'][i]['stopping_area_length_m'],
                'arrival_s': arrival, 'departure_s': departure,
            })
    need(request.itineraries != request.expected_itineraries or edits, f'Course {cid!r} has no platform rebind')
    for trace in new_traces:
        _planned_rows({'visits': planned}, trace, stock, stations, '', *bounds,
                      split_origin_stop=planned[0]['stop'], deferred_formation_length=composed)
    return edits


def _approaches(project, destinations, traces, index):
    result = set()
    for trace in traces:
        location = trace['visits'][index]
        if index == 0:
            result.add(trace['edges'][0])
        else:
            route = _arrival_route(project, destinations[trace['itinerary_name']], location['end_key'])
            result.add((project.owners[id(route)], ident(route)))
    return result


def _check_physical_links(project, rows, edits, trace_for, destinations, reviewed=()):
    """Preserve native physical continuations and reversals when moving both endpoints."""
    checked = []
    for owner, visits in rows.items():
        for index, row in enumerate(visits):
            for obj in catalogs.array(row.contents[9].value):
                link = native_connections.record(obj)
                target = link['target_course_id']
                if ((owner, index, target) in reviewed or not (link['flags'] & 3)
                        or not ({owner, target} & edits.keys())):
                    continue
                sign = link['target_station_sign'] or text(row, 5)
                matches = [i for i, other in enumerate(rows[target]) if text(other, 5) == sign]
                need(len(matches) == 1, f'Physical connection {owner} to {target} must resolve one counterpart visit')
                destination, = matches
                candidates = ((owner, index), (target, destination))
                old_a, old_b, new_a, new_b = [
                    [_visit_key(project, trace, idx, rows[name][idx])[1] for trace in trace_for(name, revised)]
                    for revised in (False, True) for name, idx in candidates
                ]
                unchanged = set(old_a) == set(new_a) and set(old_b) == set(new_b)
                terminal_link = link['flags'] == 2 and index == len(visits) - 1 and destination == 0
                if not terminal_link:
                    need(unchanged, 'A moved join or split needs explicit occupation and formation review')
                    for name, idx in candidates:
                        old, new = trace_for(name, False), trace_for(name, True)
                        if [t['itinerary_name'] for t in old] != [t['itinerary_name'] for t in new]:
                            need(_approaches(project, destinations, old, idx)
                                 == _approaches(project, destinations, new, idx),
                                 'A changed join/split approach requires its original occupation and formation review')
                    continue
                if unchanged:
                    continue
                reverse = old_a[0] != old_b[0]
                for prior, later in ((old_a, old_b), (new_a, new_b)):
                    need(all((project.related(a) if reverse else a) == b for a in prior for b in later),
                         f'Platform rebind would separate linked endpoints of {owner} and {target}')
                checked.append({'from_course': owner, 'to_course': target, 'reverse': reverse,
                                'arrival_ends': new_a, 'departure_ends': new_b})
    return checked


def _transaction(plan, state, original_project, project, requests, events):
    all_courses = plan.courses()
    original = {cid: itinerary_choice(course) for cid, course in all_courses.items()}
    revised = {**original, **{item.course_id: tuple(item.itineraries) for item in requests}}
    groups = grouped_rows(plan.rows())
    trains = {text(train, 0): train for train in catalogs.train_items(plan.roots[state['roles']['trains']])}
    depot = {text(engine, 1): engine for engine in catalogs.engine_items(plan.roots[state['roles']['depot']])}
    destinations = {ident(item)[0]: item for item in project.dests}
    original_destinations = {ident(item)[0]: item for item in original_project.dests}
    composed_mains = {event.main_course for event in events}
    split_children = {event.other_course for event in events if event.kind == 'split'}
    timing = inspect_runfile(auxiliary.core_bytes(auxiliary.records(state['run'])))['numeric']
    bounds = timing['start_seconds'], timing['stop_seconds'] + 1

    @cache
    def vehicle(cid):
        return summary(trains[text(all_courses[cid], 3)], depot)

    @cache
    def trace(cid, switched):
        options = (revised if switched else original)[cid]
        maximum = vehicle(cid)['maximum_speed_kmh']
        speed_index = str(index_for_course(state['run'], text(all_courses[cid], 4)))
        graph, choices = (project, destinations) if switched else (original_project, original_destinations)
        return [{'itinerary_name': name, **route_trace(graph, choices[name], speed_index, maximum)} for name in options]

    edits = {}
    for item in requests:
        cid = item.course_id
        need(cid in original and original[cid] == tuple(item.expected_itineraries),
             f'Saved preference order differs for {cid!r}')
        need(revised[cid] and set(revised[cid]) <= destinations.keys(), f'Missing saved Itinerary for {cid!r}')
        edits[cid] = _review_choices(project, item, groups[cid], trace(cid, False), trace(cid, True),
                                     vehicle(cid), plan.stations, bounds, composed=cid in composed_mains,
                                     split_child=cid in split_children)
    tracks = {(cid, item['index']): item['new_track_id'] for cid, visits in edits.items() for item in visits}
    signs = {(cid, item['index']): item['target_station_sign'] for cid, visits in edits.items() for item in visits
             if item['station_sign'] != item['target_station_sign']}
    original_groups = groups
    candidate_raw = None
    connection_edits = []
    if signs:
        source_timetable = state['files'][state['roles']['timetable']]
        original_groups = grouped_rows(course_factories.timetable(writer.load_next_compatible(source_timetable)[0]))
        connection_edits = rewrite_station_occurrences(plan, groups, signs)
        if events:
            candidate_raw = writer.dump_verified(plan.table)
    formations, approved = verify_formation_moves(original_project, project, events, state, original_groups, trace,
                                                   vehicle, tracks, edits.keys(), candidate_timetable=candidate_raw,
                                                   candidate_groups=groups if signs else None)
    links = _check_physical_links(project, original_groups, edits, trace, destinations, approved)
    for request in requests:
        cid = request.course_id
        if original[cid] != revised[cid]:
            plan.update_course({'course_id': cid, 'itineraries': request.itineraries})
        for item in edits[cid]:
            if item['old_track_id'] != item['new_track_id']:
                row = groups[cid][item['index']]
                plan.exclusive(plan.table, row)
                course_factories.settext(row, 18, item['new_track_id'])
    return {
        'courses': [{'course_id': cid, 'previous_itineraries': original[cid], 'revised_itineraries': revised[cid],
                     'reviewed_visit_changes': visits, 'train_length_m': vehicle(cid)['length_m'],
                     'itinerary_distances_m': [item['route_length_m'] for item in trace(cid, True)]}
                    for cid, visits in edits.items()],
        'verified_relocated_circulation_links': links, 'formation_events': formations,
        'updated_connection_stations': connection_edits, 'original_planned_times_preserved': True,
        'original_planned_times_and_connections_preserved': not connection_edits,
    }


class CoursePlatformTools(OperatingPlanEditTools):
    def rebind(self, args):
        target = project_target(self, args)
        state = self.load_operating_project(args)
        require_external_target(target, state['base'])
        run_name = args.source_project.run_file
        try:
            original = project_from(state['documents'], state['document_paths'], state['files'][state['roles']['dest']])
            staged, project, permissions = prepare_join_permissions(state, original, args.courses, args.composition_events)
            changed, report = operating_candidate(
                staged, run_name,
                lambda plan: _transaction(plan, staged, original, project, args.courses, args.composition_events),
            )
            need(changed and set(changed) <= {state['roles']['courses'], state['roles']['timetable']},
                 'Expected an atomic native Course or Timetable change')
            need(report['static_simulation_preflight']['passed'],
                 f'Native candidate preflight failed: {report["static_simulation_preflight"]["errors"]}')
            members = {name: changed.get(name, staged['files'][name]) for name in state['selected']}
            changed_members = sorted(name for name, data in members.items() if data != state['files'][name])
            if target is not None:
                members, _ = relocate_project(members, source_root=state['root'], target_root=target.as_posix(),
                                              run_file=run_name, expected_hashes={k: sha(v) for k, v in members.items()},
                                              project_type=EditableItineraryProject)
                prefix = target.as_posix() + '/'
                check = preflight.check(members[run_name], lambda path: members[path.removeprefix(prefix)])
                need(check['passed_static_subset'], f'Rebased native preflight failed: {check["errors"]}')
        except (ValueError, KeyError, IndexError, TypeError, OverflowError) as exc:
            raise APIError('COURSE_PLATFORM_REBIND', str(exc)[:700]) from exc
        result = {**report, 'preview_only': args.preview_only, 'saved': False,
                  'occupied_entry_transfers': permissions, 'changed_native_members': changed_members,
                  'member_sha256': {name: sha(raw) for name, raw in members.items()}}
        self.recheck(state)
        if args.preview_only:
            return result
        return publish_candidate(self, target, members, result, lambda: self.recheck(state))


def tool_definitions(root):
    service = CoursePlatformTools(root)
    return [('opentrack_rebind_native_course_platforms',
             'Rebind existing Courses to reviewed station tracks and Itinerary preferences. Verify the same native timetable '
             'occurrences, fit, planned times and physical continuations and publish a complete fresh native project.',
             RebindCoursePlatforms, service.rebind, False, False)]
