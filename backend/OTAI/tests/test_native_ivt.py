"""IVT tabular inputs and current ordinary operating worksheet records."""

import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.course_factories import dictionary
from opentrack_ai.current_archive.infrastructure_ivt import import_ivt, parse_ivt
from opentrack_ai.current_archive.infrastructure_ivt_tools import ImportIVT, InfrastructureIVTTools, IVTPlatform
from opentrack_ai.current_archive.infrastructure_siemens import import_siemens
from opentrack_ai.current_archive.infrastructure_sbb_zlr import import_sbb_zlr, parse_sbb_zlr
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native, topology
from opentrack_ai.current_archive.zero_operations.station_binding import bind_stations
from opentrack_ai.errors import APIError

from test_gmodel_materialization import donors


def line_rows():
    return [
        ['0', 'West A', 'West D', '12.0', '12.01', '85', '90', '95', '0', '', '', '', '', '2,5', '800', '',
         'Main Signal exit', '', 'West'],
        ['350', 'Entry A', 'Entry D', '12.35', '12.36', '80', '85', '90', '95', '81', '86', '91', '96', '-1',
         '900', 'Tunnel single, smooth', '', '', ''],
        ['650', 'Platform A', 'Platform D', '12.65', '12.66', '82', '87', '92', '97', '79', '84', '89', '94',
         '0', '0', '2,7', 'Main Signal exit', '', 'Main Platform'],
        ['800', 'Tail A', 'Tail D', '', '', '', '', '', '', '76', '81', '86', '91', '', '', '', '', 'Distant 2 aspects', ''],
    ]


def tsv(rows):
    return ('\r\n'.join('\t'.join(row) for row in rows) + '\r\n').encode('ascii')


def catalog(header, shapes):
    base, result = topology.generate_network(header, shapes, generate.spec())
    bindings = [dict(sign=sign, name=name, end_ids=[result['vertex_end_ids'][side][0]], placement=generate.placement(10, 10),
                     station_type_raw=2, interlock_type_raw=4, icon_show_type_raw=1, timing_point=False)
                for sign, name, side in [('West', 'West Junction', 'left'), ('P', 'Main Platform', 'right')]]
    return bind_stations(base, bindings)[1]


def test_ivt_applies_independent_direction_speeds_and_records_native_station_area():
    header, shapes = donors()
    supplied = catalog(header, shapes)
    area = IVTPlatform(station_sign='P', direction='ascending', entry_position_m='350')
    document, report = import_ivt(tsv(line_rows()), header, shapes, supplied, [area], 500)
    root, _, models, records = native.document(document)
    assert report['native_readback_verified'] and report['total_length_m'] == 800
    assert [item['length_m'] for item in report['edges']] == [350, 300, 150]
    assert [item['tunnel_type_raw'] for item in report['edges']] == [1, 2, 10027]
    a, b, c = [records[item['edge_id']] for item in report['edges']]
    assert a.contents[9].values[:4] == [1, 350, 800, 2.5]
    assert b.contents[9].values[:4] == [2, 300, 900, -1]
    velocities = dictionary(a.contents[16].value)
    assert [tuple(velocities[str(v)].contents[i].value for i in (1, 2)) for v in range(4)] == [
        (85, 81), (90, 86), (95, 91), (0, 96)]
    old, ref = [records[i] for i in (report['stations'][1]['entry_end_id'], report['stations'][1]['reference_end_ids'][0])]
    assert old.contents[12].value is ref.contents[12].value
    assert (old.contents[20].value, ref.contents[20].value) == (1, 2)
    assert catalogs.text(ref.contents[12].value.contents[7].value) == 'P'
    marks = report['vertices']
    assert writer.string(records[marks[2]['descending_end_id']].contents[18].value) == 'Platform D'
    assert records[marks[2]['ascending_end_id']].contents[14].value == topology.flt(12.65, 'kilometre')
    assert records[marks[2]['descending_end_id']].contents[14].value == topology.flt(12.66, 'kilometre')
    assert records[marks[3]['ascending_end_id']].contents[14].value == -99999.0
    distant = records[marks[3]['descending_end_id']].contents[11].value
    assert distant.contents[8].values[0] == 27
    assert native.validate_topology(root)[0] == models


def test_ivt_binds_multiple_station_reference_pairs_in_point_only_mode():
    header, shapes = donors()
    rows = line_rows()
    rows[1][-1] = 'P'
    document, report = import_ivt(tsv(rows), header, shapes, catalog(header, shapes), [], 500)
    refs = report['stations'][1]['reference_end_ids']
    _, _, _, models = native.document(document)
    assert len(refs) == 2 and models[refs[0]].contents[12].value is models[refs[1]].contents[12].value
    assert all(models[ident].contents[20].value == 2 for ident in refs)


def test_ivt_descending_area_uses_the_opposite_ends_of_the_same_edge():
    header, shapes = donors()
    rows = line_rows()
    rows[2][16], rows[2][18] = '', ''
    rows[1][17], rows[1][18] = 'Main Signal exit', 'P'
    area = IVTPlatform(station_sign='P', direction='descending', entry_position_m='650')
    document, report = import_ivt(tsv(rows), header, shapes, catalog(header, shapes), [area], 500)
    station = report['stations'][1]
    assert station['entry_end_id'] == report['vertices'][2]['descending_end_id']
    assert station['reference_end_ids'] == [report['vertices'][1]['descending_end_id']]
    _, _, _, records = native.document(document)
    exit_signal = records[station['reference_end_ids'][0]].contents[11].value
    assert exit_signal.contents[8].values[:2] == [1, 4]


@pytest.mark.parametrize(('row', 'col', 'value', 'error'), [
    (1, 0, '0', 'increasing positions'), (1, 0, '350.5', 'whole-metre native length'),
    (1, 9, '', 'require all four speeds'), (0, 5, '85.5', 'speed requires an integer'),
    (1, 15, 'Tunnel thin', 'tunnel factor or named native profile'), (1, 15, '7.5', 'exact native tenth'),
    (1, 17, 'Main Virtual Signal', 'Unsupported IVT signal label'),
    (1, 18, 'Unknown', 'unknown or ambiguous in the catalog'),
], ids=['duplicate-position', 'submetre-length', 'missing-directional-speed', 'fractional-speed', 'unknown-tunnel',
        'unrepresentable-tunnel-factor', 'unreviewed-signal', 'unmapped-station'])
def test_ivt_rejects_ambiguous_or_unrepresentable_records(row, col, value, error):
    header, shapes = donors()
    rows = line_rows()
    rows[row][col] = value
    with pytest.raises(ValueError, match=error):
        import_ivt(tsv(rows), header, shapes, catalog(header, shapes), [], 500)


def test_ivt_rejects_bad_tsv_and_accepts_optional_trailing_fields():
    rows = line_rows()
    rows[1] = rows[1][:15]
    assert len(parse_ivt(b'// IVT exchange\r\n' + tsv(rows))) == 4
    with pytest.raises(ValueError, match='19 tab fields'):
        parse_ivt(b'1,2,3\n4,5,6\n')
    with pytest.raises(ValueError, match='ASCII tab-separated'):
        parse_ivt(b'\xff\n')


def test_ivt_publication_preserves_station_catalog_hash_and_repeats_preview(tmp_path):
    header, shapes = donors()
    source = tsv(line_rows())
    station_catalog = catalog(header, shapes)
    work = tmp_path / 'OTAI/workspaces/IVT'
    work.mkdir(parents=True)

    def put(name, raw):
        path = work / name
        path.write_bytes(raw)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(raw)}

    args = dict(source=put('input.ivt', source), header_document=put('Header', header), shapes=put('Shapes', shapes),
                stations_catalog=put('StationData.stations', station_catalog))
    tool = InfrastructureIVTTools(tmp_path)
    preview = tool.import_line(ImportIVT(**args))
    assert not (work/'Output').exists() and preview['source_catalog_preserved']
    if not tmp_path.as_posix().isascii():
        pytest.skip('Windows candidate publishing requires an ASCII --basetemp')
    output_path = (work/'Output').relative_to(tmp_path).as_posix()
    result = tool.import_line(ImportIVT(**args, preview_only=False, target_directory=output_path))
    assert result['saved'] and result['publication']['post_commit_verified'] and result['members'] == preview['members']
    assert (work/'Output/IVTStationCatalog.stations').read_bytes() == station_catalog
    with pytest.raises(APIError, match='Target directory exists'):
        tool.import_line(ImportIVT(**args, preview_only=False, target_directory=output_path))


SBB_LIMITS = [(75, 76), (91, 92), (100, 97), (101, 99)]


def sbb_rows():
    return [
        ['A', '12:340', '10:000', '2.5', '900', '1', '120', '80', '95', '', 'Source title A', 'West'],
        ['B', '12.640', '10.250', '-4.25', '-600', '45', '', '', '100', '', 'Ignored title', ''],
        ['C', '9.900', '10.5005', '', '', '45.125', '', '', '', '', 'Source title C', 'P'],
        ['D', '', '10.7755'],
    ]


def test_sbb_zlr_writes_native_speed_slots_lengths_tunnels_and_station_signs():
    header, shapes = donors()
    supplied = catalog(header, shapes)
    data = tsv(sbb_rows())
    document, report = import_sbb_zlr(data, header, shapes, supplied, SBB_LIMITS)
    _, _, _, records = native.document(document)
    assert report['original_import_format'] == 1 and report['total_length_m'] == 776
    edges = [records[segment['edge_id']] for segment in report['edges']]
    assert [edge.contents[9].values[:4] for edge in edges] == [
        [1, 250, 900, 2.5], [2, 251, -600, -4.25], [3, 275, -600, -4.25],
    ]
    velocities = [dictionary(edge.contents[16].value) for edge in edges]
    assert [[tuple(table[str(v)].contents[i].value for i in (1, 2)) for v in range(4)] for table in velocities] == [
        [(80, 80), (95, 95), (100, 97), (120, 120)],
        [(80, 80), (100, 100), (100, 97), (120, 120)],
        [(80, 80), (100, 100), (100, 97), (120, 120)],
    ]
    for vertex, km in zip(report['vertices'], [12.340, 12.64, 9.9, -99999], strict=True):
        pair = [records[vertex[key]] for key in ('ascending_end_id', 'descending_end_id')]
        assert all(row.contents[14].value == topology.flt(km, 'kilometre mark') for row in pair)
    assert [(item['sign'], item['name']) for item in report['stations']] == [('West', 'West Junction'), ('P', 'Main Platform')]
    assert [item['station_name_column_11'] for item in report['source_annotations']] == [
        'Source title A', 'Ignored title', 'Source title C', '',
    ]


@pytest.mark.parametrize(('column', 'input_value', 'message'), [
    (2, '10.000', 'strictly increase'), (2, '10.0002', 'positive native metre length'),
    (3, '2,25', 'decimal with a period'), (5, '-1', 'nonnegative'),
    (7, '130.5', 'integer'), (9, 'H123', 'separately validated native signal profile'),
])
def test_sbb_zlr_rejects_unreviewed_or_unrepresentable_rows(column, input_value, message):
    rows = sbb_rows()
    rows[1][column] = input_value
    with pytest.raises(ValueError, match=message):
        parse_sbb_zlr(tsv(rows), SBB_LIMITS)


def test_sbb_zlr_terminal_station_requires_exact_sign_instead_of_station_name():
    rows = sbb_rows()
    rows[0][11] = 'West Junction'
    header, shapes = donors()
    with pytest.raises(ValueError, match='unknown or ambiguous'):
        import_sbb_zlr(tsv(rows), header, shapes, catalog(header, shapes), SBB_LIMITS)


def sbb_signal_template(header, shapes):
    data, plan = topology.generate_network(header, shapes, generate.spec())
    root, stream, models, ids = native.document(data)
    end = ids[plan['vertex_end_ids']['left'][0]]
    ident = max(ids) + 1
    signal = native.signal_model(end, name='', model_id=ident,
        placement=generate.signal_placement(end, float(end.contents[2].value), float(end.contents[3].value)),
        sight_m=475, delay_s=1.25, show_symbol=False, show_icon=True, signal_type=2, main_type=2, virtual=False)
    signal.contents[8].values[2] = 1
    signal.contents[11].value = -1
    end.contents[11].value = signal
    writer.set_elements(root.contents[2].value, [*models, signal])
    return writer.dump_verified(root, stream), ident


@pytest.mark.parametrize('pair', [('Hpair', 'Vpair'), ('Vpair', 'Hpair')])
def test_sbb_zlr_writes_h_v_and_one_combined_on_the_arrival_end(pair):
    header, shapes = donors()
    template, ident = sbb_signal_template(header, shapes)
    rows = sbb_rows()
    rows[0][9], rows[1][9], rows[2][9] = 'Hwest', 'Vmiddle', pair[0]
    rows.insert(3, [*rows[2][:9], pair[1], 'Retained display', rows[2][11]])
    document, report = import_sbb_zlr(tsv(rows), header, shapes, catalog(header, shapes), SBB_LIMITS, ident, template)
    assert [signal['type_raw'] for signal in report['signals']] == [1, 3, 2]
    assert report['signals'][2]['source_designations'] == list(pair)
    assert report['signals'][2]['source_lines'] == [3, 4]
    assert len(report['vertices']) == 4 and report['total_length_m'] == 776
    root, _, models, ids = native.document(document)
    assert native.validate_topology(root)[0] == models
    for vertex, signal in zip(report['vertices'][:3], report['signals'], strict=True):
        model = ids[signal['signal_id']]
        arrival, reverse = (ids[vertex[field]] for field in ('ascending_end_id', 'descending_end_id'))
        assert reverse.contents[11].value is None and arrival.contents[11].value is model
        assert model.contents[8].values == [signal['type_raw'], 2, 1]
        assert model.contents[9].values == [2, 475, 640, 0]
        assert [model.contents[key].value for key in (11, 12, 16)] == [-1, 7, 1.25]


@pytest.mark.parametrize(('field', 'value', 'message'), [
    (9, 'Hrepeated', 'complementary H/V pair'),
    (1, '12.650', 'identical explicit kilometre marks'),
    (9, 'G', 'begin with original H or V'),
])
def test_sbb_zlr_rejects_ambiguous_colocated_signal_rows(field, value, message):
    rows = sbb_rows()
    rows[1][9] = 'Hfirst'
    repeated = [*rows[1][:9], 'Vsecond', '', '']
    repeated[field] = value
    rows.insert(2, repeated)
    with pytest.raises(ValueError, match=message):
        parse_sbb_zlr(tsv(rows), SBB_LIMITS, signal_template_supplied=True)


def test_siemens_materializes_original_symmetric_speed_and_preference_defaults():
    header, shapes = donors()
    source = tsv([
        ['0', '', '2,5', '800', '0', 'West Junction'],
        ['350', '75', '', '', '2', 'Start Station', '10:03:00', 'text only'],
        ['650', '', '-2.5', '1200', '0', 'Main Platform'],
        ['800', '', '', '', ''],
    ])
    defaults = [[80, 83], [95, 91], [100, 97], [110, 105]]
    output, report = import_siemens(source, header, shapes, catalog(header, shapes), defaults)
    _, _, _, records = native.document(output)
    assert [row['sign'] for row in report['stations']] == ['West', 'P']
    assert [row['tunnel_type_raw'] for row in report['edges']] == [1, 3, 1]
    assert [row['gradient_per_mille'] for row in report['edges']] == [2.5, 2.5, -2.5]
    assert report['source_annotations'] == [{'source_line': 2, 'time': '10:03:00', 'remark': 'text only'}]
    for row, first in zip(report['edges'], [(80, 83), (75, 75), (75, 75)]):
        speeds = dictionary(records[row['edge_id']].contents[16].value)
        assert [tuple(speeds[str(idx)].contents[i].value for i in (1, 2)) for idx in range(4)] == [
            first, (95, 91), (100, 97), (110, 105)]
