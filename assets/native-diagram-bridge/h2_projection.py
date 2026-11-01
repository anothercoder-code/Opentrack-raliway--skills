"""Bounded native Corridor candidate: five real H2 through courses and three stations."""
from pathlib import Path
import bisect,copy,csv,hashlib,json,math,sys,zipfile


HERE=BASE=SOURCE=DONOR=PROJECT=OUTPUT=RECIPE=None
SOURCE_SHA=None
AUTHORIZATION_ROOT=None
COURSES=('H2E1','H2E2','H2W1','H2W2','H2E1_FOLLOW')
from grid_geometry import w,pf,ns
from build_project import project,trace


def sha(blob):return hashlib.sha256(blob).hexdigest()
def text(obj):return None if obj is None else pf.string(obj)
def items(obj):
    assert w.kind(obj)=='NSMutableArray'
    assert len(obj.contents)==1+obj.contents[0].value
    return [group.value for group in obj.contents[1:]]
def mapping(obj):
    assert w.kind(obj)=='NSMutableDictionary'
    assert len(obj.contents)==1+2*obj.contents[0].value
    return {text(obj.contents[i].value):obj.contents[i+1].value for i in range(1,len(obj.contents),2)}
def array(values):return ns.obj([('NSMutableArray',0),('NSArray',0),('NSObject',0)],
    [('i',[len(values)])]+[('@',[value]) for value in values])
def dictionary(values):
    groups=[('i',[len(values)])]
    for key,value in values.items():groups.extend([('@',[ns.string(key)]),('@',[value])])
    return ns.obj([('NSMutableDictionary',0),('NSDictionary',0),('NSObject',0)],groups)
def numeric(obj):
    assert w.kind(obj)=='NSNumber'
    return float(obj.contents[-1].value)
def object_id(obj):return text(obj) if w.kind(obj)=='NSString' else text(obj.contents[0].value)


def main():
    from opentrack_ai.license_authorization import require_authorization
    if AUTHORIZATION_ROOT is None:
        raise ValueError("Use the authorized native_diagram.py project-h2 entry")
    require_authorization(AUTHORIZATION_ROOT)
    assert not OUTPUT.exists(),'Do not overwrite an already reviewed candidate'
    raw=SOURCE.read_bytes();assert sha(raw)==SOURCE_SHA
    captured,_=w.load_next_compatible(raw)
    source_events=mapping(captured.contents[0].value.contents[0].value)
    end_models,edge_models,station_ends,net_stations=[mapping(group.value) for group in captured.contents[1].value.contents]
    recipe=json.loads(RECIPE.read_text(encoding='utf-8'))
    plans={plan['id']:plan for plan in recipe['plans']}
    document_bytes={dn:(PROJECT/'OTDocuments'/(dn+'.opentrack')).read_bytes() for dn in recipe['proofs']}
    source_input_hashes={dn:sha(blob) for dn,blob in document_bytes.items()}
    p=project(document_bytes,(PROJECT/'OTData/grid.dest').read_bytes())
    offsets={};pairs={};source_ref_ids={}
    for dn,proof in recipe['proofs'].items():
        pairs[dn]={end:tuple(pair) for pair in proof['ids'].values() for end in pair}
        refs={end for key,pair in proof['ids'].items() if key.endswith('_REF') for end in pair}
        observed={int(object_id(obj)) for obj in items(station_ends[dn])}
        offset=min(observed)-min(refs)
        assert observed=={end+offset for end in refs}
        offsets[dn]=offset;source_ref_ids[dn]=refs
    coords={};hot={};station_positions={dn:set() for dn in ('J21','J22','J23')};trace_reviews={}
    def put(key,pos,sign):
        pos=float(pos)
        if key in coords:assert abs(coords[key]-pos)<1e-6,(key,coords[key],pos)
        coords[key]=pos
        value=int(round(pos))*sign
        assert abs(value-pos*sign)<1e-6
        if key in hot:assert hot[key]==value,(key,hot[key],value)
        hot[key]=value
    def paired_native(key,pos,sign):
        put(key,pos,sign)
        if key in end_models:
            opposite=text(end_models[key].contents[1].value)
            if opposite is not None:put(opposite,pos,-sign)
    for course in COURSES:
        plan=plans[course];movement=trace(p,plan['itinerary']);nodes=[tuple(node) for node in movement['nodes']]
        assert movement['nodes']==recipe['traces'][course]['nodes']
        east=plan['documents']==['J21','J22','J23'];assert east or plan['documents']==['J23','J22','J21']
        direction=1 if east else -1;distance=0.0;native_edges=[]
        position=lambda travelled:travelled if east else 12000.0-travelled
        for index,node in enumerate(nodes):
            dn,local_id=node
            if index:
                previous=nodes[index-1];edge_key=p.edge_between(previous,node);edge=p.model(edge_key)
                length=float(edge.contents[9].values[1]);assert length>0
                before,after=position(distance),position(distance+length)
                edge_dn=edge_key[0];global_edge=str(int(edge.contents[0].value)+offsets[edge_dn])
                stored=edge_models[global_edge]
                assert numeric(stored.contents[3].value)==length
                local_end_ids=[int(edge.contents[group].value.contents[0].value) for group in (7,8)]
                current_pair=pairs[dn][local_id]
                finish=[side for side,end_id in enumerate(local_end_ids) if edge_dn==dn and end_id in current_pair]
                assert len(finish)==1,(course,previous,node,edge_key,local_end_ids)
                native_ends=[text(stored.contents[group].value) for group in (1,2)]
                paired_native(native_ends[finish[0]],after,direction)
                paired_native(native_ends[1-finish[0]],before,-direction)
                distance+=length;native_edges.append(global_edge)
            global_end=str(local_id+offsets[dn]);paired_native(global_end,position(distance),direction)
            if local_id in source_ref_ids[dn] and dn in station_positions:station_positions[dn].add(position(distance))
        assert distance==12000
        trace_reviews[course]={'source_documents':plan['documents'],'native_edge_keys':native_edges,'distance_m':distance}
    assert station_positions=={'J21':{0.0},'J22':{6000.0},'J23':{12000.0}}
    
    donor_blob=DONOR.read_bytes();root,stream_version=w.load_next_compatible(donor_blob)
    assert root.clazz.version==11 and len(root.contents)==24
    old_event_dict=mapping(root.contents[0].value.contents[1].value)
    event_array_template=next(iter(old_event_dict.values()))
    assert len(event_array_template.contents)==2
    original_points=items(event_array_template.contents[0].value)
    event_template=next(point for point in original_points if w.kind(point)=='OTCorridorSimEvent')
    assert len(event_template.contents)==3
    assert [group.encodings for group in event_template.contents]==[[b'f'],[b'f'],[b'i']]
    number_template=next(iter(mapping(root.contents[1].value.contents[1].value).values()))
    assert number_template.contents[-1].encodings==[b's']
    def number(value):
        assert -32768<=value<=32767
        obj=copy.deepcopy(number_template);obj.contents[-1].values=[int(value)];return obj
    projected={};reviews={};provenance=[]
    for course in COURSES:
        source=items(source_events[course]);observed=[]
        for index,event in enumerate(source):
            assert w.kind(event)=='OTSimEvent' and len(event.contents)==6
            if event.contents[5].value!=0:continue
            a,b=text(event.contents[1].value),text(event.contents[2].value)
            time,factor=float(event.contents[3].value),float(event.contents[4].value)
            assert a in coords and (b is None or b in coords),(course,index,a,b)
            assert math.isfinite(time) and 0<=factor<=1
            pos=coords[a] if b is None else coords[a]+(coords[b]-coords[a])*factor
            assert -.001<=pos<=12000.001
            observed.append((time,pos,index,a,b,factor))
        assert len(observed)>100 and all(a[0]<=b[0] for a,b in zip(observed,observed[1:]))
        table=CAPTURE_OUTPUT/('OT_'+course+'.st1')
        data=[tuple(map(float,line.split())) for line in table.read_text(encoding='ascii').splitlines() if line and not line.startswith('//')]
        times=[row[0] for row in data];east=plans[course]['documents'][0]=='J21'
        max_distance_error=0.0;max_time_error=0.0;max_sampled_error=0.0
        max_interpolated_error=0.0;supplemental_events=[];points=[]
        for index,(time,pos,source_index,a,b,factor) in enumerate(observed):
            found=bisect.bisect_left(times,time)
            options=range(max(0,found-2),min(len(times),found+3))
            chosen=min(options,key=lambda at:abs(times[at]-time))
            reference=data[chosen][1]*1000.0
            if not east:reference=12000.0-reference
            dt=abs(time-times[chosen]);error=abs(pos-reference)
            
            
            
            supplemental=dt>.01
            if supplemental:
                assert b is None and pos in (0.0,6000.0,12000.0) and dt<=.11,(course,index,time,pos,dt,a,b)
                supplemental_events.append({'source_event_index':source_index,'time_s':time,'position_m':pos,
                    'nearest_st1_time_difference_s':dt,'nearest_st1_distance_difference_m':error})
            else:max_sampled_error=max(max_sampled_error,error)
            left=max(0,bisect.bisect_right(times,time)-1);right=min(len(times)-1,bisect.bisect_left(times,time))
            if times[right]>times[left]:
                fraction=(time-times[left])/(times[right]-times[left])
                interpolated=(data[left][1]+(data[right][1]-data[left][1])*fraction)*1000.0
            else:interpolated=data[left][1]*1000.0
            if not east:interpolated=12000.0-interpolated
            interpolation_error=abs(pos-interpolated)
            max_interpolated_error=max(max_interpolated_error,interpolation_error)
            max_distance_error=max(max_distance_error,error);max_time_error=max(max_time_error,dt)
            point=copy.deepcopy(event_template)
            point.contents[0].values=[ns.number(time)];point.contents[1].values=[ns.number(pos)]
            point.contents[2].values=[1 if index==0 else 0];points.append(point)
            provenance.append({'course':course,'source_event_index':source_index,'time_s':time,
                'posEndID':a,'posNextEndID':b or'','posFactor':factor,'corridor_position_m':pos,
                'native_st1_row':chosen,'native_st1_position_m':reference,'distance_error_m':error,
                'native_st1_time_difference_s':dt,'supplemental_native_node_event':supplemental,
                'native_st1_interpolated_position_m':interpolated,'interpolated_distance_error_m':interpolation_error})
        series=copy.deepcopy(event_array_template)
        series.contents[0].values=[array(points)]
        series.contents[1].values=[array([ns.string(dn) for dn in plans[course]['documents']])]
        projected[course]=series
        reviews[course]={'native_source_record_count':len(source),'plotted_native_position_records':len(points),
            'non_position_messages_excluded':len(source)-len(points),'native_st1_sha256':sha(table.read_bytes()),
            'maximum_distance_difference_m':max_distance_error,'maximum_time_match_difference_s':max_time_error,
            'maximum_sampled_point_distance_difference_m':max_sampled_error,
            'maximum_st1_linear_interpolation_difference_m':max_interpolated_error,
            'supplemental_native_node_events':supplemental_events,
            'sampled_points_equal_st1_within_0_061_m':max_sampled_error<=.061,
            'actual_first_time_s':observed[0][0],'actual_last_time_s':observed[-1][0],
            'actual_first_position_m':observed[0][1],'actual_last_position_m':observed[-1][1]}
    controller=root.contents[0].value
    assert controller.clazz.version==1 and len(controller.contents)==4
    for index,value in enumerate(({},projected,{},{})):controller.contents[index].values=[dictionary(value)]
    topo=root.contents[1].value
    assert len(topo.contents)==3
    topo.contents[0].values=[array([])]
    topo.contents[1].values=[dictionary({key:number(value) for key,value in sorted(hot.items())})]
    topo.contents[2].values=[dictionary({})]
    old_stations=items(root.contents[15].value);station_template=old_stations[0];stations=[]
    for index,dn in enumerate(('J21','J22','J23')):
        station=copy.deepcopy(station_template);station.contents[0].values=[ns.string(dn)]
        station.contents[1].values=[index,index*6000,0 if index==0 else 6000,0]
        neighbours=len(items(net_stations[dn].contents[1].value))
        assert neighbours in (3,4)
        station.contents[2].values=[100,neighbours,0,1];stations.append(station)
    root.contents[2].values=[ns.string(OUTPUT.as_posix())]
    root.contents[3].values=[ns.string('H2 Actual - Five Through Courses')]
    root.contents[4].values=[copy.deepcopy(captured.contents[4].value)]
    root.contents[5].values=[copy.deepcopy(captured.contents[6].value)]
    root.contents[6].values=[0];root.contents[7].values=[32400.0,33900.0]
    root.contents[13].values=[0x8508];root.contents[15].values=[array(stations)]
    root.contents[16].values=[ns.string('Native / 5 H2 courses')]
    root.contents[18].values=[ns.string('H2: J21 - J22 - J23 / Actual Native Run')]
    for index in (19,20,23):root.contents[index].values=[array([])]
    root.contents[22].values=[0]
    blob=w.dump_verified(root,stream_version);again,version=w.load_next_compatible(blob)
    assert w.dump_verified(again,version)==blob
    assert set(mapping(again.contents[0].value.contents[1].value))==set(COURSES)
    assert all(mapping(again.contents[0].value.contents[index].value)=={} for index in (0,2,3))
    assert all(items(again.contents[index].value)==[] for index in (19,20,23))
    assert sha(SOURCE.read_bytes())==SOURCE_SHA
    assert source_input_hashes=={dn:sha((PROJECT/'OTDocuments'/(dn+'.opentrack')).read_bytes()) for dn in document_bytes}
    with OUTPUT.open('xb') as output:output.write(blob)
    with (HERE/'H2-source-point-provenance.csv').open('w',encoding='utf-8-sig',newline='') as output:
        writer=csv.DictWriter(output,fieldnames=list(provenance[0]));writer.writeheader();writer.writerows(provenance)
    receipt={'schema':'bounded-native-H2-corridor-candidate/1','candidate':OUTPUT.as_posix(),
        'candidate_bytes':len(blob),'candidate_sha256':sha(blob),'native_load_render_or_export_verified':False,
        'source_native_collector':SOURCE.as_posix(),'source_native_collector_sha256':SOURCE_SHA,
        'original_display_donor':DONOR.as_posix(),'original_display_donor_sha256':sha(donor_blob),
        'source_topology_counts':{'end':len(end_models),'edge':len(edge_models),'netStation':len(net_stations)},
        'native_document_offsets':offsets,'source_station_positions_m':{dn:sorted(values) for dn,values in station_positions.items()},
        'courses':reviews,'source_route_reviews':trace_reviews,'plotted_points':len(provenance),
        'hot_dictionary_entries':len(hot),'all_plotted_points_compared_against_original_st1':True,
        'root_version_preserved':11,'controller_version_preserved':1,'overwriteData':False,
        'display_flags':0x8508,'display_time_window':[32400,33900],
        'training_stations_events_conflicts_and_single_track_metadata_removed':True,
        'actual_curves_fabricated':False,'source_native_collector_and_native_documents_unchanged':True,
        'scope':'Five complete H2 through courses only. Native actual posEndID/posNextEndID/posFactor/time projected using real route and native edge metres, independently checked against native st1. No turning partial courses, conflicts, occupation stairways, planned timetable or GUI/export claim.',
        'native_save_validation':'Offline overwriteData is disabled. Native CLI load may check decoding but automatic Corridor rewrite is not established; do not enable live capture on this offline display candidate without separate review.'}
    receipt['st1_comparison_interpretation']='Every native source position event is compared with nearest and linearly interpolated native st1 rows. st1 stores sampled cumulative distance with 0.1m text precision; collector stores actual topology endpoint/factor events, including extra node crossings between samples. The metrics are not bitwise identical. Preserve the source events and report differences; do not alter them to force agreement. The native cause of the remaining sampled distance residual is not proven here.'
    (HERE/'H2-actual-candidate-evidence.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'candidate':str(OUTPUT),'bytes':len(blob),'sha256':sha(blob),'plotted_points':len(provenance),
        'courses':{key:review['plotted_native_position_records'] for key,review in reviews.items()},
        'largest_st1_distance_error_m':max(review['maximum_distance_difference_m'] for review in reviews.values()),
        'native_load_render_or_export_verified':False}),flush=True)


if __name__=='__main__':main()
