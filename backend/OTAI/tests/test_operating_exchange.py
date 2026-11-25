"""Regression coverage for native timetable exchange without legacy writer dependencies."""

from types import SimpleNamespace
import unittest

from opentrack_ai.current_archive import catalogs, course_factories, writer
from opentrack_ai.current_archive.operating_plan_edit import text
from opentrack_ai.current_archive.rolling_stock_exchange_import import _read_railml
from opentrack_ai.current_archive.timetable_exchange_import import import_rows
from test_operating_plan_edit import sample


def settings(kind, existing='replace', **updates):
    return SimpleNamespace(**{
        'format': kind, 'existing': existing, 'import_xml_actual': False,
        'connection_attribute_order': 'require_unambiguous', 'new_course_templates': {},
        'row_template': SimpleNamespace(course_id='A01', index=1),
        **updates,
    })


def tsv_row(cid, index, station, clock):
    return '\t'.join(map(str, [cid, 0, 0, index, station, '', 0, clock, 0, clock, 1, 0, 0, 0, '', 0]))


class OperatingExchangeTest(unittest.TestCase):
    def test_merge_preserves_unlisted_rows_and_updates_connection_time_type(self):
        plan = sample()
        content = tsv_row('A01', 0, 'EA', '23:31:00') + '\n// Connections:\n'
        content += '\t'.join(['A01', 'A02', '0', 'EA', '1', '00:02:00', '00:03:00', '16']) + '\n'
        report = import_rows(plan, content, settings('opentrack_text', 'merge'))
        plan.validate()
        self.assertEqual((report['imported_rows'], report['imported_connections']), (1, 1))
        data = course_factories.timetable(writer.load(writer.dump_verified(plan.table))[0])
        self.assertEqual(text(data['A01#0'], 6), '23:31:00')
        self.assertEqual(text(data['A01#1'], 6), '23:45:00')
        conn, = catalogs.array(data['A01#0'].contents[9].value)
        self.assertEqual((text(conn, 3), text(conn, 5), conn.contents[4].value, conn.contents[7].value),
                         ('00:02:00', '00:03:00', 4, 1))

    def test_proprietary_xml_adds_new_course_with_explicit_template(self):
        plan = sample()
        content = ('<?xml version="1.0"?><timetable><course><courseID>NEW01</courseID>'
                   '<timetableEntry stopInformation="no"><stationID>EA</stationID><departureTime>23:40:00</departureTime></timetableEntry>'
                   '<timetableEntry stopInformation="yes"><stationID>WB</stationID><arrivalTime>23:48:00</arrivalTime>'
                   '<waitTime format="s">30</waitTime><deltaLoad>1.25</deltaLoad></timetableEntry></course></timetable>')
        with self.assertRaisesRegex(ValueError, 'explicit existing Course template'):
            import_rows(plan, content, settings('opentrack_xml'))
        report = import_rows(plan, content, settings('opentrack_xml', new_course_templates={'NEW01': 'A01'}))
        plan.validate()
        self.assertEqual(report['courses_created'], ['NEW01'])
        self.assertEqual(text(plan.row('NEW01', 0), 6), 'HH:MM:SS')
        self.assertEqual(text(plan.row('NEW01', 1), 8), '30')
        self.assertEqual(plan.row('NEW01', 1).contents[17].value, 1.25)

    def test_replace_cannot_break_existing_inbound_connection(self):
        plan = sample()
        source = tsv_row('A02', 0, 'RDG', '23:37:00') + '\n'
        import_rows(plan, source, settings('opentrack_text'))
        with self.assertRaisesRegex(ValueError, 'Unresolved Connection target'):
            plan.validate()

    def test_railml_namespace_and_disallowed_entity_resource(self):
        samples = b'<railml xmlns="http://www.railml.org/schemas/2013" version="2.2"><rollingstock><vehicles><vehicle id="one"/></vehicles></rollingstock></railml>'
        records, formations = _read_railml(samples)
        self.assertEqual((records[0].tag, records[0].attrib['id'], formations), ('vehicle', 'one', []))
        with self.assertRaisesRegex(ValueError, 'no DTD'):
            _read_railml(b'<!DOCTYPE railml SYSTEM "external.dtd">' + samples)

