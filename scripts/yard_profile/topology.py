"""Pure native bytes: three eight-platform stations with two real main lines.

Twelve physical paired-End turnouts per station.  Four platform tracks in each
direction share real throat Edges, Safety Elements, Signals and stored Routes.
No application execution, publication or runtime interlocking claim is made.
"""
from __future__ import annotations

import copy
import hashlib

from opentrack_ai.current_archive import writer as w, catalogs as c, course_factories as cf
from opentrack_ai.current_archive import path_functions as pf, route_factory as rf
from opentrack_ai.current_archive.multi_document import core as cd, generate as g, operations as ops
from opentrack_ai.current_archive.multistation_timetable import topology as chain
from opentrack_ai.current_archive.zero_generation import topology as tp, native_signal_routes as ns
from opentrack_ai.current_archive.zero_operations import station_binding as sb, run_bundle as rb
from .block_helpers import _golden_block, _trace

SOURCE_KEYS = frozenset({'header', 'shapes', 'depot_template', 'trains_template',
                         'courses_template', 'timetable_template'})
SPEC_KEYS = frozenset({'stations', 'execution_root', 'block_profile'})
PROFILE = 'eight_platform_two_mains_5km'
CATALOGS = {role: 'OTData/chain.' + role for role in rb.CATALOG_KEYS}
LANES = tuple({'name': n, 'side': 0 if n[0] == 'D' else 1,
               'direction': 'forward' if n[0] == 'D' else 'reverse', 'y': y}
              for n, y in zip(('D1', 'D2', 'D3', 'D4', 'U1', 'U2', 'U3', 'U4'),
                              (70, 110, 170, 210, 310, 350, 410, 450)))
TRUNK = {'D': 'D4', 'U': 'U1'}
BRANCHES = {'D': ('D1', 'D2', 'D3'), 'U': ('U4', 'U3', 'U2')}
COMMON_ROLES = ('left', 'in_block', 'home', 'L1', 'L2', 'L3',
                'R3', 'R2', 'R1', 'out_b1', 'out_b2', 'right')
RELATIVE = dict(zip(COMMON_ROLES, (-2500, -1250, -750, -700, -650, -600,
                                  200, 250, 300, 1250, 2400, 2500)))
X = dict(zip(COMMON_ROLES, (20, 120, 230, 300, 370, 440,
                           1000, 1070, 1140, 1280, 1350, 1380)))
PLATFORM_RELATIVE = {'entry': -500, 'reference': 0, 'post': 100}
PLATFORM_X = {'entry': 550, 'reference': 850, 'post': 900}
ROOT_RECTS = {8: [80., 80., 1480., 650.], 9: [0., 0., 1463., 634.],
              10: [0., 0., 1463., 634.]}
PLATFORM_RECTS = [[580, y, 240, 16] for y in (82, 182, 322, 422)]
MAIN_DISTANCES = [0, 1250, 2400, 3750, 4250, 5000, 6250, 7400, 8750, 9250, 10000]
BLOCK_LENGTHS = [1250, 1150, 1350, 500]


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def configuration(spec):
    need(type(spec) is dict and set(spec) == SPEC_KEYS, 'Exact stations/execution_root/block_profile spec required')
    need(spec['block_profile'] == PROFILE, 'Only eight_platform_two_mains_5km is supported')
    chain._spec({'topology': 'chain', 'stations': spec['stations'],
                 'execution_root': spec['execution_root'], 'half_link_length_m': 2500})
    need(len(spec['stations']) == 3, 'Exactly three ordered stations required')
    return {r['id']: spec['execution_root'] + '/OTDocuments/' + r['id'] + '.opentrack'
            for r in spec['stations']}


def key(prefix, role):
    return prefix + '_' + role


def lane_data(name):
    return next(lane for lane in LANES if lane['name'] == name)


def common(direction, role):
    
    if direction == 'U' and role in ('left', 'right'):
        role = 'right' if role == 'left' else 'left'
    return key(direction, role)


def vertex_contract():
    out = {}
    for direction in ('D', 'U'):
        trunk_y = lane_data(TRUNK[direction])['y']
        for role in COMMON_ROLES:
            stem = common(direction, role)
            out[stem] = {'x': X[role] if direction == 'D' else 1400 - X[role],
                         'y': trunk_y, 'relative': RELATIVE[role] if direction == 'D' else -RELATIVE[role],
                         'direction': direction, 'role': role, 'lane': direction}
        for lane in (item for item in LANES if item['name'][0] == direction):
            for role in PLATFORM_RELATIVE:
                out[key(lane['name'], role)] = {
                    'x': PLATFORM_X[role] if direction == 'D' else 1400 - PLATFORM_X[role],
                    'y': lane['y'], 'relative': PLATFORM_RELATIVE[role] if direction == 'D' else -PLATFORM_RELATIVE[role],
                    'direction': direction, 'role': role, 'lane': lane['name']}
    return out


def _edge(a, b, contract, track):
    va, vb = contract[a], contract[b]
    left, right = (a, b) if va['relative'] < vb['relative'] else (b, a)
    return dict(key=a + '__' + b, **{'from': [left, 1], 'to': [right, 0]},
        length_m=abs(vb['relative'] - va['relative']), radius_m=0., gradient_per_mille=0.,
        track_type=1, loop_type=1, dlink_type=1, equal_speed=True, rack_rail=False,
        speeds=[dict(train_type='0', speed12_kmh=80, speed21_kmh=80)],
        remark='Native paired-End turnout; explicit schematic yard, shared throat resource',
        track_name=track, line_name='Guided Eight Platform Yard')


def topology_spec():
    contract = vertex_contract()
    vertices = [dict(key=stem, x=v['x'], y=v['y'], orientation='horizontal',
        names=[stem + '_L', stem + '_R'], insulated_joint=[False, False], axle_counter=[False, False])
        for stem, v in contract.items()]
    edges = []
    
    
    for direction in ('D', 'U'):
        trunk = TRUNK[direction]
        roles = [common(direction, r) for r in ('left', 'in_block', 'home', 'L1', 'L2', 'L3')]
        roles += [key(trunk, r) for r in ('entry', 'reference', 'post')]
        roles += [common(direction, r) for r in ('R3', 'R2', 'R1', 'out_b1', 'out_b2', 'right')]
        for a, b in zip(roles, roles[1:]):
            track = trunk if contract[a]['lane'] == trunk and contract[b]['lane'] == trunk else direction + '_MAIN'
            edges.append(_edge(a, b, contract, track))
    for direction in ('D', 'U'):
        for n, lane in enumerate(BRANCHES[direction], 1):
            route = [common(direction, 'L' + str(n)), key(lane, 'entry'),
                     key(lane, 'reference'), key(lane, 'post'), common(direction, 'R' + str(n))]
            for a, b in zip(route, route[1:]):
                edges.append(_edge(a, b, contract, lane))
    return {'vertices': vertices, 'edges': edges}


def signal_specs():
    specs = []
    for lane in LANES:
        specs.append(dict(lane=lane['name'], vertex=key(lane['name'], 'reference'), side=lane['side'],
                          label='EXIT', kind='exit', signal_type=1, role=4))
    for direction, side in (('D', 0), ('U', 1)):
        for label, vertex, kind, typ, role in (
            ('HOME', 'home', 'home', 1, 2), ('B1', 'out_b1', 'block', 25, 3),
            ('B2', 'out_b2', 'block', 25, 3), ('B3', 'in_block', 'block', 25, 3)):
            specs.append(dict(lane=direction, vertex=common(direction, vertex), side=side,
                              label=label, kind=kind, signal_type=typ, role=role))
    return specs


def _add_signals(blob, dn, ids):
    root, version = w.load_next_compatible(blob)
    models, byid = rf.document(root)
    ns.validate_topology(root)
    records = []
    for item in signal_specs():
        end = byid[ids[item['vertex']][item['side']]]
        need(end.contents[11].value is None, 'Fresh nonsignal End required')
        model_id = max(byid) + 1 + len(records)
        name = 'S_' + dn + '_' + item['lane'] + '_' + item['label']
        offset = -1 if item['side'] == 0 else 1
        block = item['kind'] == 'block'
        sight, flags = (400, 640) if block else (500, 644)
        alignment = [end.contents[i].value for i in (4, 5)]
        need(alignment == ([1, 0] if item['side'] == 0 else [2, 0]), 'Native horizontal End alignment required')
        ind = ns.obj([('OTSigInd', 0), ('NSObject', 0)], [('i', [0]), ('@', [end])])
        groups = [('i', [model_id]), ('f', [0.]),
            ('f', [ns.number(end.contents[2].value + 12 * offset)]),
            ('f', [ns.number(end.contents[3].value + 10 * offset)]),
            ('i', [alignment[0]]), ('i', [alignment[1]]), ('@', [None]), ('@', [end]),
            ('iii', [item['signal_type'], item['role'], 2]), ('iiii', [2, sight, flags, 0]),
            ('@', [g.wrapped('OTSigIndList', [ind])]), ('i', [0]), ('i', [7]),
            ('@', [ns.string(name)]), ('@', [ns.arr()]), ('@', [ns.arr()]), ('f', [0.])]
        signal = ns.obj([('OTSignalModel', 11), ('OTGraphicModel', 1), ('NSObject', 0)], groups)
        end.contents[11].value = signal
        models.append(signal)
        records.append({**item, 'signal_id': model_id, 'end_id': end.contents[0].value,
                        'name': name, 'alignment': alignment, 'flags': flags,
                        'show_icon': True, 'is_virtual': False})
    w.set_elements(root.contents[2].value, models)
    output = w.dump_verified(root, version)
    fresh, fv = w.load_next_compatible(output)
    made = {record['signal_id'] for record in records}
    fm, fi = rf.document(fresh)
    ns.validate_topology(fresh)
    for record in records:
        signal, end = fi[record['signal_id']], fi[record['end_id']]
        need(signal.contents[7].value is end and end.contents[11].value is signal,
             'Signal/End fresh readback differs')
        end.contents[11].value = None
    w.set_elements(fresh.contents[2].value, [model for model in fm if model.contents[0].value not in made])
    need(w.dump_verified(fresh, fv) == blob, 'Removing new Signals must restore exact graph bytes')
    return output, records


def ingress(lane):
    direction = lane[0]
    n = 3 if lane == TRUNK[direction] else BRANCHES[direction].index(lane) + 1
    return [common(direction, 'home')] + [common(direction, 'L' + str(i)) for i in range(1, n + 1)] + [key(lane, 'entry'), key(lane, 'reference')]


def egress(lane):
    direction = lane[0]
    n = 3 if lane == TRUNK[direction] else BRANCHES[direction].index(lane) + 1
    return [key(lane, 'reference'), key(lane, 'post')] + [common(direction, 'R' + str(i)) for i in range(n, 0, -1)] + [common(direction, 'out_b1')]


def _local_route(root, models, ids, side, stems, name):
    nodes = [models[ids[stem][side]] for stem in stems]
    ns.validate_movement(root, [node.contents[0].value for node in nodes])
    owner = nodes[0]
    aid = owner.contents[19].value + 1
    route = g.route(name, aid, owner.contents[0].value, nodes, -1)
    route.contents[12].values[0] = ns.arr([nodes[0], nodes[-1]])
    back = owner.contents[15].value.contents[0].value
    w.set_elements(back, pf.mutable_array(back) + [route])
    owner.contents[19].value = aid
    rf.validate_chain(root, route, [node.contents[0].value for node in nodes])
    return {'document': '', **cd.ref(route)}


def _project(docs, paths):
    return cd.Project(docs, document_paths=paths, expected_hashes={dn: sha(blob) for dn, blob in docs.items()},
                      complete_document_set=True)


def _index(p, dn):
    index = {}
    for end in p.ends(dn):
        name = c.text(end.contents[18].value)
        need(name.endswith(('_L', '_R')), 'Native End half identity required')
        stem, side = name[:-2], 0 if name.endswith('_L') else 1
        need(side not in index.setdefault(stem, {}), 'Duplicate named End half')
        index[stem][side] = end
    need(set(index) == set(vertex_contract()) and all(set(pair) == {0, 1} for pair in index.values()),
         'Exact forty-eight paired yard vertices required')
    return index


def _route_resources(p, route):
    nodes = p.route_view(route)
    
    return {(node[0], p.model(node).contents[7].value.contents[0].value) for node in nodes[1:]}


def validate(files, spec):
    """Independent full expected-graph checks; never the old parallel validator."""
    paths = configuration(spec)
    names = list(paths)
    need(type(files) is dict and set(files) == {'chain.run', *CATALOGS.values(),
         *('OTDocuments/' + dn + '.opentrack' for dn in names)}, 'Exact ten-member infrastructure bundle required')
    need(all(type(v) is bytes and v for v in files.values()), 'Immutable nonempty native bytes required')
    p = _project({dn: files['OTDocuments/' + dn + '.opentrack'] for dn in names}, paths)
    need(p.check_dest_catalog(files[CATALOGS['dest']]) == 8, 'Exactly eight full Itineraries required')
    station_catalog = c.station_items(w.load_next_compatible(files[CATALOGS['stations']])[0])
    need(set(station_catalog) == set(names), 'Station catalog membership differs')
    contract, topo = vertex_contract(), topology_spec()
    expected_signals = {(item['vertex'], item['side']): item for item in signal_specs()}
    expected_edges = {(tuple(e['from']), tuple(e['to'])): e for e in topo['edges']}
    inventories, resources = {}, {}
    for row in spec['stations']:
        dn = row['id']
        models, index = p.models[dn], _index(p, dn)
        counts = {kind: sum(w.kind(m) == kind for m in models) for kind in
                  ('OTEndModel', 'OTConnModel', 'OTElement', 'OTEdgeModel', 'OTSignalModel', 'OTStationModel')}
        need(len(models) == 209 and counts['OTEndModel'] + counts['OTConnModel'] == 96 and
             counts['OTElement'] == 44 and counts['OTEdgeModel'] == 52 and
             counts['OTSignalModel'] == 16 and counts['OTStationModel'] == 1, 'Exact yard model inventory differs')
        station = next(m for m in models if w.kind(m) == 'OTStationModel')
        need(c.text(station.contents[7].value) == dn and c.text(station_catalog[dn].contents[2].value) == row['name'],
             'One StationModel/catalog identity differs')
        need([station.contents[i].value for i in (2, 3, 4, 5)] == [700, 530, 0, 0], 'Station diagram placement differs')
        references, areas, turnouts = 0, 0, []
        for stem, pair in index.items():
            item = contract[stem]
            degrees = []
            for side, end in pair.items():
                need([end.contents[2].value, end.contents[3].value] == [item['x'], item['y']], 'Declared End geometry differs')
                need([end.contents[i].value for i in (4, 5)] == ([1, 0] if side == 0 else [2, 0]), 'End orientation differs')
                need(end.contents[21].value == 0 and end.contents[22].value == 0 and end.contents[23].values == [0, 0],
                     'Native default turnout time/position/detector profile differs')
                degrees.append(sum(end.contents[i].value is not None for i in (9, 10)))
                if item['role'] == 'reference':
                    need(end.contents[20].value == 2 and end.contents[12].value is station, 'Eight station reference pairs required')
                    references += 1
                elif item['role'] in ('entry', 'post'):
                    need(end.contents[20].value == 1 and end.contents[12].value is station, 'Ordinary platform area must share StationModel')
                    areas += 1
                else:
                    need(end.contents[20].value == 1 and end.contents[12].value is None, 'Outside throat/block must not become station area')
                sigspec, signal = expected_signals.get((stem, side)), end.contents[11].value
                if sigspec is None:
                    need(signal is None, 'Unexpected main signal inside a Route')
                else:
                    need(signal is not None and signal.contents[7].value is end, 'Signal/End ownership differs')
                    block = sigspec['kind'] == 'block'
                    need(signal.contents[8].values == [sigspec['signal_type'], sigspec['role'], 2] and
                         signal.contents[9].values == ([2, 400, 640, 0] if block else [2, 500, 644, 0]) and
                         signal.contents[11].value == 0 and signal.contents[12].value == 7 and signal.contents[16].value == 0,
                         'Exact directional Exit/Home/Block native profile differs')
                    offset = -1 if side == 0 else 1
                    need([signal.contents[i].value for i in (4, 5)] == [end.contents[i].value for i in (4, 5)] and
                         [signal.contents[i].value for i in (2, 3)] == [item['x'] + 12 * offset, item['y'] + 10 * offset],
                         'Signal orientation/visible offset differs')
                    need(c.text(signal.contents[13].value) == 'S_' + dn + '_' + sigspec['lane'] + '_' + sigspec['label'],
                         'Exact Signal identity differs')
            is_turnout = item['role'] in ('L1', 'L2', 'L3', 'R1', 'R2', 'R3')
            need(sorted(degrees) == ([1, 2] if is_turnout else [0, 1] if item['role'] in ('left', 'right') else [1, 1]),
                 'Physical turnout must have half degrees(1,2); no decorative/flat crossing vertex')
            if is_turnout:
                fork = pair[degrees.index(2)]
                need(c.text(fork.contents[9].value.contents[19].value) == item['direction'] + '_MAIN',
                     'Default firstEdge must be the real straight backbone')
                need(c.text(fork.contents[10].value.contents[19].value) in BRANCHES[item['direction']],
                     'Diverging secondEdge must be a real platform branch')
                members = pf.mutable_array(fork.contents[7].value.contents[7].value)
                need(len(members) == 3 and all(e.contents[7].value is fork.contents[7].value for e in members),
                     'Switch fork must share one native three-End Safety Element')
                turnouts.append({'vertex': stem, 'fork_end_id': fork.contents[0].value,
                    'first_edge_id': fork.contents[9].value.contents[0].value,
                    'second_edge_id': fork.contents[10].value.contents[0].value,
                    'safety_element_id': fork.contents[7].value.contents[0].value})
        need(references == 16 and areas == 32 and len(turnouts) == 12, 'Station area/turnout inventory differs')
        seen = set()
        for edge in (m for m in models if w.kind(m) == 'OTEdgeModel'):
            ends = [edge.contents[i].value for i in (7, 8)]
            refs = tuple((c.text(e.contents[18].value)[:-2], 0 if c.text(e.contents[18].value).endswith('_L') else 1) for e in ends)
            need(refs in expected_edges and refs not in seen, 'Unexpected/duplicate physical yard Edge')
            expected = expected_edges[refs]
            need(edge.contents[9].values == [1, expected['length_m'], 0., 0., 1, 1] and
                 c.text(edge.contents[19].value) == expected['track_name'] and
                 ends[0].contents[7].value is ends[1].contents[7].value, 'Physical metric/track/Safety closure differs')
            seen.add(refs)
        need(seen == set(expected_edges), 'Missing physical yard branch/backbone Edge')
        need(all(list(p.roots[dn].contents[i].values) == rect for i, rect in ROOT_RECTS.items()), 'Window/view geometry differs')
        inventories[dn] = {'models': counts, 'logical_vertices': 48, 'turnouts': turnouts,
                           'reference_pairs': 8, 'ordinary_station_area_ends': 32}
    report = p.report()
    need(len(report['connectors']) == 8 and len(report['continuations']) == 4,
         'Only two main lines may cross files: eight Connector records/four continuations')
    for conn in report['connectors']:
        src, dst = (conn['document'], conn['id']), tuple(conn['block_end'])
        a, b = p.model(src), p.model(dst)
        need(abs(names.index(src[0]) - names.index(dst[0])) == 1 and a.contents[3].value == b.contents[3].value,
             'Connector must join adjacent station on the same D/U main')
    need(len(p.routes) == 68 and len(p.paths_objects) == 8 and len(p.dests) == 8,
         'Expected sixty local Routes+four cross sources+four fragments/eight Paths/eight Itineraries')
    for route in p.routes:
        need(route.contents[6].values == [0, 40., 0.] and
             route.contents[5].values[:4] == [0, 400, 5, 0] and route.contents[5].values[5] == 0 and
             route.contents[8].values == [0., 0.] and route.contents[10].values == [5000, 0, 0] and
             route.contents[11].value == 0,
             'Exact Route flags, occupied-entry permission, delay/reservation/release defaults required')
    traces = {}
    for lane in LANES:
        ln, direction, side = lane['name'], lane['name'][0], lane['side']
        name = 'GD_' + ln
        dests = [d for d in p.dests if c.text(d.contents[1].value) == name]
        need(len(dests) == 1, 'Unique complete lane Itinerary required')
        trace = _trace(p, dests[0])
        order = names if side == 0 else names[::-1]
        need([v['station_sign'] for v in trace['visits']] == order and
             [v['distance_m'] for v in trace['visits']] == [0, 5000, 10000] and trace['distance_m'] == 10000,
             'Exact directed station trace/10km distance differs')
        need({edge['track'] for edge in trace['edges']} <= {ln, direction + '_MAIN'}, 'Itinerary enters another platform/direction')
        need([m['distance_m'] for m in trace['mains']] == MAIN_DISTANCES and
             [m['role'] for m in trace['mains']] == [4, 3, 3, 3, 2, 4, 3, 3, 3, 2, 4],
             'Actual main-signal split/5km leg distances differ')
        path = next(path for path in p.paths_objects if c.text(path.contents[1].value) == 'P_GD_' + ln)
        _, refs = p.path_view(path)
        need(len(refs) == 10, 'Ten consecutive single-main-to-main Routes required')
        rows = []
        for dn, ref in refs:
            route = p.owned((dn, ref['start_id']), 'OTRoute', (ref['name'], ref['array_id'], ref['start_id']))
            nodes = p.route_view(route)
            distance = sum(p.model(p.edge_between(a, b)).contents[9].values[1] for a, b in zip(nodes, nodes[1:]))
            rows.append({'document': dn, **ref, 'end_keys': [list(x) for x in nodes], 'distance_m': distance})
        need([r['distance_m'] for r in rows] == BLOCK_LENGTHS + [750] + BLOCK_LENGTHS + [750],
             'Each platform branch must preserve its exact Route length')
        trace['ordered_routes'], trace['four_block_lengths_per_leg_m'] = rows, BLOCK_LENGTHS.copy()
        trace['home_to_reference_m'], trace['actual_stop_area_m'] = 750, 500
        traces[name] = trace
    
    
    
    for dn in names:
        bydirection = {}
        for direction in ('D', 'U'):
            lane_rows = [lane for lane in LANES if lane['name'][0] == direction]
            all_sets, proof = [], {}
            for label in ('EXIT_B1', 'HOME_EXIT'):
                sets = []
                for lane in lane_rows:
                    rows = [r for r in p.routes if p.owners[id(r)][0] == dn and
                            c.text(r.contents[1].value) == 'R_' + dn + '_' + lane['name'] + '_' + label]
                    need(len(rows) == 1, 'Unique platform ingress/egress Route required')
                    sets.append(_route_resources(p, rows[0]))
                common_resources = set.intersection(*sets)
                need(common_resources, 'Four platform Routes must share real throat Safety Elements')
                proof['shared_' + label.lower() + '_safety_elements'] = [list(x) for x in sorted(common_resources)]
                all_sets.extend(sets)
            bydirection[direction] = set.union(*all_sets)
            resources[dn + '_' + direction] = proof
        need(not bydirection['D'] & bydirection['U'], 'Opposite main lines must not share Safety Elements')
    for direction in ('D', 'U'):
        lanes = [lane['name'] for lane in LANES if lane['name'][0] == direction]
        refsets = [{(r['document'], r['name'], r['array_id'], r['start_id'])
                    for r in traces['GD_' + lane]['ordered_routes']} for lane in lanes]
        shared = set.intersection(*refsets)
        need(len(shared) == 6, 'Four alternatives must reuse six actual common Routes across two station legs')
        resources[direction + '_shared_route_refs'] = [list(x) for x in sorted(shared)]
    for role in ('depot', 'trains', 'courses', 'timetable'):
        root, _ = w.load_next_compatible(files[CATALOGS[role]])
        items = {'depot': c.engine_items, 'trains': c.train_items, 'courses': c.course_items,
                 'timetable': cf.timetable}[role](root)
        need(not items, 'Infrastructure component must leave traffic catalogs empty')
    rb.verify_run(files['chain.run'], {k: v for k, v in files.items() if k != 'chain.run'},
        catalog_paths=CATALOGS, document_paths=['OTDocuments/' + dn + '.opentrack' for dn in names],
        execution_root=spec['execution_root'], path_style='windows', train_types=['instructional'])
    return {'documents': inventories, 'connector_records': 8, 'connector_pairs': 4,
        'turnouts_per_station': 12, 'signal_count': 48, 'block_signals': 18,
        'route_objects': 68, 'ordinary_source_routes': 64, 'continuation_fragments': 4,
        'full_itineraries': traces, 'shared_resources': resources, 'journey_distance_m': 10000,
        'main_distances_m': MAIN_DISTANCES.copy(), 'actual_stop_area_m': 500,
        'four_true_blocks_per_leg': True, 'block_lengths_per_leg_m': BLOCK_LENGTHS.copy(),
        'reconstruction': report, 'traffic_catalogs_empty': True,
        'native_runtime_verified': False, 'native_application_executed': False}


def generate(sources, spec):
    paths = configuration(spec)
    need(type(sources) is dict and set(sources) == SOURCE_KEYS and all(type(v) is bytes and v for v in sources.values()),
         'Exact six immutable nonempty sources required')
    original_spec, hashes = copy.deepcopy(spec), {k: sha(v) for k, v in sources.items()}
    golden = _golden_block(sources['header'])
    names = list(paths)
    roots, versions, ids, models = {}, {}, {}, {}
    base_reports, signals, bindings, local, cross = {}, {}, {}, {}, {}
    station_rows = []
    for row in spec['stations']:
        dn = row['id']
        blob, base = tp.generate_network(sources['header'], sources['shapes'], topology_spec())
        base_reports[dn], ids[dn] = base, base['vertex_end_ids']
        blob, signals[dn] = _add_signals(blob, dn, ids[dn])
        blob, stations, bindings[dn] = sb.bind_stations(blob, [dict(sign=dn, name=row['name'],
            end_ids=[ids[dn][key(lane['name'], 'reference')][0] for lane in LANES],
            placement=g.placement(700, 530), station_type_raw=2, interlock_type_raw=4,
            icon_show_type_raw=1, timing_point=True)])
        station_rows.append((dn, c.station_items(w.load_next_compatible(stations)[0])[dn]))
        roots[dn], versions[dn] = w.load_next_compatible(blob)
        _, models[dn] = rf.document(roots[dn])
        station = models[dn][ids[dn][key('D1', 'reference')][0]].contents[12].value
        for lane in LANES:
            for role in ('entry', 'post'):
                for eid in ids[dn][key(lane['name'], role)]:
                    models[dn][eid].contents[12].value = station
            for label, sequence in (('HOME_EXIT', ingress(lane['name'])), ('EXIT_B1', egress(lane['name']))):
                ref = _local_route(roots[dn], models[dn], ids[dn], lane['side'], sequence,
                                   'R_' + dn + '_' + lane['name'] + '_' + label)
                ref['document'] = dn
                local[(dn, lane['name'], label)] = ref
        for direction, side in (('D', 0), ('U', 1)):
            for label, roles in (('B3_HOME', ('in_block', 'home')), ('B1_B2', ('out_b1', 'out_b2'))):
                ref = _local_route(roots[dn], models[dn], ids[dn], side, [common(direction, r) for r in roles],
                                   'R_' + dn + '_' + direction + '_' + label)
                ref['document'] = dn
                local[(dn, direction, label)] = ref
        for index, values in ROOT_RECTS.items():
            roots[dn].contents[index].values = [tp.flt(v, 'saved window/view') for v in values]
    
    for i, dn in enumerate(names):
        for direction in ('D', 'U'):
            for neighbor, role, side, target_role, target_side in (
                (i - 1, 'left', 0, 'right', 1), (i + 1, 'right', 1, 'left', 0)):
                if not 0 <= neighbor < len(names):
                    continue
                target = names[neighbor]
                end = models[dn][ids[dn][key(direction, role)][side]]
                need(all(end.contents[j].value is None for j in (9, 10, 11, 12)), 'Unused external half-End required')
                end.clazz = w.Class(b'OTConnModel', 1, end.clazz)
                end.contents += [w.TypedValue(b'@', ns.string('')), w.TypedValue(b'@', ns.string(target)),
                    w.TypedValue(b'i', ids[target][key(direction, target_role)][target_side]), w.TypedValue(b'i', 0)]
    for direction, side in (('D', 0), ('U', 1)):
        order = names if side == 0 else names[::-1]
        for source, target in zip(order, order[1:]):
            owner = models[source][ids[source][common(direction, 'out_b2')][side]]
            boundary = models[source][ids[source][common(direction, 'right')][side]]
            receiver = models[target][ids[target][common(direction, 'left')][side]]
            finish = models[target][ids[target][common(direction, 'in_block')][side]]
            start, name = owner.contents[0].value, 'R_' + direction + '_' + source + '_' + target + '_B2_B3'
            route, fragment = g.route(name, 0, start, [owner, boundary], 2), g.route(name, 0, start, [finish], -1, True)
            need(owner.contents[19].value == -1, 'Fresh cross Route source required')
            w.set_elements(owner.contents[15].value.contents[0].value, [route])
            owner.contents[19].value = 0
            w.set_elements(receiver.contents[15].value.contents[0].value, [fragment])
            cross[(direction, source, target)] = {'document': source, **cd.ref(route)}
    docs = {dn: w.dump_verified(roots[dn], versions[dn]) for dn in names}
    dest = w.dump_verified(g.wrapped('OTDestInfoList', []), versions[names[0]])
    paths_made, itineraries = {}, {}
    for lane in LANES:
        ln, direction = lane['name'], lane['name'][0]
        order = names if lane['side'] == 0 else names[::-1]
        selected = []
        for source, target in zip(order, order[1:]):
            selected += [local[(source, ln, 'EXIT_B1')], local[(source, direction, 'B1_B2')],
                         cross[(direction, source, target)], local[(target, direction, 'B3_HOME')],
                         local[(target, ln, 'HOME_EXIT')]]
        docs, path = ops.create_path(docs, dest, document_paths=paths,
            expected_hashes={**{dn: sha(blob) for dn, blob in docs.items()}, '$dest_catalog': sha(dest)},
            complete_document_set=True, name='P_GD_' + ln, routes=selected)
        payload, itinerary = ops.create_itinerary(docs, dest, document_paths=paths,
            expected_hashes={**{dn: sha(blob) for dn, blob in docs.items()}, '$dest_catalog': sha(dest)},
            complete_document_set=True, name='GD_' + ln, paths=[path['created']])
        docs, dest = payload['documents'], payload['catalog']
        paths_made[ln], itineraries[ln] = path, itinerary
    files = {'OTDocuments/' + dn + '.opentrack': blob for dn, blob in docs.items()}
    for role, member in CATALOGS.items():
        files[member] = dest if role == 'dest' else w.dump_verified(sb.dictionary(station_rows), versions[names[0]]) if role == 'stations' else g.empty_catalog(sources[role + '_template'], role)
    run, run_receipt = rb.build_run(files, catalog_paths=CATALOGS,
        document_paths=['OTDocuments/' + dn + '.opentrack' for dn in names], execution_root=spec['execution_root'],
        path_style='windows', train_types=['instructional'], template=b'')
    files['chain.run'] = run
    detail = validate(files, spec)
    need(spec == original_spec and hashes == {k: sha(v) for k, v in sources.items()}, 'Caller input mutated')
    return files, {'schema': 'guided-eight-platform-yard-topology/1', 'configuration': copy.deepcopy(spec),
        'source_sha256': hashes, 'members': {n: {'sha256': sha(b), 'bytes': len(b)} for n, b in files.items()},
        'golden_block_signals': golden, 'document_paths': paths, 'lanes': copy.deepcopy(list(LANES)),
        'base_networks': base_reports, 'signals': signals, 'station_bindings': bindings,
        'paths': paths_made, 'itineraries': itineraries, 'run': run_receipt, 'validation': detail,
        'from_empty_graph': True, 'one_station_per_document': True, 'traffic_catalogs_empty': True,
        'platforms_pending': True, 'platform_visible_rects': copy.deepcopy(PLATFORM_RECTS),
        'explicit_saved_window_groups': ROOT_RECTS, 'saved': False,
        'native_application_executed': False, 'native_runtime_verified': False,
        'scope': 'Eight platform tracks share twelve real paired-End turnouts and two main lines per station. Eight10km journeys, exact native main-signal Routes and500m arrival areas. No traffic, native interlocking or runtime acceptance.'}
