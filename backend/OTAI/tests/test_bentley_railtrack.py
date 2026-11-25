"""Original Bentley report conversion and the editable native IVT import boundary."""

import pytest

from opentrack_ai.current_archive.infrastructure_bentley import convert_bentley
from opentrack_ai.current_archive.infrastructure_ivt import import_ivt, parse_ivt
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_gmodel_materialization import donors


def report(*rows):
    return ('\r\n'.join('\t'.join(row) for row in rows) + '\r\n').encode('ascii')


def horizontal(kind, chainage, radius=''):
    return [kind, 'sample', chainage, *([''] * 8), radius]


@pytest.mark.parametrize(('mode', 'raw', 'edges'), [
    ('horizontal', report(horizontal('Linear', '12+000.000 m'), horizontal('Circular', '12+350.500 m', '-812.25 m'),
                          horizontal('Linear', '12+750.000 m'), horizontal('Spiral', '12+900.000 m')),
     [[1, 351, 0, 0], [1, 399, -812.3, 0]]),
    ('vertical', report(['Linear', 'sample', '12+000.000 m', '', '1.125 %'],
                        ['Linear', 'sample', '12+350.500 m', '', '-2.125 %'],
                        ['Linear', 'sample', '12+750.000 m', '', '0'],
                        ['Circular', 'sample', '12+900.000 m', '', '3']),
     [[1, 351, 0, 1.13], [1, 399, 0, -2.13]]),
])
def test_original_bentley_text_fields_are_cold_readable_in_current_worksheet(mode, raw, edges):
    content, conversion = convert_bentley(raw, mode)
    assert b'Gradient [\x89]' in content.split(b'\r\n', 1)[0]
    assert conversion['ignored_rows'] == 1 and content.count(b'\r\n') == 4
    parsed = parse_ivt(content)
    assert [int(row.position) for row in parsed] == [12000, 12351, 12750]
    assert all(row.forward == row.reverse == (200, 200, 200, 200) for row in parsed)
    header, shapes = donors()
    worksheet, summary = import_ivt(content, header, shapes, None, [], 500)
    _, _, _, ids = native.document(worksheet)
    assert summary['native_readback_verified'] and summary['total_length_m'] == 750
    for saved, expected in zip(summary['edges'], edges, strict=True):
        assert ids[saved['edge_id']].contents[9].values[:4] == pytest.approx(expected)


def test_exact_original_header_allowance_preserves_ascii_boundaries():
    original, _ = convert_bentley(report(horizontal('Linear', '0'), horizontal('Linear', '350')), 'horizontal')
    with pytest.raises(ValueError, match='IVT uses ASCII'):
        parse_ivt(original.replace(b'Gradient', b'Unreviewed'))
    with pytest.raises(ValueError, match='IVT uses ASCII'):
        parse_ivt(original.replace(b'350', b'35\xff', 1))


@pytest.mark.parametrize(('raw', 'reason'), [
    (b'Linear\tshort\t25\nLinear\tshort\t50\n', 'missing original report columns'),
    (report(horizontal('Linear', 'x'), horizontal('Linear', '350')), 'Bentley chainage requires a bounded decimal'),
    (report(horizontal('Linear', '0'), horizontal('Circular', '350', 'none')), 'Bentley radius requires a bounded decimal'),
    (report(horizontal('Linear', '0'), horizontal('Spiral', '350')), 'requires two selected report rows'),
])
def test_bentley_converter_rejects_incomplete_supported_alignment(raw, reason):
    with pytest.raises(ValueError, match=reason):
        convert_bentley(raw, 'horizontal')
