"""Stock English OpenTrack incident text layouts, from writer and reader evidence."""

import math
import re

from . import catalogs, incident_operations, writer
from .incident_source import validate_set_graph
from .infrastructure_incidents import core, spans

LABELS = {
    1: 'Train', 2: 'Signal', 3: 'Edge', 4: 'Route', 5: 'Path',
    6: 'Position (from-to)', 7: 'Blockage (from-to)', 8: 'Stop and Wait (from-to)',
    9: 'Group of Edges', 10: 'Signal Headway', 11: 'Signal Stop',
    12: 'Train Tractive Effort', 13: 'Route (from-to)', 14: 'Train Power Limitation',
}
BY_LABEL = {name: code for code, name in LABELS.items()}
COLUMNS = ('use', 'type', 'incidentName', 'incidentComment', 'courseID', 'documentName',
           'vertexID', 'objectID', 'beginDayOffset', 'beginTime', 'endDayOffset', 'endTime',
           'speed [km/h]', 'headOnly', 'probabilityPercentage', 'beginDistributionName',
           'durationDistributionName', 'signalStopProbabilityPercentage',
           'signalStopDurationDistributionName', 'tractiveEffortFactor', 'beginLineID',
           'beginTrackID', 'beginKm', 'endLineID', 'endTrackID', 'endKm', 'periodicIncident',
           'period1On', 'period1Off', 'period2On', 'period2Off')
PERIODS = ('occupied1_s', 'free1_s', 'occupied2_s', 'free2_s')
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rows(blob, *, allow_empty=False):
    data = blob.decode('ascii')
    items = []
    names = set()
    for line_number, line in enumerate(data.split('\n'), 1):
        if line.endswith('\r'):
            line = line[:-1]
        require(len(line) <= 1022, f'Line {line_number} exceeds the original reader capacity')
        require(all(ch == '\t' or 32 <= ord(ch) < 127 for ch in line), f'Invalid control on line {line_number}')
        if not line or line.startswith('//'):
            continue
        fields = line.split('\t')
        require(len(fields) in (13, 19, 26, 31), f'Unexpected incident column count on line {line_number}')
        require(fields[1] in BY_LABEL, f'Unknown English incident type on line {line_number}: {fields[1]}')
        require(fields[2] and fields[2] not in names, f'Empty or repeated incident name on line {line_number}')
        names.add(fields[2])
        items.append(dict(zip(COLUMNS, fields)))
    require(items or allow_empty, 'No incident rows')
    return items


def integer(text):
    require(re.fullmatch(r'-?\d+', text), f'Expected a native integer: {text!r}')
    return int(text)


def scalar(text):
    require(re.fullmatch(NUMBER, text), f'Expected a native number: {text!r}')
    number = float(text)
    require(math.isfinite(number), 'A native numeric value must be finite')
    return number


def flag(text):
    require(text in ('0', '1'), f'Expected an explicit stock boolean: {text!r}')
    return text == '1'


def to_item(row):
    code = BY_LABEL[row['type']]
    require(code not in (10, 14), f'Original text omits the headway or power value: {row["incidentName"]}')
    require(code in spans.SPAN_TYPES or not any(row.get(key) for key in COLUMNS[20:26]),
            f'Span columns are not applicable to {row["type"]}')
    item = {
        'name': row['incidentName'], 'enabled': flag(row['use']),
        'type': next(name for name, value in core.TYPES.items() if value == code),
        'begin_day': integer(row['beginDayOffset']), 'begin_time': row['beginTime'],
        'end_day': integer(row['endDayOffset']), 'end_time': row['endTime'],
        'probability_percentage': scalar(row.get('probabilityPercentage', '100')),
    }
    if row['incidentComment']:
        item['comment'] = row['incidentComment']
    if flag(row.get('headOnly', '0')):
        item['head_only'] = True
    for key, name in [('beginDistributionName', 'begin_distribution'),
                      ('durationDistributionName', 'duration_distribution')]:
        if row.get(key):
            item[name] = row[key]
    if flag(row.get('periodicIncident', '0')):
        item['periodic'] = dict(zip(PERIODS, (scalar(row[key]) for key in COLUMNS[27:31])))
    if code in (1, 12):
        require(not row['documentName'] and row['vertexID'] in ('', '-1') and row['objectID'] in ('', '-1'),
                f'Unexpected infrastructure fields for {row["type"]}')
        item['course_id'] = row['courseID']
    elif code in spans.SPAN_TYPES:
        item.update(span_from_row(row, code))
    else:
        require(not row['courseID'], f'Unexpected Course ID for {row["type"]}')
        item['document'] = row['documentName']
    if code in (1, 4, 5, 6, 13):
        item['reduced_speed_kmh'] = scalar(row['speed [km/h]'])
    if code == 12:
        require('tractiveEffortFactor' in row, 'This incident layout omits the tractive-effort value')
        item['tractive_effort_factor'] = scalar(row['tractiveEffortFactor'])
    if code in (2, 3, 11):
        item['model_id'] = integer(row['vertexID'])
    if code in (4, 5):
        item.update(start_end_id=integer(row['vertexID']), array_id=integer(row['objectID']))
    if code == 9:
        item['model_ids'] = [integer(value) for value in row['vertexID'].split('#')]
    if code == 11:
        item['stop_probability_percentage'] = scalar(row.get('signalStopProbabilityPercentage', '100'))
        duration = row.get('signalStopDurationDistributionName', '0')
        if re.fullmatch(NUMBER, duration):
            item['stop_duration_s'] = scalar(duration)
        else:
            item['stop_duration_distribution'] = duration
    return item


def span_from_row(row, code):
    require(all(key in row for key in COLUMNS[20:26]), 'Original text row omits kilometre/route span columns')
    require(not row['documentName'] and row['vertexID'] in ('', '-1') and row['objectID'] in ('', '-1'),
            'Span targets use line and track selectors or Route names')
    require(scalar(row['tractiveEffortFactor']) == 1, 'Unexpected tractive-effort factor for a spatial incident')
    if code == 13:
        require(not (row['beginLineID'] or row['endLineID']), 'Route names are stored in the Track ID columns')
        result = dict(begin_route=row['beginTrackID'], end_route=row['endTrackID'],
                      begin_offset_km=row['beginKm'], end_offset_km=row['endKm'])
        if row['courseID'] not in ('', '0'):
            result['course_id'] = row['courseID']
        return result
    require(not row['courseID'], 'The original track range applies across Courses')
    require(row['beginLineID'] == row['endLineID'] and row['beginTrackID'] == row['endTrackID'],
            'The original resolver uses one line and track for both ends of the range')
    result = dict(line_id=row['beginLineID'], track_id=row['beginTrackID'],
                  begin_km=row['beginKm'], end_km=row['endKm'])
    if code == 8:
        result['wait_time_s'] = 0
    return result


def wire_number(number):
    require(math.isfinite(number), 'Cannot write a nonfinite numeric field')
    return format(number, '.9g')


def encode_catalog(blob):
    root, _ = writer.load_next_compatible(blob)
    catalogs.course_items(root)
    incidents, _ = validate_set_graph(root)
    lines = ['// Incidents (Text)', '// ' + '\t'.join(COLUMNS)]
    for incident in incidents:
        catalogs.shape(incident, 'OTIncident', 12, incident_operations.SCHEMA)
        cells = incident.contents
        def string(slot):
            return catalogs.text(cells[slot].value)
        aid, vertex, code = cells[5].values
        flags = cells[7].value
        require(code in LABELS and 0 <= flags <= 15, 'Unknown saved incident type or flags')
        require(not (flags & 4), f'Original text cannot preserve the discrete moving-block flag: {string(0)}')
        require(code not in (10, 14), f'Original text cannot preserve headway or power: {string(0)}')
        speed, tractive, mtbf, mttr = cells[6].values
        require(mtbf == mttr == 0 and cells[14].value == 0 and cells[24].value == -1,
                f'Original text cannot preserve extra time or power fields: {string(0)}')
        group = [core.number_value(value) for value in catalogs.array(cells[20].value)]
        vertex_value = '#'.join(map(str, group)) if group else str(vertex)
        begin, end = cells[15].values
        span = [string(slot) for slot in (8, 10, 12, 9, 11, 13)]
        fields = [
            str(flags & 1), LABELS[code], string(0), string(16),
            '' if string(1) == '0' else string(1), '' if string(2) == '0' else string(2),
            vertex_value, '' if aid == -1 else str(aid), str(begin), string(3), str(end), string(4),
            wire_number(speed), str(int(bool(flags & 2))), wire_number(cells[19].value), string(21), string(18),
            wire_number(cells[22].value) if code == 11 else '', string(23) if code == 11 else '',
            wire_number(tractive), *span,
        ]
        if tractive != 1 or any(span):
            # Stock 31-field reader does not restore columns 20–26.
            require(not flags & 8, f'Stock text cannot restore periodic and span/traction fields together: {string(0)}')
        else:
            fields.extend(['1', *map(wire_number, cells[17].values)] if flags & 8 else ['0', '', '', '', ''])
        require(all('\t' not in value and '\r' not in value and '\n' not in value for value in fields),
                'Native fields cannot contain table delimiters')
        lines.append('\t'.join(fields))
    data = ('\r\n'.join(lines) + '\r\n').encode('ascii')
    rows(data, allow_empty=True)
    return data
