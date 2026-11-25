from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, writer
from opentrack_ai.current_archive.native_connections import record
from opentrack_ai.current_archive.operating_plan_edit import text
from opentrack_ai.current_archive.simu_vii_timetable import import_simu, parse_simu
from test_protim_pif_timetable import three_stations


def source(*records):
    return ('\r\n'.join(records) + '\r\n').encode('ascii')


def options(**overrides):
    return SimpleNamespace(**({'course_by_simu_id': {'SIM801': 'A01'}, 'station_by_simu_sign': {'RDG H1': 'RDG'},
                               'endpoint_clocks': 'preserve', 'derive_arrivals_for_run': False} | overrides))


def archived(text_data, **updates):
    plan = three_stations()
    prior = writer.fingerprint(plan.row('A02', 0))
    prior_link = record(catalogs.array(plan.row('A01', 0).contents[9].value)[0])
    proof = import_simu(plan, *parse_simu(text_data), options(**updates))
    plan.validate()
    rows = course_factories.timetable(writer.load(writer.dump_verified(plan.table))[0])
    assert prior == writer.fingerprint(rows['A02#0'])
    assert prior_link == record(catalogs.array(rows['A01#0'].contents[9].value)[0])
    return rows, proof['assembly']['SIM801']['visits']


def test_native_durations_explicit_stop_first_station_and_suffixed_station():
    table = source('FAHRPLAN EXAMPLE', 'ZUG', 'SIM801', 'EA B23:30:00 15',
                   'RDG H1 120 x 180', '99999', 'WB 1 x 900', 'END')
    rows, receipt = archived(table)
    first, middle, last = (rows[f'A01#{i}'] for i in range(3))
    assert (text(first, 6), text(first, 7), text(first, 8), first.contents[10].value) == (
        '23:29:45', '23:30:00', '0', 3)
    assert (text(middle, 6), text(middle, 7), text(middle, 8), text(middle, 18)) == ('HH:MM:SS', '23:35:00', '120', '9')
    assert (text(last, 6), text(last, 7), text(last, 8)) == ('HH:MM:SS', '23:50:01', '1')
    assert receipt[1]['source_running_time_s'] == 180 and receipt[0]['source_dwell_s'] == 15


def test_proved_clocks_for_run_keep_dwell_time_and_pass_status():
    table = source('FAHRPLAN', 'BEDINGUNG', 'SIM801', 'EA B 23:30:00 0',
                   'RDG H1 120 x 180', 'WB 0 900', 'END')
    rows, receipt = archived(table, endpoint_clocks='mirror_for_run', derive_arrivals_for_run=True)
    assert receipt[0]['mirrored_endpoint_clock'] == 'arrival'
    assert all(item['derived_arrival_for_run'] for item in receipt[1:])
    middle, final = rows['A01#1'], rows['A01#2']
    assert (text(middle, 6), text(middle, 7), text(middle, 8)) == ('23:33:00', '23:35:00', '120')
    assert text(final, 6) == text(final, 7) == '23:50:00' and final.contents[10].value == 2


@pytest.mark.parametrize(('rows', 'error'), [
    (('OTHER', 'END'), 'FAHRPLAN header'),
    (('FAHRPLAN', 'ZUG', 'END'), 'following Course'),
    (('FAHRPLAN', 'ZUG', 'SIM801', 'EA 23:59:00 0', 'WB 0 60', 'END'), 'single day'),
    (('FAHRPLAN', 'ZUG', 'SIM801', 'EA 23:30:00 0', 'WB 120 60', 'END'), 'intervening field'),
    (('FAHRPLAN', 'ZUG', 'SIM801', 'EA 23:30:00 0', 'WB 0 0', 'END'), 'must be positive'),
    (('FAHRPLAN', 'ZUG', 'SIM801', 'EA 23:30:00 1.5', 'WB 0 60', 'END'), 'integer SIMU VII'),
    (('FAHRPLAN', 'ZUG', 'SIM801', 'EA 23:30:00 0', 'WB 0 60', 'ZUG', 'SIM801'), 'Duplicate'),
])
def test_rejects_unsafe_or_incomplete_input(rows, error):
    with pytest.raises(ValueError, match=error):
        parse_simu(source(*rows))
