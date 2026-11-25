"""A native Corridor shown against the selected project's live planned timetable bank."""

import math

from . import catalogs, course_factories, timetable_setters, writer as w
from .native_corridors import array, dictionary
from .native_evaluation_formats import require
from .prepare_contract import auxiliary, preflight
from .project_workflow.relocation import DIAGRAM, _layout, relocate_project
from .zero_generation import native_signal_routes as ns


SHOW_ACTUAL = 0x400
SHOW_PLANNED = 0x800
PLANNED_CLOCKS = {'arrival', 'departure', 'arrival_day_offset', 'departure_day_offset'}
TIME_FORMATS = {'none': 0, 'mm': 1, 'mm:ss': 2}
CORRIDOR_MEMBER = 'OTDocuments/Planned Corridor.otsimcor'


def corridor_shape(root):
    version = root.clazz.version
    require(version in (11, 13), 'Expected a native Corridor v11 or v13')
    _layout(root, 'OTCorridorDocument', version, DIAGRAM if version == 13 else DIAGRAM[:24])
    controller = root.contents[0].value
    controller_version = controller.clazz.version
    require(controller_version in (1, 2), 'Expected native Corridor controller v1 or v2')
    _layout(controller, 'OTTCorridorSimController', controller_version, ['@'] * (3 + controller_version))
    topo = root.contents[1].value
    _layout(topo, 'OTTCorridorTopoController', 0, ['@'] * 3)
    return controller, topo


def corridor_stations(root, known_stations):
    found = {}
    last_distance = -1
    for index, row in enumerate(catalogs.array(root.contents[15].value)):
        catalogs.shape(row, 'OTCorridorStation', 0, ['@', 'iiii', 'iiii'])
        sign = catalogs.text(row.contents[0].value)
        ordinal, distance, *_ = row.contents[1].values
        require(ordinal == index and sign in known_stations and sign not in found and distance > last_distance,
                f'Invalid ordered Corridor Station binding: {sign}')
        found[sign] = distance
        last_distance = distance
    require(2 <= len(found) <= 10000, 'A planned Corridor requires at least two distinct Station signs')
    return found


def time_for(row, slot):
    value = row.contents[6 + slot].value
    clock = None if value is None else catalogs.text(value)
    if clock in (None, '', 'HH:MM:SS'):
        return None
    value = course_factories.clock(clock) + row.contents[15].values[slot] * 86400
    require(0 <= value <= 10_000_000, 'Absolute planned time outside current diagram window domain')
    return value


def planned_rows(course_raw, timetable_raw, station_positions, courses):
    root, _ = w.load_next_compatible(course_raw)
    table, _ = w.load_next_compatible(timetable_raw)
    enabled = {catalogs.text(item.contents[0].value) for item in catalogs.course_items(root)
               if item.contents[5].value == 1}
    require(isinstance(courses, list) and 1 <= len(courses) <= 10000 and all(type(cid) is str for cid in courses)
            and len(courses) == len(set(courses)) and set(courses) <= enabled,
            'Select distinct enabled Course IDs from the project')
    selected = {cid: [] for cid in courses}
    for key, row in course_factories.timetable(table).items():
        cid = catalogs.text(row.contents[1].value)
        if cid in selected:
            selected[cid].append((row.contents[3].value, key, row))
    report = {}
    for cid, rows in selected.items():
        rows.sort(key=lambda row: row[0])
        require(rows and [row[0] for row in rows] == list(range(len(rows)))
                and all(row[2].contents[4].value == len(rows) - 1 for row in rows),
                f'{cid} timetable has missing or noncanonical row ordinals')
        previous = -1
        points = []
        for _, key, row in rows:
            reference = row.contents[2].value
            require(reference is None or catalogs.text(reference) in ('', '0', '-1'),
                    f'{key} uses a relative interval. Select a Course with absolute saved planned clocks.')
            arrival, departure = time_for(row, 0), time_for(row, 1)
            for instant in (arrival, departure):
                if instant is None:
                    continue
                require(instant >= previous, f'{key} planned clocks go backwards')
                previous = instant
            station = catalogs.text(row.contents[5].value)
            if station in station_positions and (arrival is not None or departure is not None):
                points.append({'row_key': key, 'station_sign': station, 'distance_m': station_positions[station],
                               'arrival_s': arrival, 'departure_s': departure})
        require(len({point['station_sign'] for point in points}) >= 2,
                f'{cid} requires at least two timed Station signs on the Corridor')
        report[cid] = points
    return report


def display_document(root, version, target_path, points, *, show_actual, time_format):
    require(type(show_actual) is bool and time_format in TIME_FORMATS, 'Invalid native graph display settings')
    controller, topo = corridor_shape(root)
    actual_fingerprints = [w.fingerprint(value.value) for value in controller.contents]
    topo_fingerprint = w.fingerprint(topo)
    if root.clazz.version == 11:
        root.clazz = w.Class(b'OTCorridorDocument', 13, root.clazz.superclass)
        root.contents.extend([w.TypedGroup([b'i', b'i'], [0, 0]), w.TypedValue(b'@', array([]))])
    if controller.clazz.version == 1:
        controller.clazz = w.Class(b'OTTCorridorSimController', 2, controller.clazz.superclass)
        controller.contents.append(w.TypedValue(b'@', dictionary({})))
    root.contents[2].value = ns.string(target_path)
    flags = root.contents[13].value & ~SHOW_ACTUAL
    root.contents[13].value = flags | SHOW_PLANNED | (SHOW_ACTUAL if show_actual else 0)
    root.contents[24].values[1] = TIME_FORMATS[time_format]
    clocks = [time for rows in points.values() for row in rows for key in ('arrival_s', 'departure_s')
              if (time := row[key]) is not None]
    saved_begin, saved_end = root.contents[7].values
    require(math.isfinite(saved_begin) and math.isfinite(saved_end) and saved_end > saved_begin,
            'Invalid saved Corridor display window')
    root.contents[7].values = [min(saved_begin, float(max(0, min(clocks) - 60))),
                               max(saved_end, float(max(clocks) + 60))]
    edited = w.dump_verified(root, version)
    fresh, _ = w.load_next_compatible(edited)
    after, after_topo = corridor_shape(fresh)
    require([w.fingerprint(group.value) for group in after.contents[:len(actual_fingerprints)]] == actual_fingerprints
            and w.fingerprint(after_topo) == topo_fingerprint, 'Corridor display edit changed saved actual or topology data')
    require(w.string(fresh.contents[2].value) == target_path and fresh.contents[13].value == root.contents[13].value
            and fresh.contents[24].values == root.contents[24].values and fresh.contents[7].values == root.contents[7].values,
            'Corridor display options failed native archive readback')
    return edited


def prepare(inputs, corridor, *, source_root, target_root, run_file, hashes, courses,
            timetable_edits=None, show_actual=True, planned_time_format='none'):
    from .itinerary_edit_tools import EditableItineraryProject

    require(not any(key == 'Train Diagram Document' for key, _, _ in auxiliary.records(inputs[run_file])),
            'Use a source run without another Train Diagram Document binding')
    moved, relocation = relocate_project(
        inputs, source_root=source_root, target_root=target_root, run_file=run_file, expected_hashes=hashes,
        discard_unrelated_destinations=True, project_type=EditableItineraryProject,
    )
    roles = relocation['catalog_paths']
    root, version = w.load_next_compatible(corridor)
    corridor_shape(root)
    stations = catalogs.station_items(w.load_next_compatible(moved[roles['stations']])[0])
    positions = corridor_stations(root, stations)
    selected_rows = planned_rows(moved[roles['courses']], moved[roles['timetable']], positions, courses)
    edits_report = None
    if timetable_edits is not None:
        require(isinstance(timetable_edits, dict) and 1 <= len(timetable_edits) <= 10000,
                'Provide a nonempty map of existing planned timetable row changes')
        keys = {row['row_key'] for rows in selected_rows.values() for row in rows}
        require(set(timetable_edits) <= keys and all(isinstance(fields, dict) and fields.keys() <= PLANNED_CLOCKS
                                                    for fields in timetable_edits.values()),
                'Only planned clocks on selected existing Corridor timetable rows may be edited')
        moved[roles['timetable']], edits_report = timetable_setters.patch_rows(moved[roles['timetable']], timetable_edits)
        selected_rows = planned_rows(moved[roles['courses']], moved[roles['timetable']], positions, courses)
    diagram_path = target_root + '/' + CORRIDOR_MEMBER
    moved[CORRIDOR_MEMBER] = display_document(root, version, diagram_path, selected_rows,
                                             show_actual=show_actual, time_format=planned_time_format)
    original_run = moved[run_file]
    newline = b'\r\n' if original_run.endswith(b'\r\n') else b'\n'
    moved[run_file] = original_run + ('Train Diagram Document#' + diagram_path + '#').encode('ascii') + newline
    prefix = target_root + '/'

    def bound_reader(path):
        require(path.startswith(prefix), 'Preflight read outside fresh project')
        return moved[path[len(prefix):]]

    checked = preflight.check(moved[run_file], bound_reader)
    require(checked['passed_static_subset'], f'Prepared planned graph preflight failed: {checked["errors"]}')
    return moved, {'schema': 'native-planned-corridor-preparation/1', 'project_directory': target_root,
                   'run_file': target_root + '/' + run_file, 'corridor_path': diagram_path,
                   'source_relocation': relocation, 'planned_timetable_rows': selected_rows,
                   'timetable_edits': edits_report, 'station_positions_m': positions,
                   'show_planned': True, 'show_actual': show_actual, 'planned_time_format': planned_time_format,
                   'preflight': checked, 'native_application_executed': False}
