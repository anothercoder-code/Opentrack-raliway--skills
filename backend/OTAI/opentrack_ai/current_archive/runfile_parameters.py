"""Pure bytes-only .run inspection/editing. No file writes or engine calls."""
from decimal import Decimal
import math
import re
import struct

WRITABLE = (b'Start Day Offset', b'Start Time', b'Stop Day Offset', b'Stop Time', b'Step')

KNOWN = frozenset([b'Adhesion Outside', b'Adhesion Tunnel', b'Break Day Offset', b'Break Time', b'Communication Period', b'CourseFile', b'Delay Format', b'Delay Scenario', b'DepotFile', b'DestInfoFile', b'Document Set Document', b'Document Set Name', b'Incident', b'Infrastructure Document', b'Keep Occupations', b'Label Size', b'Mean Delay', b'Multithreaded', b'Optimization Period', b'Optimize Dispatching', b'Optimize Train Sequence', b'Output Acc./Distance', b'Output Acc./Time', b'Output Altitude, Gradient & Radius', b'Output Braking Actions', b'Output Course & Station Statistics', b'Output Distance/Time', b'Output Distance/Time Rev. Dir.', b'Output Instruments', b'Output Messages (Text)', b'Output Resistance/Dist.', b'Output Route Occ.', b'Output Simulation Protocol', b'Output Speed/Distance', b'Output Speed/Distance Rev. Dir.', b'Output Speed/Time', b'Output Station- & Signalpositions', b'Output Time/Dist./Speed/Power', b'Output Timetable & Delay Statistics', b'Output Timetable (Text)', b'Output Tract.Effort/Dist.', b'Output Train Diagram', b'OutputPath', b'Performance', b'Power/Dist. & Energy/Dist.', b'Safety Margin', b'Show Current Time', b'Show Instruments', b'Show Messages', b'Show Train', b'Show Train Delay', b'Show Train Descr.', b'Show Train ID', b'Start Day Offset', b'Start Time', b'StationFile', b'Step', b'Stop Day Offset', b'Stop Time', b'Time Ratio', b'TimetableFile', b'Train Diagram Document', b'TrainFile', b'TrainType', b'Use Curve Resistance', b'Use Switch Time and Route Res. Time'])
NATIVE_GROUPS = ((b'Start Day Offset', b'Start Time', b'Stop Day Offset', b'Stop Time', b'Break Day Offset', b'Break Time', b'Step', b'Time Ratio', b'Adhesion Outside', b'Adhesion Tunnel', b'Delay Scenario', b'Mean Delay', b'Performance', b'Multithreaded', b'Keep Occupations', b'Optimize Dispatching', b'Show Train ID', b'Show Train Descr.', b'Show Train Delay', b'Show Train', b'Label Size', b'Delay Format', b'Show Current Time', b'Show Messages', b'Show Instruments', b'Output Train Diagram', b'Output Timetable (Text)', b'Output Distance/Time Rev. Dir.', b'Output Distance/Time', b'Output Speed/Distance Rev. Dir.', b'Output Speed/Distance', b'Output Speed/Time', b'Output Acc./Distance', b'Output Acc./Time', b'Output Tract.Effort/Dist.', b'Output Resistance/Dist.', b'Power/Dist. & Energy/Dist.', b'Output Time/Dist./Speed/Power', b'Output Braking Actions', b'Output Route Occ.', b'Output Instruments', b'Output Altitude, Gradient & Radius', b'Output Station- & Signalpositions', b'Output Messages (Text)', b'Output Course & Station Statistics', b'Output Timetable & Delay Statistics', b'Output Simulation Protocol'), (b'DestInfoFile', b'DepotFile', b'TrainFile', b'CourseFile', b'StationFile', b'TimetableFile', b'OutputPath', b'TrainType', b'Use Curve Resistance', b'Use Switch Time and Route Res. Time', b'Communication Period', b'Optimization Period', b'Optimize Train Sequence', b'Safety Margin'), (b'Infrastructure Document', b'Train Diagram Document', b'Incident'))
REPEATED = {b'TrainType', b'Infrastructure Document', b'Train Diagram Document', b'Document Set Document', b'Incident'}

class RunfileError(ValueError):
    pass

def _scan(data):
    if type(data) is not bytes:
        raise RunfileError('bytes input required')
    if not data or len(data) > 1024 * 1024:
        raise RunfileError('empty or exceeds API 1 MiB guard')
    
    if any(c > 127 or c < 32 and c not in (10, 13) for c in data):
        raise RunfileError('ambiguous encoding/control byte; ASCII only')
    rows, issues, seen, offset = [], [], {}, 0
    for number, raw in enumerate(data.splitlines(keepends=True), 1):
        body = raw[:-2] if raw.endswith(b'\r\n') else raw[:-1] if raw.endswith(b'\n') else raw
        if b'\r' in body or len(raw) > 1023:
            issues.append(f'line {number}: bare CR or native fgets limit')
        if not body or body.startswith(b'//'):
            offset += len(raw)
            continue
        parts = body.split(b'#')
        if len(parts) != 3 or parts[2] or not parts[0]:
            issues.append(f'line {number}: expected exact key#value#')
            offset += len(raw)
            continue
        key, value, _ = parts
        if key not in KNOWN:
            issues.append(f'line {number}: unknown key {key!r}')
        if key in seen and key not in REPEATED:
            issues.append(f'line {number}: duplicate singleton {key!r}')
        seen[key] = value
        
        for group in NATIVE_GROUPS:
            hit = next((token for token in group if token in body), None)
            if hit is not None and hit != key:
                issues.append(f'line {number}: native substring collision {hit!r}')
        start = offset + len(key) + 1
        rows.append((key, value, start, start + len(value)))
        offset += len(raw)
    for key in WRITABLE:
        if key not in seen:
            issues.append(f'missing required key {key!r}')
    return rows, seen, issues

def _validate(values):
    def clock(key):
        v = values[key]
        if not re.fullmatch(rb'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]', v):
            raise RunfileError(f'{key!r}: API requires HH:MM:SS in 00:00:00..23:59:59')
        h, m, s = map(int, v.split(b':'))
        return h * 3600 + m * 60 + s
    def day(key):
        v = values[key]
        if not re.fullmatch(rb'(?:0|[1-9][0-9]{0,4})', v) or int(v) > 24854:
            raise RunfileError(f'{key!r}: API day guard 0..24854 (not native business limit)')
        return int(v)
    start = day(b'Start Day Offset') * 86400 + clock(b'Start Time')
    stop = day(b'Stop Day Offset') * 86400 + clock(b'Stop Time')
    if stop <= start:
        raise RunfileError('API requires explicit stop > start; no native auto-rollover')
    v = values[b'Step']
    if not re.fullmatch(rb'[0-9]+(?:\.[0-9]+)?', v):
        raise RunfileError('Step: plain positive decimal required')
    step = Decimal(v.decode('ascii'))
    if step <= 0 or step > stop - start:
        raise RunfileError('Step: API requires 0 < seconds <= duration')
    try:
        f32 = struct.unpack('<f', struct.pack('<f', float(step)))[0]
    except (OverflowError, ValueError):
        raise RunfileError('Step: outside finite float32 encoding domain') from None
    if not math.isfinite(f32) or f32 <= 0:
        raise RunfileError('Step: underflow/nonfinite float32')
    
    end32 = struct.unpack('<f', struct.pack('<f', float(stop)))[0]
    advanced = struct.unpack('<f', struct.pack('<f', end32 + f32))[0]
    if advanced <= end32:
        raise RunfileError('Step: cannot advance float32 clock at stop (API safety guard)')
    return {'start_seconds': start, 'stop_seconds': stop, 'step_seconds_float32': f32}

def inspect_runfile(data: bytes) -> dict:
    """Report admission and exact raw values, without changing bytes or reading paths."""
    rows, values, issues = _scan(data)
    numeric = None
    if not issues:
        try:
            numeric = _validate(values)
        except RunfileError as exc:
            issues.append(str(exc))
    return {'editable': not issues, 'issues': issues, 'parameters': {k: values.get(k) for k in WRITABLE},
            'readonly': [(k, v) for k, v, _, _ in rows if k not in WRITABLE], 'numeric': numeric}

def edit_runfile(data: bytes, changes: dict[bytes, bytes]) -> bytes:
    """Replace only specified value spans. Caller owns authorization and atomic save."""
    if type(changes) is not dict or any(type(k) is not bytes or type(v) is not bytes for k, v in changes.items()):
        raise RunfileError('changes must be dict[bytes, bytes]')
    if set(changes) - set(WRITABLE):
        raise RunfileError('read-only/unknown requested key')
    rows, values, issues = _scan(data)
    if issues:
        raise RunfileError('; '.join(issues))
    _validate(values)  
    updated = values | changes
    _validate(updated)
    out = data
    for key, _, start, end in reversed(rows):
        if key in changes:
            out = out[:start] + changes[key] + out[end:]
    if not inspect_runfile(out)['editable']:
        raise RunfileError('post-edit admission failed')
    return out
