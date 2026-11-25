"""Check ordinary station turnout traversal using the selected saved Route edges."""

from . import catalogs, writer
from .signal_type_workflow.core import MAIN, ROLES


def track_legs(end):
    return [end.contents[slot].value for slot in (9, 10) if end.contents[slot].value is not None]


def same_platform_membership(project, first, second, first_station, second_station):
    if first[0] == second[0]:
        return first_station is not None and first_station is second_station
    if (writer.kind(first_station) != 'OTStationModel' or writer.kind(second_station) != 'OTStationModel'
            or first_station not in project.models[first[0]] or second_station not in project.models[second[0]]):
        return False
    first_sign = first_station.contents[7].value
    second_sign = second_station.contents[7].value
    return (first_sign is not None and bool(sign := catalogs.text(first_sign))
            and second_sign is not None and sign == catalogs.text(second_sign))


def station_turnout_kind(project, nodes, index):
    """Classify an ordinary paired turnout along the native movement's selected legs."""
    key = nodes[index]
    related = project.related(key)
    if related != project.actual_related(key):
        return None
    arrival, departure = project.model(key), project.model(related)
    station = arrival.contents[12].value
    if (writer.kind(arrival) != 'OTEndModel' or writer.kind(departure) != 'OTEndModel'
            or writer.kind(station) != 'OTStationModel' or departure.contents[12].value is not station
            or arrival.contents[20].value != 1 or departure.contents[20].value != 1):
        return None
    inward, outward = track_legs(arrival), track_legs(departure)
    if sorted((len(inward), len(outward))) != [1, 2]:
        return None

    first = None
    inside_before, outside_before = False, True
    if index > 0:
        previous = nodes[index - 1]
        first = project.model(project.edge_between(previous, key))
        if first not in inward:
            return None
        previous_station = project.model(previous).contents[12].value
        approach_station = project.model(project.actual_related(previous)).contents[12].value
        inside_before = (approach_station is station
                         and same_platform_membership(project, previous, key, previous_station, station))
        outside_before = (previous[0] == key[0] and previous_station is approach_station
                          and approach_station is not station)

    inside_after, outside_after = False, True
    if index + 1 < len(nodes):
        following = nodes[index + 1]
        second = project.model(project.edge_between(key, following))
        if second is first or second not in outward:
            return None
        following_station = project.model(following).contents[12].value
        inside_after = following_station is station
        outside_after = (following_station is not station
                         and project.model(project.related(following)).contents[12].value is following_station)

    if inside_before and inside_after:
        return 'interior'
    if outside_before and inside_after:
        return 'entry'
    if inside_before and outside_after:
        signal = arrival.contents[11].value
        if signal is not None and signal.contents[8].values[0] in MAIN and signal.contents[8].values[1] == ROLES['exit']:
            return 'exit'
    return None
