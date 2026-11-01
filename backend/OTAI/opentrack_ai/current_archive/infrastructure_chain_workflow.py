"""Single-document infrastructure synthesis through immutable byte stages."""
import re
from . import writer as w,catalogs as cats,path_functions as pf,route_factory as rf
from .zero_generation import topology as tp,native_signal_routes as ns
from .zero_operations import station_binding as sb
from .multi_document import core as cd,operations as ops,generate as g
from .graphic_alignment import reject_legacy_alignment

def need(ok,msg):
    if not ok:raise ValueError(msg)

def compose_infrastructure(header,shapes,*,expected_hashes,spec):
    need(type(header)is bytes and type(shapes)is bytes,'Immutable donor bytes required')
    need(expected_hashes=={'header':cd.sha(header),'shapes':cd.sha(shapes)},'Exact donor SHA binding required')
    need(type(spec)is dict and set(spec)=={'document_name','document_path','network','stations','signals','routes','paths','itineraries'},'Exact single-document specification required')
    name=spec['document_name'];need(type(name)is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}',name),'Safe document name required')
    need(cd.stem(spec['document_path'])==name,'Authoritative document path basename must match')
    for field in('signals','routes','paths','itineraries'):
        rows=spec[field];need(type(rows)is list and 1<=len(rows)<=100,'Explicit bounded nonempty '+field+' required')
        names=[r['name']for r in rows];need(len(names)==len(set(names)),'Duplicate '+field+' name')
    need(type(spec['stations'])is list and len(spec['stations'])<=100,'Bounded point-station list required')
    tp.validate_spec(spec['network']);need(len(spec['network']['vertices'])<=400 and len(spec['network']['edges'])<=800,'Finite infrastructure size exceeded')
    blob,top=tp.generate_network(header,shapes,spec['network']);ids=top['vertex_end_ids'];vertices={v['key']:v for v in spec['network']['vertices']};stage=[]
    def end(ref):
        need(type(ref)is dict and set(ref)=={'vertex','side'} and ref['vertex']in ids and type(ref['side'])is int and ref['side']in(0,1),'Exact known vertex/side required')
        return ids[ref['vertex']][ref['side']]
    for signal in spec['signals']:
        reject_legacy_alignment(signal)
        need(set(signal)=={'name','end','angle','alignment_x','alignment_y','sight_m','delay_s','show_symbol','show_icon'},'Exact signal fields required')
        eid=end(signal['end']);v=vertices[signal['end']['vertex']];_,_,_,index=ns.document(blob)
        blob,r=ns.build_main_signal(blob,end_id=eid,name=signal['name'],model_id=max(index)+1,placement={'x':v['x'],'y':v['y'],**{k:signal[k]for k in('angle','alignment_x','alignment_y')}},**{k:signal[k]for k in('sight_m','delay_s','show_symbol','show_icon')});stage.append(r)
    routes={}
    for route in spec['routes']:
        need(set(route)=={'name','ends','description','release_groups','reserve_previous'},'Exact Route fields required')
        blob,r=ns.build_route(blob,end_ids=[end(x)for x in route['ends']],**{k:route[k]for k in('name','description','release_groups','reserve_previous')});routes[route['name']]={'document':name,**{k:r[k]for k in('name','array_id','start_id')}};stage.append(r)
    version=w.load(blob)[1];station_blob=w.dump_verified(sb.dictionary([]),version)
    if spec['stations']:
        station_specs=[]
        for st in spec['stations']:
            need(set(st)=={'sign','name','vertex','side','placement','timing_point'},'Exact point-station fields required')
            station_specs.append(dict(sign=st['sign'],name=st['name'],end_ids=[end({k:st[k]for k in('vertex','side')})],placement=st['placement'],timing_point=st['timing_point'],station_type_raw=2,interlock_type_raw=4,icon_show_type_raw=1))
        blob,station_blob,r=sb.bind_stations(blob,station_specs);stage.append(r)
    documents={name:blob};docpaths={name:spec['document_path']};catalog=w.dump_verified(g.wrapped('OTDestInfoList',[]),version);paths={}
    def hashes():return {**{k:cd.sha(v)for k,v in documents.items()},'$dest_catalog':cd.sha(catalog)}
    for path in spec['paths']:
        need(set(path)=={'name','routes'},'Exact Path name/routes required')
        need(type(path['routes'])is list and all(x in routes for x in path['routes']),'Unknown selected Route name')
        documents,r=ops.create_path(documents,catalog,document_paths=docpaths,expected_hashes=hashes(),complete_document_set=True,name=path['name'],routes=[routes[x]for x in path['routes']]);paths[path['name']]=r['created'];stage.append(r)
    for item in spec['itineraries']:
        need(set(item)=={'name','paths'},'Exact Itinerary name/paths required')
        need(type(item['paths'])is list and all(x in paths for x in item['paths']),'Unknown selected Path name')
        out,r=ops.create_itinerary(documents,catalog,document_paths=docpaths,expected_hashes=hashes(),complete_document_set=True,name=item['name'],paths=[paths[x]for x in item['paths']]);documents=out['documents'];catalog=out['catalog'];stage.append(r)
    project=cd.Project(documents,document_paths=docpaths,expected_hashes={k:cd.sha(v)for k,v in documents.items()},complete_document_set=True);project.check_dest_catalog(catalog)
    stations=cats.station_items(w.load(station_blob)[0]);station_models=[m for m in project.models[name]if w.kind(m)=='OTStationModel'];need(set(stations)=={pf.string(m.contents[7].value)for m in station_models},'Station catalog/model closure mismatch')
    for st in spec['stations']:
        eid=end({k:st[k]for k in('vertex','side')});e=project.model((name,eid));other=project.model(project.related((name,eid)));need(e.contents[12].value is other.contents[12].value and e.contents[20].value==other.contents[20].value==2 and pf.string(e.contents[12].value.contents[7].value)==st['sign'],'Point-station references changed')
    itinerary_nodes={pf.string(o.contents[1].value):[list(k)for k in project.dest_view(o)[0]]for o in project.dests}
    members={'OTDocuments/'+name+'.opentrack':documents[name],'OTData/infrastructure.stations':station_blob,'OTData/infrastructure.dest':catalog}
    return members,{'document_paths':docpaths,'vertex_end_ids':ids,'edge_ids':top['edge_ids'],'route_references':routes,'path_references':paths,'itinerary_end_keys':itinerary_nodes,'counts':{'documents':1,'signals':len(spec['signals']),'routes':len(routes),'paths':len(paths),'itineraries':len(spec['itineraries']),'point_stations':len(stations)},'output_sha256':{k:cd.sha(v)for k,v in members.items()},'stage_receipts':stage,'fresh_archive_reload_verified':True,'operating_ready':False,'native_application_executed':False,'scope':'Single-document explicit simple movements, no connector, no automatic routing, no vehicles/timetable/run configuration; point stations are not stopping areas'}
