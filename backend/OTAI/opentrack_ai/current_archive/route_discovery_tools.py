"""Find next main-signal and reviewed physical-buffer Routes in a saved graph."""

from collections import defaultdict
import heapq
from itertools import count
from typing import Annotated

from pydantic import Field, StrictBool, StrictInt

from ..errors import APIError
from . import catalogs, route_factory, writer
from .bundle_tools import CourseBundles, Source
from .itinerary_edit_tools import EditableItineraryProject, bound_dest_catalog, run_infrastructure_paths
from .next_tools import NextFunctions
from .operation_tools import Name
from .tools import Input, sha


class DiscoverRoutes(Input):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    dest_catalog: Source
    document: Name | None = None
    start_offset: Annotated[StrictInt, Field(ge=0)] = 0
    start_limit: Annotated[StrictInt, Field(ge=1, le=100)] = 12
    routes_per_start: Annotated[StrictInt, Field(ge=1, le=100)] = 20
    max_expansions_per_start: Annotated[StrictInt, Field(ge=1, le=500000)] = 50000
    max_hops: Annotated[StrictInt, Field(ge=1, le=4096)] = 1000
    include_buffer_stops: StrictBool = False


def main_signal(end):
    signal = end.contents[11].value
    return signal is not None and signal.contents[8].values[0] in {1, 2, 24, 25, 26}


def next_edges(project, node):
    opposite = project.model(project.actual_related(node))
    for slot in (9, 10):
        edge = opposite.contents[slot].value
        if edge is None:
            continue
        left, right = edge.contents[7].value, edge.contents[8].value
        destination = project.key(right if left is opposite else left)
        yield destination, project.edge_between(node, destination), edge.contents[9].values[1]


def discover_from(project, start, args, existing):
    order = count()
    queue = [(0, next(order), (start,), ())]
    candidates, expanded, hop_limit = [], 0, False
    while queue and len(candidates) < args.routes_per_start and expanded < args.max_expansions_per_start:
        distance, _, nodes, edges = heapq.heappop(queue)
        end = nodes[-1]
        expanded += 1
        terminal = project.model(end)
        buffer = (args.include_buffer_stops and len(nodes) > 1 and terminal.contents[11].value is None
                  and route_factory.physical_buffer(terminal, project.model(project.related(end))))
        if len(nodes) > 1 and (main_signal(terminal) or buffer):
            boundaries = sum(a[0] != b[0] for a, b in zip(nodes, nodes[1:]))
            candidate = {
                'end_sequence': nodes, 'edge_sequence': edges, 'distance_m': distance,
                'document_boundaries': boundaries, 'existing_route_names': existing.get(nodes, []),
                'one_route_storage_compatible': boundaries <= 1,
            }
            if buffer:
                candidate['terminal_kind'] = 'buffer_stop'
            candidates.append(candidate)
            continue
        for target, edge, metres in next_edges(project, end):
            if target in nodes:
                continue
            if len(edges) == args.max_hops:
                hop_limit = True
            else:
                heapq.heappush(queue, (distance + metres, next(order), (*nodes, target), (*edges, edge)))
    return {'start': start, 'routes': candidates, 'expanded_states': expanded,
            'exhausted': not queue and not hop_limit}


class RouteDiscovery(NextFunctions, CourseBundles):
    def discover(self, args):
        bound = {name: self.checked(source) for name, source in args.documents.items()}
        run_path, run, scope_check, scope = self.checked_document_list(args, bound)
        dest_path, dest, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run_path, run, dest_path)
        documents = {name: record[1] for name, record in bound.items()}
        project = EditableItineraryProject(
            documents, document_paths=run_infrastructure_paths(run),
            expected_hashes={name: sha(blob) for name, blob in documents.items()}, complete_document_set=True,
        )
        project.check_dest_catalog(dest, allow_external=True)
        if args.document is not None and args.document not in documents:
            raise APIError('CURRENT_ROUTE_DISCOVERY', 'Select a document bound by this run')
        starts = sorted(project.key(end) for name in documents
                        if args.document is None or name == args.document
                        for end in project.ends(name) if writer.kind(end) == 'OTEndModel' and main_signal(end))
        existing = defaultdict(list)
        for route in project.routes:
            if writer.kind(project.model(project.owners[id(route)])) == 'OTEndModel':
                existing[tuple(project.route_view(route))].append(catalogs.text(route.contents[1].value))
        origins = [discover_from(project, start, args, existing)
                   for start in starts[args.start_offset:args.start_offset + args.start_limit]]
        scope_check()
        for path, data in [(run_path, run), (dest_path, dest), *((item[0], item[1]) for item in bound.values())]:
            if self.secure_bytes(path) != data:
                raise APIError('SOURCE_CHANGED', 'A bound route discovery input changed', str(path))
        next_offset = args.start_offset + len(origins)
        return {'document_scope': scope, 'main_signal_starts': len(starts), 'origins': origins,
                'next_start_offset': next_offset if next_offset < len(starts) else None,
                'page_exhausted': all(origin['exhausted'] for origin in origins),
                'native_execution': False}


def tool_definitions(root):
    from .buffer_route_inspection import inspect_tool

    service = RouteDiscovery(root)
    return [('opentrack_discover_network_routes',
             'Enumerate next-main-signal or reviewed buffer-stop Route candidates over a bound project.',
             DiscoverRoutes, service.discover), inspect_tool(root)]
