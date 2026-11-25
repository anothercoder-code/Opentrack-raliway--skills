"""Legacy original RailML 1.00 direct model and safe current archive writeback."""

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, writer
from opentrack_ai.current_archive.operating_plan_edit import text
from opentrack_ai.current_archive.railml_timetable_tools import ImportTimetable, RailMLWriter
from opentrack_ai.current_archive.railml_v100_timetable_tools import ExportRailML100, NativeRailML100Export
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError
from opentrack_ai.railml_timetable_v100 import HEADER, NATIVE_FOOTER, XSI, legacy_tree

from test_operating_plan_edit import sample


def railml(entries, *, train_type='planned', finish=True):
    start = HEADER + f'<railml xmlns:xsi="{XSI}" xsi:noNamespaceSchemaLocation="timetable.xsd"><timetable version="1.00">'
    train = f'<train trainID="A01" type="{train_type}" dataSource="opentrack"><timetableentries>{entries}</timetableentries></train>'
    return (start+train).encode() + (NATIVE_FOOTER if finish else b'\n')


@pytest.fixture
def case(tmp_path):
    plan = sample()
    plan.insert_timetable_row({'course_id':'A01','index':1,'template_course_id':'A01','template_index':1,
        'station_sign':'RDG','fields':{'arrival':'23:38:00','departure':'23:40:00','stop_at_station':True,'dwell_s':120,'track_id':'9'}})
    work = tmp_path/'OTAI/workspaces/RailML100'
    work.mkdir(parents=True)

    def store(name, raw):
        path = work/name
        path.write_bytes(raw)
        return {'path':path.relative_to(tmp_path).as_posix(),'sha256':sha(raw)}

    sources = {'timetable':store('Old.timetable',writer.dump_verified(plan.table)),
               'courses':store('Old.courses',writer.dump_verified(plan.catalog))}

    def import_file(data, **opts):
        binding = store('Original.xml', data)
        args = ImportTimetable(**sources, railml=binding, course_by_train_id={'A01':'A01'}, format='railml_1_00',
                              preview_only=False,target_path=store_target('New.timetable'), **opts)
        return RailMLWriter(tmp_path).import_timetable(args)

    def store_target(name):
        return (work/name).relative_to(tmp_path).as_posix()

    return work, sources, import_file, store_target


def saved(path):
    return course_factories.timetable(writer.load_next_compatible(path.read_bytes())[0])


def test_legacy_export_roundtrips_native_records_with_existing_connection(case, tmp_path):
    work, sources, import_file, target = case
    exporter = NativeRailML100Export(tmp_path)
    opts = ExportRailML100(**sources, course_ids=['A01'], target_path=target('RoundTrip.railml'),
                          railml={'planned': True, 'published': True})
    preview = exporter.export_timetable(opts)
    assert not (work/'RoundTrip.railml').exists() and preview['planned_trains'] == 1
    result = exporter.export_timetable(opts.model_copy(update={'preview_only':False}))
    raw = (work/'RoundTrip.railml').read_bytes()
    tree, recovered = legacy_tree(raw)
    entries = tree.findall('./train/timetableentries/entry')
    assert result['post_commit_verified'] and sha(raw) == preview['output_sha256']
    assert not recovered and tree.get('version') == '1.00' and result['connections'] == 1
    assert entries[1].get('publishedArrival') == '23:38:00.0' and entries[1].get('minStopTime') == 'PT120S'
    assert entries[0].find('connection').attrib == {'trainID':'A02','connOperation':'none',
        'minConnTime':'PT60S','maxConnTime':'PT240S'}
    restored = import_file(raw)
    assert restored['entry_rows_updated'] == 0
    assert (work/'New.timetable').read_bytes() == (work/'Old.timetable').read_bytes()


def test_legacy_import_updates_declared_schedule_fields_across_midnight(case):
    work, _, import_file, _ = case
    raw = railml('<entry posID="EA" departure="23:56:00.0" type="pass"/>'
                 '<entry posID="Alias" arrival="00:04:03.0" arrivalDay="1" departure="00:07:00.0" departureDay="1" '
                 'type="stop" trackID="B2" trackInfo="B2" minStopTime="PT150S" meanDelayDeparture="PT12.5S"/>'
                 '<entry posID="WB" arrival="00:12:00.0" arrivalDay="1" type="pass"/>')
    result = import_file(raw, legacy_entry_fields='update', station_by_pos_id={'Alias':'RDG'})
    old, new = [saved(work/name) for name in ('Old.timetable','New.timetable')]
    row = new['A01#1']
    assert result['entry_rows_updated'] == 1 and result['all_input_hashes_rechecked']
    assert [text(row,i) for i in (6,7,8,12,18)] == ['00:04:03','00:07:00','150','12.5','B2']
    assert row.contents[15].values == [1,1,0,0] and row.contents[10].value == old['A01#1'].contents[10].value
    assert writer.dump_verified(new['A02#0']) == writer.dump_verified(old['A02#0'])
    assert len(catalogs.array(new['A01#0'].contents[9].value)) == 1


def test_original_footer_recovery_and_sparse_calculated_clocks(case):
    work, _, import_file, _ = case
    raw = railml('<entry posID="EA" departure="23:30:18.0" type="pass"/>'
                 '<entry posID="WB" arrival="23:47:00.0" type="pass"/>',train_type='calculated',finish=False)
    with pytest.raises(APIError, match='Malformed RailML 1.00 XML'):
        import_file(raw,time_scope='calculated')
    report = import_file(raw,time_scope='calculated',legacy_recover_footer=True)
    rows = saved(work/'New.timetable')
    assert report['original_xml_footer_completed'] and report['assembly']['A01']['aligned_row_indices'] == [0,2]
    assert text(rows['A01#0'],7) == '23:30:00' and text(rows['A01#0'],14) == '23:30:18'
    assert text(rows['A01#1'],13) == 'HH:MM:SS' and text(rows['A01#2'],13) == '23:47:00'


def test_legacy_published_clocks_leave_omitted_fields_in_place(case):
    work, _, import_file, _ = case
    raw = railml('<entry posID="EA" departure="23:28:00.0" publishedDeparture="23:35:00.0" type="pass"/>'
                 '<entry posID="RDG" arrival="23:38:00.0" departure="23:40:00.0" type="stop"/>'
                 '<entry posID="WB" arrival="23:45:00.0" type="pass"/>')
    report = import_file(raw,time_scope='published')
    rows = saved(work/'New.timetable')
    assert report['rows_with_clock_changes'] == 1 and text(rows['A01#0'],7) == '23:35:00'
    assert text(rows['A01#1'],6) == '23:38:00' and text(rows['A01#1'],7) == '23:40:00'


def test_native_connection_export_normalizes_unrepresentable_wait_sentinels(case, tmp_path):
    work, sources, import_file, target = case
    root, version = writer.load_next_compatible((work/'Old.timetable').read_bytes())
    item, = catalogs.array(course_factories.timetable(root)['A01#0'].contents[9].value)
    course_factories.settext(item,3,'HH:MM:SS')
    course_factories.settext(item,5,'00:00:00')
    data = writer.dump_verified(root,version)
    (work/'Old.timetable').write_bytes(data)
    sources['timetable']['sha256'] = sha(data)
    NativeRailML100Export(tmp_path).export_timetable(ExportRailML100(**sources, course_ids=['A01'],
        target_path=target('Wait.railml'),preview_only=False))
    raw = (work/'Wait.railml').read_bytes()
    assert b'minConnTime="PT0S"' in raw and b'maxConnTime' not in raw
    import_file(raw)
    assert (work/'New.timetable').read_bytes() == data


@pytest.mark.parametrize(('entry', 'message'), [
    ('<entry posID="EA" departure="23:31:00.1"/>', 'whole-second clock'),
    ('<entry posID="EA" departure="23:31:00"><connection trainID="A02" minConnTime="PT61S"/></entry>',
     'connection targets, waits or operations differ'),
], ids=['fractional-clock','connection-mismatch'])
def test_legacy_refuses_data_that_would_lose_native_semantics(case, entry, message):
    work, _, import_file, _ = case
    raw = railml(entry+'<entry posID="RDG" arrival="23:38:00"/><entry posID="WB" arrival="23:45:00"/>')
    with pytest.raises(APIError, match=message):
        import_file(raw)
    assert not (work/'New.timetable').exists()


def test_missing_footer_recovery_refuses_a_non_original_source(case):
    _, _, import_file, _ = case
    raw = railml('<entry posID="EA"/>', finish=False).replace(b'opentrack.ch', b'other.example')
    with pytest.raises(APIError, match='Malformed RailML 1.00 XML'):
        import_file(raw,legacy_recover_footer=True)


@pytest.mark.parametrize(('variant', 'date_option', 'expected'), [
    ('ott', None, '2007-01-01'),
    ('ott', '2005-12-31  ', '2005-12-31'),
    ('standard', None, None),
    ('standard', '2005-12-31T09:00:00', '2005-12-31T09:00:00'),
])
def test_ott_calculated_operating_date_preserves_sparse_native_clocks(case, tmp_path, variant, date_option, expected):
    work, sources, _, target = case
    path = work/'Old.timetable'
    root, version = writer.load_next_compatible(path.read_bytes())
    rows = course_factories.timetable(root)
    course_factories.settext(rows['A01#0'], 14, '23:30:18')
    course_factories.settext(rows['A01#2'], 13, '00:02:00')
    rows['A01#2'].contents[15].values[2] = 1
    raw = writer.dump_verified(root, version)
    path.write_bytes(raw)
    sources['timetable']['sha256'] = sha(raw)
    opts = ExportRailML100(**sources, course_ids=['A01'], variant=variant, saved_actual='as_valid',
                          railml={'calculated': True, 'metadata_date': date_option}, target_path=target('Timetable.xml'))
    exporter = NativeRailML100Export(tmp_path)
    preview = exporter.export_timetable(opts)
    assert preview['variant'] == variant and not (work/'Timetable.xml').exists()
    saved = exporter.export_timetable(opts.model_copy(update={'preview_only': False}))
    output = (work/'Timetable.xml').read_bytes()
    assert sha(output) == preview['output_sha256'] == saved['output_sha256']
    root, recovered = legacy_tree(output)
    assert not recovered and root.get('version') == '1.00'
    planned, calculated = root.findall('train')
    assert planned.get('type') == 'planned' and planned.get('dataDateTime') is None
    assert calculated.get('type') == 'calculated' and calculated.get('dataDateTime') == expected
    calc_entries = calculated.findall('timetableentries/entry')
    assert [row.get('posID') for row in calc_entries] == ['EA', 'WB']
    assert calc_entries[0].get('departure') == '23:30:18.0' and calc_entries[0].get('arrival') is None
    assert calc_entries[1].get('arrival') == '00:02:00.0' and calc_entries[1].get('arrivalDay') == '1'
    assert saved['native_actual_validity_verified'] is False and path.read_bytes() == raw


def test_ott_accepts_only_calendar_dates_for_calculated_export(case):
    _, sources, _, _ = case
    with pytest.raises(ValueError, match='OTT calculated metadata_date must be an operating date'):
        ExportRailML100(**sources, variant='ott', railml={'calculated': True, 'metadata_date': '2026-02-30'})
