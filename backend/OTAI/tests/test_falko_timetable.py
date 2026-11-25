from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, writer
from opentrack_ai.current_archive.falko_timetable import import_falko, parse_falko
from opentrack_ai.current_archive.native_connections import record
from opentrack_ai.current_archive.operating_plan_edit import text
from opentrack_ai.current_archive.zero_generation.native_signal_routes import string
from test_operating_plan_edit import sample


def line(course, station, arrival, departure, target='-'):
    return f'{course} 0 0 0 {station} 0 0 0 0 {arrival} {departure} {target}\r\n'.encode('ascii')


def options(**overrides):
    return SimpleNamespace(**({'course_by_falko_id': {'FALK01': 'A01'}, 'station_by_falko_type': {},
                              'connections': 'require_matching', 'endpoint_clocks': 'preserve'} | overrides))


def test_parser_updates_original_dwell_flags_clock_days_and_preserves_native_records():
    plan = sample()
    plan.stations['EA'].contents[6].value = string('External-West')
    source = b'Header of Falko\r\n' + line('FALK01', 'external-west', '-1.0', '86350.0')
    source += line('FALK01', 'External-East', 86461, 86581, '#---')
    choices = options(station_by_falko_type={'External-East': 'WB'})
    existing = writer.fingerprint(plan.row('A02', 0))
    link, = catalogs.array(plan.row('A01', 0).contents[9].value)
    linked = record(link)
    plan.row('A01', 1).contents[18].value = string('7')
    report = import_falko(plan, *parse_falko(source), choices)
    plan.validate()
    reopened = course_factories.timetable(writer.load(writer.dump_verified(plan.table))[0])
    first, second = reopened['A01#0'], reopened['A01#1']
    assert report['imported_rows'] == 2 and report['source_three_column_headers'] == 1
    assert (text(first, 6), text(first, 7), first.contents[10].value) == ('HH:MM:SS', '23:59:10', 2)
    assert (text(second, 6), text(second, 7), text(second, 8)) == ('00:01:01', '00:03:01', '120')
    assert second.contents[15].values == [1, 1, 0, 0] and second.contents[10].value == 3
    assert text(second, 18) == '7' and writer.fingerprint(reopened['A02#0']) == existing
    assert record(catalogs.array(first.contents[9].value)[0]) == linked


def test_add_ordinary_transfer_by_existing_visit_then_require_exact_match():
    plan = sample()
    source = line('FALK01', 'EA', -1, 86400) + line('FALK01', 'WB', 87000, 87000, 'A02')
    args = options(connections='add_transfer')
    first = import_falko(plan, *parse_falko(source), args)
    plan.validate()
    assert first['assembly']['FALK01']['visits'][1]['connection']['action'] == 'added'
    reopened = course_factories.timetable(writer.load(writer.dump_verified(plan.table))[0])
    link, = catalogs.array(reopened['A01#1'].contents[9].value)
    assert record(link) == {'course_id': 'A01', 'target_course_id': 'A02', 'station_sign': 'WB',
        'target_station_sign': 'WB', 'minimum_wait': '00:00:00', 'maximum_wait': 'HH:MM:SS',
        'flags': 0, 'time_reference_type': 0, 'dispatching_distance_km': 0.0}
    again = import_falko(plan, *parse_falko(source), options())
    assert again['assembly']['FALK01']['visits'][1]['connection']['action'] == 'matched'


def test_explicit_endpoint_mirroring_retains_source_stop_semantics():
    plan = sample()
    source = line('FALK01', 'EA', -1, 86350) + line('FALK01', 'WB', 86461, -1)
    evidence = import_falko(plan, *parse_falko(source), options(endpoint_clocks='mirror_for_run'))
    plan.validate()
    first, second = plan.rows()['A01#0'], plan.rows()['A01#1']
    assert text(first, 6) == text(first, 7) == '23:59:10' and first.contents[10].value == 2
    assert text(second, 6) == text(second, 7) == '00:01:01' and second.contents[10].value == 3
    assert second.contents[15].values == [1, 1, 0, 0]
    visits = evidence['assembly']['FALK01']['visits']
    assert [visit['mirrored_endpoint_clock'] for visit in visits] == ['arrival', 'departure']


@pytest.mark.parametrize(('source', 'error'), [
    (line('FALK01', 'EA', 0.5, 100), 'whole elapsed second'),
    (line('FALK01', 'EA', 900, 100), 'Invalid Falko dwell'),
    (line('FALK01', 'EA', -1, -1), 'has no clock'),
    (line('FALK01', 'EA', 0, 100).replace(b' 0 ', b'\t0 ', 1), 'printable ASCII'),
    (line('FALK01', 'EA', 0, 100) + line('OTHER', 'EA', 0, 100) + line('FALK01', 'WB', 100, 100), 'Noncontiguous'),
])
def test_rejects_unsupported_or_lossy_falko_rows(source, error):
    with pytest.raises(ValueError, match=error):
        parse_falko(source)


def test_rejects_split_creation_interval_override_and_ambiguous_station_types():
    plan = sample()
    split = line('FALK01', 'EA', -1, 80000) + line('FALK01', 'WB', 82000, -1, 'A02')
    with pytest.raises(ValueError, match='native record'):
        import_falko(plan, *parse_falko(split), options(connections='add_transfer'))
    plan = sample()
    with pytest.raises(ValueError, match='interval reference'):
        import_falko(plan, *parse_falko(split), options(course_by_falko_id={'FALK01': 'A02'}))
    plan = sample()
    for station in list(plan.stations.values())[:2]:
        station.contents[6].value = string('External')
    ambiguous = line('FALK01', 'External', -1, 80000) + line('FALK01', 'WB', 82000, -1)
    with pytest.raises(ValueError, match='Ambiguous native station type'):
        import_falko(plan, *parse_falko(ambiguous), options())
