"""Generate independently replayable integer headway candidates for stock runs."""

from .current_archive import catalogs, course_factories, writer
from .current_archive.catalog_batch_reuse.catalog_batch import apply_batch
from .current_archive.catalog_batch_reuse.course_batch import course_record
from .current_archive.operating_plan_edit import UNBOUND, text, timetable_time


def sweep_courses(expectations, study):
    from .current_archive.native_headway_tools import SpacingCourse

    outcomes = (expectations or {}).get('courses')
    if type(outcomes) is not list or len(outcomes) != 2:
        raise ValueError('A headway sweep requires exactly two complete Course outcomes')
    pair = [SpacingCourse.model_validate(item).model_dump(exclude_none=True) for item in outcomes]
    if ([item['course_id'] for item in pair] != [study['leading_course_id'], study['following_course_id']]
            or pair[0]['course_id'] == pair[1]['course_id']):
        raise ValueError('Supply the ordered pair of distinct Course outcomes')
    if (study.get('comparison_mode', 'same_itinerary') == 'same_itinerary'
            and any(pair[0][key] != pair[1][key] for key in ('origin_station', 'terminal_station', 'distance_m'))):
        raise ValueError('Supply the ordered pair with identical departure station, terminal station and length')
    return pair


def course_pair(blob, ids, mode):
    root, _ = writer.load_next_compatible(blob)
    records = [course_record(item) for item in catalogs.course_items(root)]
    if sorted(item['course_id'] for item in records) != sorted(ids):
        raise ValueError('Only the two selected Courses may be in the frozen catalog')
    by_id = {item['course_id']: item for item in records}
    lead, follow = [by_id[course_id] for course_id in ids]
    if any(not item['enabled'] or len(item['itineraries']) != 1 for item in (lead, follow)):
        raise ValueError('Both Courses must be enabled and each must use a single directed Itinerary')
    if mode == 'shared_fixed_block':
        if (lead['itineraries'] == follow['itineraries']
                or (lead['spacing_mode'], follow['spacing_mode']) != ('discrete', 'discrete')):
            raise ValueError('Use different directed Itineraries with fixed-block spacing for both Courses')
    elif (lead['itineraries'] != follow['itineraries'] or lead['output_offset_m'] != follow['output_offset_m']
          or lead['spacing_mode'] != follow['spacing_mode']):
        raise ValueError('Use one directed Itinerary, spacing mode and distance reference for both Courses')
    return lead, follow


def require_shared_block(project_root, run, inputs, dest_blob, courses):
    from .current_archive.itinerary_edit_tools import EditableItineraryProject
    from .current_archive.native_interlocking import route_spans
    from .current_archive.prepare_contract.auxiliary import records
    from .current_archive.tools import sha

    paths, documents = {}, {}
    for key, value, _ in records(run):
        if key == 'Infrastructure Document':
            normalized = value.replace('\\', '/')
            if not normalized.startswith(project_root.as_posix() + '/'):
                raise ValueError('A shared fixed-block worksheet is outside the selected source project')
            member = normalized[len(project_root.as_posix()) + 1:]
            name = member.rsplit('/', 1)[-1].rsplit('.', 1)[0]
            if name in paths:
                raise ValueError('Ambiguous shared fixed-block worksheet name')
            paths[name], documents[name] = normalized, inputs[member]
    project = EditableItineraryProject(documents, document_paths=paths, complete_document_set=True,
                                      expected_hashes={name: sha(blob) for name, blob in documents.items()})
    project.check_dest_catalog(dest_blob)
    labels = {text(record, 1): record for record in project.dests}
    leading, following = [route_spans(project, labels[course['itineraries'][0]])[0] for course in courses]
    if not leading.keys() & following.keys():
        raise ValueError('The different fixed-block Itineraries do not share any saved Safety Element')


def headway_shift(blobs, study, candidate):
    lead, follow = study['leading_course_id'], study['following_course_id']
    root = writer.load_next_compatible(blobs['timetable'])[0]
    rows = course_factories.timetable(root)
    if {text(row, 1) for row in rows.values()} != {lead, follow}:
        raise ValueError('Headway sweep needs the exact two selected Courses and their timetable rows')
    if any(text(row, 2) not in UNBOUND or catalogs.array(row.contents[9].value) for row in rows.values()):
        raise ValueError('Headway sweep requires direct clocks and unlinked Courses')
    starts = [timetable_time(rows[f'{course}#0'], 'departure') for course in (lead, follow)]
    if any(clock is None or clock < 0 for clock in starts) or starts[0] >= starts[1]:
        raise ValueError('Headway sweep requires actual native planned departure clocks for the ordered pair')
    offset = candidate - (starts[1] - starts[0])
    if offset == 0:
        return blobs['timetable']
    changed, _ = apply_batch(blobs, [{'kind': 'shift_timetable_rows', 'course_ids': [follow], 'seconds': offset}])
    return changed['timetable']
