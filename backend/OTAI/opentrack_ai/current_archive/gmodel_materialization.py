"""Materialize the reviewed original bridge topology as an ordinary Document4."""

from collections import Counter
import re

from . import route_factory, writer
from .course_factories import dictionary
from .infrastructure_railml import QuotedString, archive_list, finite, gmodel_graph
from .zero_generation import topology


need = topology.need
GRAPHIC = set('isa identification angle origin_x origin_y align_x align_y label'.split())
END = GRAPHIC | set('element idOfRelated firstEdge secondEdge signal station measuringInstrument locality routeList '
                    'shuntingList pathList addition highestGivenRspID stationEndType switchTime anInfo hasInsulatedJoint '
                    'hasAxleCounter'.split())
CONNECTOR = END | {'dragFileName', 'blockTopo', 'blockEnd', 'internalConnection'}
EDGE = GRAPHIC | set('end1 end2 trackType length radius gradient loopType dLinkType crossSectionContactWire_mm2 '
                     'crossSectionTunnel_m2 anInt remark xLinkTo xLinkFrom speedKeys speedDict powerSupply '
                     'propulsionSegment trackName lineName'.split())
ELEMENT = GRAPHIC | {'ends'}
ORIENTATIONS = (((1, 0), (2, 0)), ((0, 4), (0, 3)))


def absent(value):
    return value is None or (type(value) is str and value == 'nil')


def number(row, field, default):
    return finite(row.get(field, default), field)


def integer(value, name):
    need(isinstance(value, str) and re.fullmatch(r'-?[0-9]{1,10}', value) is not None, f'Expected integer {name}')
    return topology.exact(int(value), -(2**31), 2**31 - 1, name)


def label(value):
    if absent(value):
        return ''
    need(isinstance(value, str), 'Expected a scalar GModel label')
    if isinstance(value, QuotedString):
        parts = re.findall(r'[^\\]+|\\.', value)
        need(''.join(parts) == value and all(not p.startswith('\\') or p[1:] in ('\\', '"') for p in parts),
             'Unsupported escape sequence in GModel label')
        value = ''.join(p[1:] if p.startswith('\\') else p for p in parts)
    value = str(value)
    need(all(32 <= ord(ch) <= 126 for ch in value), 'Worksheet labels require printable native ASCII')
    return topology.text(value, 'GModel label')


def fields(row, allowed, name):
    extra = set(row) - allowed
    need(not extra and absent(row.get('label')), f'Unsupported {name} fields or attached graphic label: {sorted(extra)}')


def slots(row):
    return tuple(None if absent(row.get(field)) else str(row[field]) for field in ('firstEdge', 'secondEdge'))


def edge_speeds(model, row, fallback, speed_profiles=None):
    reference = row.get('speedDict')
    entries = {}
    if not absent(reference):
        item = model.get(reference) if isinstance(reference, str) else None
        need(isinstance(item, dict) and item.get('isa') in ('NSMutableDictionary', 'NSDictionary')
             and isinstance(item.get('elements'), dict), 'Unsupported GModel speed dictionary')
        entries = item['elements']
    keys = list(entries) if absent(row.get('speedKeys')) else archive_list(model, row['speedKeys'])
    need(len(keys) == len(set(keys)) and set(keys) == set(entries), 'GModel speed keys differ from their dictionary')
    if not keys:
        need(not speed_profiles, 'Selected RailML speed profiles are missing from a GModel Edge')
        need(fallback, 'An empty GModel speed dictionary requires explicit fallback_speeds')
        return fallback, True
    result, train_types = [], set()
    for key in keys:
        ref = entries[key]
        item = model.get(ref) if isinstance(ref, str) else None
        native_key = model.get(key) if type(key) is str else None
        if native_key is not None:
            need(isinstance(native_key, dict) and set(native_key) == {'isa', 'string'} and
                 native_key['isa'] in ('NSString', 'NSMutableString') and not absent(native_key['string']),
                 'Unsupported GModel speed category reference')
            cat = label(native_key['string'])
        else:
            cat = label(key)
        need(cat and cat not in train_types, 'Empty or repeated GModel speed category')
        train_types.add(cat)
        need(isinstance(item, dict) and set(item) <= {'isa', 'trainType', 'speed12', 'speed21', 'reserved'}
             and item.get('isa') == 'OTSpeed' and not absent(item.get('trainType')) and label(item['trainType']) == cat
             and integer(item.get('reserved', '0'), 'speed reserved') == 0, 'Unsupported GModel OTSpeed record')
        result.append({'train_type': cat, 'speed12_kmh': integer(item.get('speed12'), 'speed12'),
                       'speed21_kmh': integer(item.get('speed21'), 'speed21')})
    if speed_profiles:
        by_category = {item['train_type']: item for item in result}
        need(set(by_category) == {str(index) for index in range(len(speed_profiles))},
             'GModel Edge speed slots differ from the explicit RailML ETCS mapping')
        result = [{**by_category[str(slot)], 'train_type': name} for slot, name in enumerate(speed_profiles)]
    return result, False


def build_plan(raw, fallback_speeds, speed_profiles=None):
    model, _, graphics = gmodel_graph(raw)
    classes = Counter(row['isa'] for row in graphics.values())
    need(set(classes) <= {'OTEndModel', 'OTConnModel', 'OTEdgeModel', 'OTElement'},
         f'Active or unreviewed GModel classes require a separate exchange contract: {sorted(classes)}')
    ids = {key: integer(row.get('identification'), 'graphic identification') for key, row in graphics.items()}
    need(len(set(ids.values())) == len(ids) and all(n >= 0 for n in ids.values()), 'Unique nonnegative GModel graphic IDs required')
    ends = {key: row for key, row in graphics.items() if row['isa'] in ('OTEndModel', 'OTConnModel')}
    by_end_id = {ids[key]: key for key in ends}
    source_elements = {key: row for key, row in graphics.items() if row['isa'] == 'OTElement'}
    partition = []
    for key, row in source_elements.items():
        fields(row, ELEMENT, 'safety element')
        members = archive_list(model, row.get('ends'))
        need(members and len(set(members)) == len(members)
             and all(member in ends and ends[member].get('element') == key for member in members),
             'Nonreciprocal GModel safety membership')
        partition.extend(members)
    need(len(set(partition)) == len(partition) and set(partition) == set(ends), 'GModel safety elements must partition the Ends')

    end_refs, end_specs, vertices, connectors = {}, {}, [], []
    for key, row in ends.items():
        connector = row['isa'] == 'OTConnModel'
        fields(row, CONNECTOR if connector else END, 'End')
        incoming = slots(row)
        need(incoming[0] is not None or incoming[1] is None, 'GModel End has a second edge without a first')
        need(all(absent(row.get(field)) for field in ('signal', 'station', 'measuringInstrument', 'routeList',
                                                      'shuntingList', 'pathList')),
             'GModel End carries an active railway object outside topology materialization')
        need(integer(row.get('highestGivenRspID', '-1'), 'RSP ID') == -1
             and integer(row.get('stationEndType', '1'), 'station End type') in (0, 1)
             and all(integer(row.get(flag, '0'), flag) == 0 for flag in ('hasInsulatedJoint', 'hasAxleCounter')),
             'GModel End carries station, detection or movement settings outside this contract')
        if connector:
            need(incoming == (None, None) and label(row.get('blockTopo')) == '' and label(row.get('dragFileName')) == ''
                 and integer(row.get('blockEnd'), 'connector block End') == -1
                 and integer(row.get('internalConnection', '0'), 'internal connector') == 0,
                 'An active GModel connector needs a cross-document exchange contract')
            connectors.append(ids[key])
        related = by_end_id.get(integer(row.get('idOfRelated'), 'related End ID'))
        need(related is not None and related != key and integer(ends[related].get('idOfRelated'), 'paired End') == ids[key]
             and not (connector and ends[related]['isa'] == 'OTConnModel'), 'GModel Ends must form reciprocal vertex pairs')
        default_two = integer(row.get('anInfo', '0'), 'switch default')
        need(default_two in (0, 1) and (not default_two or incoming[1] is not None), 'Invalid GModel default branch')
        switch_time = number(row, 'switchTime', 0)
        need(switch_time >= 0, 'Expected a nonnegative GModel switch time')
        position = tuple(number(row, axis, None) for axis in ('origin_x', 'origin_y'))
        alignment = tuple(integer(row.get(axis, '0'), axis) for axis in ('align_x', 'align_y'))
        end_specs[key] = {'position': position, 'alignment': alignment, 'related': related, 'element': row['element'],
                          'slots': incoming, 'default_two': default_two, 'name': label(row.get('addition')),
                          'switch_time': switch_time, 'angle': number(row, 'angle', 0),
                          'locality': number(row, 'locality', -99999)}
    for key, end in end_specs.items():
        other = end['related']
        if key in end_refs:
            continue
        peer = end_specs[other]
        need(end['position'] == peer['position'], 'GModel paired Ends disagree on worksheet position')
        matched = [pair for pair in ORIENTATIONS if set(pair) == {end['alignment'], peer['alignment']}]
        need(len(matched) == 1, 'GModel pair needs one reviewed horizontal or vertical alignment')
        pair = matched[0]
        sides = (key, other) if end['alignment'] == pair[0] else (other, key)
        name = f'vertex-{min(ids[key], ids[other])}'
        end_refs.update({identifier: (name, index) for index, identifier in enumerate(sides)})
        vertices.append({'key': name, 'x': end['position'][0], 'y': end['position'][1],
                         'orientation': 'horizontal' if pair == ORIENTATIONS[0] else 'vertical',
                         'names': [end_specs[side]['name'] for side in sides],
                         'insulated_joint': [False, False], 'axle_counter': [False, False]})

    edges, edge_ends, sections, fallback_ids = [], {}, {}, []
    for key, row in graphics.items():
        if row['isa'] != 'OTEdgeModel':
            continue
        fields(row, EDGE, 'edge')
        need(all(absent(row.get(name)) for name in ('xLinkTo', 'xLinkFrom', 'powerSupply', 'propulsionSegment')),
             'GModel Edge has active cross-link, power supply or propulsion objects')
        left, right = row.get('end1'), row.get('end2')
        need(isinstance(left, str) and isinstance(right, str) and left in end_specs and right in end_specs
             and key in end_specs[left]['slots'] and key in end_specs[right]['slots'] and left != right,
             'Nonreciprocal GModel Edge/End slots')
        need(end_specs[left]['position'] != end_specs[right]['position'], 'GModel edge has coincident drawing positions')
        need(end_specs[left]['element'] == end_specs[right]['element'], 'A GModel Edge spans different safety elements')
        need(all(integer(row.get(field, '1'), field) in (0, 1) for field in ('trackType', 'loopType', 'dLinkType')),
             'Nonstandard GModel edge types need their own native profile')
        flags = integer(row.get('anInt', '0'), 'edge flags')
        need(flags in (0, 1, 2, 3), 'Unknown GModel Edge flags')
        speeds, used_fallback = edge_speeds(model, row, fallback_speeds, speed_profiles)
        if used_fallback:
            fallback_ids.append(ids[key])
        sections[key] = [number(row, 'crossSectionContactWire_mm2', 100) or 100,
                         number(row, 'crossSectionTunnel_m2', 40)]
        need(all(value >= 0 for value in sections[key]), 'GModel Edge cross-section requires nonnegative values')
        edge_ends[key] = (left, right)
        edges.append({'key': str(key), 'from': list(end_refs[left]), 'to': list(end_refs[right]),
                      'length_m': integer(row.get('length'), 'Edge length'), 'radius_m': number(row, 'radius', 0),
                      'gradient_per_mille': number(row, 'gradient', 0), 'track_type': 1, 'loop_type': 1, 'dlink_type': 1,
                      'equal_speed': bool(flags & 1), 'rack_rail': bool(flags & 2), 'speeds': speeds,
                      'remark': label(row.get('remark')), 'track_name': label(row.get('trackName')),
                      'line_name': label(row.get('lineName'))})
    need(edges, 'GModel has no physical track edges')
    for key, end in end_specs.items():
        need(all(edge is None or key in edge_ends.get(edge, ()) for edge in end['slots'])
             and (end['slots'][1] is None or end['slots'][0] != end['slots'][1]), 'GModel End refers to an unrelated Edge')
    return {'vertices': vertices, 'edges': edges}, end_specs, end_refs, ids, sections, connectors, fallback_ids


def apply_readback(root, mapping, plan, *, write):
    spec, ends, end_refs, ids, sections, connectors, fallback_ids = plan
    _, inventory = route_factory.document(root)
    current_ends = {key: inventory[mapping['vertex_end_ids'][vertex][side]] for key, (vertex, side) in end_refs.items()}
    current_edges = {key: inventory[model_id] for key, model_id in mapping['edge_ids'].items()}
    live_groups = {}
    for key, end in ends.items():
        record = current_ends[key]
        group = record.contents[7].value
        expected = live_groups.setdefault(end['element'], group)
        need(group is expected, 'GModel has a larger safety group than the reviewed connected-edge partition')
        need(record.contents[8].value == current_ends[end['related']].contents[0].value
             and [record.contents[slot].value for slot in (2, 3)] == [topology.flt(v, 'coordinate') for v in end['position']]
             and tuple(record.contents[slot].value for slot in (4, 5)) == end['alignment']
             and writer.string(record.contents[18].value) == end['name'], 'Native End geometry differs from the source mapping')
        values = {1: topology.flt(end['angle'], 'angle'), 9: current_edges.get(end['slots'][0]),
                  10: current_edges.get(end['slots'][1]), 14: topology.flt(end['locality'], 'locality'),
                  21: topology.flt(end['switch_time'], 'switch time'), 22: end['default_two']}
        for slot, value in values.items():
            if write:
                record.contents[slot].value = value
            else:
                need(record.contents[slot].value == value, 'Native End slot, switch or position failed exact readback')
    need(len(set(live_groups.values())) == len(live_groups), 'GModel safety element groups merged during generation')
    for edge in spec['edges']:
        key = edge['key']
        record = current_edges[key]
        expected_ends = [inventory[mapping['vertex_end_ids'][edge[field][0]][edge[field][1]]]
                         for field in ('from', 'to')]
        need([record.contents[i].value for i in (7, 8)] == expected_ends, 'Native Edge direction changed')
        need(record.contents[9].values == [1, edge['length_m'], topology.flt(edge['radius_m'], 'radius'),
                                           topology.flt(edge['gradient_per_mille'], 'gradient'), 1, 1],
             'Native Edge engineering data failed readback')
        need([writer.string(record.contents[i].value) for i in (12, 19, 20)] ==
             [edge['remark'], edge['track_name'], edge['line_name']], 'Native Edge names failed readback')
        speed_rows = dictionary(record.contents[16].value)
        need({name: item.contents[1].value for name, item in speed_rows.items()} ==
             {item['train_type']: item['speed12_kmh'] for item in edge['speeds']}
             and {name: item.contents[2].value for name, item in speed_rows.items()} ==
             {item['train_type']: item['speed21_kmh'] for item in edge['speeds']}, 'Native directional speeds failed readback')
        need(record.contents[11].value == int(edge['equal_speed']) + 2 * int(edge['rack_rail']),
             'Native Edge flags failed readback')
        values = [topology.flt(v, 'cross-section') for v in sections[key]]
        if write:
            record.contents[10].values = values
        else:
            need(record.contents[10].values == values, 'Native Edge cross section failed readback')
    return {'end_ids': {str(ids[key]): obj.contents[0].value for key, obj in current_ends.items()},
            'edge_ids': {str(ids[key]): obj.contents[0].value for key, obj in current_edges.items()},
            'safety_element_ids': {str(ids[key]): obj.contents[0].value for key, obj in live_groups.items()},
            'normalized_terminal_end_ids': connectors, 'fallback_speed_edge_ids': fallback_ids}


def materialize(gmodel, header, shapes, fallback_speeds, *, speed_profiles=None):
    plan = build_plan(gmodel, fallback_speeds, speed_profiles)
    candidate, generated = topology.generate_network(header, shapes, plan[0])
    root, version = writer.load_next_compatible(candidate)
    left, bottom, width, height = root.contents[9].values
    need(all(left <= item['x'] <= left + width and bottom <= item['y'] <= bottom + height
             for item in plan[0]['vertices']), 'GModel drawing is outside the selected ordinary worksheet view; use a fitting header')
    mapped = apply_readback(root, generated, plan, write=True)
    topology.validate_network(root)
    output = writer.dump_verified(root, version)
    fresh, _ = writer.load_next_compatible(output)
    native = topology.validate_network(fresh)
    need(apply_readback(fresh, generated, plan, write=False) == mapped, 'Native identity mapping changed after archive reload')
    extra = {'recovered_speed_profiles': speed_profiles} if speed_profiles else {}
    return output, {**mapped, **extra, 'topology': native, 'total_track_length_m': sum(edge['length_m'] for edge in plan[0]['edges']),
                    'preserved_directional_slots': True, 'preserved_safety_partition': True,
                    'shape_source_sha256': generated['shapes_sha256'], 'header_source_sha256': generated['source_sha256'],
                    'opaque_header_unchanged': generated['opaque_header_unchanged']}
