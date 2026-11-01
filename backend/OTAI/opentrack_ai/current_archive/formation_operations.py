"""Current archive formation operations. Caller owns same-project resolution and atomic IO.
No native process, migration, graph alias splitting, or physical recomputation.
"""
import hashlib
from opentrack_ai.current_archive import writer as w, catalogs as c

class FormationError(ValueError): pass

def integer(value):
    if type(value) is not int or not -(2**31)<=value<2**31:
        raise FormationError('Signed int32 required; bool/coercion forbidden')
    return value

def trailer(obj):
    
    if w.kind(obj)!='OTTrailer' or obj.clazz.version!=3:
        raise FormationError('Only current OTTrailer v3 is supported')
    parent=obj.clazz.superclass
    if parent is None or parent.name!=b'OTVehicle' or parent.version!=0:
        raise FormationError('Unsupported trailer superclass')
    parent=parent.superclass
    if parent is None or parent.name!=b'NSObject' or parent.version!=0 or parent.superclass is not None:
        raise FormationError('Unsupported trailer ancestry')
    expected=['i','@','iiifif','iii','i','f','f']
    if len(obj.contents)!=len(expected) or any(g.encodings!=[bytes([b]) for b in e.encode()] or len(g.values)!=len(e) for g,e in zip(obj.contents,expected)):
        raise FormationError('Unsupported trailer fields')
    c.text(obj.contents[1].value)
    return obj

def state(blob,name):
    if type(blob) is not bytes:raise FormationError('Immutable bytes required')
    root,version=w.load_next_compatible(blob)
    trains=c.train_items(root)
    selected=[t for t in trains if c.text(t.contents[0].value)==name]
    if len(selected)!=1:raise FormationError('Exact unique Train name required')
    train=selected[0]; engines=c.array(train.contents[2].values[1]); trailers=c.array(train.contents[2].values[2])
    for x in engines:c.record(x,'OTTrainEngine');c.text(x.contents[0].value);integer(x.contents[1].value)
    for x in trailers:trailer(x);integer(x.contents[3].values[1])
    return root,version,train,engines,trailers

def occurrences(root,target):
    from .graph_references import incoming
    return incoming(root,target)


def exclusive(root,train,records=(),arrays=(1,)):
    for obj in [train,*[train.contents[2].values[i] for i in arrays],*records]:
        if occurrences(root,obj)!=1:raise FormationError('Shared record, Train or parent array: independent edit refused')

def position(record):return record.contents[1].value if w.kind(record)=='OTTrainEngine' else record.contents[3].values[1]
def posgroup(record):return 1 if w.kind(record)=='OTTrainEngine' else 3

def snapshot(root):
    
    def val(v):
        if isinstance(v,w.GenericArchivedObject):return ('object',id(v))
        if isinstance(v,w.Array):return ('array',v.elements if isinstance(v.elements,bytes) else tuple(val(a) for a in v.elements))
        if isinstance(v,w.GenericStruct):return ('struct',v.name,tuple(val(a) for a in v.fields))
        if isinstance(v,w.WireFloat):return ('wirefloat',v.bits,v.encoding,v.byte_order)
        if isinstance(v,w.SharedString):return ('string',v.data)
        if isinstance(v,w.CString):return ('cstring',v.token.data)
        return (type(v).__name__,repr(v))
    return {(id(o),i):(tuple(g.encodings),tuple(val(v) for v in g.values)) for o in w.objects(root) for i,g in enumerate(o.contents)}

def finish(root,version,before,allowed,report,removed=()):
    after=snapshot(root)
    for key,value in before.items():
        if key[0] not in removed and key not in allowed and after.get(key)!=value:
            raise FormationError('Unrelated field/reference changed')
    output=w.dump_verified(root,version)
    fresh,_=w.load_next_compatible(output)
    if w.fingerprint(fresh)!=w.fingerprint(root):raise FormationError('Fresh-reader graph mismatch')
    return output,{**report,'fresh_reload_verified':True,'unrelated_fields_and_references_preserved':True,
        'native_application_tested':False,'physical_recomputation':False}

def set_engine_position_archive(blob,train_name,engine_reference_index,position_value):
    """Exact 0x6d7f80 int32 setter, NOT a safe permutation/reorder operation."""
    value=integer(position_value);index=integer(engine_reference_index)
    root,v,train,engines,trailers=state(blob,train_name)
    if not 0<=index<len(engines):raise FormationError('Zero-based engine ordinal outside array')
    chosen=engines[index];exclusive(root,train,[chosen]);before=snapshot(root);old=position(chosen)
    chosen.contents[1].value=value
    return finish(root,v,before,{(id(chosen),1)}, {'operation':'raw_set_engine_position','setter':'0x6d7f80',
        'before':old,'after':value,'engine_reference_index':index,'array_order_preserved':True,
        'policy':'raw int32; duplicates/gaps/negative positions are not normalized'})

def add_engine_archive(blob,engine_blob,train_name,engine_name,position_value=None,policy='contiguous'):
    """0x6bb418 append; omitted pos follows 0x6bb3e8. Catalog must be same project.
    contiguous is an API safety restriction, NOT a restriction of original C.
    native policy exposes original int32 position without insertion/reordering.
    """
    if policy not in ('contiguous','native'):raise FormationError('Unknown position policy')
    if type(engine_blob) is not bytes:raise FormationError('Immutable Engine catalog required')
    er,_=w.load_next_compatible(engine_blob)
    catalog={c.text(e.contents[1].value):e for e in c.engine_items(er)}
    if type(engine_name) is not str or engine_name not in catalog:raise FormationError('Exact Engine name missing from supplied catalog')
    root,v,train,engines,trailers=state(blob,train_name);exclusive(root,train)
    n=len(engines)+len(trailers);value=integer(n+1 if position_value is None else position_value)
    if policy=='contiguous' and (sorted(position(r) for r in engines+trailers)!=list(range(1,n+1)) or value!=n+1):
        raise FormationError('Safe append requires existing complete unique 1..N and new N+1; use explicit native policy for raw semantics')
    before=snapshot(root);arr=train.contents[2].values[1]
    ns=w.Class(b'NSObject',0);refclass=w.Class(b'OTTrainEngine',0,ns)
    name=w.GenericArchivedObject(w.Class(b'NSString',1,ns),None,[w.TypedValue(b'+',engine_name.encode('utf8'))])
    ref=w.GenericArchivedObject(refclass,None,[w.TypedValue(b'@',name),w.TypedValue(b'i',value)])
    c.record(ref,'OTTrainEngine');w.set_elements(arr,engines+[ref])
    return finish(root,v,before,{key for key in before if key[0]==id(arr)},
        {'operation':'append_engine','setter':'0x6bb418','default_position_function':'0x6bb3e8',
         'engine_reference_index':len(engines),'position':value,'engine_name':engine_name,'policy':policy,
         'engine_catalog_sha256':hashlib.sha256(engine_blob).hexdigest(),'existing_positions_preserved':True})

def remove_engine_archive(blob,train_name,engine_reference_index):
    """0x6bb484 then 0x6bba44, conservative exclusive-record boundary."""
    index=integer(engine_reference_index);root,v,train,engines,trailers=state(blob,train_name)
    if not 0<=index<len(engines):raise FormationError('Zero-based engine ordinal outside array')
    exclusive(root,train,engines+trailers,arrays=(1,2))
    before=snapshot(root);removed=engines[index];old=position(removed);arr=train.contents[2].values[1]
    allowed={key for key in before if key[0]==id(arr)};shifts=[]
    
    for ref in engines[:index]+engines[index+1:]+trailers:
        if position(ref)>old:shifts.append((ref,integer(position(ref)-1)))
    w.set_elements(arr,engines[:index]+engines[index+1:])
    for ref,value in shifts:
        group=posgroup(ref);slot=0 if w.kind(ref)=='OTTrainEngine' else 1
        ref.contents[group].values[slot]=value;allowed.add((id(ref),group))
    
    live={id(o) for o in w.objects(root)};gone={key[0] for key in before if key[0] not in live}
    return finish(root,v,before,allowed,{'operation':'remove_engine','setter':'0x6bb484','shift_function':'0x6bba44',
        'engine_reference_index':index,'removed_position':old,'shifted_records':len(shifts),
        'remaining_array_order_preserved':True},removed=gone)
