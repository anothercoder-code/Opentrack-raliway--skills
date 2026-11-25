"""Corroborate original interlocking event sequences with frozen movement topology."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from pathlib import Path
import re

from . import catalogs, native_evaluation_formats as fmt, native_exclusion, native_occupation_groups as groups, writer
from .catalog_batch_reuse.course_batch import course_record
from .itinerary_edit_tools import EditableItineraryProject
from .native_run_evaluation import OutputFiles, basename, bound_run, digest, evaluate_run, read_member


CLOCK_TOLERANCE = native_exclusion.CLOCK_TOLERANCE_S
STEP_POSITION_TOLERANCE_M = 0.2


def decode_cycles(text, name, *, allow_empty=False):
    fmt.headers(text, 'OT_occ')
    fmt.require(re.findall(r'^// x-Legend[ \t]*:[ \t]*\[([^\]]+)\][ \t]*\r?$', text, re.M) == ['s'],
                'Expected seconds in original occupation output')
    results = []
    pending = {}
    sequence = ('SR', 'SO', 'EO', 'ER')
    for row in fmt.data_rows(text):
        fmt.require(len(row) == 4 and row[1] == name and row[3], 'Wrong original occupation resource or Course')
        time, _, tag, course = row
        clock = fmt.number(time)
        fmt.require(clock >= 0 or clock == -1, 'Unexpected native occupation clock')
        if not pending:
            owner = course
        fmt.require(owner == course and tag == sequence[len(pending)], f'Invalid original occupation block on {name}')
        pending[tag] = clock if clock != -1 else None
        if tag == 'ER':
            known = [pending[key] for key in sequence if pending[key] is not None]
            fmt.require(known and all(a <= b for a, b in zip(known, known[1:])),
                        f'Invalid chronological occupation cycle on {name}')
            results.append({'course_id': course, 'reservation_s': [pending['SR'], pending['ER']],
                            'occupation_s': [pending['SO'], pending['EO']]})
            pending = {}
    fmt.require((results or allow_empty) and not pending, f'Missing or truncated occupation output on {name}')
    return results


def route_spans(project, itinerary):
    nodes, _ = project.dest_view(itinerary)
    spans = defaultdict(list)
    distance = 0
    for first, second in zip(nodes, nodes[1:]):
        edge_key = project.edge_between(first, second)
        edge = project.model(edge_key)
        element = project.key(edge.contents[7].value.contents[7].value)
        end = distance + edge.contents[9].values[1]
        existing = spans[element]
        if existing and existing[-1]['to_m'] == distance:
            existing[-1]['to_m'] = end
            existing[-1]['route_edge_ids'].append(edge_key[1])
        else:
            existing.append({'from_m': distance, 'to_m': end, 'route_edge_ids': [edge_key[1]]})
        distance = end
    return dict(spans), distance


def metres_trace(text, kind, course, itinerary):
    labels = re.findall(r'^// Itineraries:[ \t]*1:[ \t]*(.+?)[ \t]*\r?$', text, re.M)
    fmt.require(labels == [itinerary], f'Native {kind} Itinerary header differs from frozen Course {course}')
    source = fmt.series(text, kind, course)
    factor = 1000.0 if source['units'][1] == 'km' else 1609.344
    fmt.require(source['points'], f'Original {kind} trace is empty for {course}')
    return [(instant, value * factor) for instant, value in source['points']]


def event_samples(points, instant):
    left = bisect_left(points, (instant - CLOCK_TOLERANCE, float('-inf')))
    right = bisect_right(points, (instant + CLOCK_TOLERANCE, float('inf')))
    return points[left:right]


def step_span(points, instant, start, end, tolerance):
    samples = event_samples(points, instant)
    for (stamp, lower), (later, upper) in zip(samples, samples[1:]):
        if stamp == later and lower < upper and lower <= start + tolerance and upper >= end - tolerance:
            return {'time_s': stamp, 'from_m': lower, 'to_m': upper}
    raise ValueError(f'Native stair transition at {instant:.2f} does not cover {start} to {end} m')


def front_position(points, instant):
    samples = event_samples(points, instant)
    fmt.require(samples, 'Occupation clock lacks an independent .st1 distance sample')
    nearest = min(samples, key=lambda row: abs(row[0] - instant))
    fmt.require(all(distance == nearest[1] for stamp, distance in samples if stamp == nearest[0]),
                'Conflicting .st1 distances at an occupation clock')
    return nearest[1]


def corroborate(cycle, span, traces, tolerance):
    reserve, release = cycle['reservation_s']
    enter, clear = cycle['occupation_s']
    fmt.require(None not in (reserve, release, enter, clear) and reserve <= enter < clear <= release,
                'Selected Course lacks complete positive-duration original occupation')
    start, end = span['from_m'], span['to_m']
    reservation = step_span(traces['step1'], reserve, start, end, STEP_POSITION_TOLERANCE_M)
    release_step = step_span(traces['step2'], release, start, end, STEP_POSITION_TOLERANCE_M)
    front_in = front_position(traces['st1'], enter)
    front_out = front_position(traces['st1'], clear)
    fmt.require(abs(front_in - start) <= tolerance and front_out >= end - tolerance and front_out > front_in,
                'Actual .st1 front trajectory fails the monitored resource position check')
    return {**cycle, **span, 'reservation_stair': reservation, 'release_stair': release_step,
            'occupation_front_m': [round(front_in, 5), round(front_out, 5)]}


class FrozenRailwayRun:
    def __init__(self, output, evidence, course_outcomes, secure_bytes, *, expected_completion=True):
        self.receipt = evaluate_run(output, {'courses': course_outcomes}, evidence, secure_bytes=secure_bytes)
        if expected_completion:
            fmt.require(self.receipt['native_run_verified'], 'Independent original Course evaluation failed for this run')
        else:
            provenance = self.receipt['provenance']
            fmt.require(provenance and provenance['process_exit_code'] == 0 and provenance['protocol_matches_frozen_run']
                        and not self.receipt['errors'] and self.receipt['verified_course_count'] == 0,
                        'Negative control must be a completed original process with incomplete declared movements')
        started, names, hashes, provenance, frozen = bound_run(evidence, output, secure_bytes)
        fmt.require(frozen and provenance['archive_hashes_verified'] and provenance['executable_matches'],
                    'Native interlocking checks need the original launch and frozen topology evidence')
        fmt.require(all(hashes.get(name) == data for name, data in self.receipt['output_sha256'].items()),
                    'Original launcher hashes do not bind the independent Course completion evidence')
        self.files = OutputFiles(output, started, names, hashes, secure_bytes)
        self.provenance = self.receipt['provenance']
        self.hashes = hashes
        inputs = Path(evidence['evidence_directory']) / 'inputs'

        def dependency(original):
            member = Path(original).relative_to(frozen['project_root']).as_posix()
            data = read_member(inputs, member, nested=True, secure_bytes=secure_bytes)
            fmt.require(digest(data) == evidence['input_sha256'][member], 'Frozen topology or course catalog changed')
            return data

        paths = {Path(path).stem: path for path in frozen['topology_documents']}
        fmt.require(len(paths) == len(frozen['topology_documents']), 'Ambiguous original worksheet identity')
        documents = {key: dependency(path) for key, path in paths.items()}
        self.project = EditableItineraryProject(documents, document_paths=paths,
            expected_hashes={key: digest(data) for key, data in documents.items()}, complete_document_set=True)
        self.project.check_dest_catalog(dependency(frozen['paths']['DestInfoFile']))
        self.dependency = dependency
        self.settings = frozen
        root, _ = writer.load_next_compatible(dependency(frozen['paths']['CourseFile']))
        itineraries = {catalogs.text(item.contents[1].value): item for item in self.project.dests}
        records = [course_record(row) for row in catalogs.course_items(root)]
        inventory = {row['course_id']: row for row in records}
        fmt.require(len(inventory) == len(records) and len(itineraries) == len(self.project.dests),
                    'Ambiguous original Course or Itinerary identity')
        self.itineraries = itineraries
        self.preferences = {}
        for outcome in course_outcomes:
            cid = outcome['course_id']
            row = inventory[cid]
            candidates = row['itineraries']
            fmt.require(row['enabled'] and candidates and len(set(candidates)) == len(candidates)
                        and set(candidates) <= itineraries.keys(), 'Select enabled Courses with valid native Itinerary order')
            self.preferences[cid] = candidates
        self.resources = {}

    def original_text(self, filename):
        fmt.require(filename in self.hashes, f'Original output hashes do not bind {filename}')
        return self.files.read(filename)

    def resource(self, reference, *, allow_empty=False):
        document, name = basename(reference['document']), groups.name(reference['group'])
        identity = document, name
        if identity not in self.resources:
            matches = [(doc, row) for doc, root in self.project.roots.items()
                       for row in groups.records(root, doc) if groups.name_key(row['name']) == groups.name_key(name)]
            fmt.require(len(matches) == 1 and matches[0][0] == document and matches[0][1]['name'] == name,
                        'Missing or ambiguous frozen worksheet occupation monitor')
            membership = native_exclusion.bound_group(self.project.roots[document], document, matches[0][1])
            filename = f'OT_Occ_{name}.occ'
            cycles = [] if allow_empty and filename not in self.files.names else decode_cycles(
                self.original_text(filename), name, allow_empty=allow_empty)
            self.resources[identity] = membership, cycles
        return self.resources[identity]


class FrozenInterlocking(FrozenRailwayRun):
    def __init__(self, output, evidence, course_outcomes, secure_bytes):
        super().__init__(output, evidence, course_outcomes, secure_bytes)
        self.routes = {}
        self.traces = {}
        for cid, candidates in self.preferences.items():
            fmt.require(len(candidates) == 1, 'Select Courses with one enabled, unambiguous saved Itinerary')
            label, = candidates
            spans, distance = route_spans(self.project, self.itineraries[label])
            self.routes[cid] = {'name': label, 'spans': spans, 'length_m': distance}

    def traversal(self, course, resource, tolerance):
        bound, cycles = self.resource(resource)
        key = bound['document'], bound['safety_element_id']
        route = self.routes[course]
        spans = route['spans'].get(key, [])
        fmt.require(len(spans) == 1, f'Expected one contiguous saved route span on {bound["resource"]} for {course}')
        visits = [cycle for cycle in cycles if cycle['course_id'] == course]
        fmt.require(len(visits) == 1, f'Expected one original occupation cycle on {bound["resource"]} for {course}')
        if course not in self.traces:
            self.traces[course] = {
                ext: metres_trace(self.original_text(f'OT_{basename(course)}.{ext}'), ext, course, route['name'])
                for ext in ('st1', 'step1', 'step2')
            }
        traces = self.traces[course]
        movement = traces['st1']
        origin = movement[0][1]
        fmt.require(all(first[1] <= second[1] for first, second in zip(movement, movement[1:]))
                    and abs(movement[-1][1] - origin - route['length_m']) <= tolerance,
                    f'Independent movement distance for {course} differs from the saved Itinerary')
        span = {**spans[0], 'from_m': spans[0]['from_m'] + origin, 'to_m': spans[0]['to_m'] + origin}
        return {**bound, 'itinerary': route['name'], **corroborate(visits[0], span, traces, tolerance)}


def ordered_release(audit, request, tolerance):
    course = request['course_id']
    entries = [audit.traversal(course, ref, tolerance) for ref in request['resources']]
    fmt.require(all(a['to_m'] <= b['from_m'] + STEP_POSITION_TOLERANCE_M for a, b in zip(entries, entries[1:])),
                'Requested release sequence is not ordered along the frozen Itinerary')
    release_gaps = [round(b['reservation_s'][1] - a['reservation_s'][1], 5) for a, b in zip(entries, entries[1:])]
    entry_gaps = [round(b['occupation_s'][0] - a['occupation_s'][0], 5) for a, b in zip(entries, entries[1:])]
    limit = request['minimum_release_gap_s']
    verified = (all(value > CLOCK_TOLERANCE and value + CLOCK_TOLERANCE >= limit for value in release_gaps)
                and all(value > CLOCK_TOLERANCE for value in entry_gaps))
    return {'course_id': course, 'resources': entries, 'release_gaps_s': release_gaps,
            'occupation_entry_gaps_s': entry_gaps, 'minimum_release_gap_s': limit, 'verified': verified}


def overlap_seconds(first, second):
    return round(max(0.0, min(first[1], second[1]) - max(first[0], second[0])), 5)


def parallel_traversal(audit, request, tolerance):
    specs = request['first'], request['second']
    courses = [side['course_id'] for side in specs]
    fmt.require(len(set(courses)) == 2, 'Concurrent traversal requires two distinct original Courses')
    a, b = [audit.traversal(spec['course_id'], spec['resource'], tolerance) for spec in specs]
    identity = [(item['document'], item['safety_element_id']) for item in (a, b)]
    fmt.require(len(set(identity)) == 2, 'Concurrent traversal needs distinct frozen Safety Elements')
    first, second = (audit.routes[course]['spans'] for course in courses)
    shared = sorted(first.keys() & second.keys())
    scope = request['scope']
    fmt.require(scope in ('monitored_spans', 'disjoint_itineraries'), 'Unknown concurrent movement scope')
    physical = overlap_seconds(a['occupation_s'], b['occupation_s'])
    return {'courses': courses, 'resources': [a, b], 'scope': scope,
            'itinerary_safety_element_counts': [len(first), len(second)],
            'shared_saved_itinerary_elements': [{'document': doc, 'safety_element_id': mid} for doc, mid in shared],
            'occupation_overlap_s': physical, 'reservation_overlap_s': overlap_seconds(a['reservation_s'], b['reservation_s']),
            'minimum_overlap_s': request['minimum_overlap_s'],
            'verified': (physical > CLOCK_TOLERANCE and physical + CLOCK_TOLERANCE >= request['minimum_overlap_s']
                         and (not shared or scope == 'monitored_spans'))}


def authority_handover(audit, request, tolerance):
    reference = request['resource']
    leading, following = request['leading_course'], request['following_course']
    fmt.require(leading != following, 'Handover requires two distinct Courses')
    a, b = [audit.traversal(course, reference, tolerance) for course in (leading, following)]
    _, cycles = audit.resource(reference)
    fmt.require(all(None not in row['reservation_s'] for row in cycles), 'Incomplete original authority cycle on handover resource')
    ordered = sorted(cycles, key=lambda row: (row['reservation_s'][0], row['reservation_s'][1], row['course_id']))
    pairs = [(x['course_id'], y['course_id']) for x, y in zip(ordered, ordered[1:])]
    gap = round(b['reservation_s'][0] - a['reservation_s'][1], 5)
    exclusivity = native_exclusion.overlaps(cycles, 'reservation_s')
    return {'resource': a['resource'], 'leading': a, 'following': b, 'handover_gap_s': gap,
            'minimum_gap_s': request['minimum_gap_s'],
            'consecutive_authorities': (leading, following) in pairs, 'whole_trace_authority_exclusion': exclusivity,
            'verified': ((leading, following) in pairs and not exclusivity['overlapping_cycle_count']
                         and gap + CLOCK_TOLERANCE >= request['minimum_gap_s'])}


def audit(output, evidence, requests, secure_bytes=None):
    releases = requests['ordered_releases']
    pairs = requests['concurrent_traversals']
    handovers = requests['consecutive_authorities']
    tolerance = requests['movement_boundary_tolerance_m']
    fmt.require(releases or pairs or handovers, 'Select an original interlocking effect to audit')
    courses = {request['course_id'] for request in releases}
    courses.update(side['course_id'] for request in pairs for side in (request['first'], request['second']))
    courses.update(request[key] for request in handovers for key in ('leading_course', 'following_course'))
    declared = requests['course_outcomes']
    ids = [outcome['course_id'] for outcome in declared]
    fmt.require(len(set(ids)) == len(ids) and set(ids) == courses,
                'Declare an independent completion outcome for each selected Course')
    data = FrozenInterlocking(output, evidence, declared, secure_bytes)
    outcomes = {'ordered_releases': [ordered_release(data, req, tolerance) for req in releases],
                'concurrent_traversals': [parallel_traversal(data, req, tolerance) for req in pairs],
                'consecutive_authorities': [authority_handover(data, req, tolerance) for req in handovers]}
    return {'verified': all(result['verified'] for results in outcomes.values() for result in results),
            'scope': 'Observed movements and authorities for declared original resources and frozen Itineraries',
            'movement_boundary_tolerance_m': tolerance,
            'native_course_completion_verified': data.receipt['native_run_verified'],
            'provenance': data.provenance,
            'original_output_sha256': {**data.receipt['output_sha256'], **data.files.hashes}, **outcomes}
