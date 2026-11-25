"""Verify a native platform choice and the primary platform's observed availability."""

from . import catalogs, native_evaluation_formats as fmt, writer
from .native_interlocking import (
    CLOCK_TOLERANCE, STEP_POSITION_TOLERANCE_M, FrozenRailwayRun, front_position, route_spans, step_span,
)
from .native_run_evaluation import basename
from .prepare_contract.auxiliary import records


def option(run, binding, course, stations, platform):
    name = binding['itinerary']
    project = run.project
    itinerary = run.itineraries[name]
    nodes, _ = project.dest_view(itinerary)
    matches = []
    start = 0
    for previous, key in zip(nodes, nodes[1:]):
        edge = project.edge_between(previous, key)
        end = project.model(key)
        station = end.contents[12].value
        start += project.model(edge).contents[9].values[1]
        if end.contents[20].value == 2 and writer.kind(station) == 'OTStationModel':
            sign = catalogs.text(station.contents[7].value)
            if sign in stations and writer.string(stations[sign].contents[2].value) == platform:
                matches.append((sign, key, edge, start))
    fmt.require(len(matches) == 1, 'Saved choice must visit the selected platform station exactly once')
    sign, reference, stopping_edge, reference_distance = matches[0]
    bound, cycles = run.resource(binding['resource'], allow_empty=True)
    key = bound['document'], bound['safety_element_id']
    fmt.require(stopping_edge[0] == key[0] and stopping_edge[1] in bound['edge_ids'],
                'The declared monitor does not contain the Itinerary platform stopping Edge')
    available = [cycle for cycle in cycles if cycle['course_id'] == course]
    fmt.require(len(available) <= 1, 'Repeated original occupation is ambiguous at this platform')
    spans, total = route_spans(project, itinerary)
    group_spans = spans[key]
    fmt.require(len(group_spans) == 1 and group_spans[0]['to_m'] >= reference_distance,
                'Use a single contiguous monitor containing the complete platform Edge')
    return {'itinerary': name, 'origin_end': nodes[0], 'platform_station_sign': sign,
            'platform_end': reference, 'platform_edge': stopping_edge, 'terminal_end': nodes[-1],
            'platform_track_id': writer.string(project.model(stopping_edge).contents[19].value),
            'resource': bound, 'span': group_spans[0], 'route_length_m': total,
            'cycle': available[0] if available else None, 'elements': spans}


def occupied_cycle(item):
    cycle = item['cycle']
    if cycle is None:
        return False
    reserve, release = cycle['reservation_s']
    enter, clear = cycle['occupation_s']
    return (None not in (reserve, release, enter, clear) and reserve <= enter < clear <= release)


def validate_choice_resources(choices):
    resources = [(row['resource']['document'], row['resource']['safety_element_id']) for row in choices]
    fmt.require(len({item['origin_end'] for item in choices}) == 1 and len(set(resources)) == len(choices),
                'Options must begin at one directed origin and use distinct platform resources')
    fmt.require(len({item['platform_station_sign'] for item in choices}) == 1,
                'Every option must reach the same exact station sign')
    fmt.require(all(resource not in choice['elements'] for index, choice in enumerate(choices)
                    for other, resource in enumerate(resources) if other != index),
                'Each platform monitor must identify only one of the selected saved Itineraries')


def verify_platform_motion(run, course, selection, tolerance):
    distance = fmt.series(run.original_text(f'OT_{course}.st1'), 'st1', course)
    reservation = fmt.series(run.original_text(f'OT_{course}.step1'), 'step1', course)

    def metres(series):
        factor = {'km': 1000, 'mi': 1609.344}[series['units'][1]]
        return [(clock, value * factor) for clock, value in series['points']]

    path = metres(distance)
    fmt.require(path, 'Original platform distance trace is empty')
    offset = path[0][1]
    fmt.require(all(a[1] <= b[1] for a, b in zip(path, path[1:])), 'Original course position reverses on the selected path')
    start = selection['span']['from_m'] + offset
    end = selection['span']['to_m'] + offset
    enter = selection['cycle']['occupation_s'][0]
    reserve = selection['cycle']['reservation_s'][0]
    front_now = front_position(path, enter)
    fmt.require(abs(front_now - start) <= tolerance
                and abs(path[-1][1] - offset - selection['route_length_m']) <= tolerance,
                'Original distance trace does not reach the selected platform and Itinerary end')
    return {'position_at_occupation_start_m': round(front_now, 5), 'final_position_m': round(path[-1][1], 5),
            'reservation_stair': step_span(metres(reservation), reserve, start, end, STEP_POSITION_TOLERANCE_M)}


def blocker_relation(mode, primary, selected, blocker, originating):
    occupation = blocker['occupation_s']
    reservations = blocker['reservation_s']
    request = selected['cycle']['reservation_s'][0]
    fmt.require(None not in (*occupation, *reservations) and occupation[0] < occupation[1],
                'Original primary platform blocker lacks a complete physical occupation')
    if mode == 'occupied_at_alternative_reservation':
        verified = (selected['itinerary'] != primary['itinerary'] and
                    occupation[0] - CLOCK_TOLERANCE <= request <= occupation[1] + CLOCK_TOLERANCE)
    elif mode == 'released_before_primary_reservation':
        verified = (selected['itinerary'] == primary['itinerary'] and
                    occupation[0] <= originating < occupation[1] and reservations[1] <= request + CLOCK_TOLERANCE)
    else:
        fmt.require(mode == 'unoccupied_at_primary_reservation', 'Unknown primary platform availability check')
        verified = (selected['itinerary'] == primary['itinerary'] and
                    (request < reservations[0] - CLOCK_TOLERANCE or request > reservations[1] + CLOCK_TOLERANCE))
    return {'mode': mode, 'blocker_course': blocker['course_id'], 'primary_occupation_s': occupation,
            'primary_reservation_s': reservations, 'selected_reservation_s': request,
            'requested_course_origin_departure_s': originating, 'verified': verified}


def course_cycle(cycles, course):
    hits = [cycle for cycle in cycles if cycle['course_id'] == course]
    fmt.require(len(hits) == 1 and occupied_cycle({'cycle': hits[0]}),
                f'Expected exactly one complete native physical occupation cycle for {course}')
    return hits[0]


def availability_at_selection(mode, blocker, selected_clock):
    first, last = blocker['occupation_s']
    start, release = blocker['reservation_s']
    occupied = first + CLOCK_TOLERANCE <= selected_clock <= last - CLOCK_TOLERANCE
    unreserved = selected_clock < start - CLOCK_TOLERANCE or selected_clock > release + CLOCK_TOLERANCE
    verified = occupied if mode == 'occupied_at_selected_reservation' else unreserved
    return {**blocker, 'mode': mode, 'selected_platform_reservation_s': selected_clock, 'verified': verified}


def ordered_authorities(cycles, courses):
    witnesses = [course_cycle(cycles, course) for course in courses]
    gaps = [round(later['reservation_s'][0] - prior['reservation_s'][1], 5)
            for prior, later in zip(witnesses, witnesses[1:])]
    return {'authority_order': witnesses, 'release_to_next_reservation_s': gaps,
            'verified': all(gap >= -CLOCK_TOLERANCE for gap in gaps)}


def occupied_priority_coverage(ordered_choices, selected, verdicts):
    higher = ordered_choices[:ordered_choices.index(selected)]
    covered = {item['itinerary'] for item in verdicts
               if item['mode'] == 'occupied_at_selected_reservation' and item['verified']}
    return {'higher_priority_itineraries': higher, 'missing_occupied_itineraries': [name for name in higher if name not in covered],
            'verified': set(higher) <= covered}


def audit(output, evidence, requests, secure_bytes=None):
    outcome = requests['course']
    blocker = requests.get('primary_availability')
    checks = requests.get('availability_checks', [])
    throats = requests.get('throat_authority', [])
    course = basename(outcome['course_id'])
    outcomes = {course: outcome}
    other_courses = [check['course'] for check in checks] + ([blocker['course']] if blocker else [])
    for other in other_courses:
        cid = basename(other['course_id'])
        fmt.require(cid != course and outcomes.get(cid, other) == other,
                    'Use independent witness Courses with consistent original outcome conditions')
        outcomes[cid] = other
    run = FrozenRailwayRun(output, evidence, list(outcomes.values()), secure_bytes)
    run_member = evidence.get('run_file')
    if run_member is None:
        run_member, = [name for name in evidence['input_sha256'] if name.lower().endswith('.run')]
    run_blob = run.dependency(str(run.settings['project_root'] / run_member))
    options = {key: value for key, value, _ in records(run_blob)}
    fmt.require(options.get('Output Route Occ.') == '1',
                'Original occupation output must be explicitly enabled in the frozen run')
    station_blob = run.dependency(run.settings['paths']['StationFile'])
    stations = catalogs.station_items(writer.load_next_compatible(station_blob)[0])
    preferences = [item['itinerary'] for item in requests['choices']]
    fmt.require(preferences == run.preferences[course] and requests['expected_selected_itinerary'] in preferences,
                'Requested order and selection must match enabled frozen native Itineraries')
    station = requests.get('platform_station', outcome['terminal_station'])
    choices = [option(run, binding, course, stations, station) for binding in requests['choices']]
    validate_choice_resources(choices)
    movements = [item for item in choices if occupied_cycle(item)]
    fmt.require(len(movements) == 1, 'Expected original physical occupation of one listed platform')
    selected, = movements
    motion = verify_platform_motion(run, course, selected, requests['movement_boundary_tolerance_m'])
    selected_clock = selected['cycle']['reservation_s'][0]
    verdict = None
    if blocker:
        primary = choices[0]
        _, cycles = run.resource(requests['choices'][0]['resource'])
        witnesses = [row for row in cycles if row['course_id'] == blocker['course']['course_id']]
        fmt.require(len(witnesses) == 1, 'Expected one physical blocker cycle in the primary platform monitor')
        original = next(row for row in run.receipt['courses'] if row['course_id'] == course)
        verdict = blocker_relation(blocker['mode'], primary, selected, witnesses[0], original['origin_event']['time_s'])

    platform_ids = [item['itinerary'] for item in checks]
    fmt.require(len(platform_ids) == len(set(platform_ids)) and set(platform_ids) <= set(preferences),
                'Availability checks must each select one saved candidate platform')
    choices_by_name = {item['itinerary']: item for item in choices}
    geometries = {item['itinerary']: item['elements'] for item in choices}

    def witnessed_span(cid, key):
        candidates = []
        for name in run.preferences[cid]:
            if name not in geometries:
                geometries[name], _ = route_spans(run.project, run.itineraries[name])
            if len(geometries[name].get(key, [])) == 1:
                candidates.append(name)
        fmt.require(candidates, f'Native resource is not a contiguous part of a saved route for {cid}')
        return candidates

    checked = []
    for check in checks:
        option_name, cid = check['itinerary'], check['course']['course_id']
        choice = choices_by_name[option_name]
        reference = choice['resource']
        key = reference['document'], reference['safety_element_id']
        witness_itineraries = witnessed_span(cid, key)
        _, cycles = run.resource({'document': reference['document'], 'group': reference['resource']})
        observed = availability_at_selection(check['mode'], course_cycle(cycles, cid), selected_clock)
        checked.append({**observed, 'itinerary': option_name, 'priority': preferences.index(option_name) + 1,
                        'witness_saved_itineraries': witness_itineraries})
    coverage = (occupied_priority_coverage(preferences, selected['itinerary'], checked)
                if requests.get('require_all_higher_priorities_occupied') else None)

    authority = []
    occupied_resources = set()
    for throat in throats:
        precedents, followers = throat['preceding_courses'], throat['following_courses']
        witness_ids = [*precedents, *followers]
        fmt.require(1 <= len(witness_ids) <= 32 and len(witness_ids) == len(set(witness_ids)) and course not in witness_ids
                    and set(witness_ids) <= outcomes.keys(), 'Common throat needs distinct bound witness Courses')
        reference, cycles = run.resource(throat['resource'])
        key = reference['document'], reference['safety_element_id']
        fmt.require(key not in occupied_resources and all(len(item['elements'].get(key, [])) == 1 for item in choices),
                    'One distinct common throat resource must lie on every candidate Itinerary')
        occupied_resources.add(key)
        witnesses = {cid: witnessed_span(cid, key) for cid in witness_ids}
        observed = ordered_authorities(cycles, [*precedents, course, *followers])
        authority.append({**reference, **observed, 'witness_saved_itineraries': witnesses})

    verified = (selected['itinerary'] == requests['expected_selected_itinerary'] and (not verdict or verdict['verified'])
                and all(row['verified'] for row in [*checked, *authority]) and (coverage is None or coverage['verified']))
    return {'verified': verified,
            'course_id': course, 'platform_station': station, 'saved_itinerary_order': preferences,
            'selected_itinerary': selected['itinerary'],
            'selected_priority': preferences.index(selected['itinerary']) + 1,
            'options': [{key: value for key, value in item.items() if key != 'elements'} for item in choices],
            'original_terminal_motion': motion, 'primary_availability': verdict, 'availability_checks': checked,
            'occupied_priority_coverage': coverage, 'throat_authority': authority, 'provenance': run.provenance,
            'original_output_sha256': {**run.receipt['output_sha256'], **run.files.hashes}}
