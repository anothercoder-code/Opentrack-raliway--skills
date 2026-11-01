"""Guarded current archive scalar setters and explicit itinerary composition."""
import struct,math,json
from typing import Annotated
from pydantic import Field,StrictFloat,StrictInt,StrictStr,StrictBool,model_validator
from .tools import Input,PathText,sha
from .operation_tools import Name,SignedI32,RouteSelector
from .bundle_tools import Source,CourseBundles
from .next_tools import NextFunctions,Save
from . import writer as w,category_dwell
from ..errors import APIError

Finite=Annotated[StrictFloat|StrictInt,Field(allow_inf_nan=False)]
class Changes(Input):
    @model_validator(mode='after')
    def explicit(self):
        if not self.model_fields_set or any(getattr(self,k) is None for k in self.model_fields_set):raise ValueError('Nonempty explicit non-null changes required')
        return self
class EngineChanges(Changes):
    adhesion_load:SignedI32|None=None
    force_max_kn:SignedI32|None=None
    force_min_kn:SignedI32|None=None
class CategoryChanges(Changes):
    stop_at_every_station_time_s:Finite|None=None
    dwell_variation_early:Finite|None=None
    dwell_variation_delayed:Finite|None=None
    dwell_variation_early_unit_code:SignedI32|None=None
    dwell_variation_delayed_unit_code:SignedI32|None=None
    dwell_variation_early_delay_offset_s:Finite|None=None
    dwell_variation_delayed_delay_offset_s:Finite|None=None
class EditEngine(Save):
    source:Source
    engine_name:Name
    changes:EngineChanges
class InspectCategory(Input):
    source_path:PathText
    category_name:Name
class EditCategory(Save):
    source:Source
    category_name:Name
    changes:CategoryChanges
class CreateItinerary(Input):
    project_run:Source
    documents:Annotated[dict[Name,Source],Field(min_length=1,max_length=100)]
    catalog:Source
    document_paths:Annotated[dict[Name,Name],Field(min_length=1,max_length=100)]
    owner_document:Name
    name:Name
    path_refs:Annotated[list[RouteSelector],Field(min_length=1,max_length=1)]
    template_name:Name
    description:StrictStr=''
    preview_only:StrictBool=True
    target_directory:PathText|None=None
    @model_validator(mode='after')
    def target(self):
        if not self.preview_only and self.target_directory is None:raise ValueError('Saving requires explicit fresh target_directory')
        return self

def bits32(value):
    if isinstance(value,w.WireFloat) and value.encoding==b'f':return (value.bits if value.byte_order=='little' else value.bits[::-1]).hex()
    return struct.pack('<f',value).hex()
def float_bits(values):
    return {k:bits32(values[k]) for k,s in category_dwell.FIELDS.items() if s[2]=='f'}
def safe_category_report(value):
    
    if isinstance(value,float) and not math.isfinite(value):
        return {'native_nonfinite':'nan' if math.isnan(value) else ('positive_infinity' if value>0 else 'negative_infinity'),'encoding':'f','width_bits':32,'bits_le':bits32(value),'native_setter_semantics_claimed':False}
    if isinstance(value,dict):return {k:safe_category_report(v) for k,v in value.items()}
    if isinstance(value,list):return [safe_category_report(v) for v in value]
    return value
class FollowingFunctions(NextFunctions,CourseBundles):
    def engine(self,args):
        from . import engine_physics
        path,blob,_,_=self.checked(args.source)
        try:output,report=engine_physics.patch_archive(blob,args.engine_name,args.changes.model_dump(exclude_unset=True))
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_ENGINE_PHYSICS',str(e)[:500]) from e
        return self.finish(args,path,blob,output,report)
    def inspect_category(self,args):
        path,blob,_,_=self.read(args.source_path)
        try:
            values=category_dwell.read_archive(blob,args.category_name)
            bits=float_bits(values)
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_CATEGORY_DWELL',str(e)[:500]) from e
        return {'source_path':args.source_path,'source_sha256':sha(blob),'category_name':args.category_name,'values':safe_category_report(values),'float32_bits_le':bits,'native_application_started':False}
    def category(self,args):
        path,blob,_,_=self.checked(args.source)
        try:
            output,report=category_dwell.patch_archive(blob,args.category_name,args.changes.model_dump(exclude_unset=True))
            report['persisted_float32_bits_le']=float_bits(category_dwell.read_archive(output,args.category_name))
            report['mcp_integrated']=True
            report=safe_category_report(report)
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_CATEGORY_DWELL',str(e)[:500]) from e
        return self.finish(args,path,blob,output,report)

    def itinerary(self,args):
        from . import itinerary_factory
        inputs={key:self.checked(spec) for key,spec in args.documents.items()}
        cp,cb,_,_=self.checked(args.catalog)
        self.same_project([cp]+[x[0] for x in inputs.values()])
        if len({x[0] for x in inputs.values()})!=len(inputs) or cp in {x[0] for x in inputs.values()}:raise APIError('DATASET_MISMATCH','Distinct document and catalog source files required')
        if args.owner_document not in inputs:raise APIError('DOCUMENT_SCOPE','Owner document missing')
        runpath,runblob,scope_check,scope_evidence=self.checked_document_list(args,inputs)
        
        
        from pathlib import Path
        catalog_entries=[line.split('#')[1] for line in runblob.decode('ascii').splitlines() if line.split('#')[0]=='DestInfoFile']
        if len(catalog_entries)!=1:raise APIError('DOCUMENT_SCOPE','Run requires exactly one DestInfoFile binding')
        raw=catalog_entries[0]
        if not raw or '%' in raw or '\\' in raw or '..' in Path(raw).parts:raise APIError('DOCUMENT_SCOPE','Unsupported run DestInfoFile path')
        project=self.root.joinpath(*self.project_scope(runpath))
        candidate=Path(raw) if Path(raw).is_absolute() else project/raw
        try:relative=candidate.relative_to(self.root).as_posix()
        except ValueError as e:raise APIError('DOCUMENT_SCOPE','DestInfoFile outside authorized root') from e
        if self.path(relative)!=cp:raise APIError('DOCUMENT_SCOPE','Supplied catalog must match the run DestInfoFile exactly')
        if args.target_directory:
            target=self.path(args.target_directory)
            project=self.root.joinpath(*self.project_scope(runpath))
            if target==project or target.is_relative_to(project):raise APIError('DOCUMENT_SCOPE','Incremental output directory must be outside the input project so its inventory remains unchanged')
        try:
            outputs,report=itinerary_factory.create_itinerary({k:x[1] for k,x in inputs.items()},cb,
                expected_hashes={**{k:sha(x[1]) for k,x in inputs.items()},'$catalog':sha(cb)},document_paths=dict(args.document_paths),
                owner_document=args.owner_document,name=args.name,path_refs=[r.model_dump() for r in args.path_refs],template_name=args.template_name,description=args.description)
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_ITINERARY_FACTORY',str(e)[:500]) from e
        owner=inputs[args.owner_document][0]
        if owner.name==cp.name:raise APIError('DATASET_MISMATCH','Output filenames collide')
        members={owner.name:outputs['documents'][args.owner_document],cp.name:outputs['catalog']}
        if any(len(b)>20*1024*1024 for b in members.values()):raise APIError('ARCHIVE_SIZE','Output exceeds 20 MiB')
        for b in members.values():w.load_next_compatible(b)
        dependencies={runpath:runblob,cp:cb,**{x[0]:x[1] for x in inputs.values()}}
        manifest={'format':'opentrack-current-itinerary-increment-v1','files':{name:{'sha256':sha(b),'bytes':len(b),'changed':True} for name,b in members.items()},
            'sources':{str(p.relative_to(self.root)):{'sha256':sha(b)} for p,b in dependencies.items()},
            'document_scope':{**scope_evidence,'run_dest_info_catalog_matched':True},'document_paths':dict(args.document_paths),'changed_sources':[str(owner.relative_to(self.root)),str(cp.relative_to(self.root))],
            'complete_relocated_project':False,'stored_document_paths_rebased':False,'source_project_automatically_updated':False,'template_semantics':'bounded composition; not native init/copy equivalence'}
        result={'preview_only':args.preview_only,'saved':False,'bundle_type':'Itinerary document/catalog increment, not a relocated complete Project','manifest':manifest,
            'change_report':report,'fresh_archive_reload_verified':True,'native_application_started':False,'complete_relocated_project':False}
        json.dumps(result,allow_nan=False) 
        return self.publish_bundle(inputs=dependencies,members=members,manifest=manifest,result=result,target_directory=args.target_directory,scope_check=scope_check)

def tool_definitions(root):
    service=FollowingFunctions(root)
    return [
      ('opentrack_create_current_itinerary','Compose one local current Itinerary from explicit same-document empty-margin template and one existing Path. Verify run/inventory/document/catalog closure and hashes; atomically save document+catalog to fresh external directory increment. Not native init/copy or a relocated project.',CreateItinerary,service.itinerary,False,False),
      ('opentrack_edit_current_engine_physics','Three exact signed-int32 Engine setters; adhesion=0 also clears first diagram display flag, rejecting shared owners. No curve, UI correction or physics recomputation. Preview/fresh file only.',EditEngine,service.engine,False,False),
      ('opentrack_inspect_current_category_dwell','Read seven persisted Category dwell values, raw unit codes and exact float32 bits; no simulation or normalization.',InspectCategory,service.inspect_category),
      ('opentrack_edit_current_category_dwell','Seven current Category fields with original finite float32 clamps and signed int32 raw unit codes. Preserves signed zero; rejects NaN, unknown layout and aliases. Preview/fresh file only.',EditCategory,service.category,False,False),
    ]
