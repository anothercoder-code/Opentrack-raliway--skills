
"""Cloud-only 3x3 geometry/payload compiler, never a simulator or native executor.

Symbolic plans are NOT callable payloads. bind() requires actual create-geometry
manifest receipts, an actual project/run binding and a verified Course speed type.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

DOCUMENT = 'Grid3x3'
POSITIONS = (0,9600,9900,10100,10400,19600,19900,20100,20400,29600,29900,30100,30400,40000)
CROSSING_EDGES = (2,6,10)


def models():
    here = Path(__file__).resolve()
    candidates = [here.parents[1] / 'backend/OTAI/opentrack_ai/models.py', here.parents[3] / 'opentrack_ai/models.py', here.parents[2] / 'OTAI/opentrack_ai/models.py']
    path = next((p for p in candidates if p.is_file()), None)
    if path is None: raise ValueError('Actual OTAI/opentrack_ai/models.py required; no substitute schema accepted')
    spec = importlib.util.spec_from_file_location('grid_actual_models', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def default_scenario():
    from full_day import scenario
    return scenario()


def end(key, side):
    return {'document': DOCUMENT, 'vertex_key': key, 'side': side}


def build_plan(scenario=None):
    scenario = scenario or default_scenario()
    from full_day import validate_plan
    if not validate_plan(scenario)['plan_valid']:
        raise ValueError('Unsupported or invalid full_day scenario')
    batches=[]; tracks=[]; crossings={f'J{i}{j}':[] for i in range(1,4) for j in range(1,4)}
    for f in scenario['families']:
        name=f['id']; horizontal=f['line'][0]=='H'; number=int(f['line'][1]); side=0 if f['direction']=='F' else 1
        vertices=[f'{name}_N{i}' for i in range(len(POSITIONS))]
        changes=[]
        for key,position in zip(vertices,POSITIONS):
            along=100+position/40; across=100+number*250+(-4 if side==0 else 4)
            changes.append({'kind':'create_vertex','document':DOCUMENT,'vertex_key':key,'x':along if horizontal else across,'y':across if horizontal else along,'angle_degrees':0 if horizontal else 90,'names':[key+'_A',key+'_B']})
        edges=[]
        for i,(a,b) in enumerate(zip(vertices,vertices[1:])):
            edge={'key':f'{name}_E{i}','first':end(a,1),'second':end(b,0),'length_m':POSITIONS[i+1]-POSITIONS[i]}
            edges.append(edge)
            changes.append({'kind':'create_edge',**{k:edge[k] for k in ('first','second','length_m')},'track_name':name,'line_name':f['line'],'speeds':[{'train_type':str(t),'forward_kmh':80 if side==0 else 0,'reverse_kmh':80 if side==1 else 0} for t in range(4)]})
        for key in vertices:
            changes.append({'kind':'create_signal','end':end(key,side),'name':'SIG_'+key,'signal_type':1,'main_signal_type':3})
        
        stations={f['line']+'_T0':end(vertices[0],side),f['line']+'_T4':end(vertices[-1],side)}
        for cross,edge_index in enumerate(CROSSING_EDGES,1):
            stations[f['line']+f'_S{cross}']=end(vertices[edge_index if side==0 else edge_index+1],side)
            resource=f'J{number}{cross}' if horizontal else f'J{cross}{number}'
            crossings[resource].append(edges[edge_index]['key'])
        tracks.append({'family':name,'direction':f['direction'],'vertices':vertices,'edges':edges,'stations':stations,'signal_side':side,'travel_vertices':vertices if side==0 else vertices[::-1]})
        batches.append({'label':'Geometry '+name,'changes':changes})
    plan={'scenario_id':scenario['scenario_id'],'evidence_level':'plan_only','goal_complete':False,'native_simulation_verified':False,'document':DOCUMENT,
          'create_project':{'project_name':'Grid3x3Day','documents':[DOCUMENT],'width':1300,'height':1300},
          'geometry_batches':batches,'tracks':tracks,'crossings':crossings,'scenario':scenario,
          'assumptions':['Synthetic 6 double-track lines; each physical track operated in one direction only; no inter-line turns, turnouts or rolling-stock circulation.',
          'At-grade crossings are shared native OTElement resources, not geometric adjacency and not edge exclusion-link cliques.',
          '300m approach holding sections before 200m crossing sections; intermediate stops at approach boundaries (+/-100m from nominal 10km station chainages).',
          'Synthetic 200m/400t formation with uncalibrated constant-power proxy; no calibrated vehicle or safety/interlocking parity claim.',
          'Origin body placement, halt-point codes, signal aspects, departure windows and terminal clearance require native preparation/runtime verification.'],
          'blocking_requirements':['Actual native create/edit/get_draft receipts before binding IDs','Verified Course speed_type from target preferences; never guess from Edge numeric train_type','Typedstream/native schema helper dependencies needed to import real server','Authorized server-side native OpenTrack runtime and run evidence before simulation acceptance']}
    validate_structure(plan)
    return plan


def validate_structure(plan):
    """Static structural invariants, not a substitute for native graph tracing."""
    from full_day import validate_plan
    if not validate_plan(plan['scenario'])['plan_valid']: raise ValueError('Invalid timetable')
    if plan['goal_complete'] or plan['native_simulation_verified']: raise ValueError('A plan cannot certify native completion')
    families={f['id']:f for f in plan['scenario']['families']}
    if len(plan['tracks'])!=12 or set(t['family'] for t in plan['tracks'])!=set(families): raise ValueError('Twelve distinct directional tracks required')
    if len(plan['geometry_batches'])!=12: raise ValueError('All twelve geometry batches required')
    all_edges={}; all_vertices=set()
    for t in plan['tracks']:
        vertices=t['vertices']; edges=t['edges']; side=t['signal_side']
        if len(vertices)!=14 or len(set(vertices))!=14 or all_vertices.intersection(vertices): raise ValueError('Distinct paired vertices required')
        all_vertices.update(vertices)
        if len(edges)!=13 or sum(e['length_m'] for e in edges)!=40000: raise ValueError('Track must be connected 40km chain')
        if side!=(0 if t['direction']=='F' else 1): raise ValueError('Signal/travel direction mismatch')
        if t['travel_vertices']!=(vertices if side==0 else vertices[::-1]): raise ValueError('Invalid directed chain')
        for i,e in enumerate(edges):
            if e['first']!=end(vertices[i],1) or e['second']!=end(vertices[i+1],0) or e['length_m']!=POSITIONS[i+1]-POSITIONS[i]: raise ValueError('Broken DVG half-vertex alternation')
            if e['key'] in all_edges: raise ValueError('Duplicate edge')
            all_edges[e['key']]=(t,e,i)
        line=families[t['family']]['line']
        if t['stations'].get(line+'_T0')!=end(vertices[0],side) or t['stations'].get(line+'_T4')!=end(vertices[-1],side): raise ValueError('Terminal station binding mismatch')
        if set(t['stations'])!={line+'_T0',line+'_T4',*(line+f'_S{j}' for j in range(1,4))}: raise ValueError('Five exact stations required')
        for cross,i in enumerate(CROSSING_EDGES,1):
            expected=end(vertices[i if side==0 else i+1],side)
            if t['stations'][families[t['family']]['line']+f'_S{cross}']!=expected: raise ValueError('Platform must precede crossing')
            if edges[i-1 if side==0 else i+1]['length_m']<300: raise ValueError('Insufficient holding length')
    if set(plan['crossings'])!={f'J{i}{j}' for i in range(1,4) for j in range(1,4)}: raise ValueError('Nine crossing resources required')
    for resource,keys in plan['crossings'].items():
        i,j=resource[1:]; expected={f'H{i}_F',f'H{i}_R',f'V{j}_F',f'V{j}_R'}
        if len(keys)!=4 or len(set(keys))!=4 or {all_edges[k][0]['family'] for k in keys}!=expected: raise ValueError('Crossing must share all four directions')
        for k in keys:
            t,e,index=all_edges[k]
            expected_index=CROSSING_EDGES[int(j if t['family'][0]=='H' else i)-1]
            if index!=expected_index or e['length_m']!=200: raise ValueError('Wrong crossing section')
    
    from pydantic import TypeAdapter
    m=models(); adapter=TypeAdapter(m.Change)
    m.CreateProject.model_validate(plan['create_project'])
    for batch,t in zip(plan['geometry_batches'],plan['tracks']):
        if not 0<len(batch['changes'])<=200: raise ValueError('Editor batch size invalid')
        for change in batch['changes']: adapter.validate_python(change)
        expected_vertices=t['vertices']
        if [x['vertex_key'] for x in batch['changes'] if x['kind']=='create_vertex']!=expected_vertices: raise ValueError('Geometry plan vertex mismatch')
        actual_edges=[x for x in batch['changes'] if x['kind']=='create_edge']
        for e,actual in zip(t['edges'],actual_edges):
            if any(actual[k]!=e[k] for k in ('first','second','length_m')): raise ValueError('Geometry payload differs from topology')
            for speed in actual['speeds']:
                if (speed['forward_kmh'],speed['reverse_kmh'])!=((80,0) if t['signal_side']==0 else (0,80)): raise ValueError('Directional speed mismatch')
        if len(actual_edges)!=13: raise ValueError('Missing geometry edges')
        signals=[x for x in batch['changes'] if x['kind']=='create_signal']
        if any(x['signal_type']!=1 or x['main_signal_type']!=3 for x in signals): raise ValueError('Signal system differs from audited plan defaults')
        if [x['end'] for x in signals]!=[end(v,t['signal_side']) for v in expected_vertices]: raise ValueError('Wrong main signal direction')
    return {'valid':True,'scope':'real schema and static DVG plan invariants only','tracks':12,'paired_vertices':168,'edges':156,'crossings':9,'goal_complete':False,'native_simulation_verified':False}


def bind(plan, manifests, project, run_file, speed_type):
    """Compile actual API payloads using receipts, never predict graphic IDs."""
    validate_structure(plan)
    if not project or not run_file or not speed_type: raise ValueError('Real target project, run_file and verified speed_type required')
    vertices={}; received_edges={}; signals={}; graphic_ids=set()
    def register(ids):
        for ident in ids:
            if type(ident)!=int or ident<0 or ident in graphic_ids: raise ValueError('Invalid or duplicate actual graphic ID')
            graphic_ids.add(ident)
    for manifest in manifests:
        if 'changes' not in manifest: raise ValueError('Supply get_draft manifest, not editor session response')
        for change in manifest['changes']:
            if change.get('document')!=DOCUMENT: continue
            kind=change['kind']
            if kind=='create_vertex':
                key=change['vertex_key']
                if key in vertices: raise ValueError('Duplicate vertex receipt')
                if len(change['end_ids'])!=2: raise ValueError('Two actual End IDs required')
                register(change['end_ids'])
                vertices[key]=change['end_ids']
            elif kind=='create_edge':
                key=tuple(change['end_ids'])
                if key in received_edges: raise ValueError('Duplicate edge receipt')
                register([change['edge_id']])
                received_edges[key]=change
            elif kind=='create_signal':
                if type(change['end_id'])!=int or change['end_id']<0 or change['end_id'] in signals: raise ValueError('Duplicate or invalid signal End receipt')
                register([change['signal_id']])
                signals[change['end_id']]=change['signal_id']
    def resolve(ref):
        ids=vertices[ref['vertex_key']]
        if len(ids)!=2 or ids[0]==ids[1] or any(type(i)!=int or i<0 for i in ids): raise ValueError('Invalid actual End IDs')
        return {'document':DOCUMENT,'end_id':ids[ref['side']]}
    all_ids=[i for ids in vertices.values() for i in ids]
    if len(set(all_ids))!=len(all_ids): raise ValueError('Actual End IDs collide')
    edge_ids={}; routes=[]; paths=[]; stations={}; itineraries=[]
    for t in plan['tracks']:
        for edge in t['edges']:
            key=(resolve(edge['first'])['end_id'],resolve(edge['second'])['end_id'])
            actual=received_edges.get(key)
            if not actual or actual['length_m']!=edge['length_m']: raise ValueError('Missing/mismatched actual Edge receipt: '+edge['key'])
            edge_ids[edge['key']]=actual['edge_id']
        refs=[]
        for n,(a,b) in enumerate(zip(t['travel_vertices'],t['travel_vertices'][1:])):
            nodes=[resolve(end(v,t['signal_side'])) for v in (a,b)]
            if any(node['end_id'] not in signals for node in nodes): raise ValueError('Missing directional main Signal receipt')
            name='R_'+t['family']+'_'+str(n)
            routes.append({'name':name,'nodes':nodes,'signal_aspects':[0],'allow_occupied_entry':False})
            refs.append({'document':DOCUMENT,'start_id':nodes[0]['end_id'],'name':name})
        paths.append({'name':'P_'+t['family'],'routes':refs})
        itineraries.append({'name':'I_'+t['family'],'paths':['P_'+t['family']]})
        for sign,ref in t['stations'].items():
            stations.setdefault(sign,{'sign':sign,'name':sign,'document':DOCUMENT,'end_ids':[]})['end_ids'].append(resolve(ref)['end_id'])
    safety=[{'kind':'merge_elements','document':DOCUMENT,'edge_ids':[edge_ids[k] for k in keys]} for keys in plan['crossings'].values()]
    base={'project':project,'run_file':run_file}
    stock={'engines':[{'name':'GridProxy200','mass_t':400,'length_m':200,'maximum_speed_kmh':80,'maximum_force_kn':200,'nominal_power_kw':4000}],
           'formations':[{'name':'GridTrain','engines':[{'engine_name':'GridProxy200','count':1}],'braking_deceleration_mps2':0.6}], 'stations':list(stations.values())}
    batches=[{**base,'label':'Grid stations and uncalibrated stock',**stock}]
    for index in range(0,len(routes),100): batches.append({**base,'label':'Grid routes '+str(index),'routes':routes[index:index+100]})
    batches.append({**base,'label':'Grid paths and itineraries','paths':paths,'itineraries':itineraries})
    
    courses=[]
    for course in plan['scenario']['courses']:
        stops=[]
        for index,row in enumerate(course['stops']):
            stop={'station_sign':row['station'],'dwell_s':60 if 0<index<4 else 0}
            for name in ('arrival','departure'):
                seconds=row[name+'_s']; day,seconds=divmod(seconds,86400)
                stop[name]=f'{seconds//3600:02}:{seconds%3600//60:02}:{seconds%60:02}'; stop[name+'_day_offset']=day
            stops.append(stop)
        courses.append({'course_id':course['course_id'],'train':'GridTrain','itineraries':['I_'+course['family']],'speed_type':speed_type,'stops':stops})
    for index in range(0,len(courses),100): batches.append({**base,'label':'Grid courses '+str(index),'courses':courses[index:index+100]})
    m=models()
    for batch in batches: m.GenerateOperations.model_validate(batch)
    for change in safety: m.SafetyElements.model_validate(change)
    return {'safety_changes':safety,'generation_batches':batches,'requires_rebinding_project_after_each_draft':True,
            'notes':'Apply safety in actual editor session before operations. Replace project/run_file with preceding draft result at every generation batch. get_draft + native topology trace must verify persisted resources and routes.',
            'goal_complete':False,'native_simulation_verified':False}


def editor_payload(batch, session_id, expected_revision):
    payload={'session_id':session_id,'expected_revision':expected_revision,**batch}
    models().EditSession.model_validate(payload)
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('plan'); p.add_argument('output',type=Path);p.add_argument('--root',type=Path,required=True)
    p=sub.add_parser('validate'); p.add_argument('plan',type=Path);p.add_argument('--root',type=Path,required=True)
    p=sub.add_parser('bind'); p.add_argument('--root',type=Path,required=True); p.add_argument('plan',type=Path); p.add_argument('--manifest',type=Path,action='append',required=True);p.add_argument('--project',required=True);p.add_argument('--run-file',required=True);p.add_argument('--speed-type',required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    from yard import require_software_authorization
    require_software_authorization(args.root)
    if args.command=='plan':
        plan=build_plan();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(plan,indent=2)); result=validate_structure(plan)
    elif args.command=='validate':result=validate_structure(json.loads(args.plan.read_text()))
    else:
        result=bind(json.loads(args.plan.read_text()),[json.loads(p.read_text()) for p in args.manifest],args.project,args.run_file,args.speed_type)
        args.output.write_text(json.dumps(result,indent=2)); result={'payload_file':str(args.output),'goal_complete':False,'native_simulation_verified':False}
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try: main()
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'error':str(exc),'code':getattr(exc,'code',None),'goal_complete':False,'native_simulation_verified':False}));sys.exit(2)
