"""Regression checks for longitudinal RailML segment assembly and saved clocks."""

import pytest

from opentrack_ai.current_archive import course_factories, writer
from opentrack_ai.current_archive.railml_timetable_tools import ImportTimetable, RailMLWriter
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.errors import APIError

from test_operating_plan_edit import sample


SEQUENTIAL = ('<trainPartSequence sequence="1"><trainPartRef ref="first"/></trainPartSequence>'
              '<trainPartSequence sequence="2"><trainPartRef ref="second"/></trainPartSequence>')


def exchange_xml(sequences=SEQUENTIAL, *, left_departure='', right_station='mid_alias', scope='scheduled'):
    return f'''<railml xmlns="http://www.railml.org/schemas/2013" version="2.2">
      <infrastructure><operationControlPoints>
        <ocp id="west" code="EA"/><ocp id="middle" code="RDG"/>
        <ocp id="mid_alias" code="RDG-alias"/><ocp id="east" code="WB"/>
      </operationControlPoints></infrastructure>
      <timetable><trainParts>
        <trainPart id="first"><ocpsTT>
          <ocpTT ocpRef="west" ocpType="pass"><times scope="{scope}" departure="23:50:00"/></ocpTT>
          <ocpTT ocpRef="middle" ocpType="pass"><times scope="{scope}" arrival="23:58:00" {left_departure}/></ocpTT>
        </ocpsTT></trainPart>
        <trainPart id="second"><ocpsTT>
          <ocpTT ocpRef="{right_station}" ocpType="stop"><times scope="{scope}" departure="00:04:00" departureDay="1"/></ocpTT>
          <ocpTT ocpRef="east" ocpType="pass"><times scope="{scope}" arrival="00:09:00" arrivalDay="1"/></ocpTT>
        </ocpsTT></trainPart>
      </trainParts><trains><train id="train1">{sequences}</train></trains></timetable>
    </railml>'''.encode('utf-8')


@pytest.fixture
def native_inputs(tmp_path):
    plan = sample()
    plan.insert_timetable_row({
        'course_id': 'A01', 'index': 1, 'template_course_id': 'A01', 'template_index': 1,
        'station_sign': 'RDG', 'fields': {'stop_at_station': True, 'dwell_s': 120, 'track_id': '9'},
    })
    root = tmp_path / 'OTAI/workspaces/Multipart'
    root.mkdir(parents=True)
    base = 'OTAI/workspaces/Multipart/'
    inputs = {}
    for field, archive in [('courses', plan.catalog), ('timetable', plan.table)]:
        data = writer.dump_verified(archive)
        name = f'original.{field}'
        (root / name).write_bytes(data)
        inputs[field] = {'path': base + name, 'sha256': sha(data)}

    def request(xml, **changes):
        (root / 'input.railml').write_bytes(xml)
        return ImportTimetable(**{
            **inputs, 'railml': {'path': base + 'input.railml', 'sha256': sha(xml)},
            'course_by_train_id': {'train1': 'A01'}, 'station_by_ocp_id': {'mid_alias': 'RDG'},
            'target_path': base + 'new.timetable', **changes,
        })

    return RailMLWriter(tmp_path), root, request


def test_join_two_sections_and_verify_native_saved_fields(native_inputs):
    api, root, request = native_inputs
    args = request(exchange_xml())
    preview = api.import_timetable(args)
    assert preview['row_count'] == 3
    assert preview['assembly'] == {'train1': {
        'course_id': 'A01', 'train_part_ids': ['first', 'second'],
        'boundaries': [{'row_index': 1, 'station': 'RDG'}],
    }}
    assert not (root / 'new.timetable').exists()
    saved = api.import_timetable(args.model_copy(update={'preview_only': False}))
    assert saved['saved'] and saved['report']['protected_graph_verified']
    published = (root / 'new.timetable').read_bytes()
    assert sha(published) == preview['output_sha256'] == saved['output_sha256']
    assert sha((root / 'original.courses').read_bytes()) == args.courses.sha256
    assert sha((root / 'original.timetable').read_bytes()) == args.timetable.sha256
    rows = course_factories.timetable(writer.load_next_compatible(published)[0])
    stop = rows['A01#1']
    assert [writer.string(stop.contents[i].value) for i in (5, 6, 7, 8, 18)] == [
        'RDG', '23:58:00', '00:04:00', '120', '9',
    ]
    assert stop.contents[15].values == [0, 1, 0, 0]
    assert len(rows) == 5


@pytest.mark.parametrize(('xml', 'message'), [
    (exchange_xml(SEQUENTIAL.replace('sequence="2"', 'sequence="1"')), 'positive, increasing'),
    (exchange_xml(SEQUENTIAL.replace('</trainPartSequence><trainPartSequence sequence="2">', '')),
     'exactly one trainPartRef'),
    (exchange_xml(SEQUENTIAL + '<trainPartSequence sequence="3"/>'), 'exactly one trainPartRef'),
    (exchange_xml(right_station='east'), 'boundary mismatch'),
    (exchange_xml(left_departure='departure="23:59:00"'), 'Conflicting RailML departure'),
    (exchange_xml().replace(b'departureDay="1"', b'departureDay="0"'), 'times go backwards'),
], ids=['duplicate-sequence', 'concurrent-parts', 'empty-sequence', 'different-station', 'conflict', 'day-order'])
def test_reject_ambiguous_or_incompatible_assembly(native_inputs, xml, message):
    api, root, request = native_inputs
    with pytest.raises(APIError, match=message):
        api.import_timetable(request(xml, preview_only=False))
    assert not (root / 'new.timetable').exists()


def test_one_part_preserves_legacy_calculated_scope(native_inputs):
    api, root, request = native_inputs
    xml = exchange_xml('<trainPartSequence><trainPartRef ref="first"/></trainPartSequence>', scope='calculated')
    xml = xml.replace(b'ocpRef="middle"', b'ocpRef="east"', 1)
    result = api.import_timetable(request(xml, course_by_train_id={'train1': 'A02'}, time_scope='calculated'))
    assert result['assembly']['train1']['boundaries'] == []
    assert [entry['field'] for entry in result['report']['rows']['A02#0']] == [
        'actual_arrival', 'actual_arrival_day_offset', 'actual_departure', 'actual_departure_day_offset',
    ]
    assert not (root / 'new.timetable').exists()
