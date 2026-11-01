from typing import Literal
"""Finite Train Incident scenario preview. No save path or native execution."""
from typing import Any
import re
from pydantic import StrictBool
from .tools import Input, sha
from .bundle_tools import Source
from .upcoming_tools import UpcomingFunctions
from ..errors import APIError

class PreviewDisturbance(Input):
    source: Source
    trains: Source
    project_run: Source
    spec: dict[str, Any]
    preview_only: Literal[True] = True

class DisturbanceTools(UpcomingFunctions):
    def preview(self,args):
        if args.preview_only is not True:
            raise APIError('PREVIEW_ONLY','This candidate supports preview only; no save or publication.')
        from .disturbance_workflow.core import plan
        try:
            incidents=args.spec.get('incidents')
            if type(incidents) is not list or not 1<=len(incidents)<=100:
                raise ValueError('A scenario needs 1..100 explicit Train incidents')
            sources={}; paths={}
            for key in ('source','trains','project_run'):
                binding=getattr(args,key);p=self.path(binding.path);b=self.secure_bytes(p)
                if sha(b)!=binding.sha256:raise APIError('SOURCE_CHANGED','SHA mismatch',key)
                sources[key]=b;paths[key]=p
            scopes=[]
            for incident in incidents:
                _,_,_,scope=self.incident_scope(args,incident['course_id']);scopes.append(scope)
            window=run_window(sources['project_run'])
            for incident in incidents:
                start=absolute(incident['begin_time'],incident['begin_day']);stop=absolute(incident['end_time'],incident['end_day'])
                if not window[0]<=start<=stop<=window[1]:raise ValueError('Explicit incident window outside selected run')
            output,receipt=plan(sources['source'],args.spec)
        except APIError:raise
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
            raise APIError('DISTURBANCE_INVALID','Outside supported Train-incident scenario data contract',str(exc)[:500]) from exc
        for key,p in paths.items():
            if self.secure_bytes(p)!=sources[key]:raise APIError('SOURCE_CHANGED','Source changed during preview',key)
        return dict(tool='opentrack_preview_disturbance_scenario',preview_only=True,saved=False,native_runtime_ready=False,
            sampling_validated=False,publication_review_pending=True,source_sha256={k:sha(v) for k,v in sources.items()},
            output={'sha256':sha(output),'bytes':len(output)},run_window_s=window,course_train_bindings=scopes,scenario=receipt,
            limitations=['Train type1 scenarios; initialized native IncidentSets and their shared member references are preserved. Other event types remain unsupported.',
                         'Declared windows checked against run; random draws and trigger timing not executed.',
                         'Named distributions are stored piecewise-linear tables, not sampling results.',
                         'Course and Train bindings only; not full project readiness or runtime verification.',
                         'No save, publication, native execution, or changes to runtime global preferences.'])

def absolute(clock,day):
    if type(day) is not int or not 0<=day<=7 or type(clock)is not str or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]',clock):
        raise ValueError('Canonical clock and bounded integer day required')
    h,m,s=map(int,clock.split(':'));return day*86400+h*3600+m*60+s

def run_window(blob):
    from .prepare_contract.auxiliary import records as run_records
    records={}
    for key,value,_ in run_records(blob):
        if key is not None:records.setdefault(key,[]).append(value)
    out=[]
    for prefix in ('Start','Stop'):
        clock=records.get(prefix+' Time',[]);day=records.get(prefix+' Day Offset',[])
        if len(clock)!=1 or len(day)!=1 or not re.fullmatch(r'[0-7]',day[0]):raise ValueError('Explicit bounded start/stop required')
        out.append(absolute(clock[0],int(day[0])))
    if not out[0]<out[1]:raise ValueError('Run window must increase')
    return out

def tool_definitions(root):
    service=DisturbanceTools(root)
    return [('opentrack_preview_disturbance_scenario','Read-only SHA-bound Train Incident12 scenario preview: batch events, bounded day windows, explicit probability and named piecewise-linear begin/duration table bindings. Preserves initialized native IncidentSets; no sampling, save or native execution.',PreviewDisturbance,service.preview)]
