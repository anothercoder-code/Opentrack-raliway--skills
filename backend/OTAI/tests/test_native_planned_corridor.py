import pytest

from opentrack_ai.current_archive import catalogs, course_factories, native_planned_corridor as planned, writer as w
from opentrack_ai.current_archive.native_corridors import array, dictionary
from opentrack_ai.current_archive.zero_generation import native_signal_routes as ns


def record(kind, version, layout, *, overrides=None, parents=None):
    defaults = {'@': None, 'f': 0.0, 'i': 0}
    overrides = overrides or {}
    groups = [(shape, overrides.get(i, [defaults[code] for code in shape])) for i, shape in enumerate(layout)]
    return ns.obj([(kind, version), *(parents or [('NSObject', 0)])], groups)


def row(cid, index, station, arrival, departure, *, day=0, reference=None):
    return record('OTTimetable', 9, course_factories.TT, overrides={
        0: [17], 1: [ns.string(cid)], 2: [ns.string(reference) if reference else None],
        3: [index], 4: [1], 5: [ns.string(station)], 6: [ns.string(arrival)], 7: [ns.string(departure)],
        9: [array([])], 15: [day, day, 0, 0],
    })


def course_catalog(cid):
    course = record('OTCourse', 11, catalogs.LAYOUTS['OTCourse'][1], overrides={0: [ns.string(cid)], 5: [1]})
    root = record('OTCourseList', 3, ['i', '@', '@', '@', '@'], parents=[('OTMutableArray', 0), ('NSObject', 0)],
                  overrides={1: [array([])], 2: [array([])], 3: [array([])], 4: [array([course])]})
    return w.dump_verified(root)


def test_planned_rows_use_saved_order_and_absolute_day_offsets_for_reverse_course():
    table = dictionary({'W1#1': row('W1', 1, 'A', '00:02:00', 'HH:MM:SS', day=1),
                        'W1#0': row('W1', 0, 'B', 'HH:MM:SS', '23:58:00')})
    result = planned.planned_rows(course_catalog('W1'), w.dump_verified(table), {'A': 0, 'B': 2400}, ['W1'])
    assert result['W1'] == [
        {'row_key': 'W1#0', 'station_sign': 'B', 'distance_m': 2400, 'arrival_s': None, 'departure_s': 86280},
        {'row_key': 'W1#1', 'station_sign': 'A', 'distance_m': 0, 'arrival_s': 86520, 'departure_s': None},
    ]


@pytest.mark.parametrize(('relative', 'message'), [(None, 'go backwards'), ('OTHER', 'relative interval')])
def test_invalid_planned_clocks_and_relative_rows_look_different(relative, message):
    table = dictionary({'E1#0': row('E1', 0, 'A', '08:00:00', '08:01:00', reference=relative),
                        'E1#1': row('E1', 1, 'B', '08:00:00', '08:10:00')})
    with pytest.raises(ValueError, match=message):
        planned.planned_rows(course_catalog('E1'), w.dump_verified(table), {'A': 0, 'B': 2500}, ['E1'])


def test_display_authoring_preserves_native_actual_graph_and_appends_real_version_fields():
    event = record('OTCorridorSimEvent', 0, ['f', 'f', 'i'], overrides={0: [60.0], 1: [120.0], 2: [1]})
    events = dictionary({'E1': array([event])})
    controller = record('OTTCorridorSimController', 1, ['@'] * 4,
                        overrides={0: [dictionary({})], 1: [events], 2: [dictionary({})], 3: [dictionary({})]})
    topology = record('OTTCorridorTopoController', 0, ['@'] * 3,
                      overrides={0: [array([])], 1: [dictionary({})], 2: [dictionary({})]})
    root = record('OTCorridorDocument', 11, planned.DIAGRAM[:24],
                  overrides={0: [controller], 1: [topology], 7: [50.0, 90.0], 13: [0x850C]})
    proof = {'E1': [{'arrival_s': 10, 'departure_s': None}, {'arrival_s': 75, 'departure_s': 110}]}
    path = 'D:/rail/OTDocuments/Planned Corridor.otsimcor'
    result = planned.display_document(root, 1000, path, proof, show_actual=False, time_format='mm:ss')
    fresh, _ = w.load_next_compatible(result)
    controller, topology = planned.corridor_shape(fresh)
    assert fresh.clazz.version == 13 and controller.clazz.version == 2
    assert w.fingerprint(controller.contents[1].value) == w.fingerprint(events)
    assert controller.contents[4].value.contents[0].value == 0
    assert fresh.contents[13].value == (0x850C & ~planned.SHOW_ACTUAL) | planned.SHOW_PLANNED
    assert fresh.contents[7].values == [0.0, 170.0]
    assert fresh.contents[24].values == [0, 2]
    assert w.elements(fresh.contents[25].value) == []
