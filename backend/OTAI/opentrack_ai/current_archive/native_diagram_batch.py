"""Prepare native live Corridor inputs and inspect original scripted graph outputs."""

import math
import re

from . import catalogs, runfile_parameters, writer as w
from .native_corridors import array, compare, dictionary, items, mapping, shape
from .native_evaluation_formats import require, series as result_series
from .native_planned_corridor import SHOW_ACTUAL, SHOW_PLANNED, corridor_shape, corridor_stations
from .prepare_contract import auxiliary, preflight
from .project_workflow.relocation import relocate_project
from .zero_generation import native_signal_routes as ns


OPEN_TRACK_SOURCE = 0x80
ONLINE_PLOTTING = 0x20
NAME_PATTERN = r'[A-Za-z0-9][A-Za-z0-9_-]{0,59}'


def drawing_name(value):
    require(isinstance(value, str) and re.fullmatch(NAME_PATTERN, value), 'Use a short native drawing basename')
    return value


def read_layout(root, station_catalog):
    controller, topology = corridor_shape(root)
    require(mapping(topology.contents[1].value), 'Drawing must contain a populated native Corridor position lookup')
    return controller, topology, corridor_stations(root, station_catalog)


def live_drawing(raw, path, name, stations, time_window_s):
    root, version = w.load_next_compatible(raw)
    controller, topology, positions = read_layout(root, stations)
    drawing_name(name)
    original_topology = w.fingerprint(topology)
    if root.clazz.version == 11:
        root.clazz = w.Class(b'OTCorridorDocument', 13, root.clazz.superclass)
        root.contents.extend([w.TypedGroup([b'i', b'i'], [0, 0]), w.TypedValue(b'@', array([]))])
    if controller.clazz.version == 1:
        controller.clazz = w.Class(b'OTTCorridorSimController', 2, controller.clazz.superclass)
        controller.contents.append(w.TypedValue(b'@', dictionary({})))
    for group in controller.contents:
        group.value = dictionary({})
    root.contents[2].value = ns.string(path)
    root.contents[3].value = ns.string(name)
    root.contents[5].value = None
    root.contents[6].value = 1
    root.contents[13].value = (root.contents[13].value & ~(SHOW_PLANNED | ONLINE_PLOTTING)) | SHOW_ACTUAL | OPEN_TRACK_SOURCE
    root.contents[16].value = ns.string('Original OpenTrack simulation')
    root.contents[18].value = ns.string(name)
    if time_window_s is not None:
        require(isinstance(time_window_s, list) and len(time_window_s) == 2
                and all(type(v) is int and 0 <= v <= 10_000_000 for v in time_window_s)
                and time_window_s[0] < time_window_s[1], 'Expected an ordered absolute seconds drawing window')
        root.contents[7].values = [float(v) for v in time_window_s]
    require(all(math.isfinite(v) for v in root.contents[7].values) and root.contents[7].values[0] < root.contents[7].values[1],
            'Invalid native display window')
    payload = w.dump_verified(root, version)
    fresh, _ = w.load_next_compatible(payload)
    saved, fresh_topology, fresh_positions = read_layout(fresh, stations)
    require(saved.clazz.version == 2 and fresh.clazz.version == 13 and fresh.contents[6].value == 1
            and fresh.contents[13].value & OPEN_TRACK_SOURCE and w.string(fresh.contents[2].value) == path
            and all(not mapping(row.value) for row in saved.contents)
            and w.fingerprint(fresh_topology) == original_topology and positions == fresh_positions,
            'Prepared definition changed topology or contains prerecorded movement')
    return payload, {'station_positions_m': positions, 'topology_sha256': original_topology,
                     'time_window_s': fresh.contents[7].values}


def prepare(inputs, drawings, *, source_root, target_root, run_file, hashes):
    from .itinerary_edit_tools import EditableItineraryProject

    require(not any(key == 'Train Diagram Document' for key, _, _ in auxiliary.records(inputs[run_file])),
            'Choose a source simulation without existing diagram declarations')
    require(isinstance(drawings, list) and 1 <= len(drawings) <= 24, 'Choose one to 24 bounded native drawings')
    names = [drawing_name(item['name']) for item in drawings]
    require(len(set(value.casefold() for value in names)) == len(names), 'Native diagram basenames must be distinct')
    moved, relocation = relocate_project(inputs, source_root=source_root, target_root=target_root, run_file=run_file,
                                         expected_hashes=hashes, discard_unrelated_destinations=True,
                                         project_type=EditableItineraryProject)
    roles = relocation['catalog_paths']
    stations = catalogs.station_items(w.load_next_compatible(moved[roles['stations']])[0])
    courses = catalogs.course_items(w.load_next_compatible(moved[roles['courses']])[0])
    enabled = {catalogs.text(row.contents[0].value) for row in courses if row.contents[5].value == 1}
    definitions = {}
    declared = []
    for name, item in zip(names, drawings, strict=True):
        course_ids = item['courses']
        require(isinstance(course_ids, list) and 1 <= len(course_ids) <= 10000
                and all(isinstance(cid, str) for cid in course_ids) and len(set(course_ids)) == len(course_ids)
                and set(course_ids) <= enabled, f'Select distinct enabled Course IDs for {name}')
        member = f'OTDocuments/{name}.otsimcor'
        path = target_root + '/' + member
        moved[member], evidence = live_drawing(item['raw'], path, name, stations, item.get('time_window_s'))
        definitions[name] = {'member': member, 'courses': course_ids, **evidence}
        declared.append(f'Train Diagram Document#{path}#'.encode('ascii'))
    run = runfile_parameters.edit_runfile(moved[run_file], {b'Output Train Diagram': b'1'})
    newline = b'\r\n' if run.endswith(b'\r\n') else b'\n'
    moved[run_file] = run + newline.join(declared) + newline
    prefix = target_root + '/'

    def bound_reader(path):
        require(path.startswith(prefix), 'Preflight read outside prepared graph project')
        return moved[path[len(prefix):]]

    checked = preflight.check(moved[run_file], bound_reader)
    require(checked['passed_static_subset'], f'Prepared native graph preflight failed: {checked["errors"]}')
    return moved, {'source_relocation': relocation, 'drawings': definitions, 'preflight': checked}


def verify_frozen_drawing(raw, definition, declared_path):
    root, _ = w.load_next_compatible(raw)
    controller, topology, positions = read_layout(root, definition['station_positions_m'])
    require(w.string(root.contents[2].value) == declared_path and root.contents[6].value == 1
            and root.contents[13].value & OPEN_TRACK_SOURCE and not any(mapping(group.value) for group in controller.contents)
            and positions == definition['station_positions_m'] and w.fingerprint(topology) == definition['topology_sha256'],
            'Frozen original input is not the requested empty live drawing definition')


def output_file(files, name, scenario):
    drawing_name(name)
    pattern = re.compile(re.escape(name) + r'\.(\d{1,10})\.otsimcor$', re.ASCII)
    matches = [item for item in files if (match := pattern.fullmatch(item)) and int(match[1]) == scenario]
    require(len(matches) == 1, f'Expected one native {name}.{scenario}.otsimcor output; got {matches}')
    return matches[0]


def traveled_distance(segment):
    """Express native signed drawing movement as positive distance traveled."""
    total = 0.0
    result = [{'time_s': segment[0]['time_s'], 'distance_m': total}]
    for left, right in zip(segment, segment[1:]):
        total += abs(right['distance_m'] - left['distance_m'])
        result.append({'time_s': right['time_s'], 'distance_m': total})
    return result


def actual_course(course_id, series, length, st1_text=None):
    shape(series, 'OTSimEventArray', ['@', '@'])
    points = items(series.contents[0].value)
    require(len(points) > 1, f'Native drawing has no movement trace for {course_id}')
    first_time = None
    previous_time = -1
    minimum = math.inf
    maximum = -math.inf
    segments = []
    for point in points:
        if w.kind(point) == 'OTCorridorBasicSimEvent':
            shape(point, 'OTCorridorBasicSimEvent', ['f', 'f'])
            starts = 0
        else:
            shape(point, 'OTCorridorSimEvent', ['f', 'f', 'i'])
            starts = point.contents[2].value
        require(point.clazz.version == 0, 'Unexpected original position point version')
        time, distance = (point.contents[i].value for i in (0, 1))
        require(math.isfinite(time) and math.isfinite(distance) and time >= max(0, previous_time)
                and -0.01 <= distance <= length + 0.01 and starts in (0, 1),
                f'Invalid original diagram point for {course_id}')
        if first_time is None:
            first_time = time
        previous_time = time
        minimum, maximum = min(minimum, distance), max(maximum, distance)
        if starts or not segments:
            segments.append([])
        segments[-1].append({'time_s': time, 'distance_m': distance})
    require(previous_time > first_time and maximum > minimum,
            f'Original {course_id} diagram points do not show elapsed movement')
    result = {'course_id': course_id, 'point_count': len(points), 'segment_count': len(segments),
              'first_time_s': first_time, 'last_time_s': previous_time, 'min_m': minimum, 'max_m': maximum}
    if st1_text is not None:
        st1 = result_series(st1_text, 'st1', course_id)
        factor = 1000.0 if st1['units'][1] == 'km' else 1609.344
        native = [(time, distance * factor) for time, distance in st1['points']]
        require(len(native) >= 2, 'Independent native .st1 trace is empty')
        residuals = [compare(traveled_distance(segment), native) for segment in segments if len(segment) >= 2]
        result['st1_max_delta_residual_m'] = max(residuals) if residuals else None
    return result


def station_events(array, positions):
    records = []
    for event in items(array):
        shape(event, 'OTCorridorStationSimEvent', ['f', 'f', 'i', 'i', 'i', '@', '@'])
        require(event.clazz.version == 0, 'Unexpected original Station point version')
        station = w.string(event.contents[5].value)
        clock, distance = (event.contents[i].value for i in (0, 1))
        require(math.isfinite(clock) and clock >= 0 and station in positions and abs(distance - positions[station]) <= .01,
                'Original Station event disagrees with its Corridor Station')
        records.append({'station_sign': station, 'time_s': clock, 'distance_m': distance,
                        'native_event_code': event.contents[3].value})
    return records


def inspect_result(raw, definition, traces_st1=None):
    root, _ = w.load_next_compatible(raw)
    controller, _, positions = read_layout(root, definition['station_positions_m'])
    require(positions == definition['station_positions_m'], 'Native output has a different Corridor Station alignment')
    require(root.contents[7].values == definition['time_window_s'], 'Native output has a different drawing time window')
    events = mapping(controller.contents[1].value)
    require(set(definition['courses']) <= events.keys(), 'Native diagram lacks an expected actual Course')
    tracks = [mapping(group.value) for group in controller.contents[2:]]
    reservations, releases = tracks[:2]
    station_bank = tracks[2] if len(tracks) > 2 else {}
    traces = []
    for cid in definition['courses']:
        entry = actual_course(cid, events[cid], max(positions.values()), traces_st1.get(cid) if traces_st1 else None)
        entry['reservation_point_count'] = len(items(reservations[cid].contents[0].value)) if cid in reservations else 0
        entry['release_point_count'] = len(items(releases[cid].contents[0].value)) if cid in releases else 0
        entry['station_events'] = station_events(station_bank[cid], positions) if cid in station_bank else []
        traces.append(entry)
    return {'native_document_version': root.clazz.version, 'station_positions_m': positions,
            'archived_doc_file_name': w.string(root.contents[2].value), 'native_course_count': len(events),
            'native_display_window_s': root.contents[7].values, 'course_traces': traces}
