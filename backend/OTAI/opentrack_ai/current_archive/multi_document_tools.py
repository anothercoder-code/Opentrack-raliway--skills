"""Explicit multi_document domain. Immutable complete source inventory; shared publisher.

Unbound derivation previews retain native path strings. Bound candidates are
relocated before publication. New A/B projects are topology only: empty traffic
catalogs are intentionally rejected by simulation preflight.
"""
import hashlib,json,os,stat
from pathlib import PurePosixPath
from typing import Annotated,Literal
from pydantic import Field,StrictBool,StrictInt,StrictStr,model_validator
from .tools import Input,PathText,sha
from .bundle_tools import Source,CourseBundles
from .project_candidate_publication import ProjectSave,project_target,publish_candidate,require_external_target
from .zero_operations import run_bundle as rb
from ..errors import APIError

Hash=Annotated[StrictStr,Field(pattern=r'^[a-f0-9]{64}$')]
Name=Annotated[StrictStr,Field(min_length=1,max_length=200,pattern=r'^[^\x00]+$')]
Member=Annotated[StrictStr,Field(min_length=1,max_length=500)]
class Inventory(Input):
    project_directory:PathText
    files:Annotated[dict[Member,Hash],Field(min_length=1,max_length=2000)]
    complete_project_inventory:Literal[True]
    run_file:Member
    execution_root:PathText
class ProjectInput(Input):
    domain:Literal['multi_document']
    source_project:Inventory
class InspectMulti(ProjectInput):
    section:Literal['summary','connectors','continuations','routes','paths','itineraries']='summary'
    offset:Annotated[StrictInt,Field(ge=0)]=0
    limit:Annotated[StrictInt,Field(ge=1,le=100)]=50
class Ref(Input):
    document:Name
    name:Name
    array_id:Annotated[StrictInt,Field(ge=0,le=2147483647)]
    start_id:Annotated[StrictInt,Field(ge=0,le=2147483647)]
class NewPath(Input):
    name:Name
    routes:Annotated[list[Ref],Field(min_length=1,max_length=1000)]
class NewItinerary(Input):
    name:Name
    paths:Annotated[list[Ref],Field(min_length=1,max_length=1000)]
class DeriveMulti(ProjectInput,ProjectSave):
    paths:Annotated[list[NewPath],Field(max_length=100)]=Field(default_factory=list)
    itineraries:Annotated[list[NewItinerary],Field(max_length=100)]=Field(default_factory=list)
    @model_validator(mode='after')
    def work(self):
        if not self.paths and not self.itineraries:raise ValueError('Provide at least one new Path or Itinerary')
        return self
class GenerateMulti(ProjectInput,ProjectSave):
    header_document:Name
    shape_archive:Source
    execution_root:PathText
    example_profile:Literal['two_station_bidirectional_topology_only']='two_station_bidirectional_topology_only'

class MultiDocumentTools(CourseBundles):
    @staticmethod
    def member(value):
        if not isinstance(value,str) or value.startswith('/') or '\\' in value or ':' in value or any(c in value for c in '\x00\r\n') or any(p in ('','.','..') for p in value.split('/')):
            raise APIError('PROJECT_MEMBER','Canonical traversal-free relative project member required',value)
        try:rb.relative(value)
        except ValueError as exc:raise APIError('PROJECT_MEMBER','Portable canonical project member required',str(exc))from exc
        if len(value.split('/'))>16:raise APIError('PROJECT_MEMBER','Project member nesting exceeds bound')
        return value
    def inventory_names(self,base):
        """Complete actual tree inventory, descriptor-only, refusing symlinks/devices."""
        if os.name=='nt':
            from .windows_io import inventory_names
            return inventory_names(self.root,base)
        out=[]
        with self.parent_fd(base/'_inventory_anchor') as (fd,_):
            def scan(at,prefix,depth):
                if depth>16:raise APIError('PROJECT_INVENTORY','Directory nesting exceeds bound')
                for name in sorted(os.listdir(at)):
                    rel=prefix+name;self.member(rel)
                    meta=os.stat(name,dir_fd=at,follow_symlinks=False)
                    if stat.S_ISDIR(meta.st_mode):
                        child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=at)
                        try:scan(child,rel+'/',depth+1)
                        finally:os.close(child)
                    elif stat.S_ISREG(meta.st_mode):
                        out.append(rel)
                        if len(out)>2000:raise APIError('PROJECT_INVENTORY','At most 2000 files per explicit project inventory')
                    else:raise APIError('PROJECT_INVENTORY','Symlink/nonregular source member refused',rel)
            scan(fd,'',0)
        if len({x.casefold() for x in out})!=len(out):raise APIError('PROJECT_INVENTORY','Case-insensitive source member collision')
        return out
    def load_project(self,spec,*,minimum_documents=2):
        base=self.path(spec.project_directory)
        for n in spec.files:self.member(n)
        self.member(spec.run_file)
        expected=sorted(spec.files)
        def scope_check():
            if self.inventory_names(base)!=expected:raise APIError('PROJECT_INVENTORY_CHANGED','Actual complete project file set differs from supplied inventory')
        scope_check();inputs={};files={}
        for n,h in spec.files.items():
            p=base/n;b=self.secure_bytes(p)
            if sha(b)!=h:raise APIError('SOURCE_CHANGED','Project member differs from exact source SHA',n)
            inputs[p]=b;files[n]=b
        if sum(map(len,files.values()))>256*1024*1024:raise APIError('PROJECT_SIZE','Complete project inventory exceeds 256 MiB')
        root=rb.root_path(spec.execution_root,'windows')
        if root!=spec.execution_root:raise APIError('PROJECT_EXECUTION_ROOT','Use canonical forward-slash execution root')
        if spec.run_file not in files:raise APIError('PROJECT_RUN','Selected run is missing from inventory')
        from .prepare_contract import auxiliary as run_aux
        rows=run_aux.records(files[spec.run_file]);bykey={}
        for k,v,_ in rows:
            if k:bykey.setdefault(k,[]).append(v)
        def resolve(path):
            if not path.startswith(root+'/'):raise APIError('PROJECT_BINDING','Input path is outside explicit project execution-root map',path)
            rel=self.member(path[len(root)+1:])
            if rel not in files:raise APIError('PROJECT_BINDING','Run-bound member absent from complete actual inventory',rel)
            return rel
        roles={}
        for role,key in rb.CATALOG_KEYS.items():
            if len(bykey.get(key,[]))!=1:raise APIError('PROJECT_BINDING','Exactly one catalog role required',key)
            roles[role]=resolve(bykey[key][0])
            if not roles[role].endswith(rb.EXTENSIONS[role]):raise APIError('PROJECT_BINDING','Catalog role extension mismatch',role)
        docpaths={};docs={};docmembers={}
        for path in bykey.get('Infrastructure Document',[]):
            rel=resolve(path);name=PurePosixPath(rel).stem
            if not rel.endswith('.opentrack') or name in docs:raise APIError('PROJECT_BINDING','Unique infrastructure basename required',rel)
            docs[name]=files[rel];docpaths[name]=path;docmembers[name]=rel
        if not minimum_documents<=len(docs)<=100:
            raise APIError('MULTI_DOCUMENT_DOMAIN',f'Selected run requires {minimum_documents}..100 infrastructure documents')
        if not spec.run_file.endswith('.run'):raise APIError('PROJECT_RUN','Selected run must use .run extension')
        selected=set(roles.values())|set(docmembers.values())|{spec.run_file}
        for key in ('Train Diagram Document','Document Set Document'):
            for path in bykey.get(key,[]):selected.add(resolve(path))
        try:
            run_aux.set_bindings(rows,set(docpaths.values())|set(bykey.get('Train Diagram Document',[])))
            run_aux.incident_bindings(files[roles['courses']],bykey.get('Incident',[]))
        except ValueError as exc:
            raise APIError('PROJECT_AUXILIARY_BINDING','Invalid named event or document-set binding',str(exc))from exc
        if len(roles.values())!=len(set(roles.values())) or set(roles.values())&set(docmembers.values()):raise APIError('PROJECT_BINDING','Catalog/document role alias refused')
        if spec.run_file in set(roles.values())|set(docmembers.values()):raise APIError('PROJECT_BINDING','Run role alias refused')
        scope_check()
        return dict(base=base,inputs=inputs,files=files,roles=roles,documents=docs,document_paths=docpaths,document_members=docmembers,selected=sorted(selected),run=files[spec.run_file],scope_check=scope_check,root=root)
    def recheck(self,state):
        state['scope_check']()
        for p,b in state['inputs'].items():
            if self.secure_bytes(p)!=b:raise APIError('SOURCE_CHANGED','Dependency changed during read',str(p.relative_to(self.root)))
    @staticmethod
    def project(state, project_type=None):
        from .multi_document.core import Project
        project_type = Project if project_type is None else project_type
        p=project_type(state['documents'],document_paths=state['document_paths'],expected_hashes={k:sha(v) for k,v in state['documents'].items()},complete_document_set=True)
        p.check_dest_catalog(state['files'][state['roles']['dest']]);return p
    @staticmethod
    def source_receipt(args,state):
        return {'project_directory':args.source_project.project_directory,'complete_actual_inventory_verified':True,'files':dict(args.source_project.files),'selected_run_file':args.source_project.run_file,'selected_run_dependency_members':state['selected'],'execution_root_mapping':state['root'],'native_paths_verified':False}
    def inspect(self,args):
        state=self.load_project(args.source_project);p=self.project(state);report=p.report()
        from .multi_document.core import ref
        report['routes']=[dict(document=p.owners[id(r)][0],**ref(r),runtime_end_keys=p.route_view(r)) for r in p.routes]
        counts={key:len(report[key]) for key in ('documents','connectors','continuations','routes','paths','itineraries')}
        result={'domain':'multi_document','source':self.source_receipt(args,state),'counts':counts,'native_execution':False,'native_runtime_fields_written':False,'scope':report['scope']}
        if args.section=='summary':result['documents']=report['documents']
        else:
            rows=report[args.section];result.update(section=args.section,items=rows[args.offset:args.offset+args.limit],total_count=len(rows),offset=args.offset,has_more=args.offset+args.limit<len(rows))
        self.recheck(state);return result
    def derive(self,args):
        target=project_target(self,args)
        require_external_target(target,self.path(args.source_project.project_directory))
        from .multi_document import operations
        from .itinerary_edit_tools import EditableItineraryProject
        state=self.load_project(args.source_project);self.project(state, EditableItineraryProject)
        docs=dict(state['documents']);catalog=state['files'][state['roles']['dest']];receipts=[]
        def context():
            return dict(document_paths=state['document_paths'],
                        expected_hashes={**{k:sha(v) for k,v in docs.items()},'$dest_catalog':sha(catalog)},
                        complete_document_set=True, project_type=EditableItineraryProject)
        for item in args.paths:
            docs,receipt=operations.create_path(docs,catalog,**context(),name=item.name,routes=[x.model_dump() for x in item.routes]);receipts.append(receipt)
        for item in args.itineraries:
            result,receipt=operations.create_itinerary(docs,catalog,**context(),name=item.name,paths=[x.model_dump() for x in item.paths]);docs,catalog=result['documents'],result['catalog'];receipts.append(receipt)
        members={n:state['files'][n] for n in state['selected']}
        for dn,b in docs.items():members[state['document_members'][dn]]=b
        members[state['roles']['dest']]=catalog
        check={**state,'documents':docs,'files':{**state['files'],**members}};self.project(check, EditableItineraryProject)
        relocation=None
        if target is not None:
            from .project_workflow.relocation import relocate_project
            try:
                members,relocation=relocate_project(
                    members,source_root=state['root'],target_root=target.as_posix(),
                    run_file=args.source_project.run_file,
                    expected_hashes={name:sha(blob) for name,blob in members.items()},
                    project_type=EditableItineraryProject,
                )
            except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
                raise APIError('RELOCATION_INVALID','Derived project cannot be rebound to the publication target',str(exc)[:500]) from exc
        manifest={'format':'opentrack-multi-document-snapshot-v1','domain':'multi_document','source':self.source_receipt(args,state),'files':{n:{'sha256':sha(b),'bytes':len(b),'changed':b!=state['files'][n]} for n,b in members.items()},'complete_selected_run_input_snapshot':True,'complete_relocated_project':relocation is not None,'native_paths_preserved':relocation is None,'native_runtime_ready':False,'receipts':receipts}
        result={'preview_only':args.preview_only,'saved':False,'bundle_type':'relocated selected-run input snapshot' if relocation else 'complete selected-run input snapshot; original native paths preserved, not a runtime relocation','manifest':manifest,'changes':receipts,'fresh_archive_reload_verified':True,'native_execution':False,'native_runtime_ready':False,'warnings':['No runtime actualRelated/cache object is persisted. Original native execution remains unverified.']}
        if relocation is None:
            result['warnings'].insert(0,'Run and diagram/document-set bytes retain their original native paths.')
        else:
            result['relocation']=relocation
        self.recheck(state)
        result['publication_review_pending']=True
        if args.preview_only:
            return result
        return publish_candidate(self,target,members,result,lambda: self.recheck(state))
    def generate(self,args):
        target=project_target(self,args,args.execution_root)
        require_external_target(target,self.path(args.source_project.project_directory))
        from .multi_document import generate,bundle
        state=self.load_project(args.source_project);self.project(state)
        if args.header_document not in state['documents']:raise APIError('HEADER_DOCUMENT','Header donor must be a selected source project document')
        path=self.path(args.shape_archive.path);shapes=self.secure_bytes(path)
        if sha(shapes)!=args.shape_archive.sha256:raise APIError('SOURCE_CHANGED','Shape donor differs from exact SHA')
        if path in state['inputs'] and state['inputs'][path]!=shapes:raise APIError('SOURCE_CHANGED','Shared shape dependency changed')
        templates={k:state['files'][state['roles'][k]] for k in ('depot','trains','courses','timetable')}
        members,receipt,_=generate.generate(state['documents'][args.header_document],shapes,templates,execution_root=args.execution_root)
        hashes={n:sha(b) for n,b in members.items()}
        verified=bundle.validate_no_service_bundle(members,run_file='cross-document.run',expected_hashes=hashes,complete_file_set=True)
        manifest={'format':'opentrack-multi-document-topology-project-v1','domain':'multi_document','source':self.source_receipt(args,state),'shape_source':args.shape_archive.model_dump(),'files':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in members.items()},'execution_root_mapping':args.execution_root,'service_catalogs_empty':True,'operating_simulation_ready':False,'native_runtime_ready':False,'generation':receipt,'static_bundle_validation':verified}
        result={'preview_only':args.preview_only,'saved':False,'bundle_type':'complete nine-file one-station-per-document topology-only project','manifest':manifest,'fresh_archive_reload_verified':True,'native_execution':False,'native_runtime_ready':False,'service_catalogs_empty':True,'warnings':['Empty Engine/Train/Course/Timetable catalogs are intentional topology-only scope and must fail strict operating preflight.','One StationVertex per document is not an implemented stopping region. Native GUI/loading/runtime behavior remains untested.']}
        def recheck():
            self.recheck(state)
            if self.secure_bytes(path)!=shapes:
                raise APIError('SOURCE_CHANGED','Shape source changed during preparation or publication')
        recheck()
        result['publication_review_pending']=True
        if args.preview_only:
            return result
        return publish_candidate(self,target,members,result,recheck)
    def preflight(self,args):
        from .prepare_contract import preflight
        state=self.load_project(args.source_project)
        def bound(path):
            if not path.startswith(state['root']+'/'):raise ValueError('Input outside explicit complete project map')
            rel=self.member(path[len(state['root'])+1:])
            if rel not in state['files']:raise ValueError('Missing full-inventory run dependency')
            return state['files'][rel]
        result=preflight.check(state['run'],bound)
        try:
            p=self.project(state);result['cross_document_static_validation']={'passed':True,'document_count':len(p.roots),'path_count':len(p.paths_objects),'itinerary_count':len(p.dests)}
        except ValueError as error:
            result['errors'].append({'rule':'MULTIDOC01','message':str(error)});result['passed_static_subset']=False;result['cross_document_static_validation']={'passed':False}
        result['source']=self.source_receipt(args,state);result['domain']='multi_document';result['native_runtime_ready']=False
        result['unestablished']+=['NSUserDefaults/profile simulation-run count and all runtime initialization side effects remain unbound; no fabricated .run key or control endpoint','Native simulation is performed by OpenTrack; this tool validates saved input data only']
        self.recheck(state);return result

def tool_definitions(root):
    service=MultiDocumentTools(root)
    return [
        ('opentrack_inspect_multi_document_project','Read explicit multi_document project: full actual source tree SHA manifest, same-project .run dependency mapping, document-local IDs, reciprocal connectors, continuation Routes and cross-document Paths/Itineraries. Read-only; separate in-memory views, no runtime cache writes or native execution.',InspectMulti,service.inspect),
        ('opentrack_create_multi_document_paths_itineraries','Add exact continuous Paths/Itineraries across documents. Preview without a target retains original paths; a Windows publication target rebases the selected-run dependency closure before saving. Every source member SHA required. Never starts OpenTrack.',DeriveMulti,service.derive,False,False),
        ('opentrack_generate_multi_document_topology','Preview or publish fresh fixed A/B instructional topology on Windows: two documents, reciprocal connectors, continuation Routes, Paths/Itineraries, six catalogs and .run. Empty traffic; no native execution.',GenerateMulti,service.generate,False,False),
        ('opentrack_preflight_simulation_prepare','Read-only strict saved-data subset of original native simulation preparation contracts with full same-project inventory and cross-document checks. Reject absent workload and native fallback cases. Partial checks passed never means native runtime ready; NSUserDefaults/framework/runtime/physical effects remain unclosed.',ProjectInput,service.preflight),
    ]
