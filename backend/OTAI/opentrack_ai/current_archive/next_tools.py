"""Exact current-archive primitives; all publication delegates to shared save_copy."""
import os,stat,json
from typing import Annotated,Literal
from pydantic import Field,StrictStr,StrictInt,StrictBool,model_validator
from .tools import Input,PathText,ArchiveTools,sha
from .operation_tools import Name,SignedI32,RouteSelector
from .bundle_tools import Source
from . import writer as w,catalogs as c,timetable_setters as times,formation_operations as formation,path_append
from ..errors import APIError

Ordinal=Annotated[StrictInt,Field(ge=0,le=2147483647)]
class Save(Input):
    preview_only:StrictBool=True
    target_path:PathText|None=None
    @model_validator(mode='after')
    def target(self):
        if not self.preview_only and self.target_path is None:raise ValueError('Saving requires an explicit fresh target_path')
        return self
class TimeChanges(Input):
    arrival:StrictStr|None=None
    departure:StrictStr|None=None
    actual_arrival:StrictStr|None=None
    actual_departure:StrictStr|None=None
    arrival_day_offset:SignedI32|None=None
    departure_day_offset:SignedI32|None=None
    actual_arrival_day_offset:SignedI32|None=None
    actual_departure_day_offset:SignedI32|None=None
    @model_validator(mode='after')
    def supplied(self):
        if not self.model_fields_set:raise ValueError('Provide at least one explicit field')
        if any(getattr(self,k) is None for k in self.model_fields_set if k.endswith('_day_offset')):raise ValueError('Day offsets cannot be null')
        return self
class EditTimetable(Save):
    source:Source
    course_id:Name
    row_index:Ordinal
    time_mode:Literal['strict','raw']='strict'
    changes:TimeChanges
class RawPosition(Input):
    action:Literal['set_raw_engine_position']
    engine_reference_index:Ordinal
    position_value:SignedI32
class AddEngine(Input):
    action:Literal['add_engine']
    engine_catalog:Source
    engine_name:Name
    policy:Literal['contiguous','native']='contiguous'
    position_value:SignedI32|None=None
    @model_validator(mode='after')
    def position(self):
        if 'position_value' in self.model_fields_set and self.position_value is None:raise ValueError('Omit default position; null is not a position')
        return self
class RemoveEngine(Input):
    action:Literal['remove_engine']
    engine_reference_index:Ordinal
FormationAction=Annotated[RawPosition|AddEngine|RemoveEngine,Field(discriminator='action')]
class EditFormation(Save):
    source:Source
    train_name:Name
    operation:FormationAction
class InspectFormation(Input):
    source_path:PathText
    train_name:Name
class AppendPath(Save):
    project_run:Source
    documents:Annotated[dict[Name,Source],Field(min_length=1,max_length=100)]
    target_document:Name
    target_ref:RouteSelector
    source_kind:Literal['OTRoute','OTPath']
    source_ref:RouteSelector
    source_document:Name|None=None
    complete_document_set:StrictBool
    @model_validator(mode='after')
    def complete(self):
        if self.complete_document_set is not True:raise ValueError('Explicit complete supplied document-set attestation required')
        return self

class NextFunctions(ArchiveTools):
    def checked(self,spec):
        path,blob,root,version=self.read(spec.path)
        if sha(blob)!=spec.sha256:raise APIError('SOURCE_CHANGED','Input differs from inspected SHA',spec.path)
        return path,blob,root,version
    def project_scope(self,path):
        parts=path.relative_to(self.root).parts
        count=2 if parts[0]=='OTProjects' else 3
        if len(parts)<=count:raise APIError('DATASET_MISMATCH','Input must be inside a named project/workspace')
        return parts[:count]
    def same_project(self,paths):
        if len({self.project_scope(p) for p in paths})!=1:raise APIError('DATASET_MISMATCH','Inputs must belong to one named project/workspace')
    def finish(self,args,path,original,output,report,additional_inputs=None,scope_check=None):
        if len(output)>20*1024*1024:raise APIError('ARCHIVE_SIZE','Generated archive exceeds 20 MiB')
        w.load_next_compatible(output)
        inputs={path:original,**(additional_inputs or {})}
        result={'preview_only':args.preview_only,'saved':False,'source_path':str(path.relative_to(self.root)),
            'source_sha256':sha(original),'input_sources':[{'path':str(p.relative_to(self.root)),'sha256':sha(b)} for p,b in inputs.items()],
            'output_sha256':sha(output),'output_bytes':len(output),'change_report':report,
            'fresh_archive_reload_verified':True,'native_application_started':False,'complete_relocated_project':False}
        from ..json_safe import checked_json
        result=checked_json(result) 
        for p,b in inputs.items():
            if self.secure_bytes(p)!=b:raise APIError('SOURCE_CHANGED','An input changed during preview',str(p.relative_to(self.root)))
        if scope_check:scope_check()
        if args.preview_only:return result
        return self.save_copy(path,original,output,result,args.target_path,additional_inputs=additional_inputs,scope_check=scope_check)
    def timetable(self,args):
        path,blob,_,_=self.checked(args.source)
        try:output,report=times.patch_archive(blob,args.course_id,args.row_index,args.changes.model_dump(exclude_unset=True),time_mode=args.time_mode)
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_TIMETABLE_SETTER',str(e)[:500]) from e
        return self.finish(args,path,blob,output,report)
    def inspect_formation(self,args):
        path,blob,_,_=self.read(args.source_path)
        try:
            root,_,train,engines,trailers=formation.state(blob,args.train_name)
            result={'engine_references':[{'engine_reference_index':i,'engine_name':c.text(o.contents[0].value),'position_value':formation.position(o),'incoming_references':formation.occurrences(root,o)} for i,o in enumerate(engines)],
                'trailer_groups':[{'trailer_reference_index':i,'position_value':formation.position(o),'incoming_references':formation.occurrences(root,o)} for i,o in enumerate(trailers)]}
        except (ValueError,TypeError,IndexError) as e:raise APIError('CURRENT_FORMATION_SCHEMA',str(e)[:500]) from e
        return {'source_path':args.source_path,'source_sha256':sha(blob),'train_name':args.train_name,**result,
            'position_semantics':'signed saved position, not array ordinal; engine and trailer groups share position namespace','native_application_started':False}
    def edit_formation(self,args):
        path,blob,_,_=self.checked(args.source);op=args.operation;extra={}
        try:
            if op.action=='set_raw_engine_position':output,report=formation.set_engine_position_archive(blob,args.train_name,op.engine_reference_index,op.position_value)
            elif op.action=='remove_engine':output,report=formation.remove_engine_archive(blob,args.train_name,op.engine_reference_index)
            else:
                ep,eb,_,_=self.checked(op.engine_catalog)
                self.same_project([path,ep])
                if ep.parent!=path.parent or ep==path:raise APIError('DATASET_MISMATCH','Train and Engine catalogs require distinct files in the same catalog directory')
                extra[ep]=eb
                output,report=formation.add_engine_archive(blob,eb,args.train_name,op.engine_name,op.position_value,op.policy)
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_FORMATION_OPERATION',str(e)[:500]) from e
        return self.finish(args,path,blob,output,report,extra)
    def discovered_documents(self,project):
        
        found=set();count=0
        with self.parent_fd(project/'scope-probe') as (fd,_):
            def visit(parent,relative):
                nonlocal count
                for name in os.listdir(parent):
                    count+=1
                    if count>10000:raise APIError('UNVERIFIED_DOCUMENT_SCOPE','Project inventory exceeds 10000 entries')
                    meta=os.stat(name,dir_fd=parent,follow_symlinks=False)
                    if stat.S_ISLNK(meta.st_mode):raise APIError('UNVERIFIED_DOCUMENT_SCOPE','Project inventory contains a symlink')
                    path=relative/name
                    if stat.S_ISDIR(meta.st_mode):
                        child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
                        try:visit(child,path)
                        finally:os.close(child)
                    elif stat.S_ISREG(meta.st_mode):
                        if name.lower().endswith('.opentrack'):
                            if not name.endswith('.opentrack'):raise APIError('UNVERIFIED_DOCUMENT_SCOPE','Noncanonical archive extension')
                            found.add(path)
                    else:raise APIError('UNVERIFIED_DOCUMENT_SCOPE','Project inventory contains unsupported filesystem entry')
            visit(fd,project)
        return found
    def checked_document_list(self,args,inputs):
        runpath=self.path(args.project_run.path);runblob=self.secure_bytes(runpath)
        if sha(runblob)!=args.project_run.sha256:raise APIError('SOURCE_CHANGED','Project run file differs from inspected SHA')
        self.same_project([runpath]+[x[0] for x in inputs.values()])
        project=self.root.joinpath(*self.project_scope(runpath))
        if runpath.parent!=project or runpath.suffix!='.run':raise APIError('DOCUMENT_SCOPE','Select a .run file directly inside the named project')
        try:lines=runblob.decode('ascii').splitlines()
        except UnicodeDecodeError as e:raise APIError('DOCUMENT_SCOPE','Audited run document list requires ASCII') from e
        paths=[];set_paths=[]
        for line in lines:
            if not line.strip() or line.startswith('//'):continue
            parts=line.split('#')
            if len(parts)!=3 or parts[2]!='':raise APIError('DOCUMENT_SCOPE','Malformed run key#value# record')
            if parts[0] not in ('Infrastructure Document','Document Set Document'):
                if 'Infrastructure' in parts[0] or ('Document Set' in parts[0] and parts[0]!='Document Set Name'):raise APIError('DOCUMENT_SCOPE','Unknown infrastructure document-list key')
                continue
            raw=parts[1]
            if not raw or '%' in raw or '\\' in raw:raise APIError('DOCUMENT_SCOPE','No template placeholders or foreign-platform run paths')
            from pathlib import Path
            value=Path(raw)
            if '..' in value.parts:raise APIError('DOCUMENT_SCOPE','Run path traversal is unsupported')
            candidate=value if value.is_absolute() else project/value
            try:relative=candidate.relative_to(self.root).as_posix()
            except ValueError as e:raise APIError('DOCUMENT_SCOPE','Run references an archive outside the data root') from e
            candidate=self.path(relative)
            if self.project_scope(candidate)!=self.project_scope(runpath):raise APIError('DOCUMENT_SCOPE','Run document is outside this project')
            (paths if parts[0]=='Infrastructure Document' else set_paths).append(candidate)
        if not paths or len(paths)!=len(set(paths)) or set(paths)!={x[0] for x in inputs.values()}:
            raise APIError('DOCUMENT_SCOPE','Supplied archive paths must exactly match the nonempty unique run Infrastructure Document list')
        if set_paths and (len(set_paths)!=len(set(set_paths)) or set(set_paths)!=set(paths)):raise APIError('DOCUMENT_SCOPE','Document Set Document conflicts with Infrastructure Document list')
        if self.discovered_documents(project)!=set(paths):raise APIError('UNVERIFIED_DOCUMENT_SCOPE','Actual project .opentrack inventory differs from run/supplied documents')
        if any(key!=item[0].stem for key,item in inputs.items()):raise APIError('DOCUMENT_SCOPE','Document keys must equal unique selected filename stems')
        external_labels=[]
        for _,_,root,_ in inputs.values():
            for obj in w.objects(root):
                if w.kind(obj)!='OTArrayExtInfo':continue
                path_append.f.hierarchy(obj,[('OTArrayExtInfo',0),('OTArrayInfo',0),('NSObject',0)])
                if len(obj.contents)!=3 or [g.encodings for g in obj.contents]!=[[b'@'],[b'i',b'i'],[b'@']]:raise APIError('DOCUMENT_SCOPE','Unknown external reference shape')
                label=path_append.f.string(obj.contents[2].value)
                external_labels.append(label)
                if label not in inputs:raise APIError('DOCUMENT_SCOPE','Unresolved external Itinerary document label',label)
        expected=set(paths)
        def check_scope(published_target=None):
            actual=self.discovered_documents(project)
            if published_target is not None:actual.discard(published_target)
            if actual!=expected:raise APIError('UNVERIFIED_DOCUMENT_SCOPE','Project archive inventory changed during operation')
        evidence={'project_root':str(project.relative_to(self.root)),'inventory_paths':sorted(str(p.relative_to(self.root)) for p in expected),
            'run_syntax':'provided run.template / archive.parse_run ASCII key#value# subset; not native-run provenance proof',
            'external_reference_count':len(external_labels),'resolved_external_document_labels':sorted(set(external_labels))}
        return runpath,runblob,check_scope,evidence
    def append_path(self,args):
        inputs={key:self.checked(spec) for key,spec in args.documents.items()}
        self.same_project([x[0] for x in inputs.values()])
        if len({x[0] for x in inputs.values()})!=len(inputs):raise APIError('DATASET_MISMATCH','Each document key must identify a distinct archive file')
        if args.target_document not in inputs:raise APIError('DATASET_MISMATCH','Target document is not supplied')
        runpath,runblob,scope_check,scope_evidence=self.checked_document_list(args,inputs)
        try:
            outputs,report=path_append.append_existing({k:x[1] for k,x in inputs.items()},args.target_document,args.target_ref.model_dump(),args.source_kind,args.source_ref.model_dump(),args.source_document,complete_document_set=args.complete_document_set)
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_PATH_APPEND',str(e)[:500]) from e
        path,blob,_,_=inputs[args.target_document]
        report['document_scope']={**scope_evidence,'complete_set_attested_by_caller':True,'run_document_list_matched':True,'project_archive_inventory_matched':True,'run_source_sha256':sha(runblob),'independently_discovered_complete_project':False,'provided_document_keys':list(inputs),'guarantee':'provided document collection only; no omitted-archive integrity claim'}
        return self.finish(args,path,blob,outputs[args.target_document],report,{runpath:runblob,**{x[0]:x[1] for k,x in inputs.items() if k!=args.target_document}},scope_check=scope_check)

def tool_definitions(root):
    service=NextFunctions(root)
    return [
        ('opentrack_edit_current_timetable','Exact existing CourseID#index primitive setters: four time strings and four signed int32 days. Strict clock policy by default, explicit raw string/nil mode; never implicitly edit actual fields, references or propagate intervals. Preview/fresh copy only.',EditTimetable,service.timetable,False,False),
        ('opentrack_inspect_current_formation','Read exact engine array ordinals, saved positions and ownership counts, plus trailer group positions. Ordinal is not position; no mutation or derived physical calculation.',InspectFormation,service.inspect_formation),
        ('opentrack_edit_current_formation','Native raw engine position setter, append using same-project Engine catalog, or ordinal removal plus native position decrements. Contiguous append safety policy by default; explicit native signed-int policy. No movement/reordering or physical recalculation.',EditFormation,service.edit_formation,False,False),
        ('opentrack_append_current_path','Append existing local Route or flattened local Path to existing unreferenced current Path. Explicit same-project document collection and caller completeness attestation required. Guarded local domain only; rejects cross-document continuation/dependencies. Preview or fresh saved file.',AppendPath,service.append_path,False,False),
    ]
