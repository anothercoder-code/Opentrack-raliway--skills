from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import catalogs, course_factories as cf, writer
from opentrack_ai.current_archive.native_timetable_import_tools import CourseMapping, import_schedule
from opentrack_ai.current_archive.operating_plan_edit import text
from test_operating_plan_edit import sample


def request(source='A01', *, existing='replace', referenced=None, stations=None, actual=False):
    return SimpleNamespace(courses=[CourseMapping(source_course=source, target_course='A01')],
                           referenced_courses=referenced or {}, station_mapping=stations or {},
                           existing=existing, import_actual_times=actual)


def test_readback_rebinds_native_rows_and_keeps_unselected_schedule():
    donor, plan = sample(), sample()
    donor.rename_courses({'renames': [{'course_id': 'A01', 'new_id': 'DONOR'}, {'course_id': 'A02', 'new_id': 'OTHER'}]})
    entry = donor.row('DONOR', 0)
    conn, = catalogs.array(entry.contents[9].value)
    cf.settext(entry, 5, 'DONOR-EAST')
    cf.settext(conn, 2, 'DONOR-EAST')
    cf.settext(conn, 6, 'DONOR-EAST')
    cf.settext(entry, 13, '23:30:01')
    cf.settext(entry, 18, 'Platform 9')
    cf.put(entry, 17, -1.25)
    cf.settext(donor.row('OTHER', 1), 6, '23:51:00')
    untouched = writer.dump(plan.row('A02', 1))
    source = writer.dump(donor.table)

    result = import_schedule(plan, donor.table,
                             request('DONOR', referenced={'OTHER': 'A02'}, stations={'DONOR-EAST': 'EA'}))
    assert result['imported_rows'] == result['replaced_rows'] == 2
    plan.validate()
    rows = cf.timetable(writer.load_next_compatible(writer.dump_verified(plan.table))[0])
    entry = rows['A01#0']
    conn, = catalogs.array(entry.contents[9].value)
    assert [text(conn, slot) for slot in (0, 1, 2, 6)] == ['A01', 'A02', 'EA', 'EA']
    assert text(entry, 13) == 'HH:MM:SS'
    assert (text(entry, 18), entry.contents[17].value) == ('Platform 9', -1.25)
    assert writer.dump(rows['A02#1']) == untouched
    assert writer.dump(donor.table) == source


def test_explicit_replacement_and_referenced_course_binding():
    donor = sample().table
    with pytest.raises(ValueError, match='already has rows'):
        import_schedule(sample(), donor, request(existing='reject'))
    with pytest.raises(ValueError, match='requires an explicit binding'):
        import_schedule(sample(), donor, request())


def test_interval_cycle_with_untouched_target_course_is_rejected():
    donor = sample()
    row = donor.row('A01', 0)
    cf.settext(row, 2, 'A02')
    cf.put(row, 11, 30.0)
    with pytest.raises(ValueError, match='Cyclic or ambiguous native interval'):
        import_schedule(sample(), donor.table, request(referenced={'A02': 'A02'}))


def test_actual_clocks_and_day_offsets_are_optional():
    donor, target = sample(), sample()
    entry = donor.row('A01', 0)
    cf.settext(entry, 14, '00:00:01')
    entry.contents[15].values[3] = 1
    import_schedule(target, donor.table, request(referenced={'A02': 'A02'}, actual=True))
    saved = target.row('A01', 0)
    assert text(saved, 14) == '00:00:01'
    assert saved.contents[15].values[3] == 1
