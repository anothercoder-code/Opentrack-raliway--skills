"""Native RailML 2.2 connection writes preserve nonrepresentable native state."""

from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, writer
from opentrack_ai.current_archive.native_connections import record
from opentrack_ai.current_archive.railml_timetable_tools import ImportTimetable, RailMLWriter
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError
from opentrack_ai.models import RailMLTimetableOptions
from opentrack_ai.timetable_railml_export import render_saved_timetable

from test_operating_plan_edit import sample


def exchange_xml(attributes, *, inner=''):
    edge = '<connections><connection ' + attributes + '>' + inner + '</connection></connections>'
    return f'''<railml xmlns="http://www.railml.org/schemas/2013" version="2.2">
    <infrastructure><operationControlPoints><ocp id="ea" code="EA"/><ocp id="wb" code="WB"/>
    </operationControlPoints></infrastructure><timetable><trainParts>
      <trainPart id="p1"><ocpsTT>
      <ocpTT ocpRef="ea" ocpType="pass"><times scope="scheduled" departure="10:00:00"/>{edge}</ocpTT>
      <ocpTT ocpRef="wb" ocpType="pass"><times scope="scheduled" arrival="10:10:00"/></ocpTT>
      </ocpsTT></trainPart><trainPart id="p2"><ocpsTT>
      <ocpTT ocpRef="ea" ocpType="pass"><times scope="scheduled" departure="10:05:00"/></ocpTT>
      <ocpTT ocpRef="wb" ocpType="pass"><times scope="scheduled" arrival="10:15:00"/></ocpTT>
      </ocpsTT></trainPart></trainParts><trains>
      <train id="t1"><trainPartSequence sequence="1"><trainPartRef ref="p1"/></trainPartSequence></train>
      <train id="t2"><trainPartSequence sequence="1"><trainPartRef ref="p2"/></trainPartSequence></train>
      </trains></timetable></railml>'''.encode('ascii')


@pytest.fixture
def import_fixture(tmp_path):
    root = tmp_path / 'OTAI/workspaces/Exchange'
    root.mkdir(parents=True)
    plan = sample()
    native = catalogs.array(plan.row('A01', 0).contents[9].value)[0]
    native.contents[4].value = 8
    native.contents[7].value = 2
    native.contents[8].value = 1.25

    def source(name, raw):
        file = root / name
        file.write_bytes(raw)
        return {'path': file.relative_to(tmp_path).as_posix(), 'sha256': sha(raw)}

    inputs = {kind: source('original.' + kind, writer.dump_verified(obj))
              for kind, obj in (('courses', plan.catalog), ('timetable', plan.table))}

    def request(xml, **changes):
        return ImportTimetable(**{
            **inputs, 'railml': source('input.railml', xml), 'course_by_train_id': {'t1': 'A01', 't2': 'A02'},
            'target_path': (root / 'new.timetable').relative_to(tmp_path).as_posix(),
            'preview_only': False, **changes,
        })

    return RailMLWriter(tmp_path), root, request


def read_connections(path):
    rows = course_factories.timetable(writer.load_next_compatible(path.read_bytes())[0])
    return [record(value) for value in catalogs.array(rows['A01#0'].contents[9].value)]


def test_refuses_implicit_write_and_saves_cross_station_target_into_fresh_archive(import_fixture):
    api, root, request = import_fixture
    xml = exchange_xml('trainRef="t2" trainPartRef="p2" ocpRef="wb" connOperation="meet" '
                       'minConnTime="PT1M30S" maxConnTime="PT5M"')
    with pytest.raises(APIError, match='separate reviewed mapping'):
        api.import_timetable(request(xml))
    with pytest.raises(APIError, match='no matching native Connection'):
        api.import_timetable(request(xml, connections='match'))
    result = api.import_timetable(request(xml, connections='merge'))
    assert result['saved'] and result['connections']['created'] == 1
    existing, incoming = read_connections(root / 'new.timetable')
    assert [existing[key] for key in ('flags', 'time_reference_type', 'dispatching_distance_km')] == [8, 2, 1.25]
    assert incoming == {
        'course_id': 'A01', 'target_course_id': 'A02', 'station_sign': 'EA', 'target_station_sign': 'WB',
        'minimum_wait': '00:01:30', 'maximum_wait': '00:05:00', 'flags': 3,
        'time_reference_type': 0, 'dispatching_distance_km': 0,
    }


def test_existing_merge_changes_exchanged_slots_only(import_fixture):
    api, root, request = import_fixture
    xml = exchange_xml('trainRef="t2" trainPartRef="p2" connOperation="split" minConnTime="PT90S"')
    result = api.import_timetable(request(xml, connections='merge'))
    assert result['saved'] and result['connections']['updated'] == 1
    saved, = read_connections(root / 'new.timetable')
    assert [saved[key] for key in ('minimum_wait', 'maximum_wait', 'flags', 'time_reference_type',
                                   'dispatching_distance_km')] == ['00:01:30', '00:04:00', 10, 2, 1.25]


@pytest.mark.parametrize(('attributes', 'inner', 'problem'), [
    ('trainPartRef="p2"', '', 'explicit mapped target'),
    ('trainRef="t2" trainPartRef="p1"', '', 'must contain the target station'),
    ('trainRef="t1"', '', 'different target'),
    ('trainRef="t2" ocpRef="p2"', '', 'one exact definition'),
    ('trainRef="t2" connType="commercial"', '', 'operational declaration'),
    ('trainRef="t2"', '<annotationRef ref="x"/>', 'operational declaration'),
    ('trainRef="t2" connOperation="IsWaitingFor"', '', 'unsupported native connection operation'),
    ('trainRef="t2" minConnTime="PT60.5S"', '', 'whole seconds'),
    ('trainRef="t2" minConnTime="PT250S"', '', 'merged minimum'),
])
def test_reject_ambiguous_or_unrepresentable_connections(import_fixture, attributes, inner, problem):
    api, root, request = import_fixture
    with pytest.raises(APIError, match=problem):
        api.import_timetable(request(exchange_xml(attributes, inner=inner), connections='merge'))
    assert not (root / 'new.timetable').exists()


def test_export_cross_station_reference_default_vs_corrected():
    from opentrack_ai.current_archive.railml_v100_timetable_tools import extract_row

    plan = sample()
    conn, = catalogs.array(plan.row('A01', 0).contents[9].value)
    course_factories.settext(conn, 6, 'WB')
    rows = [extract_row(key, row) for key, row in plan.rows().items()]
    catalog = {station: {'name': station, 'longitude': '', 'latitude': ''} for station in ('EA', 'WB')}
    scopes = dict(stations=catalog, stock=[], engine_records=[], course_records=[], all_rows=rows,
                  dwell={row['key']: '0' for row in rows}, project_name='CrossStation')
    original, warnings, _ = render_saved_timetable(
        rows, SimpleNamespace(saved_actual='omit', railml=RailMLTimetableOptions()), **scopes)
    assert 'ocpRef="tp-A02" minConnTime=' in original
    assert any(item['kind'] == 'NATIVE_CONNECTION_OCPREF_USES_COURSE_PART_ID' for item in warnings)
    corrected, warnings, _ = render_saved_timetable(rows, SimpleNamespace(
        saved_actual='omit', railml=RailMLTimetableOptions(connection_ocp_reference='station')), **scopes)
    assert 'ocpRef="ocp-WB" minConnTime=' in corrected
    assert not any(item['kind'] in ('NATIVE_CONNECTION_OCPREF_USES_COURSE_PART_ID',
                                   'UNRESOLVED_EXPORTED_REFERENCE') for item in warnings)
