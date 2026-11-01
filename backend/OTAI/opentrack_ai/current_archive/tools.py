"""Precise current-archive tools: real bytes, immutable source, fresh atomic copy."""
import hashlib,os,stat,uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated,Literal
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt,StrictStr,model_validator
from ..errors import APIError
from . import writer as w
from . import catalogs as c
from .platform_support import require_secure_filesystem

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    @model_validator(mode='before')
    @classmethod
    def strict_preview_boolean(cls, value):
        
        if isinstance(value, dict) and 'preview_only' in value and type(value['preview_only']) is not bool:
            raise ValueError('preview_only must be an actual JSON boolean')
        return value
PathText=Annotated[StrictStr,Field(min_length=1,max_length=500)]
class InspectArchive(Input):
    source_path:PathText
    catalog:Literal['engines','trains','courses','stations','categories','timetable','itineraries']
    offset:Annotated[StrictInt,Field(ge=0)]=0
    limit:Annotated[StrictInt,Field(ge=1,le=200)]=50
class PatchEngine(Input):
    source_path:PathText
    expected_sha256:Annotated[StrictStr,Field(pattern=r'^[0-9a-f]{64}$')]
    engine_name:Annotated[StrictStr,Field(min_length=1,max_length=200)]
    maximum_speed_kmh:Annotated[StrictInt,Field(gt=0,le=1000)]
    preview_only:StrictBool=True
    target_path:PathText|None=None
    @model_validator(mode='after')
    def destination(self):
        if not self.preview_only and self.target_path is None:raise ValueError('Saving requires an explicit fresh target_path')
        return self

def sha(blob):return hashlib.sha256(blob).hexdigest()
class ArchiveTools:
    def __init__(self,root):
        
        
        self.root=Path(os.path.abspath(root)) if os.name=='nt' else Path(root).resolve()
    def path(self,value):
        raw=Path(value)
        if raw.is_absolute() or '..' in raw.parts:raise APIError('ARCHIVE_PATH','Use a traversal-free relative path under OTProjects or OTAI/workspaces')
        
        
        p=self.root/raw
        bases=[self.root/'OTProjects',self.root/'OTAI/workspaces']
        if not p.is_relative_to(self.root) or not any(p.is_relative_to(base) and p!=base for base in bases):
            raise APIError('PATH_OUTSIDE_SCOPE','Archive path must remain under OTProjects or OTAI/workspaces')
        return p
    @contextmanager
    def parent_fd(self,path):
        """Walk only directory FDs: concurrent path symlinks are never followed."""
        if os.name!='posix':
            raise APIError('UNSUPPORTED_SECURE_FILESYSTEM','Descriptor-relative directory enumeration/publication requires the POSIX implementation; Windows support is limited to handle-backed secure_bytes reads.',{'operation':'directory_fd','os_name':os.name})
        require_secure_filesystem('read')
        parts=path.relative_to(self.root).parts
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=nxt
            yield fd,parts[-1]
        finally:os.close(fd)
    def secure_bytes(self,path):
        require_secure_filesystem('read')
        if os.name=='nt':
            from .windows_io import secure_bytes
            return secure_bytes(self.root,path)
        with self.parent_fd(path) as (parent,name):
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
            with os.fdopen(fd,'rb') as stream:
                meta=os.fstat(stream.fileno())
                if not stat.S_ISREG(meta.st_mode):raise APIError('ARCHIVE_NOT_FILE','Archive must be a regular file')
                if meta.st_size>20*1024*1024:raise APIError('ARCHIVE_SIZE','Archive exceeds 20 MiB limit')
                blob=stream.read(20*1024*1024+1)
                if len(blob)>20*1024*1024:raise APIError('ARCHIVE_SIZE','Archive exceeds 20 MiB limit')
                return blob
    @staticmethod
    def unlink_owned(parent,name,identity):
        try:
            found=os.stat(name,dir_fd=parent,follow_symlinks=False)
            if (found.st_dev,found.st_ino)==identity:os.unlink(name,dir_fd=parent)
        except FileNotFoundError:pass
    def read(self,value):
        p=self.path(value)
        blob=self.secure_bytes(p)
        try:root,version=w.load_next_compatible(blob)
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_ARCHIVE_DECODE','Unsupported or malformed typedstream archive',str(e)[:300]) from e
        return p,blob,root,version
    def inspect(self,args):
        path,blob,root,version=self.read(args.source_path)
        try:
            if args.catalog=='engines':rows=[{'id':c.text(x.contents[1].value),'class':'OTEngine','class_version':2,'maximum_speed_kmh':x.contents[7].value} for x in c.engine_items(root)]
            elif args.catalog=='trains':rows=[{'id':c.text(x.contents[0].value),'class':'OTTrain','class_version':16,'engine_references':c.bound_engine_names(x)} for x in c.train_items(root)]
            elif args.catalog=='courses':rows=[{'id':c.text(x.contents[0].value),'class':'OTCourse','class_version':11,'train':c.text(x.contents[3].value)} for x in c.course_items(root)]
            elif args.catalog=='stations':rows=[{'id':key,'class':'OTStation','class_version':3} for key in c.station_items(root)]
            elif args.catalog=='categories':
                from .stock_operations import CATEGORY_LAYOUT
                c.train_items(root);rows=[];names=set()
                for obj in c.array(root.contents[1].value):
                    c.shape(obj,'OTTrainCategory',19,CATEGORY_LAYOUT);name=c.text(obj.contents[1].value)
                    if not name or name in names:raise ValueError('Empty/duplicate Category name')
                    names.add(name);rows.append({'id':name,'class':'OTTrainCategory','class_version':19})
            elif args.catalog=='timetable':
                from .course_factories import timetable
                rows=[{'id':key,'class':'OTTimetable','class_version':9,'course_id':c.text(obj.contents[1].value),'station_sign':c.text(obj.contents[5].value),
                       'arrival':None if obj.contents[6].value is None else c.text(obj.contents[6].value),'departure':None if obj.contents[7].value is None else c.text(obj.contents[7].value),
                       'actual_arrival':None if obj.contents[13].value is None else c.text(obj.contents[13].value),'actual_departure':None if obj.contents[14].value is None else c.text(obj.contents[14].value),
                       'arrival_day_offset':obj.contents[15].values[0],'departure_day_offset':obj.contents[15].values[1],'actual_arrival_day_offset':obj.contents[15].values[2],'actual_departure_day_offset':obj.contents[15].values[3],'connection_count':len(c.array(obj.contents[9].value))} for key,obj in timetable(root).items()]
            else:
                from .course_factories import itinerary_names
                rows=[{'id':name,'class':'OTDestInfo','class_version':1} for name in sorted(itinerary_names(root))]

        except (c.CatalogSchemaError,ValueError,IndexError,TypeError) as e:raise APIError('CURRENT_CATALOG_SCHEMA','Unsupported current catalog shape',str(e)[:300]) from e
        return {'source_path':str(path.relative_to(self.root)),'source_sha256':sha(blob),'source_bytes':len(blob),'archive_system_version':version,
            'catalog':args.catalog,'items':rows[args.offset:args.offset+args.limit],'total_count':len(rows),'has_more':args.offset+args.limit<len(rows),
            'implementation':'independent current_archive codec/accessors','native_application_started':False}
    def patch(self,args):
        source,original,root,version=self.read(args.source_path)
        if sha(original)!=args.expected_sha256:raise APIError('SOURCE_CHANGED','Source does not match the inspected SHA-256')
        try:matches=[x for x in c.engine_items(root) if c.text(x.contents[1].value)==args.engine_name]
        except (c.CatalogSchemaError,ValueError,TypeError,IndexError) as e:raise APIError('CURRENT_CATALOG_SCHEMA','Unsupported current Engine catalog',str(e)[:300]) from e
        if len(matches)!=1:raise APIError('ENGINE_NOT_FOUND','An exact unique Engine name is required')
        row=matches[0];before=row.contents[7].value
        row.contents[7].value=args.maximum_speed_kmh
        try:
            output=w.dump_verified(root,version)
            fresh,_=w.load_next_compatible(output)
            actual=next(x for x in c.engine_items(fresh) if c.text(x.contents[1].value)==args.engine_name)
            if actual.contents[7].value!=args.maximum_speed_kmh:raise ValueError('Freshly decoded value differs')
        except (ValueError,IndexError,TypeError,OverflowError) as e:raise APIError('CURRENT_ARCHIVE_VERIFY','Edited archive failed save/reload verification',str(e)[:300]) from e
        result={'preview_only':args.preview_only,'source_path':args.source_path,'source_sha256':sha(original),'output_sha256':sha(output),'output_bytes':len(output),
            'changes':[{'engine_name':args.engine_name,'field':'maximum_speed_kmh','before':before,'after':args.maximum_speed_kmh,'unit':'km/h','archive_group':7,'encoding':'i'}],
            'function_evidence':{'setter':'0x004cbe00','getter':'0x004cb4d0','encoder':'0x004ccc54'},
            'input_domain':'API safety bound: integer 1..1000 km/h; original setter accepts an int without these API bounds',
            'fresh_archive_reload_verified':True,'native_application_started':False,'saved':False}
        if args.preview_only:return result
        return self.save_copy(source,original,output,result,args.target_path)

    def save_copy(self,source,original,output,result,target_path,additional_inputs=None,scope_check=None,validate_output=w.load_next_compatible):
        require_secure_filesystem('save_copy')
        from ..json_safe import checked_json
        result=checked_json(result) 
        target=self.path(target_path)
        inputs={source:original,**(additional_inputs or {})}
        if target in inputs:raise APIError('TARGET_EXISTS','Target must differ from every input')
        def recheck():
            for path,blob in inputs.items():
                if self.secure_bytes(path)!=blob:raise APIError('SOURCE_CHANGED','An input changed during operation',str(path.relative_to(self.root)))
        if os.name=='nt':
            from .windows_publish import save_copy
            publication=save_copy(self.root,target,output,recheck=recheck,validate_output=validate_output,scope_check=scope_check)
            return {**result,**publication,'source_unchanged':True,'all_input_hashes_rechecked':True}
        recheck()
        if scope_check:scope_check()
        with self.parent_fd(target) as (parent,name):
            temporary='.opentrack-archive-'+uuid.uuid4().hex
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
            own=os.fstat(fd);identity=(own.st_dev,own.st_ino);linked=False
            try:
                with os.fdopen(fd,'wb') as stream:stream.write(output);stream.flush();os.fsync(stream.fileno())
                recheck()
                if scope_check:scope_check()
                try:os.link(temporary,name,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False);linked=True
                except FileExistsError as e:raise APIError('TARGET_EXISTS','Target exists; nothing overwritten') from e
                
                checkfd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
                with os.fdopen(checkfd,'rb') as stream:
                    meta=os.fstat(stream.fileno())
                    if (meta.st_dev,meta.st_ino)!=identity:raise APIError('TARGET_CHANGED','Fresh target was replaced concurrently')
                    actual_blob=stream.read(len(output)+1)
                validate_output(actual_blob)
                if actual_blob!=output:
                    raise APIError('CURRENT_ARCHIVE_VERIFY','Saved file reload verification failed')
                recheck()
                if scope_check:scope_check(target)
                os.fsync(parent)
            except Exception as error:
                if linked:
                    raise APIError('ARCHIVE_COMMITTED_POSTCHECK_FAILED','A fresh archive file was published, but a subsequent check failed. Inspect the target and expected hash; do not blindly retry or overwrite.',
                        {'commit_completed':True,'post_commit_verification':False,'target_path':str(target.relative_to(self.root)),'expected_sha256':sha(output),'expected_bytes':len(output),
                         'complete_relocated_project':False,'cause_code':getattr(error,'code',None),'reason':str(error)[:300]}) from error
                raise
            finally:self.unlink_owned(parent,temporary,identity)
        return {**result,'saved':True,'target_path':str(target.relative_to(self.root)),'source_unchanged':True,'atomic_no_replace':True,'all_input_hashes_rechecked':True}

def tool_definitions(root):
    service=ArchiveTools(root)
    return [
        ('opentrack_inspect_current_archive','Read a real current Engine/Train/Category/Course/Station/Timetable/Itinerary-info catalog from a scoped path. Validate exact current record layouts and return identities/source SHA for reviewed edits. No GUI or simulation.',InspectArchive,service.inspect),
        ('opentrack_patch_current_engine','Preview or save a fresh archive copy changing only one current Engine maximum-speed integer in km/h. Require inspected source SHA, exact Engine name, explicit fresh target for saving; atomic no-overwrite and real file reload. Input 1..1000 is API safety range, not native setter restriction.',PatchEngine,service.patch,False,False),
    ]
