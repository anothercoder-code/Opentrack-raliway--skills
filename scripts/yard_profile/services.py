"""Nine native yard services on eight platforms and two shared running mains.

Pure immutable archive bytes only.  This module never opens a native window,
publishes a file, simulates traffic, or labels configured data as safe operation.
"""
from __future__ import annotations

import copy
import hashlib
import math

from opentrack_ai.current_archive import writer as w, catalogs as c, course_factories as cf
from opentrack_ai.current_archive.multi_document import core as cd, generate as g
from opentrack_ai.current_archive.zero_operations import vehicle_catalogs as vc, run_bundle as rb
from opentrack_ai.current_archive.zero_terminal.area_operations import arr_like, dictionary_like
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT, FIELDS, value_for
from opentrack_ai.current_archive.prepare_contract import auxiliary as aux
from opentrack_ai.current_archive.infrastructure_incidents import core as incidents

CATALOGS = {role: 'OTData/chain.' + role for role in rb.CATALOG_KEYS}
LANES = tuple(direction + str(i) for i in range(1, 5) for direction in ('D', 'U'))
SOURCE_KEYS = frozenset({'header', 'shapes', 'depot_template', 'trains_template',
                         'courses_template', 'timetable_template'})
RUN = 'eighttracks.run'
SPEED_TYPE = 'Reihe R'
ENGINE = 'GDAB_ENGINE'
CATEGORY = 'GDAB_CATEGORY'
INCIDENT = 'D1_BLOCK_FAILURE'
VEHICLE_PARAMETERS = {'maximum_acceleration_mps2': 1.0, 'braking_delay_s': 1.0,
                      'braking_release_speed_kmh': 0.0}
WINDOW = {'start_day': 0, 'start_time': '09:00:00', 'stop_day': 0,
          'stop_time': '09:20:00', 'step': '0.2'}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def manifest(files):
    return {name: {'sha256': sha(blob), 'bytes': len(blob)}
            for name, blob in sorted(files.items())}


def configuration(spec):
    from .topology import configuration as infrastructure_configuration
    paths = infrastructure_configuration(spec)
    for name in (ENGINE, CATEGORY, SPEED_TYPE):
        cf.name(name)
    return paths


def make_plans(spec):
    names = list(configuration(spec))
    plans = []
    for lane in LANES:
        order = names if lane.startswith('D') else list(reversed(names))
        plans.append({'lane': lane, 'course_id': 'GD' + lane + '01',
            'train': 'GD_T_' + lane, 'itinerary': 'GD_' + lane,
            'visits': [{'station_sign': name, 'absolute_seconds': second, 'stop': i == 2}
                       for i, (name, second) in enumerate(zip(order, (32460, 32760, 33060)))]})
    plans.append({'lane': 'D1', 'course_id': 'GDD102', 'train': 'GD_T_D1_FOLLOW',
        'itinerary': 'GD_D1',
        'visits': [{'station_sign': name, 'absolute_seconds': second, 'stop': i == 2}
                   for i, (name, second) in enumerate(zip(names, (32475, 32775, 33075)))]})
    return plans


def _project(files, spec):
    paths = configuration(spec)
    docs = {name: files['OTDocuments/' + name + '.opentrack'] for name in paths}
    p = cd.Project(docs, document_paths=paths,
        expected_hashes={name: sha(blob) for name, blob in docs.items()}, complete_document_set=True)
    p.check_dest_catalog(files[CATALOGS['dest']])
    return p


def trace(p, itinerary_name, order, maximum_speed, lane):
    selected = [dest for dest in p.dests if c.text(dest.contents[1].value) == itinerary_name]
    need(len(selected) == 1, 'Exactly one named full itinerary required')
    nodes, path_refs = p.dest_view(selected[0])
    need(len(path_refs) == 1, 'The finite profile uses one full Path per itinerary')
    path = next(obj for obj in p.paths_objects if c.text(obj.contents[1].value) == 'P_GD_' + lane)
    path_nodes, route_refs = p.path_view(path)
    need(path_nodes == nodes and len(route_refs) == 10, 'The full itinerary must use ten consecutive main-to-main Routes')
    distance = minimum = 0.0
    visits, edges, mains = [], [], []
    for i, key in enumerate(nodes):
        end = p.model(key)
        if i:
            edge_key = p.edge_between(nodes[i - 1], key)
            edge = p.model(edge_key)
            half = p.model(p.actual_related(nodes[i - 1]))
            length = edge.contents[9].values[1]
            need(type(length) is int and length > 0, 'Positive native Edge length required')
            track = c.text(edge.contents[19].value)
            need(track in {lane, lane[0] + '_MAIN'},
                 'Yard Itinerary enters another platform lane or the opposite running main')
            limits = cf.dictionary(edge.contents[16].value)
            need('0' in limits, 'Course speed mapping must resolve native Edge index0')
            speed = limits['0'].contents[1 if edge.contents[7].value is half else 2].value
            need(type(speed) is int and 0 < speed <= 1000, 'Invalid directional Edge speed')
            distance += length
            minimum += length / (min(maximum_speed, speed) / 3.6)
            edges.append({'document': edge_key[0], 'id': edge_key[1], 'length_m': length,
                          'track': track, 'limit_kmh': speed,
                          'safety_element_key': [edge_key[0], edge.contents[7].value.contents[7].value.contents[0].value]})
        signal = end.contents[11].value
        if signal is not None:
            need(signal.contents[7].value is end and
                 [signal.contents[j].value for j in (4, 5)] == [end.contents[j].value for j in (4, 5)],
                 'Signal must point back to and inherit the actual directional End alignment')
            mains.append({'document': key[0], 'end_id': key[1],
                'signal_id': signal.contents[0].value, 'signal_type': signal.contents[8].values[0],
                'role': signal.contents[8].values[1], 'distance_m': distance})
        if end.contents[20].value == 2:
            station = end.contents[12].value
            need(station is not None and signal is not None, 'A reference StationVertex requires its actual station/main signal')
            if i:
                previous = p.model(nodes[i - 1])
                arrival = p.model(p.edge_between(nodes[i - 1], key))
                need(previous.contents[20].value == 1 and previous.contents[12].value is station and
                     arrival.contents[9].values[1] == 500,
                     'Every approached station must retain its actual directional500m arrival area')
            visits.append({'station_sign': c.text(station.contents[7].value),
                'document': key[0], 'end_id': key[1], 'distance_m': distance,
                'minimum_edge_time_s': minimum})
    need([v['station_sign'] for v in visits] == order and
         [v['distance_m'] for v in visits] == [0, 5000, 10000] and distance == 10000,
         'Exact directed five-km legs/ten-km full journey required')
    need([row['distance_m'] for row in mains] ==
         [0, 1250, 2400, 3750, 4250, 5000, 6250, 7400, 8750, 9250, 10000] and
         [row['role'] for row in mains] == [4, 3, 3, 3, 2, 4, 3, 3, 3, 2, 4],
         'The four block sections plus750m Home-to-reference yard Routes differ')
    need(all(row['signal_type'] == 25 for row in mains if row['role'] == 3),
         'Block signals must use the native main/distant three-aspect type25')
    native_route_resources = []
    for dn, reference in route_refs:
        route = p.owned((dn, reference['start_id']), 'OTRoute',
                        (reference['name'], reference['array_id'], reference['start_id']))
        need(route.contents[6].values[0] == 0 and route.contents[11].value == 0,
             'Yard main Route must forbid occupied entry and reservation-with-previous')
        expanded = p.route_view(route)
        
        
        elements = sorted({(key[0], p.model(key).contents[7].value.contents[0].value)
                           for key in expanded[1:]})
        switches = []
        for a, b in zip(expanded, expanded[1:]):
            related = p.model(p.actual_related(a))
            if related.contents[9].value is not None and related.contents[10].value is not None:
                edge = p.model(p.edge_between(a, b))
                need(edge in (related.contents[9].value, related.contents[10].value),
                     'Facing turnout Route does not select an actual branch Edge')
                switches.append({'document': p.key(related)[0], 'branch_half_end_id': related.contents[0].value,
                    'edge_id': edge.contents[0].value, 'required_position':
                    1 if related.contents[9].value is edge else 2})
            arriving = p.model(b)
            if arriving.contents[9].value is not None and arriving.contents[10].value is not None:
                edge = p.model(p.edge_between(a, b))
                need(edge in (arriving.contents[9].value, arriving.contents[10].value),
                     'Trailing turnout Route does not select an actual incoming branch Edge')
                switches.append({'document': b[0], 'branch_half_end_id': arriving.contents[0].value,
                    'edge_id': edge.contents[0].value, 'required_position':
                    1 if arriving.contents[9].value is edge else 2})
        native_route_resources.append({'document': dn, **reference,
            'element_keys': [list(k) for k in elements], 'switch_requirements': switches})
    need(any(edge['track'] == lane for edge in edges) and
         any(edge['track'] == lane[0] + '_MAIN' for edge in edges),
         'A yard journey must use both its actual platform track and shared running main')
    return {'itinerary': itinerary_name, 'lane': lane, 'nodes': [list(key) for key in nodes],
        'visits': visits, 'edges': edges, 'mains': mains, 'ordered_route_count': len(route_refs),
        'distance_m': distance, 'minimum_edge_time_s': minimum,
        'native_route_resources': native_route_resources}


def _vehicle(files, plans):
    depot, _ = w.load_next_compatible(files[CATALOGS['depot']])
    trains, _ = w.load_next_compatible(files[CATALOGS['trains']])
    engines, rows, categories = c.engine_items(depot), c.train_items(trains), c.array(trains.contents[1].value)
    need(len(engines) == len(categories) == 1 and len(rows) == 9,
         'One Engine/Category type and nine distinct native Trains required')
    engine, category = engines[0], categories[0]
    c.shape(category, 'OTTrainCategory', 19, CATEGORY_LAYOUT)
    need(c.text(engine.contents[1].value) == ENGINE and c.text(category.contents[1].value) == CATEGORY,
         'Generated Engine/Category identities differ')
    need(not (category.contents[0].values[1] & 0x20), 'stopAtEveryStation conflicts with the final-only plans')
    need({c.text(row.contents[0].value) for row in rows} == {plan['train'] for plan in plans},
         'The nine selected Train definitions must close exactly')
    length, speed = float(engine.contents[2].values[2]), engine.contents[7].value
    need(math.isfinite(length) and 0 < length <= 500 and type(speed) is int and 0 < speed <= 1000,
         'The native single unit must fit the500m arrival area')
    for row in rows:
        refs = c.array(row.contents[2].values[1])
        need(len(refs) == 1 and refs[0].contents[1].value == 1 and not c.array(row.contents[2].values[2]),
             'One powered unit at posInTrain1 and no trailers required')
        need(c.bound_engine_names(row) == [ENGINE] and c.text(row.contents[3].value) == CATEGORY,
             'Train/Engine/Category reference closure differs')
        for field, expected in VEHICLE_PARAMETERS.items():
            layout = FIELDS[field]
            need(row.contents[layout[2]].values[layout[3]] == value_for(field, expected),
                 'Selected native Train physical parameters differ')
    return trains, length, speed


def _topology_projection(files, spec):
    """Reapply the strict infrastructure validator, removing only known Rects/services."""
    from .topology import validate as validate_topology
    from .graphics import _inspect_rect
    paths = configuration(spec)
    projection = {name: blob for name, blob in files.items() if name != RUN}
    platform_counts, label_counts = {}, {}
    for dn in paths:
        member = 'OTDocuments/' + dn + '.opentrack'
        raw_root, _ = w.load_next_compatible(projection[member])
        labels = [obj for obj in c.array(raw_root.contents[2].value) if w.kind(obj) == 'OTLabelModel']
        if labels:
            from .text import strip_yard_labels
            projection[member], label_receipt = strip_yard_labels(projection[member])
            label_counts[dn] = len(labels)
            need(label_counts[dn] == 15, 'Only the complete audited15-label yard set is supported')
        else:
            label_counts[dn] = 0
        root, version = w.load_next_compatible(projection[member])
        models = c.array(root.contents[2].value)
        rects = [obj for obj in models if w.kind(obj) == 'OTRectModel']
        need(len(rects) in (0, 4), 'Only zero or four source-evidenced island Rects supported')
        if rects:
            for index, obj in enumerate(rects):
                _inspect_rect(obj, (580.0, (82.0, 182.0, 322.0, 422.0)[index], 240.0, 16.0))
            need({id(o) for o in w.objects(root) if w.kind(o) == 'OTRectModel'} == {id(o) for o in rects},
                 'Hidden or nonmember island drawing refused')
            w.set_elements(root.contents[2].value, [obj for obj in models if w.kind(obj) != 'OTRectModel'])
            projection[member] = w.dump_verified(root, version)
        platform_counts[dn] = len(rects)
    for role in ('depot', 'trains', 'courses', 'timetable'):
        projection[CATALOGS[role]] = g.empty_catalog(files[CATALOGS[role]], role)
    projection['chain.run'], _ = rb.build_run(projection, catalog_paths=CATALOGS,
        document_paths=['OTDocuments/' + dn + '.opentrack' for dn in paths],
        execution_root=spec['execution_root'], path_style='windows', train_types=['instructional'], template=b'')
    return validate_topology(projection, spec), platform_counts, label_counts


def validate(files, spec, plans=None, *, output_directory='output', incident_names=()):
    expected_plans = make_plans(spec)
    plans = expected_plans if plans is None else plans
    need(plans == expected_plans, 'Exact nine lane/following service plans required')
    paths = configuration(spec)
    expected_members = {RUN, *CATALOGS.values(), *('OTDocuments/' + dn + '.opentrack' for dn in paths)}
    need(type(files) is dict and set(files) == expected_members and
         all(type(blob) is bytes and blob for blob in files.values()), 'Exact ten immutable native input members required')
    infrastructure, platform_counts, label_counts = _topology_projection(files, spec)
    p = _project(files, spec)
    trains, length, maximum_speed = _vehicle(files, plans)
    course_root, _ = w.load_next_compatible(files[CATALOGS['courses']])
    courses = {c.text(obj.contents[0].value): obj for obj in c.course_items(course_root)}
    rows = cf.timetable(w.load_next_compatible(files[CATALOGS['timetable']])[0])
    need(set(courses) == {plan['course_id'] for plan in plans} and len(rows) == 27,
         'Nine exact Courses and27 native Timetable rows required')
    need(set(rows) == {plan['course_id'] + '#' + str(i) for plan in plans for i in range(3)},
         'Exact Course/Timetable key closure differs')
    traces, movement_by_lane = {}, {}
    for plan in plans:
        cid, lane = plan['course_id'], plan['lane']
        course = courses[cid]
        need(c.text(course.contents[3].value) == plan['train'] and
             [c.text(obj) for obj in c.array(course.contents[2].value)] == [plan['itinerary']] and
             c.text(course.contents[4].value) == SPEED_TYPE and course.contents[5].value == 1,
             'Course Train/Itinerary/speed/enabled binding differs')
        need(course.contents[1].value == 0 and course.contents[6].value == 100 and
             course.contents[7].values[0] == 0 and course.contents[8].value == 0 and
             course.contents[9].value == 100 and course.contents[12].values == [0, 0],
             'Fixed-block Course must retain discrete spacing, zero entry/output offset, full acceleration and zero additional reservation/release')
        tr = trace(p, plan['itinerary'], [v['station_sign'] for v in plan['visits']], maximum_speed, lane)
        traces[cid] = tr
        movement = {(edge['document'], edge['id']) for edge in tr['edges']}
        if lane in movement_by_lane:
            need(lane == 'D1' and cid == 'GDD102' and movement == movement_by_lane[lane],
                 'Only the explicit D1 following service may share its leader physical movement')
        else:
            movement_by_lane[lane] = movement
        for index, visit in enumerate(plan['visits']):
            row = rows[cid + '#' + str(index)]
            clock = _clock(visit['absolute_seconds'])
            need(c.text(row.contents[1].value) == cid and row.contents[3].value == index and row.contents[4].value == 2 and
                 c.text(row.contents[5].value) == visit['station_sign'] and
                 c.text(row.contents[6].value) == c.text(row.contents[7].value) == clock,
                 'Native Timetable owner/order/station/planned clocks differ')
            need(row.contents[10].value == 2 + int(index == 2) and row.contents[15].values == [0, 0, 0, 0] and
                 c.text(row.contents[13].value) == c.text(row.contents[14].value) == 'HH:MM:SS' and
                 c.text(row.contents[18].value) == lane and not c.array(row.contents[9].value),
                 'Native stop flags/actual reset/track/Connection profile differs')
            if index:
                need(visit['absolute_seconds'] - plan['visits'][index - 1]['absolute_seconds'] >=
                     tr['visits'][index]['minimum_edge_time_s'] - tr['visits'][index - 1]['minimum_edge_time_s'],
                     'Planned interval is below the actual directional Edge/Engine speed bound')
    parsed = aux.records(files[RUN])
    selected_names = [value for key, value, _ in parsed if key == 'Incident']
    need(selected_names == list(incident_names), 'Selected native Incident names differ from the scenario')
    incident_binding = aux.incident_bindings(files[CATALOGS['courses']], selected_names)
    events = c.array(course_root.contents[1].value)
    need(len(events) == len(incident_names) and {c.text(event.contents[0].value) for event in events} == set(incident_names),
         'Incident catalog must contain exactly this scenario selection')
    need(not c.array(course_root.contents[2].value) and not c.array(course_root.contents[3].value),
         'No hidden IncidentSets or delay distributions allowed in this fixed scenario')
    incidents.state(files[CATALOGS['courses']], p, (32400, 33600))
    if events:
        need(tuple(incident_names) == (INCIDENT,), 'Only the explicit first-station Down B2 failure case is supported')
        targets = [obj for obj in p.models[spec['stations'][0]['id']] if w.kind(obj) == 'OTSignalModel' and
                   c.text(obj.contents[13].value) == 'S_' + spec['stations'][0]['id'] + '_D_B2']
        need(len(targets) == 1 and targets[0].contents[8].values == [25, 3, 2],
             'The fixed failure target must be one actual shared Down-main B2 three-aspect Block signal')
        need(incidents.item_from_object(events[0]) == _failure_item(spec['stations'][0]['id'], targets[0].contents[0].value),
             'Fixed failure target, Use, probability or 09:00..09:06 interval differs')
    core_run = aux.core_bytes(parsed)
    archives = {name: blob for name, blob in files.items() if name != RUN}
    run = rb.verify_run(core_run, archives, catalog_paths=CATALOGS,
        document_paths=['OTDocuments/' + dn + '.opentrack' for dn in paths],
        execution_root=spec['execution_root'], path_style='windows', output_directory=output_directory,
        train_types=[SPEED_TYPE], **WINDOW)
    binding = rb.verify_archive_bindings(core_run, archives, catalog_paths=CATALOGS,
        document_paths=['OTDocuments/' + dn + '.opentrack' for dn in paths])
    need(cf.clock('09:01:15') - cf.clock('09:01:00') == 15 and
         traces['GDD102']['nodes'] == traces['GDD101']['nodes'], 'Following service must share D1 with15s planned offset')
    sharing = validate_shared_resources(traces)
    return {'schema': 'yard-nine-service-validation/1', 'courses': 9, 'trains': 9,
        'engines': 1, 'categories': 1, 'timetable_rows': 27, 'journey_distance_m': 10000,
        'station_reference_distances_m': [0, 5000, 10000], 'train_length_m': length,
        'following_pair': {'leader': 'GDD101', 'follower': 'GDD102', 'planned_start_gap_s': 15,
            'shared_itinerary': 'GD_D1', 'runtime_separation_verified': False},
        'infrastructure': infrastructure, 'platform_counts': platform_counts,
        'label_counts': label_counts, 'traces': traces, 'shared_resources': sharing,
        'run': run, 'archive_bindings': binding, 'incident_binding': incident_binding,
        'actual_results_unset': True, 'native_application_executed': False, 'runtime_safety_verified': False}


def validate_shared_resources(traces):
    """Persisted shared-resource candidates, not simulated conflict outcomes."""
    need(set(traces) == {plan['course_id'] for plan in make_plans_for_names()},
         'The exact nine Course resource traces are required')
    pairs = []
    names = sorted(traces)
    for i, aid in enumerate(names):
        a = traces[aid]
        ae = {(edge['document'], edge['id']): edge for edge in a['edges']}
        ar = {tuple(key) for route in a['native_route_resources'] for key in route['element_keys']}
        for bid in names[i + 1:]:
            b = traces[bid]
            be = {(edge['document'], edge['id']): edge for edge in b['edges']}
            br = {tuple(key) for route in b['native_route_resources'] for key in route['element_keys']}
            edges, elements = set(ae) & set(be), ar & br
            same_direction = a['lane'][0] == b['lane'][0]
            if same_direction:
                need(edges and elements, 'Same-direction yard Courses must share real main Edge/SafetyElement resources')
                if a['lane'] != b['lane']:
                    need(all(ae[key]['track'] == a['lane'][0] + '_MAIN' for key in edges),
                         'Different platform lanes unexpectedly share a platform-specific Edge')
                else:
                    need({aid, bid} == {'GDD101', 'GDD102'} and set(ae) == set(be) and a['nodes'] == b['nodes'],
                         'Only the explicit D1 leader/follower may have the same full platform movement')
            else:
                need(not edges and not elements, 'Opposite running mains must have independent physical and native reservation resources')
            pairs.append({'course_a': aid, 'course_b': bid, 'same_direction': same_direction,
                'shared_edge_keys': [list(k) for k in sorted(edges)],
                'shared_native_element_keys': [list(k) for k in sorted(elements)],
                'potential_native_resource_conflict': bool(edges or elements)})
    need(sum(row['same_direction'] for row in pairs) == 16 and len(pairs) == 36,
         'Expected five Down and four Up Course resource pairs')
    return {'course_pairs': pairs, 'same_direction_shared_pairs': 16, 'opposite_direction_disjoint_pairs': 20,
        'runtime_conflicts_or_separation_verified': False,
        'policy': 'Actual shared running-main Edge/OTElement identity; selected directions only. No head-on/crossover runtime certificate.'}


def make_plans_for_names():
    
    return [{'course_id': 'GD' + lane + '01'} for lane in LANES] + [{'course_id': 'GDD102'}]


def _clock(seconds):
    need(type(seconds) is int and 0 <= seconds < 86400, 'Same-day integer planned seconds required')
    return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'


def _failure_item(document, signal_id):
    return {'name': INCIDENT, 'type': 'signal_blockage', 'document': document,
        'model_id': signal_id, 'begin_time': '09:00:00', 'end_time': '09:06:00',
        'begin_day': 0, 'end_day': 0, 'enabled': True, 'probability_percentage': 100}


def compose(sources, network_files, topology_spec, topology_receipt):
    spec = copy.deepcopy(topology_spec)
    paths = configuration(spec)
    need(type(sources) is dict and set(sources) == SOURCE_KEYS and
         all(type(blob) is bytes and blob for blob in sources.values()), 'Exact six immutable native donor roles required')
    need(type(network_files) is dict and type(topology_receipt) is dict and
         topology_receipt.get('members') == manifest(network_files), 'Network receipt must bind the exact immutable source members')
    need(topology_receipt.get('configuration') == spec and topology_receipt.get('source_sha256') ==
         {role: sha(blob) for role, blob in sources.items()}, 'Topology/source/specification receipt differs')
    source_hashes = {role: sha(blob) for role, blob in sources.items()}
    original_network = manifest(network_files)
    plans = make_plans(spec)
    vehicle_spec = {'engine_template': 'CR400AF_8_PROXY_350', 'train_template': 'CR400AF_8_PROXY_350',
        'category_template': 'Category 1', 'engine_name': ENGINE, 'category_name': CATEGORY,
        'train_names': [plan['train'] for plan in plans], 'use_template_physics': True,
        'inherit_conflict_definitions': True, 'train_parameters': copy.deepcopy(VEHICLE_PARAMETERS)}
    vehicles, vehicle_receipt = vc.generate_vehicle_catalogs(sources['depot_template'], sources['trains_template'], vehicle_spec)
    files = dict(network_files)
    for role, blob in vehicles.items():
        files[CATALOGS[role]] = blob
    trains, length, speed = _vehicle(files, plans)
    p = _project(files, spec)
    ct, cv = w.load_next_compatible(sources['courses_template'])
    tt, tv = w.load_next_compatible(sources['timetable_template'])
    templates = {c.text(obj.contents[0].value): obj for obj in c.course_items(ct)}
    rows = cf.timetable(tt)
    cid0, key0 = 'G1046', 'G1046#0'
    need(ct.contents[0].value == 17 and cid0 in templates and key0 in rows and
         not c.array(rows[key0].contents[9].value), 'Exact current connection-free Course/Timetable donor templates required')
    courses = cf.clone(ct)
    for index in (1, 2, 3):
        courses.contents[index].value = arr_like(ct.contents[index].value, [])
    courses.contents[4].value = arr_like(ct.contents[4].value, [copy.deepcopy(templates[cid0])])
    table = dictionary_like(tt, [(key0, copy.deepcopy(rows[key0]))])
    dest = w.load_next_compatible(files[CATALOGS['dest']])[0]
    stations = w.load_next_compatible(files[CATALOGS['stations']])[0]
    traces = {}
    for plan in plans:
        cid = plan['course_id']
        tr = trace(p, plan['itinerary'], [v['station_sign'] for v in plan['visits']], speed, plan['lane'])
        traces[cid] = tr
        fields = {'speed_type': SPEED_TYPE, 'description': 'Yard platform journey over shared running mains',
            'comment': 'Planned only; original simulator acceptance pending', 'train_number': cid, 'course_type': '',
            'acceleration_percent': 100, 'delayed_acceleration_percent': 100, 'enabled': True,
            'entering_speed_kmh': 0, 'output_offset_m': 0, 'spacing_mode': 'discrete',
            'additional_reservation_time_s': 0, 'additional_release_time_s': 0}
        courses = cf.new_course(courses, trains, dest, template_id=cid0, course_id=cid,
            train=plan['train'], itineraries=[plan['itinerary']], fields=fields)
        stops = []
        for index, visit in enumerate(plan['visits']):
            if index:
                need(visit['absolute_seconds'] - plan['visits'][index - 1]['absolute_seconds'] >=
                     tr['visits'][index]['minimum_edge_time_s'] - tr['visits'][index - 1]['minimum_edge_time_s'],
                     'Planned interval below actual direction-specific Edge/Engine speed bound')
            clock = _clock(visit['absolute_seconds'])
            stops.append({'template_key': key0, 'station_sign': visit['station_sign'],
                'arrival': clock, 'departure': clock, 'arrival_day_offset': 0, 'departure_day_offset': 0,
                'stop_at_station': visit['stop'], 'timing_station': True,
                'interval_reference_course_id': None, 'interval_offset_s': 0, 'dwell_s': 0,
                'mean_delay_s': 0, 'track_id': plan['lane'], 'distribution_name': '', 'delta_mass_t': 0})
        table = cf.new_timetable(table, courses, stations, course_id=cid, stops=stops)
    courses.contents[4].value = arr_like(courses.contents[4].value,
        [obj for obj in c.course_items(courses) if c.text(obj.contents[0].value) != cid0])
    table = dictionary_like(table, [(key, row) for key, row in cf.timetable(table).items() if key != key0])
    files[CATALOGS['courses']] = w.dump_verified(courses, cv)
    files[CATALOGS['timetable']] = w.dump_verified(table, tv)
    files.pop('chain.run')
    files[RUN], run_receipt = rb.build_run(files, catalog_paths=CATALOGS,
        document_paths=['OTDocuments/' + dn + '.opentrack' for dn in paths],
        execution_root=spec['execution_root'], path_style='windows', output_directory='output',
        train_types=[SPEED_TYPE], template=b'', **WINDOW)
    validation = validate(files, spec, plans)
    need(source_hashes == {role: sha(blob) for role, blob in sources.items()} and
         original_network == manifest(network_files) and spec == topology_spec,
         'Composition mutated donor bytes, network members or caller specification')
    receipt = {'schema': 'yard-nine-service-composition/1', 'spec': spec, 'plans': plans,
        'source_sha256': source_hashes, 'input_network_members': original_network,
        'members': manifest(files), 'vehicles': vehicle_receipt, 'vehicle_specification': vehicle_spec,
        'train_length_m': length, 'traces': traces, 'run': run_receipt, 'validation': validation,
        'selected_run_filename': RUN, 'source_and_network_bytes_unchanged': True,
        'saved': False, 'native_application_executed': False, 'runtime_safety_verified': False,
        'scope': 'Nine planned native platform services over two shared running mains, including15s D1 following; merging, delay, occupancy and fault recovery require actual native execution.'}
    return files, receipt


def make_failure_case(normal_files, spec, plans, signal_id, *, document=None):
    """Separate candidate: native type2 denial before any reservation, then recovery.

    It does not directly set a colour or revoke an already granted movement.  A
    native red/stop/recovery observation is required; no failure safety is inferred.
    """
    baseline = manifest(normal_files)
    document = spec['stations'][0]['id'] if document is None else document
    validate(normal_files, spec, plans)
    p = _project(normal_files, spec)
    need(type(signal_id) is int and document == spec['stations'][0]['id'] and document in p.byid,
         'Exact existing signal identity required')
    signal = p.byid[document].get(signal_id)
    need(signal is not None and w.kind(signal) == 'OTSignalModel' and
         signal.contents[8].values == [25, 3, 2] and
         c.text(signal.contents[13].value) == 'S_' + document + '_D_B2',
         'Failure target must be the exact shared Down-main B2 native three-aspect Block signal')
    files = dict(normal_files)
    paths = configuration(spec)
    archives = {name: blob for name, blob in files.items() if name != RUN}
    core_run, _ = rb.build_run(archives, catalog_paths=CATALOGS,
        document_paths=['OTDocuments/' + dn + '.opentrack' for dn in paths],
        execution_root=spec['execution_root'], path_style='windows', output_directory='output-failure',
        train_types=[SPEED_TYPE], template=normal_files[RUN], **WINDOW)
    item = _failure_item(document, signal_id)
    docs = {dn: files['OTDocuments/' + dn + '.opentrack'] for dn in paths}
    courses, incident_receipt = incidents.plan(files[CATALOGS['courses']], docs,
        {'incidents': [item], 'set_actions': []}, document_paths=paths, run_bytes=core_run,
        course_path=spec['execution_root'] + '/' + CATALOGS['courses'],
        trains_blob=files[CATALOGS['trains']], depot_blob=files[CATALOGS['depot']],
        train_path=spec['execution_root'] + '/' + CATALOGS['trains'],
        depot_path=spec['execution_root'] + '/' + CATALOGS['depot'])
    files[CATALOGS['courses']] = courses
    files[RUN] = core_run + ('Incident#' + INCIDENT + '#\n').encode('ascii')
    validation = validate(files, spec, plans, output_directory='output-failure', incident_names=(INCIDENT,))
    parsed_incidents = c.array(w.load_next_compatible(courses)[0].contents[1].value)
    decoded = [incidents.item_from_object(obj) for obj in parsed_incidents]
    need(decoded == [item], 'Fixed-window native type2 incident roundtrip differs')
    changed = sorted(name for name in files if files[name] != normal_files[name])
    need(changed == sorted((RUN, CATALOGS['courses'])) and manifest(normal_files) == baseline,
         'Failure candidate changed normal bytes or unrelated members')
    return files, {'schema': 'yard-shared-main-signal-blockage-case/1', 'spec': copy.deepcopy(spec),
        'plans': copy.deepcopy(plans), 'normal_members': baseline, 'members': manifest(files),
        'incident': item, 'incident_receipt': incident_receipt, 'validation': validation,
        'changed_members': changed, 'output_directory': 'output-failure',
        'incident_explicitly_selected_by_run': INCIDENT,
        'failure_starts_before_new_route_reservation': True,
        'does_not_revoke_already_granted_routes': True, 'does_not_directly_write_lamp_colour': True,
        'saved': False, 'native_application_executed': False,
        'fault_red_stop_recovery_runtime_verified': False}
