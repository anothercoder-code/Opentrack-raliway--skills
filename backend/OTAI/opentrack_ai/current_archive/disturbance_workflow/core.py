"""Finite Train Incident12 scenario storage. Pure bytes; never samples or runs events."""
import hashlib, math
from opentrack_ai.current_archive import writer as w, catalogs as c, incident_operations as old, named_distributions as nd
from opentrack_ai.current_archive.incident_source import validate_set_graph
class ScenarioError(ValueError): pass
def need(x,msg):
    if not x: raise ScenarioError(msg)
def name(x):
    need(type(x)is str and 0<len(x)<=200 and all(32<=ord(k)<127 for k in x) and '#' not in x,'Printable nonempty name without # required');return x
def number(x,lo,hi):
    need(type(x)in(int,float) and math.isfinite(x) and lo<=x<=hi,'Number outside finite policy domain')
    return nd.float32(x)
def day(x):
    need(type(x)is int and 0<=x<=6,'Day offset must be 0..6');return x
def seconds(t):
    old.time(t);h,m,s=map(int,t.split(':'));return h*3600+m*60+s
def state(blob):
    root,v=w.load_next_compatible(blob);c.course_items(root)
    need(root.contents[0].value==17,'Marker17 required')
    validate_set_graph(root)
    
    lib=nd.catalog(root)
    for n,obj in lib.items():
        name(n);need(obj.contents[1].value==1,'Only piecewise-linear named distributions supported')
        nd.exclusive(root,obj)
        need(nd.validity([r.contents[0].values for r in nd.interval_array(obj.contents[2].value)[1]])['passes_api_guard'],'Invalid source distribution table')
    
    
    check,_=w.load_next_compatible(blob)
    
    
    w.set_elements(check.contents[2].value,[])
    for obj in c.array(check.contents[1].value):
        c.shape(obj,'OTIncident',12,old.SCHEMA)
        bd,ed=obj.contents[15].values;day(bd);day(ed)
        b=seconds(c.text(obj.contents[3].value))+86400*bd;e=seconds(c.text(obj.contents[4].value))+86400*ed
        need(b<=e,'Reversed absolute incident window')
        number(float(obj.contents[19].value),0,100)
        for g in (18,21):
            ref=c.text(obj.contents[g].value);need(ref=='' or ref in lib,'Missing named distribution')
            obj.contents[g].value=old.string('')
        obj.contents[15].values=[0,0];obj.contents[3].value=old.string('00:00:00');obj.contents[4].value=old.string('23:59:59');obj.contents[19].value=100.
    old.state(w.dump_verified(check,v))
    return root,v,lib

def distribution(spec):
    need(type(spec)is dict and set(spec)=={'name','intervals'},'Distribution exact name/intervals required');name(spec['name'])
    vals=nd.parse_rows(spec['intervals']);nd.validate_policy(vals,'piecewise_linear_guard')
    def cls(n,v=0,s=None):return w.Class(n.encode(),v,s or w.Class(b'NSObject',0))
    arr=w.GenericArchivedObject(cls('NSMutableArray',0,cls('NSArray',0)),[]);w.set_elements(arr,[w.GenericArchivedObject(cls('OTDelayInterval'),[w.TypedGroup([b'f']*3,x)]) for x in vals])
    wrapper=w.GenericArchivedObject(cls('OTDelayIntervalArray',0,cls('OTMutableArray')),[w.TypedValue(b'@',arr)])
    return w.GenericArchivedObject(cls('OTDistribution',1),[w.TypedValue(b'@',old.string(spec['name'])),w.TypedValue(b'i',1),w.TypedValue(b'@',wrapper)])

FIELDS={'name','course_id','begin_time','end_time','begin_day','end_day','enabled','reduced_speed_kmh','probability_percentage','begin_distribution','duration_distribution'}
def plan(blob,spec):
    need(type(blob)is bytes,'Immutable source bytes required')
    need(type(spec)is dict and set(spec)=={'incidents','distributions'},'Exact incidents/distributions spec required')
    need(type(spec['incidents'])is list and 1<=len(spec['incidents'])<=1000,'1..1000 incidents required')
    need(type(spec['distributions'])is list and len(spec['distributions'])<=100,'At most 100 new tables')
    root,v,lib=state(blob);before=w.fingerprint(root);incidents=c.array(root.contents[1].value);names={c.text(x.contents[0].value)for x in incidents};library=c.array(root.contents[3].value)
    for ds in spec['distributions']:
        obj=distribution(ds);n=ds['name'];need(n not in lib,'Distribution name collision');library.append(obj);lib[n]=obj
    w.set_elements(root.contents[3].value,library)
    
    
    factory,_=w.load_next_compatible(blob)
    
    w.set_elements(factory.contents[2].value,[]);w.set_elements(factory.contents[1].value,[])
    for item in spec['incidents']:
        need(type(item)is dict and set(item)==FIELDS,'Exact incident fields required')
        name(item['name']);name(item['course_id']);need(item['name']not in names,'Incident name collision');names.add(item['name'])
        bd=day(item['begin_day']);ed=day(item['end_day']);b=seconds(item['begin_time'])+86400*bd;e=seconds(item['end_time'])+86400*ed;need(b<=e,'Reversed absolute incident window')
        p=number(item['probability_percentage'],0,100);speed=number(item['reduced_speed_kmh'],0,10000)
        need(type(item['enabled'])is bool,'Boolean enabled required')
        for k in ('begin_distribution','duration_distribution'):need(type(item[k])is str and (item[k]=='' or item[k]in lib),'Unknown distribution binding')
        baseline=old.create_train_incident(w.dump_verified(factory,v),name=item['name'],course_id=item['course_id'],begin_time='00:00:00',end_time='23:59:59',enabled=item['enabled'],reduced_speed_kmh=speed)
        ir,_=w.load_next_compatible(baseline);obj=c.array(ir.contents[1].value)[0]
        obj.contents[3].value=old.string(item['begin_time']);obj.contents[4].value=old.string(item['end_time']);obj.contents[15].values=[bd,ed];obj.contents[19].value=p
        obj.contents[18].value=old.string(item['duration_distribution']);obj.contents[21].value=old.string(item['begin_distribution']);incidents.append(obj)
    w.set_elements(root.contents[1].value,incidents);out=w.dump_verified(root,v);fresh,_,_=state(out)
    src,_=w.load_next_compatible(blob)
    for g in (2,4):need(w.fingerprint(src.contents[g].value)==w.fingerprint(fresh.contents[g].value),'Protected group changed')
    for n,obj in nd.catalog(src).items():need(w.fingerprint(obj)==w.fingerprint(nd.catalog(fresh)[n]),'Existing distribution changed')
    old_count=len(c.array(src.contents[1].value))
    for i,obj in enumerate(c.array(src.contents[1].value)):need(w.fingerprint(obj)==w.fingerprint(c.array(fresh.contents[1].value)[i]),'Existing incident changed')
    report={'source_sha256':hashlib.sha256(blob).hexdigest(),'output_sha256':hashlib.sha256(out).hexdigest(),'added_incidents':spec['incidents'],'added_distribution_names':[x['name']for x in spec['distributions']],'source_incidents_preserved':old_count,'random_time_window_verified':False,'sampling_executed':False,'runtime_validated':False,'incident_sets_supported':True,'preserved_incident_set_count':len(c.array(fresh.contents[2].value)),'scope':'Train type1, days0..6, probability and named piecewise-linear start/duration references; no sampling', 'duration_distribution_overrides_end_time':True}
    return out,report
