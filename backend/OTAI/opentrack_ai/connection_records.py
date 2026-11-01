"""Audited connection data commands; JSON records only, never native execution."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import uuid
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


class RecordError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties, 'required': list(properties) if required is None else required, 'additionalProperties': False}


STR = {'type': 'string'}
ID = {'type': 'string', 'minLength': 1}
INDEX = {'type': 'integer', 'minimum': 0, 'maximum': 1000000}
NUM = {'type': 'number'}
BOOL = {'type': 'boolean'}
ROW_REF = obj({'course_id': STR, 'index': INDEX})
CONNECTION = obj({
    'course_id': STR, 'target_course_id': STR, 'station_sign': STR,
    'target_station_sign': STR, 'minimum_wait': STR, 'maximum_wait': STR,
    'maximum_wait_is_nil': BOOL, 'join': BOOL, 'split': BOOL,
    'entry_connection': BOOL, 'dispo_connection': BOOL,
    'time_reference_type': INDEX, 'dispatching_distance_km': NUM,
}, ['course_id','target_course_id','station_sign','target_station_sign','minimum_wait','maximum_wait','join','split','entry_connection','dispo_connection','time_reference_type','dispatching_distance_km'])
ROW = obj({'course_id': STR, 'index': INDEX, 'station_sign': STR,
           'connections': {'type': 'array', 'items': CONNECTION},
           'metadata': {'type': 'object'}}, ['course_id','index','station_sign','connections'])
STATE = obj({'format': {'const':'opentrack-connection-records-v1'},
             'revision': INDEX,
             'rows': {'type':'array','maxItems':100000,'items':ROW},
             'courses': {'type':'array','items':obj({'course_id':STR,'train':STR})},
             'formations': {'type':'array','items':obj({'name':STR,'category':STR})},
             'categories': {'type':'array','items':obj({'name':STR,'default_connection_time_s':NUM})},
             'metadata': {'type':'object'}}, ['format','revision','rows','courses','formations','categories'])
ACTIONS = ['insert','delete','turnround_to','turnround_from','add_start','add_end','join_at_station','split_at_station','split_at_end']
COMMAND = obj({'action': {'enum':ACTIONS}, 'row': ROW_REF,
               'target_course_id': {**ID,'not':{'enum':['0','-1']}}, 'connection_index': INDEX}, ['action','row'])
COMMAND['allOf'] = [
    {'if': {'properties':{'action':{'const':'delete'}}},
     'then': {'required':['connection_index'],'not':{'required':['target_course_id']}},
     'else': {'not':{'required':['connection_index']}}},
    {'if': {'properties':{'action':{'not':{'enum':['insert','delete']}}}},
     'then': {'required':['target_course_id']}}]
BATCH = {'type':'array','minItems':1,'maxItems':1000,'items':COMMAND}
APPLY_SCHEMA = obj({'state':STATE,'expected_version':ID,'commands':BATCH})


def validate(value, schema):
    try:
        
        json.dumps(value, allow_nan=False)
        Draft202012Validator(schema).validate(value)
    except (ValueError, TypeError, ValidationError) as exc:
        raise RecordError('SCHEMA', str(exc)) from exc


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def version(state):
    return hashlib.sha256(canonical(state)).hexdigest()


def check_state(state):
    validate(state, STATE)
    seen = set()
    for row in state['rows']:
        key = (row['course_id'], row['index'])
        if key in seen: raise RecordError('DUPLICATE_ROW', str(key))
        seen.add(key)
    for collection, key in [('courses','course_id'),('formations','name'),('categories','name')]:
        names = [x[key] for x in state[collection]]
        if len(names) != len(set(names)): raise RecordError('AMBIGUOUS_ID', collection)


def native_wait_string(value):
    try:
        value = struct.unpack('f', struct.pack('f', value))[0]
        if not math.isfinite(value): raise ValueError('nonfinite')
        if value < 0: return 'HH:MM:SS'
        value = struct.unpack('f', struct.pack('f', math.fmod(value, 86400)))[0]
        seconds = math.trunc(value) % 86400
        return f'{seconds//3600:02d}:{seconds//60%60:02d}:{seconds%60:02d}'
    except (OverflowError, ValueError, struct.error) as exc:
        raise RecordError('CONNECTION_DEFAULT_TIME','Category time cannot be represented as finite float32') from exc


def apply_commands(state, commands, expected_version):
    validate({'state':state,'commands':commands,'expected_version':expected_version}, APPLY_SCHEMA)
    check_state(state)
    if version(state) != expected_version: raise RecordError('STALE_VERSION','State changed')
    draft = deepcopy(state)
    lookup = {(r['course_id'],r['index']):r for r in draft['rows']}
    groups = {}
    for r in draft['rows']: groups.setdefault(r['course_id'], []).append(r)
    for rows in groups.values(): rows.sort(key=lambda r:r['index'])
    created = deleted = 0
    actions = []

    def wait(cid):
        course = next((c for c in draft['courses'] if c['course_id']==cid), None)
        train = next((t for t in draft['formations'] if course and t['name']==course['train']), None)
        cat = next((c for c in draft['categories'] if train and c['name']==train['category']), None)
        return native_wait_string(cat['default_connection_time_s']) if cat else '00:07:00'

    def find(row, target):
        return next(((c,i) for i,c in enumerate(row['connections']) if c['target_course_id']==target),(None,None))

    def shell(row):
        nonlocal created
        c = {'course_id':'0','target_course_id':'0','station_sign':'', 'target_station_sign':'',
             'minimum_wait':'','maximum_wait':'HH:MM:SS','join':False,'split':False,
             'entry_connection':False,'dispo_connection':False,'time_reference_type':0,'dispatching_distance_km':0.0}
        index = len(row['connections']); row['connections'].append(c); created += 1
        return c,index

    def finish(c,row,target,nil=False):
        c.update(course_id=row['course_id'],target_course_id=target,station_sign=row['station_sign'],
                 target_station_sign=row['station_sign'],minimum_wait=wait(row['course_id']),maximum_wait='HH:MM:SS')
        if nil: c['maximum_wait_is_nil']=True
        else: c.pop('maximum_wait_is_nil',None)

    def helper(row,target,style):
        c,index = find(row,target); new = c is None
        if new: c,index=shell(row); finish(c,row,target,style=='start')
        if style=='join': c['join']=True
        if style in ['split','split_end']: c['split']=True
        return c,index,new

    for number,cmd in enumerate(commands):
        key=(cmd['row']['course_id'],cmd['row']['index']); row=lookup.get(key)
        if row is None: raise RecordError('TIMETABLE_ROW_NOT_FOUND',str(key))
        action=cmd['action']; target=cmd.get('target_course_id','0'); rows=groups[key[0]]
        if action in ['insert','turnround_to','turnround_from'] and key[0] in ['','0','-1']:
            raise RecordError('COURSE_RESERVED_ID',key[0])
        if action in ['turnround_to','add_end','split_at_end']: row=rows[-1]
        elif action in ['turnround_from','add_start']: row=rows[0]
        elif action in ['join_at_station','split_at_station']:
            row=next(r for r in rows if r['station_sign']==row['station_sign'])
        if action!='delete' and not row['station_sign']: raise RecordError('TIMETABLE_STATION','Empty station')
        
        if action!='delete' and target!='0' and action not in ['turnround_to','turnround_from'] and not any(c['course_id']==target for c in draft['courses']):
            raise RecordError('CONNECTION_COURSE','Missing exact target Course: '+target)
        item={'command_index':number,'action':action,'selected_row':list(key),'effective_row':[row['course_id'],row['index']]}
        if action=='delete':
            index=cmd['connection_index']
            if index>=len(row['connections']): raise RecordError('CONNECTION_INDEX','Delete index outside array')
            row['connections'].pop(index); deleted+=1; item.update(connection_index=index,deleted=True)
        elif action in ['turnround_to','turnround_from']:
            targets=groups.get(target,[]); station=row['station_sign']
            if not targets: raise RecordError('CONNECTION_TARGET_TIMETABLE',target)
            matches=[r for r in targets if r['station_sign']==station]
            if not matches: raise RecordError('CONNECTION_TARGET_STATION',station)
            if not any(c['course_id']==target for c in draft['courses']): raise RecordError('CONNECTION_COURSE',target)
            c,index=find(row,target); new=c is None
            if new: c,index=shell(row)
            c.update(station_sign=station,target_station_sign=station,entry_connection=False,dispo_connection=False)
            if action=='turnround_to':
                starts=targets[0]['station_sign']==station
                counter=targets[0] if starts else matches[0]; style='start' if starts else 'join'
                join,split=not starts,starts
            else:
                ends=targets[-1]['station_sign']==station
                counter=targets[-1] if ends else matches[0]; style='split_end' if ends else 'split'
                join=split=False
            _,ci,cn=helper(counter,row['course_id'],style)
            c.update(join=join,split=split)
            if new: finish(c,row,target)
            item.update(connection_index=index,created=new,counterpart={'row':[counter['course_id'],counter['index']],'connection_index':ci,'created':cn,'style':style})
        else:
            style={'add_start':'start','add_end':'end','join_at_station':'join','split_at_station':'split','split_at_end':'split_end'}.get(action,'insert')
            _,index,new=helper(row,target,style); item.update(connection_index=index,created=new)
        actions.append(item)
    diffs=[{'row':[b['course_id'],b['index']],'before':deepcopy(b),'after':deepcopy(a)} for b,a in zip(state['rows'],draft['rows']) if a!=b]
    draft['revision']+=1
    check_state(draft)
    after_version=version(draft)
    receipt={'before':deepcopy(state),'before_version':expected_version,'after_version':after_version}
    return {'state':draft,'version':after_version,'undo':receipt,'diff':diffs,'actions':actions,
            'preview':actions[:10],'preview_truncated':len(actions)>10,'connections_created':created,'connections_deleted':deleted,
            'pending_connection_count':sum(c['target_course_id']=='0' for r in draft['rows'] for c in r['connections']),
            'native_verified':False,'scope':'JSON connection records only; no scheduling, native archive or simulation verification.'}


def undo(state, receipt, expected_version):
    check_state(state)
    if expected_version!=version(state) or receipt['after_version']!=expected_version:
        raise RecordError('STALE_VERSION','Undo belongs to another state version')
    check_state(receipt['before'])
    if version(receipt['before'])!=receipt['before_version']: raise RecordError('UNDO_INTEGRITY','Snapshot changed')
    result=deepcopy(receipt['before']); result['revision']=state['revision']+1
    
    
    check_state(result)
    return result


def save_state(state, path):
    """Atomic JSON replace; trusted server path, deliberately not exposed as an MCP path tool."""
    check_state(state); path=Path(path); payload=canonical(state)
    fd,tmp=tempfile.mkstemp(prefix='.connection-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def load_state(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise RecordError('JSON_DUPLICATE_KEY',key)
            result[key]=value
        return result
    state=json.loads(Path(path).read_text('utf-8'),object_pairs_hook=unique)
    check_state(state); return state


class ConnectionRecordTools:
    """Host hook with server-held undo snapshots; independent of shared registry."""
    def __init__(self): self.receipts={}

    def inspect(self, state):
        validate({"state":state},INSPECT_SCHEMA)
        check_state(state)
        return {"version":version(state), "revision":state["revision"],
                "rows":len(state["rows"]),
                "connections":sum(len(r["connections"]) for r in state["rows"]),
                "pending_connection_count":sum(c["target_course_id"]=="0" for r in state["rows"] for c in r["connections"]),
                "native_verified":False,"scope":"JSON structural validation only, not operational validity."}

    def apply(self, state, expected_version, commands):
        result=apply_commands(state,commands,expected_version)
        token=str(uuid.uuid4()); self.receipts[token]=result.pop('undo'); result['undo_token']=token
        return result

    def undo(self, state, expected_version, undo_token):
        validate({'state':state,'expected_version':expected_version,'undo_token':undo_token},UNDO_SCHEMA)
        if undo_token not in self.receipts: raise RecordError('UNDO_TOKEN','Unknown or already used token')
        restored=undo(state,self.receipts[undo_token],expected_version)
        del self.receipts[undo_token]
        return {'state':restored,'version':version(restored),'native_verified':False}

    def register(self, register_tool):
        """register_tool(name, input_schema, handler); host supplies real transport."""
        register_tool('opentrack_inspect_connection_records',deepcopy(INSPECT_SCHEMA),self.inspect)
        register_tool('opentrack_apply_connection_records',deepcopy(APPLY_SCHEMA),self.apply)
        register_tool('opentrack_undo_connection_records',deepcopy(UNDO_SCHEMA),self.undo)


UNDO_SCHEMA=obj({'state':STATE,'expected_version':ID,'undo_token':ID})

INSPECT_SCHEMA=obj({"state":STATE})
