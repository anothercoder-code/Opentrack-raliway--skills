"""Six current stock setters on genuine typedstream graphs; no runtime physics.

Integration draft: caller owns filesystem scope, expected hash and atomic publish.
This module accepts immutable archive bytes and returns newly verified bytes.
"""
import math
import struct
from opentrack_ai.current_archive import writer as w
from opentrack_ai.current_archive import catalogs as c

CATEGORY_LAYOUT=['ii','@','@','ii','fff','f','f','fff','f','i','@','i','@','@','@','f','i','@','ffii','i','f','f','i','i','ff']

FIELDS={
 'maximum_acceleration_mps2':('OTTrain',16,4,0,'f','006c1410','m/s^2','identity'),
 'braking_delay_s':('OTTrain',16,16,0,'f','006c1c90','s','identity'),
 'braking_release_speed_kmh':('OTTrain',16,16,1,'f','006c1d14','km/h','identity'),
 'default_connection_time_s':('OTTrainCategory',19,20,0,'f','006c49f0','s','identity'),
 'departure_process_time_s':('OTTrainCategory',19,21,0,'f','006c4604','s','clamp_zero'),
 'departure_process_starts_at_departure_time':('OTTrainCategory',19,22,0,'i','006c45b0',None,'inverse_bool'),
}

class StockError(ValueError):pass

def value_for(field,value):
    spec=FIELDS[field]
    if spec[7]=='inverse_bool':
        if type(value) is not bool:raise StockError('Boolean required; integer coercion forbidden')
        return int(not value)
    if type(value) not in (int,float):raise StockError('Finite number required; booleans and strings forbidden')
    try:
        value=float(value)
        if not math.isfinite(value):raise StockError('NaN/infinity forbidden by API safety policy')
        value=struct.unpack('<f',struct.pack('<f',value))[0]
    except (OverflowError,struct.error) as e:raise StockError('Outside binary32 representation') from e
    if not math.isfinite(value):raise StockError('Outside finite binary32 representation')
    return (0. if value < 0. else value) if spec[7]=='clamp_zero' else value

def select(root,class_name,name):
    if class_name not in ('OTTrain','OTTrainCategory'):raise StockError('Unsupported class')
    if not isinstance(name,str) or not name:raise StockError('Exact nonempty identity required')
    candidates=[o for o in w.objects(root) if w.kind(o)==class_name]
    rows={}
    for obj in candidates:
        if class_name=='OTTrain':c.record(obj,class_name);slot=0
        else:c.shape(obj,class_name,19,CATEGORY_LAYOUT);slot=1
        key=c.text(obj.contents[slot].value)
        if not key or key in rows:raise StockError('Empty/ambiguous catalog identity')
        rows[key]=obj
    if name not in rows:raise StockError('Selected identity not found')
    return rows[name]

def patch_archive(blob,class_name,name,changes):
    """No files, no input-graph mutation. All fields validated before assignment.

    Float API deliberately exposes finite binary32 setter domain, including
    negative values for unguarded setters. It does not assert physical validity.
    """
    if type(blob) is not bytes:raise StockError('Immutable archive bytes required')
    if type(changes) is not dict or not changes:raise StockError('Nonempty explicit changes required')
    normalized={}
    for field,value in changes.items():
        if field not in FIELDS or FIELDS[field][0]!=class_name:raise StockError('Unknown or wrong-class field')
        normalized[field]=value_for(field,value)
    root,version=w.load_next_compatible(blob)
    obj=select(root,class_name,name)
    report=[]
    for field,value in normalized.items():
        _,_,group,slot,encoding,address,unit,mode=FIELDS[field]
        before=obj.contents[group].values[slot]
        obj.contents[group].values[slot]=value
        report.append({'field':field,'requested':changes[field],'before_native':before,'after_native':value,
                       'group':group,'slot':slot,'encoding':encoding,'unit':unit,'setter':'0x'+address})
    output=w.dump_verified(root,version)
    fresh,_=w.load_next_compatible(output)
    actual=select(fresh,class_name,name)
    for field,value in normalized.items():
        spec=FIELDS[field]
        if actual.contents[spec[2]].values[spec[3]]!=value:raise StockError('Fresh archive reload mismatch')
    return output,{'class':class_name,'name':name,'changes':report,'fresh_reload_verified':True,
                   'native_application_tested':False,'scope':'archive setter equivalence only; not physical validation',
                   'reference_changes':False,'derived_field_recomputation':False}

def rebind_engine_archive(train_blob,engine_blob,train_name,engine_reference_index,engine_name):
    """Replace one existing name binding; preserve array order and posInTrain.

    Caller must resolve both bytes from the same authorized project/dataset and
    atomically recheck both source hashes. No engine import/create or renaming.
    """
    import hashlib
    if type(train_blob) is not bytes or type(engine_blob) is not bytes:raise StockError('Immutable archive bytes required')
    if type(engine_reference_index) is not int or engine_reference_index<0:raise StockError('Zero-based nonnegative reference index required')
    if type(engine_name) is not str or not engine_name:raise StockError('Exact nonempty Engine identity required')
    root,version=w.load_next_compatible(train_blob);engines,_=w.load_next_compatible(engine_blob)
    train=select(root,'OTTrain',train_name)
    names={}
    for engine in w.objects(engines):
        if w.kind(engine)!='OTEngine':continue
        c.record(engine,'OTEngine');key=c.text(engine.contents[1].value)
        if not key or key in names:raise StockError('Empty/ambiguous Engine catalog identity')
        names[key]=engine
    if engine_name not in names:raise StockError('Engine does not exist in supplied current catalog')
    refs=c.array(train.contents[2].values[1])
    for ref in refs:c.record(ref,'OTTrainEngine');c.text(ref.contents[0].value)
    if engine_reference_index>=len(refs):raise StockError('Engine reference index outside array')
    chosen=refs[engine_reference_index]
    
    
    from .graph_references import reference_inventory
    graph_objects,counts=reference_inventory(root)
    occurrences=counts[id(chosen)]
    ref_array=train.contents[2].values[1]
    array_occurrences=counts[id(ref_array)]
    owner_paths=0
    for owner in graph_objects:
        if w.kind(owner)=='OTTrain':
            c.record(owner,'OTTrain')
            owner_paths+=sum(ref is chosen for ref in c.array(owner.contents[2].values[1]))
    if occurrences!=1 or array_occurrences!=1 or owner_paths!=1:
        raise StockError('Shared Engine reference record or parent array cannot be edited independently')
    old=c.text(chosen.contents[0].value);position=chosen.contents[1].value
    old_string=chosen.contents[0].value
    if old==engine_name:
        return train_blob,{'changed':False,'before':old,'after':old,'position':position,'native_application_tested':False}
    
    
    chosen.contents[0].value=w.GenericArchivedObject(old_string.clazz,None,[w.TypedValue(b'+',engine_name.encode('utf8'))])
    output=w.dump_verified(root,version);fresh,_=w.load_next_compatible(output)
    actual=c.array(select(fresh,'OTTrain',train_name).contents[2].values[1])[engine_reference_index]
    if c.text(actual.contents[0].value)!=engine_name or actual.contents[1].value!=position:raise StockError('Fresh binding reload mismatch')
    return output,{'changed':True,'before':old,'after':engine_name,'position':position,
        'engine_reference_index':engine_reference_index,'array_order_preserved':True,
        'setter':'0x006d7f90','encoder':'0x006d800c','train_encoder':'0x006c2dbc',
        'engine_catalog_sha256':hashlib.sha256(engine_blob).hexdigest(),
        'fresh_reload_verified':True,'native_application_tested':False,
        'scope':'existing reference name setter; no ordering or physical recomputation'}

def clone_engine_archive(blob,template_name,new_name):
    """Explicit current-template factory, NOT native copyWithZone equivalence.

    Mirrors audited generation.template/store deepcopy+append semantics with no
    automatic template/defaults, no replace and no old-version migration.
    """
    import copy
    if type(blob) is not bytes:raise StockError('Immutable archive bytes required')
    for name in (template_name,new_name):
        if type(name) is not str or not name or '\x00' in name:raise StockError('Nonempty NUL-free explicit names required')
    root,version=w.load_next_compatible(blob)
    items=c.engine_items(root)
    by_name={c.text(e.contents[1].value):e for e in items}
    if template_name not in by_name:raise StockError('Explicit current Engine template missing')
    if new_name in by_name:raise StockError('Fresh Engine name required; replacement forbidden')
    template=by_name[template_name];before=w.fingerprint(template)
    clone=copy.deepcopy(template)
    old_name=clone.contents[1].value
    clone.contents[1].value=w.GenericArchivedObject(old_name.clazz,None,[w.TypedValue(b'+',new_name.encode('utf8'))])
    w.set_elements(root,items+[clone])
    if w.fingerprint(template)!=before:raise StockError('Template changed during factory')
    output=w.dump_verified(root,version);fresh,_=w.load_next_compatible(output)
    actual=c.engine_items(fresh)
    if len(actual)!=len(items)+1 or c.text(actual[-1].contents[1].value)!=new_name:raise StockError('New Engine fresh reload mismatch')
    if w.fingerprint(actual[list(by_name).index(template_name)])!=before:raise StockError('Reloaded template differs')
    return output,{'template_name':template_name,'new_name':new_name,'before_count':len(items),'after_count':len(actual),
        'template_unchanged':True,'all_unspecified_fields_preserved':True,'fresh_reload_verified':True,
        'new_engine_graph':'deep copy; internal aliases preserved, no new mutable aliases to template',
        'native_application_tested':False,'native_copyWithZone_equivalence':False,
        'basis':'audited generation.py template/store explicit deepcopy and fresh-name append'}
