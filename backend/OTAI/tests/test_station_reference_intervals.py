"""Check the native timetable fields and closure used by endpoint interval review."""

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, writer
from opentrack_ai.current_archive.multi_document.core import sha
from opentrack_ai.current_archive.saved_platform_resize import _operating_data
from opentrack_ai.current_archive.station_reference_intervals import review_saved_intervals

from test_itinerary_lifecycle import course_archive
from test_native_rolling_stock_import import stock
from test_operating_plan_edit import dictionary, native_record, row


def inputs(*, altered=None):
    courses, version = writer.load_next_compatible(course_archive(Root=['I Shared'], First=['I Shared'],
                                                                    Second=['I Shared'], Other=['I Different']))
    by_id = {catalogs.text(obj.contents[0].value): obj for obj in catalogs.course_items(courses)}
    for key, obj in by_id.items():
        course_factories.settext(obj, 3, 'Passenger')
        course_factories.settext(obj, 4, 'Passenger')
        obj.contents[5].value = int(key != 'Second')
    rows = {}
    for cid, origin, terminal, arrival_day, reference, offset in (
        ('Root', '23:50:00', '23:57:00', 0, '0', 0),
        ('First', '00:00:00', '00:07:00', 1, 'Root', 600),
        ('Second', '00:10:00', '00:17:00', 1, 'Root', 1200),
        ('Other', '23:40:00', '23:47:00', 0, '0', 0),
    ):
        for index, (station, time) in enumerate(zip(('A', 'B'), (origin, terminal), strict=True)):
            item = row(cid, station, index, time, reference=reference, offset=offset)
            item.contents[15].values[:2] = [arrival_day, arrival_day]
            rows[f'{cid}#{index}'] = item
    if altered is not None:
        altered(rows, by_id)
    depot, trains = stock(120)
    stations = dictionary({name: native_record('OTStation', *catalogs.LAYOUTS['OTStation'],
                                                {1: [course_factories.string(rows['Root#0'], name)]})
                           for name in ('A', 'B')})
    banks = {'courses': writer.dump_verified(courses, version), 'timetable': writer.dump_verified(dictionary(rows)),
             'depot': writer.dump_verified(depot), 'trains': writer.dump_verified(trains),
             'stations': writer.dump_verified(stations)}
    run = (b'Start Day Offset#0#\nStart Time#23:30:00#\nStop Day Offset#1#\n'
           b'Stop Time#00:30:00#\nStep#0.2#\nTrainType#Passenger#\n')
    return banks, run


def test_reviews_direct_siblings_with_absolute_clocks_across_midnight():
    banks, run = inputs()
    receipts, rows = review_saved_intervals(banks, {'Root', 'First'})
    assert rows == {('First', 0), ('First', 1), ('Second', 0), ('Second', 1)}
    assert receipts['Root'] == {
        'reference_course_id': None, 'offset_s': 0, 'family_course_ids': ['Root', 'First', 'Second'],
        'ordered_station_signs': ['A', 'B'], 'timetable_sha256': sha(banks['timetable']),
    }
    assert [(receipts[cid]['reference_course_id'], receipts[cid]['offset_s'])
            for cid in ('First', 'Second')] == [('Root', 600), ('Root', 1200)]
    with pytest.raises(ValueError, match='uses a native interval timetable reference'):
        _operating_data(banks, run, {'I Shared'})
    operating, _, _ = _operating_data(banks, run, {'I Shared'}, verified_interval_rows=rows)
    assert set(operating) == {'Root', 'First'}
    assert operating['First'][3][0]['arrival_s'] - operating['Root'][3][0]['arrival_s'] == 600


def test_reviews_nested_family_from_a_leaf_and_keeps_each_direct_offset():
    def altered(rows, courses):
        for index in (0, 1):
            item = rows[f'Second#{index}']
            course_factories.settext(item, 2, 'First')
            item.contents[11].value = 600
        courses['Second'].contents[5].value = 1

    banks, run = inputs(altered=altered)
    source_bytes = banks.copy()
    receipts, rows = review_saved_intervals(banks, {'Second', 'Root', 'First'})
    assert receipts['Second'] == {
        'reference_course_id': 'First', 'offset_s': 600,
        'root_reference_course_id': 'Root', 'root_offset_s': 1200,
        'family_course_ids': ['Root', 'First', 'Second'], 'ordered_station_signs': ['A', 'B'],
        'timetable_sha256': sha(banks['timetable']),
    }
    operating, _, _ = _operating_data(banks, run, {'I Shared'}, verified_interval_rows=rows)
    assert operating['Second'][3][0]['arrival_s'] - operating['First'][3][0]['arrival_s'] == 600
    assert operating['Second'][3][1]['departure_s'] - operating['Root'][3][1]['departure_s'] == 1200
    with pytest.raises(ValueError, match='review of every enabled'):
        review_saved_intervals(banks, {'Second'})
    assert banks == source_bytes


@pytest.mark.parametrize(('case', 'message'), (
    ('nested_bad_itinerary', 'one shared rebound Itinerary'), ('unreviewed', 'review of every enabled'),
    ('station', 'reference Stations or their order'), ('offset', 'one whole-second offset'),
    ('partial', 'a single direct timetable reference'), ('clock', 'inconsistent with the direct interval offset'),
    ('different_itinerary', 'one shared rebound Itinerary'),
    ('cycle', 'no reference cycle'), ('missing', 'missing Course or timetable'), ('root_offset', 'needs a zero offset'),
))
def test_rejects_ambiguous_or_inconsistent_intervals(case, message):
    def altered(rows, courses):
        if case == 'nested_bad_itinerary':
            for index in (0, 1):
                course_factories.settext(rows[f'Other#{index}'], 2, 'First')
        elif case == 'unreviewed':
            courses['Second'].contents[5].value = 1
        elif case == 'station':
            course_factories.settext(rows['First#1'], 5, 'Other')
        elif case == 'offset':
            rows['First#1'].contents[11].value = 599.5
        elif case == 'partial':
            course_factories.settext(rows['First#1'], 2, None)
        elif case == 'clock':
            course_factories.settext(rows['First#1'], 6, '00:07:01')
        elif case == 'different_itinerary':
            values = courses['Second'].contents[2].value
            writer.set_elements(values, [course_factories.string(rows['First#1'], 'I Different')])
        elif case == 'cycle':
            for index in (0, 1):
                course_factories.settext(rows[f'Root#{index}'], 2, 'Second')
                course_factories.settext(rows[f'Second#{index}'], 2, 'First')
        elif case == 'missing':
            for index in (0, 1):
                course_factories.settext(rows[f'Second#{index}'], 2, 'Missing')
                course_factories.settext(rows[f'First#{index}'], 2, 'Second')
        elif case == 'root_offset':
            rows['Root#0'].contents[11].value = 1

    banks, _ = inputs(altered=altered)
    with pytest.raises(ValueError, match=message):
        review_saved_intervals(banks, {'Root', 'First'})
