"""Resolve saved timetable families by direct Course references and row positions."""

from collections import defaultdict
import math

from .operating_plan_edit import ROW_INDEX, UNBOUND, need, text, timetable_time


def _ordered_stations(course_id, rows, *, distinct):
    stations = [text(row, 5) for row in rows]
    indices = [row.contents[3].value for row in rows]
    need(len(rows) >= 2 and indices == list(range(len(rows))) and all(stations)
         and (not distinct or len(set(stations)) == len(stations))
         and all(row.contents[4].value == len(rows) - 1 for row in rows),
         f'Interval Course {course_id} needs consecutive unambiguous native timetable Stations')
    return stations


def _family_references(table, family):
    parents, children = {}, defaultdict(list)
    for cid in sorted(family):
        rows = table[cid]
        references = {text(row, 2) for row in rows}.difference(UNBOUND)
        need(len(references) <= 1, f'Interval Course {cid} needs a single direct timetable reference')
        if references:
            parent = references.pop()
            parents[cid] = parent
            children[parent].append(cid)
        else:
            need(all(row.contents[11].value == 0 for row in rows),
                 f'Interval reference Course {cid} with no parent reference needs a zero offset')
    roots = family - parents.keys()
    need(len(roots) == 1, 'Interval family needs a single root Course and no reference cycle')
    root = roots.pop()
    ordered = [root]
    for cid in ordered:
        ordered.extend(children[cid])
    need(len(ordered) == len(family), 'Interval family contains a reference cycle')
    return root, ordered, parents


def reference_families(table, selected):
    neighbors = defaultdict(set)
    for cid, rows in table.items():
        for row in rows:
            reference = text(row, 2)
            if reference not in UNBOUND:
                neighbors[reference].add(cid)
                neighbors[cid].add(reference)
    pending = set(selected).intersection(neighbors)
    while pending:
        first = min(pending)
        component, frontier = {first}, [first]
        while frontier:
            new = neighbors[frontier.pop()] - component
            component.update(new)
            frontier.extend(new)
        pending.difference_update(component)
        need(component <= table.keys(),
             f'Interval family contains a missing Course or timetable: {", ".join(sorted(component))}')
        yield _family_references(table, component)


def family_timing(table, root, family, parents, *, distinct_stations=False, require_times=False):
    """Check each immediate link and calculate exact offsets from the saved root."""
    stations = _ordered_stations(root, table[root], distinct=distinct_stations)
    cumulative_offsets = {root: 0}
    for cid in family[1:]:
        rows = table[cid]
        need(_ordered_stations(cid, rows, distinct=distinct_stations) == stations,
             f'Interval Course {cid} differs from its reference Stations or their order')
        reference = parents[cid]
        offset = rows[0].contents[11].value
        need(math.isfinite(offset) and offset == int(offset)
             and all(text(row, 2) == reference and row.contents[11].value == offset for row in rows),
             f'Interval Course {cid} needs a single direct timetable reference and one whole-second offset')
        for row, reference_row in zip(rows, table[reference], strict=True):
            for event in ROW_INDEX:
                saved, baseline = timetable_time(row, event), timetable_time(reference_row, event)
                consistent = (baseline is not None and saved == baseline + offset
                              or not require_times and baseline is None and saved is None)
                need(consistent, f'Interval Course {cid} has a saved {event} inconsistent with the direct interval offset')
        cumulative_offsets[cid] = cumulative_offsets[reference] + int(offset)
    return stations, cumulative_offsets
