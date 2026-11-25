"""Check an original OpenTrack through-platform stop using frozen run evidence."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
from itertools import groupby
import json
import math
from pathlib import Path
import re


STOCK_EXE_SHA = 'f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(condition, message):
    if not condition:
        raise ValueError(message)


def actual_timetable(text):
    start = text.index('Actual Timetable')
    end = text.index('Actual Timetable vs. Planned Timetable', start + 1)
    events = []
    for line in text[start:end].splitlines():
        columns = [field.strip() for field in line.split('\t')]
        if len(columns) < 4 or columns[1] not in {'Arr.', 'Dep.', 'Pass'}:
            continue
        checked(re.fullmatch(r'[0-9]+', columns[3]) is not None, 'Missing actual event elapsed seconds')
        events.append({'station': columns[0], 'kind': columns[1], 'clock': columns[2], 'time_s': int(columns[3])})
    return events


def samples(text):
    pairs = []
    for line in text.splitlines():
        if not line.strip() or line.startswith('//'):
            continue
        fields = line.split()
        checked(len(fields) == 2, 'Unexpected native time-series record')
        instant, value = map(float, fields)
        checked(math.isfinite(instant) and math.isfinite(value), 'Non-finite native sample')
        checked(not pairs or instant >= pairs[-1][0], 'Out-of-order native sample times')
        pairs.append((instant, value))
    return pairs


def verify(project, request, prepared, launch_evidence):
    checked(prepared.get('saved') is True and prepared.get('tool') == 'opentrack_build_reference_platform_corridor',
            'Expected a saved reference-platform build receipt')
    before = json.loads((launch_evidence / 'before.json').read_bytes())
    process = json.loads((launch_evidence / 'process.json').read_bytes())
    output = project / 'output'
    checked(process['exit_code'] == 0 and Path(process['output_directory']).resolve() == output,
            'Original process did not return normally for this output directory')
    checked(before['executable_sha256'] == STOCK_EXE_SHA, 'Unrecognized original executable fingerprint')
    hashes = {name: meta['sha256'] for name, meta in prepared['files'].items()}
    checked(hashes == before['input_sha256'], 'Original process did not use the published bytes')
    checked(all(digest(launch_evidence / 'inputs' / name) == value for name, value in hashes.items()),
            'Frozen original inputs do not match the build manifest')
    started = datetime.fromisoformat(before['started_utc']).timestamp()
    output_hashes = {}

    def read(name):
        path = output / name
        checked(name in process['output_files'] and path.stat().st_mtime >= started - 2,
                f'Native output was not recorded for this run: {name}')
        raw = path.read_bytes()
        output_hashes[name] = hashlib.sha256(raw).hexdigest()
        return raw.decode('latin-1')

    messages = read('OT_Messages.txt')
    levels = Counter(line.split('\t', 1)[0].strip() for line in messages.splitlines() if '\t' in line)
    checked(not any(levels[level] for level in ('ERROR', 'SEVERE', 'FATAL')), 'Original reported a runtime error')
    checked('Cancel Simulation' not in messages, 'Original reported a canceled simulation')
    stats = [line.split('\t') for line in read('OT_CourseStatistics.txt').splitlines()]
    stations = {station['id']: station['name'] for station in request['spec']['network']['stations']}
    plans = {course['course_id']: course for course in prepared['plan']}
    completed = []
    for visit in prepared['reference_platform_visits']:
        cid = visit['course_id']
        stop_name = stations[visit['station_sign']]
        terminal_name = stations[plans[cid]['visits'][-1]['station_sign']]
        events = actual_timetable(read(f'OT_{cid}.tt'))
        arrival, = [event for event in events if event['station'] == stop_name and event['kind'] == 'Arr.']
        departure, = [event for event in events if event['station'] == stop_name and event['kind'] == 'Dep.']
        terminal, = [event for event in events if event['station'] == terminal_name and event['kind'] == 'Arr.']
        a, d, end = (event['time_s'] for event in (arrival, departure, terminal))
        checked(a < d < end and d - a >= visit['planned_departure_s'] - visit['planned_arrival_s'] - 1,
                'Actual platform dwell or downstream arrival missing')
        speeds = samples(read(f'OT_{cid}.vt'))
        positions = samples(read(f'OT_{cid}.st1'))
        # The original compresses a constant interval to its boundary samples.
        # Timetable clocks omit the fractional seconds recorded in the series.
        plateaux = []
        for zero, group in groupby(speeds, key=lambda sample: sample[1] == 0):
            if not zero:
                continue
            run = list(group)
            start, stop = run[0][0], run[-1][0]
            if abs(start - a) <= 1 and abs(stop - d) <= 1 and stop > start:
                plateaux.append((start, stop, len(run)))
        checked(len(plateaux) == 1, 'Missing continuous zero-speed interval aligned with actual platform events')
        start, stop, count = plateaux[0]
        checked(abs((stop - start) - (d - a)) <= 1, 'Zero-speed duration differs from actual dwell')
        standing = [(t, v * 1000) for t, v in positions if start <= t <= stop]
        checked(len(standing) >= 2 and standing[0][0] == start and standing[-1][0] == stop,
                'Position series does not cover both dwell boundaries')
        standing_m = [value for _, value in standing]
        checked(max(standing_m) - min(standing_m) <= 0.11,
                'Train distance changed during the platform dwell')
        edge_end = visit['distance_m']
        edge_start = edge_end - visit['area_length_m']
        checked(all(edge_start - 0.11 <= p <= edge_end + 0.11 for p in standing_m),
                'Stopped distance reference is outside the modeled platform Edge')
        checked(any(stop < t < end and v > 0 for t, v in speeds)
                and positions[-1][1] * 1000 > edge_end, 'No measured onward movement after the platform stop')
        course, = [row for row in stats if len(row) == 26 and row[0] == cid]
        expected_m = prepared['traces'][plans[cid]['itinerary']]['length_m']
        checked(course[9].strip() == terminal['clock'] and abs(int(course[10]) - end) <= 1
                and abs(float(course[21]) * 1000 - expected_m) <= 1,
                'Native course statistics do not show the planned downstream completion')
        completed.append({
            'course_id': cid, 'actual_arrival': arrival['clock'], 'actual_departure': departure['clock'],
            'dwell_s': d - a, 'zero_speed_samples': count, 'zero_speed_interval_s': [start, stop],
            'standing_distance_m': round(standing_m[0], 3), 'platform_edge_span_m': [edge_start, edge_end],
            'planned_train_length_m': visit['train_length_m'], 'downstream_arrival': terminal['clock'],
            'course_distance_m': expected_m, 'onward_positive_speed_verified': True,
        })
    checked(bool(completed), 'Build receipt contains no through-platform visit')
    return {'native_run_verified': True, 'courses': completed, 'message_levels': dict(levels),
            'warning_rows': [line for line in messages.splitlines() if line.startswith('WARNING')],
            'user_preferences_changed': process['prefs_file_changed'], 'input_sha256': hashes,
            'output_sha256': output_hashes,
            'position_semantics': 'Native distance/time reference; no independent axle or rear-position measurement.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = verify(args.project.resolve(), json.loads(args.request.read_bytes()),
                    json.loads(args.receipt.read_bytes()), args.evidence.resolve())
    payload = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
    if args.report is not None:
        with args.report.open('x', encoding='utf-8') as stream:
            stream.write(payload)
    print(payload, end='')
