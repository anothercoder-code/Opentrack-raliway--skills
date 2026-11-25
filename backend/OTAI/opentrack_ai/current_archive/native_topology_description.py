"""Original Windows OpenTrack topology description data from saved archives."""

from collections import Counter
from functools import cache
from math import isfinite

from . import catalogs, course_factories, path_functions, route_factory, writer
from .multi_document.core import ident
from .operating_plan_edit import text


SECTION_NAMES = {'itineraries': 'Itineraries', 'paths': 'Paths', 'routes': 'Routes'}
SUFFIXES = {'itineraries': 'I', 'paths': 'P', 'routes': 'R'}
MODEL_NAMES = {
    'OTElement': 'Element', 'OTEndModel': 'Vertex', 'OTConnModel': 'Connector',
    'OTSignalModel': 'Signal', 'OTEdgeModel': 'Edge', 'OTStationModel': 'Station',
    'OTLabelModel': 'Text', 'OTPlotModel': 'Plot', 'OTRectModel': 'Rectangle',
    'OTCircleModel': 'Circle', 'OTLineModel': 'Line', 'OTLogoModel': 'Picture',
    'OTMeasuringModel': 'Instrument', 'OTPowerSupplyModel': 'PowerSupply',
}
TUNNEL_NAMES = {1: '0', 2: 'SS', 3: 'DS', 4: 'SR', 5: 'DR'}
SIGNAL_NAMES = {
    1: 'M', 2: 'MD', 3: 'D', 4: 'SH', 6: 'HH', 7: 'B', 8: 'H100',
    9: 'H200', 10: 'H300', 11: 'H400', 16: 'H500', 17: 'H600', 18: 'H700',
    19: 'H800', 20: 'HT', 21: 'HC', 28: 'H10', 29: 'H20', 30: 'H30',
    31: 'H40', 32: 'H50', 33: 'H60', 34: 'H70', 35: 'H80', 36: 'H90',
    37: 'H900', 38: 'H1000', 51: 'H150', 52: 'H250',
}


def single_line(value):
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('Original topology description requires single-line archive captions')
    return value


def header(title, filename):
    return ['//', f'// File: {single_line(filename)}', '//', '// Produced by OpenTrack Skill',
            f'// {single_line(title)}', '// Type    : OT_Text', '// Desc.   : OT_topo_text',
            '// x-Legend: none', '// y-Legend: none', '//']


def encoded(lines):
    return ('\n'.join(lines) + '\n').encode('utf-8')


def worksheet(root, name, filename):
    objects, ids = route_factory.document(root)
    lines = header(f'Topology of Document : {name}', filename)
    kinds = Counter()
    unknown = Counter()
    for obj in objects:
        model_id = obj.contents[0].value
        kind = writer.kind(obj)
        label = MODEL_NAMES.get(kind)
        if label is None:
            unknown[kind] += 1
            label = f'Unknown Object   {kind}'
        kinds[label] += 1
        record = [f'ID = {model_id}', f'Typ = {label}']
        if kind == 'OTElement':
            record.extend(f'End {i} ID = {end.contents[0].value}'
                          for i, end in enumerate(path_functions.mutable_array(obj.contents[7].value)))
        elif kind == 'OTEdgeModel':
            record.extend(f'End {i} ID = {obj.contents[slot].value.contents[0].value}'
                          for i, slot in enumerate((7, 8)))
        elif kind in ('OTEndModel', 'OTConnModel'):
            neighbour = obj.contents[8].value
            record.append(f'Neighbour End ID = {neighbour if neighbour in ids else 0}')
            if kind == 'OTConnModel':
                record.extend((f'Connector Document Name = {single_line(text(obj, 25))}',
                               f'Connector End ID = {obj.contents[26].value}'))
        lines.append('\t'.join(record))
    return encoded(lines), {'object_count': len(objects), 'model_counts': dict(kinds),
                            'unclassified_model_classes': dict(unknown)}


def station_sign(end):
    station = end.contents[12].value
    return text(station, 7) if station is not None else ''


def end_caption(project, key):
    end = project.model(key)
    prefix = station_sign(end)
    label = text(end, 18) or text(project.model(project.related(key)), 18)
    signal = end.contents[11].value
    signal_name = text(signal, 13) if signal is not None else ''
    return single_line('_'.join(filter(None, (prefix, label, signal_name))) or f'[{key[1]}]')


def route_settings(route):
    distance, _, release, reserve = route.contents[5].values[:4]
    previous = 'YES' if writer.kind(route) == 'OTRoute' and route.contents[11].value else 'NO'
    return (f' / Res. Time = {reserve} s / Rel. Time = {release} s / Dist. to Rel. Point = {distance} m'
            f' / Res. with prev. Route = {previous}')


def track_profile(project, nodes, speed_count, stations):
    columns = ['Len.', 'Pos.', 'Grad.', 'Rad.', 'Tunnel',
               *(f'v_{i + 1}' for i in range(speed_count)), 'Sig.', 'Station', 'Sign']
    yield '\t'.join(columns)
    position = 0
    for start, end in zip(nodes, nodes[1:]):
        edge = project.model(project.edge_between(start, end))
        departure = project.model(project.actual_related(start))
        forward = edge.contents[7].value is departure
        direction = 1 if forward else -1
        tunnel, length, radius, gradient, _, _ = edge.contents[9].values
        if not all(map(isfinite, (radius, gradient))):
            raise ValueError('Original topology description needs finite radius and gradient')
        values = [f'{length / 1000:.3f}', f'{position / 1000:.3f}', f'{direction * gradient:.2f}',
                  f'{direction * radius:.0f}', TUNNEL_NAMES.get(tunnel, '*')]
        speeds = course_factories.dictionary(edge.contents[16].value)
        speed_size = len(speeds)
        for index in range(speed_count):
            if index == speed_size:
                values.append('200')
                speed_size += 1
                continue
            speed = speeds.get(str(index))
            if speed is not None:
                catalogs.shape(speed, 'OTSpeed', 0, ['@', 'i', 'i', 'i'])
            values.append(str(0 if speed is None else speed.contents[1 if forward else 2].value))
        model = project.model(start)
        signal = model.contents[11].value
        signal_label = ''
        if signal is not None:
            signal_label = SIGNAL_NAMES.get(signal.contents[8].values[0], '')
            addition = text(model, 18)
            if addition:
                signal_label += f' {single_line(addition)}'
        values.append(signal_label)
        sign = station_sign(model) if model.contents[20].value == 2 else ''
        if sign:
            values.extend((single_line(stations.get(sign) or sign), single_line(sign)))
        yield '\t'.join(values)
        position += length
    yield f'0.000\t{position / 1000:.3f}'


def movements(project, sections, filename, *, detailed_routes, profile_speed_count=None, stations=None):
    sections = [part for part in SECTION_NAMES if part in sections]
    title = '/'.join(SECTION_NAMES[part] for part in sections)
    lines = header(f'Descriptions of all {title}', filename)
    counts = {}

    @cache
    def length(nodes):
        return sum(project.model(project.edge_between(a, b)).contents[9].values[1] for a, b in zip(nodes, nodes[1:]))

    def resolve(kind, document, ref):
        name, array_id, start_id = (ref[field] for field in ('name', 'array_id', 'start_id'))
        if kind == 'OTPath':
            return project.itinerary_path((document, start_id), (name, array_id, start_id))
        return project.owned((document, start_id), kind, (name, array_id, start_id))

    def route_line(route, nodes, indent):
        extension = route_settings(route) if detailed_routes else ''
        return (f'{indent}{single_line(ident(route)[0])} \t'
                f'(Length = {length(tuple(nodes))} m{extension})')

    def path_routes(path):
        nodes, refs = project.path_view(path)
        if refs and refs[0][1].get('kind') == 'shunting':
            body, = path_functions.mutable_array(path.contents[0].value)
            return [(body, nodes)]
        routes = [resolve('OTRoute', dn, info) for dn, info in refs]
        return [(route, project.route_view(route)) for route in routes]

    def name(obj):
        return single_line(text(obj, 1))

    for part in sections:
        lines.extend((SECTION_NAMES[part], ''))
        if part == 'itineraries':
            counts[part] = len(project.dests)
            for itinerary in sorted(project.dests, key=name):
                nodes, path_refs = project.dest_view(itinerary)
                paths = [resolve('OTPath', dn, info) for dn, info in path_refs]
                entries = [(path, path_routes(path)) for path in paths]
                routes = sum(len(items) for _, items in entries)
                lines.append(f'{name(itinerary)} \t\t\t(Contains {len(paths)} Paths / {routes} Routes / '
                             f'Total Length = {length(tuple(nodes))} m)')
                for path, items in entries:
                    lines.append(f'\t{name(path)} \t\t(Length = {length(tuple(project.path_view(path)[0]))} m)')
                    lines.extend(route_line(route, nodes, '\t\t') for route, nodes in items)
                lines.append('')
                if profile_speed_count is not None:
                    lines.extend(track_profile(project, nodes, profile_speed_count, stations or {}))
                    lines.append('')
        elif part == 'paths':
            counts[part] = len(project.paths_objects)
            for path in sorted(project.paths_objects, key=name):
                nodes, references = project.path_view(path)
                lines.append(f'{name(path)} \t(Contains {len(references)} Routes / Total Length = {length(tuple(nodes))} m)')
                lines.extend(route_line(route, nodes, '\t') for route, nodes in path_routes(path))
                lines.append('')
        else:
            primary = [route for route in project.routes
                       if writer.kind(project.model(project.owners[id(route)])) != 'OTConnModel']
            counts[part] = len(primary)
            for route in sorted(primary, key=name):
                nodes = project.route_view(route)
                extension = route_settings(route) if detailed_routes else ''
                lines.append(f'{name(route)} \t(Contains {len(nodes)} Vertices / '
                             f'Total Length = {length(tuple(nodes))} m{extension})')
                lines.extend(f'\t{end_caption(project, key)} \t(ID = {key[1]})' for key in nodes)
                lines.append('')
        lines.append('')
    return encoded(lines), {'sections': sections, 'record_counts': counts, 'detailed_routes': detailed_routes,
                            'profile_speed_count': profile_speed_count}
