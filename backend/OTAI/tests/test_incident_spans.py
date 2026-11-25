import pytest

from opentrack_ai.current_archive import incident_text, writer
from opentrack_ai.current_archive.infrastructure_incidents import core, spans
from opentrack_ai.current_archive.route_lifecycle_tools import _guard_incidents
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_cross_document_route_native_edit import REFERENCE, fixture
from test_saved_geometry import apply


PERIOD = dict(name='Signal proof', enabled=True, probability_percentage=100,
              begin_time='08:01:00', end_time='08:03:00', begin_day=0, end_day=0)


def entered(item):
    array = native.arr()
    record = core.create(item, array)
    writer.set_elements(array, [record])
    root = native.obj([('OTCourseList', 3), ('OTMutableArray', 0), ('NSObject', 0)],
                      [('i', [17]), ('@', [array]), ('@', [native.arr()]),
                       ('@', [native.arr()]), ('@', [native.arr()])])
    return record, writer.dump_verified(root)


def track_item(kind, start, end, **fields):
    return dict(PERIOD, type=kind, line_id='A-B', track_id='1', begin_km=start, end_km=end, **fields)


def test_spans_follow_kilometre_direction_and_cross_document_connectors():
    docs, catalog = fixture()
    project, _ = apply(docs, catalog, {'action': 'calculate_kilometre_points',
        'direction': 'increasing', 'itinerary': 'I:A-B', 'end_sequence': None,
        'start_km': 50, 'replace_conflicting': False})
    for begin, end in [('50.65', '51.35'), ('51.35', '50.65')]:
        match = spans.track_edges(project, track_item('position_blockage', begin, end))
        assert {row['document'] for row in match['edges']} == {'A', 'B'}
    point = spans.track_edges(project, track_item('position_stop_wait', '51.125', '51.125', wait_time_s=20))
    assert any(row['document'] == 'B' and row['kilometre_interval_m'][0] <= point['begin_m']
               < row['kilometre_interval_m'][1] for row in point['edges'])
    with pytest.raises(ValueError, match='No original edge'):
        spans.track_edges(project, track_item('position_blockage', '70', '71'))


def test_range_fields_roundtrip_and_stock_tsv_preserves_lossless_fields_only():
    speed = track_item('position_speed', '50.65', '51.35', reduced_speed_kmh=30, head_only=True)
    source, blob = entered(speed)
    assert core.item_from_object(source) == speed
    raw = incident_text.encode_catalog(blob)
    assert len(raw.splitlines()[-1].split(b'\t')) == 26
    assert incident_text.to_item(incident_text.rows(raw)[0]) == speed

    wait = track_item('position_stop_wait', '51.125', '51.125', wait_time_s=35, head_only=True)
    source, blob = entered(wait)
    assert core.item_from_object(source) == wait
    with pytest.raises(ValueError, match='extra time or power'):
        incident_text.encode_catalog(blob)
    _, blob = entered({**wait, 'wait_time_s': 0})
    assert incident_text.to_item(incident_text.rows(incident_text.encode_catalog(blob))[0])['wait_time_s'] == 0


def test_route_relative_span_uses_track_id_slots_and_guards_named_dependencies():
    name = REFERENCE['name']
    item = dict(PERIOD, type='route_span_speed', course_id='T01', begin_route=name, end_route=name,
                begin_offset_km='0.19', end_offset_km='1.5', reduced_speed_kmh=25)
    record, blob = entered(item)
    assert core.item_from_object(record) == item
    assert incident_text.to_item(incident_text.rows(incident_text.encode_catalog(blob))[0]) == item
    with pytest.raises(ValueError, match='route-relative Incident'):
        _guard_incidents(blob, set(), {name})
    docs, catalog = fixture()
    project, _ = apply(docs, catalog, {'action': 'calculate_kilometre_points',
        'direction': 'increasing', 'itinerary': 'I:A-B', 'end_sequence': None,
        'start_km': 50, 'replace_conflicting': False})
    assert spans.route_bounds(project, item)['begin']['offset_m'] == 190
    assert spans.route_bounds(project, item)['end']['length_m'] == 2000
    with pytest.raises(ValueError, match='offset outside'):
        spans.route_bounds(project, {**item, 'end_offset_km': '2.01'})
