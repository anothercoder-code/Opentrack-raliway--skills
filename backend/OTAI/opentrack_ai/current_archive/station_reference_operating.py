"""Check booked events after a native Itinerary's station endpoint is changed."""

from . import catalogs, writer
from .catalog_batch_reuse.course_batch import course_record
from .multi_document.core import ident, need
from .network_operating_plan import _planned_rows, route_trace
from .saved_platform_resize import OPERATING_FILES, _operating_data


def _course_geometry(project, itinerary, stock, speed, planned, stations, bounds, *,
                     formation_by_visit=None, split_origin=False, split_berth_indices=(), join_berth_indices=()):
    trace = route_trace(project, itinerary, speed, stock['maximum_speed_kmh'])
    visits = []
    _planned_rows({'visits': planned}, trace, stock, stations, '', *bounds, resolved_visits=visits,
                  formation_by_visit=formation_by_visit, split_origin_stop=split_origin,
                  verified_split_berth_indices=split_berth_indices,
                  verified_join_berth_indices=join_berth_indices)
    start, finish = visits[0], visits[-1]
    head = finish['stopping_point']
    if finish['planned']['stop']:
        need(head is not None, 'A booked terminal relocation needs a resolved native stopping point')
    return trace, visits, {
        'start': {'document': start['end_key'][0], 'end_id': start['end_key'][1]},
        'terminal': {'document': finish['end_key'][0], 'end_id': finish['end_key'][1]},
        'route_length_m': trace['route_length_m'],
        'terminal_head_m': finish['event_distance_m'],
        'terminal_head_edge': None if head is None else head['stop_edge_key'],
        'terminal_head_offset_from_edge_start_m': None if head is None else head['head_edge_offset_m'],
        'terminal_stopping_signal_id': None if head is None else head['signal_id'],
        'terminal_available_length_m': None if head is None else head['available_length_m'],
        'train_length_m': stock['length_m'],
    }


def _event_position(visit):
    point = visit['stopping_point']
    if point is None:
        return ('end', visit['end_key'])
    return ('edge', point['stop_edge_key'], point['head_edge_offset_m'])


def _endpoint_courses(banks, itineraries):
    courses, _ = writer.load_next_compatible(banks['courses'])
    return {course['course_id'] for course in map(course_record, catalogs.course_items(courses))
            if course['enabled'] and itineraries.intersection(course['itineraries'])}


def _operating_for_links(banks, run, itineraries, links, verified_interval_rows=(), *, formation=None,
                         allow_moving_block=False):
    link_courses = set() if formation is None else set(formation['course_ids'])
    connection_rows = set() if formation is None else set(formation['connection_rows'])
    for link in links:
        for side in ('from', 'to'):
            cid = link[f'{side}_course']
            link_courses.add(cid)
            connection_rows.add((cid, link[f'{side}_visit_index'], link[f'{side}_connection_index']))
    return _operating_data(banks, run, itineraries, linked_course_ids=link_courses, verified_connection_rows=connection_rows,
                           verified_interval_rows=verified_interval_rows, allow_moving_block=allow_moving_block)


def _resolved_courses(project, operating, stations, bounds, formation=None):
    destinations = {ident(dest)[0]: dest for dest in project.dests}
    context, reports = {}, {}
    verified_berths = {} if formation is None else formation['verified_berth_indices']
    for cid, (name, stock, speed, planned) in operating.items():
        itinerary = destinations[name]
        try:
            lengths = None if formation is None else formation['formation_by_visit'].get(cid)
            split_origin = formation is not None and cid in formation['split_origins']
            trace, visits, observed = _course_geometry(
                project, itinerary, stock, speed, planned, stations, bounds,
                formation_by_visit=lengths, split_origin=split_origin,
                split_berth_indices={index for course, index in verified_berths.get('split', ()) if course == cid},
                join_berth_indices={index for course, index in verified_berths.get('join', ()) if course == cid})
        except ValueError as error:
            raise ValueError(f'Course {cid}: {error}') from error
        context[cid] = (itinerary, trace, visits)
        reports[cid] = observed
    return context, reports


def frozen_endpoint_turnrounds(banks, run, project, reviews):
    from .station_reference_connections import review_saved_turnrounds, verify_turnround_geometry

    participants = {review[key] for review in reviews for key in ('from_course', 'to_course')}
    links = review_saved_turnrounds(banks, participants, reviews)
    operating, stations, bounds = _operating_for_links(banks, run, set(), links)
    context, reports = _resolved_courses(project, operating, stations, bounds)
    return links, reports, verify_turnround_geometry(links, project, project, context, context)


def review_endpoint_courses(state, before, after, moved, itineraries, reviews, link_reviews=None, formation_reviews=None):
    from .station_reference_connections import review_saved_turnrounds, verify_turnround_geometry
    from .station_reference_intervals import review_saved_intervals

    banks = {role: state['files'][state['roles'][role]] for role in OPERATING_FILES}
    required = _endpoint_courses(banks, itineraries)
    approvals = {row['course_id']: row for row in reviews}
    need(len(approvals) == len(reviews) and approvals.keys() == required,
         'Review each enabled Course using a rebound endpoint Itinerary exactly once')
    formation, transfers = None, None
    link_reviews = [] if link_reviews is None else link_reviews
    if formation_reviews:
        from .station_reference_formation import endpoint_formation_turnrounds, review_endpoint_formations

        formation = review_endpoint_formations(state, before, after, required, formation_reviews)
        transfers = endpoint_formation_turnrounds(state, formation, link_reviews)
    formation_rows = () if formation is None else formation['connection_rows']
    links = review_saved_turnrounds(banks, required, link_reviews, formation_rows=formation_rows,
                                    projected_transfers=transfers)
    if not required:
        return [], [], [], {}

    interval_receipts, interval_rows = review_saved_intervals(banks, required)
    operating, stations, bounds = _operating_for_links(banks, state['run'], itineraries, links, interval_rows, formation=formation,
                                                      allow_moving_block=True)
    before_context, before_reports = _resolved_courses(before, operating, stations, bounds, formation)
    after_context, after_reports = _resolved_courses(after, operating, stations, bounds, formation)
    berths = {} if formation is None else formation['berth_relocations']
    output = []
    for cid, (name, _, _, _) in operating.items():
        old_visits, new_visits = before_context[cid][2], after_context[cid][2]
        old, new = before_reports[cid], after_reports[cid]
        for index, (former, revised) in enumerate(zip(old_visits, new_visits, strict=True)):
            key = former['end_key']
            need(revised['end_key'] == moved.get(key, key), f'Unreviewed directed station occurrence for {cid}#{index}')
            reviewed_endpoint = cid in approvals and key in moved and index in (0, len(old_visits) - 1)
            if former['planned']['stop'] and not reviewed_endpoint and (cid, index) not in berths:
                need(_event_position(former) == _event_position(revised),
                     f'Rebinding an endpoint would move a different booked stop for {cid}#{index}')
        if cid not in approvals:
            need(old == new, f'Rebinding a connected Course changes another physical endpoint: {cid}')
            continue
        approval = approvals[cid]
        for prefix, observed in (('expected_', old), ('replacement_', new)):
            fields = ('start', 'terminal', 'route_length_m', 'terminal_head_m')
            need(all(approval[prefix + key] == observed[key] for key in fields),
                 f'Reviewed start, terminal, total length or terminal head differs for {cid}')
        result = {'course_id': cid, 'itinerary': name, 'before': old, 'after': new}
        if cid in interval_receipts:
            result['interval_timetable'] = interval_receipts[cid]
        output.append(result)
    return (output, verify_turnround_geometry(links, before, after, before_context, after_context),
            [] if formation is None else formation['receipts'], berths)
