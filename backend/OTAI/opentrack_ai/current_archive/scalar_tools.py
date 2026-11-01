"""Bounded stock field batches, saved curves and same-formation template cloning."""
from pathlib import Path
from typing import Annotated, Literal
from pydantic import Field, StrictStr, StrictInt, StrictFloat, model_validator
from .tools import Input, PathText, sha
from .bundle_tools import Source
from .next_tools import NextFunctions, Save, Ordinal
from .operation_tools import Name
from ..errors import APIError
from ..json_safe import checked_json

Kind=Literal['OTTrain','OTEngine','OTTrainCategory']
ScalarField=Literal['trainType','avgDeceleration','maxDrawbarForce_kN','decelerationUsedFormula','brakedWeightPercentage','decelerationFunctionParameterC1','decelerationFunctionParameterC2','brakingDelayType','startingRollingResistanceOffsetSpeed_kmh','startingRollingResistanceFactor_Nt','resistFactor','adhesion','dispatchingType','timingStationsType','initialDelayDistributionFunction','trackNameCreationType','delayAddType']
class InspectFields(Input):
    source_path:PathText
    kind:Kind
    name:Name
    fields:Annotated[list[ScalarField],Field(min_length=1,max_length=10)]
class EditFields(Save):
    source:Source
    kind:Kind
    name:Name
    changes:Annotated[dict[ScalarField,StrictInt|StrictFloat],Field(min_length=1,max_length=10)]
class EditCurve(Save):
    source:Source
    engine_name:Name
    diagram_index:Ordinal
    content:Annotated[StrictStr,Field(max_length=1048576)]|None=None
    points:Annotated[list[list[StrictInt]],Field(max_length=100000)]|None=None
    mode:Literal['replace','append']='replace'
    @model_validator(mode='after')
    def exactly_one(self):
        if (self.content is None)==(self.points is None):raise ValueError('Supply exactly one of content or points')
        return self
class CloneTrain(Save):
    source:Source
    project_run:Source
    depot:Source
    template_name:Name
    new_name:Name

class ScalarFunctions(NextFunctions):
    @staticmethod
    def fields_call(blob,args,write=False):
        from . import train_fields as t, engine_category_fields as e
        module=t if args.kind=='OTTrain' else e
        fn=module.patch_fields if write else module.read_fields
        params=[blob]+([] if args.kind=='OTTrain' else [args.kind])+[args.name,args.changes if write else args.fields]
        try:return fn(*params)
        except (ValueError,TypeError,IndexError,OverflowError) as exc:raise APIError('CURRENT_STOCK_FIELDS',str(exc)[:500]) from exc
    def inspect_fields(self,args):
        _,blob,_,_=self.read(args.source_path)
        return checked_json({'source_path':args.source_path,'source_sha256':sha(blob),'kind':args.kind,'name':args.name,'fields':self.fields_call(blob,args),'native_application_started':False})
    def edit_fields(self,args):
        path,blob,_,_=self.checked(args.source)
        output,report=self.fields_call(blob,args,True)
        return self.finish(args,path,blob,output,report)
    def curve(self,args):
        from .engine_curves import patch_archive
        path,blob,_,_=self.checked(args.source)
        try:output,report=patch_archive(blob,args.engine_name,args.diagram_index,content=args.content,points=args.points,mode=args.mode,preview=False)
        except (ValueError,TypeError,IndexError,OverflowError) as exc:raise APIError('CURRENT_ENGINE_CURVE',str(exc)[:500]) from exc
        return self.finish(args,path,blob,output,report)
    def train_scope(self,args,path,depot_path):
        runpath=self.path(args.project_run.path);runblob=self.secure_bytes(runpath)
        if sha(runblob)!=args.project_run.sha256:raise APIError('SOURCE_CHANGED','Run differs from inspected SHA')
        self.same_project([path,depot_path,runpath]);project=self.root.joinpath(*self.project_scope(runpath))
        if runpath.parent!=project or runpath.suffix!='.run':raise APIError('TRAIN_SCOPE','Run must be directly inside selected project')
        try:lines=runblob.decode('ascii').splitlines()
        except UnicodeDecodeError as exc:raise APIError('TRAIN_SCOPE','ASCII run key#value# subset required') from exc
        bindings={}
        for line in lines:
            if not line.strip() or line.startswith('//'):continue
            parts=line.split('#')
            if len(parts)!=3 or parts[2]!='':raise APIError('TRAIN_SCOPE','Malformed run record')
            if parts[0] not in ('TrainFile','DepotFile'):continue
            key,raw=parts[:2]
            if key in bindings or not raw or '%' in raw or '\\' in raw or '..' in Path(raw).parts:raise APIError('TRAIN_SCOPE','Unique explicit catalog binding required')
            candidate=Path(raw) if Path(raw).is_absolute() else project/raw
            try:relative=candidate.relative_to(self.root).as_posix()
            except ValueError as exc:raise APIError('TRAIN_SCOPE','Catalog outside authorized root') from exc
            bindings[key]=self.path(relative)
        if bindings!={'TrainFile':path,'DepotFile':depot_path} or path==depot_path:raise APIError('TRAIN_SCOPE','Train and depot must match run bindings exactly')
        return runpath,runblob
    def clone_train(self,args):
        from .train_factory import clone_train_archive
        path,blob,_,_=self.checked(args.source);dp,db,_,_=self.checked(args.depot)
        rp,rb=self.train_scope(args,path,dp)
        try:output,report=clone_train_archive(blob,db,template_name=args.template_name,new_name=args.new_name)
        except (ValueError,TypeError,IndexError,OverflowError) as exc:raise APIError('CURRENT_TRAIN_FACTORY',str(exc)[:500]) from exc
        report['run_catalog_bindings_matched']=True
        report['same_project_verified']=True
        report['validation_scope']='current_train_same_formation_and_catalog_references'
        report['unvalidated_domains']=['infrastructure_topology','routing','simulation']
        return self.finish(args,path,blob,output,report,{rp:rb,dp:db})

def tool_definitions(root):
    service=ScalarFunctions(root)
    return [
      ('opentrack_inspect_current_stock_fields','Read explicit raw Train16/Engine2/Category19 allowlisted scalar getters. Nonfinite existing values use strict JSON native-bit tags; no business enum or unit inference.',InspectFields,service.inspect_fields),
      ('opentrack_edit_current_stock_fields','Atomic same-object partial field batch: Train10, Engine2 or Category5 allowlist. Exact int32 raw codes or finite binary32; no defaults, enum labels, physical validation or simulation. Preview/fresh copy only.',EditFields,service.edit_fields,False,False),
      ('opentrack_edit_current_engine_curve','Edit existing Engine2 diagram saved Z/V points; split/dedup/sort and recompute groups6/7/17 across diagrams, preserve powerMax. Explicit text or saved-int32 triples. No UI autoscale/simulation. Preview/fresh copy.',EditCurve,service.curve,False,False),
      ('opentrack_clone_current_train','Clone explicit Train16 template with identical formation, independent owned children and fresh name. Verify run TrainFile/DepotFile plus Category/Engine references. Not native copy/init equivalence. Preview/fresh copy.',CloneTrain,service.clone_train,False,False),
    ]
