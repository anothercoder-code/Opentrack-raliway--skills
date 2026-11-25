"""Audit exclusive original safety elements using a bound occupation trace."""

from pathlib import Path

from . import native_evaluation_formats as fmt
from . import native_occupation_groups as groups
from . import writer


# Original occupation files print both clocks to hundredths of a second.
CLOCK_TOLERANCE_S = 0.010001


def bound_group(root, document, group):
    _, inventory = groups.models(root)
    groups.verify_edges(inventory, group['edge_ids'])
    fmt.require(group['selected'] and group['saved_document'] == document,
                'Monitor must be selected and bound to the original worksheet')
    edges = {key: item for key, item in inventory.items() if writer.kind(item) == 'OTEdgeModel'}
    elements = {id(edges[key].contents[index].value.contents[7].value):
                edges[key].contents[index].value.contents[7].value
                for key in group['edge_ids'] for index in (7, 8)}
    fmt.require(len(elements) == 1, 'An exclusive monitor must resolve to a single saved Safety Element')
    element, = elements.values()
    attached = {key for key, edge in edges.items()
                if any(edge.contents[index].value.contents[7].value is element for index in (7, 8))}
    fmt.require(attached == set(group['edge_ids']), 'Monitor omits one or more Edges of the saved Safety Element')
    return {'document': document, 'resource': group['name'], 'safety_element_id': element.contents[0].value,
            'edge_ids': sorted(attached)}


def overlaps(cycles, phase):
    order = sorted((cycle[phase][0], cycle[phase][1], cycle['course_id']) for cycle in cycles)
    leaders = []
    count = 0
    witnesses = []
    for start, end, course in order:
        # The two latest ends of distinct Courses suffice for the longest previous
        # candidate whose Course differs from the current one.
        other = next((item for item in leaders if item[2] != course), None)
        if other is not None:
            shared = min(other[0], end) - start
            if shared > CLOCK_TOLERANCE_S:
                count += 1
                if len(witnesses) < 30:
                    witnesses.append({'courses': [other[2], course], 'overlap_s': round(shared, 5),
                                      'intervals_s': [[other[1], other[0]], [start, end]]})
        if end - start <= CLOCK_TOLERANCE_S:
            continue
        same = next((item for item in leaders if item[2] == course), None)
        if same is None or end > same[0]:
            leaders = sorted([item for item in leaders if item[2] != course] + [(end, start, course)],
                             reverse=True)[:2]
    return {'overlapping_cycle_count': count, 'examples': witnesses}


def examine(text, group, required_courses):
    events = fmt.occupations(text)
    fmt.require(all(item['resource'] == group for item in events), 'Native output resource name differs from its monitor')
    cycles, unpaired = fmt.occupation_intervals(events)
    fmt.require(events and cycles and not unpaired and all(item['time_s'] is not None for item in events),
                'Native occupation trace lacks complete, timed reservation and occupation cycles')
    occupied = {cycle['course_id'] for cycle in cycles if cycle['occupation_s'][1] > cycle['occupation_s'][0]}
    missing = sorted(set(required_courses) - occupied)
    reserve = overlaps(cycles, 'reservation_s')
    physical = overlaps(cycles, 'occupation_s')
    return {'cycle_count': len(cycles), 'event_count': len(events), 'courses_occupying': sorted(occupied),
            'required_courses_missing': missing, 'reservation': reserve, 'occupation': physical,
            'timestamp_tolerance_s': .01,
            'verified': not (missing or reserve['overlapping_cycle_count'] or physical['overlapping_cycle_count'])}


def audit(specs, files, frozen, evidence, *, read_member, digest, basename, secure_bytes):
    fmt.require(frozen is not None and evidence is not None, 'Exclusive-resource checks require frozen original inputs')
    fmt.require(isinstance(specs, list) and 1 <= len(specs) <= 64, 'Specify 1 to 64 exclusive groups')
    requested = {}
    for spec in specs:
        fmt.require(isinstance(spec, dict) and set(spec) == {'document', 'group', 'courses'},
                    'Specify document, group and courses for each exclusive-resource check')
        name = groups.name(spec['group'])
        courses = spec['courses']
        fmt.require(isinstance(courses, list) and 2 <= len(courses) <= 10000
                    and len({basename(course).casefold() for course in courses}) == len(courses),
                    'Specify at least two distinct expected Courses using this resource')
        key = groups.name_key(name)
        fmt.require(key not in requested, 'Duplicate exclusive occupation group name')
        requested[key] = (basename(spec['document']), name, courses)
    inputs = Path(evidence['evidence_directory']).resolve(strict=True) / 'inputs'
    selections = {}
    for original in frozen['topology_documents']:
        path = Path(original)
        document = path.stem
        relative = path.relative_to(frozen['project_root']).as_posix()
        data = read_member(inputs, relative, nested=True, secure_bytes=secure_bytes)
        fmt.require(digest(data) == evidence['input_sha256'][relative], 'Frozen worksheet differs from its manifest')
        root, _ = writer.load_next_compatible(data)
        for group in groups.records(root, document):
            key = groups.name_key(group['name'])
            if key not in requested:
                continue
            expected_document, name, _ = requested[key]
            fmt.require(key not in selections and document == expected_document and group['name'] == name,
                        'Ambiguous or misbound original monitor name')
            selections[key] = bound_group(root, document, group)
    fmt.require(set(selections) == set(requested), 'One or more monitor names are absent from the frozen worksheets')
    return [{**selections[key], **examine(files.read(f'OT_Occ_{name}.occ'), name, courses)}
            for key, (_, name, courses) in requested.items()]
