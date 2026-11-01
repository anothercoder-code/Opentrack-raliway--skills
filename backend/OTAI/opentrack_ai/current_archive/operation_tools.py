"""Typed current-archive transformations; exact modules, never a JSON-only save."""
from typing import Annotated,Literal
from pydantic import Field,StrictStr,StrictInt,StrictBool,StrictFloat,model_validator
from .tools import Input,PathText,ArchiveTools,sha
from ..errors import APIError
from . import writer as w,catalogs as c,stock_operations as stock,path_functions as paths

Name=Annotated[StrictStr,Field(min_length=1,max_length=200)]
I32=Annotated[StrictInt,Field(ge=0,le=2147483647)]
SignedI32=Annotated[StrictInt,Field(ge=-2147483648,le=2147483647)]
F32=Annotated[StrictFloat|StrictInt,Field(ge=-3.4028234663852886e38,le=3.4028234663852886e38,allow_inf_nan=False)]
class Changes(Input):
    @model_validator(mode='after')
    def supplied(self):
        if not self.model_fields_set or any(getattr(self,k) is None for k in self.model_fields_set):raise ValueError('Provide nonempty changes without nulls')
        return self
class TrainChanges(Changes):
    maximum_acceleration_mps2:F32|None=None
    braking_delay_s:F32|None=None
    braking_release_speed_kmh:F32|None=None
class CategoryChanges(Changes):
    default_connection_time_s:F32|None=None
    departure_process_time_s:F32|None=None
    departure_process_starts_at_departure_time:StrictBool|None=None
class PatchTrain(Input):
    action:Literal['patch_train']
    name:Name
    changes:TrainChanges
class PatchCategory(Input):
    action:Literal['patch_category']
    name:Name
    changes:CategoryChanges
class CloneEngine(Input):
    action:Literal['clone_engine']
    template_name:Name
    new_name:Name
class Description(Input):
    action:Literal['set_description']
    kind:Literal['OTRoute','OTPath','OTDest']
    name:Name
    array_id:SignedI32|None=None
    start_id:SignedI32|None=None
    description:Annotated[StrictStr,Field(max_length=1048576)]
class RouteSelector(Input):
    name:Name
    array_id:I32
    start_id:I32
class CreatePath(Input):
    action:Literal['create_local_path']
    name:Name
    array_id:I32
    routes:Annotated[list[RouteSelector],Field(min_length=1,max_length=10000)]
    description:Annotated[StrictStr,Field(max_length=1048576)]=''
    document_local_name_scope:Literal['single_archive_only']
Action=Annotated[PatchTrain|PatchCategory|CloneEngine|Description|CreatePath,Field(discriminator='action')]
class Transform(Input):
    source_path:PathText
    expected_sha256:Annotated[StrictStr,Field(pattern=r'^[0-9a-f]{64}$')]
    operation:Action
    preview_only:StrictBool=True
    target_path:PathText|None=None
    @model_validator(mode='after')
    def destination(self):
        if not self.preview_only and self.target_path is None:raise ValueError('Saving requires a fresh target_path')
        return self
class RouteObjects(Input):
    source_path:PathText
    kind:Literal['OTRoute','OTPath','OTDest']
    offset:Annotated[StrictInt,Field(ge=0)]=0
    limit:Annotated[StrictInt,Field(ge=1,le=100)]=25

class Operations(ArchiveTools):
    def list_objects(self,args):
        source,original,root,version=self.read(args.source_path)
        try:
            rows=[]
            for obj in w.objects(root):
                if w.kind(obj)!=args.kind:continue
                row=paths.info(obj);description=row.pop('description')
                row.update(description_preview=description[:240],description_characters=len(description),description_truncated=len(description)>240)
                rows.append(row)
        except (ValueError,TypeError,IndexError) as e:raise APIError('CURRENT_PATH_SCHEMA',str(e)[:300]) from e
        return {'source_path':args.source_path,'source_sha256':sha(original),'items':rows[args.offset:args.offset+args.limit],
                'total_count':len(rows),'has_more':args.offset+args.limit<len(rows),'scope':'saved objects in one archive; no runtime expansion'}
    def transform(self,args):
        source,original,root,version=self.read(args.source_path)
        if sha(original)!=args.expected_sha256:raise APIError('SOURCE_CHANGED','Inspected source SHA differs')
        op=args.operation
        try:
            if op.action in ('patch_train','patch_category'):
                c.train_items(root) 
                classname='OTTrain' if op.action=='patch_train' else 'OTTrainCategory'
                output,report=stock.patch_archive(original,classname,op.name,op.changes.model_dump(exclude_unset=True))
            elif op.action=='clone_engine':output,report=stock.clone_engine_archive(original,op.template_name,op.new_name)
            elif op.action=='set_description':output,report=paths.set_description(original,op.kind,op.name,op.description,op.array_id,op.start_id)
            else:output,report=paths.create_local_path(original,op.name,op.array_id,[x.model_dump() for x in op.routes],op.description)
        except paths.ExpectedRspIDError as e:
            raise APIError('EXPECTED_FRESH_RSP_ID',str(e),{'expected_fresh_id':e.expected_fresh_id,'highestGivenRspID':e.highestGivenRspID,'source_sha256':sha(original),'saved':False,'mutation_performed':False}) from e
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_ARCHIVE_OPERATION',str(e)[:500]) from e
        if len(output)>20*1024*1024:raise APIError('ARCHIVE_SIZE','Generated archive exceeds 20 MiB safety limit')
        w.load_next_compatible(output)
        result={'preview_only':args.preview_only,'saved':False,'source_path':args.source_path,'source_sha256':sha(original),
                'output_sha256':sha(output),'output_bytes':len(output),'operation':op.action,'change_report':report,
                'fresh_archive_reload_verified':True,'native_application_started':False}
        if args.preview_only:return result
        return self.save_copy(source,original,output,result,args.target_path)

def tool_definitions(root):
    service=Operations(root)
    return [
        ('opentrack_list_current_route_objects','Inspect saved Route/Path/Itinerary identities and references in one real archive. Description previews are bounded and flagged; no runtime expansion or project-wide reference claim.',RouteObjects,service.list_objects),
        ('opentrack_transform_current_archive','Preview or atomically save a fresh real archive copy using exact current stock setters, explicit Engine-template clone, Route/Path/Itinerary description setter or single-document Path creation. Strict action schemas, source SHA, no overwrite, fresh file reload. No legacy migration or guessed defaults.',Transform,service.transform,False,False),
    ]
