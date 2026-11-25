"""Materialize the original SBB ZLR continuous line from its audited format-1 columns."""

from decimal import Decimal
import math
import re

from .infrastructure_ivt import MAX_SOURCE_BYTES, Row, decimal_value, materialize_line, require, speed
from .infrastructure_signal_profile import attach_template_signals, inspect_signal_template
from .zero_generation.topology import flt


ZLR_DECIMAL = re.compile(r'-?[0-9]{1,9}(?:\.[0-9]{1,9})?')


def number(value, label, *, kilometration=False):
    if kilometration:
        value = value.replace(':', '.')
    require(ZLR_DECIMAL.fullmatch(value) is not None, f'{label} requires a signed decimal with a period')
    return decimal_value(value, label)


def edge_length(previous, current):
    require(current > previous, 'SBB ZLR cumulative positions must strictly increase in the selected table')
    # importCreatePressed (0x549bf8) reads binary64 positions then rounds metres
    # using the binary32 input and the native 0x6def2c half-up conversion.
    metres = flt((float(current) - float(previous)) * 1000.0, 'SBB ZLR edge length')
    length = math.floor(metres + 0.5)
    require(0 < length <= 2147483647, 'SBB ZLR consecutive positions must yield a positive native metre length')
    return length


def tunnel_profile(area):
    if area <= 1:
        return 1
    return 2 if area <= 45 else 3


def parse_sbb_zlr(raw, default_limits, *, signal_template_supplied=False):
    require(0 < len(raw) <= MAX_SOURCE_BYTES, 'Expected bounded nonempty SBB ZLR text')
    try:
        table = raw.decode('ascii')
    except UnicodeError as exc:
        raise ValueError('SBB ZLR requires printable ASCII tab-delimited text') from exc

    rows, annotations = [], []
    previous = None
    line_position = Decimal(0)
    limits = [tuple(pair) for pair in default_limits]
    grade = radius = area = 0.0
    for index, line in enumerate(table.split('\n'), 1):
        line = line.removesuffix('\r')
        require(len(line) <= 1022 and all(char == '\t' or ' ' <= char <= '~' for char in line),
                f'SBB ZLR line {index} exceeds the original input row or printable ASCII range')
        line = line.lstrip(' \t')
        if not line or line.startswith('//'):
            continue
        try:
            fields = line.split('\t')
            require(3 <= len(fields) <= 12, 'expected SBB ZLR columns 1–3 and up to nine optional trailing fields')
            code, km, position, gradient, curve, tunnel, limit4, limit1, limit2, signal, station_name, station_sign = [
                value.strip() for value in fields + [''] * (12 - len(fields))
            ]
            measured = number(position, 'cumulative position', kilometration=True)
            kilometre_mark = number(km, 'kilometre mark', kilometration=True) if km else None
            if signal:
                require(signal_template_supplied, 'SBB ZLR signal fields require a separately validated native signal profile')
                require(signal[0] in 'HV', 'SBB ZLR signal fields must begin with original H or V')
            duplicate = measured == previous
            if duplicate:
                prior = annotations[-1]['signal_column_10']
                require(signal and prior and signal[0] != prior[0]
                        and (len(annotations) < 2 or annotations[-2]['distance_from_start_m'] != int(line_position)),
                        'SBB ZLR positions must strictly increase except for one complementary H/V pair')
                require(kilometre_mark is not None and rows[-1].km[0] == kilometre_mark,
                        'Complementary SBB ZLR signals require identical explicit kilometre marks')
                require(not rows[-1].station or rows[-1].station == station_sign,
                        'The surviving SBB ZLR row must retain the station sign of the first co-located row')
            reverse = rows[-1].reverse if duplicate else tuple(pair[1] for pair in limits)
            if previous is not None and not duplicate:
                line_position += edge_length(previous, measured)
            for category, value in ((0, limit1), (1, limit2), (3, limit4)):
                if value:
                    require(not value.startswith('-'), 'SBB ZLR speeds require nonnegative fields')
                    limit = speed(str(number(value, 'speed')))
                    limits[category] = (limit, limit)
            if gradient:
                grade = float(flt(float(number(gradient, 'gradient')), 'SBB ZLR gradient'))
            if curve:
                radius = float(flt(float(number(curve, 'radius')), 'SBB ZLR radius'))
            if tunnel:
                require(not tunnel.startswith('-'), 'SBB ZLR tunnel area must be nonnegative')
                area = float(flt(float(number(tunnel, 'tunnel area')), 'SBB ZLR tunnel area'))
            forward = tuple(pair[0] for pair in limits)
            row = Row(index, line_position, ('', ''), (kilometre_mark, kilometre_mark), forward,
                      reverse if rows else tuple(pair[1] for pair in limits), grade, radius,
                      tunnel_profile(area), (None, None), station_sign)
            if duplicate:
                rows[-1] = row
            else:
                rows.append(row)
            annotations.append({'source_line': index, 'source_position_km': str(measured),
                                'distance_from_start_m': int(line_position), 'kilometre_mark': (
                                    str(kilometre_mark) if kilometre_mark is not None else None),
                                'column_1': code, 'signal_column_10': signal, 'station_name_column_11': station_name,
                                'station_sign_column_12': station_sign,
                                'effective_tunnel_area_m2': area})
            previous = measured
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f'SBB ZLR line {index}: {exc}') from exc
        require(len(annotations) <= 1000, 'SBB ZLR continuous import supports at most 1000 selected rows')
    require(len(rows) >= 2, 'SBB ZLR continuous line requires at least two positions')
    return rows, annotations


def attach_sbb_signals(document, vertices, annotations, template):
    by_position = {}
    for source in annotations:
        if source['signal_column_10']:
            by_position.setdefault(str(source['distance_from_start_m']), []).append(source)
    selections = []
    for vertex in vertices:
        sources = by_position.get(vertex['position_m'])
        if not sources:
            continue
        codes = [source['signal_column_10'] for source in sources]
        signal_type = 2 if len(codes) == 2 else {'H': 1, 'V': 3}[codes[0][0]]
        selections.append({'end_id': vertex['ascending_end_id'], 'position_m': vertex['position_m'],
                           'source_lines': [source['source_line'] for source in sources], 'source_designations': codes,
                           'type_raw': signal_type, 'direction': 'ascending'})
    return attach_template_signals(document, selections, template)


def import_sbb_zlr(raw, header, shapes, station_catalog, default_limits, signal_id=None, signal_template=None):
    require((signal_template is None) == (signal_id is None), 'Bind both the SBB ZLR signal template and model ID')
    rows, annotations = parse_sbb_zlr(raw, default_limits, signal_template_supplied=signal_template is not None)
    template = inspect_signal_template(signal_template, signal_id) if signal_template is not None else None
    worksheet, report = materialize_line(rows, header, shapes, station_catalog, (), 500, station_match='sign')
    worksheet, signals = attach_sbb_signals(worksheet, report['vertices'], annotations, template)
    return worksheet, {**report, 'source_format': 'SBB_ZLR', 'original_import_format': 1,
                       'source_annotations': annotations, 'default_directional_limits_kmh': default_limits,
                       'signals': signals, 'signal_template': template}
