"""Unified typed project initialization preview; no bytes are published."""
from typing import Annotated,Literal
from pydantic import Field,model_validator
from .tools import Input,ArchiveTools,PathText,sha
from .bundle_tools import Source
from .network_generation_tools import Network,MainSignal,Route,Text
from .infrastructure_chain_tools import PathPlan,ItineraryPlan
from .finite_topology_tools import PointStation
from .terminal_generation_schema import AreaStation
from .operating_generation_tools import Vehicles,CoursePlan
from .operating_chain_tools import WindowsRunConfiguration
from .final_stop_tools import StopPlan
from ..errors import APIError
class InitializationSources(Input):
 header:Source
 shapes:Source
 depot_template:Source
 trains_template:Source
 courses_template:Source
 timetable_template:Source
class PassInfrastructure(Input):
 document_name:Annotated[str,Field(strict=True,pattern=r'^[A-Za-z][A-Za-z0-9_]{0,39}$')]
 document_path:PathText
 network:Network
 stations:Annotated[list[PointStation],Field(max_length=100)]
 signals:Annotated[list[MainSignal],Field(min_length=1,max_length=100)]
 routes:Annotated[list[Route],Field(min_length=1,max_length=100)]
 paths:Annotated[list[PathPlan],Field(min_length=1,max_length=100)]
 itineraries:Annotated[list[ItineraryPlan],Field(min_length=1,max_length=100)]
class FinalStopInfrastructure(PassInfrastructure):
 stations:Annotated[list[AreaStation],Field(min_length=2,max_length=100)]
class PassProject(Input):
 infrastructure:PassInfrastructure
 vehicles:Vehicles
 course_template_id:Text
 timetable_template_key:Text
 train_types:Annotated[list[Text],Field(min_length=1,max_length=100)]
 speed_type:Text
 plan:Annotated[list[CoursePlan],Field(min_length=1,max_length=1000)]
 run_configuration:WindowsRunConfiguration
class FinalStopProject(PassProject):
 infrastructure:FinalStopInfrastructure
 plan:Annotated[list[StopPlan],Field(min_length=1,max_length=100)]
class InitializeProject(Input):
 sources:InitializationSources
 profile:Literal['single_document_pass','single_document_final_stop']
 project:PassProject|FinalStopProject
 preview_only:Literal[True]=True
 @model_validator(mode='after')
 def match_profile(self):
  if self.profile=='single_document_pass' and type(self.project)is not PassProject:raise ValueError('Pass profile requires point stations and pass visits')
  if self.profile=='single_document_final_stop' and type(self.project)is not FinalStopProject:raise ValueError('Final-stop profile requires explicit area stations and stop visits')
  return self
def validate_initialization_receipt(members,receipt,sources,*,profile,project):
 """Compare receipt claims against the actual immutable candidates, never publish."""
 def check(ok,message):
  if not ok:raise APIError('INITIALIZATION_RECEIPT',message)
 check(type(members)is dict and len(members)==8 and all(type(k)is str and type(v)is bytes for k,v in members.items()),'Exactly eight immutable named candidates required')
 check(type(receipt)is dict,'Receipt must be an object')
 cfg=project['run_configuration'];roles={cfg['run_filename']:'run','OTDocuments/'+project['infrastructure']['document_name']+'.opentrack':'document'}
 roles.update({'OTData/infrastructure.'+k:k for k in ('depot','trains','courses','dest','stations','timetable')})
 check(len(roles)==8 and set(members)==set(roles),'Candidate names must match the exact single-document eight-role contract')
 manifest={n:{'sha256':sha(b),'bytes':len(b)}for n,b in members.items()}
 def manifest_matches(value):
  return type(value)is dict and value==manifest and all(type(row)is dict and type(row.get('bytes'))is int for row in value.values())
 check(receipt.get('schema')=='project-initialization/1' and receipt.get('profile')==profile,'Receipt schema/profile mismatch')
 check(manifest_matches(receipt.get('members')),'Receipt member manifest differs from actual candidate bytes')
 check(receipt.get('member_roles')==roles,'Receipt member-role mapping differs from candidates')
 for key in ('saved','native_application_executed','native_runtime_ready'):
  check(receipt.get(key)is False,'Receipt must explicitly declare '+key+'=false')
 counts=receipt.get('counts');check(type(counts)is dict and all(type(counts.get(k))is int and counts[k]==v for k,v in {'members':8,'documents':1,'catalogs':6}.items()),'Receipt candidate role counts mismatch')
 source_hashes={k:sha(v)for k,v in sources.items()}
 check(receipt.get('source_sha256')==source_hashes,'Receipt source hashes mismatch')
 resources=receipt.get('resource_manifest');check(type(resources)is dict and set(resources)==set(sources),'Receipt resource roles mismatch')
 for key,blob in sources.items():
  row=resources[key];check(type(row)is dict and row.get('sha256')==sha(blob)and type(row.get('bytes'))is int and row['bytes']==len(blob),'Resource manifest differs from supplied donor bytes: '+key)
 chain=receipt.get('chain_receipt');check(type(chain)is dict,'Missing chain receipt')
 check(chain.get('output_sha256')=={n:row['sha256']for n,row in manifest.items()},'Chain output hashes differ from candidates')
 for key in ('saved','native_application_executed','native_runtime_ready'):
  check(chain.get(key)is False,'Chain receipt must explicitly declare '+key+'=false')
 check(receipt.get('dependency_bindings')==chain.get('cross_file_bindings') and type(receipt.get('dependency_bindings'))is dict,'Dependency receipt disagreement')
 nxt=receipt.get('next_write_contract');check(type(nxt)is dict and nxt.get('state')=='not_enabled_pending_independent_publication_review','Next-write state must remain disabled')
 check(manifest_matches(nxt.get('required_members')),'Next-write candidate manifest mismatch')
 check(nxt.get('run_member')==cfg['run_filename'] and nxt.get('execution_root')==cfg['execution_root'] and nxt.get('path_style')==cfg['path_style'],'Next-write mapping differs from project request')
 return manifest
class ProjectInitializationTools(ArchiveTools):
 def preview(self,args):
  from .project_initialization_workflow import initialize_project
  inputs={};sources={};total=0
  for key in type(args.sources).model_fields:
   spec=getattr(args.sources,key);path=self.path(spec.path);blob=self.secure_bytes(path);total+=len(blob)
   if sha(blob)!=spec.sha256:raise APIError('SOURCE_CHANGED','Exact initialization donor SHA mismatch',key)
   if total>256*1024*1024:raise APIError('INITIALIZATION_SIZE','Six donors exceed256MiB total')
   if path in inputs and inputs[path]!=blob:raise APIError('SOURCE_CHANGED','Repeated resolved donor path changed between resource-role reads',key)
   inputs[path]=blob;sources[key]=blob
  project=args.project.model_dump();project['infrastructure']['network']=args.project.infrastructure.network.core_spec()
  try:members,receipt=initialize_project(sources,expected_hashes={k:getattr(args.sources,k).sha256 for k in sources},profile=args.profile,project=project)
  except(ValueError,TypeError,KeyError,IndexError,OverflowError)as e:raise APIError('PROJECT_INITIALIZATION_INVALID','Outside bounded project initialization profile',str(e)[:700])from e
  for path,data in inputs.items():
   if self.secure_bytes(path)!=data:raise APIError('SOURCE_CHANGED','Donor changed during initialization preview')
  manifest=validate_initialization_receipt(members,receipt,sources,profile=args.profile,project=project)
  return {'tool':'opentrack_preview_initialize_project','profile':args.profile,'preview_only':True,'saved':False,'native_application_executed':False,'native_runtime_ready':False,'publication_review_pending':True,'source_bindings':args.sources.model_dump(),'receipt':receipt,'outputs':manifest,'limitations':['Only candidate archive bytes in memory; no files or directories are delivered or created.','Explicit single-document bounded topology and inherited format/vehicle templates, not arbitrary railway engineering.','Pass or final-only forward stop profile; no intermediate dwell, turnround or physical fleet circulation.','Static validation and saved-data readback only; no native OpenTrack execution or simulation success claim.']}
def tool_definitions(root):
 s=ProjectInitializationTools(root)
 return [('opentrack_preview_initialize_project','Unified six-donor project initialization: empty-topology start, explicit infrastructure/signals/Routes/Paths/Itineraries, vehicles/services/timetable and run bindings. Select pass or final-only stop profile. In-memory candidate preview only; no file delivery, export, native execution or legacy whole-project pipeline.',InitializeProject,s.preview)]
