"""Strict .run TrainType records. Pure bytes: never write application preferences.

Native readPreferencesFromRunFile 0x5784c8 replaces the in-memory ordered list
when the first TrainType record is encountered. Course names are resolved by
case-insensitive lookup, not by parsing an integer or assuming fallback index 0.
"""
import hashlib

class SpeedPreferencesError(ValueError): pass

def need(ok,msg):
    if not ok: raise SpeedPreferencesError(msg)

NATIVE_RUN_KEYS = ('Adhesion Outside', 'Adhesion Tunnel', 'Break Day Offset', 'Break Time', 'Communication Period', 'CourseFile', 'Delay Format', 'Delay Scenario', 'DepotFile', 'DestInfoFile', 'Incident', 'Infrastructure Document', 'Keep Occupations', 'Label Size', 'Mean Delay', 'Multithreaded', 'Optimization Period', 'Optimize Dispatching', 'Optimize Train Sequence', 'Output Acc./Distance', 'Output Acc./Time', 'Output Distance/Time', 'Output Distance/Time Rev. Dir.', 'Output Speed/Distance', 'Output Speed/Distance Rev. Dir.', 'Output Speed/Time', 'Output Timetable (Text)', 'Output Train Diagram', 'OutputPath', 'Performance', 'Safety Margin', 'Show Current Time', 'Show Instruments', 'Show Messages', 'Show Train', 'Show Train Delay', 'Show Train Descr.', 'Show Train ID', 'Start Day Offset', 'Start Time', 'StationFile', 'Step', 'Stop Day Offset', 'Stop Time', 'Time Ratio', 'TimetableFile', 'Train Diagram Document', 'TrainFile', 'TrainType', 'Use Curve Resistance', 'Use Switch Time and Route Res. Time')

def _name(value):
    need(type(value) is str and 0<len(value)<=200,'Bounded explicit train-type name required')
    need(value==value.strip() and all(32<=ord(c)<127 for c in value) and '#' not in value,'Printable ASCII, no separator or edge whitespace required')
    
    need(not any(k.lower() in value.lower() for k in NATIVE_RUN_KEYS),'Train-type name collides with native run-file keyword')
    return value

def _names(values):
    need(type(values) is list and 1<=len(values)<=100,'1..100 ordered train-type names required')
    for value in values:_name(value)
    need(len({x.upper() for x in values})==len(values),'Case-insensitive duplicate train type')
    return values

def _records(blob, require_present=True):
    need(type(blob) is bytes and len(blob)<=1048576,'Immutable run bytes <=1MiB required')
    need(b'\0' not in blob,'NUL bytes would truncate native parser')
    lines=blob.splitlines(keepends=True);rows=[];names=[]
    for i,line in enumerate(lines):
        need(len(line)<=1023,'Line can be split by native fgets(1024)')
        body=line[:-2] if line.endswith(b'\r\n') else line[:-1] if line.endswith(b'\n') else line
        need(b'\r' not in body and b'\n' not in body,'Bare CR or embedded newline unsupported')
        if body.startswith(b'//'):continue
        if b'TrainType' not in body:continue
        parts=body.split(b'#')
        need(len(parts)==3 and parts[0]==b'TrainType' and parts[2]==b'','Ambiguous/noncanonical TrainType record')
        try:value=parts[1].decode('ascii')
        except UnicodeDecodeError as e:raise SpeedPreferencesError('ASCII names only in verified parser domain') from e
        _name(value);names.append(value);rows.append(i)
    if names:_names(names)
    elif require_present:raise SpeedPreferencesError('No explicit TrainType mapping; refusing application-global fallback')
    return lines,rows,names

def read_train_types(blob):
    """Ordered names. Index in this list is the key used by native Edge speed tables."""
    return _records(blob)[2]

def index_for_course(blob, course_speed_type):
    _name(course_speed_type)
    names=read_train_types(blob)
    matches=[i for i,value in enumerate(names) if value.upper()==course_speed_type.upper()]
    need(len(matches)==1,'Course speed type missing; native fallback0 is not accepted')
    return matches[0]

def replace_train_types(blob, names):
    """Return replacement run bytes + receipt; every non-TrainType line byte preserved.

    This edits a requested .run configuration, never the application-global .pref
    file, and does not execute or activate the resulting configuration.
    """
    _names(names);lines,rows,old=_records(blob,False)
    if not rows:need(not blob or blob.endswith(b'\n'),'Insertion needs empty file or terminal newline to preserve other bytes')
    sample=lines[rows[0]] if rows else next((x for x in lines if x.endswith(b'\n')),b'\n')
    newline=b'\r\n' if sample.endswith(b'\r\n') else b'\n'
    block=b''.join(b'TrainType#'+n.encode('ascii')+b'#'+newline for n in names)
    if rows:
        selected=set(rows);new=[]
        for i,line in enumerate(lines):
            if i==rows[0]:new.append(block)
            if i not in selected:new.append(line)
        output=b''.join(new)
    else:output=blob+block
    need(read_train_types(output)==names,'Readback mapping mismatch')
    newlines,newrows,_=_records(output)
    oldother=b''.join(x for i,x in enumerate(lines) if i not in set(rows))
    newother=b''.join(x for i,x in enumerate(newlines) if i not in set(newrows))
    need(oldother==newother,'Non-target bytes changed')
    return output,{'operation':'replace_run_train_type_mapping','before':old,'after':names,'source_sha256':hashlib.sha256(blob).hexdigest(),'output_sha256':hashlib.sha256(output).hexdigest(),'non_target_bytes_preserved':True,'native_loader':'0x5784c8','native_name_to_index':'0x5799ac','application_preferences_file_modified':False,'native_application_executed':False}
