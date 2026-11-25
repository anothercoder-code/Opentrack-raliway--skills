"""Verify fixed-formation native Connection6 transfers around a station endpoint edit."""

from collections import defaultdict

from . import catalogs, course_factories, native_connections, writer
from .catalog_batch_reuse.course_batch import course_record
from .consist_workflow.core import summary
from .graph_references import incoming_counts
from .multi_document.core import ident, need, ref, sha
from .native_link_start import successor_start
from .native_station_rebind import grouped_rows
from .network_composition_plan import itinerary_routes
from .operating_plan_edit import UNBOUND, text, timetable_time


def _closure(table, seeds):
    by_course = defaultdict(list)
    for cid, rows in table.items():
        for row in rows:
            for ordinal, obj in enumerate(catalogs.array(row.contents[9].value)):
                data = native_connections.record(obj)
                entry = (cid, row, ordinal, obj, data)
                by_course[cid].append(entry)
                if data['target_course_id'] not in UNBOUND and data['target_course_id'] != cid:
                    by_course[data['target_course_id']].append(entry)
    todo, visited, entries = list(seeds), set(), {}
    while todo:
        cid = todo.pop()
        if cid in visited:
            continue
        visited.add(cid)
        for entry in by_course[cid]:
            owner, _, _, obj, data = entry
            entries[id(obj)] = entry
            for candidate in (owner, data['target_course_id']):
                if candidate not in UNBOUND and candidate not in visited:
                    todo.append(candidate)
    return entries.values()


def _pairs(table, entries, counts):
    pairs = defaultdict(dict)
    for owner, row, ordinal, obj, data in entries:
        target, action = data['target_course_id'], data['flags']
        need(data['course_id'] == owner and target not in UNBOUND and owner != target and counts[id(obj)] == 1,
             f'Connection6 at {owner} requires one saved owner and a distinct bound counterpart')
        need(action in (0, 2) and data['time_reference_type'] == 0 and data['dispatching_distance_km'] == 0.0
             and data['maximum_wait'] in (None, '', 'HH:MM:SS'),
             f'Connection6 at {owner} is outside the ordinary fixed-formation turnround contract')
        first, last = table[owner][0], table[owner][-1]
        need(first is not last and row is (last if action == 2 else first),
             f'Connection6 at {owner} has an intermediate or nonterminal split/join and requires formation review')
        sign = text(row, 5)
        target_sign = data['target_station_sign']
        need(bool(sign) and data['station_sign'] == sign and target_sign in (None, '', sign),
             f'Connection6 at {owner} does not bind the same saved native station')
        pair = (owner, target) if action == 2 else (target, owner)
        need(action not in pairs[pair], f'Duplicate saved Connection6 in turnround {pair}')
        pairs[pair][action] = (row, ordinal, data)
    need(all(set(pair) == {0, 2} for pair in pairs.values()), 'Every affected turnround needs one reciprocal Connection6 pair')
    need(len({first for first, _ in pairs}) == len({last for _, last in pairs}) == len(pairs),
         'Each linked Course may have only one immediate predecessor and one successor')
    return pairs


def _reviewed_pairs(reviews, pairs):
    need(type(reviews) is list and len(reviews) <= 1000, 'Expected a bounded explicit list of reviewed direct turnrounds')
    approvals = {}
    for row in reviews:
        need(type(row) is dict and set(row) == {'from_course', 'to_course', 'movement'}
             and all(type(row[role]) is str and row[role] not in UNBOUND for role in ('from_course', 'to_course'))
             and row['movement'] in ('continue', 'reverse'), 'Review both exact Courses and their turnround direction')
        key = row['from_course'], row['to_course']
        need(key not in approvals, f'Review each saved direct turnround once: {key}')
        approvals[key] = row['movement']
    need(approvals.keys() == pairs.keys(), 'Review every direct reciprocal turnround in the affected Course chain exactly once')
    return approvals


def _course_details(banks, table, participants):
    course_root = writer.load_next_compatible(banks['courses'])[0]
    train_root = writer.load_next_compatible(banks['trains'])[0]
    depot_root = writer.load_next_compatible(banks['depot'])[0]
    courses = {}
    for row in map(course_record, catalogs.course_items(course_root)):
        cid = row['course_id']
        if cid in participants:
            need(cid not in courses, f'Ambiguous native linked Course identity: {cid}')
            courses[cid] = row
    trains = {text(row, 0): row for row in catalogs.train_items(train_root)}
    depot = {text(row, 1): row for row in catalogs.engine_items(depot_root)}
    result = {}
    for cid in sorted(participants):
        course = courses.get(cid)
        rows = table.get(cid, ())
        need(course is not None and course['enabled'] and len(course['itineraries']) == 1
             and course['train'] in trains and course['spacing_mode_code'] == 0,
             f'Linked Course {cid} needs one enabled fixed-block Itinerary and a saved Train')
        need(len(rows) >= 2 and [row.contents[3].value for row in rows] == list(range(len(rows)))
             and all(row.contents[4].value == len(rows) - 1 and text(row, 2) in UNBOUND
                     and row.contents[11].value == 0 for row in rows),
             f'Linked Course {cid} needs consecutive direct planned timetable rows without interval inheritance')
        first, last = rows[0], rows[-1]
        depart, arrive = timetable_time(first, 'departure'), timetable_time(last, 'arrival')
        need(depart is not None and arrive is not None and depart < arrive
             and timetable_time(first, 'arrival') == depart and timetable_time(last, 'departure') == arrive,
             f'Linked Course {cid} requires explicit direct first departure and last arrival clocks')
        result[cid] = course['itineraries'][0], summary(trains[course['train']], depot), depart, arrive
    return result


def _pair_clock(text_value, action, key):
    need(type(text_value) is str, f'Turnround {key} requires explicit saved {action} minimum hold')
    return course_factories.clock(text_value)


def review_saved_turnrounds(banks, active_endpoint_courses, reviews, *, formation_rows=(), projected_transfers=None):
    """Read the complete connected fixed-formation transfer chain from immutable operating archives."""
    required = {'courses', 'timetable', 'trains', 'depot'}
    need(isinstance(banks, dict) and required <= banks.keys() and all(type(banks[key]) is bytes for key in required),
         'Turnround review needs exact frozen Course, Timetable, Train and Depot bytes')
    seeds = set(active_endpoint_courses)
    if not seeds:
        _reviewed_pairs(reviews, {})
        return []
    timetable_bytes = banks['timetable']
    root, _ = writer.load_next_compatible(timetable_bytes)
    table = grouped_rows(course_factories.timetable(root))
    entries = (entry for entry in _closure(table, seeds)
               if (entry[0], entry[1].contents[3].value, entry[2]) not in formation_rows)
    pairs = _pairs(table, entries, incoming_counts(root))
    approvals = _reviewed_pairs(reviews, pairs)
    if not pairs:
        return []
    contexts = _course_details(banks, table, {cid for pair in pairs for cid in pair})
    result = []
    transfers = {} if projected_transfers is None else projected_transfers
    for key, ends in pairs.items():
        former, successor = key
        from_itinerary, from_stock, _, arrival = contexts[former]
        to_itinerary, to_stock, departure, _ = contexts[successor]
        from_row, from_index, from_data = ends[2]
        to_row, to_index, to_data = ends[0]
        station = text(from_row, 5)
        need(text(to_row, 5) == station and bool(from_row.contents[10].value & 1)
             and not to_row.contents[10].value & 1,
             f'Turnround {key} requires a scheduled terminal stop and a same-station origin departure')
        transfer = transfers.get(key)
        if transfer is None:
            need(from_stock == to_stock, f'Turnround {key} requires the same exact ordered native Train formation')
        else:
            need(transfer['projected_length_m'] == to_stock['length_m'],
                 f'Turnround {key} must transfer the verified post-composition length')
        minimum_to = _pair_clock(to_data['minimum_wait'], 'successor', key)
        minimum_from = _pair_clock(from_data['minimum_wait'], 'predecessor', key)
        gap = departure - arrival
        need(gap > 0 and gap >= minimum_to, f'Turnround {key} violates the native successor minimum hold')
        link = {'from_course': former, 'to_course': successor, 'movement': approvals[key], 'station_sign': station,
                       'from_itinerary': from_itinerary, 'to_itinerary': to_itinerary,
                       'from_visit_index': from_row.contents[3].value, 'to_visit_index': to_row.contents[3].value,
                       'from_connection_index': from_index, 'to_connection_index': to_index,
                       'planned_arrival_s': arrival, 'planned_departure_s': departure, 'planned_gap_s': gap,
                       'minimum_hold_s': minimum_to, 'predecessor_recorded_hold_s': minimum_from,
                       'train': to_stock['train_name'], 'train_length_m': to_stock['length_m'],
                       'formation': to_stock['formation'], 'predecessor_connection': from_data, 'successor_connection': to_data,
                       'timetable_sha256': sha(timetable_bytes)}
        if transfer is not None:
            link['projected_formation_transfer'] = transfer
        result.append(link)
    return sorted(result, key=lambda row: (row['planned_arrival_s'], row['from_course'], row['to_course']))


def _physical_link(project, context, link):
    former, successor = link['from_course'], link['to_course']
    need({former, successor} <= context.keys(), 'Resolve both native Courses in the selected turnround chain')
    first, first_trace, first_visits = context[former]
    second, second_trace, second_visits = context[successor]
    need((ident(first)[0], ident(second)[0]) == (link['from_itinerary'], link['to_itinerary'])
         and len(first_visits) - 1 == link['from_visit_index'] and link['to_visit_index'] == 0,
         f'Native saved Itinerary or endpoint visit differs for {former} → {successor}')
    stop, origin = first_visits[-1], second_visits[0]
    need(stop['visit_index'] == link['from_visit_index'] and origin['visit_index'] == link['to_visit_index']
         and stop['station_sign'] == origin['station_sign'] == link['station_sign'],
         f'Native directed station occurrences differ for {former} → {successor}')
    need(stop['planned']['stop'] and not origin['planned']['stop']
         and stop['planned']['arrival_s'] == stop['planned']['departure_s'] == link['planned_arrival_s']
         and origin['planned']['arrival_s'] == origin['planned']['departure_s'] == link['planned_departure_s'],
         f'Native booked arrival or departure differs for {former} → {successor}')
    length = link['train_length_m']
    need(all(visit['arrival_consist_length_m'] == visit['departure_consist_length_m'] == length for visit in (stop, origin)),
         f'Native endpoint formation differs for {former} → {successor}')
    point = stop['stopping_point']
    need(point is not None and point['available_length_m'] >= length,
         f'Native terminal berth cannot accommodate the linked Train for {former} → {successor}')
    bound = successor_start(project, first, second, first_trace, second_trace, stop, origin, link['movement'], (former, successor))
    first_route = next(iter(itinerary_routes(project, second)))
    document, end_id = project.owners[id(first_route)]
    need((document, end_id) == bound['birth_end_key'], 'The selected successor does not begin at its first native Route owner')
    return {**bound, 'first_route': {'document': document, **ref(first_route)}, 'terminal_head_edge': point['stop_edge_key'],
            'terminal_head_offset_from_edge_start_m': point['head_edge_offset_m'], 'terminal_available_length_m': point['available_length_m']}


def verify_turnround_geometry(links, before_project, after_project, before_context, after_context):
    """Confirm both frozen geometries admit the exact native direction and successor origin."""
    return [{**link, 'before': _physical_link(before_project, before_context, link),
             'after': _physical_link(after_project, after_context, link)} for link in links]
