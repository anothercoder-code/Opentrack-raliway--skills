
"""Legacy full-day example planning and checkpointed paired CLI calls; not a simulator."""
import argparse
import importlib.util
import os
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ALLOWED = {'opentrack_capabilities', 'opentrack_create_project',
 'opentrack_start_editor', 'opentrack_get_editor', 'opentrack_get_draft', 'opentrack_edit_editor',
 'opentrack_inspect_topology', 'opentrack_search_network',
 'opentrack_generate_operations', 'opentrack_get_service',
 'opentrack_list_catalog', 'opentrack_list_routes', 'opentrack_list_paths',
 'opentrack_trace_path', 'opentrack_validate_project',
 'opentrack_publish_draft', 'opentrack_read_run_logs'}

EVIDENCE_TOOLS={'opentrack_simulation_capabilities','opentrack_simulation_control','opentrack_inspect_simulation_evidence'}
ALLOWED |= EVIDENCE_TOOLS

MUTATING = {'opentrack_create_project','opentrack_start_editor','opentrack_edit_editor',
 'opentrack_generate_operations','opentrack_publish_draft'}

def scenario():
    families=[]; courses=[]
    for index, (line, direction) in enumerate((l,d) for l in ['H1','H2','H3','V1','V2','V3'] for d in ['F','R']):
        family=f'{line}_{direction}'
        stops=[f'{line}_T0']+[f'{line}_S{i}' for i in range(1,4)]+[f'{line}_T4']
        if direction=='R': stops.reverse()
        families.append({'id':family,'line':line,'direction':direction,'stops':stops,'offset_s':index*20})
        for hour in range(24):
            departure=hour*3600+index*20
            rows=[{'station':station,'arrival_s':departure+i*540,
                   'departure_s':departure+i*540+(60 if 0<i<4 else 0)} for i,station in enumerate(stops)]
            courses.append({'course_id':f'{family}_{hour:02}','family':family,'stops':rows})
    return {'scenario_id':'grid3x3-full-day-v1','assumptions':'Synthetic proposed default, not user-supplied railway data',
      'evidence_level':'plan_only','goal_complete':False,'native_simulation_verified':False,
      'window':{'start_absolute_s':0,'stop_absolute_s':86400,'step_s':1},
      'line_count':6,'tracks_per_line':2,'line_length_m':40000,
      'crossing_resources':[f'J{i}{j}' for i in range(1,4) for j in range(1,4)],
      'crossing_semantics':'At-grade exclusive conflicts; no turns; not grade-separated',
      'families':families,'courses':courses}

def validate_plan(plan):
    if not isinstance(plan,dict):
        return {'plan_valid':False,'errors':['Plan must be an object'],'goal_complete':False,'native_simulation_verified':False}
    errors=[]
    expected=scenario()
    
    for key in ['scenario_id','line_count','tracks_per_line','line_length_m','crossing_resources','crossing_semantics','families','courses']:
        if plan.get(key)!=expected[key]: errors.append('Default scenario mismatch: '+key)
    if plan.get('evidence_level')!='plan_only' or plan.get('goal_complete') is not False or plan.get('native_simulation_verified') is not False:
        errors.append('Plan must never claim native completion')
    if plan.get('window')!={'start_absolute_s':0,'stop_absolute_s':86400,'step_s':1}: errors.append('Expected exact 24-hour window')
    if errors:
        return {'plan_valid':False,'errors':errors,'goal_complete':False,'native_simulation_verified':False,'scope':'Default scenario semantics only'}
    courses=plan.get('courses',[]); ids=[c['course_id'] for c in courses]
    if len(ids)!=288 or len(set(ids))!=288: errors.append('Expected 288 unique courses')
    if len(set(plan.get('crossing_resources',[])))!=9: errors.append('Expected nine crossing resources')
    family_map={f['id']:f for f in plan.get('families',[])}
    if len(family_map)!=12: errors.append('Expected twelve service families')
    for family,f in family_map.items():
        group=[c for c in courses if c['family']==family]
        departures=sorted(c['stops'][0]['departure_s'] for c in group)
        if departures!=[h*3600+f['offset_s'] for h in range(24)]: errors.append('Incorrect hourly family '+family)
    for c in courses:
        stops=c['stops']; f=family_map.get(c['family'],{})
        if len(stops)!=5 or [s['station'] for s in stops]!=f.get('stops'): errors.append('Incorrect station chain '+c['course_id'])
        previous=-1
        for s in stops:
            if not 0<=s['arrival_s']<=s['departure_s']<86400 or s['arrival_s']<previous: errors.append('Invalid chronology '+c['course_id'])
            previous=s['departure_s']
    return {'plan_valid':not errors,'errors':errors,'course_count':len(courses),
      'stop_row_count':sum(len(c['stops']) for c in courses),'goal_complete':False,
      'native_simulation_verified':False,'scope':'Timetable and scenario semantics only; no physical feasibility or native archives verified'}

def invoke(root, tool, args_file, checkpoint):
    from yard import require_software_authorization
    require_software_authorization(root)
    if tool not in ALLOWED: raise ValueError('Tool outside this legacy checkpoint helper workflow')
    root=Path(root).resolve()
    bridge=Path(__file__).resolve().with_name('ot.py')
    if not bridge.is_file(): raise ValueError('Matching installed Skill scripts/ot.py is required; no data-root backend fallback')
    spec=importlib.util.spec_from_file_location('_full_day_paired_bridge',bridge)
    if spec is None or spec.loader is None: raise ValueError('Cannot load matching Skill backend metadata')
    paired=importlib.util.module_from_spec(spec);spec.loader.exec_module(paired)
    environment=dict(os.environ)
    _,server=paired.locate_backend(bridge,environment)
    server=Path(server).resolve()
    bridge_sha=hashlib.sha256(bridge.read_bytes()).hexdigest()
    server_sha=hashlib.sha256(server.read_bytes()).hexdigest()
    raw=args_file.read_bytes(); args=json.loads(raw)
    canonical=json.dumps(args,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    identity={'data_root':str(root),'bridge':str(bridge),'bridge_sha256':bridge_sha,
              'backend_entry':str(server),'backend_entry_sha256':server_sha,'tool':tool}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()+b'\0'+canonical).hexdigest()
    
    if tool not in MUTATING: key += '-'+uuid.uuid4().hex
    checkpoint.mkdir(parents=True,exist_ok=True)
    record=checkpoint/(key+'.json')
    if record.exists():
        prior=json.loads(record.read_text())
        if prior.get('state')=='succeeded' and prior.get('tool')==tool and prior.get('invocation_key')==key and isinstance(prior.get('result'),dict) and prior['result'].get('ok') is True:
            return {'state':'already_succeeded','record':str(record),'result':prior.get('result'),'goal_complete':False,'native_simulation_verified':False,'evidence_level':'cached_tool_response_only'}
        
        raise ValueError('Previous attempt exists: inspect its actual server state before a manual retry with a new checkpoint directory')
    
    with record.open('x') as claim:
        json.dump({'state':'started','invocation_key':key,'tool':tool,'data_root':str(root),'bridge_path':str(bridge),'bridge_sha256':bridge_sha,'backend_entry':str(server),'args_sha256':hashlib.sha256(canonical).hexdigest(),'server_sha256':server_sha,'goal_complete':False},claim,indent=2)
    snapshot=checkpoint/(key+'.args.json')
    with snapshot.open('xb') as out: out.write(canonical)
    payload=['--args-file',str(snapshot.resolve())]
    environment['PYTHONUTF8']='1';environment['PYTHONIOENCODING']='utf-8'
    if hashlib.sha256(bridge.read_bytes()).hexdigest()!=bridge_sha or hashlib.sha256(server.read_bytes()).hexdigest()!=server_sha:
        raise ValueError('Paired bridge/backend entry changed before dispatch; inspect checkpoint before retry')
    result=subprocess.run([sys.executable,'-X','utf8','-B',str(bridge),'--root='+str(root),'--profile=all','call',tool,*payload],capture_output=True,text=True,encoding='utf-8',env=environment)
    try: envelope=json.loads(result.stdout)
    except ValueError: envelope=None
    state='succeeded' if result.returncode==0 and isinstance(envelope,dict) and envelope.get('ok') is True else 'failed_or_uncertain'
    data={'state':state,'invocation_key':key,'data_root':str(root),'bridge_path':str(bridge),'bridge_sha256':bridge_sha,'backend_entry':str(server),'server_sha256':server_sha,'args_sha256':hashlib.sha256(canonical).hexdigest(),'tool':tool,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'result':envelope,'goal_complete':False,'native_simulation_verified':False}
    with tempfile.NamedTemporaryFile(mode='w',dir=checkpoint,prefix=key+'.',suffix='.tmp',delete=False) as out:
        json.dump(data,out,ensure_ascii=False,indent=2);temporary=Path(out.name)
    temporary.replace(record)
    return {'record':str(record),**data}

def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('plan');a.add_argument('output',type=Path);a.add_argument('--root',type=Path,required=True)
    a=sub.add_parser('validate-plan');a.add_argument('input',type=Path);a.add_argument('--root',type=Path,required=True)
    a=sub.add_parser('call');a.add_argument('--root',type=Path,required=True);a.add_argument('--tool',required=True);a.add_argument('--args-file',type=Path,required=True);a.add_argument('--checkpoint',type=Path,required=True)
    a=p.parse_args()
    from yard import require_software_authorization
    require_software_authorization(a.root)
    if a.command=='plan':
        result=scenario();a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2));result=validate_plan(result)
    elif a.command=='validate-plan': result=validate_plan(json.loads(a.input.read_text()))
    else: result=invoke(a.root.resolve(),a.tool,a.args_file,a.checkpoint)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if result.get('plan_valid') is False or result.get('state')=='failed_or_uncertain' else 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'error':str(exc),'code':getattr(exc,'code',None),'goal_complete':False,'native_simulation_verified':False}));sys.exit(2)
