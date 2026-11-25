"""Regressions for the current Course, Timetable and Connection edit contract."""

import unittest

from opentrack_ai.current_archive import catalogs, course_factories as cf, writer
from opentrack_ai.current_archive.operating_plan_edit import OperatingPlan, text, timetable_time
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native
from test_itinerary_lifecycle import course_archive


def native_record(kind, version, groups, slots):
    defaults = {'@': None, 'i': 0, 'f': 0.0}
    return native.obj([(kind, version), ('NSObject', 0)],
                      [(group, slots.get(index, [defaults[code] for code in group]))
                       for index, group in enumerate(groups)])


def dictionary(entries):
    return native.obj([('NSMutableDictionary', 0), ('NSDictionary', 0), ('NSObject', 0)],
                      [('i', [len(entries)]), *[(code, [obj]) for key, entry in entries.items()
                                                for code, obj in (('@', native.string(key)), ('@', entry))]])


def row(cid, station, index, clock, *, reference='0', offset=0, connections=()):
    return native_record('OTTimetable', 9, cf.TT, {
        0: [17], 1: [native.string(cid)], 2: [native.string(reference)], 3: [index], 4: [1], 5: [native.string(station)],
        6: [native.string(clock)], 7: [native.string(clock)], 8: [native.string('0')], 9: [native.arr(connections)],
        10: [2], 11: [offset], 12: [native.string('0')], 13: [native.string('HH:MM:SS')],
        14: [native.string('HH:MM:SS')], 16: [native.string('')], 18: [native.string('')],
    })


def connection(owner, target, station):
    return native_record('OTConnection', 6, ['@', '@', '@', '@', 'i', '@', '@', 'i', 'f'], {
        0: [native.string(owner)], 1: [native.string(target)], 2: [native.string(station)],
        3: [native.string('00:01:00')], 5: [native.string('00:04:00')], 6: [native.string(station)],
    })


def sample():
    courses, _ = writer.load(course_archive(A01=['I Main'], A02=['I Main']))
    trains = native.obj([('OTTrainList', 3), ('OTMutableArray', 0), ('NSObject', 0)],
                        [('i', [17]), ('@', [native.arr()]), ('@', [native.arr()]),
                         ('@', [native.arr([native_record('OTTrain', *catalogs.LAYOUTS['OTTrain'],
                                                         {0: [native.string('Passenger')]})])])])
    stations = dictionary({
        name: native_record('OTStation', *catalogs.LAYOUTS['OTStation'], {1: [native.string(name)]})
        for name in ('EA', 'RDG', 'WB')
    })
    timetable = dictionary({
        'A01#0': row('A01', 'EA', 0, '23:30:00', connections=(connection('A01', 'A02', 'EA'),)),
        'A01#1': row('A01', 'WB', 1, '23:45:00'),
        'A02#0': row('A02', 'EA', 0, '23:32:00', reference='A01', offset=120),
        'A02#1': row('A02', 'WB', 1, '23:47:00', reference='A01', offset=120),
    })
    roots = {'courses': courses, 'timetable': timetable, 'trains': trains, 'stations': stations}
    return OperatingPlan(roots, {key: key for key in roots}, {'I Main': ('EA', 'RDG', 'WB')}, ['main'])


def nested_interval_plan():
    plan = sample()
    plan.generate_interval_courses({'course_id': 'A02', 'count': 1, 'interval_s': 900,
                                    'number_step': 1, 'number_position': 0})
    plan.generate_interval_courses({'course_id': 'A02', 'count': 1, 'interval_s': 600,
                                    'number_step': 3, 'number_position': 0})
    for index in range(2):
        plan.update_timetable_row({'course_id': 'A03', 'index': index, 'fields': {
            'interval_reference_course_id': 'A02', 'interval_offset_s': 900}})
    return plan


class OperatingPlanEditTest(unittest.TestCase):
    def test_rename_and_detach_updates_native_reference_names(self):
        plan = sample()
        plan.rename_courses({'renames': [{'course_id': 'A01', 'new_id': 'A10'}, {'course_id': 'A02', 'new_id': 'A20'}]})
        plan.validate()
        saved = cf.timetable(writer.load(writer.dump_verified(plan.table))[0])
        self.assertEqual(text(saved['A20#1'], 2), 'A10')
        conn, = catalogs.array(saved['A10#0'].contents[9].value)
        self.assertEqual((text(conn, 0), text(conn, 1)), ('A10', 'A20'))
        with self.assertRaisesRegex(ValueError, 'explicit detach'):
            plan.delete_courses({'course_ids': ['A10'], 'reference_policy': 'reject'})
        plan.delete_courses({'course_ids': ['A10'], 'reference_policy': 'detach'})
        plan.validate()
        self.assertEqual(set(plan.rows()), {'A20#0', 'A20#1'})
        self.assertEqual(text(plan.row('A20', 1), 2), '0')
        self.assertEqual(plan.row('A20', 1).contents[11].value, 0)

    def test_insertion_row_controls_and_connection_reference_changes(self):
        plan = sample()
        report = plan.insert_timetable_row({
            'course_id': 'A01', 'index': 1, 'template_course_id': 'A01', 'template_index': 1, 'station_sign': 'RDG',
            'fields': {'arrival': '23:37:00', 'departure': '23:39:00', 'arrival_day_offset': 0,
                       'departure_day_offset': 0, 'dwell_s': 120, 'stop_at_station': True, 'timing_station': True,
                       'track_id': '9', 'delta_mass_t': 1.25},
        })
        self.assertEqual(report['row_inserted'], 'A01#1')
        plan.update_course({'course_id': 'A01', 'train': 'Passenger', 'itineraries': ['I Main'],
                            'fields': {'speed_type': 'main', 'spacing_mode': 'moving_cbtc'}})
        plan.update_connection({'course_id': 'A01', 'index': 0, 'connection_index': 0,
                                'fields': {'time_reference': 'departure', 'location': 'entry', 'minimum_wait': '00:02:00'}})
        plan.validate()
        saved = cf.timetable(writer.load(writer.dump_verified(plan.table))[0])
        self.assertEqual(text(saved['A01#1'], 18), '9')
        self.assertEqual(text(saved['A01#1'], 8), '120')
        self.assertEqual(saved['A01#1'].contents[17].value, 1.25)
        self.assertEqual(saved['A01#2'].contents[4].value, 2)
        self.assertEqual(plan.course('A01').contents[8].value, 3)
        conn, = catalogs.array(saved['A01#0'].contents[9].value)
        self.assertEqual((conn.contents[4].value, conn.contents[7].value), (4, 1))
        with self.assertRaisesRegex(ValueError, 'outgoing Connections'):
            plan.delete_timetable_row({'course_id': 'A01', 'index': 0})

    def test_interval_expansion_preserves_family_and_crosses_day_boundary(self):
        plan = sample()
        plan.generate_interval_courses({'course_id': 'A01', 'count': 1, 'interval_s': 3600,
                                        'number_step': 2, 'number_position': 0})
        plan.generate_interval_courses({'course_id': 'A02', 'count': 1, 'interval_s': 3600,
                                        'number_step': 2, 'number_position': 0})
        plan.validate()
        latest = plan.row('A03', 0)
        self.assertEqual((text(latest, 2), text(latest, 6), latest.contents[15].values[0]), ('A01', '00:30:00', 1))
        self.assertEqual(plan.row('A04', 0).contents[11].value, 3720)
        copied, = catalogs.array(latest.contents[9].value)
        self.assertEqual((text(copied, 0), text(copied, 1)), ('A03', 'A04'))
        result = plan.update_connection({'course_id': 'A01', 'index': 0, 'connection_index': 0,
                                         'propagate_interval': True, 'fields': {'time_reference': 'departure'}})
        self.assertEqual(result['interval_rows_propagated'], ['A03#0'])
        self.assertEqual(copied.contents[7].value, 1)

    def test_retimes_every_related_row_from_a_follower_across_midnight(self):
        plan = nested_interval_plan()
        before_start = {cid: writer.fingerprint(plan.row(cid, 0)) for cid in plan.courses()}
        receipt = plan.update_timetable_row({
            'course_id': 'A02', 'index': 1, 'propagate_interval': True,
            'fields': {'arrival': '00:01:00', 'arrival_day_offset': 1,
                       'departure': '00:01:00', 'departure_day_offset': 1},
        })
        plan.validate()
        self.assertEqual(receipt['interval_root_course_id'], 'A01')
        self.assertEqual(receipt['interval_rows_updated'], ['A01#1', 'A02#1', 'A05#1', 'A03#1'])
        self.assertEqual(before_start, {cid: writer.fingerprint(plan.row(cid, 0)) for cid in plan.courses()})
        fresh = cf.timetable(writer.load(writer.dump_verified(plan.table))[0])
        for cid, reference, offset, seconds in (
            ('A01', '0', 0, 86340), ('A02', 'A01', 120, 86460),
            ('A03', 'A02', 900, 87360), ('A05', 'A01', 720, 87060),
        ):
            row = fresh[f'{cid}#1']
            self.assertEqual((text(row, 2), row.contents[11].value), (reference, offset))
            self.assertEqual([timetable_time(row, event) for event in ('arrival', 'departure')], [seconds, seconds])

    def test_clears_then_reinstates_a_planned_clock_for_the_whole_interval_family(self):
        plan = nested_interval_plan()
        op = {'course_id': 'A03', 'index': 1, 'propagate_interval': True}
        plan.update_timetable_row({**op, 'fields': {'arrival': None}})
        for cid in plan.courses():
            row = plan.row(cid, 1)
            self.assertIsNone(timetable_time(row, 'arrival'))
            self.assertEqual(row.contents[15].values[0], 0)
        plan.update_timetable_row({**op, 'fields': {'arrival': '00:01:00', 'arrival_day_offset': 1}})
        plan.validate()
        self.assertEqual(timetable_time(plan.row('A01', 1), 'arrival'), 85440)
        self.assertEqual(timetable_time(plan.row('A03', 1), 'departure'), 86520)

    def test_rejects_inconsistent_interval_family_without_mutating_any_row(self):
        plan = nested_interval_plan()
        plan.update_timetable_row({'course_id': 'A03', 'index': 1, 'fields': {'arrival': '00:03:00'}})
        before = writer.fingerprint(plan.table)
        with self.assertRaisesRegex(ValueError, 'inconsistent with the direct interval offset'):
            plan.update_timetable_row({'course_id': 'A02', 'index': 1, 'propagate_interval': True,
                                       'fields': {'arrival': '23:48:00'}})
        self.assertEqual(writer.fingerprint(plan.table), before)

    def test_reject_missing_station_reference_and_wrong_itinerary(self):
        plan = sample()
        plan.delete_timetable_row({'course_id': 'A02', 'index': 0})
        with self.assertRaisesRegex(ValueError, 'Unresolved Connection target'):
            plan.validate()
        plan = sample()
        with self.assertRaisesRegex(ValueError, 'Repeated Station participates'):
            plan.update_timetable_row({'course_id': 'A01', 'index': 1, 'station_sign': 'EA'})
        plan.itineraries['I Reverse'] = ('WB', 'RDG', 'EA')
        plan.update_course({'course_id': 'A01', 'itineraries': ['I Reverse']})
        with self.assertRaisesRegex(ValueError, 'do not follow each'):
            plan.validate()

