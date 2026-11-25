"""Move the station signs of saved timetable occurrences and every bound Connection6."""

from collections import defaultdict

from . import catalogs, course_factories, native_connections
from .graph_references import incoming_counts
from .operating_plan_edit import UNBOUND, need, text


def grouped_rows(rows):
    groups = defaultdict(list)
    for row in rows.values():
        groups[text(row, 1)].append(row)
    for group in groups.values():
        group.sort(key=lambda row: row.contents[3].value)
    return groups


def rewrite_station_occurrences(plan, groups, target_signs):
    """Resolve references against the original timetable before changing any cells."""
    if not target_signs:
        return []
    by_station = defaultdict(list)
    for cid, rows in groups.items():
        for row in rows:
            by_station[cid, text(row, 5)].append(row.contents[3].value)
    counts = incoming_counts(plan.table)
    pending = []
    receipt = []

    def target_for(course, old_sign):
        matches = by_station.get((course, old_sign), ())
        need(matches, f'Missing original reference to {course!r} at {old_sign!r}')
        projected = {target_signs.get((course, index), old_sign) for index in matches}
        need(len(projected) == 1, f'Repeated visits to {old_sign!r} make the reference to {course!r} ambiguous')
        return next(iter(projected))

    for cid, rows in groups.items():
        for row in rows:
            index = row.contents[3].value
            old_sign = text(row, 5)
            sign = target_signs.get((cid, index), old_sign)
            interval = text(row, 2)
            if interval not in UNBOUND:
                need(target_for(interval, old_sign) == sign,
                     f'Interval-linked Courses must migrate their common station together at {cid}#{index}')
            for item in catalogs.array(row.contents[9].value):
                link = native_connections.record(item)
                other = link['target_course_id']
                prior_target = link['target_station_sign'] or old_sign
                new_target = target_for(other, prior_target)
                if (old_sign, prior_target) == (sign, new_target):
                    continue
                need(counts[id(item)] == 1 and link['course_id'] == cid and link['station_sign'] == old_sign,
                     'The affected Connection6 must have one explicit owner in the original timetable')
                if old_sign != sign:
                    pending.append((item, 2, sign))
                if link['target_station_sign'] or new_target != sign:
                    if link['target_station_sign'] != new_target:
                        pending.append((item, 6, new_target))
                receipt.append({'course_id': cid, 'index': index, 'target_course_id': other,
                                'from_station': old_sign, 'to_station': sign,
                                'from_target_station': prior_target, 'to_target_station': new_target})
            if old_sign != sign:
                need(sign in plan.stations and counts[id(row)] == 1, 'The selected row needs an existing native station')
                pending.append((row, 5, sign))
                plan.changed_course_visits.add(cid)
    for obj, slot, value in pending:
        course_factories.settext(obj, slot, value)
    return receipt
