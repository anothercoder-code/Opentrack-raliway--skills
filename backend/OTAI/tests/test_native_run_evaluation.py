from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from opentrack_ai.current_archive import native_evaluation_formats as fmt
from opentrack_ai.current_archive.native_run_evaluation import (
    STOCK_EXE_SHA, OutputFiles, configured_window_matches, evaluate_run, incident_outcome, read_receipts,
    signal_reservation_headways,
)
from opentrack_ai.native_execution import output_hashes


def native(descriptor, body, extra=''):
    return ('// Produced by OpenTrack: Mon Nov 23 11:00:00 2026\n'
            f'// Desc.   : {descriptor}\n{extra}{body}').replace('\n', '\r\n')


def trajectory(descriptor, title, unit, points):
    return native(descriptor, ''.join(f'{x}\t{y}\n' for x, y in points),
                  f'// {title} of Course: T01\n// x-Legend: [s]\n// y-Legend: [{unit}]\n')


def test_native_protocol_stop_clock_includes_a_reported_nonzero_day():
    assert configured_window_matches('23:45:00 - 1 / 00:45:00', 89100)
    assert not configured_window_matches('23:45:00 - 00:45:00', 89100)
    assert not configured_window_matches('23:45:00 - 1 / 00:45:00', 2700)
    assert configured_window_matches('00:05:00 - 00:45:00', 2700)
    assert not configured_window_matches('invalid', 2700)

def test_native_speed_distance_can_start_at_a_negative_reference_offset():
    text = native('OT_vs', '-0.1000\t0.0\n0.0000\t18.0\n',
                  '// Speed/Distance of Course: T01\n// x-Legend: [km]\n// y-Legend: [km/h]\n')
    assert fmt.series(text, 'vs', 'T01') == {'units': ['km', 'km/h'], 'points': [(-0.1, 0.0), (0.0, 18.0)]}
    with pytest.raises(ValueError, match='Invalid speed'):
        fmt.series(text.replace('18.0', '-18.0'), 'vs', 'T01')


@pytest.fixture
def run(tmp_path):
    output = tmp_path / 'output'
    output.mkdir()
    evidence = tmp_path / 'evidence'
    inputs = evidence / 'inputs'
    inputs.mkdir(parents=True)
    paths = {'DestInfoFile': 'chain.dest', 'DepotFile': 'chain.depot', 'TrainFile': 'chain.trains',
             'CourseFile': 'chain.courses', 'StationFile': 'chain.stations',
             'TimetableFile': 'chain.timetable', 'Infrastructure Document': 'start.opentrack'}
    for name in paths.values():
        (inputs / name).write_bytes(b'original input')
    run_members = {key: (tmp_path / value).as_posix() for key, value in paths.items()}
    run_members.update({'Stop Time': '00:03:30', 'Stop Day Offset': '0', 'OutputPath': output.as_posix()})
    (inputs / 'test.run').write_bytes(''.join(f'{key}#{value}#\n' for key, value in run_members.items()).encode())
    native_database_lines = '\n'.join(f'{key}:{value}' for key, value in run_members.items()
                                      if key.endswith('File')) + '\n'
    norm = 'NORMAL\t00:00:10\t\tStart of Simulation\n'
    courses = ([''] * 5 + ['[HH:MM:SS]'] + [''] * 15 + ['[km]', '[km/h]'] + [''] * 3)
    stats = ('T01\tTest\t\tTrain\tBasic\t00:00:10\t10\t00:00:10\t10\t00:03:10\t191'
             '\t00:03:20\t200\t00:03:10\t190\t00:00:50\t50\t00:02:20\t140\t00:02:20\t140'
             '\t2.000\t50.0\t2\t0\t0')
    for name, text in {
        'OT_CourseStatistics.txt': native('OT_coursestat', '\t'.join(courses) + '\n' + stats + '\n'),
        'OT_Messages.txt': native('OT_messages', norm),
        'OT_Protocol.test.txt': native(
            'OT_protocol', f'Databases:\n{native_database_lines}OutputPath:\n{output.as_posix()}\nScenario:\n'
            'Simulation Time: 00:00:00 - 00:03:30\nUsed Courses:\nT01\t(100 %/100 %)\n'
            f'Open Topology-Files:\nUntitled\n{run_members["Infrastructure Document"]}\n'),
        'OT_T01.tt': native(
            'OT_tt', '\nActual Timetable\nStart\tDep.\t00:00:10\t10\t00:00:00\t0\n'
            'Platform\tArr.\t00:00:30\t30\t00:00:20\t20\nPlatform\tDep.\t00:02:30\t150\t00:02:00\t120\n'
            'Platform\tPass\t00:02:31\t151\t00:00:01\t1\nEnd\tArr.\t00:03:10\t190\t00:00:39\t39\n'
            '\nActual Timetable vs. Planned Timetable\n', '// Timetable of Course: T01\n'),
        'OT_T01.vt': trajectory('OT_vt', 'Speed/Time', 'km/h',
                               [(10, 0), (15, 10), (30.91, 0), (150.91, 0), (170, 10), (190.91, 0), (200, 0)]),
        'OT_T01.st1': trajectory('OT_st1', 'Distance/Time', 'km',
                                [(10, 0), (15, .5), (30.91, 1), (150.91, 1), (170, 1.5), (190.91, 2), (200, 2)]),
    }.items():
        (output / name).write_bytes(text.encode('utf-8'))
    before = {'started_utc': (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(),
              'executable_sha256': STOCK_EXE_SHA,
              'command': ['OpenTrack.exe', f'-runfile={(tmp_path / "test.run").as_posix()}'],
              'input_sha256': {path.name: sha256(path.read_bytes()).hexdigest() for path in inputs.iterdir()}}
    process = {'exit_code': 0, 'output_directory': str(output),
               'output_files': [p.name for p in output.iterdir()]}
    (evidence / 'before.json').write_text(json.dumps(before), encoding='utf-8')
    (evidence / 'process.json').write_text(json.dumps(process), encoding='utf-8')
    expect = {'window_end_s': 210, 'courses': [{
        'course_id': 'T01', 'origin_station': 'Start', 'terminal_station': 'End', 'distance_m': 2000,
        'required_stops': [{'station': 'Platform', 'min_dwell_s': 120,
                            'position_min_m': 800, 'position_max_m': 1000}],
    }]}
    return output, evidence, expect


def test_compressed_stationary_interval_and_terminal_completion(run):
    output, evidence, expect = run
    observed = evaluate_run(output, expect, read_receipts(evidence))
    assert observed['native_run_verified']
    assert observed['configured_end_clock_matches']
    assert not observed['end_message_observed']
    stop = observed['courses'][0]['required_stops'][0]
    assert stop['stationary_interval']['duration_s'] == pytest.approx(120)
    assert stop['stationary_interval']['distance_reference_m'] == 1000
    assert stop['resumed_movement']


def test_history_and_explicit_end_are_separate_claims(run):
    output, evidence, expect = run
    measured_only = evaluate_run(output, expect)
    assert measured_only['all_expected_courses_completed']
    assert not measured_only['native_run_verified']
    strict = evaluate_run(output, {**expect, 'require_end_message': True}, read_receipts(evidence))
    assert not strict['native_run_verified']
    assert 'Native runtime did not record an explicit end message' in strict['errors']
    without_endpoint = evaluate_run(output, {'courses': ['T01']}, read_receipts(evidence))
    assert not without_endpoint['native_run_verified']
    assert not without_endpoint['courses'][0]['checks']['terminal_station_named']


def test_explicit_distance_tolerance_records_the_observed_discrepancy(run):
    output, evidence, expect = run
    expect['courses'][0]['distance_m'] = 2002
    narrow = evaluate_run(output, expect, read_receipts(evidence))
    assert not narrow['native_run_verified']
    expect['courses'][0]['distance_tolerance_m'] = 2
    result = evaluate_run(output, expect, read_receipts(evidence))
    assert result['native_run_verified']
    row = result['courses'][0]
    assert (row['expected_distance_m'], row['displacement_m'], row['distance_difference_m'],
            row['distance_tolerance_m']) == (2002, 2000, 2, 2)


def test_motion_during_stop_and_stale_frozen_inputs_fail(run):
    output, evidence, expect = run
    speeds = [(10, 0), (15, 10), (30.91, 0), (40, .1), (150.91, 0), (170, 10), (190.91, 0), (200, 0)]
    (output / 'OT_T01.vt').write_bytes(trajectory('OT_vt', 'Speed/Time', 'km/h', speeds).encode())
    assert not evaluate_run(output, expect, read_receipts(evidence))['native_run_verified']
    (evidence / 'inputs/test.run').write_bytes(b'altered')
    with pytest.raises(ValueError, match='Frozen input hash mismatch'):
        evaluate_run(output, expect, read_receipts(evidence))


def test_original_protocol_fallback_is_not_accepted(run):
    output, evidence, expect = run
    protocol = output / 'OT_Protocol.test.txt'
    protocol.write_bytes(protocol.read_bytes().replace(b'chain.courses', b'other.courses'))
    result = evaluate_run(output, expect, read_receipts(evidence))
    assert result['all_expected_courses_completed']
    assert not result['native_run_verified']
    assert not result['provenance']['protocol_matches_frozen_run']
    assert any('CourseFile differs' in line for line in result['errors'])


def test_overlap_reservation_is_separate_from_physical_occupation():
    rows = fmt.occupations(native('OT_occ', '10\tA\tSR\tC1\n-1\tA\tSO\tC1\n'
                                  '-1\tA\tEO\tC1\n30\tA\tER\tC1\n40\tA\tSR\tC2\n'))
    cycles, invalid = fmt.occupation_intervals(rows)
    assert invalid == 1
    assert cycles == [{'resource': 'A', 'course_id': 'C1', 'reservation_s': [10, 30],
                       'occupation_s': [None, None]}]


def test_pre_reservation_end_preserves_the_original_interval_and_optional_occupation():
    contents = '100\tA\tSR\tC1\n112\tA\tEP\tC1\n-1\tA\tSO\tC1\n-1\tA\tEO\tC1\n130\tA\tER\tC1\n'
    rows = fmt.occupations(native('OT_occ', contents))
    cycles, invalid = fmt.occupation_intervals(rows)
    assert invalid == 0 and cycles == [{
        'resource': 'A', 'course_id': 'C1', 'reservation_s': [100, 130],
        'occupation_s': [None, None], 'pre_reservation_s': [100, 112],
    }]
    for bad_clock in (99, 131):
        invalid_rows = fmt.occupations(native('OT_occ', contents.replace('112\t', f'{bad_clock}\t')))
        assert fmt.occupation_intervals(invalid_rows) == ([], 1)
    with pytest.raises(ValueError, match='negative occupation clock'):
        fmt.occupations(native('OT_occ', contents.replace('112\t', '-1\t')))


def test_messages_keep_course_prefix_and_normalize_incident_subject():
    rows = fmt.messages(native('OT_messages',
                               'NORMAL\t10:21:00\tT01\tCourse T01: Incident started: Cap\t(A)\n'
                               'NORMAL\t10:22:00\t\tIncident stopped: R:1\n'))['incident_events']
    assert [r['transition'] for r in rows] == ['started', 'stopped']
    assert [r['subject'] for r in rows] == ['Cap', 'R:1']
    assert rows[0]['course_id'] == 'T01'
    assert rows[0]['message'] == 'Course T01: Incident started: Cap'


def test_incident_matches_one_course_and_ordered_transitions():
    events = fmt.messages(native('OT_messages',
        'NORMAL\t10:20:00\tOTHER\tCourse OTHER: Incident started: Cap\n'
        'NORMAL\t10:26:10\tT01\tCourse T01: Incident stopped: Cap\n'
        'NORMAL\t10:24:50\tT01\tCourse T01: Incident started: Cap\n'
        'NORMAL\t10:26:10\tOTHER\tCourse OTHER: Incident stopped: Cap\n'))['incident_events']
    exact = {'name': 'Cap', 'target': 'Cap', 'course_id': 'T01',
             'started_clock': '10:24:50', 'stopped_clock': '10:26:10'}
    assert not incident_outcome(exact, True, events)['expectation_met']
    assert incident_outcome(exact, True, [events[2], events[1]])['expectation_met']


def test_physical_peak_requires_matching_original_output_hash_and_bounds(run):
    output, evidence, expect = run
    filename = 'OT_T01.tsvP'
    header = ('// Time/Distance/Speed/Acceleration/TractEffort/Resistance/Mech. Power/Power In/Energy In/Power Supply of Course: T01\n'
              '// [s] [km] [km/h] [m/s^2] [kN] [kW] [MJ]\n')
    (output / filename).write_bytes(native('OT_tsvP', '151\t1.01\t10\t1\t140\t3\t900\t900\t1\t\n'
                                          '152\t1.02\t20\t1\t139\t3\t1800\t1800\t2\t\n', header).encode())
    report = read_receipts(evidence)
    report['output_files'].append(filename)
    bounds = dict(course_id='T01', quantity='tractive_effort_kn', begin_s=150, end_s=155,
                  peak_min=135, peak_max=140, minimum_moving_samples=2)
    expect['expected_physical_peaks'] = [bounds]
    assert not evaluate_run(output, expect, report)['native_run_verified']
    report['output_sha256'] = output_hashes(output)
    verified = evaluate_run(output, expect, report)
    assert verified['native_run_verified'] and verified['physical_peaks'][0]['observed_peak'] == 140
    bounds['peak_max'] = 139
    assert not evaluate_run(output, expect, report)['native_run_verified']
    bounds['peak_max'] = 140
    (output / filename).write_bytes((output / filename).read_bytes() + b'// altered\n')
    assert not evaluate_run(output, expect, report)['native_run_verified']


def test_reservation_headway_uses_the_selected_signal_at_each_course_distance(tmp_path):
    label = 'W_HOME_A_S_J22_W_HOME'
    for course, position, time in (('First', 5.3, 100.25), ('Second', 3.4, 260.28)):
        legend = native('OT_Signals', f'1.0\tDS\tDistant\n{position}\tMS\t{label}\tTS\n',
                        f'// Signal Positions of Course: {course}\n// x-Legend: [km]\n')
        step = (trajectory('OT_step1', 'Route Reservation', 'km',
                           [(time - 20, position - 1), (time - 20, position),
                            (time, position), (time, position + 1), (time + 15, position + 1)])
                .replace('of Course: T01', f'of Course: {course}'))
        (tmp_path / f'OT_{course}.sigpos').write_bytes(legend.encode())
        (tmp_path / f'OT_{course}.step1').write_bytes(step.encode())
    hashes = output_hashes(tmp_path)
    files = OutputFiles(tmp_path, None, set(hashes), hashes, None)
    requested = dict(signal_label=label, leading_course='First', following_course='Second', minimum_s=160)
    outcome, = signal_reservation_headways([requested], files, {'First', 'Second'}, True)
    assert outcome['headway_s'] == 160.03 and outcome['verified']
    requested['minimum_s'] = 160.1
    outcome, = signal_reservation_headways([requested], files, {'First', 'Second'}, True)
    assert not outcome['verified']
