"""Capture and independently review original outputs for the bounded yard.

Only evidence is written. No native launch, project edit or GUI observation.
Station identities come from the generated recipe; resource traces are rebuilt
from the exact seventeen reference archives, not trusted from a JSON trace.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from pathlib import Path
import copy,json,math,re
from . import output_io as io,output_kernel as k
from . import composition,services,topology
from opentrack_ai.current_archive import writer as w,catalogs as c
from opentrack_ai.current_archive.prepare_contract import auxiliary as aux
from opentrack_ai.current_archive.tools import ArchiveTools

SCHEMA='yard-native-output-baseline/1'

def encoded(value):
    return (json.dumps(value,ensure_ascii=True,allow_nan=False,indent=2)+'\n').encode('ascii')

def manifest(files):
    return {n:{'sha256':io.sha(b),'bytes':len(b)} for n,b in sorted(files.items())}

def input_names(spec):
    topology.configuration(spec)
    return sorted([*('OTDocuments/'+s['id']+'.opentrack' for s in spec['stations']),
        *('OTData/'+prefix+'.'+role for prefix in ('chain','failure') for role in io.ROLES),
        'eighttracks.run','failure.run'])

def read_inputs(reader,directory,names):
    return {n:reader.secure_bytes(directory/n) for n in names}

def break_value(raw):
    rows=aux.records(raw)
    values=[value for key,value,_ in rows if key=='Break Time']
    days=[value for key,value,_ in rows if key=='Break Day Offset']
    io.need(len(values)==1 and days==['0'],'One same-day native Break control required')
    io.clock(values[0]);return values[0]

def break_projection(raw,expected):
    return composition.rewrite_run(raw,{'Break Time':(break_value(raw),expected)})[0]

def reference_context(files,receipt,project):
    io.need(receipt.get('schema')=='three-station-yard-candidate/1',
            'A yard.py candidate receipt is required')
    spec=receipt['recipe'];topology.configuration(spec)
    io.need(Path(spec['execution_root']).resolve()==project,'Receipt execution root differs from actual project')
    io.need(set(files)==set(input_names(spec)) and manifest(files)==receipt['members'],
            'All seventeen generated reference bytes must match the receipt')
    projected=dict(files)
    
    
    for name in ('eighttracks.run','failure.run'):
        projected[name]=break_projection(projected[name],'00:00:00')
    actual=composition.validate_seventeen(projected,spec)
    normal=actual['scenarios']['normal']['service_alias_projection']['validation']
    infrastructure=normal['infrastructure'];plans=services.make_plans(spec)
    io.need(float(normal['train_length_m'])==209.,'Auditor requires this209m proxy profile')
    io.need(infrastructure['main_distances_m']==k.BOUNDARIES,'Actual reference block distances differ')
    traces={'itineraries':{},'traces':{}}
    for plan in plans:
        cid,itinerary=plan['course_id'],plan['itinerary']
        tr=k.normalize_trace(normal['traces'][cid],infrastructure['full_itineraries'][itinerary])
        traces['itineraries'][itinerary]=tr;traces['traces'][cid]=tr
    return spec,plans,traces

def audit_preexisting_actuals(before,after):
    """Preserve all planned fields/aliases while recording prior result fields.

    At capture these are only preexisting stored values, not verified previous
    train movements. Post-run selected results require the fresh output check.
    """
    def parse(raw):
        root,version=w.load_next_compatible(raw)
        io.need(w.kind(root)=='NSMutableDictionary' and root.clazz.version==0 and
            root.contents[0].encodings==[b'i'] and root.contents[0].value==27 and len(root.contents)==55,
            'Exact27-entry native Timetable required')
        rows={};connections=[]
        for i in range(27):
            key=c.text(root.contents[1+2*i].value);row=root.contents[2+2*i].value
            c.shape(row,'OTTimetable',9,['i','@','@','i','i','@','@','@','@','@','i','f','@','@','@','iiii','@','f','@'])
            io.need(row.contents[0].value==17 and key==c.text(row.contents[1].value)+'#'+str(row.contents[3].value)
                    and key not in rows,'Timetable record identity differs')
            io.need(c.array(row.contents[9].value)==[],'Unexpected timetable connection')
            rows[key]=row;connections.append(id(row.contents[9].value))
        io.need(len(set(connections))==27 and len({id(r) for r in rows.values()})==27,
                'Timetable mutable rows/connection arrays must be independent')
        return rows,version
    old,ov=parse(before);new,nv=parse(after)
    io.need(ov==nv and set(old)==set(new),'Timetable version or key set changed')
    values=[]
    for key,row in new.items():
        prior=old[key];a,b=copy.deepcopy(prior),copy.deepcopy(row)
        for index in (13,14):
            value=c.text(row.contents[index].value)
            if value!='HH:MM:SS':io.clock(value)
            b.contents[index]=copy.deepcopy(a.contents[index])
        io.need(row.contents[15].values[2:]==[0,0],'Stored actual day offsets must remain same-day')
        b.contents[15].values[2:]=a.contents[15].values[2:]
        for rec in (a,b):
            for group in rec.contents:
                for i,x in enumerate(group.values):
                    if isinstance(x,w.GenericArchivedObject) and w.kind(x)=='NSString':
                        c.text(x);group.values[i]=copy.deepcopy(x)
        io.need(k.semantic_graph(a,w)==k.semantic_graph(b,w),
                'Timetable plan, business field or mutable alias changed: '+key)
        values.append({'key':key,'arrival':c.text(row.contents[13].value),
                       'departure':c.text(row.contents[14].value)})
    return {'planned_fields_preserved':True,'mutable_rows_and_connections_distinct':True,
        'preexisting_actual_values':values,'prior_native_movements_inferred':False}

def audit_input_changes(before,after,spec,plans,*,phase,scenario,output=None,output_texts=None,allow_break=False):
    io.need(set(before)==set(after)==set(input_names(spec)),'Exact17 input set required')
    proof={};prefix='chain' if scenario=='normal' else 'failure'
    for name,actual in after.items():
        previous=before[name]
        if previous==actual:continue
        if name.startswith('OTDocuments/'):
            proof[name]=k.audit_native_saved_document(actual,previous)
        elif name in ('OTData/chain.dest','OTData/failure.dest'):
            a,av=w.load_next_compatible(previous);b,bv=w.load_next_compatible(actual)
            io.need(av==bv and w.kind(a)==w.kind(b)=='OTDestInfoList'
                and k.semantic_graph(a,w)==k.semantic_graph(b,w),
                'Destination business graph/order/object aliases changed')
            p=services._project(after,spec)
            io.need(p.check_dest_catalog(actual)==8,'Destination must resolve the actual eight document itineraries')
            proof[name]={'business_graph_order_and_aliases_equal':True,'itineraries_resolved':8}
        elif name.endswith('.timetable'):
            if phase=='capture':proof[name]=audit_preexisting_actuals(previous,actual)
            else:
                io.need(name=='OTData/'+prefix+'.timetable' and output is not None,
                        'Inactive timetable changed after the captured run baseline')
                proof[name]=k.audit_native_timetable_actuals(previous,actual,plans,output,
                    {s['id']:s['name'] for s in spec['stations']},texts=output_texts)
        elif name in ('eighttracks.run','failure.run'):
            io.need(allow_break and break_projection(actual,break_value(previous))==previous,
                    'Protected run changed; only explicitly accepted Break Time restoration is allowed')
            proof[name]={'only_change':'Break Time','old':break_value(previous),'new':break_value(actual)}
        else:raise io.ReviewError('Protected operational input changed: '+name)
    return proof

def locations(args):
    io.need(io.LABEL.fullmatch(args.label) is not None,'Safe evidence label required')
    reader=ArchiveTools(args.root)
    project=reader.path(args.project);evidence=reader.path(args.evidence)
    io.need(evidence.is_relative_to(reader.root/'OTAI/workspaces') and not evidence.is_relative_to(project),
            'Evidence must be a workspace directory outside the native project')
    return reader,project,evidence

def capture(args):
    reader,project,evidence=locations(args)
    io.need(args.receipt is not None,'Capture requires the yard.py publication/preview receipt')
    receipt_raw=io.stable_file(args.receipt)[0];outer=io.parse_json(receipt_raw)
    receipt=outer.get('candidate_receipt',outer);spec=receipt['recipe']
    names=input_names(spec);reference=reader.path(args.reference) if args.reference else project
    refs=read_inputs(reader,reference,names);spec,plans,traces=reference_context(refs,receipt,project)
    files=read_inputs(reader,project,names)
    selected='output' if args.scenario=='normal' else 'output-failure';output=project/selected
    io.need(not io.output_set(output),'Capture requires empty selected output; preserve prior evidence before a rerun')
    changes=audit_input_changes(refs,files,spec,plans,phase='capture',scenario=args.scenario,
                               allow_break=args.allow_break_control_changes)
    target=evidence/(args.label+'-baseline.json')
    io.need(not target.exists(),'Baseline label already exists; do not overwrite it')
    for name,b in refs.items():io.write_new(evidence/(args.label+'-reference')/name,b)
    for name,b in files.items():io.write_new(evidence/(args.label+'-inputs')/name,b)
    io.write_new(evidence/(args.label+'-receipt.json'),receipt_raw)
    io.need(not io.output_set(output) and read_inputs(reader,project,names)==files
        and read_inputs(reader,reference,names)==refs and io.stable_file(args.receipt)[0]==receipt_raw,
        'Input, source receipt or output changed during capture')
    baseline={'schema':SCHEMA,'captured_at_utc':datetime.now(timezone.utc).isoformat(),
        'project_root':str(project),'scenario':args.scenario,'output_directory':str(output),
        'label':args.label,'members':manifest(files),'reference_members':manifest(refs),
        'receipt_sha256':io.sha(receipt_raw),'output_files':[],
        'capture_input_attribution':changes,'reference_actual_topology_rebuilt':True,
        'native_application_started':False,'GUI_operated':False}
    io.write_new(target,encoded(baseline))
    return {'baseline_captured':True,'baseline':str(target),'inputs':17,'output_empty':True,
        'native_execution_verified':False}

def verify(args):
    reader,project,evidence=locations(args);bp=evidence/(args.label+'-baseline.json')
    baseline_raw=io.stable_file(bp)[0];baseline=io.parse_json(baseline_raw)
    io.need(baseline.get('schema')==SCHEMA and baseline['scenario']==args.scenario
        and baseline['label']==args.label and baseline['output_files']==[]
        and Path(baseline['project_root']).resolve()==project,'Exact captured project/scenario baseline required')
    rp=evidence/(args.label+'-receipt.json');raw=io.stable_file(rp)[0]
    io.need(io.sha(raw)==baseline['receipt_sha256'],'Captured receipt drifted')
    outer=io.parse_json(raw);receipt=outer.get('candidate_receipt',outer);spec=receipt['recipe'];names=input_names(spec)
    refs=read_inputs(reader,evidence/(args.label+'-reference'),names)
    before=read_inputs(reader,evidence/(args.label+'-inputs'),names)
    io.need(manifest(refs)==baseline['reference_members'] and manifest(before)==baseline['members'],
            'Captured reference or before-input bytes drifted')
    spec,plans,traces=reference_context(refs,receipt,project)
    
    audit_input_changes(refs,before,spec,plans,phase='capture',scenario=args.scenario,
                        allow_break=args.allow_break_control_changes)
    current=read_inputs(reader,project,names)
    output=project/('output' if args.scenario=='normal' else 'output-failure')
    io.need(Path(baseline['output_directory']).resolve()==output,'Baseline output binding differs')
    paths=io.output_set(output);io.need(paths,'No actual native outputs; execution acceptance remains pending')
    blobs={};inventory={}
    for p in paths:
        name=p.relative_to(output).as_posix();blobs[name],inventory[name]=io.stable_file(p)
    protocol_names=[n for n in blobs if re.fullmatch(r'OT_Protocol\.\d{8}-\d{4}\.txt',n)]
    io.need(len(protocol_names)==1,'Exactly one native protocol cohort required')
    started=datetime.now(timezone.utc);low=io.iso(baseline['captured_at_utc'])-timedelta(seconds=2)
    high=started+timedelta(seconds=2);headers={}
    for name,b in blobs.items():
        matches=io.HEADER.findall(b.decode('latin1'));io.need(len(matches)<=1,'Multiple producer headers: '+name)
        if matches:
            stamp=io.producer(matches[0],io.zone(args.producer_offset))
            io.need(low<=stamp<=high,'Stale/future native producer: '+name);headers[name]=stamp
        io.need(low<=io.iso(inventory[name]['mtime_utc'])<=high,'Stale/future native output mtime: '+name)
    io.need(headers and (max(headers.values())-min(headers.values())).total_seconds()<=args.max_header_span_s,
            'Native producer span exceeds the explicitly selected review limit')
    protocol_name=protocol_names[0]
    required=[protocol_name,'OT_Messages.txt','OT_CourseStatistics.txt']+[
        'OT_'+cid+'.'+ext for cid in sorted(k.COURSES) for ext in ('tt','vt','st1','step1','step2')]
    io.need(all(n in blobs and n in headers for n in required),'Critical native output/header missing')
    texts={n:blobs[n].decode('utf-8-sig') for n in required}
    for n,text in texts.items():
        io.need(Path(io.header_value(text,r'^// File:\s*(.+)$','File')).resolve()==(output/n).resolve(),
                'Native output File header points outside this exact cohort: '+n)
        per_course=re.fullmatch(r'OT_(?:GDD[1-4]01|GDU[1-4]01|GDD102)\.(?:tt|vt|st1|step1|step2)',n) is not None
        expected_scenario=('Adh. Outside: good / Adh. Tunnel: good / Delay: None / Global Perf.: 100.0 % / Course on Time Perf.: 100.0 % / Course Delay Perf.: 100.0 % / Step: 0.2 s / Time: 09:00:00 - 09:20:00'
            if per_course else 'Adh. Outside: good / Adh. Tunnel: good / Delay: none / Global Perf.: 100.0 % / Step: 0.2 s / Time: 09:00:00 - 09:20:00')
        io.need(io.header_value(text,r'^// Scenario:\s*(.+)$','Scenario')==expected_scenario,
            'Actual native output scenario/Delay/performance differs: '+n)
        if per_course:
            io.need(io.header_value(text,r'^// Train Speedtype:\s*(.+)$','Train Speedtype')==services.SPEED_TYPE,
                    'Actual native per-Course speed type differs: '+n)
    protocol=texts[protocol_name];messages=texts['OT_Messages.txt'];prefix='chain' if args.scenario=='normal' else 'failure'
    for role,key in io.ROLES.items():
        io.need(Path(io.header_value(protocol,r'^'+re.escape(key)+r':(.+)$',key)).resolve()==
            (project/'OTData'/(prefix+'.'+role)).resolve(),'Native catalog binding differs: '+key)
    io.need(Path(io.header_value(protocol,r'^OutputPath:\s*\n([^\r\n]+)','OutputPath')).resolve()==output,
            'Native output path differs')
    io.need('Simulation Time   : 09:00:00 - 09:20:00' in protocol and
        float(io.header_value(protocol,r'^Simulation Step\s*:\s*([0-9.]+) s\s*$','Step'))==.2,
        'Native run window/step differs')
    for key,expected in (('Adhesion Outside','good'),('Adhesion Tunnel','good'),
                         ('Delay Scenario','None'),('Global Performance','100.0 %')):
        io.need(io.header_value(protocol,r'^'+re.escape(key)+r'\s*:\s*(.+)$',key)==expected,
                'Actual native protocol scenario differs: '+key)
    speed_types=[s.strip() for s in protocol.split('Train Speed Types:',1)[1].split('Scenario:',1)[0].splitlines() if s.strip()]
    io.need(speed_types==[services.SPEED_TYPE],'Actual native speed-type selection differs')
    incident_rows=[s.strip() for s in protocol.split('Incidents:',1)[1].splitlines() if s.strip()]
    expected_incidents=[] if args.scenario=='normal' else ['D1_BLOCK_FAILURE\t09:00:00\t09:06:00']
    io.need(incident_rows==expected_incidents,'Actual native selected Incident inventory differs')
    used=protocol.split('Used Courses:',1)[1].split('Occupations:',1)[0]
    rows_used=[re.fullmatch(r'([^\s]+)\s+\(100 %/100 %\)',line.strip()) for line in used.splitlines() if line.strip()]
    io.need(len(rows_used)==9 and all(rows_used) and {m[1] for m in rows_used}==k.COURSES,
            'Exact nine selected native Courses/performance required')
    entries=[s.strip() for s in protocol.split('Open Topology-Files:',1)[1].split('Incidents:',1)[0].splitlines() if s.strip()]
    docs={(project/'OTDocuments'/(s['id']+'.opentrack')).resolve() for s in spec['stations']}
    io.need(len([s for s in entries if Path(s).is_absolute()])==3
        and {Path(s).resolve() for s in entries if Path(s).is_absolute()}==docs
        and entries.count('Untitled')<=1 and all(s=='Untitled' or Path(s).is_absolute() for s in entries),
        'Native topology document inventory differs')
    for line in messages.splitlines():
        parts=[x.strip() for x in line.split('\t')]
        if len(parts)>=4 and parts[0] in {'NORMAL','WARNING','ERROR','FATAL'}:
            io.need(not parts[2] or parts[2] in k.COURSES,'Unexpected native Message Course: '+parts[2])
    stats,routes=io.parse_stats(texts['OT_CourseStatistics.txt'],k.COURSES)
    message_review=k.classify_native_messages(messages,plans,stats,traces)
    reports={};trajectories={};vts={};station_names={s['id']:s['name'] for s in spec['stations']}
    for plan in plans:
        cid=plan['course_id']
        reports[cid],trajectories[cid],vts[cid]=k.course(plan,station_names,messages,texts,
            stats[cid],routes[cid],traces['itineraries'][plan['itinerary']])
    traffic=k.all_pairs(reports,traces,trajectories,texts)
    first=io.clock(io.header_value(protocol,r'^First Process\s*:\s*(.+)$','First Process'))
    last=io.clock(io.header_value(protocol,r'^Last Process\s*:\s*(.+)$','Last Process'))
    io.need(32400<=first<=last<=33600 and last>=max(r['end_s'] for r in reports.values())-.51,
            'Native process range does not cover actual Course completions')
    failure=None
    if args.scenario=='failure':
        incident=k.fault_incident_events(messages,spec['stations'][0]['id'])
        down,heads,not_departed=k.fault_barrier(reports,trajectories)
        stops={}
        for cid in down:
            times=[t for t,_ in trajectories[cid]]
            import bisect
            stopped=[t for t,v in vts[cid] if 32460<t<32760 and v==0 and
                trajectories[cid][max(0,bisect.bisect_right(times,t)-1)][1]>1250]
            if stopped:stops[cid]=stopped
        io.need(stops,'No actual Down front train stop approaching failed B2')
        failure={'target':spec['stations'][0]['id']+'/S_'+spec['stations'][0]['id']+'_D_B2',
            'native_incident_event_lines':incident,'all_five_Down_courses':down,
            'maximum_recorded_head_m_before_recovery':heads,'not_departed_before_recovery':not_departed,
            'actual_stopped_Down_courses':stops,'all_B2_to_B3_reservations_after_0906':True,
            'fault_red_lamp_observed':False,'continuous_motion_in_sampling_gaps_verified':False}
    snapshot=evidence/(args.label+'-outputs-'+io.sha(blobs[protocol_name])[:12])
    for name,b in blobs.items():io.write_new(snapshot/name,b)
    changes=audit_input_changes(before,current,spec,plans,phase='verify',scenario=args.scenario,
        output=snapshot,output_texts=texts,allow_break=args.allow_break_control_changes)
    io.need(read_inputs(reader,project,names)==current and
        [p.relative_to(output).as_posix() for p in io.output_set(output)]==list(blobs)
        and all(io.stable_file(output/n)[0]==b and io.stable_file(snapshot/n)[0]==b for n,b in blobs.items())
        and io.stable_file(bp)[0]==baseline_raw and io.stable_file(rp)[0]==raw,
        'Inputs, outputs, captured baseline or receipt changed during review')
    result={'schema':'portable-yard-native-output-review/1','passed':True,'native_output_checks_passed':True,
        'project_root':str(project),'scenario':args.scenario,'baseline':str(bp),
        'baseline_sha256':io.sha(baseline_raw),'checked_at_utc':started.isoformat(),
        'current17_input_manifest':manifest(current),'input_change_attribution':changes,
        'reference_resource_traces_rebuilt_from_archives':True,
        'output_file_count':len(blobs),'output_manifest':inventory,'output_snapshot':str(snapshot),
        'courses':reports,'total_distance_km':90.,'terminal_stops':9,
        'native_message_review':message_review,'shared_yard_traffic':traffic,'failure':failure,
        'native_application_started':False,'GUI_operated':False,'GUI_End_observed':False,
        'dynamic_lamp_colours_observed':False,'final_terminal_throat_release_verified':False,
        'physical_clearance_is_conditional_on_explicit_error_envelope':True,
        'continuous_railway_safety_certified':False,'proxy_physics_calibrated':False}
    report=evidence/(args.label+'-review-'+started.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    io.write_new(report,encoded(result))
    return {'passed':True,'report':str(report),'native_output_checks_passed':True,'courses':9,
            'output_files':len(blobs),'GUI_or_lamp_acceptance':False}
