"""Review ordinary through-block Routes inside a multi-worksheet berth."""

from . import catalogs, route_factory, writer


def is_main_role(project, key, role):
    end = project.model(key)
    signal = end.contents[11].value
    return (writer.kind(end) == 'OTEndModel' and signal is not None and writer.kind(signal) == 'OTSignalModel'
            and signal.contents[7].value is end and signal.contents[8].values[:2] == [1, role])


def through_route(project, nodes):
    """Check a saved block-to-block/exit Route traversing one reciprocal hop."""
    if len(nodes) < 3 or not is_main_role(project, nodes[0], 3) or not any(
            is_main_role(project, nodes[-1], role) for role in (3, 4)):
        return False
    if sum(a[0] != b[0] for a, b in zip(nodes, nodes[1:])) != 1:
        return False
    owner = project.model(nodes[0])
    peer = project.model(project.related(nodes[0]))
    if (writer.kind(peer) != 'OTEndModel' or peer.contents[11].value is not None
            or owner.contents[7].value is peer.contents[7].value):
        return False
    routes = route_factory.wrapper(owner.contents[15].value, 'OTRouteList')
    return (len(routes) == 1 and routes[0].contents[5].values[4] > 0 and bool(routes[0].contents[11].value & 1)
            and list(project.route_view(routes[0])) == list(nodes))


def station_sign(end):
    member = end.contents[12].value
    return catalogs.text(member.contents[7].value) if member is not None and writer.kind(member) == 'OTStationModel' else None


def continued_berth_after_block(project, nodes, index, track):
    """Confirm the actual route suffix reaches one shared-sign physical exit."""
    if not track or not is_main_role(project, nodes[index], 3):
        return False
    sign = station_sign(project.model(nodes[index]))
    if not sign:
        return False
    last_block = index
    for position in range(index + 1, len(nodes)):
        previous, current = nodes[position - 1:position + 1]
        arriving = project.model(current)
        departure = project.model(project.actual_related(previous))
        if (station_sign(arriving) != sign or station_sign(departure) != sign or departure.contents[20].value != 1
                or any(sum(end.contents[slot].value is not None for slot in (9, 10)) != 1
                       for end in (arriving, departure)) or departure.contents[11].value is not None
                or writer.string(project.model(project.edge_between(previous, current)).contents[19].value) != track):
            return False
        if arriving.contents[20].value == 2:
            return is_main_role(project, current, 4) and through_route(project, nodes[last_block:position + 1])
        if arriving.contents[20].value != 1:
            return False
        if arriving.contents[11].value is not None:
            if not is_main_role(project, current, 3) or not through_route(project, nodes[last_block:position + 1]):
                return False
            last_block = position
    return False
