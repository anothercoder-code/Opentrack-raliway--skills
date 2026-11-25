from opentrack_ai.current_archive.native_corridors import Alignment, NativeNetwork
from opentrack_ai.current_archive.native_corridor_conflicts import route_conflicts, route_warnings
from opentrack_ai.current_archive.native_corridor_occupations import project_occupations


def point(index, time, end, to=None, position=None, kind=0):
    output = {'index': index, 'time_s': float(time), 'from_end': end, 'to_end': to,
              'factor': 0.0, 'kind': kind}
    if position is not None:
        output.update(distance_m=position, st1_course_distance_m=position)
    return output


def traces(kind, rows):
    title = 'Route Reservation' if kind == 'step1' else 'Route Release'
    return (f'// Produced by OpenTrack: test\n// {title} of Course: T\n// Desc. : OT_{kind}\n'
            '// x-Legend: [s]\n// y-Legend: [km]\n// Scenario: covered\n'
            + ''.join(f'{time}\t{distance}\n' for time, distance in rows))


def test_partial_end_holds_without_fabricating_a_release():
    net = NativeNetwork.__new__(NativeNetwork)
    net.edges = {'ab': ('a', 'b', 100), 'bc': ('br', 'c', 100)}
    net.related = {'a': 'ar', 'ar': 'a', 'b': 'br', 'br': 'b', 'c': 'cr', 'cr': 'c'}
    net.station_ends = {'A': {'a'}, 'C': {'c'}}
    axis = Alignment(net, [{'edges': [{'edge_id': 'ab', 'from_end': 'a'}, {'edge_id': 'bc', 'from_end': 'br'}]}],
                     [{'station': 'A', 'end_id': 'a'}, {'station': 'C', 'end_id': 'c'}])
    motion = [[point(0, 10, 'a', 'b', 0), point(1, 20, 'br', 'c', 100),
               point(2, 30, 'c', position=200)]]
    bank = {
        1: [point(0, 10, 'a'), point(1, 10, 'b'), point(2, 10, 'c')],
        2: [point(0, 25, 'a'), point(1, 25, 'b'), point(2, 30, 'br'), point(3, 30, 'c')],
    }
    net.events = lambda _, choice: iter(bank[choice])
    data = project_occupations(net, axis, 'T', motion, '// Scenario: covered\n',
                               traces('step1', [(10, 0), (10, .2)]),
                               traces('step2', [(25, 0), (25, .1), (30, .1)]))
    assert data['encoded']
    assert data['recorded_interval_distance_m'] == 100
    assert data['release']['excluded_counts'] == {'no_independent_nonzero_step': 2}
    assert not data['full_motion_alignment_covered']
    assert [(i['from_m'], i['to_m']) for i in data['intervals']] == [(0, 100)]


def test_parallel_track_at_same_distance_is_not_counted():
    net = NativeNetwork.__new__(NativeNetwork)
    net.edges = {'ab': ('a', 'b', 100), 'xy': ('x', 'y', 100)}
    net.related = {'a': 'ar', 'ar': 'a', 'b': 'br', 'br': 'b',
                   'x': 'xr', 'xr': 'x', 'y': 'yr', 'yr': 'y'}
    net.station_ends = {'A': {'a'}, 'B': {'b'}}
    axis = Alignment(net, [{'edges': [{'edge_id': 'ab', 'from_end': 'a'}]},
                           {'edges': [{'edge_id': 'xy', 'from_end': 'x'}]}],
                     [{'station': 'A', 'end_id': 'a'}, {'station': 'B', 'end_id': 'b'}])
    motion = [[point(0, 10, 'a', 'b', 0), point(1, 20, 'b', position=100)]]
    bank = {1: [point(0, 10, 'x'), point(1, 10, 'y')], 2: [point(0, 25, 'a'), point(1, 25, 'b')]}
    net.events = lambda _, choice: iter(bank[choice])
    data = project_occupations(net, axis, 'T', motion, '// Scenario: covered\n',
                               traces('step1', [(10, 0), (10, .1)]),
                               traces('step2', [(25, 0), (25, .1)]))
    assert not data['encoded']
    assert data['reservation']['excluded_counts'] == {'not_unique_travelled_path_or_step_position': 2}


def test_conflict_needs_same_course_visible_motion_and_excludes_unarchived_tag():
    rows = ['// Produced by OpenTrack: test', '// Desc. : OT_messages',
            'WARNING\t00:00:11\tT\tCourse T: Braking for Route S_A\t(A)',
            'WARNING\t00:00:21\tT\tCourse T: Braking for Route S_B\t(B)',
            'WARNING\t00:00:12\tW\tCourse W: Braking for Route S_X\t(A)']
    messages = route_warnings('\n'.join(rows))
    net = NativeNetwork.__new__(NativeNetwork)
    events = [point(0, 11.2, None, kind=4), point(1, 12.3, None, kind=18),
              point(2, 12.6, None, kind=4), point(3, 21.0, None, kind=4)]
    net.events = lambda _: iter(events)
    selected = route_conflicts(net, 'T', [[point(0, 10, 'a'), point(1, 20, 'b')]], messages)
    assert [r['key'] for r in selected['events']] == ['00:00:11#T']
    assert selected['events'][0]['conflict_tag'] == 0
    assert selected['excluded_counts']['outside_unique_retained_motion_segment'] == 1
    assert selected['excluded_counts']['native_types_requiring_unarchived_tag'] == 1
