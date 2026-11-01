"""Seven audited Engine2/Category19 raw scalar pairs, immutable bytes in/out; no simulator."""
import math
import struct
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.graph_references import reference_inventory
from opentrack_ai.json_safe import checked_json


FIELDS = {'resistFactor': (4, 0, 'f', '004cbd90', '004cb444'), 'adhesion': (5, 0, 'i', '004cbdd0', '004cb478'), 'dispatchingType': (11, 0, 'i', '006c429c', '006c4290'), 'timingStationsType': (16, 0, 'i', '006c4458', '006c444c'), 'initialDelayDistributionFunction': (9, 0, 'i', '006c44e0', '006c44d4'), 'trackNameCreationType': (23, 0, 'i', '006c4590', '006c4584'), 'delayAddType': (19, 0, 'i', '006c48c0', '006c48b4')}
KINDS = {'resistFactor': 'OTEngine', 'adhesion': 'OTEngine', 'dispatchingType': 'OTTrainCategory', 'timingStationsType': 'OTTrainCategory', 'initialDelayDistributionFunction': 'OTTrainCategory', 'trackNameCreationType': 'OTTrainCategory', 'delayAddType': 'OTTrainCategory'}
class ScalarFieldError(ValueError): pass

def normalize(field, value):
    if type(field) is not str or field not in FIELDS:
        raise ScalarFieldError('Field outside explicit Engine2/Category19 allowlist')
    if FIELDS[field][2] == 'i':
        if type(value) is not int or not -(2**31) <= value < 2**31:
            raise ScalarFieldError('Exact signed int32 required; not enum validation')
        return value
    if type(value) not in (int,float):
        raise ScalarFieldError('Exact int/float required; bool/subclasses/coercion forbidden')
    try:
        f=float(value)
        if not math.isfinite(f):raise ScalarFieldError('Only finite binary32 API domain')
        f=struct.unpack('<f',struct.pack('<f',f))[0]
    except (OverflowError,struct.error) as e:
        raise ScalarFieldError('Binary32 overflow') from e
    if not math.isfinite(f):raise ScalarFieldError('Binary32 overflow')
    return f

def inspect(root, kind, name):
    if type(kind) is not str or kind not in ('OTEngine','OTTrainCategory'):
        raise ScalarFieldError('Explicit OTEngine or OTTrainCategory required')
    if type(name) is not str or not name or '\0' in name:
        raise ScalarFieldError('Exact nonempty NUL-free name required')
    objects, counts=reference_inventory(root)
    if kind=='OTEngine':
        rows=c.engine_items(root)
        selected=next((o for o in rows if c.text(o.contents[1].value)==name),None)
        parent=root
    else:
        from opentrack_ai.current_archive.category_dwell import select
        selected=select(root,name)
        parent=root.contents[1].value
    if selected is None:raise ScalarFieldError('Selected object not found')
    for obj,expected,label in ((root,0,'root'),(selected,1,'selected object')):
        if counts[id(obj)]!=expected:raise ScalarFieldError('Shared '+label+' cannot be edited independently')
    if parent is not root and counts[id(parent)]!=1:
        raise ScalarFieldError('Shared parent cannot be edited independently')
    return selected

def read_fields(blob, kind, name, fields):
    """Exact requested raw getters; duplicates/unknown fields rejected."""
    if type(blob) is not bytes:raise ScalarFieldError('Immutable bytes required')
    if type(fields) not in (list,tuple) or not fields:raise ScalarFieldError('Nonempty explicit field list required')
    seen=set()
    for field in fields:
        if type(field) is not str or field not in FIELDS or KINDS[field]!=kind or field in seen:
            raise ScalarFieldError('Unknown or repeated field')
        seen.add(field)
    root,_=w.load_next_compatible(blob);target=inspect(root,kind,name)
    return checked_json({f:target.contents[FIELDS[f][0]].values[FIELDS[f][1]] for f in fields})

def patch_fields(blob, kind, name, changes):
    """Transactional small batch. Accept dict or list/tuple of (field,value).

    No callbacks/coercion, globals holding graphs, filesystem writes or caller
    graph mutation. Each call decodes a private graph, so re-entry is isolated.
    """
    if type(blob) is not bytes:raise ScalarFieldError('Immutable bytes required')
    if type(changes) is dict:pairs=list(changes.items())
    elif type(changes) in (list,tuple):pairs=changes
    else:raise ScalarFieldError('Explicit dict or field/value pairs required')
    if not pairs or len(pairs)>len(FIELDS):raise ScalarFieldError('Batch size must be 1..7')
    values={}
    for pair in pairs:
        if type(pair) not in (tuple,list) or len(pair)!=2:raise ScalarFieldError('Malformed pair')
        field,value=pair
        normalized=normalize(field,value)
        if KINDS[field]!=kind:raise ScalarFieldError("Field belongs to other class")
        if field in values:raise ScalarFieldError('Repeated field')
        values[field]=normalized
    root,version=w.load_next_compatible(blob);target=inspect(root,kind,name)
    before_fingerprint=w.fingerprint(root);old={};report=[]
    for field,value in values.items():
        g,s,e,setter,getter=FIELDS[field];old[field]=target.contents[g].values[s]
        target.contents[g].values[s]=value
        report.append({'field':field,'group':g,'slot':s,'encoding':e,'setter':'F-'+setter,'getter':'F-'+getter,'before':old[field],'after':value})
    output=w.dump_verified(root,version)
    fresh,_=w.load_next_compatible(output);actual=inspect(fresh,kind,name)
    for field,value in values.items():
        g,s,e,_,_=FIELDS[field];got=actual.contents[g].values[s]
        if (struct.pack('<f',got)!=struct.pack('<f',value)) if e=='f' else (got!=value):
            raise ScalarFieldError('Fresh value verification failed')
        actual.contents[g].values[s]=old[field]
    if w.fingerprint(fresh)!=before_fingerprint:
        raise ScalarFieldError('Unselected data/reference topology changed')
    return output, checked_json({'class':kind,'version':2 if kind=='OTEngine' else 19,'name':name,'changes':report,
        'fresh_reload_verified':True,'unselected_graph_verified':True,
        'native_application_tested':False,'physical_validation':False,'units':'raw; no unit inference','integer_semantics':'raw_native_code; no business enum validation'})
