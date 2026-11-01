"""Read-only actual Course -> Train -> Engine/Trailer binding, finite catalog domain.
No fallback catalogs, source mutation, runtime preparation or physical recalculation.
"""
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.consist_workflow import core as consist
from opentrack_ai.current_archive.zero_operations import run_bundle as rb
from opentrack_ai.current_archive.prepare_contract.auxiliary import records as run_records
from opentrack_ai.current_archive.disturbance_workflow import core as scenario
import hashlib

def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()

def bind(courses_blob,trains_blob,depot_blob,run_bytes,course_path,train_path,depot_path):
    need(type(trains_blob)is bytes and type(depot_blob)is bytes,'Actual immutable TrainFile and DepotFile bytes are required')
    need(type(train_path)is str and type(depot_path)is str,'Explicit native TrainFile/DepotFile paths required')
    root=course_path.rsplit('/',2)[0]
    for label,path in [('TrainFile',train_path),('DepotFile',depot_path)]:
        rb.root_path(path,'windows')
        need(path.rsplit('/',2)[0]==root and path.rsplit('/',2)[1]=='OTData','Vehicle files must use the same native root/OTData layout')
        need([v for k,v,_ in run_records(run_bytes)if k==label]==[path],'Exact unique '+label+' binding required')
    need(len({course_path,train_path,depot_path})==3,'Course/Train/Depot native roles require distinct paths')
    tr,_,dep,trains,engines,categories,_=consist.load(trains_blob,depot_blob)
    summaries={name:consist.summary(obj,engines)for name,obj in trains.items()}
    cr,_=w.load_next_compatible(courses_blob); rows=c.course_items(cr);bindings={}
    need(rows,'Nonempty actual CourseList required')
    for course in rows:
        cid=c.text(course.contents[0].value);name=c.text(course.contents[3].value)
        need(name in trains,'Unresolved Course Train reference: '+cid)
        need(type(course.contents[5].value)is int and course.contents[5].value in (0,1),'Canonical Course enabled flag required')
        info=summaries[name]
        entering_kmh=float(course.contents[1].value)*3.6
        scenario.number(entering_kmh,0,info['maximum_speed_kmh'])
        bindings[cid]={'train_name':name,'enabled':bool(course.contents[5].value),'category':c.text(trains[name].contents[3].value),'entering_speed_kmh':entering_kmh,'formation':info}
    return bindings,{'train_file_sha256':sha(trains_blob),'depot_file_sha256':sha(depot_blob),
      'native_train_path':train_path,'native_depot_path':depot_path,'course_count':len(bindings),
      'train_count':len(trains),'engine_count':len(engines),'category_count':len(categories),
      'courses':bindings,'scope':'All Course references and all catalog formations validated; initial cold static values only.',
      'initial_catalogs_modified':False,'physical_performance_validated':False,'native_simulation_prepared':False}

def validate_event(item,bindings):
    if item['type'] not in ('train_speed','train_tractive_effort','train_power_limit'):return
    cid=item['course_id'];need(cid in bindings and bindings[cid]['enabled'],'Incident must bind an actual enabled Course vehicle')
    if item['type']=='train_speed':
        scenario.number(item['reduced_speed_kmh'],0,bindings[cid]['formation']['maximum_speed_kmh'])
