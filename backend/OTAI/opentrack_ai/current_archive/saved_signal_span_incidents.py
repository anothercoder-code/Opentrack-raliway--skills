"""Keep Route-relative speed Incident chainage exact through a new relay."""

from . import catalogs, writer
from .catalog_batch_reuse.course_batch import course_record
from .multi_document.core import need
from .saved_span_incident_rebinding import rebind_span_incidents
from .saved_terminal_overlap import _edge_locking_resources


def rebind_signal_route_incidents(courses, original, saved, reviews, *, sequence, split, old_name, suffix_name):
    """Keep the original physical speed interval while renewing its native Route names."""
    cut = sequence.index(split)
    edges = [original.edge_between(first, last) for first, last in zip(sequence, sequence[1:])]
    first, first_exclusions = _edge_locking_resources(original, edges[:cut])
    last, last_exclusions = _edge_locking_resources(original, edges[cut:])
    need(not (first | first_exclusions) & (last | last_exclusions),
         'Incident-preserving sections require independent native Safety Elements and Edge exclusions')
    controlled = {key for end in sequence for key in (end, original.related(end), original.actual_related(end))}
    need(all(original.model(key).contents[21].value == 0 for key in controlled),
         'The reviewed Incident Route must have zero saved switch time at its direction Ends')
    root, _ = writer.load_next_compatible(courses)
    active = {row['course_id']: row for row in map(course_record, catalogs.course_items(root)) if row['enabled']}
    output, receipts = rebind_span_incidents(courses, original, saved, reviews)
    for receipt in receipts:
        before, after = receipt['before'], receipt['after']
        need(receipt['type'] == 13 and before['attachment']['course_id'],
             'The relay can preserve only a named-Course Route-span speed Incident')
        old = before['selector']
        new = after['selector']
        need(old['begin_route'] == old['end_route'] == old_name
             and [new['begin_route'], new['end_route']] in ([old_name, suffix_name], [suffix_name, suffix_name]),
             'The reviewed Incident must use the original Route and pass into the new suffix')
        original_attachment, saved_attachment = before['attachment'], after['attachment']
        need(all(original_attachment[key] == saved_attachment[key] for key in ('course_id', 'begin', 'end', 'edges')),
             'The original and revised Incident must bind the same directed physical positions and interval')
        course = active[original_attachment['course_id']]
        need(course['spacing_mode_code'] == 0 and course['additional_reservation_time_s'] == 0
             and len(course['itineraries']) == 1,
             'Incident preservation requires one fixed-block Course Itinerary and zero additional reservation delay')
    return output, receipts
