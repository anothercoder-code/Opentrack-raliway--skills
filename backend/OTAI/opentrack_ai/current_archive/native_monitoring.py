"""Saved OpenTrack power-supply and measurement models from native stock shapes."""

from copy import deepcopy
import re

from . import path_functions, route_factory, writer as w
from .graph_references import incoming_counts
from .zero_generation import native_signal_routes as ns


DEMO_DONOR_SHA256 = '55f03e67a8b9c028bae2662b0a69f595de80e62b98f96e7fb97aab4de93b408a'
SUPPLY = ['i', 'f', 'f', 'f', 'i', 'i', '@', '@', 'iiii', '@', 'i', 'i', '@']
INSTRUMENT = ['i', 'f', 'f', 'f', 'i', 'i', '@', '@', 'i', 'ff', 'ff', '@', '@', '@', '@', 'i', 'i']
DOCUMENT3 = ['i', 'i', '@', 'i', 'i', '@', '@', '@', 'ffff', 'ffff', 'ffff', 'f',
             '@', '@', 'ffff', 'iii', 'ff', '@', '@']
FLAGS = {'name': 1, 'course': 2, 'speed': 4, 'clock': 8, 'headway': 16, 'marked': 32,
         'train_count': 64, 'switch_operations': 128, 'signal_stops': 256}
MAIN_SIGNAL_TYPES = frozenset({1, 2, 24, 25, 26})
POWER_SYSTEM_CODES = frozenset(range(15)) | frozenset(range(101, 201))
PROPULSION_SEGMENT_CODES = frozenset({1000, 1001, 1002})
PROPULSION_GROUP_CODE = 2000
POWER_EDGE_SLOT = 17
PROPULSION_EDGE_SLOT = 18


def require(condition, message):
    if not condition:
        raise ValueError(message)


def shape(obj, kind, version, groups):
    require(w.kind(obj) == kind and obj.clazz.version == version and
            [''.join(value.decode() for value in group.encodings) for group in obj.contents] == groups,
            f'Outside the reviewed {kind} v{version} saved shape')


def models(root):
    require(w.kind(root) == 'OTDocument' and root.clazz.version in (3, 4), 'Use an evidenced original worksheet')
    if root.clazz.version == 4:
        _, identities = route_factory.document(root)
        return root.contents[2].value, identities
    shape(root, 'OTDocument', 3, DOCUMENT3)
    listing = root.contents[2].value
    all_models = w.elements(listing)
    identities = {obj.contents[0].value: obj for obj in all_models}
    require(len(identities) == len(all_models) and all(type(item) is int for item in identities),
            'Worksheet graphical identities are not unique')
    return listing, identities


def model(identities, model_id, kind):
    obj = identities.get(model_id)
    require(obj is not None and w.kind(obj) == kind, f'Expected selected {kind} at ID {model_id}')
    return obj


def identifier(obj):
    return obj.contents[0].value


def label(name):
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,59}', name)
            and name == name.strip(), 'Use a native output-safe printable name up to 60 characters')
    return name


def normalized_name(name):
    return name.replace(' ', '_').casefold()


def unique_name(items, kind, slot, name, exclude=None):
    for other in items.values():
        if w.kind(other) == kind and other is not exclude:
            existing = w.string(other.contents[slot].value)
            require(normalized_name(existing) != normalized_name(name), 'Native output name collides in this worksheet')


def floats(values):
    return [ns.number(value, -1000000, 1000000) for value in values]


def new_id(identities, reserve_after=-1):
    value = max(reserve_after, max(identities, default=-1)) + 1
    require(0 <= value <= 2_147_483_647, 'Native identity space exhausted')
    return value


def supply_shape(obj):
    shape(obj, 'OTPowerSupplyModel', 2, SUPPLY)
    require(w.kind(obj.contents[9].value) == 'NSColor'
            and w.kind(obj.contents[12].value) == 'NSMutableArray', 'Unsupported power-area presentation shape')


def supply_code(obj):
    return obj.contents[8].values[0]


def segment_group_members(obj, items):
    members = w.elements(obj.contents[12].value)
    require(all(w.kind(member) == 'OTPowerSupplyModel' and items.get(identifier(member)) is member
                and supply_code(member) in PROPULSION_SEGMENT_CODES for member in members),
            'Propulsion group contains a foreign or non-segment object')
    ids = [identifier(member) for member in members]
    require(len(ids) == len(set(ids)), 'Propulsion group contains duplicate segment identities')
    return ids


def instrument_shape(obj):
    version = obj.clazz.version
    require(version in (3, 4), 'Unsupported instrument version')
    shape(obj, 'OTMeasuringModel', version, INSTRUMENT + (['if'] if version == 4 else []))
    require(w.kind(obj.contents[12].value) == 'NSMutableArray'
            and all(w.kind(obj.contents[index].value) == 'NSColor' for index in (13, 14)),
            'Unsupported measuring instrument color/Edge array shape')


def records(root):
    _, items = models(root)
    output = {'power_supplies': [], 'instruments': []}
    edge_associations = {}
    for ident, edge in items.items():
        if w.kind(edge) != 'OTEdgeModel':
            continue
        for slot in (POWER_EDGE_SLOT, PROPULSION_EDGE_SLOT):
            if len(edge.contents) > slot and edge.contents[slot].encodings == [b'@']:
                owner = edge.contents[slot].value
                if owner is not None:
                    edge_associations.setdefault((slot, id(owner)), []).append(ident)
    for ident, obj in items.items():
        kind = w.kind(obj)
        if kind == 'OTPowerSupplyModel':
            supply_shape(obj)
            code = supply_code(obj)
            row = {'id': ident, 'name': w.string(obj.contents[7].value), 'power_system_code': code,
                   'icon_mode': obj.contents[8].values[1], 'edge_mode': obj.contents[8].values[2],
                   'position': [obj.contents[i].value for i in (2, 3)],
                   'edge_ids': sorted(edge_associations.get((POWER_EDGE_SLOT, id(obj)), []))}
            if code in PROPULSION_SEGMENT_CODES:
                row.update(kind='propulsion_segment',
                           edge_ids=sorted(edge_associations.get((PROPULSION_EDGE_SLOT, id(obj)), [])),
                           allow_multiple_trains=bool(obj.contents[10].value))
            elif code == PROPULSION_GROUP_CODE:
                row.update(kind='propulsion_group', segment_ids=segment_group_members(obj, items),
                           max_active_segments=obj.contents[11].value)
            output['power_supplies'].append(row)
        elif kind == 'OTMeasuringModel':
            instrument_shape(obj)
            end = obj.contents[7].value
            require(end is not None and items.get(identifier(end)) is end and end.contents[13].value is obj,
                    'Instrument and directional End association is not reciprocal')
            selected_edges = w.elements(obj.contents[12].value)
            require(all(w.kind(edge) == 'OTEdgeModel' and items.get(identifier(edge)) is edge for edge in selected_edges),
                    'Instrument contains a foreign Edge')
            mask = obj.contents[15].value
            output['instruments'].append({'id': ident, 'name': w.string(obj.contents[11].value),
                 'end_id': identifier(end), 'edge_ids': [identifier(edge) for edge in selected_edges],
                 'direction_code': obj.contents[8].value, 'frame': [*obj.contents[9].values, *obj.contents[10].values],
                 'display': [name for name, bit in FLAGS.items() if mask & bit],
                 'visible': True if len(obj.contents) < 18 else bool(obj.contents[17].values[0]),
                 'size_code': obj.contents[16].value})
    return output


def supply_options(obj, items, operation, allowed_codes):
    if 'name' in operation:
        name = label(operation['name'])
        unique_name(items, 'OTPowerSupplyModel', 7, name, obj)
        obj.contents[7].value = ns.string(name)
    for item, index in (('power_system_code', 0), ('icon_mode', 1), ('edge_mode', 2)):
        if item in operation:
            value = operation[item]
            require(type(value) is int and (value in allowed_codes if index == 0 else 0 <= value <= 2),
                    'Use a reviewed named power system or presentation value')
            obj.contents[8].values[index] = value
    if 'position' in operation:
        obj.contents[2].value, obj.contents[3].value = floats(operation['position'])


def assign_power(items, power, edge_ids, replace, *, slot=POWER_EDGE_SLOT):
    require(edge_ids and len(edge_ids) == len(set(edge_ids)), 'Select unique native power or propulsion Edge IDs')
    for edge_id in edge_ids:
        edge = model(items, edge_id, 'OTEdgeModel')
        route_factory.layout(edge, 'OTEdgeModel', 3, route_factory.EDGE, graphic=True)
        previous = edge.contents[slot].value
        require(previous is None or (w.kind(previous) == 'OTPowerSupplyModel'
                                     and items.get(identifier(previous)) is previous),
                'Edge contains an unrecognized external power reference')
        require(previous is None or previous is power or replace,
                f'Edge {edge_id} already has a power or propulsion assignment')
        edge.contents[slot].value = power


def require_power_family(obj, operation):
    supply_shape(obj)
    code = supply_code(obj)
    if operation == 'propulsion_segment':
        require(code in PROPULSION_SEGMENT_CODES, 'Select a native propulsion segment')
    elif operation == 'propulsion_group':
        require(code == PROPULSION_GROUP_CODE, 'Select a native propulsion segment group')
    else:
        require(code not in PROPULSION_SEGMENT_CODES and code != PROPULSION_GROUP_CODE,
                'Select a regular power supply for the power Edge slot')


def edit_power_model(items, donors, operation, reserve_after):
    action, family = operation['action'].split('_', 1)
    if action == 'create':
        native = model(donors, 775, 'OTPowerSupplyModel')
        supply_shape(native)
        require(native.contents[6].value is None and not w.elements(native.contents[12].value),
                'Stock supply template carries external graph references')
        obj = deepcopy(native)
        ident = new_id(items, reserve_after)
        obj.contents[0].value = ident
        obj.contents[10].value = 0
        obj.contents[11].value = 1
        if family == 'propulsion_group':
            obj.contents[8].values[0] = PROPULSION_GROUP_CODE
    else:
        ident = operation['id']
        obj = model(items, ident, 'OTPowerSupplyModel')
        require_power_family(obj, family)

    codes = PROPULSION_SEGMENT_CODES if family == 'propulsion_segment' else POWER_SYSTEM_CODES
    supply_options(obj, items, operation, codes)
    if family == 'propulsion_segment' and 'allow_multiple_trains' in operation:
        value = operation['allow_multiple_trains']
        require(type(value) is bool, 'Allowing multiple trains must be a boolean')
        obj.contents[10].value = int(value)
    if family == 'propulsion_group':
        if 'segment_ids' in operation:
            segments = operation['segment_ids']
            require(len(segments) == len(set(segments)), 'Select unique propulsion segment IDs')
            members = [model(items, segment, 'OTPowerSupplyModel') for segment in segments]
            for member in members:
                require_power_family(member, 'propulsion_segment')
            w.set_elements(obj.contents[12].value, members)
        if 'max_active_segments' in operation:
            capacity = operation['max_active_segments']
            require(type(capacity) is int and 0 <= capacity <= 2_147_483_647,
                    'Use a nonnegative native propulsion segment group limit')
            obj.contents[11].value = capacity

    if action == 'create':
        require_power_family(obj, family)
        items[ident] = obj
        if family != 'propulsion_group':
            slot = PROPULSION_EDGE_SLOT if family == 'propulsion_segment' else POWER_EDGE_SLOT
            assign_power(items, obj, operation['edge_ids'], operation.get('replace', False), slot=slot)
    return ident


POWER_MODEL_EDITS = frozenset({
    'create_supply', 'update_supply', 'create_propulsion_segment', 'update_propulsion_segment',
    'create_propulsion_group', 'update_propulsion_group',
})


def delete_power_model(root, items, operation):
    ident = operation['id']
    obj = model(items, ident, 'OTPowerSupplyModel')
    supply_shape(obj)
    edge_slots = []
    groups = []
    for candidate in items.values():
        if w.kind(candidate) == 'OTEdgeModel':
            route_factory.layout(candidate, 'OTEdgeModel', 3, route_factory.EDGE, graphic=True)
            for slot in (POWER_EDGE_SLOT, PROPULSION_EDGE_SLOT):
                field = candidate.contents[slot]
                if field.value is obj:
                    edge_slots.append((identifier(candidate), slot, field))
        elif (w.kind(candidate) == 'OTPowerSupplyModel' and supply_code(candidate) == PROPULSION_GROUP_CODE
              and ident in segment_group_members(candidate, items)):
            groups.append(candidate)
    require(incoming_counts(root)[id(obj)] == 1 + len(edge_slots) + len(groups),
            'Power model has additional references outside native Edge and group memberships')
    for _, _, field in edge_slots:
        field.value = None
    for group in groups:
        members = group.contents[12].value
        w.set_elements(members, [member for member in w.elements(members) if member is not obj])
    del items[ident]
    return {'id': ident, 'cleared_supply_edge_ids': [edge for edge, slot, _ in edge_slots if slot == POWER_EDGE_SLOT],
            'cleared_propulsion_edge_ids': [edge for edge, slot, _ in edge_slots if slot == PROPULSION_EDGE_SLOT],
            'removed_from_group_ids': [identifier(group) for group in groups]}


def validate_instrument_location(items, target, display_mask, *, check_incidence=False):
    if display_mask & FLAGS['signal_stops']:
        signal = target.contents[11].value
        require(signal is not None, 'Signal-stop measurement requires the anchored main signal')
        route_factory.layout(signal, 'OTSignalModel', 11, route_factory.SIGNAL, graphic=True)
        require(items.get(identifier(signal)) is signal and signal.contents[8].values[0] in MAIN_SIGNAL_TYPES
                and signal.contents[7].value is target, 'Measurement must bind the reciprocal main signal')
    if display_mask & FLAGS['switch_operations']:
        other = model(items, target.contents[8].value, 'OTEndModel')
        legs = [other.contents[index].value for index in (9, 10)]
        require(other.contents[8].value == identifier(target) and None not in legs and legs[0] is not legs[1],
                'Switch measurement belongs on the reciprocal End facing a real two-leg turnout')
        if check_incidence:
            for edge in legs:
                require(other in verified_edge_ends(items, edge), 'Turnout leg endpoint is not reciprocal')


def verified_edge_ends(items, edge):
    route_factory.layout(edge, 'OTEdgeModel', 3, route_factory.EDGE, graphic=True)
    require(items.get(identifier(edge)) is edge, 'Instrument edge must belong to this worksheet')
    ends = [edge.contents[index].value for index in (7, 8)]
    require(ends[0] is not ends[1] and all(w.kind(end) in {'OTEndModel', 'OTConnModel'}
            and items.get(identifier(end)) is end and edge in [end.contents[index].value for index in (9, 10)]
            for end in ends), 'Instrument Edge endpoint is not reciprocal')
    return ends


def instrument_options(obj, items, target, operation):
    if 'name' in operation:
        name = label(operation['name'])
        unique_name(items, 'OTMeasuringModel', 11, name, obj)
        obj.contents[11].value = ns.string(name)
    if 'display' in operation:
        flags = operation['display']
        require(len(flags) == len(set(flags)) and set(flags) <= FLAGS.keys(), 'Invalid instrument display flags')
        mask = sum(FLAGS[name] for name in flags)
        validate_instrument_location(items, target, mask)
        obj.contents[15].value = mask
    if 'direction_code' in operation:
        require(type(operation['direction_code']) is int and operation['direction_code'] in (1, 2, 3),
                'Invalid original measurement direction code')
        obj.contents[8].value = operation['direction_code']
    if 'size_code' in operation:
        require(type(operation['size_code']) is int and 1 <= operation['size_code'] <= 7,
                'Measure size code must be 1 through 7')
        obj.contents[16].value = operation['size_code']
    if 'edge_ids' in operation:
        edge_ids = operation['edge_ids']
        require(len(edge_ids) == len(set(edge_ids)), 'Distinct instrument Edge IDs required')
        obj.contents[12].value = path_functions.array_like(obj.contents[12].value,
                                                         [model(items, edge_id, 'OTEdgeModel') for edge_id in edge_ids])
    if 'frame' in operation:
        frame = floats(operation['frame'])
        require(all(1 <= value <= 1000 for value in frame[2:]), 'Instrument frame size is out of range')
        obj.contents[9].values = frame[:2]
        obj.contents[10].values = frame[2:]
        obj.contents[17].values[1] = frame[2]
    if 'visible' in operation:
        require(type(operation['visible']) is bool, 'Use an actual visibility boolean')
        obj.contents[17].values[0] = int(operation['visible'])


def upgrade_instrument(obj):
    instrument_shape(obj)
    if obj.clazz.version == 3:
        obj.clazz = w.Class(b'OTMeasuringModel', 4, obj.clazz.superclass)
        obj.contents.append(w.TypedGroup([b'i', b'f'], [1, obj.contents[10].values[0]]))


def paired_instrument_end(items, end_id):
    end = model(items, end_id, 'OTEndModel')
    route_factory.layout(end, 'OTEndModel', 7, route_factory.END, graphic=True)
    opposite = model(items, end.contents[8].value, 'OTEndModel')
    route_factory.layout(opposite, 'OTEndModel', 7, route_factory.END, graphic=True)
    require(opposite is not end and opposite.contents[8].value == end_id,
            'Instrument requires reciprocal directional Ends')
    return end


def relocate_instrument(root, items, operation):
    ident, from_id, to_id = (operation[key] for key in ('id', 'from_end_id', 'to_end_id'))
    obj = model(items, ident, 'OTMeasuringModel')
    instrument_shape(obj)
    old = paired_instrument_end(items, from_id)
    target = paired_instrument_end(items, to_id)
    require(obj.contents[7].value is old and old.contents[13].value is obj,
            'Reviewed source End does not carry the selected instrument')
    require(old is not target and target.contents[13].value is None,
            'Select a different directional End without an existing measuring instrument')
    require(incoming_counts(root)[id(obj)] == 2, 'Measuring instrument has unexpected saved references')
    validate_instrument_location(items, target, obj.contents[15].value, check_incidence=True)

    edge_array = obj.contents[12].value
    edges = path_functions.mutable_array(edge_array)
    before_edges = [identifier(edge) for edge in edges]
    require(('edge_ids' in operation) == ('expected_edge_ids' in operation),
            'Provide both expected and replacement instrument Edge IDs to change the observation area')
    if 'edge_ids' in operation:
        require(operation['expected_edge_ids'] == before_edges, 'Reviewed instrument Edge area has changed')
        edge_ids = operation['edge_ids']
        require(len(edge_ids) == len(set(edge_ids)), 'Distinct instrument Edge IDs required')
        edges = [model(items, edge_id, 'OTEdgeModel') for edge_id in edge_ids]
    for edge in edges:
        verified_edge_ends(items, edge)

    dx, dy = floats([target.contents[i].value - old.contents[i].value for i in (2, 3)])
    offset = [dx, dy]
    obj.contents[2].value, obj.contents[3].value = floats(
        [obj.contents[i].value + delta for i, delta in zip((2, 3), offset)])
    configured_frame = any((*obj.contents[9].values, *obj.contents[10].values))
    if configured_frame:
        obj.contents[9].values = floats([value + delta for value, delta in zip(obj.contents[9].values, offset)])
    for index in (4, 5):
        obj.contents[index].value = target.contents[index].value
    if 'edge_ids' in operation:
        obj.contents[12].value = path_functions.array_like(edge_array, edges)
    old.contents[13].value = None
    target.contents[13].value = obj
    obj.contents[7].value = target
    return {'id': ident, 'from_end_id': from_id, 'to_end_id': to_id, 'frame_translation': offset if configured_frame else [0.0, 0.0],
            'before_edge_ids': before_edges, 'after_edge_ids': [identifier(edge) for edge in edges]}


def create_instrument(items, donors, operation, reserve_after=-1):
    target = model(items, operation['end_id'], 'OTEndModel')
    require(target.clazz.version == 7 and target.contents[13].value is None,
            'Select a current directional End without an existing measuring instrument')
    native = model(donors, 796, 'OTMeasuringModel')
    instrument_shape(native)
    require(native.contents[6].value is None, 'Unexpected reference in stock instrument layout')
    # Clone only detached presentation values, leaving native worksheet objects local.
    obj = w.GenericArchivedObject(native.clazz, [
        deepcopy(group) if index not in (7, 12)
        else w.TypedGroup([b'@'], [None] if index == 7 else [
            ns.obj([('NSMutableArray', 0), ('NSArray', 0), ('NSObject', 0)], [('i', [0])])])
        for index, group in enumerate(native.contents)])
    upgrade_instrument(obj)
    ident = new_id(items, reserve_after)
    obj.contents[0].value = ident
    for index in (2, 3, 4, 5):
        obj.contents[index].value = target.contents[index].value
    obj.contents[7].value = target
    instrument_options(obj, items, target, operation)
    target.contents[13].value = obj
    items[ident] = obj
    return ident


def create_instruments_at_locations(items, donors, operation, reserve_after=-1):
    # OTDocView iterates the graphic array in reverse candidate order when
    # allocating and OTMeasuringModel only attaches to an ordinary paired End.
    scope = operation.get('selected_end_ids')
    selection = set(scope) if scope is not None else None
    if selection is not None:
        require(len(selection) == len(scope), 'Select each directional End once')
        for ident in selection:
            model(items, ident, 'OTEndModel')
    location = operation['location']
    require(location in {'main_signal', 'switch'}, 'Unknown instrument location')
    candidates = []
    monitored = []
    for ident, end in items.items():
        if w.kind(end) != 'OTEndModel' or (selection is not None and ident not in selection):
            continue
        route_factory.layout(end, 'OTEndModel', 7, route_factory.END, graphic=True)
        opposite = items.get(end.contents[8].value)
        if opposite is None or w.kind(opposite) != 'OTEndModel':
            continue
        route_factory.layout(opposite, 'OTEndModel', 7, route_factory.END, graphic=True)
        require(opposite is not end and opposite.contents[8].value == ident,
                'Instrument requires reciprocal directional Ends')
        if location == 'main_signal':
            signal = end.contents[11].value
            if signal is None:
                continue
            route_factory.layout(signal, 'OTSignalModel', 11, route_factory.SIGNAL, graphic=True)
            require(items.get(identifier(signal)) is signal and signal.contents[7].value is end,
                    'Main signal and directional End association is not reciprocal')
            if signal.contents[8].values[0] not in MAIN_SIGNAL_TYPES:
                continue
        else:
            legs = [opposite.contents[index].value for index in (9, 10)]
            if None in legs:
                continue
            require(legs[0] is not legs[1]
                    and all(w.kind(edge) == 'OTEdgeModel' and items.get(identifier(edge)) is edge for edge in legs),
                    'Instrument requires two distinct local turnout legs')
            for edge in legs:
                route_factory.layout(edge, 'OTEdgeModel', 3, route_factory.EDGE, graphic=True)
                ends = [edge.contents[index].value for index in (7, 8)]
                require(opposite in ends and ends[0] is not ends[1]
                        and all(w.kind(end) in {'OTEndModel', 'OTConnModel'}
                                and items.get(identifier(end)) is end
                                and edge in [end.contents[index].value for index in (9, 10)] for end in ends),
                        'Turnout leg endpoint is not reciprocal')
        if end.contents[13].value is None:
            candidates.append(end)
        else:
            monitored.append(ident)

    require(len(candidates) <= 4096, 'Select at most 4096 eligible instrument locations per worksheet')
    created = []
    if len(candidates) >= 2:
        caption = 'Main Signal' if location == 'main_signal' else 'Switch'
        flag = 'signal_stops' if location == 'main_signal' else 'switch_operations'
        for end in reversed(candidates):
            target = identifier(end)
            x, y = (end.contents[index].value for index in (2, 3))
            ident = create_instrument(items, donors, {
                'end_id': target, 'name': f'{caption} End {target}',
                'frame': [x + 12, y + 12, 90, 42],
                'display': ['name', 'course', 'speed', 'clock', 'headway', 'train_count', flag],
            }, reserve_after)
            created.append({'end_id': target, 'instrument_id': ident})
    return {'location': location, 'candidate_end_ids': [identifier(end) for end in candidates],
            'already_monitored_end_ids': monitored, 'created': created,
            'stock_minimum_eligible_count': 2}


def transform(source, donor, operations):
    root, version = w.load_next_compatible(source)
    listing, items = models(root)
    require(root.clazz.version == 4, 'Writing requires the current version-4 OpenTrack worksheet')
    before = records(root)
    donors = {} if donor is None else models(w.load_next_compatible(donor)[0])[1]
    changes = []
    reserve_after = -1
    for operation in operations:
        action = operation['action']
        if action in POWER_MODEL_EDITS:
            ident = edit_power_model(items, donors, operation, reserve_after)
        elif action == 'delete_power_model':
            w.set_elements(listing, list(items.values()))
            change = delete_power_model(root, items, operation)
            reserve_after = max(reserve_after, change['id'])
            changes.append({'action': action, **change})
            continue
        elif action in {'set_edge_supply', 'set_edge_propulsion_segment'}:
            is_supply = action == 'set_edge_supply'
            ident = operation['supply_id' if is_supply else 'segment_id']
            obj = None if ident is None else model(items, ident, 'OTPowerSupplyModel')
            if obj is not None:
                require_power_family(obj, 'supply' if is_supply else 'propulsion_segment')
            slot = POWER_EDGE_SLOT if is_supply else PROPULSION_EDGE_SLOT
            assign_power(items, obj, operation['edge_ids'], operation.get('replace', False) or obj is None, slot=slot)
        elif action == 'create_instrument':
            ident = create_instrument(items, donors, operation, reserve_after)
        elif action == 'create_instruments_at_locations':
            changes.append({'action': action, **create_instruments_at_locations(items, donors, operation, reserve_after)})
            continue
        elif action == 'update_instrument':
            ident = operation['id']
            obj = model(items, ident, 'OTMeasuringModel')
            upgrade_instrument(obj)
            instrument_options(obj, items, obj.contents[7].value, operation)
        elif action == 'relocate_instrument':
            # New instruments in a preceding operation must be present in both the graph and its identity list.
            w.set_elements(listing, list(items.values()))
            changes.append({'action': action, **relocate_instrument(root, items, operation)})
            continue
        else:
            raise ValueError('Unknown native monitoring operation')
        changes.append({'action': action, 'id': ident})
    w.set_elements(listing, list(items.values()))
    expected = records(root)
    changed = w.dump_verified(root, version)
    actual = records(w.load_next_compatible(changed)[0])
    require(actual == expected, 'Fresh archive changed a measurement or power association')
    return changed, {'operations': changes, 'before': before, 'after': actual,
                     'native_execution_verified': False}
