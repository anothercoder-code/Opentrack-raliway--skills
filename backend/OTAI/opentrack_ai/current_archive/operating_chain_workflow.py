"""Single-document pass-only operating member composition; no filesystem effects."""
from .infrastructure_chain_workflow import compose_infrastructure
from .zero_operations import vehicle_catalogs as vc,operations as op,run_bundle as rb,speed_preferences as sp
from .multi_document import core as cd
from . import writer as w,catalogs as cats,course_factories as cf

def need(ok,msg):
    if not ok:raise ValueError(msg)
SOURCE_KEYS={'header','shapes','depot_template','trains_template','courses_template','timetable_template'}
def compose_operating_chain(sources,*,expected_hashes,infrastructure,vehicles,course_template_id,timetable_template_key,train_types,speed_type,plan,run_configuration):
    need(type(sources)is dict and set(sources)==SOURCE_KEYS and all(type(b)is bytes for b in sources.values()),'Six explicit immutable donor sources required')
    need(expected_hashes=={k:cd.sha(v)for k,v in sources.items()},'Exact complete donor SHA binding required')
    cfg=dict(run_configuration);run_name=cfg.pop('run_filename');rb.relative(run_name);need('/'not in run_name and run_name.endswith('.run'),'Simple run filename required')
    need(set(cfg)=={'execution_root','path_style','output_directory','start_day','start_time','stop_day','stop_time','step'},'Exact run configuration required')
    rb.relative(cfg['output_directory']);a=run_name.casefold();b=cfg['output_directory'].casefold()
    need(a!=b and not a.startswith(b+'/') and not b.startswith(a+'/'),'Output directory overlaps final run member')
    need(cfg['path_style']=='windows','This operating domain requires explicit Windows path style');root=rb.root_path(cfg['execution_root'],cfg['path_style']);doc_member='OTDocuments/'+infrastructure['document_name']+'.opentrack'
    need(infrastructure['document_path']==root+'/'+doc_member,'Infrastructure document_path must match exact run execution-root/member')
    preference,_=sp.replace_train_types(b'',train_types);need(sp.read_train_types(preference)==train_types,'Ordered speed types changed')
    sp.index_for_course(preference,speed_type)
    files,infra=compose_infrastructure(sources['header'],sources['shapes'],expected_hashes={k:expected_hashes[k]for k in('header','shapes')},spec=infrastructure)
    vehicle,vr=vc.generate_vehicle_catalogs(sources['depot_template'],sources['trains_template'],vehicles)
    service_inputs={'courses_template':sources['courses_template'],'timetable_template':sources['timetable_template'],'trains':vehicle['trains'],'depot':vehicle['depot'],'stations':files['OTData/infrastructure.stations'],'document':files[doc_member],'dest':files['OTData/infrastructure.dest'],'run_template':preference}
    services,sr=op.generate_service_catalogs(service_inputs,course_template_id=course_template_id,timetable_template_key=timetable_template_key,document_name=infrastructure['document_name'],plan=plan,speed_type=speed_type)
    members=dict(files);members.update({'OTData/infrastructure.'+role:blob for role,blob in {**vehicle,**services}.items()})
    catalog_paths={role:'OTData/infrastructure.'+role for role in rb.CATALOG_KEYS}
    need(set(members)=={doc_member,*catalog_paths.values()},'Exactly document and six catalog members required')
    run,rr=rb.build_run(members,catalog_paths=catalog_paths,document_paths=[doc_member],train_types=train_types,**cfg)
    bindings=rb.verify_archive_bindings(run,members,catalog_paths=catalog_paths,document_paths=[doc_member]);rb.verify_manifest(run,members,rr)
    
    project=cd.Project({infrastructure['document_name']:members[doc_member]},document_paths={infrastructure['document_name']:infrastructure['document_path']},expected_hashes={infrastructure['document_name']:cd.sha(members[doc_member])},complete_document_set=True);project.check_dest_catalog(members[catalog_paths['dest']])
    saved_courses={cats.text(o.contents[0].value):o for o in cats.course_items(w.load(members[catalog_paths['courses']])[0])};table=cf.timetable(w.load(members[catalog_paths['timetable']])[0])
    need(set(saved_courses)=={p['course_id']for p in plan},'Exact generated Course identities differ')
    need(len(table)==sum(len(p['visits'])for p in plan),'Exact generated timetable row count differs')
    for p in plan:
        course=saved_courses[p['course_id']];need(cats.text(course.contents[3].value)==p['train'] and [cats.text(o)for o in cats.array(course.contents[2].value)]==[p['itinerary']],'Fresh Course references differ')
        for index,visit in enumerate(p['visits']):
            row=table[p['course_id']+'#'+str(index)];sec=visit['absolute_seconds'];day,clock=divmod(sec,86400);h,m=divmod(clock,3600);minute,second=divmod(m,60);formatted=f'{h:02}:{minute:02}:{second:02}'
            need(cats.text(row.contents[1].value)==p['course_id'] and row.contents[3].value==index and cats.text(row.contents[5].value)==visit['station_sign'],'Fresh TT identity/order/station mismatch')
            need(cats.text(row.contents[6].value)==cats.text(row.contents[7].value)==formatted and row.contents[15].values[:2]==[day,day],'Fresh TT absolute clock/day mismatch')
            need(row.contents[10].value==2 and float(cats.text(row.contents[8].value))==0.,'Pass-only flags/dwell mismatch')
    members[run_name]=run;need(len(members)==8,'Eight-member result required')
    return members,{'schema':'single-document-pass-operating-chain/1','source_sha256':expected_hashes,'infrastructure':infra,'vehicles':vr,'services':sr,'run':rr,'cross_file_bindings':bindings,'counts':{'members':8,'documents':1,'catalogs':6,'courses':len(plan),'timetable_rows':len(table),'train_definitions':len(vehicles['train_names'])},'fresh_archive_reload_verified':True,'pass_only':True,'saved':False,'native_application_executed':False,'native_runtime_ready':False,'physical_fleet_circulation_proven':False,'output_sha256':{k:cd.sha(v)for k,v in members.items()},'scope':'Static single-document pass plan and six catalogs/run; not stopping, train circulation, capacity, conflict resolution or native simulation'}
