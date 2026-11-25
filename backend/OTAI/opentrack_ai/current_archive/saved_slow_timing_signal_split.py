"""Keep a finite native slow zone and terminal timing on their reviewed sections."""

from .catalog_batch_reuse.course_batch import course_record
from .multi_document.core import ident, need
from .network_composition_plan import itinerary_routes
from .runfile_parameters import inspect_runfile
from .saved_timing_signal_split import DEFAULT_ROUTE_TIMING


SWITCH_TIMING = b'Use Switch Time and Route Res. Time'


def _delayed_prefix_scope(project, route, sequence, course_items, run_bytes):
    need(project is not None and route is not None and sequence and course_items is not None
         and type(run_bytes) is bytes,
         'Review the bound native Project .run, CourseList and effective Route for delayed prefix reservation')
    run = inspect_runfile(run_bytes)
    need(run['editable'] and run['editable_options'][SWITCH_TIMING] == b'1',
         'Enable the original switch and route reservation timing explicitly in the bound Project .run')
    uses = {ident(dest)[0]: sum(item is route for item in itinerary_routes(project, dest)) for dest in project.dests}
    active = [course for course in map(course_record, course_items)
              if course['enabled'] and any(uses.get(label) for label in course['itineraries'])]
    need(len(active) == 1,
         'Review one enabled native Course on the positively timed slow-zone Route')
    course, = active
    choices = course['itineraries']
    need(len(choices) == 1 and uses[choices[0]] == 1 and course['spacing_mode_code'] == 0
         and course['additional_reservation_time_s'] == 0,
         'The positively timed prefix needs a fixed-block Course with one exact saved Itinerary and zero additional reservation delay')

    scope = {key for end in sequence for key in (end, project.related(end), project.actual_related(end))}
    need(all(project.model(key).contents[21].value == 0 for key in scope),
         'The reviewed native Route must have zero saved switch times on its direction Ends')
    return {'course_id': course['course_id'], 'itinerary': choices[0],
            'course_reservation_delay_s': 0, 'maximum_saved_switch_time_s': 0}


def plan_slow_zone_timing(slow_zone, timing, *, reserve_with_previous, allow_delayed_prefix_retry=False,
                          project=None, route=None, sequence=None, course_items=None, run_bytes=None):
    original = timing['original']
    need(reserve_with_previous,
         'Combined slow-zone and timing review requires synchronized downstream reservation')
    inactive = ('release_distance_m', 'reservation_distance_m', 'use_reservation_distance', 'use_release_distance')
    need(all(original[key] == DEFAULT_ROUTE_TIMING[key] for key in inactive),
         'Combined slow-zone and timing review supports only release delay and terminal approach fields, '
         'plus an explicitly reviewed prefix reservation delay')
    delay = original['reserve_time_s']
    need((allow_delayed_prefix_retry is True) == (delay > 0),
         'Combined slow-zone and timing review supports only release delay and terminal approach fields '
         'without an explicit review of delayed prefix retry')
    zone = slow_zone['original_zone_m_from_route_origin']
    cut = timing['cut_m_from_original_route_origin']
    approach = timing['terminal_approach_m_from_original_route_origin']
    need(slow_zone['position'] == 'upstream' and zone[1] <= cut,
         'Combined slow-zone and timing review requires the entire slow zone before or ending at the relay')
    need(approach is None or zone[1] < approach[0],
         'The native slow zone and terminal approach require a positive separating distance')
    review = {
        'slow_zone_m_from_original_route_origin': zone,
        'terminal_approach_m_from_original_route_origin': approach,
        'zone_to_approach_m': None if approach is None else approach[0] - zone[1],
        'cut_m_from_original_route_origin': cut,
        'release_time_s': original['release_time_s'],
    }
    if delay:
        need((timing['upstream']['reserve_time_s'], timing['downstream']['reserve_time_s']) == (delay, 0)
             and slow_zone['upstream']['aspect_code'] > 0 and slow_zone['downstream']['aspect_code'] == 0,
             'The saved delayed reservation and speed restriction must be on the prefix only')
        scope = _delayed_prefix_scope(project, route, sequence, course_items, run_bytes)
        # 0050de4c can trim the request before 006614d4 retries with the retained cap.
        review['linked_downstream_reservation_requested'] = True
        review['delayed_prefix_reservation'] = {
            **scope, 'upstream_delay_s': delay, 'downstream_delay_s': 0,
            'initial_attempt_may_be_limited_to_prefix': True,
            'same_clock_reservation_guaranteed': False,
            'subsequent_relay_lock_runtime_unverified': True,
        }
    else:
        review['synchronized_downstream_reservation'] = True
    return review
