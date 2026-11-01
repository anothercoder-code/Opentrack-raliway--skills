"""Strict six-catalog batch API using the existing atomic bundle publisher."""
from typing import Annotated, Literal
from pydantic import Field, StrictInt, StrictFloat, StrictBool, StrictStr, model_validator
from .tools import Input, PathText, sha
from .bundle_tools import Source, CourseBundles
from .operation_tools import Name
from .catalog_batch_reuse.catalog_batch import apply_batch
from ..errors import APIError

Names=Annotated[list[Name],Field(min_length=1,max_length=10000)]
class BatchSources(Input):
    depot:Source
    trains:Source
    courses:Source
    dest:Source
    stations:Source
    timetable:Source
class EngineEdit(Input):
    kind:Literal['update_engines']
    names:Names
    cw_value:Annotated[StrictFloat|StrictInt,Field(ge=0,le=100,allow_inf_nan=False)]|None=None
    understands_radio:StrictBool|None=None
    @model_validator(mode='after')
    def fields(self):
        editable=self.model_fields_set-{'kind','names'}
        if not editable or any(getattr(self,k) is None for k in editable):raise ValueError('Explicit non-null Engine changes required')
        return self
class CourseEdit(Input):
    kind:Literal['update_courses']
    course_ids:Names
    acceleration_percent:Annotated[StrictInt,Field(ge=50,le=100)]|None=None
    delayed_acceleration_percent:Annotated[StrictInt,Field(ge=50,le=100)]|None=None
    comment:Annotated[StrictStr,Field(max_length=240,pattern=r'^[\x20-\x7E]*$')]|None=None
    @model_validator(mode='after')
    def fields(self):
        editable=self.model_fields_set-{'kind','course_ids'}
        if not editable or any(getattr(self,k) is None for k in editable):raise ValueError('Explicit non-null Course changes required')
        return self
class ShiftRows(Input):
    kind:Literal['shift_timetable_rows']
    course_ids:Names
    seconds:Annotated[StrictInt,Field(ge=-(2**31),lt=2**31)]
    include_actual:StrictBool=False
    @model_validator(mode='after')
    def planned_only(self):
        if self.include_actual:raise ValueError('Only planned arrival/departure shifting is supported')
        return self
Operation=Annotated[EngineEdit|CourseEdit|ShiftRows,Field(discriminator='kind')]
class CatalogBatch(Input):
    sources:BatchSources
    operations:Annotated[list[Operation],Field(min_length=1,max_length=100)]
    preview_only:StrictBool=True
    target_directory:PathText|None=None
    @model_validator(mode='after')
    def destination(self):
        if not self.preview_only and self.target_directory is None:raise ValueError('Saving requires a fresh target_directory')
        return self
class CatalogBatchTools(CourseBundles):
    def apply(self,args):
        inputs={};blobs={};receipts={}
        for key in type(args.sources).model_fields:
            spec=getattr(args.sources,key);path,blob,_,_=self.read(spec.path)
            if sha(blob)!=spec.sha256:raise APIError('SOURCE_CHANGED','Catalog differs from inspected SHA',key)
            inputs[key]=path;blobs[key]=blob;receipts[key]={'source_path':spec.path,'sha256':spec.sha256}
        if len(set(inputs.values()))!=6 or len({p.parent for p in inputs.values()})!=1:
            raise APIError('DATASET_MISMATCH','All six distinct catalogs must belong to the same catalog directory')
        try:output,report=apply_batch(blobs,[x.model_dump(exclude_unset=True) for x in args.operations])
        except (ValueError,TypeError,IndexError,OverflowError) as exc:raise APIError('CURRENT_CATALOG_BATCH',str(exc)[:500]) from exc
        members={inputs[k].name:blob for k,blob in output.items()}
        manifest={'format':'opentrack-current-catalog-batch-v1','sources':receipts,
            'files':{inputs[k].name:{'sha256':sha(blob),'bytes':len(blob),'changed':blob!=blobs[k]} for k,blob in output.items()},
            'complete_relocated_project':False,'infrastructure_documents_included':False,'run_file_included':False,
            'operation_report':report}
        result={'preview_only':args.preview_only,'saved':False,'bundle_type':'six-catalog increment, not a complete relocated Project',
            'manifest':manifest,'report':report,'native_application_started':False,'fresh_archive_reload_verified':True}
        return self.publish_bundle(inputs={inputs[k]:blobs[k] for k in inputs},members=members,manifest=manifest,result=result,target_directory=args.target_directory)

def tool_definitions(root):
    service=CatalogBatchTools(root)
    return [('opentrack_batch_current_catalogs','Atomically batch narrow current catalog edits: Engine cw/radio, Course acceleration/delayed acceleration/comment, planned-only timetable shifts. Requires six real same-directory SHA-bound catalogs. Fresh incremental bundle only, not complete Project or simulation validation. cw float batch is not native integer-setter equivalence.',CatalogBatch,service.apply,False,False)]
