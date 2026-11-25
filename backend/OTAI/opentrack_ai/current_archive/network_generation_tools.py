"""Generate a native network pair or seed a fresh complete construction project."""
from pathlib import PurePosixPath
from typing import Annotated, Literal
from pydantic import Field, StrictStr, StrictInt, StrictFloat, StrictBool, model_validator
from .tools import Input, PathText, sha
from .graphic_alignment import SignalAlignedInput
from .bundle_tools import Source
from . import writer as w, path_functions as pf, route_factory as rf
from .multi_document.bundle import validate_no_service_bundle
from .multi_document_tools import Inventory, MultiDocumentTools
from .project_candidate_publication import project_target, publish_candidate, require_external_target
from .project_workflow.relocation import relocate_project
from .zero_generation import topology, native_signal_routes as sr, empty_path_factory as paths, loop_itinerary as itineraries
from .zero_generation.empty_project import worksheet_header_fingerprint
from .zero_operations import run_bundle
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
    source_project: Inventory | None = None
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

class NetworkGeneration(MultiDocumentTools):
    def generate(self,args):
        inputs={};blobs={};sources={}
        for key in Sources.model_fields:
            spec=getattr(args.sources,key);path,blob,_,_=self.read(spec.path)
            if sha(blob)!=spec.sha256:raise APIError('SOURCE_CHANGED','Explicit source SHA mismatch',key)
            if path in inputs and inputs[path]!=blob:raise APIError('SOURCE_CHANGED','Shared source changed during reads',key)
            inputs[path]=blob;blobs[key]=blob;sources[key]={'path':spec.path,'sha256':spec.sha256}
        if args.source_project is not None:
            return self.generate_project(args, inputs, blobs, sources)
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

    def generate_project(self, args, inputs, blobs, sources):
        target = project_target(self, args)
        state = self.load_project(args.source_project, minimum_documents=1)
        source_root = state['root']
        run = args.source_project.run_file
        original = state['files']
        dest = state['roles']['dest']
        require_external_target(target, state['base'])
        if target is not None and state['base'].is_relative_to(target):
            raise APIError('PROJECT_TARGET_BINDING', 'Publication target cannot enclose the source project')
        for path, blob in inputs.items():
            if target is not None and path.is_relative_to(target):
                raise APIError('PROJECT_TARGET_BINDING', 'Publication target cannot enclose an input archive')
            if path in state['inputs'] and state['inputs'][path] != blob:
                raise APIError('SOURCE_CHANGED', 'A shared project and template input changed during reads')
            state['inputs'][path] = blob

        try:
            topology.need(source_root == state['base'].as_posix(), 'Use the blank project at its actual native execution root')
            topology.need(args.catalog_filename == PurePosixPath(dest).name,
                          'Select the existing run-bound DestInfo filename')
            topology.need(args.document_name in state['document_members'], 'Select an existing run-bound worksheet')
            worksheet = state['document_members'][args.document_name]
            validation = validate_no_service_bundle(original, run_file=run, expected_hashes=args.source_project.files,
                                                    complete_file_set=True)
            topology.need(validation['station_count'] == validation['destination_count'] == 0,
                          'The run-bound Station and DestInfo catalogues must contain zero records')
            selected, _ = w.load_next_compatible(original[worksheet])
            topology.doc_layout(selected)
            topology.need(not pf.mutable_array(selected.contents[2].value)
                          and not pf.mutable_array(selected.contents[5].value.contents[0].value)
                          and not rf.wrapper(selected.contents[12].value, 'OTOccInfoList'),
                          'The selected worksheet must have empty graphic, itinerary and occupation collections')
            header, _ = w.load_next_compatible(blobs['header_document'])
            topology.doc_layout(header)
            header_fingerprint = worksheet_header_fingerprint(selected)
            topology.need(worksheet_header_fingerprint(header) == header_fingerprint,
                          'The supplied worksheet header differs from the selected blank worksheet')

            pair, report = self.compose(args, {**blobs, 'header_document': original[worksheet]},
                                        document_path=state['document_paths'][args.document_name])
            revised = pair[args.document_name + '.opentrack']
            updated, _ = w.load_next_compatible(revised)
            topology.need(worksheet_header_fingerprint(updated) == header_fingerprint,
                          'Generated geometry changed protected or other non-collection worksheet fields')
            members = {**original, worksheet: revised, dest: pair[args.catalog_filename]}
            relocation = None
            if target is not None:
                output_path, = [value for key, value, _ in run_bundle.records(state['run']) if key == 'OutputPath']
                members, relocation = relocate_project(
                    members, source_root=source_root, target_root=target.as_posix(), run_file=run,
                    expected_hashes={name: sha(data) for name, data in members.items()},
                    output_directory=output_path[len(source_root) + 1:],
                )
            preserved = {name: sha(data) for name, data in original.items() if name not in {worksheet, dest, run}}
            topology.need(all(sha(members[name]) == digest for name, digest in preserved.items()),
                          'The selected run uses an altered unselected worksheet or empty catalogue')
            hashes = {name: sha(data) for name, data in members.items()}
            validation = validate_no_service_bundle(members, run_file=run, expected_hashes=hashes, complete_file_set=True)
            topology.need(validation['destination_count'] == len(args.itineraries) and validation['station_count'] == 0,
                          'Freshly loaded run does not bind exactly the generated itineraries and empty Station catalogue')
        except (ValueError, TypeError, IndexError, KeyError, OverflowError) as exc:
            raise APIError('CURRENT_NETWORK_PROJECT_GENERATION', str(exc)[:500]) from exc

        report['complete_project_validated'] = True
        manifest = {
            'format': 'opentrack-current-network-project-v1', 'sources': sources,
            'files': {name: {'sha256': hashes[name], 'bytes': len(data)} for name, data in members.items()},
            'scope': 'native geometry and itineraries in a complete no-service project',
            'complete_relocated_project': relocation is not None,
            'native_simulation_executed': False, 'report': report,
        }
        result = {
            'preview_only': args.preview_only, 'saved': False, 'publication_review_pending': True,
            'bundle_type': 'complete native no-service project', 'manifest': manifest, 'report': report,
            'source_project': self.source_receipt(args, state), 'source_project_modified': False,
            'worksheet_member': worksheet, 'destination_catalog_member': dest, 'run_member': run,
            'member_sha256': hashes, 'preserved_member_sha256': preserved, 'relocation': relocation,
            'complete_project_validation': validation, 'fresh_archive_reload_verified': True,
            'native_application_started': False, 'native_simulation_executed': False,
        }

        def recheck():
            self.recheck(state)

        recheck()
        if args.preview_only:
            return result
        return publish_candidate(self, target, members, result, recheck)

    @staticmethod
    def compose(args,blobs,*,document_path=None):
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
        owner_path = filename if document_path is None else document_path
        for item in args.itineraries:
            extra={} if prior else {'template_document':blobs['template_document'],'template_catalog':blobs['template_dest_catalog'],
                'expected_template_hashes':{'document':sha(blobs['template_document']),'catalog':sha(blobs['template_dest_catalog'])}}
            changed,receipt=itineraries.create_itinerary({args.document_name:data},catalog,
                expected_hashes={args.document_name:sha(data),'$catalog':sha(catalog)},document_paths={args.document_name:owner_path},
                owner_document=args.document_name,name=item.name,path_refs=[path_refs[name] for name in item.paths],
                template_name=prior or args.templates.itinerary_name,description=item.description,**extra)
            data=changed['documents'][args.document_name];catalog=changed['catalog'];prior=item.name;report['itineraries'].append(receipt)
        root,_,_,_=sr.document(data);sr.validate_topology(root)
        report['counts']={'vertices':len(args.network.vertices),'edges':len(args.network.edges),'signals':len(args.signals),
            'routes':len(args.routes),'paths':len(args.paths),'itineraries':len(args.itineraries)}
        return {filename:data,args.catalog_filename:catalog},report

def tool_definitions(root):
    service=NetworkGeneration(root)
    return [('opentrack_generate_current_network_archives','Generate a single-document network and itinerary catalog from explicit paired Ends, Edges, Safety Elements, main signals, Routes, Paths and finite multi-Path itineraries. Preserves the worksheet header; shape templates supply no old movements. Preview or publish a fresh archive pair, or provide source_project to populate a selected blank worksheet and DestInfo in a complete native no-service project with rebased paths and preserved run settings.',GenerateNetwork,service.generate,False,False)]
