"""Mapped original RailML 2.2 rolling-stock import into current native catalogs."""

import copy
from typing import Literal
from xml.etree import ElementTree as ET

from pydantic import StrictBool, model_validator

from ..errors import APIError
from ..railml_values import float_text, imported_points, int_text
from . import catalogs as c, course_factories as cf, writer as w
from .bundle_tools import Source
from .consist_workflow.core import make_trailer, summary
from .engine_curves import DIAGRAM
from .graph_references import incoming_counts
from .multi_document_tools import Inventory
from .operating_plan_edit import need, set_sequence, text
from .operating_plan_edit_tools import Id, OperatingPlanEditTools, operating_candidate
from .project_candidate_publication import ProjectSave
from .stock_operations import CATEGORY_LAYOUT
from .tools import sha
from .zero_generation.native_signal_routes import arr, obj, string
from .zero_operations.vehicle_catalogs import validate_graph


MAX_SIZE = 20_000_000
RAILML_22 = '{http://www.railml.org/schemas/2013}'


class ImportRollingStockRailML(ProjectSave):
    source_project: Inventory
    exchange: Source
    engine_template: Id
    formation_template: Id
    category: Id | None = None
    accept_inherited_model: Literal[True]
    on_conflict: Literal['error', 'keep', 'replace'] = 'error'
    recompute_curve_speed_limit: StrictBool = False

    @model_validator(mode='after')
    def explicit_category(self):
        if 'category' in self.model_fields_set and self.category is None:
            raise ValueError('Omit category to inherit the formation category')
        return self


def _read_railml(blob):
    # OpenTrack's exporter is ASCII-safe ISO-8859-1. Standard UTF-8 is also supported.
    need(len(blob) <= MAX_SIZE and b'\0' not in blob and b'<!DOCTYPE' not in blob.upper()
         and b'<!ENTITY' not in blob.upper(), 'Bounded single-byte/UTF-8 XML with no DTD or entity declarations required')
    root = ET.fromstring(blob)
    for node in root.iter():
        if node.tag.startswith(RAILML_22):
            node.tag = node.tag.removeprefix(RAILML_22)
    need(root.tag == 'railml' and root.attrib.get('version') == '2.2', 'Expected RailML 2.2 root and version')
    sections = root.findall('rollingstock')
    need(len(sections) == 1 and sections[0].attrib.get('version', '2.2') == '2.2',
         'Exactly one current rollingstock block required')
    vehicles = sections[0].findall('vehicles/vehicle')
    formations = sections[0].findall('formations/formation')
    need(vehicles and len(vehicles) <= 2000 and len(formations) <= 1000, 'Vehicle/formation input exceeds supported count')
    ids = [node.attrib.get('id', '') for node in vehicles]
    need(all(ids) and len(set(ids)) == len(ids), 'Vehicle IDs must be unique and nonempty')
    return vehicles, formations


def _bounded_int(node, key, lower, upper, default=None):
    if key in node.attrib:
        value = int_text(node.attrib[key])
    else:
        need(default is not None, f'Missing {key}')
        value = default
    return cf.integer(value, lower, upper)


def _number(i):
    return obj([('NSNumber', 0), ('NSValue', 0), ('NSObject', 0)],
               [('*', [w.CString(w.SharedString(b'i'))]), ('i', [i])])


def _name(node):
    value = node.attrib.get('name', '')
    need(value.strip() == value and bool(value), 'Saved vehicle/formation name is empty or whitespace padded')
    return cf.name(value)


def _propulsion(diagram_template, propulsion):
    diagram = copy.deepcopy(diagram_template)
    c.shape(diagram, 'OTDDiagram', 3, DIAGRAM)
    supplies = {'electric': 1, 'diesel': 20}
    power_type = propulsion.attrib.get('powerType', 'electric')
    need(power_type in supplies, 'Only original electric and diesel RailML propulsion powerType supported')
    tables = propulsion.findall('tractiveEffort/valueTable')
    need(len(tables) == 1, 'Each propulsion must have one observed tractive-effort table')
    table = tables[0]
    lines = table.findall('valueLine')
    need(0 < len(lines) <= 100000, 'Each propulsion must have 1..100000 traction points')
    points = []
    for line in lines:
        value, = line.findall('values')
        points.append((float_text(line.attrib['xValue']), float_text(value.attrib['yValue'])))
    parsed, skipped = imported_points(points, table.attrib.get('xValueName', ''), table.attrib.get('yValueName', ''))
    need(parsed[0][0] == 0 and all(speed >= 0 and force >= 0 for speed, force, _ in parsed)
         and all(left[0] < right[0] for left, right in zip(parsed, parsed[1:])),
         'Traction speeds must start at zero and increase after native conversion, with nonnegative forces')
    need(any(force > 0 for _, force, _ in parsed), 'Imported traction diagram has no positive effort')
    set_sequence(diagram, 1, [obj([('OTDPoint', 0), ('NSObject', 0)], [('iii', point)]) for point in parsed])
    set_sequence(diagram, 3, [_number(supplies[power_type])])
    if 'description' in propulsion.attrib:
        cf.settext(diagram, 6, propulsion.attrib['description'])
    return diagram, parsed, skipped


def _engine(vehicle, template, args):
    c.record(template, 'OTEngine')
    target = copy.deepcopy(template)
    mass = _bounded_int(vehicle, 'bruttoWeight', 1, 1000000)
    length = _bounded_int(vehicle, 'length', 1, 100000)
    speed = _bounded_int(vehicle, 'speed', 1, 10000)
    adhesion = _bounded_int(vehicle, 'bruttoAdhesionWeight', 0, mass, default=0)
    propagations = vehicle.findall('engine/propulsion')
    need(0 < len(propagations) <= 64, 'Each Engine needs 1..64 explicit propulsions')
    prototypes = c.array(template.contents[16].value)
    need(prototypes, 'Selected shared engine template has no audited propulsion diagram')
    rotations = {float_text(prop.attrib['rotationMassFactor']) for prop in propagations if 'rotationMassFactor' in prop.attrib}
    need(len(rotations) <= 1 and all(0 < factor <= 10 for factor in rotations), 'Inconsistent or unsupported rotating-mass factor')
    cf.settext(target, 1, _name(vehicle))
    target.contents[2].values[1:3] = [mass, length]
    if rotations:
        target.contents[2].values[3], = rotations
    cf.put(target, 3, adhesion)
    tables = [_propulsion(prototypes[0], prop) for prop in propagations]
    set_sequence(target, 16, [diagram for diagram, _, _ in tables])
    cf.put(target, 6, max(force for _, points, _ in tables for _, force, _ in points))
    cf.put(target, 7, max(x for _, points, _ in tables for x, _, _ in points) if args.recompute_curve_speed_limit else speed)
    need(target.contents[7].value > 0, 'Imported speed limit must be positive')
    validate_graph(target)
    return target, sum(len(rows) for _, rows, _ in tables), sum(count for _, _, count in tables)


def _trailer(vehicle, position, count):
    wagon, = vehicle.findall('wagon')
    model = {
        'kind': 'trailer', 'name': _name(vehicle),
        'length_m': _bounded_int(vehicle, 'length', 1, 100000) * count,
        'mass_t': _bounded_int(vehicle, 'bruttoWeight', 1, 1000000) * count,
        'maximum_speed_kmh': _bounded_int(vehicle, 'speed', 1, 10000),
        'rotating_mass_factor': float_text(wagon.attrib.get('rotationMassFactor', '1.06')),
        'axles': _bounded_int(vehicle, 'numberOfAxles', 1, 1024, default=4),
        'cw': 1.0,
        'number_of_items': count,
        'power_loss_kw': float_text(wagon.attrib.get('auxiliaryPowerConsumption', '0')) * count / 1000.0,
        'delta_load_power_loss_kw_per_t': 0.0,
        'vehicle_marker': 17, 'vehicle_reserved': 0, 'trailer_reserved': 0,
    }
    return make_trailer(model, position)


def _formation(node, template, category, vehicles, depot):
    train = copy.deepcopy(template)
    refs = node.findall('trainOrder/vehicleRef')
    need(0 < len(refs) <= 256, 'Formation requires 1..256 ordered references')
    positions = [_bounded_int(ref, 'orderNumber', 1, len(refs), default=index) for index, ref in enumerate(refs, 1)]
    need(set(positions) == set(range(1, len(refs) + 1)), 'Formation positions must be unique and contiguous')
    engines, trailers = [], []
    for position, ref in sorted(zip(positions, refs)):
        vehicle, powered = vehicles[ref.attrib['vehicleRef']]
        count = _bounded_int(ref, 'vehicleCount', 1, 1024, default=1)
        if powered:
            need(count == 1, 'List repeated powered units in separate explicit positions')
            engines.append(obj([('OTTrainEngine', 0), ('NSObject', 0)],
                               [('@', [string(_name(vehicle))]), ('i', [position])]))
        else:
            trailers.append(_trailer(vehicle, position, count))
    need(engines, 'A native Formation must reference at least one imported Engine')
    cf.settext(train, 0, _name(node))
    cf.settext(train, 3, category)
    train.contents[2].values[1:] = [arr(engines), arr(trailers)]
    summary(train, depot)
    return train


def _assign(records, item, slot, args, kind):
    key = text(item, slot)
    if key in records:
        need(args.on_conflict != 'error', f'Existing native {kind} name: {key}')
        if args.on_conflict == 'keep':
            return False
    records[key] = item
    return True


def import_stock(plan, blob, args):
    vehicles, formations = _read_railml(blob)
    depot = plan.roots[plan.roles['depot']]
    trains = plan.roots[plan.roles['trains']]
    train_array = trains.contents[3].value
    need(not incoming_counts(depot).get(id(depot)) and incoming_counts(trains)[id(train_array)] == 1,
         'Existing vehicle catalog ownership must be exclusive')
    known_engines = {text(item, 1): item for item in c.engine_items(depot)}
    known_trains = {text(item, 0): item for item in c.train_items(trains)}
    engine_template = known_engines[args.engine_template]
    formation_template = known_trains[args.formation_template]
    categories = {text(c.shape(item, 'OTTrainCategory', 19, CATEGORY_LAYOUT), 1) for item in c.array(trains.contents[1].value)}
    category = args.category if args.category is not None else text(formation_template, 3)
    need(category in categories, 'Imported Formation Category must exist')
    powered = {vehicle.attrib['id']: (vehicle, vehicle.find('engine') is not None) for vehicle in vehicles}
    engine_names = [_name(node) for node, is_engine in powered.values() if is_engine]
    formation_names = [_name(node) for node in formations]
    need(len(engine_names) == len(set(engine_names)) and len(formation_names) == len(set(formation_names)),
         'Duplicate imported native Engine or Formation names')
    engine_count = formation_count = points = skipped = 0
    for vehicle, is_engine in powered.values():
        if not is_engine:
            continue
        item, added, duplicates = _engine(vehicle, engine_template, args)
        points += added
        skipped += duplicates
        need(points <= 100000, 'Total imported traction table exceeds 100000 points')
        engine_count += int(_assign(known_engines, item, 1, args, 'Engine'))
    created = []
    for formation in formations:
        item = _formation(formation, formation_template, category, powered, known_engines)
        if _assign(known_trains, item, 0, args, 'Formation'):
            formation_count += 1
            created.append(text(item, 0))
    w.set_elements(depot, list(known_engines.values()))
    w.set_elements(train_array, list(known_trains.values()))
    c.engine_items(depot)
    c.train_items(trains)
    need(all(set(c.bound_engine_names(train)) <= known_engines.keys() for train in known_trains.values()),
         'One or more Train formations reference a missing native Engine')
    return {'format': 'railml_2_2', 'engines_written': engine_count, 'formations_written': formation_count,
            'traction_points_read': points, 'native_adjacent_speed_duplicates_skipped': skipped,
            'formation_summaries': [summary(known_trains[name], known_engines) for name in created[:20]],
            'vehicle_model_policy': 'Explicit verified-layout templates preserve unrepresented native physical fields',
            'unrepresented_physical_calibration_verified': False,
            'representability': 'Native losses include supply genericization, force truncation, and inherited braking/resistance'}


class RollingStockRailMLImporter(OperatingPlanEditTools):
    def import_rolling_stock(self, args):
        state = self.load_operating_project(args)
        source = self.path(args.exchange.path)
        raw = self.secure_bytes(source)
        if len(raw) > MAX_SIZE or not raw or sha(raw) != args.exchange.sha256:
            raise APIError('ROLLING_STOCK_EXCHANGE_SOURCE', 'RailML payload must match SHA and contain up to 20 MB')
        try:
            changed, report = operating_candidate(state, args.source_project.run_file,
                                                   lambda plan: import_stock(plan, raw, args))
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, ET.ParseError) as exc:
            raise APIError('ROLLING_STOCK_EXCHANGE_INVALID', str(exc)[:700]) from exc
        state['inputs'][source] = raw
        report['exchange_source'] = args.exchange.model_dump()
        return self.publish_operating_increment(args, state, changed, report)


def tool_definitions(root):
    service = RollingStockRailMLImporter(root)
    return [('opentrack_import_current_rolling_stock_railml',
             'Import RailML 2.2 Engines, propulsion tables and ordered formations into native Depot/Train catalogs. '
             'Exact current project and input hashes, explicit physical donor templates, bounded electric/diesel and stock collision policy. '
             'Can publish a fresh catalog increment after structural and reference readback.',
             ImportRollingStockRailML, service.import_rolling_stock, False, False)]

