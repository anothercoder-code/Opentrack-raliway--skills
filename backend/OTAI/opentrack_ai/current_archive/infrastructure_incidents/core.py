"""Finite Incident12 periodic and named-duration data; no runtime/sampling/writes."""
import hashlib,re
from opentrack_ai.current_archive import writer as w, catalogs as c, incident_operations as old
from opentrack_ai.current_archive.disturbance_workflow import core as scenario
from opentrack_ai.current_archive.incident_source import validate_set_graph
from opentrack_ai.current_archive.incident_set_workflow import core as sets
from opentrack_ai.current_archive.multi_document.core import Project
from opentrack_ai.current_archive.disturbance_tools import run_window, absolute
from opentrack_ai.current_archive.zero_operations import run_bundle as rb
from opentrack_ai.current_archive.prepare_contract.auxiliary import records as run_records

class InfrastructureIncidentError(ValueError): pass
def need(ok,msg):
    if not ok:raise InfrastructureIncidentError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
TYPES={'train_speed':1,'signal_blockage':2,'edge_blockage':3,'route_speed':4,'path_speed':5,'edge_group_blockage':9,'signal_headway':10,'signal_stop':11,'train_tractive_effort':12,'train_power_limit':14}
FIELDS={'name','type','document','model_id','begin_time','end_time','begin_day','end_day','enabled','probability_percentage'}

def binding(documents,document_paths,run_bytes,course_path):
    need(type(documents)is dict and 1<=len(documents)<=32,'1..32 immutable documents required')
    need(type(document_paths)is dict and set(documents)==set(document_paths),'Complete document paths required')
    need(type(run_bytes)is bytes and type(course_path)is str,'Explicit run bytes/course path required')
    window=run_window(run_bytes)
    rows=run_records(run_bytes)
    values=[v for k,v,_ in rows if k=='CourseFile'];need(values==[course_path],'Exact selected CourseFile binding required')
    rb.root_path(course_path,'windows')
    root=course_path.rsplit('/',2)[0]
    need('/OTData/' in course_path and course_path.rsplit('/',2)[1]=='OTData','CourseFile must use bounded OTData layout')
    need(all(document_paths[k]==root+'/OTDocuments/'+k+'.opentrack' for k in documents),'Documents must use selected common root/OTDocuments layout')
    declared=[v for k,v,_ in rows if k=='Infrastructure Document']
    need(len(declared)==len(documents) and set(declared)==set(document_paths.values()),'All selected-run infrastructure documents must be supplied exactly')
    p=Project(documents,document_paths=document_paths,expected_hashes={k:sha(v)for k,v in documents.items()},complete_document_set=True)
    return p,window

def target(p,dn,mid,typ):
    need(type(dn)is str and dn in p.byid,'Unknown exact document namespace')
    need(type(mid)is int and 0<=mid<=2147483647,'Nonnegative canonical model ID required')
    obj=p.byid[dn].get(mid)
    need(obj is not None and w.kind(obj)==('OTSignalModel' if typ==2 else 'OTEdgeModel'),'Target model class does not match incident type')
    if typ==2:
        e=obj.contents[7].value
        need(e in p.models[dn] and e.contents[11].value is obj,'Signal directional-End identity mismatch')
    else:
        need(all(e in p.models[dn] and obj in [e.contents[i].value for i in (9,10)] for e in [obj.contents[j].value for j in (7,8)]),'Edge endpoint identity mismatch')
    return obj

COMMON={'name','type','begin_time','end_time','begin_day','end_day','enabled','probability_percentage'}
EXTRA={1:{'course_id','reduced_speed_kmh'},2:{'document','model_id'},3:{'document','model_id'},
 4:{'document','start_end_id','array_id','reduced_speed_kmh'},5:{'document','start_end_id','array_id','reduced_speed_kmh'},
 9:{'document','model_ids'},10:{'document','model_ids','headway_s'},
 11:{'document','model_id','stop_probability_percentage','stop_duration_s'},
 12:{'course_id','tractive_effort_factor'},14:{'course_id','limited_power_kw'}}

def integer(n):
    need(type(n)is int and 0<=n<=2147483647,'Nonnegative int32 identity required');return n

def number_object(n):
    return w.GenericArchivedObject(w.Class(b'NSNumber',0,w.Class(b'NSValue',0,w.Class(b'NSObject',0))),[
      w.TypedValue(b'*',w.CString(w.SharedString(b'i'))),w.TypedValue(b'i',integer(n))])

def number_value(obj):
    need(w.kind(obj)=='NSNumber' and obj.clazz.version==0 and [g.encodings for g in obj.contents]==[[b'*'],[b'i']],'Canonical NSNumber0 int layout required')
    cl=obj.clazz.superclass
    need(cl is not None and cl.name==b'NSValue' and cl.version==0 and cl.superclass is not None and cl.superclass.name==b'NSObject' and cl.superclass.version==0 and cl.superclass.superclass is None,'NSNumber inheritance')
    token=obj.contents[0].value
    need(isinstance(token,w.CString) and token.token.data==b'i','Canonical int NSNumber required')
    return integer(obj.contents[1].value)

PERIOD_FIELDS={'occupied1_s','free1_s','occupied2_s','free2_s'}
def period_values(value):
    need(type(value)is dict and set(value)==PERIOD_FIELDS,'Exact four named periodic seconds required')
    out=[scenario.number(value[k],0,86400)for k in ('occupied1_s','free1_s','occupied2_s','free2_s')]
    need(out[0]>0,'First occupied interval must be positive: finite periodic policy')
    need(out[2]>0 or out[3]==0,'Disabled second interval requires both second values zero')
    return out

def named_reference(root,name):
    scenario.name(name)
    lib=scenario.nd.catalog(root);need(name in lib,'Exact existing CourseList distribution required')
    obj=lib[name];need(obj.contents[1].value==1,'Only piecewise-linear distribution supported')
    scenario.nd.exclusive(root,obj)
    need(scenario.nd.validity([r.contents[0].values for r in scenario.nd.interval_array(obj.contents[2].value)[1]])['passes_api_guard'],'Invalid named distribution table')

def validate(item,p,window,root):
    need(type(item)is dict and type(item.get('type'))is str and item['type']in TYPES,'Unsupported Incident type; 6/7/8/13 spatial from-to contracts not implemented')
    typ=TYPES[item['type']]
    fields=COMMON|EXTRA[typ]
    for key in ('begin_distribution','duration_distribution'):
        if key in item:
            fields=fields|{key}
            need(type(item[key])is str,'Explicit distribution reference string required')
            if item[key]:named_reference(root,item[key])
    if 'discrete_moving_block' in item:
        fields=fields|{'discrete_moving_block'}
        need(typ in (1,4,5,12,14) and type(item['discrete_moving_block'])is bool,'Discrete flag only finite types1/4/5/12/14 boolean')
    if 'periodic' in item:fields=fields|{'periodic'};period_values(item['periodic'])
    if typ==11 and 'stop_duration_distribution' in item:
        fields=(fields-{'stop_duration_s'})|{'stop_duration_distribution'}
    need(set(item)==fields,'Exact type-specific fields required')
    scenario.name(item['name']);scenario.day(item['begin_day']);scenario.day(item['end_day'])
    start=absolute(item['begin_time'],item['begin_day']);end=absolute(item['end_time'],item['end_day'])
    need(window[0]<=start<=end<=window[1],'Event outside selected run window')
    need(type(item['enabled'])is bool,'Explicit boolean Use required')
    scenario.number(item['probability_percentage'],0,100)
    if typ in (2,3,11):target(p,item['document'],item['model_id'],2 if typ==11 else typ)
    elif typ in (4,5):
        dn=item['document'];need(type(dn)is str and dn in p.byid,'Unknown document namespace')
        start=integer(item['start_end_id']);aid=integer(item['array_id']);owner=p.byid[dn].get(start)
        need(owner is not None and w.kind(owner)=='OTEndModel','Canonical original End owner required; continuation connector refused')
        slot=15 if typ==4 else 17;wrapper='OTRouteList' if typ==4 else 'OTPathList'
        from opentrack_ai.current_archive import route_factory as rf
        matches=[o for o in rf.wrapper(owner.contents[slot].value,wrapper)if o.contents[2].values==[aid,start]]
        need(len(matches)==1 and p.owners.get(id(matches[0]))==(dn,start),'Exact RSP owner/start/array identity required')
        scenario.number(item['reduced_speed_kmh'],0,10000)
    elif typ in (9,10):
        ids=item['model_ids'];need(type(ids)is list and 1<=len(ids)<=256,'1..256 ordered group target IDs required')
        need(all(type(x)is int for x in ids) and len(set(ids))==len(ids),'Distinct canonical group IDs required')
        for mid in ids:target(p,item['document'],mid,3 if typ==9 else 2)
        if typ==10:scenario.number(item['headway_s'],0,86400)
    else:
        course=item['course_id'];scenario.name(course)
        matches=[o for o in c.course_items(root)if c.text(o.contents[0].value)==course]
        need(len(matches)==1 and matches[0].contents[5].value==1,'Exact enabled Course reference required')
        if typ==1:scenario.number(item['reduced_speed_kmh'],0,10000)
        elif typ==12:scenario.number(item['tractive_effort_factor'],0,1)
        else:
            x=scenario.number(item['limited_power_kw'],0,1000000000);need(x>0,'Positive finite kW policy required; zero power not implemented')
    if typ==11:
        scenario.number(item['stop_probability_percentage'],0,100)
        if 'stop_duration_distribution' in item:
            name=item['stop_duration_distribution'];scenario.name(name)
            need(re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',name)is None,'Numeric-looking distribution names are ambiguous')
            lib=scenario.nd.catalog(root);need(name in lib,'Exact existing CourseList distribution required')
            obj=lib[name];need(obj.contents[1].value==1,'Only piecewise-linear named duration supported')
            scenario.nd.exclusive(root,obj)
            need(scenario.nd.validity([r.contents[0].values for r in scenario.nd.interval_array(obj.contents[2].value)[1]])['passes_api_guard'],'Invalid named duration table')
        else:
            duration=scenario.number(item['stop_duration_s'],0,86400)
            need(format(duration,'.9g') not in scenario.nd.catalog(root),'Numeric duration shadowed by existing named distribution')
    return typ

def create(item,arr):
    typ=TYPES[item['type']]
    groupids=w.GenericArchivedObject(arr.clazz,[]);w.set_elements(groupids,[number_object(n)for n in item.get('model_ids',[])])
    cid=item.get('course_id','0');dn=item.get('document','0')
    vals=[[old.string(x)]for x in (item['name'],cid,dn,item['begin_time'],item['end_time'])]
    aid=item.get('array_id',-1);start=item.get('start_end_id',item.get('model_id',-1))
    perf=[scenario.number(item.get('reduced_speed_kmh',0),0,10000),scenario.number(item.get('tractive_effort_factor',1),0,1),0.,0.]
    vals += [[aid,start,typ],perf,[int(item['enabled'])|(8 if 'periodic' in item else 0)|(4 if item.get('discrete_moving_block',False) else 0)]]
    vals += [[old.string('')]for _ in range(6)]
    
    duration='' if typ!=11 else (item['stop_duration_distribution'] if 'stop_duration_distribution' in item else format(scenario.number(item['stop_duration_s'],0,86400),'.9g'))
    vals += [[scenario.number(item.get('headway_s',0),0,86400)],[item['begin_day'],item['end_day']],[old.string('')],period_values(item['periodic']) if 'periodic' in item else [0.]*4,[old.string(item.get('duration_distribution',''))],[scenario.number(item['probability_percentage'],0,100)],[groupids],[old.string(item.get('begin_distribution',''))],[scenario.number(item.get('stop_probability_percentage',100),0,100)],[old.string(duration)],[scenario.number(item['limited_power_kw'],0,1000000000)if typ==14 else -1.]]
    return w.GenericArchivedObject(w.Class(b'OTIncident',12,w.Class(b'NSObject',0)),[w.TypedGroup([x.encode()for x in enc],value)for enc,value in zip(old.SCHEMA,vals)])

def item_from_object(o):
    typ=o.contents[5].values[2];need(type(typ)is int and typ in EXTRA,'Unsupported source incident type')
    item=dict(name=c.text(o.contents[0].value),type=next(k for k,v in TYPES.items()if v==typ),begin_time=c.text(o.contents[3].value),end_time=c.text(o.contents[4].value),begin_day=o.contents[15].values[0],end_day=o.contents[15].values[1],enabled=bool(o.contents[7].value & 1),probability_percentage=float(o.contents[19].value))
    need(type(o.contents[7].value)is int and o.contents[7].value in (0,1,4,5,8,9,12,13),'Only Use, proven discrete and periodic flags supported')
    if o.contents[7].value & 4:item['discrete_moving_block']=True
    for key,group in [('begin_distribution',21),('duration_distribution',18)]:
        ref=c.text(o.contents[group].value)
        if ref:item[key]=ref
    if o.contents[7].value & 8:item['periodic']=dict(zip(('occupied1_s','free1_s','occupied2_s','free2_s'),map(float,o.contents[17].values)))
    if typ not in (1,12,14):item['document']=c.text(o.contents[2].value)
    if typ in (2,3,11):item['model_id']=o.contents[5].values[1]
    if typ in (4,5):item.update(start_end_id=o.contents[5].values[1],array_id=o.contents[5].values[0],reduced_speed_kmh=float(o.contents[6].values[0]))
    if typ in (9,10):item['model_ids']=[number_value(x)for x in c.array(o.contents[20].value)]
    if typ==10:item['headway_s']=float(o.contents[14].value)
    if typ==11:
        raw=c.text(o.contents[23].value)
        item['stop_probability_percentage']=float(o.contents[22].value)
        if re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?',raw):item['stop_duration_s']=float(raw)
        else:item['stop_duration_distribution']=raw
    if typ in (1,12,14):item['course_id']=c.text(o.contents[1].value)
    if typ==1:item['reduced_speed_kmh']=float(o.contents[6].values[0])
    if typ==12:item['tractive_effort_factor']=float(o.contents[6].values[1])
    if typ==14:item['limited_power_kw']=float(o.contents[24].value)
    return item

def state(blob,p,window):
    need(type(blob)is bytes,'Immutable CourseList bytes required')
    root,v=w.load_next_compatible(blob);c.course_items(root)
    incidents,groups=validate_set_graph(root);need(root.contents[0].value==17,'CourseList marker17 required')
    seen=set()
    for obj in incidents:
        c.shape(obj,'OTIncident',12,old.SCHEMA)
        n=c.text(obj.contents[0].value);scenario.name(n);need(n not in seen,'Duplicate Incident name');seen.add(n)
        item=item_from_object(obj);validate(item,p,window,root)
        expected=create(item,root.contents[1].value)
        need(w.fingerprint(obj)==w.fingerprint(expected),'Noncanonical or unsupported source Incident fields/alias/flags')
    check,_=w.load_next_compatible(blob)
    keep=[o for o in c.array(check.contents[1].value)if o.contents[5].values[2]==1];ids={id(o)for o in keep}
    w.set_elements(check.contents[1].value,keep)
    for s in c.array(check.contents[2].value):w.set_elements(s.contents[0].value,[o for o in c.array(s.contents[0].value)if id(o)in ids])
    
    
    for obj in keep:
        obj.contents[7].value &= 1
        obj.contents[17].values=[0.]*4
    scenario.state(w.dump_verified(check,v))
    return root,v,incidents,groups

def plan(blob,documents,spec,*,document_paths,run_bytes,course_path,trains_blob=None,depot_blob=None,train_path=None,depot_path=None):
    need(type(spec)is dict and set(spec)=={'incidents','set_actions'},'Exact incidents/set_actions required')
    items=spec['incidents'];actions=spec['set_actions']
    need(type(items)is list and len(items)<=100 and type(actions)is list and len(actions)<=100 and (items or actions),'Bounded nonempty incident/set action plan required')
    p,window=binding(documents,document_paths,run_bytes,course_path)
    from . import vehicle_binding
    vehicles,vehicle_receipt=vehicle_binding.bind(blob,trains_blob,depot_blob,run_bytes,course_path,train_path,depot_path)
    root,v,incidents,groups=state(blob,p,window)
    for incident in incidents:vehicle_binding.validate_event(item_from_object(incident),vehicles)
    names={c.text(o.contents[0].value)for o in incidents}
    for item in items:
        validate(item,p,window,root)
        vehicle_binding.validate_event(item,vehicles)
        need(item['name']not in names,'Incident name collision');names.add(item['name'])
        incidents.append(create(item,root.contents[1].value))
    w.set_elements(root.contents[1].value,incidents);out=w.dump_verified(root,v);state(out,p,window)
    sr=None
    if actions:
        out,sr=sets.plan(out,{'actions':actions},validator=lambda b:state(b,p,window))
        sr['scope']='Initialized IncidentSets over validated Incident1/2/3/4/5/9/10/11/12/14; data only'
    fresh,_,incs,ss=state(out,p,window)
    
    a,_=w.load_next_compatible(blob);b,_=w.load_next_compatible(out)
    for g in (a,b):w.set_elements(g.contents[1].value,[]);w.set_elements(g.contents[2].value,[])
    need(w.fingerprint(a)==w.fingerprint(b),'Non-target catalog graph changed')
    return out,{'source_sha256':sha(blob),'output_sha256':sha(out),'document_sha256':{k:sha(x)for k,x in documents.items()},'run_sha256':sha(run_bytes),'incident_count':len(incs),'added_names':[i['name']for i in items],'types_supported':{**{str(v):k for k,v in TYPES.items()}},'sets':sr,'run_window_s':window,'saved':False,'native_runtime_ready':False,'sampling_executed':False,'runtime_validated':False,'random_time_window_verified':False,'train_file_dependency_verified':True,'engine_depot_dependency_verified':True,'vehicle_dependencies':vehicle_receipt,'speed_guard_policy':'Train speed incident and Course entry speed must not exceed the resolved static consist speed; API guard, not native clamp','duration_distribution_overrides_end_time':True,'distribution_fields':{'begin_distribution':21,'duration_distribution':18,'stop_duration_distribution':23},'limitations':['No runtime occupancy/trigger success proof.','Types6/7/8/13 and head-only flag refused; finite periodic and typed discrete flags plus existing piecewise-linear references only; no runtime sampling.','Legacy Train-only previews remain type1-only; this document-bound tool validates supported mixed types.','Legacy v9/v10 real examples plus current12 coder evidence; no native current12 execution.']}
