import pytest

from opentrack_ai.current_archive.itinerary_edit_tools import set_safety_margins
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, project_from, transform

from test_saved_multi_document_reroute import chain
from test_saved_track_topology import save_project


@pytest.fixture
def marked_chain(chain):
    docs, paths, catalog, _ = chain
    project = project_from(docs, paths, catalog)
    for key, kilometres in ((('A', 16), 0.0), (('B', 4), 0.5625), (('B', 5), -3.0),
                            (('B', 13), 1.75), (('B', 16), 1.0)):
        project.model(key).contents[14].value = kilometres
    operation = {'action': 'calculate_edge_lengths_from_kilometration', 'edges': [
        {'edge_id': 20, 'expected_length_m': 500, 'expected_calculated_length_m': 563},
        {'edge_id': 23, 'expected_length_m': 500, 'expected_calculated_length_m': 750},
        {'edge_id': 21, 'expected_length_m': 500},
    ]}
    return save_project(project), paths, catalog, operation


def test_native_cal_applies_endpoint_priority_crossing_fallback_and_integer_rounding(marked_chain):
    docs, paths, catalog, operation = marked_chain
    changed, report = transform(docs, paths, catalog, 'B', operation)
    assert report['changed_documents'] == ['B']
    assert report['chainage_and_signal_protections_verified']
    first, second, missing = report['edges']
    assert first['endpoints'] == [
        {'end': ('B', 1), 'kilometre_source': ('A', 16), 'kilometres': 0.0},
        {'end': ('B', 4), 'kilometre_source': ('B', 4), 'kilometres': 0.5625},
    ]
    assert first['saved_length_m'] == 563 and second['saved_length_m'] == 750
    assert missing['status'] == 'missing_kilometres' and missing['saved_length_m'] == 500
    assert {row['kind'] for row in report['movements']} == {'route', 'path', 'itinerary'}
    assert all(row['after_distance_m'] - row['before_distance_m'] in (63, 250, 313) for row in report['movements'])
    original = project_from(docs, paths, catalog)
    output = project_from({**docs, **changed}, paths, catalog)
    assert all(a[:2] == b[:2] for a, b in zip(_movement_manifest(original).values(), _movement_manifest(output).values(), strict=True))


def test_multiple_selected_lengths_remap_each_original_distance_span_once(marked_chain):
    docs, paths, catalog, operation = marked_chain
    project = project_from(docs, paths, catalog)
    view = _movement_manifest(project)
    identity = next(key for key in view if key[0] == 'itinerary' and key[2][0] == 'I:chain:forward')
    sequence = view[identity][0]
    position = 0
    offsets = []
    for a, b in zip(sequence, sequence[1:]):
        edge = project.edge_between(a, b)
        length = project.model(edge).contents[9].values[1]
        if edge in {('B', 20), ('B', 23)}:
            offsets.append(position)
        position += length
    first, second = offsets
    docs['A'], _ = set_safety_margins(docs['A'], 'I:chain:forward', [
        {'position_m': value, 'safety_margin_m': 30 + index}
        for index, value in enumerate((first + 250, second + 250, position))
    ])
    with pytest.raises(ValueError, match='explicit map_itinerary_safety_margins'):
        transform(docs, paths, catalog, 'B', operation)
    changed, report = transform(docs, paths, catalog, 'B', {**operation, 'map_itinerary_safety_margins': True})
    assert sorted(changed) == ['A', 'B']
    mapped, = report['mapped_safety_margin_profiles']
    assert [item['position_m'] for item in mapped['after']] == [first + 281.5, second + 63 + 375, position + 313]
    assert [item['safety_margin_m'] for item in mapped['after']] == [30, 31, 32]


def test_review_guard_and_original_missing_data_noop(marked_chain):
    docs, paths, catalog, operation = marked_chain
    row = operation['edges'][0]
    with pytest.raises(ValueError, match='saved Edge length differs'):
        transform(docs, paths, catalog, 'B', {**operation, 'edges': [{**row, 'expected_length_m': 499}]})
    with pytest.raises(ValueError, match='calculated length differs'):
        transform(docs, paths, catalog, 'B', {**operation, 'edges': [{**row, 'expected_calculated_length_m': 562}]})
    missing, = operation['edges'][2:]
    changed, report = transform(docs, paths, catalog, 'B', {**operation, 'edges': [missing]})
    assert not changed and report['edges'][0]['status'] == 'missing_kilometres'
