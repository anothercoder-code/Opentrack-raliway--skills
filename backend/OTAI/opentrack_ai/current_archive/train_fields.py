"""Ten audited Train16 raw scalar pairs, immutable bytes in/out; no simulator."""
import math
import struct
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.graph_references import reference_inventory
from opentrack_ai.json_safe import checked_json


FIELDS = {
 'trainType': (1,0,'i','006bb378','006bb184'),
 'avgDeceleration': (1,2,'f','006c13f4','006c1404'),
 'maxDrawbarForce_kN': (14,0,'f','006c1478','006c142c'),
 'decelerationUsedFormula': (12,0,'i','006c167c','006c1670'),
 'brakedWeightPercentage': (12,1,'f','006c1744','006c1738'),
 'decelerationFunctionParameterC1': (13,0,'f','006c1760','006c1754'),
 'decelerationFunctionParameterC2': (13,1,'f','006c177c','006c1770'),
 'brakingDelayType': (17,0,'i','006c1d30','006c1d24'),
 'startingRollingResistanceOffsetSpeed_kmh': (21,1,'f','006c15cc','006c15c0'),
 'startingRollingResistanceFactor_Nt': (21,2,'f','006c160c','006c1600'),
}
class TrainFieldError(ValueError): pass

def normalize(field, value):
    if type(field) is not str or field not in FIELDS:
        raise TrainFieldError('Field outside explicit Train16 allowlist')
    if FIELDS[field][2] == 'i':
        if type(value) is not int or not -(2**31) <= value < 2**31:
            raise TrainFieldError('Exact signed int32 required; not enum validation')
        return value
    if type(value) not in (int,float):
        raise TrainFieldError('Exact int/float required; bool/subclasses/coercion forbidden')
    try:
        f=float(value)
        if not math.isfinite(f):raise TrainFieldError('Only finite binary32 API domain')
        f=struct.unpack('<f',struct.pack('<f',f))[0]
    except (OverflowError,struct.error) as e:
        raise TrainFieldError('Binary32 overflow') from e
    if not math.isfinite(f):raise TrainFieldError('Binary32 overflow')
    return f

def inspect(root, name):
    if type(name) is not str or not name:raise TrainFieldError('Exact nonempty Train name required')
    
    objects, counts=reference_inventory(root)
    trains=c.train_items(root)
    selected=next((t for t in trains if c.text(t.contents[0].value)==name),None)
    if selected is None:raise TrainFieldError('Train not found')
    parent=root.contents[3].value
    for obj,expected,label in ((root,0,'root'),(parent,1,'Train parent array'),(selected,1,'Train')):
        if counts[id(obj)]!=expected:raise TrainFieldError('Shared '+label+' cannot be edited independently')
    return selected

def read_fields(blob, name, fields):
    """Exact requested raw getters; duplicates/unknown fields rejected."""
    if type(blob) is not bytes:raise TrainFieldError('Immutable bytes required')
    if type(fields) not in (list,tuple) or not fields:raise TrainFieldError('Nonempty explicit field list required')
    seen=set()
    for field in fields:
        if type(field) is not str or field not in FIELDS or field in seen:
            raise TrainFieldError('Unknown or repeated field')
        seen.add(field)
    root,_=w.load_next_compatible(blob);target=inspect(root,name)
    return checked_json({f:target.contents[FIELDS[f][0]].values[FIELDS[f][1]] for f in fields})

def patch_fields(blob, name, changes):
    """Transactional small batch. Accept dict or list/tuple of (field,value).

    No callbacks/coercion, globals holding graphs, filesystem writes or caller
    graph mutation. Each call decodes a private graph, so re-entry is isolated.
    """
    if type(blob) is not bytes:raise TrainFieldError('Immutable bytes required')
    if type(changes) is dict:pairs=list(changes.items())
    elif type(changes) in (list,tuple):pairs=changes
    else:raise TrainFieldError('Explicit dict or field/value pairs required')
    if not pairs or len(pairs)>len(FIELDS):raise TrainFieldError('Batch size must be 1..10')
    values={}
    for pair in pairs:
        if type(pair) not in (tuple,list) or len(pair)!=2:raise TrainFieldError('Malformed pair')
        field,value=pair
        normalized=normalize(field,value)
        if field in values:raise TrainFieldError('Repeated field')
        values[field]=normalized
    root,version=w.load_next_compatible(blob);target=inspect(root,name)
    before_fingerprint=w.fingerprint(root);old={};report=[]
    for field,value in values.items():
        g,s,e,setter,getter=FIELDS[field];old[field]=target.contents[g].values[s]
        target.contents[g].values[s]=value
        report.append({'field':field,'group':g,'slot':s,'encoding':e,'setter':'F-'+setter,'getter':'F-'+getter,'before':old[field],'after':value})
    output=w.dump_verified(root,version)
    fresh,_=w.load_next_compatible(output);actual=inspect(fresh,name)
    for field,value in values.items():
        g,s,e,_,_=FIELDS[field];got=actual.contents[g].values[s]
        if (struct.pack('<f',got)!=struct.pack('<f',value)) if e=='f' else (got!=value):
            raise TrainFieldError('Fresh value verification failed')
        actual.contents[g].values[s]=old[field]
    if w.fingerprint(fresh)!=before_fingerprint:
        raise TrainFieldError('Unselected data/reference topology changed')
    return output, checked_json({'class':'OTTrain','version':16,'name':name,'changes':report,
        'fresh_reload_verified':True,'unselected_graph_verified':True,
        'native_application_tested':False,'physical_validation':False,'units':'raw; no unit inference'})
