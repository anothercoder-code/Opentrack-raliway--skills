"""Typed, preview-only raw Signal11 parameters; no operational enum claims."""
from typing import Annotated,Literal
from pydantic import Field,StrictBool,StrictInt,StrictStr,model_validator
from .tools import Input,ArchiveTools,sha
from .bundle_tools import Source
from ..errors import APIError
I32=Annotated[StrictInt,Field(ge=-(2**31),lt=2**31)]
class SignalSelector(Input):
 model_index:Annotated[StrictInt,Field(ge=0)]
 signal_id:I32
 end_id:I32
 signal_name:StrictStr
class InspectSignalParameters(Input):
 source:Source
 target:SignalSelector
class SignalParameterChanges(Input):
 raw_dispatch_code:I32|None=None
 balise_release_at_balise_position:StrictBool|None=None
 acceleration_forbidden:StrictBool|None=None
 keep_closed_for_station_stop:StrictBool|None=None
 balise_control_all_braking_actions:StrictBool|None=None
 @model_validator(mode='after')
 def explicit(self):
  if not self.model_fields_set or any(getattr(self,x)is None for x in self.model_fields_set):raise ValueError('Explicit non-null parameter changes required')
  return self
class UpdateSignalParameters(InspectSignalParameters):
 changes:SignalParameterChanges
 preview_only:Literal[True]=True
class SignalSavedParameterTools(ArchiveTools):
 def invoke(self,args,write=False):
  path=self.path(args.source.path);data=self.secure_bytes(path)
  if sha(data)!=args.source.sha256:raise APIError('SOURCE_CHANGED','Signal source differs from exact SHA')
  from .signal_saved_parameters import inspect,update
  try:
   if write:output,result=update(data,args.target.model_dump(),args.changes.model_dump(exclude_unset=True))
   else:output,result=data,inspect(data,args.target.model_dump())
  except(ValueError,TypeError,IndexError,KeyError,OverflowError)as e:raise APIError('SIGNAL_PARAMETER_INVALID','Outside the bounded saved Signal11 parameter domain',str(e)[:500])from e
  if self.secure_bytes(path)!=data:raise APIError('SOURCE_CHANGED','Signal source changed during operation')
  return {'source':args.source.model_dump(),'saved':False,'preview_only':True,'result':result,'output':{'sha256':sha(output),'bytes':len(output)},'native_execution':False,'whole_project_validated':False,'limitations':['Raw dispatch integer has no certified business enum or operational validity.','Stored bool configuration only; no train-protection or signalling-safety validation.','No type changes, array edits, external-reference resolution, native runtime or export.']}
 def inspect(self,args):return self.invoke(args)
 def update(self,args):return self.invoke(args,True)
def tool_definitions(root):
 s=SignalSavedParameterTools(root)
 return [('opentrack_inspect_signal_saved_parameters','Read exact local Signal11 raw int32 dispatch and four saved boolean bits; SHA/index/Signal-End ID/name binding. Not an enum or operational safety certification.',InspectSignalParameters,s.inspect),('opentrack_preview_signal_saved_parameters','Preview raw int32 dispatch and four independently masked boolean Signal11 fields, preserving other bits and graph identity. No type/array edits, saving, export or native execution.',UpdateSignalParameters,s.update)]
