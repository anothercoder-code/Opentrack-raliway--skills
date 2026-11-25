from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, writer
from opentrack_ai.current_archive.native_connections import record
from opentrack_ai.current_archive.operating_plan_edit import text
from opentrack_ai.current_archive.protim_pif_timetable import ImportProtimPIF, import_pif, parse_pif
from test_operating_plan_edit import sample


def pif(*rows):
    return ('\r\n'.join('\t'.join(row) for row in rows) + '\r\n').encode('ascii')


def move(origin, destination, departure, arrival, marker='0'):
    return 'TMV', '', '', origin, destination, '', departure, arrival, marker


HEADER = ('PIF', '1')
COURSE = ('THD', '', '', 'PIF804')
TRAILER = ('PIT', '')


def request(**overrides):
    return SimpleNamespace(**({'course_by_pif_id': {'PIF804': 'A01'}, 'station_by_pif_sign': {},
                               'endpoint_clocks': 'preserve', 'mirror_passage_arrivals_for_run': False,
                               'source_encoding': 'windows-1252'} | overrides))


def three_stations():
    plan = sample()
    plan.insert_timetable_row({'course_id': 'A01', 'index': 1, 'template_course_id': 'A01',
        'template_index': 1, 'station_sign': 'RDG', 'fields': {'arrival': '23:37:00', 'departure': '23:39:00',
        'arrival_day_offset': 0, 'departure_day_offset': 0, 'stop_at_station': True, 'dwell_s': 120,
        'timing_station': True, 'track_id': '9'}})
    return plan


def test_imports_extended_hours_stop_fields_and_preserves_flow_dependencies():
    plan = three_stations()
    source = pif(HEADER, ('LOC', 'station inventory supplemental'), COURSE, move('EA', 'PIF-RDG', '23:58', '24:02:10'),
                 ('TSP', '', '', 'PIF-RDG'), move('PIF-RDG', 'WB', '24:06:10', '24:11'), TRAILER)
    before = writer.fingerprint(plan.row('A02', 0))
    previous_link = record(catalogs.array(plan.row('A01', 0).contents[9].value)[0])
    evidence = import_pif(plan, *parse_pif(source), request(station_by_pif_sign={'PIF-RDG': 'RDG'}))
    plan.validate()
    rows = course_factories.timetable(writer.load(writer.dump_verified(plan.table))[0])
    first, middle, last = (rows[f'A01#{i}'] for i in range(3))
    assert (text(first, 6), text(first, 7), first.contents[10].value) == ('HH:MM:SS', '23:58:00', 2)
    assert (text(middle, 6), text(middle, 7), text(middle, 8), text(middle, 18)) == ('00:02:10', '00:06:10', '240', '9')
    assert middle.contents[15].values == [1, 1, 0, 0] and middle.contents[10].value == 3
    assert (text(last, 6), text(last, 7), last.contents[10].value) == ('00:11:00', 'HH:MM:SS', 3)
    assert evidence['source_record_counts'] == {'LOC': 1, 'THD': 1, 'TMV': 2, 'TSP': 1, 'PIT': 1}
    assert evidence['assembly']['PIF804']['visits'][1]['stop_marker_line'] == 5
    assert record(catalogs.array(first.contents[9].value)[0]) == previous_link
    assert writer.fingerprint(rows['A02#0']) == before


def test_explicit_clock_mirroring_keeps_pass_native_stop_false():
    plan = three_stations()
    source = pif(HEADER, COURSE, move('EA', 'RDG', '23:30', '23:35'), ('TSP', '', '', 'RDG'),
                 move('RDG', 'WB', '23:36', '23:40', marker='1'), TRAILER)
    evidence = import_pif(plan, *parse_pif(source), request(endpoint_clocks='mirror_for_run',
                                                          mirror_passage_arrivals_for_run=True))
    plan.validate()
    first, middle, last = evidence['assembly']['PIF804']['visits']
    assert first['mirrored_endpoint_clock'] == 'arrival' and last['mirrored_endpoint_clock'] == 'departure'
    assert middle['arrival'] == middle['departure'] == '23:36:00'
    assert middle['mirrored_passage_arrival'] and not middle['stop_at_station'] and middle['dwell_s'] == 0


def test_thd_closes_previous_course_and_pit_closes_final_course():
    source = pif(HEADER, COURSE, move('EA', 'WB', '23:40', '23:50'), ('THD', '', '', 'PIF805'),
                 move('WB', 'EA', '23:51', '23:55'), TRAILER)
    visits, _, _ = parse_pif(source)
    assert [(row.station, row.stop) for row in visits['PIF804']] == [('EA', False), ('WB', True)]
    assert [(row.station, row.stop) for row in visits['PIF805']] == [('WB', False), ('EA', True)]


def patterned_header(pattern, course='PIF804'):
    return 'THD', 'field2', 'field3', course, '', 'field5', 'field6', 'field7', pattern


def test_selects_one_of_two_same_id_week_patterns_by_native_positions():
    source = pif(HEADER, patterned_header('y?NYNNYtrailing'), move('EA', 'WB', '10:20', '10:30'),
                 patterned_header('NYYYYNN'), move('EA', 'WB', '11:20', '11:30'), TRAILER)
    first, counts, filter_report = parse_pif(source, thd_week_pattern='y')
    assert first['PIF804'][0].departure == 10 * 3600 + 20 * 60
    assert counts['THD'] == 2
    assert filter_report == {
        'requested_pattern': 'y', 'normalized_pattern': 'Y******', 'matched_variants': 1, 'excluded_variants': 1,
        'selected_headers': {'PIF804': {'source_thd_line': 2, 'source_thd_week_pattern': 'Y*NYNNY'}},
    }
    second, _, filter_report = parse_pif(source, thd_week_pattern='n*******Y')
    assert second['PIF804'][0].departure == 11 * 3600 + 20 * 60
    assert filter_report['normalized_pattern'] == 'N******'
    assert filter_report['selected_headers']['PIF804']['source_thd_line'] == 4
    with pytest.raises(ValueError, match='multiple THD variants'):
        parse_pif(source, thd_week_pattern='?')
    with pytest.raises(ValueError, match='Duplicate PIF Course'):
        parse_pif(source)


def test_distinguishes_excluded_unbound_and_requested_variants_and_isolates_stop_markers():
    source = pif(HEADER, patterned_header('NNNNNNN'), move('EA', 'RDG', '08:00', '08:05'),
                 ('TSP', '', '', 'RDG'), move('RDG', 'WB', '08:10', '08:15'),
                 patterned_header('YYYYYYY'), move('EA', 'RDG', '09:00', '09:05'),
                 move('RDG', 'WB', '09:10', '09:15'),
                 patterned_header('NNNNNNN', 'OTHER1'), move('EA', 'WB', '10:00', '10:10'), TRAILER)
    chosen, _, details = parse_pif(source, thd_week_pattern='Y', selected_sources={'PIF804'})
    assert not chosen['PIF804'][1].stop and chosen['PIF804'][1].stop_marker_line is None
    assert details['excluded_variants'] == 2
    with pytest.raises(ValueError, match='OTHER1.*no THD variant'):
        parse_pif(source, thd_week_pattern='Y', selected_sources={'OTHER1'})


@pytest.mark.parametrize(('header', 'error'), [
    (('THD', '', '', 'PIF804', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'YYYYYYY'), 'fourth-token'),
    (('THD', 'field2', 'field3', 'PIF804'), 'eighth token'),
    (patterned_header('YYN'), 'seven source'),
])
def test_filter_rejects_unverified_thd_layout_and_short_source_pattern(header, error):
    with pytest.raises(ValueError, match=error):
        parse_pif(pif(HEADER, header, move('EA', 'WB', '10:00', '10:10'), TRAILER), thd_week_pattern='Y')


def test_pif_request_rejects_absolute_date_as_week_pattern():
    field = ImportProtimPIF.model_fields['thd_week_pattern']
    from pydantic import TypeAdapter, ValidationError

    with pytest.raises(ValidationError):
        TypeAdapter(field.rebuild_annotation()).validate_python('2026-11-24')


@pytest.mark.parametrize(('rows', 'error'), [
    ([COURSE, move('EA', 'WB', '23:30', '23:31'), TRAILER], 'PIF header'),
    ([HEADER, COURSE, move('EA', 'WB', '23:50', '24:00'), TRAILER], '24:00 is ambiguous'),
    ([HEADER, COURSE, move('EA', 'WB', '23:50', '23:49'), TRAILER], 'arrives before'),
    ([HEADER, COURSE, move('EA', 'WB', '23:31', '23:35'), move('EA', 'RDG', '23:37', '23:42'), TRAILER], 'discontinuous'),
    ([HEADER, COURSE, move('EA', 'WB', '23:31', '23:35'), move('WB', 'RDG', '23:33', '23:42'), TRAILER], 'go backwards'),
    ([HEADER, COURSE, move('EA', 'WB', '23:30', '23:31')], 'closing PIT'),
    ([HEADER, COURSE, move('EA', 'WB', '23:50', '23:59'), ('XXX', ''), TRAILER], 'Unsupported Protim PIF record'),
])
def test_rejects_unverified_shapes_or_bad_clock_sequence(rows, error):
    with pytest.raises(ValueError, match=error):
        parse_pif(pif(*rows))
