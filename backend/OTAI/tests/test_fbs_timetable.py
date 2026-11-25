from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, writer
from opentrack_ai.current_archive.fbs_timetable import import_fbs, parse_fbs
from opentrack_ai.current_archive.native_connections import record
from opentrack_ai.current_archive.operating_plan_edit import text
from opentrack_ai.current_archive.zero_generation.native_signal_routes import string
from test_operating_plan_edit import sample


def matrix(*rows):
    return ('\r\n'.join('\t'.join(row) for row in rows) + '\r\n').encode('cp1252')


def options(**overrides):
    return SimpleNamespace(**({'course_by_fbs_id': {'F804': 'A01'}, 'station_by_fbs_name': {},
                               'source_encoding': 'windows-1252', 'endpoint_clocks': 'preserve'} | overrides))


def test_native_matrix_stop_pass_clock_dwell_and_original_connection_preserved():
    plan = sample()
    plan.stations['EA'].contents[2].value = string('Dürfen')
    plan.row('A01', 1).contents[18].value = string('2')
    source = matrix(('Station', 'Type', 'F804', 'F805'),
                    ('dürfen', 'an', '|', ''),
                    ('', 'ab', '(23.29,5)', ''),
                    ('West Alias', 'an/ab', '23:42:31/23:45,5', '23:47'),
                    (), ('Richtung West',), ('Malformed second direction', 'ab', '25:00'))
    prior_other = writer.fingerprint(plan.row('A02', 0))
    prior_link = record(catalogs.array(plan.row('A01', 0).contents[9].value)[0])
    args = options(station_by_fbs_name={'West Alias': 'WB'})
    result = import_fbs(plan, *parse_fbs(source), args)
    plan.validate()
    restored = course_factories.timetable(writer.load(writer.dump_verified(plan.table))[0])
    start, end = restored['A01#0'], restored['A01#1']
    assert (text(start, 6), text(start, 7), start.contents[10].value) == ('HH:MM:SS', '23:29:30', 2)
    assert (text(end, 6), text(end, 7), text(end, 8)) == ('23:42:31', '23:45:30', '179')
    assert end.contents[10].value == 3 and text(end, 18) == '2'
    assert record(catalogs.array(start.contents[9].value)[0]) == prior_link
    assert writer.fingerprint(restored['A02#0']) == prior_other
    assert result['next_direction_line'] == 6 and result['source_services'] == 2
    assert result['assembly']['F804']['visits'][0]['source_lines'] == [2, 3]


def test_combined_single_pass_and_explicit_endpoint_clock_policy():
    plan = sample()
    source = matrix(('Station', 'Type', 'F804'), ('EA', 'an/ab', '(2330)'), ('WB', 'an', '234530'))
    result = import_fbs(plan, *parse_fbs(source), options(endpoint_clocks='mirror_for_run'))
    plan.validate()
    start, end = result['assembly']['F804']['visits']
    assert start['mirrored_endpoint_clock'] == 'arrival' and not start['stop_at_station']
    assert end['mirrored_endpoint_clock'] == 'departure' and end['stop_at_station']
    assert start['arrival'] == start['departure'] == '23:30:00'
    assert end['arrival'] == end['departure'] == '23:45:30'


@pytest.mark.parametrize(('rows', 'error'), [
    ([('Station', 'Type', 'F804', 'F804'), ('EA', 'an', '23:30')], 'distinct nonempty'),
    ([('Station', 'Type', 'F804'), ('EA', 'an', '23:30', '23:31')], 'more cells'),
    ([('Station', 'Type', 'F804'), ('', 'an', '23:30')], 'no preceding Station'),
    ([('Station', 'Type', 'F804'), ('EA', '?', '23:30')], 'requires an/ab'),
    ([('Station', 'Type', 'F804'), ('EA', 'an', '24:30')], 'within one day'),
    ([('Station', 'Type', 'F804'), ('EA', 'ab', '23:30,12')], 'one tenth digit'),
    ([('Station', 'Type', 'F804'), ('EA', 'ab', '23:30/23:31')], 'Unexpected FBS slash'),
])
def test_rejects_unverified_matrix_shapes(rows, error):
    with pytest.raises(ValueError, match=error):
        parse_fbs(matrix(*rows))


def test_rejects_ambiguous_names_and_wrong_service_order():
    source = matrix(('Station', 'Type', 'F804'), ('Same', 'ab', '23:31'), ('WB', 'an', '23:40'))
    plan = sample()
    for sign in ('EA', 'WB'):
        plan.stations[sign].contents[2].value = string('Same')
    with pytest.raises(ValueError, match='Ambiguous native Station name'):
        import_fbs(plan, *parse_fbs(source), options())
    plan = sample()
    with pytest.raises(ValueError, match='does not match native'):
        import_fbs(plan, *parse_fbs(source), options(station_by_fbs_name={'Same': 'RDG'}))
