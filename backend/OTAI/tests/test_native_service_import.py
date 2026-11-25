from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, path_functions, writer
from opentrack_ai.current_archive import native_service_import_tools as transfer
from opentrack_ai.current_archive.native_timetable_import_tools import CourseMapping
from opentrack_ai.current_archive.operating_plan_edit import text
from test_native_itinerary_import import state
from test_native_rolling_stock_import import stock
from test_operating_plan_edit import sample


def service_plan(speed=160):
    plan = sample()
    depot, trains = stock(speed)
    plan.roots.update(trains=trains, depot=depot)
    plan.roles['depot'] = 'depot'
    for course in plan.courses().values():
        course_factories.settext(course, 3, 'Passenger')
        course_factories.settext(course, 4, 'main')
    return plan


def request(*mappings):
    return SimpleNamespace(
        courses=[CourseMapping(source_course=source, target_course=target) for source, target in mappings],
        train_mapping={}, itinerary_mapping={}, import_actual_times=False,
    )


def test_selected_courses_and_native_references_roundtrip(monkeypatch):
    donor, target = service_plan(), service_plan()
    main = donor.course('A01')
    course_factories.settext(main, 11, 'Saved donor controls')
    course_factories.put(main, 6, 90)
    donor.row('A01', 1).contents[15].values[:2] = [1, 1]
    course_factories.settext(donor.row('A01', 1), 18, '9')
    destination = donor.row('A01', 0)
    connection, = catalogs.array(destination.contents[9].value)
    course_factories.put(connection, 4, 2)
    course_factories.put(connection, 8, 1.25)
    course_factories.settext(destination, 13, '23:35:18')
    monkeypatch.setattr(transfer, 'movement_bindings', lambda *_: {})
    run = {'run': b'TrainType#main#\n'}
    pristine = {key: writer.dump_verified(root) for key, root in target.roots.items()}
    source_table = writer.fingerprint(donor.table)
    report = transfer.import_services(target, donor.roots, run, run, request(('A01', 'B01'), ('A02', 'B02')))
    assert report['native_references'] == {'connections': 1, 'interval_rows': 2}
    assert report['imported_courses'] == 2 and report['imported_rows'] == 4
    assert report['matched_stations'] == ['EA', 'WB']
    assert writer.fingerprint(donor.table) == source_table
    target.validate()
    changes = {role: writer.dump_verified(target.roots[role]) for role in ('courses', 'timetable')}
    transfer.verify_preserved_members(changes, {'roles': target.roles, 'files': pristine}, {'B01', 'B02'})
    fresh_table = course_factories.timetable(writer.load_next_compatible(changes['timetable'])[0])
    b1, = catalogs.array(fresh_table['B01#0'].contents[9].value)
    assert [text(b1, slot) for slot in (0, 1, 2, 3, 5, 6)] == [
        'B01', 'B02', 'EA', '00:01:00', '00:04:00', 'EA',
    ]
    assert b1.contents[4].value == 2 and b1.contents[8].value == 1.25
    assert text(fresh_table['B01#0'], 13) == 'HH:MM:SS'
    assert text(fresh_table['B01#1'], 18) == '9'
    assert fresh_table['B01#1'].contents[15].values[:2] == [1, 1]
    assert text(fresh_table['B02#1'], 2) == 'B01'
    fresh_courses = catalogs.course_items(writer.load_next_compatible(changes['courses'])[0])
    b01 = next(course for course in fresh_courses if text(course, 0) == 'B01')
    assert text(b01, 11) == 'Saved donor controls' and b01.contents[6].value == 90
    assert text(b01, 3) == 'Passenger'


def test_selection_cannot_strand_connection_or_interval():
    donor = service_plan()
    with pytest.raises(ValueError, match='both ends of connections'):
        transfer.closed_references(donor.rows(), {'A02'})
    with pytest.raises(ValueError, match='both ends of connections'):
        transfer.closed_references(donor.rows(), {'A01'})
    row = donor.row('A01', 0)
    writer.set_elements(row.contents[9].value, [])
    with pytest.raises(ValueError, match='both ends of interval_rows'):
        transfer.closed_references(donor.rows(), {'A01'})


def test_changed_train_engine_detected_under_identical_names():
    original, changed = service_plan(), service_plan(speed=100)
    with pytest.raises(ValueError, match='Engine definition differs'):
        transfer.stock_bindings(original.roots, changed.roots, {'Passenger': 'Passenger'})
    renamed = service_plan()
    train, = catalogs.train_items(renamed.roots['trains'])
    course_factories.settext(train, 0, 'New Passenger')
    transfer.stock_bindings(original.roots, renamed.roots, {'Passenger': 'New Passenger'})


def test_bound_movement_rejects_modified_traversed_worksheet():
    donor, _ = state('D:/Donor')
    target, _ = state('D:/Target')
    assert set(transfer.movement_bindings(donor, target, {'Service': 'Service'})) == {'Line'}
    target['documents']['Line'], _ = path_functions.set_description(
        target['documents']['Line'], 'OTRoute', 'R0', 'Changed worksheet',
    )
    with pytest.raises(ValueError, match='Traversed worksheet differs'):
        transfer.movement_bindings(donor, target, {'Service': 'Service'})
