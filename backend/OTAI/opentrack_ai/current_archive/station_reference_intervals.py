"""Review saved timetable reference families whose shared Itinerary changes endpoint."""

from . import catalogs, course_factories, writer
from .catalog_batch_reuse.course_batch import course_record
from .multi_document.core import need, sha
from .native_station_rebind import grouped_rows
from .timetable_intervals import family_timing, reference_families


def review_saved_intervals(banks, endpoint_courses):
    """Validate each saved parent reference on the affected native Itinerary."""
    if not endpoint_courses:
        return {}, set()
    timetable = banks['timetable']
    table = grouped_rows(course_factories.timetable(writer.load_next_compatible(timetable)[0]))
    families = list(reference_families(table, endpoint_courses))
    if not families:
        return {}, set()
    catalog = writer.load_next_compatible(banks['courses'])[0]
    courses = {item['course_id']: item for item in map(course_record, catalogs.course_items(catalog))}
    receipts, verified_rows = {}, set()
    timetable_sha = sha(timetable)
    for root, family, parents in families:
        need(set(family) <= courses.keys(),
             f'Interval family contains a missing Course or timetable: {", ".join(family)}')
        itineraries = courses[root]['itineraries']
        need(len(itineraries) == 1 and all(courses[cid]['itineraries'] == itineraries for cid in family)
             and all(not courses[cid]['enabled'] or cid in endpoint_courses for cid in family),
             f'Interval family {root} needs one shared rebound Itinerary and review of every enabled Course')
        stations, cumulative_offsets = family_timing(table, root, family, parents, distinct_stations=True,
                                                      require_times=True)
        for cid in family:
            reference = parents.get(cid)
            offset = 0 if reference is None else cumulative_offsets[cid] - cumulative_offsets[reference]
            receipt = {'reference_course_id': reference, 'offset_s': offset, 'ordered_station_signs': stations,
                       'family_course_ids': family, 'timetable_sha256': timetable_sha}
            if reference is not None:
                if reference != root:
                    receipt.update(root_reference_course_id=root, root_offset_s=cumulative_offsets[cid])
                verified_rows.update((cid, row.contents[3].value) for row in table[cid])
            receipts[cid] = receipt
    return receipts, verified_rows
