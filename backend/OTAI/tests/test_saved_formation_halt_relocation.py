"""Native centre and tail markers must move with proven booked train bounds."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive import catalogs, route_factory, writer
from opentrack_ai.current_archive.saved_geometry import project_from, transform

from test_saved_multi_document_reroute import chain
from test_saved_platform_replacement import occupied_platform
from test_saved_platform_resize import _add_center_marker, _operating


def _case(occupied_platform, signal_type, factor):
    docs, paths, dest, original, shapes = occupied_platform
    replaced, report = transform(docs, paths, dest, 'B', original, shapes=shapes)
    first, second = [point['end_ids'][0] for point in report['replacement_waypoints']]
    marked, marker_id = _add_center_marker(replaced['B'], first)
    root, version = writer.load_next_compatible(marked)
    _, models = route_factory.document(root)
    marker = models[marker_id]
    marker.contents[8].values[0] = signal_type
    marked = writer.dump_verified(root, version)
    banks, run, train = _operating()
    length = train['length_m']
    old_head, new_head = 1630 + length * factor, 1850 + length * factor
    request = {'action': 'relocate_station_halt_signal', 'station_id': original['station_id'],
               'signal_id': marker_id, 'from_end_id': first, 'to_end_id': second,
               'arrival_route': {'document': 'A', 'name': 'R:A-B', 'array_id': 0, 'start_id': 8},
               'expected_platform_edge_ids': report['replacement_edge_ids'],
               'expected_stop_shift_m': 220,
               'expected_halt_signals': [{'signal_id': marker_id, 'end_id': first, 'signal_type': signal_type}],
               'visit_reviews': [{'course_id': 'Booked', 'visit_index': 1, 'expected_train_length_m': length,
                                  'expected_reference_distance_m': 2000, 'replacement_reference_distance_m': 2000,
                                  'expected_head_distance_m': old_head, 'replacement_head_distance_m': new_head,
                                  'expected_tail_distance_m': old_head - length, 'replacement_tail_distance_m': new_head - length,
                                  'expected_available_length_m': old_head - 1500,
                                  'replacement_available_length_m': new_head - 1500}]}
    return {**docs, 'B': marked}, paths, dest, request, banks, run


@pytest.mark.parametrize(('signal_type', 'factor'), [(6, 0), (21, 0.5), (20, 1)])
def test_local_marker_preserves_id_and_recomputes_booked_head_and_tail(occupied_platform, signal_type, factor):
    docs, paths, dest, request, banks, run = _case(occupied_platform, signal_type, factor)
    out, report = transform(docs, paths, dest, 'B', request, platform_inputs=banks, run_bytes=run)
    assert set(out) == {'B'} and report['nonselected_graph_verified']
    assert report['signal_type'] == signal_type and report['signal_id'] == request['signal_id']
    assert report['checked_operating_courses'] == ['Booked'] and report['checked_directed_platform_stops'] == 1
    checked = project_from({**docs, **out}, paths, dest)
    marker = checked.model(('B', request['signal_id']))
    new = checked.model(('B', request['to_end_id']))
    assert checked.model(('B', request['from_end_id'])).contents[11].value is None
    assert marker.contents[7].value is new and new.contents[11].value is marker
    before_after, = report['verified_platform_visits']
    review, = request['visit_reviews']
    for state, prefix in (('before', 'expected'), ('after', 'replacement')):
        visit = before_after[state]
        for field in ('head_distance_m', 'tail_distance_m', 'reference_distance_m', 'available_length_m'):
            assert visit[field] == review[f'{prefix}_{field}']
        assert visit['head_offset_from_marker_m'] == factor * visit['train_length_m']
        assert visit['stop_signal_id'] == request['signal_id']
    assert before_after['before']['planned_arrival_s'] == before_after['after']['planned_arrival_s']


def test_formation_marker_rejects_omitted_operating_scope_and_wrong_booked_tail(occupied_platform):
    docs, paths, dest, request, banks, run = _case(occupied_platform, 21, 0.5)
    with pytest.raises(ValueError, match='reviewed original operating catalogs'):
        transform(docs, paths, dest, 'B', request)
    with pytest.raises(ValueError, match='every affected booked'):
        transform(docs, paths, dest, 'B', {**request, 'visit_reviews': []},
                  platform_inputs=banks, run_bytes=run)
    stale = deepcopy(request)
    stale['visit_reviews'][0]['replacement_tail_distance_m'] += 1
    with pytest.raises(ValueError, match='native train tail position'):
        transform(docs, paths, dest, 'B', stale, platform_inputs=banks, run_bytes=run)


def test_tail_marker_cannot_move_booked_head_beyond_the_original_exit(occupied_platform):
    docs, paths, dest, request, banks, run = _case(occupied_platform, 20, 1)
    depot, version = writer.load_next_compatible(banks['depot'])
    engine, = catalogs.engine_items(depot)
    engine.contents[2].values[2] = 220
    longer = {**banks, 'depot': writer.dump_verified(depot, version)}
    with pytest.raises(ValueError, match='train head beyond the directed platform exit'):
        transform(docs, paths, dest, 'B', request, platform_inputs=longer, run_bytes=run)
