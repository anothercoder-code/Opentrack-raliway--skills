"""The original tabulated Bentley Rail Track to OpenTrack IVT converters."""

from decimal import Decimal, ROUND_HALF_UP
import re

from .infrastructure_ivt import MAX_SOURCE_BYTES, NATIVE_BENTLEY_IVT_HEADER, decimal_value, parse_ivt, require
from .zero_generation.topology import flt


def bentley_scalar(text, label):
    # OTOutputController.removeYMSigns: (0x52cd44).
    cleaned = re.sub(r'[^0-9.\-]', '', text)
    return float(flt(float(decimal_value(cleaned, label)), label))


def fixed(value, places):
    # Original Windows MSVCRT printf rounds an exact half away from zero.
    precision = Decimal(1).scaleb(-places)
    return str(Decimal.from_float(value).quantize(precision, rounding=ROUND_HALF_UP))


def convert_bentley(raw, orientation):
    require(orientation in ('horizontal', 'vertical'), 'Select an original Bentley alignment report type')
    require(0 < len(raw) <= MAX_SOURCE_BYTES, 'Expected a bounded nonempty Bentley Rail Track report')
    try:
        source = raw.decode('ascii')
    except UnicodeError as exc:
        raise ValueError('Bentley alignment reports require printable ASCII tab-delimited text') from exc

    rendered, records = [], []
    ignored = 0
    for line_number, line in enumerate(source.split('\n'), 1):
        line = line.removesuffix('\r')
        require(len(line) <= 1022 and all(char == '\t' or ' ' <= char <= '~' for char in line),
                f'Bentley report line {line_number} exceeds its original buffer or printable ASCII range')
        line = line.lstrip(' \t')
        if not line:
            continue
        circular = orientation == 'horizontal' and 'Circular' in line
        if not circular and 'Linear' not in line:
            ignored += 1
            continue
        fields = line.split('\t')
        try:
            require(len(fields) >= (12 if orientation == 'horizontal' else 5), 'missing original report columns')
            position = bentley_scalar(fields[2], 'Bentley chainage')
            metre = int(fixed(position, 0))
            require(-2147483648 <= metre <= 2147483647, 'Bentley chainage exceeds signed native metres')
            km = fixed(float(flt(position / 1000, 'Bentley kilometre mark')), 3)
            if orientation == 'vertical':
                gradient, radius = fixed(bentley_scalar(fields[4], 'Bentley gradient'), 2), ''
            else:
                gradient, radius = '', fixed(bentley_scalar(fields[11], 'Bentley radius') if circular else 0.0, 1)
            values = [str(metre), '', '', km, km, *(['200'] * 8), gradient, radius, '', '', '', '']
            rendered.append('\t'.join(values).encode('ascii'))
            records.append({'source_line': line_number, 'source_type': 'Circular' if circular else 'Linear',
                            'position_m': metre, 'kilometre_mark': km, 'gradient_per_mille': gradient or None,
                            'radius_m': radius or None})
        except (ValueError, OverflowError) as exc:
            raise ValueError(f'Bentley report line {line_number}: {exc}') from exc
        require(len(rendered) <= 1000, 'Bentley to IVT supports up to 1000 selected report rows')
    require(len(rendered) >= 2, 'Bentley continuous alignment requires two selected report rows')
    output = NATIVE_BENTLEY_IVT_HEADER.replace(b'\n', b'\r\n') + b'\r\n'.join(rendered) + b'\r\n'
    parsed = parse_ivt(output)
    require([int(row.position) for row in parsed] == [row['position_m'] for row in records],
            'Bentley IVT positions differ after reading the converted output')
    return output, {'source_format': 'Bentley Rail Track', 'orientation': orientation, 'selected_rows': records,
                    'ignored_rows': ignored, 'native_generated_speed_kmh': 200,
                    'original_conversion_function': '0x55432c' if orientation == 'vertical' else '0x5547f4'}
