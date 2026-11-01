"""Current Station3 + StationModel1 + End7 paired StationVertex bindings (type2).
Pure bytes; no stopping/platform boundary, project runtime, or native execution claim.
"""
import hashlib, math, struct
from opentrack_ai.current_archive import writer as w, catalogs as c, path_functions as pf, route_factory as rf
from opentrack_ai.current_archive.graph_references import incoming
from opentrack_ai.current_archive.graphic_alignment import validate_placement

class StationBindingError(ValueError): pass

def need(ok,msg):
    if not ok: raise StationBindingError(msg)

def integer(v,lo=0,hi=2147483647):
    need(type(v)is int and lo<=v<=hi,'Exact bounded integer required');return v

def number(v):
    need(type(v) in (int,float) and math.isfinite(v) and abs(v)<=1e7,'Finite bounded placement required')
    return struct.unpack('<f',struct.pack('<f',v))[0]

def text(v):
    need(type(v)is str and 0<len(v)<=200 and all(32<=ord(x)<127 for x in v) and '#' not in v,'Explicit printable ASCII identity/text required')
    return v

def cls(chain):
    base=None
    for name,version in reversed(chain):base=w.Class(name.encode(),version,base)
    return base

def obj(chain,groups):
    return w.GenericArchivedObject(cls(chain),None,[w.TypedGroup(w.split_types(e.encode()),v) for e,v in groups])

def string(v):return obj([('NSString',1),('NSObject',0)],[('+',[v.encode('ascii')])])

def dictionary(items):
    return obj([('NSMutableDictionary',0),('NSDictionary',0),('NSObject',0)],[('i',[len(items)])]+[g for sign,item in items for g in [('@',[string(sign)]),('@',[item])]])

DOC=['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@','ffff','iii','ff','@','@','@','@']
MODEL=['i','f','f','f','i','i','@','@','ii','ii']

def read_document(blob,allow_stations=False):
    need(type(blob)is bytes,'Immutable archive bytes required')
    root,version=w.load_next_compatible(blob)
    rf.layout(root,'OTDocument',4,DOC)
    models,byid=rf.document(root)
    need(incoming(root,root)==0 and incoming(root,root.contents[2].value)==1,'Aliased root/model array refused')
    allowed={'OTEndModel','OTEdgeModel','OTElement','OTSignalModel'}|({'OTStationModel'} if allow_stations else set())
    need(all(w.kind(m) in allowed for m in models),'Unsupported or preexisting graphic station model')
    for mid in byid:integer(mid,0,2147483646)
    for m in models:
        k=w.kind(m)
        if k=='OTEndModel':
            rf.layout(m,k,7,rf.END,graphic=True)
            need(type(m.contents[20].value)is int and m.contents[20].value in ((1,2) if allow_stations else (1,)),'Only ordinary type1 sources and explicit type2 StationVertices supported')
            pair=byid.get(m.contents[8].value)
            need(pair is not m and pair in models and w.kind(pair)=='OTEndModel' and pair.contents[8].value==m.contents[0].value,'Related End closure invalid')
            if not allow_stations:need(m.contents[12].value is None,'Existing End station binding refused')
            else:
                st=m.contents[12].value
                need(st is None or (st in models and w.kind(st)=='OTStationModel'),'Station binding outside model array')
                need(pair.contents[20].value==m.contents[20].value,'StationVertex type must agree on related halves')
                need(pair.contents[12].value is st,'Related halves must reference the same actual StationModel')
                need((m.contents[20].value==2)==(st is not None),'Point-only generated profile requires type2 for station associations; native type1 area members are outside this profile')
        elif k=='OTEdgeModel':rf.layout(m,k,3,rf.EDGE,graphic=True)
        elif k=='OTElement':rf.layout(m,k,0,['i','f','f','f','i','i','@','@'],graphic=True)
        elif k=='OTSignalModel':rf.layout(m,k,11,rf.SIGNAL,graphic=True)
        else:rf.layout(m,k,1,MODEL,graphic=True)
    
    stations=[m for m in models if w.kind(m)=='OTStationModel']
    need(all(o in stations for o in w.objects(root) if w.kind(o)=='OTStationModel'),'Hidden StationModel reference refused')
    signs=[text(pf.string(o.contents[7].value)) for o in stations]
    need(len(signs)==len(set(signs)),'Duplicate StationModel sign is ambiguous')
    return root,version,models,byid


def bind_stations(document_bytes,specs):
    """spec={sign,name,end_ids,placement,station_type_raw,interlock_type_raw,
    icon_show_type_raw,timing_point}. Fresh catalog; no prior station replacement.
    Both halves of every selected logical vertex become type2 and share the actual
    StationModel. This is a static pass-consumer contract, NOT a stopping region.
    """
    need(type(specs)is list and 1<=len(specs)<=1000,'Explicit 1..1000 station specs required')
    root,version,models,byid=read_document(document_bytes)
    before=w.dump_verified(root,version);nextid=max(byid,default=-1)+1
    need(nextid+len(specs)<=2147483647,'Graphic ID exhausted')
    signs=set();bound=set();made=[];catalog=[];bindings={};alignments={}
    required={'sign','name','end_ids','placement','station_type_raw','interlock_type_raw','icon_show_type_raw','timing_point'}
    for spec in specs:
        need(type(spec)is dict and set(spec)==required,'Missing or unknown station spec fields')
        sign=text(spec['sign']);name=text(spec['name'])
        need(sign not in signs,'Duplicate station sign');signs.add(sign)
        need((spec['station_type_raw'],spec['interlock_type_raw'],spec['icon_show_type_raw'])==(2,4,1) and all(type(spec[k])is int for k in ('station_type_raw','interlock_type_raw','icon_show_type_raw')),'Only explicit verified raw station profile 2/4/1 supported')
        need(type(spec['timing_point'])is bool,'Explicit timing_point boolean required')
        ids=spec['end_ids'];need(type(ids)is list and 1<=len(ids)<=10000 and all(type(i)is int for i in ids) and len(set(ids))==len(ids),'Explicit unique End ID list required')
        selected_ids=list(ids);expanded=[]
        for eid in selected_ids:
            end=byid.get(eid);need(end is not None and w.kind(end)=='OTEndModel','Unknown End ID')
            for actual in (eid,end.contents[8].value):
                if actual not in expanded:expanded.append(actual)
        ids=expanded
        need(not bound.intersection(ids),'Logical vertex pair bound to multiple station signs')
        ends=[]
        for eid in ids:
            end=byid.get(eid);need(end is not None and w.kind(end)=='OTEndModel','Unknown End ID')
            
            
            pf.guard_counter_references(root,end)
            ends.append(end)
        p=validate_placement(spec['placement'])
        alignments[sign]=(p['alignment_x'],p['alignment_y'])
        model=obj([('OTStationModel',1),('OTGraphicModel',1),('NSObject',0)],
          [('i',[nextid]),('f',[number(p['angle'])]),('f',[number(p['x'])]),('f',[number(p['y'])]),('i',[p['alignment_x']]),('i',[p['alignment_y']]),('@',[None]),('@',[string(sign)]),('ii',[2,4]),('ii',[1,0])])
        nextid+=1
        
        
        station=obj([('OTStation',3),('NSObject',0)],[('i',[17]),('@',[string(sign)]),('@',[string(name)]),('i',[0]),('iii',[0,0,0]),('ii',[0,0]),('@',[string('')]),('i',[int(spec['timing_point'])]),('@',[string('')]),('@',[string('')])])
        c.record(station,'OTStation')
        
        
        for end in ends:
            end.contents[12].value=model
            end.contents[20].value=2
        bound.update(ids);bindings[sign]=ids;made.append(model);catalog.append((sign,station))
    w.set_elements(root.contents[2].value,models+made)
    cat=dictionary(catalog);c.station_items(cat)
    output=w.dump_verified(root,version);station_bytes=w.dump_verified(cat,version)
    check,cv,cm,ci=read_document(output,True);savedcat,_=w.load_next_compatible(station_bytes)
    lookup=c.station_items(savedcat);savedmodels={pf.string(m.contents[7].value):m for m in cm if w.kind(m)=='OTStationModel'}
    need(set(lookup)==set(savedmodels)==signs,'Station catalog/model sign closure mismatch')
    for sign,ids in bindings.items():
        sm=savedmodels[sign]
        need((sm.contents[4].value,sm.contents[5].value)==alignments[sign],'Station native alignment readback mismatch')
        need([m.contents[0].value for m in cm if w.kind(m)=='OTEndModel' and m.contents[12].value is sm]==[m.contents[0].value for m in cm if w.kind(m)=='OTEndModel' and m.contents[0].value in ids],'Binding readback mismatch')
    
    for eid in bound:
        ci[eid].contents[12].value=None
        ci[eid].contents[20].value=1
    w.set_elements(check.contents[2].value,[m for m in cm if w.kind(m)!='OTStationModel'])
    need(w.dump_verified(check,cv)==before,'Unrelated graph/header mutated')
    return output,station_bytes,{'operation':'create_current_paired_station_vertices','station_count':len(specs),'bindings':bindings,'model_ids':{sign:savedmodels[sign].contents[0].value for sign in signs},'source_sha256':hashlib.sha256(document_bytes).hexdigest(),'document_sha256':hashlib.sha256(output).hexdigest(),'stations_sha256':hashlib.sha256(station_bytes).hexdigest(),'original_graph_restored_after_removal':True,'station_record_numeric_units':'raw zeros from init, not geographic coordinates','model_profile_raw':[2,4,1],'station_end_type':2,'related_half_type_synchronized':True,'related_half_station_explicitly_assigned':True,'recognized_planned_points_only':True,'station_stopping_regions_supported':False,'native_application_executed':False,'simulation_executed':False}
