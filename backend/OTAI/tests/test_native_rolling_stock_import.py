import os
from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import catalogs as c, writer as w
from opentrack_ai.current_archive.native_rolling_stock_import_tools import (
    ImportNativeStock, NativeRollingStockImport, categories, import_stock, validate_saved_stock,
)
from opentrack_ai.current_archive.operating_plan_edit import text
from opentrack_ai.current_archive.pre_service_project import validate_pre_service_project
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation.empty_project import build_empty_project
from opentrack_ai.current_archive.zero_generation import native_signal_routes as n
from opentrack_ai.errors import APIError

from test_empty_project import sources, stable_fixture_reads
from test_itinerary_lifecycle import course_archive
from test_operating_plan_edit import dictionary, native_record, row


def wrapped(kind, rows=()):
    return n.obj([(kind, 0), ('OTMutableArray', 0), ('NSObject', 0)], [('@', [n.arr(rows)])])


def stock(speed):
    color = n.obj([('NSColor', 0), ('NSObject', 0)], [('c', [0]), ('ff', [0.0, 1.0])])
    point = native_record('OTDPoint', 0, ['iii'], {0: [0, 100, 1]})
    diagram = native_record('OTDDiagram', 3, ['iiiiiii', '@', '@', '@', '@', 'i', '@', '@'], {
        1: [n.arr([point])], 2: [n.arr()], 3: [n.arr()], 4: [color],
        6: [n.string('curve')], 7: [wrapped('OTEfficiencyArray')],
    })
    engine = native_record('OTEngine', *c.LAYOUTS['OTEngine'], {
        0: [17], 1: [n.string('Motor')], 2: [0, 70, 22, 1.0, 4, 0.0], 7: [speed], 16: [n.arr([diagram])],
    })
    engine.clazz.superclass = w.Class(b'OTVehicle', 0, w.Class(b'NSObject', 0))
    reference = native_record('OTTrainEngine', *c.LAYOUTS['OTTrainEngine'], {0: [n.string('Motor')], 1: [1]})
    train = native_record('OTTrain', *c.LAYOUTS['OTTrain'], {
        0: [n.string('Passenger')], 2: [wrapped('OTDecelerationArray'), n.arr([reference]), n.arr()],
        3: [n.string('Category')],
    })
    category = native_record('OTTrainCategory', 19, CATEGORY_LAYOUT, {
        1: [n.string('Category')], 2: [color], 10: [wrapped('OTDelayIntervalArray')],
        12: [wrapped('OTDelayPriorityArray')], 13: [wrapped('OTPerformanceIntervalArray')],
        14: [wrapped('OTPerformanceIntervalArray')], 17: [color],
    })
    train_list = n.obj([('OTTrainList', 3), ('OTMutableArray', 0), ('NSObject', 0)],
                       [('i', [17]), ('@', [n.arr([category])]), ('@', [n.arr()]), ('@', [n.arr([train])])])
    return n.arr([engine]), train_list


def plan_for(depot, trains):
    return SimpleNamespace(roots={'depot': depot, 'trains': trains},
                           roles={'depot': 'depot', 'trains': 'trains'})


def options(*, alias_engine='Donor Motor', policy='require_identical'):
    return SimpleNamespace(formations={'Passenger': 'New Passenger'}, engines={'Motor': alias_engine},
                           categories={'Category': 'New Category'}, existing=policy)


def test_native_stock_import_adds_dependencies_and_preserves_old_entries():
    target_depot, target_train_list = stock(250)
    from_depot, from_train_list = stock(110)
    target = plan_for(target_depot, target_train_list)
    archived = [w.fingerprint(item) for item in [*c.engine_items(target_depot), *c.train_items(target_train_list)]]
    result = import_stock(target, from_depot, from_train_list, options())
    assert result['formation_summaries'][0]['maximum_speed_kmh'] == 110
    assert result['engines']['added'] == ['Donor Motor']
    assert result['categories']['added'] == ['New Category']
    depot = w.load_next_compatible(w.dump_verified(target_depot))[0]
    train_list = w.load_next_compatible(w.dump_verified(target_train_list))[0]
    assert [w.fingerprint(item) for item in (c.engine_items(depot)[0], c.train_items(train_list)[0])] == archived
    train = c.train_items(train_list)[1]
    assert (text(train, 0), text(train, 3), c.bound_engine_names(train)) == (
        'New Passenger', 'New Category', ['Donor Motor'])
    assert 'New Category' in categories(train_list)
    assert c.bound_engine_names(c.train_items(from_train_list)[0]) == ['Motor']


def test_same_name_requires_exact_stock_and_retries_can_reuse_it():
    target = plan_for(*stock(250))
    depot, trains = stock(110)
    with pytest.raises(ValueError, match='fresh alias or an exact match'):
        import_stock(target, depot, trains, options(alias_engine='Motor'))
    import_stock(target, depot, trains, options())
    repeated = import_stock(target, depot, trains, options())
    assert repeated['engines']['reused_identical'] == ['Donor Motor']
    assert repeated['formations']['reused_identical'] == ['New Passenger']
    with pytest.raises(ValueError, match='fresh alias or an exact match'):
        import_stock(target, depot, trains, options(policy='reject'))


def example_stock():
    depot, train_list = stock(130)
    train_list.contents[0].value = 16
    engine, = c.engine_items(depot)
    engine.contents[0].value = 1
    diagram, = c.array(engine.contents[16].value)
    table = diagram.contents[7].value.contents[0].value
    w.set_elements(table, [native_record('OTEfficiency', 0, ['iff'], {0: [70, 0.125, 45.0]})])
    category, = c.array(train_list.contents[1].value)
    category.clazz.version = 11
    category.contents = category.contents[:15]
    formation, = c.array(train_list.contents[3].value)
    formation.clazz.version = 12
    formation.contents = formation.contents[:19]
    unset = w.WireFloat(bytes.fromhex('0000c0ff'), b'f', 'little')
    formation.contents[1].values[2] = unset
    refs = formation.contents[2].values[1]
    w.set_elements(refs, [native_record('OTTrainEngine', 0, ['@', 'i'], {0: [n.string('Motor')], 1: [3]})
                          for _ in range(2)])
    brake = native_record('OTDeceleration', 1, ['iff'], {0: [0, -0.5, -0.5]})
    w.set_elements(formation.contents[2].values[0].contents[0].value, [brake])
    car = native_record('OTTrailer', 2, ['i', '@', 'iiifif', 'iii', 'i', 'f'], {
        0: [0], 1: [n.string('Stock Trailer')], 2: [0, 70, 30, 1.0, 4, 1.0],
        3: [0, 6, 1], 4: [160], 5: [12.0],
    })
    car.clazz.superclass = w.Class(b'OTVehicle', 0, w.Class(b'NSObject', 0))
    w.set_elements(formation.contents[2].values[2], [car])
    return depot, train_list


def test_original_example_stock_decoding_and_current_archive_readback():
    donor = example_stock()
    original = [w.fingerprint(archive) for archive in donor]
    target = plan_for(*stock(250))
    result = import_stock(target, *donor, options())
    assert [w.fingerprint(archive) for archive in donor] == original
    assert result['legacy_class_upgrades']['source_train_list_marker'] == 16
    summary, = result['formation_summaries']
    assert (summary['length_m'], summary['cold_mass_t'], summary['maximum_speed_kmh']) == (74, 210, 130)
    assert [row['position'] for row in summary['formation']] == [1, 2, 3]
    depot, train_list = (w.load_next_compatible(w.dump_verified(item))[0] for item in target.roots.values())
    engine = c.engine_items(depot)[1]
    diagram, = c.array(engine.contents[16].value)
    efficiency, = c.array(diagram.contents[7].value.contents[0].value)
    assert engine.contents[0].value == 1 and efficiency.contents[0].values == [70, 0.125, 45.0]
    category = categories(train_list)['New Category']
    assert category.clazz.version == 19 and category.contents[20].value == 420.0
    assert category.contents[22].value == 1 and category.contents[24].values == [-1.0, 1.0]
    train = c.train_items(train_list)[1]
    assert train.clazz.version == 16 and train.contents[19].value == 100.0
    assert train.contents[1].values[2].bits == bytes.fromhex('0000c0ff')
    trailer, = c.array(train.contents[2].values[2])
    assert trailer.clazz.version == 3 and trailer.contents[-1].value == 0.0
    assert trailer.contents[0].value == 0 and trailer.contents[-2].value == 12.0
    repeated = import_stock(target, *donor, options())
    assert repeated['formations']['reused_identical'] == ['New Passenger']


def test_original_average_deceleration_cache_requires_active_braking_table():
    depot, train_list = example_stock()
    train, = c.array(train_list.contents[3].value)
    train.contents[12].values[0] = 4
    with pytest.raises(ValueError, match='active saved braking table'):
        import_stock(plan_for(*stock(250)), depot, train_list, options())


def test_efficiency_table_requires_exact_original_owned_record():
    depot, train_list = example_stock()
    engine, = c.engine_items(depot)
    diagram, = c.array(engine.contents[16].value)
    row, = c.array(diagram.contents[7].value.contents[0].value)
    row.contents[0].encodings = [b'i', b'i', b'f']
    with pytest.raises(ValueError, match='Unsupported OTEfficiency field-group encoding'):
        import_stock(plan_for(*stock(250)), depot, train_list, options())


@pytest.mark.parametrize(('changed', 'error'), [
    ({'OTData/empty.courses': course_archive(A01=['Main'])}, 'zero saved Courses'),
    ({'OTData/empty.timetable': w.dump_verified(dictionary({'A01#0': row('A01', 'EA', 0, '10:10:00')}))},
     'zero saved timetable rows'),
])
def test_pre_service_binding_refuses_existing_operation_rows(changed, error):
    root = 'D:/Test/Prepare'
    files, _ = build_empty_project(*sources(), document_names=['Main'], execution_root=root,
                                   run_filename='starter.run', train_types=['Freight'])
    with pytest.raises(ValueError, match=error):
        validate_pre_service_project({**files, **changed}, run_file='starter.run', execution_root=root)


def test_saved_stock_requires_exact_native_category_and_engine_closure():
    depot, trains = stock(110)
    report = validate_saved_stock(w.dump_verified(depot), w.dump_verified(trains))
    assert report['formations'] == [{'name': 'Passenger', 'category': 'Category', 'engine_array_order': ['Motor'], 'length_m': 22}]
    with pytest.raises(ValueError, match='Missing Engine'):
        validate_saved_stock(w.dump_verified(n.arr()), w.dump_verified(trains))
    w.set_elements(trains.contents[1].value, [])
    with pytest.raises(ValueError, match='unknown category'):
        validate_saved_stock(w.dump_verified(depot), w.dump_verified(trains))


@pytest.mark.skipif(os.name != 'nt', reason='Complete project preview validates the native Windows execution path')
def test_complete_stock_project_preview_and_existing_increment_use_same_archive_bytes(tmp_path, stable_fixture_reads):
    home = tmp_path / 'OTProjects/StationSource'
    donor = tmp_path / 'OTProjects/StockDonor'
    tools = NativeRollingStockImport(tmp_path)
    home.mkdir(parents=True)
    donor.mkdir(parents=True)

    def source(path, blob):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        return {'path': path.relative_to(tmp_path).as_posix(), 'sha256': sha(blob)}

    raw, _ = build_empty_project(*sources(), document_names=['Main'], execution_root=home.as_posix(),
                                 run_filename='starter.run', train_types=['Freight'])
    files = {name: source(home / name, blob)['sha256'] for name, blob in raw.items()}
    depot, trains = (w.dump_verified(part) for part in stock(110))
    requested = {'source_project': {'project_directory': 'OTProjects/StationSource', 'run_file': 'starter.run',
                                    'execution_root': home.as_posix(), 'files': files,
                                    'complete_project_inventory': True},
                 'donor_depot': source(donor / 'sample.depot', depot),
                 'donor_trains': source(donor / 'sample.trains', trains),
                 'formations': {'Passenger': 'P9 Demo'}}
    archive = tools.import_rolling_stock(ImportNativeStock.model_validate(requested))
    complete = tools.import_rolling_stock(ImportNativeStock.model_validate({
        **requested, 'target_scope': 'pre_service_project', 'target_directory': 'OTProjects/Stocked',
    }))
    assert archive['manifest']['format'] == 'opentrack-operating-plan-increment-v1'
    assert complete['target_scope'] == 'pre_service_project' and not complete['saved']
    assert complete['structural_readback_verified']
    assert complete['pre_service_validation']['course_count'] == complete['pre_service_validation']['timetable_count'] == 0
    assert complete['saved_stock_validation']['formations'][0]['name'] == 'P9 Demo'
    for role in ('depot', 'trains'):
        assert complete['member_sha256'][f'OTData/empty.{role}'] == archive['manifest']['files'][f'empty.{role}']['sha256']
    assert complete['preserved_member_sha256']['OTDocuments/Main.opentrack'] == files['OTDocuments/Main.opentrack']
    assert not (tmp_path / 'OTProjects/Stocked').exists()
    requested['donor_depot']['sha256'] = '0' * 64
    with pytest.raises(APIError) as stale:
        tools.import_rolling_stock(ImportNativeStock.model_validate({
            **requested, 'target_scope': 'pre_service_project', 'target_directory': 'OTProjects/Stocked',
        }))
    assert stale.value.code == 'NATIVE_STOCK_SOURCE'
