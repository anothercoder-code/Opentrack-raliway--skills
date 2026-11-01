"""Static current-only planned shift reuse; caller owns atomic bytes transaction.
Original selected methods are AST-identical static copies, never runtime exec.
Adapters narrow legacy context and time parsing: nil/sentinel remain untouched.
Actual shifting and interval propagation are explicitly outside this slice.
"""
from collections import defaultdict
from types import SimpleNamespace
import re
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.course_factories import timetable
from opentrack_ai.errors import APIError
SOURCE_SHA256 = {'timetable_editing.py': '32133a3b12915e779514edc51a8956b9213bc27499d625a584173f013aae632f', 'native_records.py': 'dc68123f6d3c95dd50e318c1ddfbb0a375832b9e9fc59f438ca62f80a539fd4b', 'course_lifecycle.py': 'cf7031877892fc31888354a74c350fd50a2f9f42bef2b14133db931316aec4c2', 'archive.py': 'a4ab02c67b5a13102c4ac5e468b87587be747dc9125530a76cf49526c7fbd89c'}


def clock(seconds):
    if not 0 <= seconds < 86400:
        raise APIError('TIME_OUT_OF_RANGE', 'This editor supports times within one day (00:00:00–23:59:59).')
    return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'

DAY_SECONDS = 86400

MAX_DAY = 366

def split_time(value):
    day, within = divmod(value, DAY_SECONDS)
    if not -MAX_DAY <= day <= MAX_DAY:
        raise APIError('DAY_OFFSET_RANGE', 'Generated times support day offsets -366 through 366.', day)
    return (int(day), clock(within))

def number(text):
    return float(text) if text else 0.0

def native_string(obj, value):
    sample = next((item for item in w.objects(obj) if w.kind(item) == 'NSString'))
    return w.ar.GenericArchivedObject(sample.clazz, None, [w.ar.TypedValue(b'+', value.encode('ascii'))])

def connection_record(obj):
    if w.kind(obj) != 'OTConnection' or len(obj.contents) < 4:
        raise APIError('CONNECTION_SCHEMA', 'Expected an audited original OTConnection record.')
    flags = obj.contents[4].value if len(obj.contents) > 4 else 0
    return {'course_id': w.string(obj.contents[0].value), 'target_course_id': w.string(obj.contents[1].value), 'station_sign': w.string(obj.contents[2].value), 'minimum_wait': w.string(obj.contents[3].value), 'maximum_wait': w.string(obj.contents[5].value) if len(obj.contents) > 5 and obj.contents[5].value is not None else 'HH:MM:SS', **({'maximum_wait_is_nil': True} if len(obj.contents) > 5 and obj.contents[5].value is None else {}), 'target_station_sign': w.string(obj.contents[6].value) if len(obj.contents) > 6 else w.string(obj.contents[2].value), 'join': bool(flags & 1), 'split': bool(flags & 2), 'entry_connection': bool(flags & 4), 'dispo_connection': bool(flags & 8), 'time_reference_type': obj.contents[7].value if len(obj.contents) > 7 else 0, 'dispatching_distance_km': obj.contents[8].value if len(obj.contents) > 8 else 0.0}

def timetable_record(key, obj):
    if w.kind(obj) != 'OTTimetable' or len(obj.contents) < 17:
        raise APIError('TIMETABLE_SCHEMA', 'Expected an audited original OTTimetable record.')
    days = obj.contents[15].values
    return {'key': key, 'course_id': w.string(obj.contents[1].value), 'index': obj.contents[3].value, 'last_index': obj.contents[4].value, 'station_sign': w.string(obj.contents[5].value), 'arrival': w.string(obj.contents[6].value), 'departure': w.string(obj.contents[7].value), 'arrival_day_offset': days[0], 'departure_day_offset': days[1], 'actual_arrival_day_offset': days[2], 'actual_departure_day_offset': days[3], 'actual_arrival': w.string(obj.contents[13].value), 'actual_departure': w.string(obj.contents[14].value), 'track_id': w.string(obj.contents[18].value) if len(obj.contents) > 18 else '', 'dwell_s': number(w.string(obj.contents[8].value)), 'stop_at_station': bool(obj.contents[10].value & 1), 'timing_station': bool(obj.contents[10].value & 2), 'interval_reference_course_id': w.string(obj.contents[2].value), 'interval_offset_s': obj.contents[11].value, 'mean_delay_s': number(w.string(obj.contents[12].value)), 'distribution_name': w.string(obj.contents[16].value), 'delta_mass_t': obj.contents[17].value if len(obj.contents) > 17 else 0.0, 'connections': [connection_record(c) for c in w.elements(obj.contents[9].value)]}

def string_slot(obj, index):
    if len(obj.contents) <= index or obj.contents[index].encodings != [b'@']:
        raise APIError('COURSE_REFERENCE_SCHEMA', 'Audited Course reference field is missing.', {'class': w.kind(obj), 'index': index})
    value = obj.contents[index].value
    if value is None:
        return ''
    if not isinstance(value, w.ar.GenericArchivedObject) or w.kind(value) != 'NSString':
        raise APIError('COURSE_REFERENCE_SCHEMA', 'Expected an original NSString Course reference.', {'class': w.kind(obj), 'index': index})
    return w.string(value)

def write_slot(obj, index, value):
    obj.contents[index].values[0] = native_string(obj, value)

def identity(row):
    return (string_slot(row, 1), row.contents[3].value)

def row_record(row):
    cid, index = identity(row)
    return timetable_record(cid + '#' + str(index), row)

def set_time(row, field, value):
    index = 6 if field == 'arrival' else 7
    day_index = 0 if field == 'arrival' else 1
    if value is None:
        day, text = (0, 'HH:MM:SS')
    else:
        if int(value) != value:
            raise APIError('TIMETABLE_SUBSECOND', 'An undefined-time interval propagation needs an integral offset at the saved HH:MM:SS resolution.', value)
        day, text = split_time(int(value))
    write_slot(row, index, text)
    row.contents[15].values[day_index] = day

class TimetableOperations:

    def __init__(self, operations):
        self.o = operations
        self.p = operations.p
        self.d = operations.d

    def load(self, check_indices=True):
        self.o.prepare_timetable()
        table = self.p.table()
        groups = defaultdict(list)
        for key, row in table.items():
            cid, index = identity(row)
            if key != cid + '#' + str(index):
                raise APIError('TIMETABLE_KEY', 'Saved timetable key differs from its Course/index.', key)
            groups[cid].append(row)
        for cid, rows in groups.items():
            rows.sort(key=lambda row: row.contents[3].value)
            if check_indices and any((row.contents[3].value != i or row.contents[4].value != len(rows) - 1 for i, row in enumerate(rows))):
                raise APIError('TIMETABLE_INDEX', 'Saved Course rows must have contiguous indices and a consistent last index.', cid)
        return (table, groups)

    def budget(self, rows, connections=0):
        self.o.requested_rows += rows
        self.o.requested_connections += connections
        if self.o.requested_rows > 10000 or self.o.requested_connections > 10000:
            raise APIError('GENERATION_SIZE', 'One draft supports at most 10000 requested timetable row targets and 10000 requested connections.')

    def select(self, args, groups):
        courses = {w.string(c.contents[0].value) for c in self.p.courses()}
        ids = args.course_ids if args.course_ids else list(dict.fromkeys((ref.course_id for ref in args.rows)))
        missing = [cid for cid in ids if cid not in courses]
        if missing:
            raise APIError('COURSE_NOT_FOUND', 'Selected timetable Courses do not exist.', missing[:50])
        if args.course_ids:
            result = [row for cid in args.course_ids for row in groups.get(cid, [])]
        else:
            lookup = {identity(row): row for rows in groups.values() for row in rows}
            missing = [(r.course_id, r.index) for r in args.rows if (r.course_id, r.index) not in lookup]
            if missing:
                raise APIError('TIMETABLE_ROW_NOT_FOUND', 'Selected Course/index rows do not exist.', missing[:50])
            result = [lookup[r.course_id, r.index] for r in args.rows]
        if not result:
            raise APIError('TIMETABLE_EMPTY_SELECTION', 'The selected Courses have no timetable rows.')
        return result

    def changes(self, before, rows):
        after = {identity(row): row_record(row) for row in rows}
        result = []
        for key in dict.fromkeys([*before, *after]):
            old = before.get(key)
            new = after.get(key)
            if old != new:
                result.append({'course_id': key[0], 'index': key[1], 'fields': {name: {'before': old.get(name) if old else None, 'after': new.get(name) if new else None} for name in sorted(set(old or {}) | set(new or {})) if (old or {}).get(name) != (new or {}).get(name)}})
        self.o.changed_timetables.update((key[0] for key in set(before) | set(after)))
        return {'rows_changed': len(result), 'timetable_changes': result, 'actual_data_scope': 'Saved fields only; native runtime validity flags are not serialized or inspected.'}

    def shift_timetable_rows(self, args):
        table, groups = self.load()
        selected = self.select(args, groups)
        targets = {id(row): row for source in selected for row in (self.family(source, table) if args.propagate_interval else [source])}
        self.budget(len(targets))
        before = {identity(row): row_record(row) for row in targets.values()}
        for row in targets.values():
            for field in ['arrival', 'departure']:
                value = time_value(row, field)
                if value is not None:
                    set_time(row, field, value + args.seconds)
        return {'rows_selected': len(selected), 'expanded_row_targets': len(targets), 'seconds': args.seconds, **self.changes(before, list(targets.values()))}


def time_value(row,field):
    
    
    slot=6 if field=='arrival' else 7
    obj=row.contents[slot].value
    day=row.contents[15].values[0 if field=='arrival' else 1]
    if type(day)is not int or not -MAX_DAY<=day<=MAX_DAY:
        raise APIError('DAY_OFFSET_RANGE','Shift business domain is -366..366 days.',day)
    value=None if obj is None else c.text(obj)
    if value in (None,'HH:MM:SS'):
        if day!=0:raise APIError('UNDEFINED_DAY_OFFSET','Undefined planned time requires zero day offset.',day)
        return None
    if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]',value):
        raise APIError('TIMETABLE_TIME','Defined planned time must be canonical HH:MM:SS.',value)
    h,m,s=map(int,value.split(':'));return day*DAY_SECONDS+h*3600+m*60+s

class _CatalogAccess:
    __slots__=('data',)
    def __init__(self,data):self.data=data
    def courses(self):return c.course_items(self.data['courses'])
    def table(self):return timetable(self.data['timetable'])

class _Operations:
    __slots__=('p','d','requested_rows','requested_connections','changed_timetables')
    def __init__(self,data):
        self.p=_CatalogAccess(data);self.d=None
        self.requested_rows=0;self.requested_connections=0;self.changed_timetables=set()
    def prepare_timetable(self):
        
        rows=self.p.table();self.p.courses()
        for row in rows.values():
            for connection in c.array(row.contents[9].value):
                c.shape(connection,'OTConnection',6,['@','@','@','@','i','@','@','i','f'])

def validate_spec(spec):
    if type(spec)is not dict or set(spec)-{'kind','course_ids','seconds','include_actual'}:
        raise APIError('BATCH_PARAMETERS','Unknown timetable shift parameter.')
    if spec.get('kind','shift_timetable_rows')!='shift_timetable_rows':
        raise APIError('BATCH_PARAMETERS','Wrong timetable operation kind.')
    ids=spec.get('course_ids');delta=spec.get('seconds')
    if type(ids)is not list or not ids or any(type(x)is not str or not x or x in ('0','-1') for x in ids) or len(ids)!=len(set(ids)):
        raise APIError('BATCH_PARAMETERS','Nonempty unique exact Course IDs required.')
    if type(delta)is not int or not -(2**31)<=delta<2**31:
        raise APIError('BATCH_PARAMETERS','seconds requires signed int32, including negative deltas.')
    if 'include_actual' in spec and spec['include_actual'] is not False:
        raise APIError('BATCH_PARAMETERS','Actual shifting is not exposed by this original planned-only method; include_actual must be omitted or false.')
    return SimpleNamespace(course_ids=ids,rows=[],seconds=delta,propagate_interval=False)

def apply(context,spec):
    args=validate_spec(spec);operations=_Operations(context.data)
    runner=TimetableOperations(operations)
    
    
    table,groups=runner.load();selected=runner.select(args,groups)
    for row in selected:
        for field in ('arrival','departure'):
            value=time_value(row,field)
            if value is not None:
                result=value+args.seconds
                if not -(2**31)<=result<2**31:raise APIError('TIMETABLE_OVERFLOW','Absolute shifted seconds exceed int32.')
                split_time(result)
    result=runner.shift_timetable_rows(args)
    result.update(actual_times_shifted=False,interval_propagation=False,run_window_modified=False,time_domain='signed int32 seconds; normalized day -366..366; nil/undefined preserved')
    return result

