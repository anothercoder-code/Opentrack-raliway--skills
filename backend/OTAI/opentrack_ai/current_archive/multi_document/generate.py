"""Minimal two-document instructional fixture. New target bytes only.

One StationVertex pair per document; no stopping region or service timetable.
Source Document4 is solely the unmodified opaque header/container donor.
"""
import copy
from pathlib import Path
import json
from .core import *
from opentrack_ai.current_archive.zero_generation import native_signal_routes as ns
from opentrack_ai.current_archive.zero_operations import station_binding as sb, run_bundle as rb
from opentrack_ai.current_archive import catalogs as cats
from opentrack_ai.current_archive.graphic_alignment import make_placement, make_signal_placement


def vertex(key,x):return dict(key=key,x=x,y=30,orientation='horizontal',names=[key+'-left',key+'-right'],insulated_joint=[False,False],axle_counter=[False,False])
def spec():return dict(vertices=[vertex('left',30),vertex('right',230)],edges=[dict(key='track',**{'from':['left',1],'to':['right',0]},length_m=1000,radius_m=0.,gradient_per_mille=0.,track_type=1,loop_type=1,dlink_type=1,equal_speed=True,rack_rail=False,speeds=[dict(train_type='0',speed12_kmh=80,speed21_kmh=80)],remark='',track_name='1',line_name='A-B')])
def placement(x,y):
    return make_placement(x,y)
def signal_placement(end,x,y):
    return make_signal_placement(end,x,y)

def wrapped(kind,items):
    chain=[(kind,0)]+([]if kind=='OTMutableArray'else[('OTMutableArray',0)])+[('NSObject',0)]
    return ns.obj(chain,[('@',[ns.arr(items)])])
def inf(obj,doc=None):
    groups=[('@',[ns.string(ident(obj)[0])]),('ii',list(ident(obj)[1:]))]
    if doc is not None:groups.append(('@',[ns.string(doc)]))
    return ns.obj(([('OTArrayExtInfo',0)]if doc is not None else [])+[('OTArrayInfo',0),('NSObject',0)],groups)
def route(name,aid,start,nodes,continuation,fragment=False):
    groups=[('@',[ns.arr(nodes)]),('@',[ns.string(name)]),('ii',[aid,start]),('@',[ns.string('')]),('@',[None]),('iiiiii',[0,400,5,0,continuation,0]),('iff',[0,40.,0.]),('@',[ns.string('')]),('ff',[0.,0.]),('i',[-1]),('iii',[5000,0,0]),('i',[0]),('@@@',[ns.arr([]if fragment else [nodes[0]]),None,None])]
    r=ns.obj(f.SHAPES['OTRoute'][0],groups)
    ind=ns.obj([('OTSigInd',0),('NSObject',0)],[('i',[0]),('@',[r])])
    r.contents[4].value=wrapped('OTSigIndList',[]if fragment else[ind]);return r

def make_pair(documents,document_paths):
    """Private fixed empty-topology generator stage; not arbitrary connector edit."""
    roots={};versions={};models={};byid={};baseline={}
    for dn,blob in documents.items():
        r,v=w.load(blob);roots[dn]=r;versions[dn]=v;models[dn],byid[dn]=rf.document(r);baseline[dn]=w.dump_verified(r,v)
    for dn,mid,target,tid in [('A',5,'B',0),('B',0,'A',5)]:
        end=byid[dn][mid];rf.layout(end,'OTEndModel',7,rf.END,graphic=True)
        related=byid[dn][end.contents[8].value]
        need(all(end.contents[i].value is None for i in (9,10,11,12)) and related.contents[11].value is None and end.contents[20].value==1,'Boundary is not eligible for native connector')
        need(all(not rf.wrapper(end.contents[i].value,k)for i,k in [(15,'OTRouteList'),(16,'OTShuntingList'),(17,'OTPathList')]),'Preexisting boundary RSP refused')
        end.clazz=w.Class(b'OTConnModel',1,end.clazz)
        end.contents += [w.TypedValue(b'@',ns.string('')),w.TypedValue(b'@',ns.string(target)),w.TypedValue(b'i',tid),w.TypedValue(b'i',0)]
    destrows=[]
    for dn,target,start,local_end,target_end,remote_conn in [('A','B',0,4,4,0),('B','A',5,1,1,5)]:
        owner=byid[dn][start];need(owner.contents[19].value==-1,'Only fresh generated empty owner supported')
        name='R:'+dn+'-'+target
        primary=route(name,0,start,[owner,byid[dn][local_end]],2)
        fragment=route(name,0,start,[byid[target][target_end]],-1,True)
        w.set_elements(owner.contents[15].value.contents[0].value,[primary])
        conn=byid[target][remote_conn];w.set_elements(conn.contents[15].value.contents[0].value,[fragment])
        path=ns.obj(f.SHAPES['OTPath'][0],[('@',[ns.arr([primary])]),('@',[ns.string('P:'+dn+'-'+target)]),('ii',[1,start]),('@',[ns.string('')]),('@',[ns.arr([inf(primary)])])])
        w.set_elements(owner.contents[17].value.contents[0].value,[path]);owner.contents[19].value=1
        dest=ns.obj(f.SHAPES['OTDest'][0],[('@',[ns.arr([path])]),('@',[ns.string('I:'+dn+'-'+target)]),('ii',[-1,-1]),('@',[ns.string('')]),('@',[ns.arr([inf(path,dn)])]),('@',[wrapped('OTSafetyMarginArray',[])])])
        w.set_elements(roots[dn].contents[5].value.contents[0].value,[dest])
        destrows.append(ns.obj([('OTDestInfo',1),('NSObject',0)],[('i',[17]),('@',[ns.string('I:'+dn+'-'+target)]),('@',[ns.string(document_paths[dn])]),('i',[start]),('@',[ns.arr([inf(path,dn)])])]))
    output={dn:w.dump_verified(r,versions[dn])for dn,r in roots.items()}
    project=Project(output,document_paths=document_paths,expected_hashes={k:sha(v)for k,v in output.items()},complete_document_set=True)
    catalog=w.dump_verified(wrapped('OTDestInfoList',destrows),versions['A']);project.check_dest_catalog(catalog)
    
    
    for dn in output:
        r,v=w.load(output[dn]);ms,ids=rf.document(r)
        connector=ids[5 if dn=='A'else 0];connector.clazz=connector.clazz.superclass;connector.contents=connector.contents[:24]
        for e in (m for m in ms if w.kind(m)=='OTEndModel'):
            for i in (15,17):w.set_elements(e.contents[i].value.contents[0].value,[])
            e.contents[19].value=-1
        w.set_elements(r.contents[5].value.contents[0].value,[])
        need(w.dump_verified(r,v)==baseline[dn],'Whole-graph rollback preservation failed')
    return output,catalog,project.report()

def empty_catalog(blob,role):
    root,v=w.load(blob)
    if role=='depot':cats.engine_items(root);w.set_elements(root,[])
    elif role=='courses':
        cats.course_items(root)
        for i in (1,2,3,4):w.set_elements(root.contents[i].value,[])
    elif role=='trains':
        cats.train_items(root)
        for i in (1,2,3):w.set_elements(root.contents[i].value,[])
    elif role=='timetable':
        need(w.kind(root)=='NSMutableDictionary','Current timetable dictionary required');root.contents=[w.TypedValue(b'i',0)]
    else:raise CrossDocumentError('Unsupported empty catalog role')
    return w.dump_verified(root,v)

def generate(header_document,shapes,catalog_templates,*,execution_root,run_template=b''):
    need(type(header_document)is bytes and type(shapes)is bytes,'Immutable source bytes required')
    need(set(catalog_templates)=={'depot','trains','courses','timetable'},'Four current catalog shape donors required')
    rb.root_path(execution_root,'windows')
    documents={};pre_connect={};station_roots=[];steps=[]
    for dn,station_ends,signal_ends in [('A',[0],[0,1]),('B',[4],[4,5])]:
        blob,report=tp.generate_network(header_document,shapes,spec());steps.append(report)
        for eid in signal_ends:
            root,_=w.load(blob);models,byid=rf.document(root)
            blob,rep=ns.build_main_signal(blob,end_id=eid,name='S:'+dn+':'+str(eid),model_id=max(m.contents[0].value for m in models)+1,placement=signal_placement(byid[eid],30 if dn=='A'else 230,20),sight_m=500,delay_s=0.,show_symbol=True,show_icon=True);steps.append(rep)
        blob,stations,rep=sb.bind_stations(blob,[dict(sign=dn,name='Station '+dn,end_ids=station_ends,placement=placement(30 if dn=='A'else 230,50),station_type_raw=2,interlock_type_raw=4,icon_show_type_raw=1,timing_point=False)]);steps.append(rep)
        documents[dn]=blob;pre_connect[dn]=blob;station_roots.append(w.load(stations)[0])
    paths={dn:execution_root+'/OTDocuments/'+dn+'.opentrack'for dn in documents}
    documents,dest,reconstruction=make_pair(documents,paths)
    stations=sb.dictionary([(dn,cats.station_items(r)[dn])for dn,r in zip(('A','B'),station_roots)])
    stations=w.dump_verified(stations,1000)
    files={'OTDocuments/'+dn+'.opentrack':b for dn,b in documents.items()};catalog_paths={r:'OTData/example.'+r for r in rb.CATALOG_KEYS}
    for role in rb.CATALOG_KEYS:
        files[catalog_paths[role]]=dest if role=='dest'else stations if role=='stations'else empty_catalog(catalog_templates[role],role)
    run,run_receipt=rb.build_run(files,catalog_paths=catalog_paths,document_paths=list('OTDocuments/'+dn+'.opentrack'for dn in documents),execution_root=execution_root,path_style='windows',train_types=['instructional'],template=run_template)
    rb.verify_run(run,files,catalog_paths=catalog_paths,document_paths=['OTDocuments/A.opentrack','OTDocuments/B.opentrack'],execution_root=execution_root,path_style='windows',train_types=['instructional'])
    files['cross-document.run']=run
    from .bundle import validate_no_service_bundle
    validated_bundle=validate_no_service_bundle(files,run_file='cross-document.run',expected_hashes={k:sha(v)for k,v in files.items()},complete_file_set=True)
    return files,dict(operation='generate_minimal_two_document_station_vertices',source_sha256={'header':sha(header_document),'shapes':sha(shapes),**{k:sha(v)for k,v in catalog_templates.items()}},members={k:{'sha256':sha(v),'bytes':len(v)}for k,v in files.items()},document_paths=paths,reconstruction=reconstruction,steps=steps,run=run_receipt,bundle_validation=validated_bundle,one_station_per_document=True,bidirectional_connector_pair=True,original_header_opaque_fields_preserved=True,preconnector_full_graph_rollback_verified=True,native_runtime_fields_fabricated=False,connector_creation='explicit saved-schema synthesis retaining generated local IDs; not native GUI allocation/deletion history',fragment_safety_profile='native fetch construction: empty indication/groups/zones; existing edited fragments may differ',native_application_executed=False,simulation_executed=False,service_catalogs_empty=True,operating_simulation_ready=False,station_stopping_regions_supported=False,atomic_group_publication_required=True,scope='Static linked infrastructure + Routes/Paths/Itineraries and explicit complete no-service project; native acceptance unverified'),pre_connect

if __name__=='__main__':
    base=Path(__file__).resolve().parent;inputs=base/'inventory/inputs';wave=base.parent/'opentrack-wave12/OTAI'
    sources={k:(inputs/('BJTU_demo.'+k)).read_bytes()for k in ('depot','trains','courses','timetable')}
    files,report,baselines=generate((inputs/'BJTU1.opentrack').read_bytes(),(wave/'resources/native-shapes.archive').read_bytes(),sources,execution_root='C:/OpenTrackProjects/TwoStations')
    out=base/'outputs/one-station-per-document';need(not out.exists(),'Fresh target only; no overwrite');out.mkdir(parents=True)
    for p,b in files.items():target=out/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
    for dn,b in baselines.items():(out/(dn+'.preconnector.opentrack')).write_bytes(b)
    (out/'receipt.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items()if k not in ('steps','reconstruction','run')},indent=2))
