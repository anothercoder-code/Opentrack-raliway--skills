"""Finite explicit multi-document topology data generation, not operation planning."""
import re
from . import writer as w,catalogs as cats,route_factory as rf
from .zero_generation import topology as tp,native_signal_routes as ns
from .zero_operations import station_binding as sb
from .multi_document import core as cd

def need(ok,msg):
    if not ok:raise ValueError(msg)

def generate_finite_topology(header,shapes,*,expected_hashes,documents,connectors):
    need(type(header)is bytes and type(shapes)is bytes,'Immutable donor bytes required')
    need(expected_hashes=={'header':cd.sha(header),'shapes':cd.sha(shapes)},'Exact donor SHA binding required')
    need(type(documents)is list and 1<=len(documents)<=16,'Tool domain requires 1..16 documents')
    need(type(connectors)is list and len(connectors)<=400,'Tool domain allows at most 400 connector pairs')
    names=[];total_v=total_e=0;station_signs=set()
    for doc in documents:
        need(type(doc)is dict and set(doc)=={'name','network','stations'},'Exact document name/network/stations required')
        name=doc['name'];need(type(name)is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}',name),'Safe logical document name required')
        need(name.casefold() not in [x.casefold()for x in names],'Duplicate document name');names.append(name)
        tp.validate_spec(doc['network']);total_v+=len(doc['network']['vertices']);total_e+=len(doc['network']['edges'])
        need(type(doc['stations'])is list and len(doc['stations'])<=400,'Bounded station list required')
        for st in doc['stations']:
            need(type(st)is dict and set(st)=={'sign','name','vertex','side','placement','timing_point'},'Exact point-station fields required')
            sb.text(st['sign']);need(st['sign'] not in station_signs,'Duplicate project station sign');station_signs.add(st['sign'])
    need(total_v<=400 and total_e<=800,'Tool domain requires at most 400 vertices and 800 edges')
    blobs={};roots={};versions={};byid={};reports={};catalog_rows=[]
    for doc in documents:
        dn=doc['name'];blob,report=tp.generate_network(header,shapes,doc['network']);reports[dn]=report
        station_specs=[]
        for st in doc['stations']:
            need(st['vertex']in report['vertex_end_ids'] and type(st['side'])is int and st['side']in(0,1),'Unknown station vertex/side')
            station_specs.append(dict(sign=st['sign'],name=st['name'],end_ids=[report['vertex_end_ids'][st['vertex']][st['side']]],placement=st['placement'],station_type_raw=2,interlock_type_raw=4,icon_show_type_raw=1,timing_point=st['timing_point']))
        if station_specs:
            blob,cat,_=sb.bind_stations(blob,station_specs)
            catalog_rows.extend(cats.station_items(w.load(cat)[0]).items())
        roots[dn],versions[dn]=w.load(blob);_,byid[dn]=rf.document(roots[dn]);blobs[dn]=blob
    used=set();bindings=[]
    def endpoint(ref):
        need(type(ref)is dict and set(ref)=={'document','vertex','side'},'Exact connector endpoint required')
        dn=ref['document'];need(dn in reports,'Unknown connector document')
        need(ref['vertex']in reports[dn]['vertex_end_ids'] and type(ref['side'])is int and ref['side']in(0,1),'Unknown connector vertex/side')
        mid=reports[dn]['vertex_end_ids'][ref['vertex']][ref['side']];key=(dn,mid)
        need(key not in used,'Connector endpoint reused');used.add(key)
        end=byid[dn][mid];related=byid[dn][end.contents[8].value]
        need(w.kind(end)=='OTEndModel' and end.contents[20].value==1 and all(end.contents[i].value is None for i in(9,10,11,12)) and related.contents[11].value is None,'Connector requires free nonstation ordinary half-end')
        return key,end
    for pair in connectors:
        need(type(pair)is dict and set(pair)=={'a','b'},'Exact connector a/b pair required')
        ka,a=endpoint(pair['a']);kb,b=endpoint(pair['b']);need(ka[0]!=kb[0],'Cross-document pair required')
        for end,target in ((a,kb),(b,ka)):
            end.clazz=w.Class(b'OTConnModel',1,end.clazz)
            end.contents +=[w.TypedValue(b'@',ns.string('')),w.TypedValue(b'@',ns.string(target[0])),w.TypedValue(b'i',target[1]),w.TypedValue(b'i',0)]
        bindings.append({'a':list(ka),'b':list(kb)})
    output={dn:w.dump_verified(root,versions[dn])for dn,root in roots.items()}
    paths={dn:'OTDocuments/'+dn+'.opentrack'for dn in names}
    project=cd.Project(output,document_paths=paths,expected_hashes={dn:cd.sha(blob)for dn,blob in output.items()},complete_document_set=True)
    for pair in bindings:
        a,b=tuple(pair['a']),tuple(pair['b']);need(project.block_end(a)==b and project.block_end(b)==a,'Reciprocal connector reload mismatch')
    
    for dn,blob in output.items():
        root,version=w.load(blob);_,index=rf.document(root)
        for pair in bindings:
            for doc,mid in (pair['a'],pair['b']):
                if doc==dn:index[mid].clazz=index[mid].clazz.superclass;index[mid].contents=index[mid].contents[:24]
        need(w.dump_verified(root,version)==blobs[dn],'Connector rollback changed underlying graph')
    station_blob=w.dump_verified(sb.dictionary(catalog_rows),versions[names[0]])
    need(set(cats.station_items(w.load(station_blob)[0]))==station_signs,'Station catalog reload mismatch')
    members={paths[dn]:blob for dn,blob in output.items()};members['OTData/finite.stations']=station_blob
    return members,{'documents':len(documents),'double_vertices':total_v,'edges':total_e,'station_points':len(station_signs),'connector_pairs':bindings,'vertex_end_ids':{dn:r['vertex_end_ids']for dn,r in reports.items()},'edge_ids':{dn:r['edge_ids']for dn,r in reports.items()},'output_sha256':{k:cd.sha(v)for k,v in members.items()},'fresh_archive_reload_verified':True,'connector_rollback_verified':True,'operating_ready':False,'native_application_executed':False,'scope':'Finite explicit topology and point-station catalog; no routes, paths, vehicles, timetable, run configuration or stopping areas'}
