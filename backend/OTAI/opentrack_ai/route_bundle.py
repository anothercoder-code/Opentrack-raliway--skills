"""Pure directional-graph information compiler; never opens an archive or simulator.

Input links are resolved directional End transitions, not raw drawing edges.
All generated payloads are checked against the production models. Native graph
binding and actual signal interpretation remain the applying server's job.
"""
import argparse
import json
import math
import sys
from collections import deque
from typing import Annotated, Literal
from pydantic import Field, StrictBool, StrictInt
from .models import Input, ArchiveName, DefineRoute, DefinePath, DefineItinerary, GenerateOperations


class RouteBundleError(ValueError):
    """Fail-closed invalid input or incomplete graph search."""


def _fail(message):
    raise RouteBundleError(message)


def _object(value, allowed, required, label):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        _fail(label + ': missing or unknown fields')


def _ref(value):
    _object(value, ('document', 'end_id'), ('document', 'end_id'), 'End reference')
    if not isinstance(value['document'], str) or not 1 <= len(value['document']) <= 100:
        _fail('Invalid document')
    if type(value['end_id']) is not int or value['end_id'] < 0:
        _fail('End IDs must be nonnegative integers, never inferred or coerced')
    return value['document'], value['end_id']


def _json_ref(key):
    return {'document': key[0], 'end_id': key[1]}


def _list(value, label, low=0, high=10000):
    if not isinstance(value, list) or not low <= len(value) <= high:
        _fail(label + ': invalid list or size limit')
    return value


def compile_route_bundle(spec):
    """Discover signal-boundary routes and compile uniquely selected simple paths.

    A budget exhaustion raises, never returns an allegedly complete prefix.
    cycle_policy=reject rejects any directed graph cycle; simple_paths explicitly
    excludes repeated directional Ends. Crossings are NOT graph connectivity.
    """
    _object(spec, ('project', 'run_file', 'route_name_prefix', 'nodes', 'links',
                   'paths', 'itineraries', 'cycle_policy', 'max_expansions', 'max_routes'),
            ('project', 'route_name_prefix', 'nodes', 'links', 'paths', 'itineraries'), 'bundle')
    if not isinstance(spec['project'], str) or not spec['project'].strip():
        _fail('Explicit target project required')
    if 'run_file' in spec and (not isinstance(spec['run_file'], str) or not spec['run_file'].strip()):
        _fail('run_file must be a nonempty string when supplied')
    prefix = spec['route_name_prefix']
    if not isinstance(prefix, str) or not prefix:
        _fail('Explicit route_name_prefix required')
    policy = spec.get('cycle_policy', 'reject')
    if policy not in ('reject', 'simple_paths'):
        _fail('cycle_policy must be reject or simple_paths')
    budget = spec.get('max_expansions', 50000)
    route_limit = spec.get('max_routes', 10000)
    if type(budget) is not int or not 1 <= budget <= 500000:
        _fail('max_expansions must be 1..500000')
    if type(route_limit) is not int or not 1 <= route_limit <= 10000:
        _fail('max_routes must be 1..10000')
    nodes = {}
    for row in _list(spec['nodes'], 'nodes', 2):
        _object(row, ('document', 'end_id', 'main_signal', 'signal_aspects'),
                ('document', 'end_id', 'main_signal'), 'node')
        key = _ref({k: row[k] for k in ('document', 'end_id')})
        if key in nodes:
            _fail('Duplicate directional End ID')
        if type(row['main_signal']) is not bool:
            _fail('main_signal must be an explicit boolean')
        if 'signal_aspects' in row:
            if not row['main_signal']:
                _fail('Signal aspects on non-main node')
            aspects = _list(row['signal_aspects'], 'signal_aspects', 1, 64)
            if any(type(x) is not int or not 0 <= x <= 10000 for x in aspects):
                _fail('Invalid explicit signal aspect code')
        nodes[key] = row
    adjacency = {key: [] for key in nodes}
    lengths = {}
    for row in _list(spec['links'], 'links', 1, 50000):
        _object(row, ('source', 'target', 'length_m'), ('source', 'target', 'length_m'), 'link')
        a, b = _ref(row['source']), _ref(row['target'])
        if a not in nodes or b not in nodes:
            _fail('Link references unknown directional End')
        if (a, b) in lengths:
            _fail('Parallel directional transitions are ambiguous in native node-only Route payloads')
        length = row['length_m']
        try:
            valid_length = type(length) in (int, float) and math.isfinite(length) and length >= 0
        except OverflowError:
            valid_length = False
        if not valid_length:
            _fail('length_m must be finite and nonnegative')
        lengths[a, b] = length
        adjacency[a].append(b)
    for values in adjacency.values():
        values.sort()
    if policy == 'reject':
        degrees = dict.fromkeys(nodes, 0)
        for a, b in lengths:
            degrees[b] += 1
        queue = deque(sorted(n for n in nodes if degrees[n] == 0))
        visited = 0
        while queue:
            a = queue.popleft(); visited += 1
            for b in adjacency[a]:
                degrees[b] -= 1
                if degrees[b] == 0:
                    queue.append(b)
        if visited != len(nodes):
            _fail('Directed cycle found; select simple_paths explicitly to exclude repeated Ends')
    expansions = 0

    def walks(start, stop, via=()):
        nonlocal expansions
        path = [start]
        seen = {start}
        stack = [None]
        while stack:
            if stack[-1] is None:
                expansions += 1
                if expansions > budget:
                    _fail('Search budget exhausted; no partial bundle returned')
                if len(path) > 4096:
                    _fail('Walk exceeds compiler node bound')
                if len(path) > 1 and stop(path[-1]):
                    if not via or tuple(n for n in path if n in via) == tuple(via):
                        yield tuple(path)
                    stack.pop(); seen.remove(path.pop())
                    continue
                stack[-1] = iter(adjacency[path[-1]])
            nxt = next(stack[-1], None)
            if nxt is None:
                stack.pop(); seen.remove(path.pop())
            elif nxt not in seen:
                path.append(nxt); seen.add(nxt); stack.append(None)

    def distance(walk):
        try:
            result = math.fsum(lengths[a, b] for a, b in zip(walk, walk[1:]))
        except OverflowError:
            _fail('Accumulated distance is not finite')
        if not math.isfinite(result):
            _fail('Accumulated distance is not finite')
        return result

    route_walks = []
    for start in sorted(n for n in nodes if nodes[n]['main_signal']):
        for walk in walks(start, lambda end: nodes[end]['main_signal']):
            if sum(a[0] != b[0] for a, b in zip(walk, walk[1:])) > 1:
                _fail('Route through multiple document boundaries is not verified by native writer')
            if 'signal_aspects' not in nodes[start]:
                _fail('Explicit signal_aspects required at each discovered Route start')
            route_walks.append(walk)
            if len(route_walks) > route_limit:
                _fail('Route count limit exceeded; no partial bundle returned')
    route_walks.sort()
    routes = []
    route_by_walk = {}
    for index, walk in enumerate(route_walks, 1):
        route = {'name': prefix + str(index).zfill(4), 'nodes': [_json_ref(n) for n in walk],
                 'signal_aspects': list(nodes[walk[0]]['signal_aspects']), 'allow_occupied_entry': False}
        DefineRoute.model_validate(route)
        distance(walk)
        routes.append(route); route_by_walk[walk] = route
    paths = []; path_walks = {}
    for row in sorted(_list(spec['paths'], 'paths', 1, 1000), key=lambda r: str(r.get('name', '')) if isinstance(r, dict) else ''):
        _object(row, ('name', 'start', 'end', 'via', 'nodes'), ('name', 'start', 'end'), 'path request')
        if not isinstance(row['name'], str) or row['name'] in path_walks:
            _fail('Invalid or duplicate Path name')
        start, end = _ref(row['start']), _ref(row['end'])
        if start not in nodes or end not in nodes or not nodes[start]['main_signal'] or not nodes[end]['main_signal']:
            _fail('Path endpoints must be known main-signal directional Ends')
        if start == end:
            _fail('Closed Paths are not supported by the simple-path policy')
        via = tuple(_ref(v) for v in _list(row.get('via', []), 'via', 0, 100))
        if len(set(via)) != len(via) or any(n not in nodes or n in (start, end) for n in via):
            _fail('via must contain distinct known intermediate Ends')
        if 'nodes' in row:
            walk = tuple(_ref(v) for v in _list(row['nodes'], 'explicit path nodes', 2, 4096))
            if walk[0] != start or walk[-1] != end or len(set(walk)) != len(walk):
                _fail('Explicit Path endpoint mismatch or repeated End')
            if any((a, b) not in lengths for a, b in zip(walk, walk[1:])):
                _fail('Explicit Path is not physically connected in the supplied directed graph')
            if tuple(n for n in walk if n in via) != via:
                _fail('Explicit Path does not honor ordered via Ends')
        else:
            candidates = walks(start, lambda n: n == end, via)
            walk = next(candidates, None)
            if walk is None:
                _fail('No directed simple Path satisfies request: ' + row['name'])
            if next(candidates, None) is not None:
                _fail('Ambiguous Path; supply ordered via or explicit nodes: ' + row['name'])
        refs = []; offset = 0
        for i in range(1, len(walk)):
            if nodes[walk[i]]['main_signal']:
                route = route_by_walk.get(walk[offset:i + 1])
                if route is None:
                    _fail('Path segment missing from complete Route discovery')
                refs.append({'document': walk[offset][0], 'start_id': walk[offset][1], 'name': route['name']})
                offset = i
        path = {'name': row['name'], 'routes': refs}
        DefinePath.model_validate(path)
        paths.append(path); path_walks[row['name']] = walk
    itineraries = []; itinerary_names = set()
    for row in _list(spec['itineraries'], 'itineraries', 0, 1000):
        _object(row, ('name', 'paths'), ('name', 'paths'), 'itinerary')
        DefineItinerary.model_validate(row)
        if row['name'] in itinerary_names:
            _fail('Duplicate Itinerary name')
        itinerary_names.add(row['name']); combined = ()
        for name in row['paths']:
            if name not in path_walks:
                _fail('Itinerary references unknown Path')
            walk = path_walks[name]
            if combined and combined[-1] != walk[0]:
                _fail('Itinerary Paths are disconnected; automatic reversals are not inferred')
            combined += walk if not combined else walk[1:]
        if len(set(combined)) != len(combined):
            _fail('Itinerary repeats directional Ends; cyclic itineraries are outside compiler scope')
        itineraries.append({'name': row['name'], 'paths': list(row['paths'])})
    itineraries.sort(key=lambda row: row['name'])
    base = {'project': spec['project']}
    if 'run_file' in spec:
        base['run_file'] = spec['run_file']
    batches = []
    for kind, values in (('routes', routes), ('paths', paths), ('itineraries', itineraries)):
        for offset in range(0, len(values), 100):
            batch = {**base, 'label': 'Compiled ' + kind + ' ' + str(offset // 100 + 1), kind: values[offset:offset + 100]}
            GenerateOperations.model_validate(batch)
            batches.append(batch)
    return {'schema_version': 1, 'evidence_level': 'user_graph_compiled',
            'native_archive_written': False, 'native_simulation_verified': False,
            'cycle_policy': policy, 'complete_within_policy': True,
            'counts': {'routes': len(routes), 'paths': len(paths), 'itineraries': len(itineraries), 'search_expansions': expansions},
            'routes': routes, 'paths': paths, 'itineraries': itineraries,
            'path_distances_m': {name: distance(walk) for name, walk in path_walks.items()},
            'native_apply_spec': {'tool': 'opentrack_generate_operations', 'ordered_batches': batches,
                                  'chain_draft_project_between_batches': True},
            'limitations': ['User graph connectivity and main-signal assertions require native verification before application.',
                            'Generated route names are deterministic; all supplied End IDs, Path and Itinerary names are preserved.',
                            'No inferred crossing connectivity, reversal, signal aspect, protection, archive ID, or simulation result.',
                            'Existing target names and graph are not inspected; native application may reject collisions or stale bindings.',
                            'Batches are not one transaction; use each returned draft_project as the next batch project; source project is not overwritten.']}


class GraphEnd(Input):
    document: str = Field(min_length=1, max_length=100)
    end_id: StrictInt = Field(ge=0)


class GraphNode(GraphEnd):
    main_signal: StrictBool
    signal_aspects: list[Annotated[StrictInt, Field(ge=0, le=10000)]] | None = Field(default=None, min_length=1, max_length=64)


class GraphLink(Input):
    source: GraphEnd
    target: GraphEnd
    length_m: Annotated[float, Field(strict=True, ge=0)]


class GraphPath(Input):
    name: ArchiveName
    start: GraphEnd
    end: GraphEnd
    via: list[GraphEnd] = Field(default_factory=list, max_length=100)
    nodes: list[GraphEnd] | None = Field(default=None, min_length=2, max_length=4096)


class GraphItinerary(Input):
    name: ArchiveName
    paths: list[ArchiveName] = Field(min_length=1, max_length=1000)


class RouteBundleInput(Input):
    project: str = Field(min_length=1)
    run_file: str | None = Field(default=None, min_length=1)
    route_name_prefix: str = Field(min_length=1, max_length=150)
    nodes: list[GraphNode] = Field(min_length=2, max_length=10000)
    links: list[GraphLink] = Field(min_length=1, max_length=50000)
    paths: list[GraphPath] = Field(min_length=1, max_length=1000)
    itineraries: list[GraphItinerary] = Field(max_length=1000)
    cycle_policy: Literal['reject', 'simple_paths'] = 'reject'
    max_expansions: StrictInt = Field(default=50000, ge=1, le=500000)
    max_routes: StrictInt = Field(default=10000, ge=1, le=10000)


def compile_tool(args):
    from .errors import APIError
    try:
        return compile_route_bundle(args.model_dump(exclude_none=True))
    except RouteBundleError as error:
        raise APIError('ROUTE_BUNDLE_INVALID', str(error)) from error


def tool_definitions():
    return [('opentrack_compile_route_bundle',
             'Compile a caller-asserted directional End graph into all simple next-main-signal Routes, unique requested Paths and continuous Itineraries. Strict direction, ambiguity rejection and fail-closed search budgets. Produces schema-validated ordered native apply specifications only; no archive access, writes, topology verification or simulation.',
             RouteBundleInput, compile_tool)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='JSON file or - for stdin')
    args = parser.parse_args(argv)
    try:
        if args.input == '-':
            spec = json.load(sys.stdin)
        else:
            with open(args.input, encoding='utf-8') as stream:
                spec = json.load(stream)
        print(json.dumps(compile_route_bundle(spec), ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, TypeError, OSError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
