import pytest

from opentrack_ai.current_archive.native_corridors import Alignment, NativeNetwork, observed_segments, compare


def event(index, time, a, b=None, fraction=0):
    return dict(index=index, kind=0, from_end=a, to_end=b, time_s=time, factor=fraction)


@pytest.fixture
def layout():
    network = NativeNetwork.__new__(NativeNetwork)
    network.related = {'a': 'ar', 'ar': 'a', 'b': 'br', 'br': 'b', 'c': 'cr', 'cr': 'c', 'x': 'xr', 'xr': 'x'}
    network.edges = {'1': ('a', 'b', 100), '2': ('br', 'c', 100), '3': ('br', 'x', 100)}
    network.station_ends = {'A': {'a'}, 'B': {'b', 'br'}, 'C': {'c'}}
    path = [{'edge_id': '1', 'from_end': 'a'}, {'edge_id': '2', 'from_end': 'br'}]
    stations = [{'station': 'A', 'end_id': 'a'}, {'station': 'B', 'end_id': 'br'}, {'station': 'C', 'end_id': 'c'}]
    return network, path, stations


def test_reverse_alias_and_station_coordinates(layout):
    network, path, stations = layout
    alignment = Alignment(network, [{'edges': path}], stations)
    assert network.reverse_alignment(path) == [{'edge_id': '2', 'from_end': 'c'}, {'edge_id': '1', 'from_end': 'b'}]
    assert alignment.position(event(0, 0, 'cr', 'b', .75)) == 125
    assert alignment.stations == [('A', 0), ('B', 100), ('C', 200)]


def test_off_corridor_break_and_reverse_join(layout):
    network, path, stations = layout
    alignment = Alignment(network, [{'edges': path}], stations)
    events = [event(0, 0, 'a'), event(1, 5, 'ar', 'b', .5), event(2, 10, 'br'),
              event(3, 15, 'br', 'x', .5), event(4, 20, 'x'), event(5, 25, 'b'),
              event(6, 30, 'br', 'ar', .5), event(7, 35, 'a')]
    network.events = lambda *args: iter(events)
    segments, outside, isolated = observed_segments(network, alignment, 'Course')
    assert outside == 2 and isolated == 0
    assert [[point['distance_m'] for point in s] for s in segments] == [[0, 50, 100], [100, 50, 0]]
    st1 = [(0, 0), (5, 50), (10, 100), (20, 200), (25, 250), (30, 300), (35, 350)]
    assert [compare(segment, st1) for segment in segments] == [0, 0]


def test_discontinuous_alignment_and_wrong_station_reference_fail(layout):
    network, path, stations = layout
    with pytest.raises(ValueError, match='not continuous'):
        Alignment(network, [{'edges': [path[0], {'edge_id': '2', 'from_end': 'c'}]}], stations)
    with pytest.raises(ValueError, match='does not belong'):
        Alignment(network, [{'edges': path}], [{'station': 'A', 'end_id': 'b'}, stations[-1]])
