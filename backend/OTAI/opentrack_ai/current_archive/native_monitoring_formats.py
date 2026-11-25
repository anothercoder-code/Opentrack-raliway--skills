"""Native English OpenTrack monitoring and occupation-statistics file readers."""

import re

from .native_evaluation_formats import data_rows, headers, integer, number, require, series_summary


OCCUPATION_STATISTICS_COLUMNS = {
    'occupation_count': 'Tr.',
    'average_trains_per_hour': 'Tr./h',
    'peak_trains_per_hour': 'Tr./h',
    'time_slot_trains_per_hour': 'Tr./h',
    'average_reservation_percentage': '%',
    'peak_reservation_percentage': '%',
    'time_slot_reservation_percentage': '%',
}


def occupation_slot_time(value):
    if value == 'HH:MM':
        return None
    match = re.fullmatch(r'(?:(\d{1,5}) / )?([01]\d|2[0-3]):([0-5]\d)', value)
    require(match, 'Unexpected original occupation time-slot clock')
    day, hour, minute = match.groups()
    return int(day or 0) * 86400 + int(hour) * 3600 + int(minute) * 60


def occupation_statistics(text):
    headers(text, 'OT_occstatistics')
    lines = set(text.splitlines()[:40])
    known = {'// Type    : OT_BarYPlot', '// x-Legend: none', '// y-Legend: [Tr.]',
             *[f'// y{index}-Legend: [Tr./h]' for index in (1, 2, 3)],
             *[f'// y{index}-Legend: [%]' for index in (4, 5, 6)]}
    require(known <= lines, 'Unexpected native occupation statistics plot type or units')
    slots = re.findall(r'^// Scenario: .* / Occ\. Time Slot: ([^\r\n]+)\r?$', text, re.M)
    require(len(slots) == 1 and slots[0].count(' - ') == 1, 'Missing original occupation statistics time slot')
    start, end = map(occupation_slot_time, slots[0].split(' - '))
    configured = start is not None and end is not None and end > start
    time_slot = {'display_text': slots[0], 'start_s': start, 'end_s': end,
                 'duration_s': end - start if configured else None}
    stats = []
    seen = set()
    for row in data_rows(text):
        require(len(row) == 8 and row[0] and row[0] not in seen, 'Invalid occupation statistics row or duplicate group name')
        values = [integer(row[1]), *map(number, row[2:])]
        require(all(value >= 0 for value in values), 'Negative original occupation statistic')
        stats.append({'name': row[0], **dict(zip(OCCUPATION_STATISTICS_COLUMNS, values, strict=True))})
        seen.add(row[0])
    return {'time_slot': time_slot, 'units': OCCUPATION_STATISTICS_COLUMNS.copy(), 'records': stats}


def power_supply(text):
    headers(text, 'OT_PowerSupply')
    named = re.findall(r'^// Power Supply Output: ([^\r\n]+)\r?$', text, re.M)
    require(len(named) == 1 and named[0].strip() == named[0], 'Missing exact original power-area output name')
    known_header = set(text.splitlines()[:15])
    require({'// x-Legend: [s]', '// y-Legend: [kW]'} <= known_header, 'Unexpected power-area units')
    points = []
    for row in data_rows(text):
        require(len(row) == 2, 'Malformed original power-area series')
        x, y = map(number, row)
        require(x >= 0 and (not points or x >= points[-1][0]), 'Nonchronological power-area clocks')
        points.append((x, y))
    data = {'name': named[0], 'points': points, 'units': ['s', 'kW']}
    return {**data, 'summary': series_summary(data)}


def instruments(text):
    headers(text, 'OT_ins')
    rows = []
    for row in data_rows(text):
        require(len(row) in (6, 7), 'Unexpected native measuring-instrument record')
        run, scenario, instant = integer(row[0]), integer(row[1]), number(row[2])
        require(run >= 0 and instant >= 0, 'Invalid instrument scenario clock or run number')
        output = {'run': run, 'scenario': scenario, 'time_s': instant}
        if len(row) == 7 and row[6]:
            require(row[3:6] == ['', '', ''], 'Unexpected switch-operations columns')
            count = integer(row[6])
            require(count >= 0, 'Negative native switch operation count')
            output.update(kind='switch_operations', switch_operations=count)
        else:
            require(bool(row[4]), 'Missing native instrument Course identity')
            speed = number(row[3])
            direction = integer(row[5])
            output.update(kind='train_record', course_id=row[4], speed_kmh=speed, direction_code=direction)
        rows.append(output)
    summaries = []
    pending = None
    for line in text.splitlines():
        match = re.fullmatch(r'// No\. of Signal Stops\s*:\s*(\d+)\s*', line)
        if match:
            require(pending is None, 'Native signal stop summary is incomplete')
            pending = int(match[1])
        match = re.fullmatch(r'// Sum of Signal Stop Time\s*:\s*([^\s]+)\s*', line)
        if match:
            require(pending is not None, 'No actual stop count accompanies the duration')
            duration = number(match[1])
            require(duration >= 0, 'Negative native signal stop duration')
            summaries.append({'signal_stops': pending, 'signal_stop_time_s': duration})
            pending = None
    require(pending is None, 'Native signal stop summary is incomplete')
    return {'records': rows, 'signal_stop_summaries': summaries,
            'train_record_count': sum(row['kind'] == 'train_record' for row in rows),
            'switch_record_count': sum(row['kind'] == 'switch_operations' for row in rows)}


def instrument_signals(text):
    headers(text, 'OT_sig')
    observed = {}
    for line in text.splitlines():
        match = re.fullmatch(r'// Signal (Doc\.|ID|Name|Kilometre)\s*:\s*(.*?)\s*', line)
        if match:
            require(match[1] not in observed, 'Duplicate original instrument-signal metadata')
            observed[match[1]] = match[2]
    require(set(observed) == {'Doc.', 'ID', 'Name', 'Kilometre'}, 'Missing original instrument-signal metadata')
    signal = {'document': observed['Doc.'], 'model_id': integer(observed['ID']),
              'name': observed['Name'], 'kilometre': number(observed['Kilometre']) if observed['Kilometre'] else None}
    rows = []
    for row in data_rows(text):
        require(len(row) == 7 and row[3], 'Unexpected native instrument-signal record')
        rows.append({'run': integer(row[0]), 'scenario': integer(row[1]), 'time_s': number(row[2]),
                     'course_id': row[3], 'main_signal': row[4], 'distant_signal': row[5],
                     'signal_aspect': row[6]})
    return {'signal': signal, 'records': rows}
