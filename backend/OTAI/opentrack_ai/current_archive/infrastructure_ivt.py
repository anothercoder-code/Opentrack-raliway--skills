"""OpenTrack IVT tabular line import against the current native worksheet schema."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
import math
import re

from . import catalogs, writer
from .course_factories import dictionary
from .multi_document.generate import placement, signal_placement
from .signal_type_workflow.core import COMBINED, ROLES, TYPES, preview as create_signal
from .station_exchange import read_catalog
from .zero_generation import native_signal_routes as native, topology
from .zero_operations import station_binding
from .zero_terminal import terminal_areas


NUMBER = re.compile(r'[+-]?(?:[0-9]{1,9}(?:[.,][0-9]{0,9})?|[.,][0-9]{1,9})')
TUNNELS = {'': 1, 'no tunnel': 1, 'tunnel single smooth': 2, 'tunnel double smooth': 3,
           'tunnel single rough': 4, 'tunnel double rough': 5}
SIGNAL_TYPES = {'main': 'main', 'main distant': 'main_distant', 'distant': 'distant', 'shunt': 'shunting',
                'shunting': 'shunting', 'main 2 asp': 'main_two_aspect', 'main distant 3 asp': 'main_distant_three_aspect',
                'main distant 2 asp': 'main_two_aspect', 'main distant 4 asp': 'main_distant_four_aspect',
                'distant 2 asp': 'distant_two_aspect'}
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_SIGNALS = 100
NATIVE_BENTLEY_IVT_HEADER = (
    b'// Position [m] \tVertex Name Up \tVertex Name Down \tVertex km Up [km] \tVertex km Down [km] '
    b'\tSpeed Up 1 [km/h] \tSpeed Up 2 [km/h] \tSpeed Up 3 [km/h] \tSpeed Up 4 [km/h] '
    b'\tSpeed Down 1 [km/h] \tSpeed Down 2 [km/h] \tSpeed Down 3 [km/h] \tSpeed Down 4 [km/h] '
    b'\tGradient [\x89] \tRadius [m] \tTunnel Type \tSignal Up \tSignal Down \tStation Name \n'
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def decimal_value(value, label):
    value = value.strip()
    require(NUMBER.fullmatch(value) is not None, f'{label} requires a bounded decimal number')
    return Decimal(value.replace(',', '.'))


def speed(value):
    if not value.strip():
        return None
    amount = decimal_value(value, 'speed')
    require(amount == int(amount) and 0 <= amount <= 1000, 'speed requires an integer in 0–1000 km/h')
    return int(amount)


def optional_number(value, label, default):
    return decimal_value(value, label) if value.strip() else default


def tunnel(value):
    label = ' '.join(value.lower().replace(',', ' ').split())
    if label in TUNNELS:
        return TUNNELS[label]
    factor = decimal_value(value, 'tunnel factor or named native profile')
    require(Decimal('0.5') <= factor <= 50 and (factor * 10) == int(factor * 10) and
            (factor <= 6 or factor == int(factor)), 'tunnel factor must be an exact native tenth 0.5–6.0 or whole 7–50')
    return 10000 + int(factor * 10)


def signal(value):
    if not value.strip():
        return None
    words = re.findall(r'[a-z0-9]+', value.lower())
    roles = [word for word in words if word in ROLES]
    key = ' '.join('asp' if word in ('aspect', 'aspects') else word for word in words
                   if word not in ROLES and word not in ('signal', 'signals'))
    require(len(roles) <= 1 and key in SIGNAL_TYPES, f'Unsupported IVT signal label {value!r}')
    signal_type = SIGNAL_TYPES[key]
    main = signal_type.startswith('main')
    require(main or not roles, 'Only main IVT signal tags have an explicit home, block or exit role')
    return signal_type, (roles[0] if roles else 'block') if main else 'exit'


@dataclass(frozen=True)
class Row:
    line: int
    position: Decimal
    names: tuple
    km: tuple
    forward: tuple
    reverse: tuple
    grade: float
    radius: float
    tunnel: int
    signals: tuple
    station: str


def parse_ivt(blob):
    require(0 < len(blob) <= MAX_SOURCE_BYTES, 'Expected bounded nonempty IVT text')
    header, separator, body = blob.partition(b'\n')
    if separator and header.removesuffix(b'\r') == NATIVE_BENTLEY_IVT_HEADER[:-1]:
        # The stock Bentley converter emits the Windows per-mille byte in this exact comment.
        blob = header.replace(b'\x89', b'per mille') + separator + body
    try:
        source = blob.decode('ascii')
    except UnicodeError as exc:
        raise ValueError('IVT uses ASCII tab-separated text') from exc
    rows = []
    for index, line in enumerate(source.split('\n'), 1):
        line = line.removesuffix('\r')
        require(len(line) <= 1022 and all(char == '\t' or ' ' <= char <= '~' for char in line),
                f'IVT line {index} exceeds the native row or printable ASCII range')
        if not line.strip() or line.lstrip().startswith('//'):
            continue
        try:
            fields = line.split('\t')
            require(15 <= len(fields) <= 19, 'expected 19 tab fields, with optional trailing facility fields')
            fields += [''] * (19 - len(fields))
            rows.append(Row(index, decimal_value(fields[0], 'position'), tuple(fields[1:3]),
                            tuple(optional_number(value, 'kilometre post', None) for value in fields[3:5]),
                            tuple(speed(value) for value in fields[5:9]), tuple(speed(value) for value in fields[9:13]),
                            float(optional_number(fields[13], 'gradient', 0)), float(optional_number(fields[14], 'radius', 0)),
                            tunnel(fields[15]), tuple(signal(value) for value in fields[16:18]), fields[18]))
        except ValueError as exc:
            raise ValueError(f'IVT line {index}: {exc}') from exc
        require(len(rows) <= 1000, 'IVT continuous import supports at most 1000 rows')
    require(len(rows) >= 2, 'IVT continuous line requires at least two distinct positions')
    require(sum(profile is not None for row in rows for profile in row.signals) <= MAX_SIGNALS,
            f'IVT worksheet supports up to {MAX_SIGNALS} explicit signal placements')
    return rows


def prepare_spec(rows, header, *, drawing_coordinates=None):
    root, _ = writer.load_next_compatible(header)
    topology.doc_layout(root)
    left, top, width, height = map(float, root.contents[9].values)
    require(all(math.isfinite(value) for value in (left, top, width, height)) and width > 40 and height > 30,
            'Current ordinary worksheet view must have room for the IVT line')
    if drawing_coordinates is None:
        step = min(130.0, (width - 40) / (len(rows) - 1))
        drawing_coordinates = [(left + 20 + step * i, top + height * 0.5) for i in range(len(rows))]
    else:
        require(len(drawing_coordinates) == len(rows)
                and all(left <= x < left + width and top <= y < top + height for x, y in drawing_coordinates),
                'Drawing coordinates fall outside the native worksheet view')
    vertices = [dict(key=str(i), x=x, y=y, orientation='horizontal',
                     names=list(row.names), insulated_joint=[False, False], axle_counter=[False, False])
                for i, (row, (x, y)) in enumerate(zip(rows, drawing_coordinates, strict=True))]
    edges, profile = [], []
    for i, (start, stop) in enumerate(zip(rows, rows[1:])):
        length = stop.position - start.position
        require(0 < length <= 2147483647 and length == int(length),
                f'IVT lines {start.line} and {stop.line} require increasing positions with a whole-metre native length')
        require(None not in (*start.forward, *stop.reverse),
                f'IVT lines {start.line} and {stop.line} require all four speeds in each outgoing direction')
        speeds = list(zip(start.forward, stop.reverse))
        specs = [dict(train_type=str(k), speed12_kmh=max(1, u), speed21_kmh=max(1, d))
                 for k, (u, d) in enumerate(speeds)]
        edges.append(dict(key=str(i), **{'from': [str(i), 1], 'to': [str(i+1), 0]}, length_m=int(length),
                          radius_m=start.radius, gradient_per_mille=start.grade, track_type=1, loop_type=1, dlink_type=1,
                          equal_speed=False, rack_rail=False, speeds=specs, remark='', track_name='', line_name=''))
        profile.append((speeds, start.tunnel))
    return {'vertices': vertices, 'edges': edges}, profile


def fields(root, rows, report, spec, profile, *, write):
    models, records = native.validate_topology(root)
    for i, row in enumerate(rows):
        for side, ident in enumerate(report['vertex_end_ids'][str(i)]):
            end = records[ident]
            stored = topology.flt(float(row.km[side]) if row.km[side] is not None else -99999.0, 'IVT kilometre post')
            require(row.km[side] is None or float(stored) != -99999.0, 'IVT kilometre post conflicts with the native unset value')
            if write:
                end.contents[14].value = stored
            require(end.contents[14].value == stored and writer.string(end.contents[18].value) == row.names[side],
                    'Native directional vertex name or kilometre figure differs from IVT')
    for i, (speeds, tunnel_code) in enumerate(profile):
        edge = records[report['edge_ids'][str(i)]]
        band = spec['edges'][i]
        expected = [tunnel_code, band['length_m'], topology.flt(band['radius_m'], 'IVT radius'),
                    topology.flt(band['gradient_per_mille'], 'IVT gradient'), 1, 1]
        saved = dictionary(edge.contents[16].value)
        require(set(saved) == {'0', '1', '2', '3'}, 'Native IVT speed table does not have four positional categories')
        if write:
            edge.contents[9].values[0] = tunnel_code
            for j, (up, down) in enumerate(speeds):
                saved[str(j)].contents[1].value = up
                saved[str(j)].contents[2].value = down
        require(edge.contents[9].values == expected and edge.contents[11].value == 0 and
                all(tuple(saved[str(j)].contents[k].value for k in (1, 2)) == limits for j, limits in enumerate(speeds)),
                'Native IVT directional speeds or Edge properties differ after readback')
    return models, records


def signal_graph(document, rows, geometry, sight):
    identities = []
    next_id = geometry['allocation_highwater'] + 1
    for index, row in enumerate(rows):
        for side, profile in enumerate(row.signals):
            if profile is None:
                continue
            signal_type, role = profile
            ident = geometry['vertex_end_ids'][str(index)][side]
            _, _, _, records = native.document(document)
            end = records[ident]
            name = f'IVT_{index+1}_{"A" if side == 0 else "D"}'
            document, _ = create_signal(document, {'action': 'create', 'signal_type': signal_type,
                'main_role': role, 'warning_speed_kmh': 0 if TYPES[signal_type] in COMBINED else None,
                'creation': {'end_id': ident, 'name': name, 'model_id': next_id,
                             'placement': signal_placement(end, float(end.contents[2].value), float(end.contents[3].value)),
                             'sight_m': sight, 'delay_s': 0, 'show_symbol': True, 'show_icon': True}})
            identities.append({'position_m': str(row.position), 'end_id': ident, 'signal_id': next_id,
                               'direction': 'ascending' if side == 0 else 'descending', 'name': name,
                               'type': signal_type, 'role': role, 'sight_m': sight})
            next_id += 1
    return document, identities


def station_graph(document, rows, geometry, native_catalog, area_bindings, *, station_match='name_or_sign'):
    markers = [(index, row) for index, row in enumerate(rows) if row.station]
    require(not markers or native_catalog is not None, 'Explicit original station catalog required to bind IVT station marks')
    if native_catalog is None:
        require(not area_bindings, 'IVT platform bindings require named station markers and a native catalog')
        return document, []
    _, _, _, stations = read_catalog(native_catalog)
    names = {sign: row['name'] for sign, row in stations.items()}
    aliases = defaultdict(set)
    for sign, name in names.items():
        if station_match != 'sign':
            aliases[name].add(sign)
        if station_match != 'name':
            aliases[sign].add(sign)
    used = {}
    _, _, _, byid = native.document(document)

    def end_id(index, side):
        return geometry['vertex_end_ids'][str(index)][side]

    for index, row in markers:
        matches = aliases[row.station]
        require(len(matches) == 1, f'IVT line {row.line}: station {row.station!r} is unknown or ambiguous in the catalog')
        sign, = matches
        used.setdefault(sign, []).append(index)
    areas = {binding.station_sign: binding for binding in area_bindings}
    require(len(areas) == len(area_bindings) and areas.keys() <= used.keys(), 'IVT platform bindings must address distinct marked stations')
    specs, result = [], []
    for sign, indices in used.items():
        reference = end_id(indices[0], 0)
        vertex = byid[reference]
        spec = {'sign': sign, 'name': names[sign], 'placement': placement(float(vertex.contents[2].value),
                float(vertex.contents[3].value)), 'station_type_raw': 2, 'interlock_type_raw': 4,
                'icon_show_type_raw': 1, 'timing_point': True}
        report = {'sign': sign, 'name': names[sign], 'position_m': [str(rows[index].position) for index in indices],
                  'reference_end_ids': [end_id(index, 0) for index in indices]}
        if areas:
            require(len(indices) == 1, 'Explicit IVT stopping areas require one reference pair per marked station')
            spec.update(reference_end_id=reference, ordinary_end_ids=[], stop=None)
            if sign in areas:
                area = areas[sign]
                side = 0 if area.direction == 'ascending' else 1
                index = indices[0]
                entry_index = index - 1 if side == 0 else index + 1
                require(0 <= entry_index < len(rows) and rows[entry_index].position ==
                        decimal_value(area.entry_position_m, 'platform entry position'),
                        f'IVT platform {sign!r} must select the adjacent physical Edge')
                entry, reference = end_id(entry_index, side), end_id(index, side)
                area_edge = geometry['edge_ids'][str(min(entry_index, index))]
                exit_signal = byid[reference].contents[11].value
                require(exit_signal is not None, f'IVT platform {sign!r} requires an explicit directional exit signal')
                length = int(abs(rows[index].position - rows[entry_index].position))
                spec.update(reference_end_id=reference, ordinary_end_ids=[entry], stop={
                    'entry_end_id': entry, 'exit_end_id': reference, 'area_edge_id': area_edge, 'length_m': length,
                    'exit_signal_name': catalogs.text(exit_signal.contents[13].value), 'direction': 'forward_only'})
                report.update(reference_end_ids=[reference], platform_edge_id=area_edge, entry_end_id=entry, length_m=length)
        else:
            spec['end_ids'] = report['reference_end_ids']
        specs.append(spec)
        result.append(report)
    if specs:
        document = (terminal_areas.bind_areas(document, specs) if areas else station_binding.bind_stations(document, specs))[0]
    return document, result


def import_ivt(blob, header, shapes, station_catalog, areas, sight):
    return materialize_line(parse_ivt(blob), header, shapes, station_catalog, areas, sight)


def materialize_line(rows, header, shapes, station_catalog, areas, sight, *, station_match='name_or_sign',
                     drawing_coordinates=None):
    spec, profile = prepare_spec(rows, header, drawing_coordinates=drawing_coordinates)
    document, geometry = topology.generate_network(header, shapes, spec)
    root, version = writer.load_next_compatible(document)
    fields(root, rows, geometry, spec, profile, write=True)
    document = writer.dump_verified(root, version)
    document, signals = signal_graph(document, rows, geometry, sight)
    document, stations = station_graph(document, rows, geometry, station_catalog, areas,
                                      station_match=station_match)
    saved, _ = writer.load_next_compatible(document)
    _, byid = fields(saved, rows, geometry, spec, profile, write=False)
    for signal_row in signals:
        model = byid[signal_row['signal_id']]
        require(model.contents[7].value is byid[signal_row['end_id']] and
                model.contents[8].values[:2] == [TYPES[signal_row['type']], ROLES[signal_row['role']]],
                'Saved IVT signal direction or type differs')
    markers = []
    for index, row in enumerate(rows):
        ascending, descending = geometry['vertex_end_ids'][str(index)]
        markers.append({'position_m': str(row.position), 'source_line': row.line, 'ascending_end_id': ascending,
                        'descending_end_id': descending})
    segments = [{'edge_id': geometry['edge_ids'][str(i)], 'start_m': str(rows[i].position),
                 'end_m': str(rows[i+1].position), 'length_m': edge['length_m'], 'tunnel_type_raw': profile[i][1],
                 'radius_m': edge['radius_m'], 'gradient_per_mille': edge['gradient_per_mille'],
                 'directional_limits_kmh': profile[i][0]} for i, edge in enumerate(spec['edges'])]
    return document, {'native_readback_verified': True, 'vertices': markers, 'edges': segments, 'signals': signals,
                      'stations': stations, 'total_length_m': sum(item['length_m'] for item in segments),
                      'unapplied_terminal_values': {'first_row_descending': rows[0].reverse,
                          'last_row_ascending': rows[-1].forward, 'last_row_gradient': rows[-1].grade,
                          'last_row_radius': rows[-1].radius, 'last_row_tunnel_type_raw': rows[-1].tunnel}}
