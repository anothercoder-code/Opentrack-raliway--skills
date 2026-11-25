"""Native archive checks for bulk indications and train-category signals."""

import pytest

from opentrack_ai.current_archive import path_functions, route_factory, writer
from opentrack_ai.current_archive.movement_edits import _movement_project
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.signal_operating_fields import append_route_aspects, edit_category_signals
from opentrack_ai.current_archive.signal_operating_tools import CoastingOperation, PerformanceOperation
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_cross_document_route_native_edit import NATIVE_PATHS, REFERENCE, fixture
from test_itinerary_native_edit import schematic_document


def codes(holder, owner):
    rows = route_factory.wrapper(holder, 'OTSigIndList')
    assert all(row.contents[1].value is owner for row in rows)
    return [row.contents[0].value for row in rows]


def test_bulk_appends_native_metric_codes_preserving_existing_order_and_companion():
    docs, catalog = fixture()
    available = [{'start_end': ['A', 0], 'speeds_kmh': [40, 55]}]
    changed, report = append_route_aspects(docs, NATIVE_PATHS, catalog, [['A', 0]], available)
    assert report['updated_route_count'] == 1
    assert set(changed) == {'A'}
    assert report['signals'][0]['after'] == [0, 4, 1055]
    assert report['routes'][0]['appended'] == [4, 1055]
    project = _movement_project({**docs, **changed}, NATIVE_PATHS, catalog)
    start = project.model(('A', 0))
    route = project.owned(('A', 0), 'OTRoute', tuple(REFERENCE.values()))
    signal = start.contents[11].value
    assert codes(signal.contents[10].value, start) == codes(route.contents[4].value, route) == [0, 4, 1055]
    fragment = project.owned(('B', 0), 'OTRoute', tuple(REFERENCE.values()))
    assert codes(fragment.contents[4].value, fragment) == []
    assert not append_route_aspects({**docs, **changed}, NATIVE_PATHS, catalog, [('A', 0)], available)[0]


def train_list(names):
    values = {'i': 0, 'f': 0.0, 'c': 0, '@': None}
    categories = [
        native.obj([('OTTrainCategory', 19), ('NSObject', 0)],
                   [(enc, [native.string(name)] if n == 1 else [values[e] for e in enc])
                    for n, enc in enumerate(CATEGORY_LAYOUT)])
        for name in names
    ]
    root = native.obj([('OTTrainList', 3), ('OTMutableArray', 0), ('NSObject', 0)], [
        ('i', [17]), ('@', [native.arr(categories)]), ('@', [native.arr()]), ('@', [native.arr()]),
    ])
    return writer.dump_verified(root)


def test_current_category_signals_follow_bound_order_and_keep_other_entries():
    document, _ = schematic_document(generate.spec(), [('left', 0), ('right', 0)])
    docs = {'A': document}
    paths = {'A': 'A.opentrack'}
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
    trains = train_list(['First', 'Second'])
    performance = PerformanceOperation(
        action='insert', kind='performance_category', document='A', end_id=1,
        name='Performance', x=30, y=20,
        rows=[{'category': 'Second', 'delay_s': 12.5, 'performance_percent': 90}],
    )
    coasting = CoastingOperation(
        action='insert', kind='coasting', document='A', end_id=5,
        name='Coasting', x=230, y=20, lower_speed_kmh=30, upper_speed_kmh=60,
        rows=[{'category': 'Second', 'enabled': True}],
    )
    changes, report = edit_category_signals(docs, paths, catalog, trains,
                                           [performance.model_dump(), coasting.model_dump()])
    perf, coast = report['signals']
    assert report['category_order'] == ['First', 'Second']
    assert perf['after']['categories'] == [
        {'category': 'First', 'delay_s': 0.0, 'performance_percent': 100.0},
        {'category': 'Second', 'delay_s': 12.5, 'performance_percent': 90.0},
    ]
    assert coast['after']['categories'] == [{'category': 'First', 'enabled': False},
                                           {'category': 'Second', 'enabled': True}]
    project = _movement_project(changes, paths, catalog)
    signal = project.model(('A', perf['signal_id']))
    assert signal.contents[8].values[0] == 50
    assert path_functions.mutable_array(signal.contents[14].value)[1].contents[0].values == [12.5, 90.0]
    change = CoastingOperation(action='edit', kind='coasting', document='A', end_id=5, signal_id=coast['signal_id'],
                               rows=[{'category': 'First', 'enabled': True}])
    _, receipt = edit_category_signals(changes, paths, catalog, trains, [change.model_dump()])
    assert all(row['enabled'] for row in receipt['signals'][0]['after']['categories'])
    with pytest.raises(ValueError, match='run-bound category'):
        edit_category_signals(docs, paths, catalog, trains,
                              [{**performance.model_dump(), 'rows': [{'category': 'Other',
                               'delay_s': 0, 'performance_percent': 100}]}])
