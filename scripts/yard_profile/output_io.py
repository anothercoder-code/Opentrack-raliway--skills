"""Portable native-output primitives; no launch or GUI actions."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,math,os,re,stat

ROLES={'dest':'DestInfoFile','depot':'DepotFile','trains':'TrainFile','courses':'CourseFile','stations':'StationFile','timetable':'TimetableFile'}
MONTHS={name:i for i,name in enumerate('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(),1)}
HEADER=re.compile(r'^// Produced by OpenTrack:\s*(.+?)\s*$',re.M)
LABEL=re.compile(r'^[A-Za-z0-9_-]{1,48}$')

class ReviewError(ValueError):
    pass



def need(condition, message):
    if not condition:
        raise ReviewError(message)



def sha(blob):
    return hashlib.sha256(blob).hexdigest()



def parse_json(blob):
    def unique(items):
        out={}
        for key,value in items:
            need(key not in out,'Duplicate JSON key: '+key);out[key]=value
        return out
    def invalid(value):raise ReviewError('Nonfinite JSON value: '+value)
    return json.loads(blob.decode('utf-8-sig'),object_pairs_hook=unique,parse_constant=invalid)


def read_json(path):
    return parse_json(stable_file(path)[0])



def clock(value):
    need(re.fullmatch(r'\d{2}:\d{2}:\d{2}', value) is not None, 'Invalid native clock: ' + value)
    h, m, s = map(int, value.split(':'))
    need(0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60, 'Native clock outside same-day range')
    return h * 3600 + m * 60 + s



def iso(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(parsed.tzinfo is not None, 'Baseline timestamp needs an explicit UTC offset')
    return parsed.astimezone(timezone.utc)



def zone(value):
    need(re.fullmatch(r'[+-]\d{2}:\d{2}', value) is not None, 'Use an explicit offset such as +08:00')
    h, m = map(int, value[1:].split(':'))
    need(h <= 14 and m < 60, 'Timezone offset outside supported range')
    return timezone((1 if value[0] == '+' else -1) * timedelta(hours=h, minutes=m))



def producer(value, tz):
    match = re.fullmatch(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\d{4})', value)
    need(match is not None and match[2] in MONTHS, 'Unsupported native producer date: ' + value)
    h, m, s = map(int, match[4].split(':'))
    result = datetime(int(match[5]), MONTHS[match[2]], int(match[3]), h, m, s, tzinfo=tz)
    need(result.weekday() == ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].index(match[1]), 'Producer weekday/date mismatch')
    return result.astimezone(timezone.utc)



def clean_parents(path):
    for parent in (path.absolute(),*path.absolute().parents):
        if parent.exists():
            need(not parent.is_symlink() and not getattr(parent.lstat(),'st_file_attributes',0)&0x400,
                 'Symlink/reparse input, output or evidence ancestor refused: '+str(parent))


def regular(path):
    clean_parents(path)
    meta = path.lstat()
    need(stat.S_ISREG(meta.st_mode) and meta.st_nlink==1 and not path.is_symlink() and not getattr(meta, 'st_file_attributes', 0) & 0x400,
         'Nonregular/reparse output or input refused: ' + str(path))
    return meta



def stable_file(path):
    before = regular(path); blob = path.read_bytes(); after = regular(path)
    need((before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns),
         'File changed during read: ' + str(path))
    need(path.read_bytes() == blob, 'File bytes changed during read: ' + str(path))
    return blob, {'sha256': sha(blob), 'bytes': len(blob), 'mtime_ns': after.st_mtime_ns,
                  'mtime_utc': datetime.fromtimestamp(after.st_mtime_ns / 1e9, timezone.utc).isoformat()}



def output_set(output):
    clean_parents(output)
    need(output.is_dir() and not output.is_symlink(), 'Actual project output directory is absent or a symlink')
    result = []
    for path in sorted(output.rglob('*')):
        meta = path.lstat()
        need(not path.is_symlink() and not getattr(meta, 'st_file_attributes', 0) & 0x400, 'Reparse output path refused')
        if path.is_file(): result.append(path)
        else: need(path.is_dir(), 'Nonregular output member refused')
    return result



def write_new(path, blob):
    clean_parents(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean_parents(path)
    if path.exists():
        regular(path)
        need(path.read_bytes() == blob, 'Evidence collision; use a fresh label: ' + str(path))
    else:
        with path.open('xb') as handle:
            handle.write(blob);handle.flush();os.fsync(handle.fileno())



def header_value(text, pattern, name):
    values = re.findall(pattern, text, re.M)
    need(len(values) == 1, 'Exactly one ' + name + ' required')
    return values[0].strip()



def parse_stats(text, course_ids):
    rows = {}; routes = {cid: [] for cid in course_ids}
    for line in text.splitlines():
        parts = [s.strip() for s in line.split('\t')]
        if len(parts) == 26 and parts[0] not in set(course_ids) | {'Course', 'Total', ''}:
            raise ReviewError('Unexpected CourseStatistics primary Course: ' + parts[0])
        if not parts or parts[0] not in course_ids: continue
        if len(parts) == 26:
            need(parts[0] not in rows, 'Duplicate CourseStatistics primary row: ' + parts[0]); rows[parts[0]] = parts
        elif len(parts) == 6: routes[parts[0]].append(parts)
        else: raise ReviewError('Unexpected CourseStatistics row width for ' + parts[0])
    need(set(rows) == set(course_ids), 'CourseStatistics lacks one or more of the declared primary rows')
    return rows, routes



def parse_vt(text):
    need('// x-Legend: [s]' in text and '// y-Legend: [km/h]' in text, 'VT units must be seconds and km/h')
    samples = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('//'): continue
        values = line.split(); need(len(values) == 2, 'Non-two-column VT body row')
        try: pair = tuple(map(float, values))
        except ValueError as exc: raise ReviewError('Nonnumeric VT row') from exc
        need(all(math.isfinite(v) for v in pair) and pair[1] >= 0, 'Nonfinite/negative VT speed')
        samples.append(pair)
    need(len(samples) >= 2 and all(a[0] <= b[0] for a, b in zip(samples, samples[1:])), 'Insufficient or unordered VT samples')
    need(max(v for _, v in samples) > 0 and samples[-1][1] == samples[-2][1] == 0, 'No physical motion followed by two terminal zero-speed samples')
    return samples

