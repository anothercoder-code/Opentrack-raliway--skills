"""Read the original directional buffer Route records without assigning replacement IDs."""

from collections import Counter, defaultdict
from typing import Annotated

from pydantic import Field, StrictInt

from ..errors import APIError
from . import path_functions as native, route_factory, writer
from .bundle_tools import Source
from .multi_document.core import ident
from .next_tools import NextFunctions
from .route_discovery_tools import main_signal
from .tools import Input


class InspectBufferRoutes(Input):
    source: Source
    offset: Annotated[StrictInt, Field(ge=0)] = 0
    limit: Annotated[StrictInt, Field(ge=1, le=200)] = 50


def _id(obj):
    return obj.contents[0].value


def _mates(end, ends):
    return [mate for mate in ends[end.contents[8].value] if mate.contents[8].value == _id(end) and mate is not end]


def _edge(source, target, ends):
    matches = []
    for mate in _mates(source, ends):
        for slot in (9, 10):
            edge = mate.contents[slot].value
            if (edge is not None and writer.kind(edge) == 'OTEdgeModel' and edge not in matches
                    and any(edge.contents[a].value is mate and edge.contents[b].value is target for a, b in ((7, 8), (8, 7)))
                    and any(target.contents[index].value is edge for index in (9, 10))):
                matches.append(edge)
    return matches[0] if len(matches) == 1 else None


def inspect_archive(root):
    native.hierarchy(root, [('OTDocument', 4), ('NSObject', 0)])
    models = native.mutable_array(root.contents[2].value)
    duplicates = {key: count for key, count in sorted(Counter(map(_id, models)).items()) if count > 1}
    ends = defaultdict(list)
    for end in models:
        if writer.kind(end) in ('OTEndModel', 'OTConnModel'):
            ends[_id(end)].append(end)
    rows = []
    ambiguous = []
    all_ends = {id(end) for matches in ends.values() for end in matches}
    for owner in (model for model in models if writer.kind(model) == 'OTEndModel' and main_signal(model)):
        group = owner.contents[15].value
        if group is None:
            continue
        for route in route_factory.wrapper(group, 'OTRouteList'):
            native.shape(route, 'OTRoute')
            nodes = native.mutable_array(route.contents[0].value)
            if (len(nodes) < 2 or nodes[0] is not owner or route.contents[5].values[4] != -1
                    or any(id(node) not in all_ends or writer.kind(node) != 'OTEndModel' for node in nodes)
                    or nodes[-1].contents[11].value is not None):
                continue
            terminal = nodes[-1]
            mates = _mates(terminal, ends)
            buffers = [mate for mate in mates if route_factory.physical_buffer(terminal, mate)]
            if not buffers:
                continue
            name, array_id, start_id = ident(route)
            sequence = [_edge(a, b, ends) for a, b in zip(nodes, nodes[1:])]
            if len(mates) != 1 or start_id != _id(owner) or any(edge is None for edge in sequence):
                ambiguous.append({'route': name, 'array_id': array_id, 'start_id': start_id, 'buffer_end_id': _id(terminal)})
                continue
            station = terminal.contents[12].value
            length = sum(edge.contents[9].values[1] for edge in sequence)
            rows.append({'name': name, 'array_id': array_id, 'start_id': start_id, 'end_ids': list(map(_id, nodes)),
                         'edge_ids': list(map(_id, sequence)), 'distance_m': length, 'buffer_end_id': _id(terminal),
                         'buffer_paired_end_id': _id(buffers[0]), 'terminal_signal_id': None,
                         'station_sign': native.string(station.contents[7].value) if station is not None else None,
                         'station_reference_end_ids': [_id(end) for end in nodes if end.contents[12].value is station
                                                       and station is not None and end.contents[20].value == 2]})
    return {'routes': rows, 'ambiguous_routes': ambiguous, 'duplicate_graphic_ids': duplicates,
            'full_project_validation_performed': False, 'native_execution_tested': False}


class BufferRouteInspection(NextFunctions):
    def inspect_buffers(self, args):
        path, blob, root, _ = self.checked(args.source)
        try:
            report = inspect_archive(root)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            raise APIError('CURRENT_BUFFER_ROUTE_INSPECTION', str(error)[:500]) from error
        rows = report['routes']
        report['resolved_route_count'] = len(rows)
        report['routes'] = rows[args.offset:args.offset + args.limit]
        if self.secure_bytes(path) != blob:
            raise APIError('SOURCE_CHANGED', 'The inspected buffer Route source changed', str(path))
        return {**report, 'source': args.source.model_dump()}


def inspect_tool(root):
    return ('opentrack_inspect_native_buffer_routes',
            'Read exact local unsignalized-buffer Routes in a SHA-bound current worksheet and report ambiguous graphic IDs.',
            InspectBufferRoutes, BufferRouteInspection(root).inspect_buffers)
