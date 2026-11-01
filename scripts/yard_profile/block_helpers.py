"""Source-bound type25 block profile and exact native traversal helpers."""
from opentrack_ai.current_archive import writer as w, catalogs as c, route_factory as rf
from opentrack_ai.current_archive.signal_type_workflow import core as signal_types

def need(ok, message):
    if not ok:
        raise ValueError(message)

def _golden_block(header):
    root, _ = w.load_next_compatible(header)
    rows = []
    for signal in w.objects(root):
        if w.kind(signal) != 'OTSignalModel':
            continue
        rf.layout(signal, 'OTSignalModel', 11, rf.SIGNAL, graphic=True)
        if signal.contents[8].values != [25, 3, 2] or signal.contents[11].value != 0:
            continue
        need(signal.contents[9].values == [2, 400, 640, 0] and signal.contents[12].value == 7,
             'Type25/block golden scalar profile differs; do not infer unknown parameters')
        rows.append({'source_signal_id': signal.contents[0].value,
                     'type_role_location': [25, 3, 2], 'show_sight_flags_release': [2, 400, 640, 0],
                     'warning_speed_kmh': 0, 'dispatch_raw': 7,
                     'delay_s': float(signal.contents[16].value)})
    need(rows and all(row['delay_s'] == 0 for row in rows), 'An actual current type25/block golden is required')
    need(signal_types.TYPES['main_distant_three_aspect'] == 25 and signal_types.ROLES['block'] == 3,
         'Audited type/role catalog changed')
    return rows

def _trace(project, dest):
    nodes, paths = project.dest_view(dest)
    distance = 0
    visits, mains, edges = [], [], []
    for i, end_key in enumerate(nodes):
        if i:
            edge_key = project.edge_between(nodes[i - 1], end_key)
            edge = project.model(edge_key)
            distance += edge.contents[9].values[1]
            edges.append({'document': edge_key[0], 'id': edge_key[1],
                          'length_m': edge.contents[9].values[1], 'track': c.text(edge.contents[19].value)})
        end = project.model(end_key)
        signal = end.contents[11].value
        if signal is not None and signal.contents[8].values[0] in signal_types.MAIN:
            mains.append({'document': end_key[0], 'end_id': end_key[1],
                          'signal_id': signal.contents[0].value, 'name': c.text(signal.contents[13].value),
                          'type': signal.contents[8].values[0], 'role': signal.contents[8].values[1],
                          'distance_m': distance})
        if end.contents[20].value == 2:
            station = end.contents[12].value
            need(station is not None, 'Station reference is unbound')
            if i:
                previous = project.model(nodes[i - 1])
                edge = project.model(project.edge_between(nodes[i - 1], end_key))
                need(previous.contents[20].value == 1 and previous.contents[12].value is station and
                     edge.contents[9].values[1] == 500, 'Actual500m same-station arrival area required')
            visits.append({'station_sign': c.text(station.contents[7].value), 'end_key': list(end_key),
                           'distance_m': distance})
    return {'nodes': [list(value) for value in nodes], 'paths': paths, 'visits': visits,
            'mains': mains, 'edges': edges, 'distance_m': distance}
