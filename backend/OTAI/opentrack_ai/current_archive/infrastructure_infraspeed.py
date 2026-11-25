"""Original Infraspeed format-5 geometry, station and directed signal import."""

from decimal import Decimal
import re

from .infrastructure_ivt import MAX_SOURCE_BYTES, Row, decimal_value, materialize_line, require, speed, tunnel
from .infrastructure_signal_profile import attach_template_signals, inspect_signal_template


SIGNAL_TYPES = {'main': 1, 'main distant': 2, 'distant': 3, 'main 2 asp': 24,
                'main distant 2 asp': 24, 'main 3 asp': 25, 'main distant 3 asp': 25,
                'main 4 asp': 26, 'main distant 4 asp': 26, 'distant 2 asp': 27}
MAIN_ROLES = {'home': 2, 'block': 3, 'exit': 4}


def signal_profile(text, template):
    require(template is not None, 'Infraspeed signal fields require a pinned native signal profile')
    words = text.lower().split()
    roles = [word for word in words if word in MAIN_ROLES]
    virtual = [word for word in words if word in ('virt', 'virtual')]
    key = ' '.join(word for word in words if word not in (*roles, *virtual, 'signal'))
    require(key in SIGNAL_TYPES and len(roles) <= 1 and len(virtual) <= 1,
            f'Unsupported Infraspeed signal label {text!r}')
    main = key.startswith('main')
    require(main or not roles, 'Infraspeed home, block and exit roles apply to main signals')
    role = MAIN_ROLES[roles[0]] if roles else (3 if main else template['main_role'])
    return {'type_raw': SIGNAL_TYPES[key], 'main_role': role, 'virtual': bool(virtual)}


def whole(value, label):
    require(re.fullmatch(r'-?[0-9]{1,8}', value) is not None, f'Infraspeed {label} requires a whole integer')
    result = int(value)
    require(abs(result) <= 16777216, f'Infraspeed {label} exceeds the reviewed exact binary32 integer range')
    return result


def source_number(value, label):
    require(',' not in value, f'Infraspeed {label} uses a period as decimal separator')
    return float(decimal_value(value, label))


def track_type(value):
    if value in ('0', '1', '2'):
        return int(value) + 1
    require(value.lower() != 'no tunnel', 'Use original Infraspeed tunnel code 0 for open track')
    return tunnel(value)


def parse_infraspeed(raw, default_limits, template=None):
    require(0 < len(raw) <= MAX_SOURCE_BYTES, 'Expected bounded nonempty Infraspeed text')
    try:
        text = raw.decode('ascii')
    except UnicodeError as exc:
        raise ValueError('Infraspeed requires printable ASCII tab-delimited text') from exc
    rows, drawing, source_signals = [], [], []
    limits = [tuple(pair) for pair in default_limits]
    grade = radius = 0.0
    track = 1
    for line_index, line in enumerate(text.split('\n'), 1):
        line = line.removesuffix('\r')
        require(len(line) <= 1022 and all(char == '\t' or ' ' <= char <= '~' for char in line),
                f'Infraspeed line {line_index} exceeds the original row or printable ASCII range')
        line = line.lstrip(' \t')
        if not line or line.startswith('//'):
            continue
        try:
            fields = line.split('\t')
            require(4 <= len(fields) <= 12, 'expected the four leading Infraspeed columns and up to eight optional fields')
            position, name, x, y, ascending, descending, gradient, curve, tunnel_value, up, down, station = [
                value.strip() for value in fields + [''] * (12 - len(fields))
            ]
            metres = whole(position, 'chainage')
            xy = (whole(x, 'X'), whole(y, 'Y'))
            if rows:
                require(0 < metres - rows[-1].position <= 16777216, 'Infraspeed chainage must increase by native whole metres')
                require(xy[0] > drawing[-1][0] and xy[1] == drawing[-1][1],
                        'Infraspeed drawing requires increasing X on one horizontal native worksheet line')
            prior_reverse = tuple(pair[1] for pair in limits)
            limit_up, limit_down = (speed(str(source_number(value, 'speed'))) if value else None
                                    for value in (ascending, descending))
            current_up, current_down = limits[0]
            limits[0] = (current_up if limit_up is None else limit_up, current_down if limit_down is None else limit_down)
            grade = source_number(gradient, 'gradient') if gradient else grade
            radius = source_number(curve, 'radius') if curve else radius
            track = track_type(tunnel_value) if tunnel_value else track
            km = Decimal(metres) / 1000
            rows.append(Row(line_index, Decimal(metres), (name, name), (km, km), tuple(pair[0] for pair in limits),
                            prior_reverse if rows else tuple(pair[1] for pair in limits), grade, radius, track,
                            (None, None), station))
            drawing.append(xy)
            for side, label in enumerate((up, down)):
                if label:
                    source_signals.append((len(rows) - 1, side, label, signal_profile(label, template)))
        except (ValueError, OverflowError) as exc:
            raise ValueError(f'Infraspeed line {line_index}: {exc}') from exc
        require(len(rows) <= 1000, 'Infraspeed continuous import supports at most 1000 selected rows')
    require(len(rows) >= 2, 'Infraspeed requires at least two positions')
    return rows, drawing, source_signals


def import_infraspeed(raw, header, shapes, station_catalog, default_limits, signal_id=None, signal_template=None):
    require((signal_template is None) == (signal_id is None), 'Bind both the Infraspeed signal template and model ID')
    template = inspect_signal_template(signal_template, signal_id) if signal_template is not None else None
    rows, drawing, source_signals = parse_infraspeed(raw, default_limits, template)
    document, report = materialize_line(rows, header, shapes, station_catalog, (), 500, drawing_coordinates=drawing)
    selections = []
    for index, side, label, profile in source_signals:
        vertex = report['vertices'][index]
        direction = 'descending' if side else 'ascending'
        selections.append({**profile, 'source_label': label, 'source_line': rows[index].line,
                           'direction': direction, 'end_id': vertex[f'{direction}_end_id'],
                           'position_m': vertex['position_m']})
    document, signals = attach_template_signals(document, selections, template)
    return document, {**report, 'source_format': 'Infraspeed', 'original_import_format': 5,
                      'drawing_coordinates': drawing, 'signals': signals, 'signal_template': template,
                      'default_directional_limits_kmh': default_limits}
