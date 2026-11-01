"""One explicit-spec network archive transaction, not a complete simulation project."""
from typing import Annotated, Literal
from pydantic import Field, StrictStr, StrictInt, StrictFloat, StrictBool, model_validator
from .tools import Input, PathText, sha
from .graphic_alignment import SignalAlignedInput
from .bundle_tools import Source, CourseBundles
from . import writer as w, path_functions as pf
from .zero_generation import topology, native_signal_routes as sr, empty_path_factory as paths, loop_itinerary as itineraries
from ..errors import APIError

Text=Annotated[StrictStr,Field(min_length=1,max_length=200,pattern=r'^[^\x00]+$')]
Number=Annotated[StrictInt|StrictFloat,Field(allow_inf_nan=False)]
Side=Annotated[StrictInt,Field(ge=0,le=1)]
PairText=Annotated[list[StrictStr],Field(min_length=2,max_length=2)]
PairBool=Annotated[list[StrictBool],Field(min_length=2,max_length=2)]
class EndRef(Input):
    vertex:Text
    side:Side
class Vertex(Input):
    key:Text
    x:Number
    y:Number
    orientation:Literal['horizontal','vertical']
    names:PairText
    insulated_joint:PairBool
    axle_counter:PairBool
class Speed(Input):
    train_type:Text
    speed12_kmh:Annotated[StrictInt,Field(ge=1,le=1000)]
    speed21_kmh:Annotated[StrictInt,Field(ge=1,le=1000)]
class Edge(Input):
    key:Text
    from_end:EndRef
    to_end:EndRef
    length_m:Annotated[StrictInt,Field(ge=1,le=2147483647)]
    radius_m:Number
    gradient_per_mille:Number
    track_type:Annotated[StrictInt,Field(ge=1,le=1)]
    loop_type:Annotated[StrictInt,Field(ge=1,le=1)]
    dlink_type:Annotated[StrictInt,Field(ge=1,le=1)]
    equal_speed:StrictBool
    rack_rail:StrictBool
    speeds:Annotated[list[Speed],Field(min_length=1,max_length=100)]
    remark:StrictStr
    track_name:StrictStr
    line_name:StrictStr
class Network(Input):
    vertices:Annotated[list[Vertex],Field(min_length=1,max_length=1000)]
    edges:Annotated[list[Edge],Field(max_length=2000)]
    def core_spec(self):
        out=self.model_dump()
        for e in out['edges']:
            for source,dest in [('from_end','from'),('to_end','to')]:
                v=e.pop(source);e[dest]=[v['vertex'],v['side']]
        return out
class MainSignal(SignalAlignedInput):
    name:Text
    end:EndRef
    angle:Number
    sight_m:Annotated[StrictInt,Field(ge=1,le=100000)]
    delay_s:Annotated[Number,Field(ge=0,le=86400)]
    show_symbol:StrictBool
    show_icon:StrictBool
class Route(Input):
    name:Text
    ends:Annotated[list[EndRef],Field(min_length=2,max_length=1000)]
    description:StrictStr
    release_groups:Literal['global','each_end']
    reserve_previous:StrictBool
class Path(Input):
    name:Text
    routes:Annotated[list[Text],Field(min_length=1,max_length=1000)]
    description:StrictStr
class Itinerary(Input):
    name:Text
    paths:Annotated[list[Text],Field(min_length=1,max_length=10000)]
    description:StrictStr
class Templates(Input):
    path_name:Text
    path_array_id:Annotated[StrictInt,Field(ge=0,le=2147483647)]
    path_start_id:Annotated[StrictInt,Field(ge=0,le=2147483647)]
    itinerary_name:Text
class Sources(Input):
    header_document:Source
    shape_archive:Source
    template_document:Source
    template_dest_catalog:Source
class GenerateNetwork(Input):
    sources:Sources
    templates:Templates
    document_name:Annotated[StrictStr,Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')]
    catalog_filename:Annotated[StrictStr,Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\.dest$')]
    network:Network
    signals:Annotated[list[MainSignal],Field(min_length=1,max_length=2000)]
    routes:Annotated[list[Route],Field(min_length=1,max_length=1000)]
    paths:Annotated[list[Path],Field(min_length=1,max_length=1000)]
    itineraries:Annotated[list[Itinerary],Field(min_length=1,max_length=1000)]
    preview_only:StrictBool=True
    target_directory:PathText|None=None
    @model_validator(mode='after')
    def destination(self):
        if not self.preview_only and self.target_directory is None:raise ValueError('Saving requires fresh target_directory')
        if self.document_name.endswith('.opentrack'):raise ValueError('document_name is a logical name without .opentrack suffix')
        for key in ('signals','routes','paths','itineraries'):
            vals=[x.name for x in getattr(self,key)]
            if len(vals)!=len(set(vals)):raise ValueError('Duplicate '+key+' name')
        return self

class NetworkGeneration(CourseBundles):
    def generate(self,args):
        inputs={};blobs={};sources={}
        for key in Sources.model_fields:
            spec=getattr(args.sources,key);path,blob,_,_=self.read(spec.path)
            if sha(blob)!=spec.sha256:raise APIError('SOURCE_CHANGED','Explicit source SHA mismatch',key)
            if path in inputs and inputs[path]!=blob:raise APIError('SOURCE_CHANGED','Shared source changed during reads',key)
            inputs[path]=blob;blobs[key]=blob;sources[key]={'path':spec.path,'sha256':spec.sha256}
        try:members,report=self.compose(args,blobs)
        except (ValueError,TypeError,IndexError,KeyError,OverflowError) as exc:
            raise APIError('CURRENT_NETWORK_GENERATION',str(exc)[:500]) from exc
        manifest={'format':'opentrack-current-network-archives-v1','sources':sources,
            'files':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in members.items()},
            'scope':'generated network and itinerary catalog only; no station/vehicle/course/timetable/run configuration',
            'complete_relocated_project':False,'native_simulation_executed':False,'report':report}
        result={'preview_only':args.preview_only,'saved':False,'bundle_type':'generated network archive pair, not a complete Project',
            'manifest':manifest,'report':report,'fresh_archive_reload_verified':True,
            'native_application_started':False,'native_simulation_executed':False}
        return self.publish_bundle(inputs=inputs,members=members,manifest=manifest,result=result,target_directory=args.target_directory)

    @staticmethod
    def compose(args,blobs):
        data,top=topology.generate_network(blobs['header_document'],blobs['shape_archive'],args.network.core_spec())
        report={'topology':top,'signals':[],'routes':[],'paths':[],'itineraries':[],
            'old_movement_reused':False,'opaque_header_preserved':True,'licence_granted_or_modified':False,
            'native_simulation_executed':False,'complete_project_validated':False}
        ids=top['vertex_end_ids']
        def end(ref):
            if ref.vertex not in ids:raise ValueError('Unknown vertex '+ref.vertex)
            return ids[ref.vertex][ref.side]
        vertices={x.key:x for x in args.network.vertices}
        for signal in args.signals:
            root,_,models,byid=sr.document(data);v=vertices[signal.end.vertex]
            data,receipt=sr.build_main_signal(data,end_id=end(signal.end),name=signal.name,model_id=max(byid,default=-1)+1,
                placement={'x':v.x,'y':v.y,'angle':signal.angle,'alignment_x':signal.alignment_x,'alignment_y':signal.alignment_y},
                sight_m=signal.sight_m,delay_s=signal.delay_s,show_symbol=signal.show_symbol,show_icon=signal.show_icon)
            report['signals'].append(receipt)
        route_refs={}
        for route in args.routes:
            data,receipt=sr.build_route(data,name=route.name,end_ids=[end(x) for x in route.ends],description=route.description,
                release_groups=route.release_groups,reserve_previous=route.reserve_previous)
            route_refs[route.name]={k:receipt[k] for k in ('name','array_id','start_id')};report['routes'].append(receipt)
        path_refs={}
        for path in args.paths:
            refs=[route_refs[name] for name in path.routes]
            root,_,_,byid=sr.document(data);owner=byid[refs[0]['start_id']]
            fresh=owner.contents[19].value+1
            existing=pf.mutable_array(owner.contents[17].value.contents[0].value)
            extra={} if existing else {'template_data':blobs['template_document'],'template_name':args.templates.path_name,
                'template_array_id':args.templates.path_array_id,'template_start_id':args.templates.path_start_id,
                'expected_template_sha256':sha(blobs['template_document'])}
            data,receipt=paths.create_local_path(data,path.name,fresh,refs,path.description,**extra)
            path_refs[path.name]={'name':path.name,'array_id':fresh,'start_id':refs[0]['start_id']};report['paths'].append(receipt)
        cat,cv=w.load_next_compatible(blobs['template_dest_catalog']);itineraries.wrapper(cat,'OTDestInfoList')
        w.set_elements(cat.contents[0].value,[]);catalog=w.dump_verified(cat,cv)
        filename=args.document_name+'.opentrack';prior=None
        for item in args.itineraries:
            extra={} if prior else {'template_document':blobs['template_document'],'template_catalog':blobs['template_dest_catalog'],
                'expected_template_hashes':{'document':sha(blobs['template_document']),'catalog':sha(blobs['template_dest_catalog'])}}
            changed,receipt=itineraries.create_itinerary({args.document_name:data},catalog,
                expected_hashes={args.document_name:sha(data),'$catalog':sha(catalog)},document_paths={args.document_name:filename},
                owner_document=args.document_name,name=item.name,path_refs=[path_refs[name] for name in item.paths],
                template_name=prior or args.templates.itinerary_name,description=item.description,**extra)
            data=changed['documents'][args.document_name];catalog=changed['catalog'];prior=item.name;report['itineraries'].append(receipt)
        root,_,_,_=sr.document(data);sr.validate_topology(root)
        report['counts']={'vertices':len(args.network.vertices),'edges':len(args.network.edges),'signals':len(args.signals),
            'routes':len(args.routes),'paths':len(args.paths),'itineraries':len(args.itineraries)}
        return {filename:data,args.catalog_filename:catalog},report

def tool_definitions(root):
    service=NetworkGeneration(root)
    return [('opentrack_generate_current_network_archives','Generate a new single-document network and itinerary catalog from an explicit bounded spec: paired Ends, Edges, Safety Elements, main signals, new Routes, Paths and finite multi-Path itineraries. Preserves source header licence/registration unchanged; explicit shape templates do not reuse movements. Preview by default or atomically publish a fresh archive pair. Not a complete Project, timetable, vehicle configuration or native simulation.',GenerateNetwork,service.generate,False,False)]
