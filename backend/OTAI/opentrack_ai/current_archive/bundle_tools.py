"""Explicit-template Course/timetable creation into a fresh atomic catalog bundle."""
import ctypes,errno,json,os,sys,uuid,stat
from pathlib import Path
from typing import Annotated,Literal
from pydantic import Field,StrictStr,StrictInt,StrictBool,StrictFloat,model_validator
from .tools import Input,PathText,ArchiveTools,sha
from .operation_tools import Name
from . import writer as w,catalogs as c,course_factories as factory
from ..errors import APIError

class Source(Input):
    path:PathText
    sha256:Annotated[StrictStr,Field(pattern=r'^[0-9a-f]{64}$')]
class Sources(Input):
    courses:Source
    trains:Source
    dest:Source
    stations:Source
    timetable:Source
Num=Annotated[StrictFloat|StrictInt,Field(allow_inf_nan=False)]
class CourseFields(Input):
    speed_type:StrictStr|None=None
    description:StrictStr|None=None
    comment:StrictStr|None=None
    train_number:StrictStr|None=None
    course_type:StrictStr|None=None
    acceleration_percent:Annotated[StrictInt,Field(ge=50,le=100)]|None=None
    delayed_acceleration_percent:Annotated[StrictInt,Field(ge=50,le=100)]|None=None
    enabled:StrictBool|None=None
    entering_speed_kmh:Annotated[Num,Field(ge=0,le=1000)]|None=None
    output_offset_m:Annotated[Num,Field(ge=-1000000,le=1000000)]|None=None
    spacing_mode:Literal['discrete','moving','moving_cbtc']|None=None
    additional_reservation_time_s:Annotated[Num,Field(ge=0,le=86400)]|None=None
    additional_release_time_s:Annotated[Num,Field(ge=0,le=86400)]|None=None
    @model_validator(mode='after')
    def no_null(self):
        if any(getattr(self,k) is None for k in self.model_fields_set):raise ValueError('Omit inherited Course fields; explicit null is not a value')
        return self
class Stop(Input):
    template_key:Name
    station_sign:Name
    arrival:StrictStr|None
    departure:StrictStr|None
    arrival_day_offset:Annotated[StrictInt,Field(ge=-366,le=366)]
    departure_day_offset:Annotated[StrictInt,Field(ge=-366,le=366)]
    stop_at_station:StrictBool|None=None
    timing_station:StrictBool|None=None
    interval_reference_course_id:StrictStr|None=None
    interval_offset_s:Annotated[Num,Field(ge=-31622400,le=31622400)]|None=None
    dwell_s:Annotated[Num,Field(ge=0,le=86400)]|None=None
    mean_delay_s:Annotated[Num,Field(ge=0,le=86400)]|None=None
    track_id:StrictStr|None=None
    distribution_name:StrictStr|None=None
    delta_mass_t:Annotated[Num,Field(ge=-1000000,le=1000000)]|None=None
    @model_validator(mode='after')
    def nulls(self):
        allowed={'arrival','departure','interval_reference_course_id'}
        if any(getattr(self,k) is None for k in self.model_fields_set-allowed):raise ValueError('Omit inherited row fields; explicit null is unsupported')
        return self
class GenerateCourse(Input):
    sources:Sources
    external_engine_catalog:Source
    template_id:Name
    course_id:Name
    train:Name
    itineraries:Annotated[list[Name],Field(min_length=1,max_length=1000)]
    stops:Annotated[list[Stop],Field(min_length=1,max_length=10000)]
    fields:CourseFields=Field(default_factory=CourseFields)
    preview_only:StrictBool=True
    target_directory:PathText|None=None
    @model_validator(mode='after')
    def target(self):
        if not self.preview_only and self.target_directory is None:raise ValueError('Saving requires a fresh target_directory')
        return self

class CourseBundles(ArchiveTools):
    @staticmethod
    def rename_noreplace(parent,source,target):
        if not sys.platform.startswith('linux'):raise APIError('ATOMIC_BUNDLE_UNSUPPORTED','Atomic no-replace directory commit requires Linux renameat2')
        libc=ctypes.CDLL(None,use_errno=True)
        if not hasattr(libc,'renameat2'):raise APIError('ATOMIC_BUNDLE_UNSUPPORTED','Host libc lacks renameat2')
        fn=libc.renameat2;fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
        if fn(parent,os.fsencode(source),parent,os.fsencode(target),1)!=0:
            err=ctypes.get_errno()
            if err==errno.EEXIST:raise APIError('TARGET_EXISTS','Bundle target exists; nothing overwritten')
            if err in (errno.ENOSYS,errno.EINVAL,errno.EOPNOTSUPP):raise APIError('ATOMIC_BUNDLE_UNSUPPORTED','Filesystem cannot atomically commit a no-replace directory')
            raise OSError(err,os.strerror(err))
    def generate(self,args):
        inputs={};blobs={};roots={};receipts={}
        for key,spec in {**{k:getattr(args.sources,k) for k in type(args.sources).model_fields},'external_engines':args.external_engine_catalog}.items():
            path,blob,root,_=self.read(spec.path)
            if sha(blob)!=spec.sha256:raise APIError('SOURCE_CHANGED','An input differs from its inspected SHA',key)
            inputs[key]=path;blobs[key]=blob;roots[key]=root;receipts[key]={'source_path':spec.path,'sha256':spec.sha256}
        if len({p.parent for p in inputs.values()})!=1:raise APIError('DATASET_MISMATCH','All six inputs must belong to the same catalog directory')
        try:
            engines={c.text(x.contents[1].value) for x in c.engine_items(roots['external_engines'])}
            for train in c.train_items(roots['trains']):
                if not set(c.bound_engine_names(train))<=engines:raise ValueError('Train refers to missing Engine name')
            before_courses=len(c.course_items(roots['courses']));before_rows=len(factory.timetable(roots['timetable']))
            changed=factory.generate({k:v for k,v in blobs.items() if k!='external_engines'},template_id=args.template_id,course_id=args.course_id,train=args.train,
                itineraries=list(args.itineraries),stops=[x.model_dump(exclude_unset=True) for x in args.stops],fields=args.fields.model_dump(exclude_unset=True))
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_COURSE_FACTORY',str(e)[:500]) from e
        output={k:changed.get(k,blobs[k]) for k in type(args.sources).model_fields}
        if any(len(b)>20*1024*1024 for b in output.values()):raise APIError('ARCHIVE_SIZE','An output exceeds 20 MiB')
        fresh={k:w.load_next_compatible(v)[0] for k,v in output.items()}
        after_courses=c.course_items(fresh['courses']);after_rows=factory.timetable(fresh['timetable'])
        if len(after_courses)!=before_courses+1 or len(after_rows)!=before_rows+len(args.stops):raise APIError('CURRENT_ARCHIVE_VERIFY','Generated counts differ after fresh load')
        docpaths=sorted({c.text(x.contents[2].value) for x in c.array(roots['dest'].contents[0].value)})
        external={'engine_catalog':{**receipts['external_engines'],'included':False,'all_train_engine_names_resolved':True},
            'documents':[{'original_saved_path':p,'sha256':None,'included':False,'loaded_or_rebased':False} for p in docpaths],
            'project_run_file_included':False,'complete_relocated_project':False}
        manifest={'format':'opentrack-current-catalog-increment-v1','sources':receipts,'files':{f'empty.{k}':{'sha256':sha(v),'bytes':len(v),'changed':k in changed} for k,v in output.items()},
            'created_course':args.course_id,'created_timetable_rows':len(args.stops),'external_dependencies':external,
            'template_semantics':'Explicit current template; not guessed init defaults or claimed copyWithZone equivalence'}
        result={'preview_only':args.preview_only,'saved':False,'bundle_type':'catalog increment, not a relocated complete Project','manifest':manifest,
            'before':{'courses':before_courses,'timetable_rows':before_rows},'after':{'courses':len(after_courses),'timetable_rows':len(after_rows)},
            'fresh_archive_reload_verified':True,'native_application_started':False}
        return self.publish_bundle(inputs={inputs[k]:blobs[k] for k in inputs},members={f'empty.{k}':v for k,v in output.items()},manifest=manifest,result=result,target_directory=args.target_directory)

    def publish_bundle(self,*,inputs,members,manifest,result,target_directory,scope_check=None,member_validators=None,empty_directories=()):
        
        
        if not members or any(not isinstance(n,str) or n in ('','.','..','bundle-manifest.json') or '/' in n or '\\' in n or '\0' in n for n in members):raise APIError('BUNDLE_MEMBERS','Flat distinct archive member names required')
        from ..json_safe import checked_json
        validators={} if member_validators is None else member_validators
        if not isinstance(validators,dict) or not set(validators)<=set(members) or not all(callable(f) for f in validators.values()):raise APIError('BUNDLE_VALIDATORS','Explicit member validator mapping required')
        if not isinstance(empty_directories,(list,tuple)):raise APIError('BUNDLE_DIRECTORIES','Explicit list of flat directories required')
        directories=tuple(empty_directories)
        if any(not isinstance(n,str) or n in ('','.','..','bundle-manifest.json') or '/' in n or '\\' in n or '\0' in n for n in directories):raise APIError('BUNDLE_DIRECTORIES','Flat fresh directory names required')
        all_names=list(members)+['bundle-manifest.json']+list(directories)
        if len({n.casefold() for n in all_names})!=len(all_names):raise APIError('BUNDLE_MEMBERS','Case-insensitive file/directory collision')
        def validate_member(name,blob):
            if len(blob)>20*1024*1024:raise APIError('ARCHIVE_SIZE','Output exceeds 20 MiB')
            if name in validators:validators[name](blob)
            else:w.load_next_compatible(blob)
        result=checked_json(result);manifest=checked_json(manifest)
        expected_directories=[{'path':n,'empty':True} for n in directories]
        if manifest.get('directories',expected_directories)!=expected_directories:raise APIError('BUNDLE_DIRECTORIES','Manifest directory contract mismatch')
        manifest['directories']=expected_directories
        if 'manifest' in result:result['manifest']=manifest
        for name,blob in members.items():validate_member(name,blob)
        def check_inputs():
            for path,blob in inputs.items():
                if self.secure_bytes(path)!=blob:raise APIError('SOURCE_CHANGED','A dependency changed during bundle generation',str(path.relative_to(self.root)))
            if scope_check:scope_check()
        check_inputs()
        if result['preview_only']:return result
        target=self.path(target_directory)
        if any(target==p or p.is_relative_to(target) for p in inputs):raise APIError('TARGET_EXISTS','Bundle target cannot enclose or equal an input')
        with self.parent_fd(target) as (parent,name):
            staging='.opentrack-bundle-'+uuid.uuid4().hex
            os.mkdir(staging,0o700,dir_fd=parent)
            stagefd=os.open(staging,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            meta=os.fstat(stagefd);stage_identity=(meta.st_dev,meta.st_ino)
            owned={};owned_dirs={};committed=False
            def check_directories(parentfd):
                for dirname,identity in owned_dirs.items():
                    current=os.stat(dirname,dir_fd=parentfd,follow_symlinks=False)
                    if not stat.S_ISDIR(current.st_mode) or (current.st_dev,current.st_ino)!=identity:raise APIError('TARGET_CHANGED','Output directory identity changed')
                    child=os.open(dirname,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parentfd)
                    try:
                        opened=os.fstat(child)
                        if (opened.st_dev,opened.st_ino)!=identity:raise APIError('TARGET_CHANGED','Opened output directory identity changed')
                        if os.listdir(child):raise APIError('TARGET_CHANGED','Fresh output directory is not empty')
                        os.fsync(child)
                    finally:os.close(child)
            try:
                for dirname in directories:
                    os.mkdir(dirname,0o700,dir_fd=stagefd)
                    st=os.stat(dirname,dir_fd=stagefd,follow_symlinks=False);owned_dirs[dirname]=(st.st_dev,st.st_ino)
                staged_members=dict(members)
                staged_members['bundle-manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False).encode()
                for filename,blob in staged_members.items():
                    fd=os.open(filename,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=stagefd)
                    st=os.fstat(fd);owned[filename]=(st.st_dev,st.st_ino)
                    with os.fdopen(fd,'wb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
                    fd=os.open(filename,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=stagefd)
                    with os.fdopen(fd,'rb') as stream:actual=stream.read(len(blob)+1)
                    if actual!=blob:raise APIError('CURRENT_ARCHIVE_VERIFY','Staged file bytes differ')
                    if filename!='bundle-manifest.json':validate_member(filename,actual)
                check_inputs()
                check_directories(stagefd)
                os.fsync(stagefd)
                current=os.stat(staging,dir_fd=parent,follow_symlinks=False)
                if (current.st_dev,current.st_ino)!=stage_identity:raise APIError('TARGET_CHANGED','Staging directory was replaced')
                self.rename_noreplace(parent,staging,name);committed=True;os.fsync(parent)
                current=os.stat(name,dir_fd=parent,follow_symlinks=False)
                if (current.st_dev,current.st_ino)!=stage_identity:raise APIError('TARGET_CHANGED','Committed directory was replaced')
            except Exception as error:
                if committed:
                    raise APIError('BUNDLE_COMMITTED_POSTCHECK_FAILED','The whole bundle was atomically committed, but a subsequent durability/identity check failed. Inspect target; do not retry as an overwrite.',
                        {'commit_completed':True,'post_commit_verification':False,'bundle_type':result.get('bundle_type','archive increment'),'complete_relocated_project':False,'target_directory':str(target.relative_to(self.root)),'expected_files':manifest['files'],'expected_directories':manifest['directories'],'reason':str(error)[:300]}) from error
                raise
            finally:
                if not committed:
                    for filename,identity in owned.items():self.unlink_owned(stagefd,filename,identity)
                    for dirname,identity in owned_dirs.items():
                        try:
                            current=os.stat(dirname,dir_fd=stagefd,follow_symlinks=False)
                            if stat.S_ISDIR(current.st_mode) and (current.st_dev,current.st_ino)==identity:os.rmdir(dirname,dir_fd=stagefd)
                        except OSError:pass
                    try:
                        current=os.stat(staging,dir_fd=parent,follow_symlinks=False)
                        if (current.st_dev,current.st_ino)==stage_identity:os.rmdir(staging,dir_fd=parent)
                    except OSError:pass
                os.close(stagefd)
        
        try:
            for filename,blob in staged_members.items():
                if self.secure_bytes(target/filename)!=blob:raise APIError('TARGET_CHANGED','Committed bundle was changed by another writer')
            with self.parent_fd(target/'_directory_check') as (committedfd,_):check_directories(committedfd)
            check_inputs()
        except Exception as error:
            raise APIError('BUNDLE_COMMITTED_POSTCHECK_FAILED','The whole bundle was atomically committed, but final path verification failed. Inspect target; no existing files will be overwritten on retry.',
                {'commit_completed':True,'post_commit_verification':False,'bundle_type':result.get('bundle_type','archive increment'),'complete_relocated_project':False,'target_directory':str(target.relative_to(self.root)),'expected_files':manifest['files'],'expected_directories':manifest['directories'],'reason':str(error)[:300]}) from error
        return {**result,'saved':True,'target_directory':str(target.relative_to(self.root)),'atomic_directory_commit':True,'source_hashes_rechecked_before_commit':True,'source_hashes_rechecked_after_commit':True,'commit_completed':True,'created_empty_directories':list(directories)}

def tool_definitions(root):
    service=CourseBundles(root)
    return [('opentrack_generate_current_course','Create one Course and explicit timetable rows from named current archive templates, validating actual Train/Engine/Itinerary/Station references. Preview or atomically save five catalogs as a fresh incremental bundle, not a complete relocated Project; external document dependencies are explicit. No guessed defaults or GUI.',GenerateCourse,service.generate,False,False)]
