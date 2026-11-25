import pytest

from opentrack_ai.current_archive import native_diagram_batch as batch, writer as w
from opentrack_ai.current_archive.native_corridors import array, dictionary, mapping
from opentrack_ai.current_archive.native_planned_corridor import DIAGRAM
from opentrack_ai.current_archive.zero_generation import native_signal_routes as ns


def wrap(name, version, groups):
    return ns.obj([(name, version), ('NSObject', 0)], groups)


def trajectory(points):
    return wrap('OTSimEventArray', 0, [('@', [array(points)]), ('@', [array([])])])


def point(time, distance, starts=None):
    groups = [('f', [time]), ('f', [distance])]
    if starts is None:
        return wrap('OTCorridorBasicSimEvent', 0, groups)
    return wrap('OTCorridorSimEvent', 0, [*groups, ('i', [starts])])


def sample_corridor():
    positions = dictionary({'12': ns.obj([('NSNumber', 0), ('NSValue', 0), ('NSObject', 0)],
                            [('*', [w.CString(w.SharedString(b's'))]), ('s', [0])])})
    topology = wrap('OTTCorridorTopoController', 0, [('@', [array([])]), ('@', [positions]), ('@', [dictionary({})])])
    traces = dictionary({'E1': trajectory([point(10.0, 0.0, 1), point(20.0, 300.0)])})
    controller = wrap('OTTCorridorSimController', 1, [('@', [dictionary({})]), ('@', [traces]),
                                                     ('@', [dictionary({})]), ('@', [dictionary({})])])
    stations = array([wrap('OTCorridorStation', 0, [('@', [ns.string(sign)]), ('iiii', [index, distance, distance, 0]),
                      ('iiii', [100, 1, 0, 1])]) for index, (sign, distance) in enumerate((('A', 0), ('B', 300)))])
    defaults = {'@': None, 'f': 0.0, 'i': 0}
    values = {0: [controller], 1: [topology], 6: [0], 7: [0.0, 60.0], 13: [0x8508], 15: [stations]}
    return w.dump_verified(wrap('OTCorridorDocument', 11, [
        (group, values.get(index, [defaults[kind] for kind in group])) for index, group in enumerate(DIAGRAM[:24])]))


def test_live_seed_preserves_native_positions_and_clears_all_actual_banks():
    source = sample_corridor()
    target = 'D:/case/OTDocuments/Zoom.otsimcor'
    seed, receipt = batch.live_drawing(source, target, 'Zoom', {'A', 'B'}, [20, 45])
    assert receipt['time_window_s'] == [20, 45]
    assert receipt['station_positions_m'] == {'A': 0, 'B': 300}
    batch.verify_frozen_drawing(seed, receipt, target)
    original, _ = w.load_next_compatible(source)
    assert 'E1' in mapping(original.contents[0].value.contents[1].value)
    with pytest.raises(ValueError, match='expected actual Course'):
        batch.inspect_result(seed, {**receipt, 'courses': ['E1']})


def test_compressed_actual_points_and_reversed_movement_match_distance_trace():
    source = trajectory([point(10.0, 50.0, 1), point(20.0, 0.0), point(30.0, 25.0)])
    st1 = ('// Produced by OpenTrack: fixture\n// Distance/Time of Course: E1\n'
           '// Desc.   : OT_st1\n// x-Legend: [s]\n// y-Legend: [km]\n'
           '10.00\t0.000\n20.00\t0.050\n30.00\t0.075\n')
    summary = batch.actual_course('E1', source, 50, st1)
    assert summary['point_count'] == 3 and summary['segment_count'] == 1
    assert summary['st1_max_delta_residual_m'] == pytest.approx(0.0)
    with pytest.raises(ValueError, match='Invalid original diagram point'):
        batch.actual_course('E1', trajectory([point(20.0, 0.0, 1), point(10.0, 50.0)]), 50)


def test_original_scenario_filename_binds_basename_and_numeric_scenario_exactly():
    files = ['Zoom.0.otsimcor', 'Zoom.17.otsimcor', 'Other.17.otsimcor', 'Zoom.17.eps']
    assert batch.output_file(files, 'Zoom', 17) == 'Zoom.17.otsimcor'
    with pytest.raises(ValueError, match='Expected one native Zoom.1.otsimcor'):
        batch.output_file(files, 'Zoom', 1)
    with pytest.raises(ValueError, match='Expected one native Zoom.17.otsimcor'):
        batch.output_file([*files, 'Zoom.017.otsimcor'], 'Zoom', 17)
