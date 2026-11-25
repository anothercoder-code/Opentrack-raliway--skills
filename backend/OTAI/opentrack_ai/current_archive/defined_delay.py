"""Saved inputs for the original Defined delay selection."""

from math import isfinite

from . import course_factories, writer
from .operating_plan_edit import need, text


def update_visits(plan, visits):
    identities = [(item['course_id'], item['index']) for item in visits]
    need(len(identities) == len(set(identities)), 'A Defined delay timetable occurrence was selected twice')
    report = []
    for item in visits:
        cid, index = item['course_id'], item['index']
        row = plan.row(cid, index)
        station = text(row, 5)
        need(station == item['station_sign'], 'Selected Defined delay occurrence has a different saved Station sign')
        old_delay, distribution = text(row, 12), text(row, 16)
        fields = {'mean_delay_s': item['delay_s']}
        if distribution:
            need(item['clear_distribution'], 'Confirm removal of the existing named distribution for this fixed mean')
            fields['distribution_name'] = ''
        plan.update_timetable_row({'course_id': cid, 'index': index, 'fields': fields})
        report.append({'course_id': cid, 'index': index, 'station_sign': station,
                       'mean_delay_before': old_delay, 'mean_delay_s': item['delay_s'],
                       'removed_distribution_name': distribution or None})
    return report


def preflight(values, timetable_path, blob):
    if values.get('Delay Scenario') != ['-1']:
        return None
    raw_global = values.get('Mean Delay', [None])[0]
    raw_rows = course_factories.timetable(writer.load_next_compatible(blob)[0])
    mean_rows = initial_row_means = named_rows = 0
    for row in raw_rows.values():
        value = text(row, 12)
        numeric = float(value) if value else 0.0
        need(isfinite(numeric), 'Defined delay timetable contains a nonfinite mean')
        mean_rows += numeric != 0
        initial_row_means += numeric != 0 and row.contents[3].value == 0
        named_rows += bool(text(row, 16))
    global_mean = float(raw_global) if raw_global is not None else None
    need(global_mean is None or isfinite(global_mean), 'Defined delay uses a nonfinite global mean')
    return {'name': 'defined', 'scenario': -1, 'timetable_path': timetable_path,
            'global_mean_delay_s': global_mean, 'timetable_rows_with_nonzero_mean': mean_rows,
            'index_zero_rows_with_nonzero_mean': initial_row_means,
            'timetable_rows_with_named_distribution': named_rows, 'separate_delay_file_required': False}
