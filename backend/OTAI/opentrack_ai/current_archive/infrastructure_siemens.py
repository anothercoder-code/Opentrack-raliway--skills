"""Restore the original Siemens tabular line format to an ordinary worksheet."""

from .infrastructure_ivt import (
    MAX_SOURCE_BYTES, Row, decimal_value, materialize_line, optional_number, require, speed,
)


def parse_siemens(raw, default_limits):
    require(0 < len(raw) <= MAX_SOURCE_BYTES, 'Expected bounded nonempty Siemens text')
    try:
        source = raw.decode('ascii')
    except UnicodeError as exc:
        raise ValueError('Siemens infrastructure uses ASCII tab-separated text') from exc
    rows, annotations = [], []
    forward, reverse = (list(limits) for limits in zip(*default_limits))
    grade = radius = 0
    for index, line in enumerate(source.split('\n'), 1):
        line = line.removesuffix('\r')
        require(len(line) <= 1022 and all(char == '\t' or ' ' <= char <= '~' for char in line),
                f'Siemens line {index} exceeds the native row or printable ASCII range')
        line = line.lstrip(' \t')
        if not line or line.startswith('//'):
            continue
        try:
            fields = line.split('\t')
            require(len(fields) <= 8, 'expected the eight Siemens tab fields')
            position, velocity, gradient, curve, tunnel, station, time, remark = [
                value.strip() for value in fields + [''] * (8 - len(fields))
            ]
            position = decimal_value(position.replace(':', '.'), 'position')
            previous_reverse = tuple(reverse)
            limit = speed(velocity)
            if limit is not None:
                forward[0] = reverse[0] = limit
            grade = optional_number(gradient, 'gradient', grade)
            radius = optional_number(curve, 'radius', radius)
            tunnel_type = optional_number(tunnel, 'tunnel type', 0)
            require(tunnel_type == int(tunnel_type), 'tunnel type must be an original integer')
            if 'Start Station' in station or 'End Station' in station:
                station = ''
            rows.append(Row(index, position, ('', ''), (None, None), tuple(forward),
                            previous_reverse if rows else tuple(reverse), float(grade),
                            float(radius), 3 if tunnel_type == 2 else 1, (None, None), station))
            if time or remark:
                annotations.append({'source_line': index, 'time': time, 'remark': remark})
        except ValueError as exc:
            raise ValueError(f'Siemens line {index}: {exc}') from exc
        require(len(rows) <= 1000, 'Siemens continuous import supports at most 1000 rows')
    require(len(rows) >= 2, 'Siemens continuous line requires at least two distinct positions')
    return rows, annotations


def import_siemens(raw, header, shapes, station_catalog, default_limits):
    rows, annotations = parse_siemens(raw, default_limits)
    worksheet, report = materialize_line(rows, header, shapes, station_catalog, (), 500,
                                         station_match='name')
    return worksheet, {**report, 'source_format': 'Siemens', 'source_annotations': annotations,
                       'default_directional_limits_kmh': default_limits}
