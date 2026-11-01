"""Bounded, explicit offline planning for the synthetic three-station demo.

Adapted from OTUndo/tools/prepare_hsr_capacity.py. No native methods or solver
are invoked. Its padded spatial model is a planning screen, not a simulation
acceptance test or a railway capacity result.
"""
import bisect
import collections
import math

from .archive import APIError,seconds,w
from hsr_capacity_graph import initial_tail_resources
from opentrack_train_schema import train_items,engine_items,bound_engine_names


def estimate(path,models,engine,train,config,middle_m):
    if train.contents[6].value!=0 or w.elements(train.contents[2].values[2]):
        raise APIError('PLANNING_MODEL','Only the audited Strahl single-engine, no-trailer proxy is supported.')
    mass=engine.contents[2].values[1];length=engine.contents[2].values[2]
    rotating=engine.contents[2].values[3];resistance_factor=engine.contents[4].value
    diagram,=w.elements(engine.contents[16].value)
    curve=sorted(tuple(o.contents[0].values[:2]) for o in w.elements(diagram.contents[1].value))
    maximum=engine.contents[7].value
    if len(curve)<2 or curve[0][0]!=0 or curve[-1][0]<maximum or len({v for v,f in curve})!=len(curve):
        raise APIError('TRACTION_COVERAGE','Tractive-effort points must cover 0 through the engine speed limit.')
    total=path['distance_m'];edges=[e for r in path['routes'] for e in r['edges']]
    if not 0<middle_m<total:raise APIError('PLANNING_STOP','Intermediate stop must lie inside the through Path.')
    points=sorted({0,total,middle_m,*range(0,total,25),*(e['start_m'] for e in edges),*(e['end_m'] for e in edges)})
    ends=[e['end_m'] for e in edges];limits=[]
    for x in points:
        i=min(bisect.bisect_right(ends,x),len(edges)-1)
        speed=min(maximum,edges[i]['limit_kmh'])/3.6
        if i and edges[i]['start_m']==x:speed=min(speed,edges[i-1]['limit_kmh']/3.6)
        limits.append(speed)
    limits[0]=limits[-1]=limits[points.index(middle_m)]=0.0
    def effort(v):
        kmh=v*3.6;i=max(0,min(len(curve)-2,bisect.bisect_right([x for x,f in curve],kmh)-1))
        x0,f0=curve[i];x1,f1=curve[i+1]
        linear=(f0+(f1-f0)*(kmh-x0)/(x1-x0))*1000
        return min(linear,engine.contents[6].value*1000,config['nominal_power_kw']*1000/max(v,1))
    velocity=[0.0]*len(points)
    for i in range(1,len(points)):
        v=velocity[i-1]
        
        resistance=9.81*(resistance_factor*mass+.03*(v*3.6+15)**2)
        acceleration=(effort(v)-resistance)/(mass*1000*rotating)
        if acceleration<=0 and v<min(limits[i],maximum/3.6)-.01:
            raise APIError('PROXY_UNDERPOWERED','The chosen effort envelope cannot sustain the planned acceleration.')
        acceleration=min(max(.001,acceleration),train.contents[4].value)
        velocity[i]=min(limits[i],math.sqrt(v*v+2*acceleration*(points[i]-points[i-1])))
    for i in range(len(points)-2,-1,-1):
        velocity[i]=min(velocity[i],math.sqrt(velocity[i+1]**2+2*.7*(points[i+1]-points[i])))
    times=[0.0];moving_time=0.0
    for i in range(1,len(points)):
        dt=2*(points[i]-points[i-1])/max(.01,velocity[i]+velocity[i-1]);moving_time+=dt
        elapsed=times[-1]+dt*1.15+(config['dwell_s'] if points[i-1]==middle_m else 0)
        if points[i] in [middle_m,total]:elapsed=math.ceil(elapsed/60)*60
        times.append(elapsed)
    def at(x):
        if x>=total:return times[-1]+(120 if x>total else 0)
        i=max(0,bisect.bisect_right(points,x)-1)
        return times[i]+(times[i+1]-times[i])*(x-points[i])/(points[i+1]-points[i])
    windows={}
    def reserve(key,a,b):
        old=windows.get(tuple(key));windows[tuple(key)]=(min(old[0],a),max(old[1],b)) if old else (a,b)
    for route in path['routes']:
        a=max(0,math.floor(at(route['start_m'])-180));b=math.ceil(at(route['end_m']+length)+120+180)
        for key in route['resources']:reserve(key,a,b)
    initial=initial_tail_resources(path,models,length)
    for key in initial['resources']:reserve(key,0,math.ceil(at(length))+120+180)
    stop=times[points.index(middle_m)]
    peak=max(velocity)*3.6
    cruise=sum(points[i]-points[i-1] for i in range(1,len(points)) if min(velocity[i],velocity[i-1])*3.6>=maximum-.1)
    return {'duration_s':int(times[-1]),'middle_arrival_s':int(stop),'middle_departure_s':int(stop+config['dwell_s']),
        'windows':windows,'peak_speed_kmh':round(peak,3),'cruise_distance_m':cruise,
        'unbuffered_moving_time_s':round(moving_time,2),'initial_body':initial,
        'samples':[{'distance_m':x,'planning_time_s':round(t,3),'kinematic_speed_kmh':round(v*3.6,3)} for x,t,v in zip(points,times,velocity)]}


def summary(profile):
    return {k:v for k,v in profile.items() if k not in ['samples','windows']}


def conflicts(schedule,profiles):
    calendar=collections.defaultdict(list)
    for course in schedule:
        for resource,(a,b) in profiles[course['direction']]['windows'].items():
            calendar[resource].append((course['departure_s']+a,course['departure_s']+b,course['course_id']))
    overlaps=[];minimum=None
    for resource,entries in calendar.items():
        entries.sort()
        for first,second in zip(entries,entries[1:]):
            gap=second[0]-first[1];minimum=gap if minimum is None else min(minimum,gap)
            if gap<0:overlaps.append({'resource':list(resource),'first':first[2],'second':second[2],'overlap_s':-gap})
    return {'resource_conflicts':overlaps[:100],'conflict_count':len(overlaps),'exclusive_resources':len(calendar),'minimum_remaining_gap_s':minimum}


def arrange(profiles,args):
    calendar=collections.defaultdict(list);schedule=[];begin=seconds(args.first_departure);last={}
    jobs=sorted((begin+i*args.departure_interval_s+(args.reverse_offset_s if direction=='up' else 0),direction,i)
        for i in range(args.departures_each_direction) for direction in ['down','up'])
    for requested,direction,index in jobs:
        departure=max(requested,last.get(direction,-args.departure_interval_s)+args.departure_interval_s)
        profile=profiles[direction]
        for attempt in range(500):
            shifted=departure
            for resource,(a,b) in profile['windows'].items():
                for start,stop,cid in calendar[resource]:
                    if departure+a<stop and start<departure+b:shifted=max(shifted,stop-a)
            if shifted==departure:break
            departure=math.ceil(shifted/60)*60
        else:raise APIError('SCHEDULE_SEARCH','Could not find a bounded conflict-free slot.')
        if departure+profile['duration_s']+1800>=86400:raise APIError('DEMO_TOO_LATE','Demo timetable plus run-out exceeds one day; reduce departures or start earlier.')
        cid='G'+str(9001+index*2+(1 if direction=='up' else 0))
        course={'course_id':cid,'direction':direction,'departure_s':departure,'arrival_s':departure+profile['duration_s'],
            'requested_departure_s':requested,'adjusted_s':departure-requested,
            'middle_arrival_s':departure+profile['middle_arrival_s'],'middle_departure_s':departure+profile['middle_departure_s']}
        for resource,(a,b) in profile['windows'].items():calendar[resource].append((departure+a,departure+b,cid))
        schedule.append(course);last[direction]=departure
    return sorted(schedule,key=lambda x:(x['departure_s'],x['course_id']))


def profiles_for(project):
    config=project.scenario
    if config.get('model_type')!='three_station_synthetic_demo':raise APIError('PLANNING_SCOPE','This checker is for generated three-station synthetic demos.')
    train=next((t for t in train_items(project.data['trains']) if w.string(t.contents[0].value)==config['demo_train']),None)
    if train is None:raise APIError('DEMO_VEHICLE_MISSING','Generated demo vehicle is missing.')
    refs=bound_engine_names(train)
    if len(refs)!=1:raise APIError('PLANNING_MODEL','One powered unit is required.')
    engine=next((e for e in engine_items(project.data['depot']) if w.string(e.contents[1].value)==refs[0]),None)
    if engine is None:raise APIError('DEMO_ENGINE_MISSING','Generated demo engine is missing.')
    _,models,paths=project.graph();a,b,c=config['station_signs']
    names={'down':f'P:{a}-{c}_1','up':f'P:{c}-{a}_1'}
    distances={'down':paths[f'P:{a}-{b}_1']['distance_m'],'up':paths[f'P:{c}-{b}_1']['distance_m']}
    return {direction:estimate(paths[name],models,engine,train,config,distances[direction]) for direction,name in names.items()}


def check_plan(project):
    profiles=profiles_for(project);config=project.scenario;a,b,c=config['station_signs'];schedule=[];errors=[]
    for course in project.courses():
        item=project.service(course)
        if not item['enabled']:continue
        rows=sorted((project.timetable_row(k,v) for k,v in project.table().items() if w.string(v.contents[1].value)==item['course_id']),key=lambda r:r['index'])
        signs=[r['station_sign'] for r in rows]
        direction='down' if signs==[a,b,c] else 'up' if signs==[c,b,a] else None
        if direction is None:errors.append({'code':'DEMO_STOP_ORDER','course':item['course_id']});continue
        if item['train']!=config['demo_train']:errors.append({'code':'DEMO_TRAIN_BINDING','course':item['course_id']})
        required='I:'+('P:'+a+'-'+c+'_1' if direction=='down' else 'P:'+c+'-'+a+'_1')[2:]
        if item['itineraries']!=[required]:errors.append({'code':'DEMO_ITINERARY_BINDING','course':item['course_id']})
        departure=seconds(rows[0]['departure']);profile=profiles[direction]
        expected=[profile['middle_arrival_s'],profile['middle_departure_s'],profile['duration_s']]
        actual=[seconds(rows[1]['arrival'])-departure,seconds(rows[1]['departure'])-departure,seconds(rows[2]['arrival'])-departure]
        if actual!=expected:errors.append({'code':'DEMO_RUNTIME_TABLE','course':item['course_id'],'expected':expected,'actual':actual})
        schedule.append({'course_id':item['course_id'],'direction':direction,'departure_s':departure,'arrival_s':seconds(rows[-1]['arrival'])})
    if not schedule:errors.append({'code':'DEMO_EMPTY','details':'No enabled generated courses.'})
    for direction in ['down','up']:
        departures=sorted(row['departure_s'] for row in schedule if row['direction']==direction)
        if len(departures)!=config['departures_each_direction']:errors.append({'code':'DEMO_DIRECTION_COUNT','direction':direction})
        if any(b-a<config['departure_interval_s'] for a,b in zip(departures,departures[1:])):errors.append({'code':'DEMO_HEADWAY','direction':direction})
    audit=conflicts(schedule,profiles)
    if audit['conflict_count']:errors.append({'code':'MODEL_RESOURCE_CONFLICT','count':audit['conflict_count']})
    for direction,p in profiles.items():
        if abs(p['peak_speed_kmh']-config['maximum_speed_kmh'])>.1 or p['cruise_distance_m']<=0:errors.append({'code':'DEMO_SPEED_NOT_REACHED','direction':direction})
    mileage=[];_,_,paths=project.graph()
    for name,path in paths.items():
        ends=name[2:].split('_')[0].split('-');i=config['station_signs'].index(ends[0]);j=config['station_signs'].index(ends[1])
        expected=sum(config['section_distances_m'][min(i,j):max(i,j)])
        mileage.append({'path':name,'metres':path['distance_m'],'expected_metres':expected})
        if path['distance_m']!=expected:errors.append({'code':'DEMO_MILEAGE','path':name})
    for name,diagram in project.corridors.items():
        stations=w.elements(diagram.contents[15].value);signs=[w.string(s.contents[0].value) for s in stations]
        expected=[0]
        for x,y in zip(signs,signs[1:]):
            i=config['station_signs'].index(x);j=config['station_signs'].index(y)
            expected.append(expected[-1]+sum(config['section_distances_m'][min(i,j):max(i,j)]))
        if [s.contents[1].values[1] for s in stations]!=expected:errors.append({'code':'DEMO_DIAGRAM_MILEAGE','diagram':name})
        if diagram.contents[7].values!=[float(config['begin_s']),float(config['end_s'])]:errors.append({'code':'DEMO_DIAGRAM_WINDOW','diagram':name})
    return {'valid':not errors,'errors':errors,'courses':len(schedule),'profiles':{k:summary(v) for k,v in profiles.items()},
        'mileage':mileage,**audit,'planning_model':'25m spatial integration; stored effort/Strahl estimate; 0.7m/s2 braking; 15% running-time allowance; 180s reservation and 300s release/gap',
        'native_simulation_verified':False,'scope':'Offline synthetic resource screen; excludes native dispatch variations, calibrated performance and actual terminal clearance.'}
