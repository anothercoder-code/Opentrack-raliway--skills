from hashlib import sha256

import pytest

from opentrack_ai.current_archive.native_endpoint_connections import output_names, verify_endpoint_connection


def native(descriptor, body, headers=''):
    return (f'// Produced by OpenTrack: Mon Nov 23 11:00:00 2026\n'
            f'// Desc. : {descriptor}\n{headers}{body}').encode()


def course_outputs(course, origin, terminal, departure, arrival, head_m, positions, speeds):
    cid, itinerary = course['course_id'], course['itinerary']
    prefix = f'OT_{cid}'
    headers = f'// Itineraries: 1: {itinerary}\n'
    legend = ''.join(f'{course[boundary]["position_m"] / 1000:.4f}\tMS\t{course[boundary]["label"]}\tTS\n'
                     for boundary in ('origin', 'terminal'))

    def trace(descriptor, title, unit, rows):
        body = ''.join(f'{clock}\t{value}\n' for clock, value in rows)
        return native(descriptor, body,
                      headers + f'// {title} of Course: {cid}\n// x-Legend: [s]\n// y-Legend: [{unit}]\n')

    return {
        prefix + '.sigpos': native('OT_Signals', legend,
                                   headers + f'// Signal Positions of Course: {cid}\n// x-Legend: [km]\n'),
        prefix + '.tt': native('OT_tt', f'Actual Timetable\n{origin}\tDep.\t{departure[0]}\t{departure[1]}\n'
                               f'{terminal}\tArr.\t{arrival[0]}\t{arrival[1]}\n'
                               'Actual Timetable vs. Planned Timetable\n', f'// Timetable of Course: {cid}\n'),
        prefix + '.vt': trace('OT_vt', 'Speed/Time', 'km/h', speeds),
        prefix + '.st1': trace('OT_st1', 'Distance/Time', 'km',
                               [*positions, (speeds[-1][0], head_m / 1000)]),
    }


@pytest.fixture(params=['reverse', 'continue'])
def endpoint_run(tmp_path, request):
    reverse = request.param == 'reverse'
    first = {'course_id': 'FIRST', 'itinerary': 'I:Start-Link', 'terminal_station': 'Link platform',
             'terminal_head_m': 950, 'origin': {'label': 'Start', 'position_m': 0},
             'terminal': {'label': 'Link east', 'position_m': 1000}}
    second = {'course_id': 'NEXT', 'itinerary': 'I:Link-End', 'terminal_station': 'End',
              'terminal_head_m': 1200, 'origin': {'label': 'Link west' if reverse else 'Link east', 'position_m': 0},
              'terminal': {'label': 'End', 'position_m': 1200}}
    check = {'predecessor': first, 'successor': second, 'station_sign': 'LP', 'movement': request.param,
             'minimum_hold_s': 420}
    messages = ('NORMAL\t23:59:50\tNEXT\tCourse NEXT: Trains splitted at LP\t(LP)\n'
                'NORMAL\t23:59:50\tNEXT\tCourse NEXT: Ready for Simulation\t(LP)\n')
    files = {
        'OT_Messages.txt': native('OT_messages', messages),
        **course_outputs(first, 'Start', 'Link platform', ('23:59:20', 86360), ('23:59:50', 86390), 950,
                         [(86360, 0), (86375, .5)], [(86360, 0), (86375, 50), (86390.4, 0)]),
        **course_outputs(second, 'Link platform', 'End', ('1 / 00:09:50', 86990), ('1 / 00:10:20', 87020), 1200,
                         [(86390.4, 0), (86990, 0), (87000, .5)],
                         [(86390.4, 0), (86990, 0), (87000, 50), (87020.4, 0)]),
    }
    hashes = {}

    def replace(name, data):
        (tmp_path / name).write_bytes(data)
        hashes[name] = sha256(data).hexdigest()

    for name, data in files.items():
        replace(name, data)
    return tmp_path, check, files, hashes, replace


def test_endpoint_connection_binds_original_courses_and_actual_hold_across_midnight(endpoint_run):
    directory, check, _, hashes, _ = endpoint_run
    result = verify_endpoint_connection(directory, check, hashes)
    assert result['verified'] and result['movement'] == check['movement']
    assert result['predecessor']['terminal_signal']['observed_position_m'] == 1000
    assert result['predecessor']['arrival_trajectory_m'] == 950
    assert result['successor']['final_trajectory_m'] == 1200
    assert result['successor_first_trajectory'] == {'time_s': 86390.4, 'position_m': 0}
    assert result['motion']['successor_stationary_interval']['duration_s'] == pytest.approx(599.6)
    assert set(result['output_sha256']) == output_names(check) == hashes.keys()
    with pytest.raises(ValueError, match='stationary hold was shorter'):
        verify_endpoint_connection(directory, {**check, 'minimum_hold_s': 600}, hashes)


def test_matching_split_message_alone_cannot_override_original_fallback_warning(endpoint_run):
    directory, check, files, hashes, replace = endpoint_run
    name = 'OT_Messages.txt'
    replace(name, files[name] + b'WARNING\t23:59:50\tNEXT\tCourse NEXT: Itinerary changed after Split at LP\t(LP)\n')
    with pytest.raises(ValueError, match='fallback Itinerary'):
        verify_endpoint_connection(directory, check, hashes)


def test_endpoint_connection_requires_expected_first_signal_and_bound_content(endpoint_run):
    directory, check, files, hashes, replace = endpoint_run
    name = 'OT_NEXT.sigpos'
    data = files[name].replace(check['successor']['origin']['label'].encode(), b'Other directed End')
    (directory / name).write_bytes(data)
    with pytest.raises(ValueError, match='hash mismatch'):
        verify_endpoint_connection(directory, check, hashes)
    replace(name, data)
    with pytest.raises(ValueError, match='origin main signal differs'):
        verify_endpoint_connection(directory, check, hashes)
