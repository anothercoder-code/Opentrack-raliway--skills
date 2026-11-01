"""Pure current-format mixed-consist construction. No simulator, cache or IO."""
import copy, hashlib, math, struct
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.train_factory import name, validate_template
from opentrack_ai.current_archive.formation_operations import trailer, position, snapshot
from opentrack_ai.current_archive.graph_references import reference_inventory
from opentrack_ai.current_archive.zero_operations.vehicle_catalogs import validate_graph
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT

class ConsistError(ValueError): pass
def need(ok,msg):
    if not ok: raise ConsistError(msg)
def sha(b): return hashlib.sha256(b).hexdigest()
def integer(v,label,lo=0,hi=2**24):
    need(type(v)is int and lo<=v<=hi,label+' outside exact integer API domain');return v
def f32(v,label):
    need(type(v)in(int,float) and math.isfinite(v),label+' requires finite number')
    try: f=struct.unpack('<f',struct.pack('<f',v))[0]
    except (OverflowError,struct.error) as e: raise ConsistError(label+' outside binary32') from e
    need(math.isfinite(f) and (v==0 or f!=0),label+' overflow/underflow');return f
def string(s):
    name(s);return w.GenericArchivedObject(w.Class(b'NSString',1,w.Class(b'NSObject',0)),None,[w.TypedValue(b'+',s.encode())])
def array(proto,rows):
    c.array(proto);out=w.GenericArchivedObject(proto.clazz,None,[]);w.set_elements(out,rows);return out
def unique(rows,slot,label):
    out={}
    for row in rows:
        k=name(c.text(row.contents[slot].value));need(k not in out,'Duplicate '+label);out[k]=row
    return out

def finite(root):
    for o in reference_inventory(root)[0]:
        for g in o.contents:
            for enc,v in zip(g.encodings,g.values):
                if enc in (b'f',b'd'):
                    need(isinstance(v,float) and math.isfinite(v),'Nonfinite persisted scalar')
                    if enc==b'f':need(f32(float(v),'source float')==v,'Nonexact binary32 source')
                elif enc in (b'i',b's',b'c'):
                    need(type(v)is int and -(2**31)<=v<2**31,'Invalid persisted integer')

def load(trains_blob,depot_blob):
    need(type(trains_blob)is bytes and type(depot_blob)is bytes,'Immutable catalog bytes required')
    root,ver=w.load_next_compatible(trains_blob);depot,_=w.load_next_compatible(depot_blob)
    need(root.contents[0].value==17,'Current TrainList marker17 required')
    trains=unique(c.train_items(root),0,'Train');engines=unique(c.engine_items(depot),1,'Engine')
    cats=c.array(root.contents[1].value)
    for cat in cats:c.shape(cat,'OTTrainCategory',19,CATEGORY_LAYOUT)
    categories=unique(cats,1,'Category')
    
    
    detached=[]
    for t in trains.values():
        refs,trailers=validate_template(t)
        need(c.text(t.contents[3].value) in categories,'Missing Category')
        need(all(c.text(r.contents[0].value) in engines for r in refs),'Unresolved Engine')
        for tr in trailers:
            trailer(tr)
            need(tr.contents[0].value==17 and tr.contents[2].values[0]==0 and tr.contents[3].values[0]==0,
                 'Source Trailer requires marker17 and zero reserved fields (audited API domain)')
        detached.append((t,t.contents[2].values[2]));t.contents[2].values[2]=array(t.contents[2].values[2],[])
    try:
        for g in root.contents[1:]:validate_graph(g.value)
        validate_graph(depot)
    finally:
        for t,a in detached:t.contents[2].values[2]=a
    finite(root);finite(depot)
    _,counts=reference_inventory(root)
    need(counts[id(root)]==0 and counts[id(root.contents[3].value)]==1,'Shared root/Train parent')
    return root,ver,depot,trains,engines,categories,counts

TRAILER_KEYS={'kind','name','length_m','mass_t','rotating_mass_factor','axles','cw','number_of_items','maximum_speed_kmh','power_loss_kw','delta_load_power_loss_kw_per_t','vehicle_marker','vehicle_reserved','trailer_reserved'}
def make_trailer(row,pos):
    need(type(row)is dict and set(row)==TRAILER_KEYS,'Explicit complete Trailer3 fields required')
    need(row['kind']=='trailer','Trailer kind required')
    
    marker=integer(row['vehicle_marker'],'vehicle_marker',17,17)
    reserved=integer(row['vehicle_reserved'],'vehicle_reserved',0,0)
    tr_reserved=integer(row['trailer_reserved'],'trailer_reserved',0,0)
    mass=integer(row['mass_t'],'mass_t',0);length=integer(row['length_m'],'length_m',1)
    axles=integer(row['axles'],'axles',1,1024);items=integer(row['number_of_items'],'number_of_items',0,1024)
    speed=integer(row['maximum_speed_kmh'],'maximum_speed_kmh',1,10000)
    rot=f32(row['rotating_mass_factor'],'rotating_mass_factor');cw=f32(row['cw'],'cw')
    loss=f32(row['power_loss_kw'],'power_loss_kw');delta=f32(row['delta_load_power_loss_kw_per_t'],'delta_load_power_loss_kw_per_t')
    cl=w.Class(b'OTTrailer',3,w.Class(b'OTVehicle',0,w.Class(b'NSObject',0)))
    out=w.GenericArchivedObject(cl,None,[w.TypedValue(b'i',marker),w.TypedValue(b'@',string(row['name'])),w.TypedGroup([b'i',b'i',b'i',b'f',b'i',b'f'],[reserved,mass,length,rot,axles,cw]),w.TypedGroup([b'i',b'i',b'i'],[tr_reserved,pos,items]),w.TypedValue(b'i',speed),w.TypedValue(b'f',loss),w.TypedValue(b'f',delta)])
    trailer(out);return out

def summary(train,engines):
    refs,trs=validate_template(train);need(refs,'At least one Engine required')
    rows=[]
    for r in refs:
        key=c.text(r.contents[0].value);need(key in engines,'Missing Engine');e=engines[key]
        rows.append({'kind':'engine','position':position(r),'name':key,'length_m':e.contents[2].values[2],'mass_t':e.contents[2].values[1],'maximum_speed_kmh':e.contents[7].value})
    for t in trs:
        rows.append({'kind':'trailer','position':position(t),'name':c.text(t.contents[1].value),'length_m':t.contents[2].values[2],'mass_t':t.contents[2].values[1],'maximum_speed_kmh':t.contents[4].value,'number_of_items_not_quantity':t.contents[3].values[2]})
    length=mass=0;speed=10000
    for r in rows:
        length+=integer(r['length_m'],'resolved length',1)
        mass+=integer(r['mass_t'],'resolved mass',0)
        integer(length,'total length',1);integer(mass,'total mass',0)
        speed=min(speed,integer(r['maximum_speed_kmh'],'resolved speed',1,10000))
    return {'train_name':c.text(train.contents[0].value),'formation':sorted(rows,key=lambda r:r['position']),'engine_array_order':[c.text(r.contents[0].value) for r in refs],'engine_reference_count':len(refs),'trailer_record_count':len(trs),'length_m':length,'cold_mass_t':mass,'maximum_speed_kmh':speed,'runtime_delta_mass_t_assumption':0,'native_simulation_prepared':False,'physical_performance_validated':False,'braking_resistance_model_recalculated':False}

def generate_consist(trains_blob,depot_blob,spec):
    need(type(spec)is dict and set(spec)=={'mode','template_name','output_name','formation','model_policy','accept_uncalibrated_inherited_model'},'Exact consist spec keys required')
    need(spec['mode'] in ('clone','replace'),'mode clone/replace required')
    need(spec['model_policy']=='inherit_template' and spec['accept_uncalibrated_inherited_model'] is True,'Explicit unchanged whole-train model acceptance required')
    source_name=name(spec['template_name']);out_name=name(spec['output_name'])
    formation=spec['formation'];need(type(formation)is list and 1<=len(formation)<=256,'1..256 explicit records required (API bound)')
    root,ver,depot,trains,engines,cats,counts=load(trains_blob,depot_blob)
    need(source_name in trains,'Unknown template')
    if spec['mode']=='clone':need(out_name not in trains,'Output name collision')
    else:need(out_name==source_name,'replace must retain exact name; external rename refs not supported')
    template=trains[source_name]
    
    for o in reference_inventory(template)[0]:
        if w.kind(o)!='NSString':need(counts[id(o)]==1,'Shared mutable template object')
    before=w.fingerprint(root);old_snapshot=snapshot(root)
    created=copy.deepcopy(template);old_name=created.contents[0].value;old_eng=created.contents[2].values[1];old_tr=created.contents[2].values[2]
    refs=[];trailers=[];trnames=set()
    for pos,row in enumerate(formation,1):
        need(type(row)is dict,'Formation object required')
        if row.get('kind')=='engine':
            need(set(row)=={'kind','name'},'Engine record requires kind/name only; position follows list, no quantity')
            key=name(row['name']);need(key in engines,'Unknown Engine')
            refs.append(w.GenericArchivedObject(w.Class(b'OTTrainEngine',0,w.Class(b'NSObject',0)),None,[w.TypedValue(b'@',string(key)),w.TypedValue(b'i',pos)]))
        else:
            tr=make_trailer(row,pos);key=c.text(tr.contents[1].value);need(key not in trnames,'Duplicate Trailer name');trnames.add(key);trailers.append(tr)
    need(refs,'At least one Engine required')
    created.contents[0].value=string(out_name);created.contents[2].values[1]=array(old_eng,refs);created.contents[2].values[2]=array(old_tr,trailers)
    validate_template(created);finite(created)
    changed=(created.contents[0].value,created.contents[2].values[1],created.contents[2].values[2])
    created.contents[0].value=old_name;created.contents[2].values[1]=old_eng;created.contents[2].values[2]=old_tr
    need(w.fingerprint(created)==w.fingerprint(template),'Template model changed')
    created.contents[0].value,created.contents[2].values[1],created.contents[2].values[2]=changed
    old_ids={id(o) for o in reference_inventory(root)[0]}
    need(not any(id(o) in old_ids for o in reference_inventory(created)[0]),'Clone ownership leaked')
    rows=list(trains.values());parent=root.contents[3].value
    if spec['mode']=='clone':rows.append(created)
    else:rows[rows.index(template)]=created
    w.set_elements(parent,rows)
    expected=summary(created,engines);output=w.dump_verified(root,ver)
    fresh,_,_,fts,fes,_,_=load(output,depot_blob);actual=summary(fts[out_name],fes)
    need(actual==expected,'Fresh summary mismatch')
    
    source,_=w.load_next_compatible(trains_blob)
    source_rows=c.train_items(source)
    if spec['mode']=='replace':source_rows=[t for t in source_rows if c.text(t.contents[0].value)!=source_name]
    w.set_elements(source.contents[3].value,source_rows)
    w.set_elements(fresh.contents[3].value,[t for t in c.train_items(fresh) if c.text(t.contents[0].value)!=out_name])
    need(w.fingerprint(source)==w.fingerprint(fresh),'Non-target graph/alias change')
    return output,{'operation':'mixed_consist_'+spec['mode'],'source_sha256':{'trains':sha(trains_blob),'depot':sha(depot_blob)},'output_sha256':sha(output),'static_summary':actual,'model_policy':'inherit_template','inherited_model_calibration_verified':False,'template_nonformation_model_preserved':True,'non_target_graph_and_aliases_preserved':True,'depot_modified':False,'cache_fields_written':False,'trailer_constructor_equivalent_to_native_addTrailer':False,'same_project_verified':False,'native_application_tested':False,'published':False}
