from typing import Literal
"""Read-only project-bound simulation run review, with execution always blocked."""
from typing import Any
from pydantic import StrictBool,Field
from .multi_document_tools import MultiDocumentTools,ProjectInput
from .tools import sha
from ..errors import APIError

class PreviewRunPlan(ProjectInput):
    preview_only: Literal[True] = True
    profile_observations:dict[str,Any]=Field(default_factory=dict)
    evidence_observation:dict[str,Any]|None=None

class SimulationRunTools(MultiDocumentTools):
    def preview(self,args):
        if args.preview_only is not True:raise APIError('PREVIEW_ONLY','No launch, save or publication capability')
        from .simulation_run_workflow.core import summarize,profile_report
        from .prepare_contract import preflight
        try:profile_report(args.profile_observations)
        except (ValueError,TypeError)as e:raise APIError('RUN_PLAN_INVALID','Unsupported profile observation',str(e))from e
        if sha(preflight.PARSER_CONTRACT_PATH.read_bytes())!='ccaee62288edd48bcf2005017b682decc42942e109fbdcf1ce1e308262eac6d2':raise APIError('EVIDENCE_CHANGED','Native parser contract mismatch')
        state=self.load_project(args.source_project)
        def bound(path):
            if not path.startswith(state['root']+'/'):raise ValueError('Run dependency outside mapped root')
            member=self.member(path[len(state['root'])+1:])
            if member not in state['files']:raise ValueError('Missing mapped dependency')
            return state['files'][member]
        pf=preflight.check(state['run'],bound)
        if not args.source_project.run_file.endswith('.run'):
            pf['errors'].append({'rule':'SNAPSHOT_ONLY','message':'Selected source is not a .run project'})
            pf['passed_static_subset']=False
        try:
            project=self.project(state)
            pf['cross_document_static_validation']={'passed':True,'document_count':len(project.roots),'itinerary_count':len(project.dests)}
        except ValueError as e:
            pf['errors'].append({'rule':'MULTIDOC01','message':str(e)});pf['passed_static_subset']=False
        
        try:
            from .prepare_contract.auxiliary import records
            outputs=[v for k,v,_ in records(state['run']) if k=='OutputPath']
            if len(outputs)!=1 or not outputs[0].startswith(state['root']+'/'):raise ValueError('OutputPath must be one explicit descendant of execution-root mapping')
            output_member=self.member(outputs[0][len(state['root'])+1:])
            folded=output_member.casefold()
            if any(n.casefold()==folded or n.casefold().startswith(folded+'/') or folded.startswith(n.casefold()+'/') for n in state['files']):raise ValueError('Output declaration overlaps an input file or a populated inventory subtree')
            pf['output_mapping']={'declared_path':outputs[0],'relative_member':output_member,'input_overlap':False,'native_exists_checked':False,'created':False}
        except (ValueError,APIError,UnicodeError) as e:
            pf['errors'].append({'rule':'OUTPUT01','message':str(e)});pf['passed_static_subset']=False
        try:result=summarize(state['run'],args.source_project.files,pf,args.profile_observations,args.evidence_observation)
        except (ValueError,TypeError,KeyError,UnicodeError)as e:raise APIError('RUN_PLAN_INVALID','Unsupported run plan or evidence observation',str(e)[:500])from e
        result['tool']='opentrack_preview_simulation_run_plan';result['source']=self.source_receipt(args,state)
        self.recheck(state)
        return result

def tool_definitions(root):
    service=SimulationRunTools(root)
    return [('opentrack_preview_simulation_run_plan','Read-only exact-project run normalization, bounded preparation checks and caller-observation triage. Always blocked for native execution; no command, launch, save or runtime success certification.',PreviewRunPlan,service.preview)]
