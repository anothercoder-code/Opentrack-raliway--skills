"""Fresh current vehicle catalogs from an explicitly accepted physical type template.
Pure bytes only. No physical recalculation, original simulator, filesystem or migration.
"""
import copy, hashlib, math, struct
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.train_factory import validate_template, name
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT, FIELDS, value_for
from opentrack_ai.current_archive.graph_references import reference_inventory
from opentrack_ai.json_safe import checked_json

class VehicleError(ValueError): pass

def need(ok,msg):
    if not ok: raise VehicleError(msg)

def enc(obj): return [''.join(e.decode('ascii') for e in g.encodings) for g in obj.contents]

def text(value):
    name(value)
    return w.GenericArchivedObject(w.Class(b'NSString',1,w.Class(b'NSObject',0)),None,[w.TypedValue(b'+',value.encode('utf8'))])

def fresh_array(prototype, items=()):
    c.array(prototype)
    return w.GenericArchivedObject(prototype.clazz,None,[w.TypedValue(b'i',len(items))]+[w.TypedValue(b'@',x) for x in items])

WRAPPERS={'OTDelayIntervalArray','OTDelayPriorityArray','OTPerformanceIntervalArray','OTEfficiencyArray','OTDecelerationArray'}
LAYOUTS={
 'OTDDiagram':(3,['iiiiiii','@','@','@','@','i','@','@']),
 'OTDPoint':(0,['iii']), 'OTDelayInterval':(0,['fff']),
 'OTDelayPriority':(0,['fi']), 'OTPerformanceInterval':(0,['fff']),
 'OTDeceleration':(1,['iff']), 'OTConflictCategory':(0,['iii','@','@']),
}

def validate_graph(root):
    """Close every owned object edge by exact current layouts; reject hidden types."""
    objs,_=reference_inventory(root)
    for obj in objs:
        kind=w.kind(obj)
        if kind in c.LAYOUTS:c.record(obj,kind)
        elif kind=='OTTrainCategory':c.shape(obj,kind,19,CATEGORY_LAYOUT)
        elif kind in LAYOUTS:
            ver,shape=LAYOUTS[kind];c.shape(obj,kind,ver,shape)
        elif kind in WRAPPERS:
            cl=obj.clazz
            need(cl.version==0 and enc(obj)==['@'], 'Unsupported wrapper '+kind)
            cl=cl.superclass
            need(cl is not None and cl.name==b'OTMutableArray' and cl.version==0 and cl.superclass is not None and cl.superclass.name==b'NSObject' and cl.superclass.version==0 and cl.superclass.superclass is None,'Wrapper inheritance')
            c.array(obj.contents[0].value)
        elif kind in ('NSArray','NSMutableArray'):c.array(obj)
        elif kind=='NSString':c.text(obj)
        elif kind=='NSColor':
            c.hierarchy(obj)
            need(obj.clazz.version==0 and enc(obj) in (['c','ff'],['c','ffff']),'Unsupported Color representation')
        elif kind=='NSNumber':
            cl=obj.clazz.superclass
            need(cl is not None and cl.name==b'NSValue' and cl.version==0 and cl.superclass is not None and cl.superclass.name==b'NSObject' and cl.superclass.version==0 and cl.superclass.superclass is None,'NSNumber inheritance')
            need(obj.clazz.version==0 and enc(obj) in (['*','s'],['*','i']),'Unsupported Number representation')
            token=obj.contents[0].value
            need(isinstance(token,w.CString) and token.token.data==obj.contents[1].encodings[0], 'NSNumber scalar token mismatch')
        else:raise VehicleError('Unknown owned class '+kind)
        for g in obj.contents:
            for encoding,value in zip(g.encodings,g.values):
                if encoding in (b'f',b'd'):need(math.isfinite(value),'Nonfinite template physical/color scalar')
                elif encoding in (b'i',b's',b'c'):
                    need(type(value) is int,'Noninteger template scalar')
    def expect(obj,kind):need(w.kind(obj)==kind,'Wrong-role owned object; expected '+kind)
    for obj in objs:
        kind=w.kind(obj)
        if kind=='OTEngine':
            need(obj.contents[0].value==17,'Current Engine encoder marker17 required')
            c.text(obj.contents[1].value)
            ds=c.array(obj.contents[16].value);need(ds,'At least one current force diagram required')
            for d in ds:expect(d,'OTDDiagram')
        elif kind=='OTDDiagram':
            from opentrack_ai.current_archive.engine_curves import point_row
            for slot in (1,2):
                rows=[point_row(p) for p in c.array(obj.contents[slot].value)]
                need(len({p[0] for p in rows})==len(rows),'Duplicate curve speeds')
                need(all((p[1]<0)==(slot==2) for p in rows),'Wrong force sign')
            for x in c.array(obj.contents[3].value):expect(x,'NSNumber')
            expect(obj.contents[4].value,'NSColor');c.text(obj.contents[6].value)
            expect(obj.contents[7].value,'OTEfficiencyArray')
        elif kind=='OTTrainCategory':
            need(obj.contents[0].values[1]&~63==0,'Unknown category flags')
            c.text(obj.contents[1].value)
            for slot in (2,17):expect(obj.contents[slot].value,'NSColor')
            for slot,wrapper in ((10,'OTDelayIntervalArray'),(12,'OTDelayPriorityArray'),(13,'OTPerformanceIntervalArray'),(14,'OTPerformanceIntervalArray')):expect(obj.contents[slot].value,wrapper)
        elif kind=='OTConflictCategory':
            need(obj.contents[0].values[1] in (0,1),'Unknown conflict flags')
            c.text(obj.contents[1].value);expect(obj.contents[2].value,'NSColor')
        elif kind in WRAPPERS:
            rows=c.array(obj.contents[0].value)
            if kind=='OTEfficiencyArray':need(not rows,'Nonempty efficiency table outside audited scope')
            else:
                expected={'OTDelayIntervalArray':'OTDelayInterval','OTDelayPriorityArray':'OTDelayPriority','OTPerformanceIntervalArray':'OTPerformanceInterval','OTDecelerationArray':'OTDeceleration'}[kind]
                for row in rows:expect(row,expected)
    return objs

def lookup(items, slot, label):
    found={}
    for obj in items:
        key=c.text(obj.contents[slot].value)
        need(key and key not in found,'Duplicate/empty '+label)
        found[key]=obj
    return found

def numeric_manifest(obj):
    """All template primitive groups, with binary32 encoding kept in audit digest."""
    result=[]
    for index,g in enumerate(obj.contents):
        row=[]
        for e,v in zip(g.encodings,g.values):
            if e in (b'f',b'd',b'i',b's',b'c'):
                row.append({'encoding':e.decode(),'value':v})
            elif isinstance(v,w.GenericArchivedObject) and w.kind(v)=='NSString':row.append({'encoding':'@NSString','value':c.text(v)})
            else:row.append({'encoding':e.decode(),'owned_class':w.kind(v) if isinstance(v,w.GenericArchivedObject) else 'nil'})
        result.append({'group':index,'slots':row})
    return checked_json(result)

def generate_vehicle_catalogs(depot_blob, trains_blob, spec):
    required={'engine_template','train_template','category_template','engine_name','category_name','train_names','use_template_physics','inherit_conflict_definitions','train_parameters'}
    need(type(depot_blob) is bytes and type(trains_blob) is bytes,'Immutable two-catalog bytes required')
    need(type(spec) is dict and set(spec)==required,'Explicit complete vehicle spec required')
    need(spec['use_template_physics'] is True,'Explicit template physics acceptance required')
    need(spec['inherit_conflict_definitions'] is True,'Explicit conflict-definition retention required')
    for key in ('engine_template','train_template','category_template','engine_name','category_name'):name(spec[key])
    names=spec['train_names'];need(type(names) is list and 1<=len(names)<=1000,'1..1000 new Train names required')
    for n in names:name(n)
    need(len(set(names))==len(names),'Duplicate output Train name')
    depot,dv=w.load_next_compatible(depot_blob);source,tv=w.load_next_compatible(trains_blob)
    engines=lookup(c.engine_items(depot),1,'Engine');trains=lookup(c.train_items(source),0,'Train')
    need(source.contents[0].value==17,'Current TrainList marker17 required')
    cats=lookup(c.array(source.contents[1].value),1,'Category')
    for cat in cats.values():c.shape(cat,'OTTrainCategory',19,CATEGORY_LAYOUT)
    need(spec['engine_template'] in engines and spec['train_template'] in trains and spec['category_template'] in cats,'Explicit current templates not found')
    need(spec['engine_name'] not in engines and spec['category_name'] not in cats and not set(names)&set(trains),'Names must be fresh, not existing entities')
    engine=engines[spec['engine_template']];train=trains[spec['train_template']];cat=cats[spec['category_template']]
    refs,trailers=validate_template(train)
    need(len(refs)==1 and not trailers,'Guarded template requires exactly one Engine and no trailers')
    need(c.text(refs[0].contents[0].value)==spec['engine_template'],'Selected Train must already use selected Engine type')
    need(c.text(train.contents[3].value)==spec['category_template'],'Selected Train must already use selected Category type')
    conflicts=source.contents[2].value
    conflict_types=set();conflict_names=set()
    for x in c.array(conflicts):
        c.shape(x,'OTConflictCategory',0,['iii','@','@'])
        typ=x.contents[0].values[2];key=c.text(x.contents[1].value)
        need(typ not in conflict_types and key and key not in conflict_names,'Ambiguous conflict definitions')
        conflict_types.add(typ);conflict_names.add(key)
    for x in (engine,train,cat,conflicts):validate_graph(x)
    changes=spec['train_parameters'];allowed={'maximum_acceleration_mps2','braking_delay_s','braking_release_speed_kmh'}
    need(type(changes) is dict and set(changes)==allowed,'Three explicit Train parameters required')
    normalized={key:value_for(key,val) for key,val in changes.items()}
    need(0<normalized['maximum_acceleration_mps2']<=10 and 0<=normalized['braking_delay_s']<=60 and 0<=normalized['braking_release_speed_kmh']<=400,'Train physical inputs outside guarded educational domain')
    new_engine=copy.deepcopy(engine);old_engine_name=new_engine.contents[1].value;new_engine.contents[1].value=text(spec['engine_name'])
    new_category=copy.deepcopy(cat);old_category_name=new_category.contents[1].value;new_category.contents[1].value=text(spec['category_name'])
    new_trains=[];train_originals=[]
    source_obj_ids={id(o) for r in (depot,source) for o in reference_inventory(r)[0]}
    for n in names:
        new=copy.deepcopy(train);old_refs,_=validate_template(new);train_originals.append((new.contents[0].value,new.contents[3].value,old_refs[0].contents[0].value));new.contents[0].value=text(n);new.contents[3].value=text(spec['category_name'])
        newrefs,_=validate_template(new);newrefs[0].contents[0].value=text(spec['engine_name'])
        for key,val in normalized.items():
            field=FIELDS[key];new.contents[field[2]].values[field[3]]=val
        validate_template(new);validate_graph(new);new_trains.append(new)
    new_depot=fresh_array(depot,[new_engine])
    new_list=w.GenericArchivedObject(source.clazz,None,[w.TypedValue(b'i',17),w.TypedValue(b'@',fresh_array(source.contents[1].value,[new_category])),w.TypedValue(b'@',copy.deepcopy(conflicts)),w.TypedValue(b'@',fresh_array(source.contents[3].value,new_trains))])
    all_new=[o for root in (new_depot,new_list) for o in reference_inventory(root)[0]]
    need(not {id(o) for o in all_new}&source_obj_ids,'Source owned object leaked into fresh catalogs')
    
    train_graph_ids=[{id(o) for o in reference_inventory(t)[0]} for t in new_trains]
    need(sum(map(len,train_graph_ids))==len(set().union(*train_graph_ids)),'Generated Train objects are aliased')
    output={'depot':w.dump_verified(new_depot,dv),'trains':w.dump_verified(new_list,tv)}
    actual_d,_=w.load_next_compatible(output['depot']);actual_t,_=w.load_next_compatible(output['trains'])
    need(w.fingerprint(actual_d)==w.fingerprint(new_depot) and w.fingerprint(actual_t)==w.fingerprint(new_list),'Fresh graph mismatch')
    need({c.text(e.contents[1].value) for e in c.engine_items(actual_d)}=={spec['engine_name']},'Fresh engine closure')
    for t in c.train_items(actual_t):
        need(c.bound_engine_names(t)==[spec['engine_name']] and c.text(t.contents[3].value)==spec['category_name'],'Fresh Train external-name closure')
    
    current=new_engine.contents[1].value;new_engine.contents[1].value=old_engine_name
    need(w.fingerprint(new_engine)==w.fingerprint(engine),'Unselected Engine graph changed')
    new_engine.contents[1].value=current
    current=new_category.contents[1].value;new_category.contents[1].value=old_category_name
    need(w.fingerprint(new_category)==w.fingerprint(cat),'Unselected Category graph changed')
    new_category.contents[1].value=current
    for new,old_names in zip(new_trains,train_originals):
        ref=c.array(new.contents[2].values[1])[0]
        current=(new.contents[0].value,new.contents[3].value,ref.contents[0].value)
        new.contents[0].value,new.contents[3].value,ref.contents[0].value=old_names
        for key in normalized:
            field=FIELDS[key];new.contents[field[2]].values[field[3]]=train.contents[field[2]].values[field[3]]
        need(w.fingerprint(new)==w.fingerprint(train),'Unselected Train graph/alias changed')
        new.contents[0].value,new.contents[3].value,ref.contents[0].value=current
        for key,value in normalized.items():
            field=FIELDS[key];new.contents[field[2]].values[field[3]]=value
    receipt={'operation':'fresh_vehicle_type_catalogs','train_count':len(names),'engine_count':1,'category_count':1,'conflict_definition_count':len(conflict_types),'source_sha256':{'depot':hashlib.sha256(depot_blob).hexdigest(),'trains':hashlib.sha256(trains_blob).hexdigest()},'template_graph_sha256':{key:hashlib.sha256(w.dump_verified(obj,tv if key!='engine' else dv)).hexdigest() for key,obj in [('engine',engine),('train',train),('category',cat)]},'template_physics':{key:numeric_manifest(obj) for key,obj in [('engine',engine),('train',train),('category',cat)]},'train_parameter_inputs':normalized,'output_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in output.items()},'source_bytes_unchanged':True,'unselected_template_graph_preserved':True,'mutable_graphs_isolated':True,'conflict_definitions':'deep-copy verified configuration, not operational entities','physical_recalculation':False,'calibrated_vehicle_model':False,'native_simulation_executed':False,'scope':'new named vehicle definitions; not six individually tracked physical trains or circulation'}
    return output,checked_json(receipt)
