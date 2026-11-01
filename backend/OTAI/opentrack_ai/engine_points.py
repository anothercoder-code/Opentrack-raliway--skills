"""Original point/scale data commands, based on reviewed native function bodies."""
import copy
import math

from .archive import APIError,w
from .native_colors import color_record

CURVES={'traction':1,'braking':2}
ACTIONS={'add_point','update_point','move_point','delete_points','set_scale','auto_scale'}
POINT_TYPES={'linear':1,'hyperbolic':2}
INT_MIN=-2147483648
INT_MAX=2147483647


def values(point):
    if w.kind(point)!='OTDPoint' or point.clazz.version!=0 or len(point.contents)!=1 or point.contents[0].encodings!=[b'i']*3:
        raise APIError('ENGINE_POINT_SCHEMA','Point editing/reading requires the audited OTDPoint v0 iii layout.')
    return tuple(point.contents[0].values)


def array(diagram,curve):
    value=diagram.contents[CURVES[curve]].value
    return w.elements(value) if value else []


def selected(diagram,curve,index):
    points=array(diagram,curve)
    if not 0<=index<len(points):raise APIError('ENGINE_POINT_INDEX','Point index is outside the current curve.',{'curve':curve,'point_index':index,'point_count':len(points)})
    point=points[index];values(point);return point


def work(operations,count):
    operations.requested_point_work=getattr(operations,'requested_point_work',0)+count
    if operations.requested_point_work>1000000:raise APIError('GENERATION_SIZE','Point commands share a 1000000 touched-row work budget per draft.')


def bounds(diagram):
    return {'minimum_speed_kmh':0,'maximum_speed_kmh':diagram.contents[0].values[0],
        'minimum_force_kn':diagram.contents[5].value,'maximum_force_kn':diagram.contents[0].values[1]}


def within(diagram,speed,force):
    b=bounds(diagram)
    return b['minimum_speed_kmh']<=speed<=b['maximum_speed_kmh'] and b['minimum_force_kn']<=force<=b['maximum_force_kn']


def auto_axis(value):
    
    
    scaled=math.floor((float(value)*1.1)/10.0)*10
    if not INT_MIN<=scaled<=INT_MAX:raise APIError('ENGINE_SCALE_OVERFLOW','Autoscale exceeds the native signed-int32 axis domain.',{'limit':value,'computed_axis':scaled})
    return scaled


def execute(stock,engine,diagrams,command):
    from .engine_diagrams import selection_index,recompute_limits
    diagram=selection_index(diagrams,command.index);result={'action':command.action,'index':command.index,'applied':True}
    if command.action=='add_point':
        if not within(diagram,command.speed_kmh,command.force_kn):return {**result,'applied':False,'reason':'outside_diagram_scale','bounds':bounds(diagram)}
        curve='braking' if command.force_kn<0 else 'traction';points=array(diagram,curve);work(stock.o,len(points)+1)
        existing=next((i for i,point in enumerate(points) if values(point)[0]==command.speed_kmh),None)
        if existing is not None:
            details={'curve':curve,'point_index':existing,'speed_kmh':command.speed_kmh}
            if command.if_speed_exists=='error':raise APIError('ENGINE_POINT_EXISTS','A point at this speed already exists in the destination curve.',details)
            return {**result,'applied':False,'reason':'speed_exists',**details}
        point=copy.deepcopy(stock.d.template('OTDPoint'));point.contents[0].values=[command.speed_kmh,command.force_kn,POINT_TYPES[command.interpolation]]
        points.append(point);points.sort(key=lambda p:values(p)[0]);diagram.contents[CURVES[curve]].values[0]=stock.d.array(points)
        return {**result,'curve':curve,'point_index':next(i for i,p in enumerate(points) if p is point),'point_count':len(points)}
    if command.action in ['update_point','move_point']:
        point=selected(diagram,command.curve,command.point_index);work(stock.o,1);before=values(point)
        if command.action=='move_point':
            if not within(diagram,command.speed_kmh,command.force_kn):return {**result,'applied':False,'reason':'outside_diagram_scale','bounds':bounds(diagram)}
            force=max(0,command.force_kn) if command.curve=='traction' else min(0,command.force_kn)
            point.contents[0].values[:2]=[command.speed_kmh,force]
        else:
            for field,index in [('speed_kmh',0),('force_kn',1),('interpolation',2)]:
                value=getattr(command,field)
                if value is not None:point.contents[0].values[index]=POINT_TYPES[value] if field=='interpolation' else value
        return {**result,'curve':command.curve,'point_index':command.point_index,'before':before,'after':values(point),'point_order_preserved':True,'curve_membership_preserved':True}
    if command.action=='delete_points':
        arrays={curve:array(diagram,curve) for curve in CURVES};work(stock.o,sum(map(len,arrays.values())))
        picked=[point for points in arrays.values() for point in points] if command.all_points else [selected(diagram,ref.curve,ref.point_index) for ref in command.points]
        identities={id(point) for point in picked};removed={}
        for curve,points in arrays.items():
            kept=[point for point in points if id(point) not in identities];removed[curve]=len(points)-len(kept)
            diagram.contents[CURVES[curve]].values[0]=stock.d.array(kept)
        return {**result,'selected_objects':len(identities),'removed_positions':removed,'all_points':command.all_points}
    if command.action=='set_scale':
        before=bounds(diagram)
        for field,group,slot in [('axis_maximum_speed_kmh',0,0),('axis_maximum_force_kn',0,1),('axis_minimum_force_kn',5,0)]:
            value=getattr(command,field)
            if value is not None:diagram.contents[group].values[slot]=max(10,value) if group==0 else min(0,value)
        return {**result,'before':before,'after':bounds(diagram)}
    if command.action=='auto_scale':
        if len(engine.contents)<=17:raise APIError('ROLLING_STOCK_VERSION','Autoscale requires an Engine layout with the audited signed minimum-force field.')
        if command.limits_source=='curves':
            work(stock.o,sum(len(array(d,c)) for d in diagrams for c in CURVES));recompute_limits(engine,diagrams)
        speed=engine.contents[7].value;force=engine.contents[6].value;minimum=engine.contents[17].value
        if speed==0 or force==0:return {**result,'applied':False,'reason':'zero_engine_speed_or_force','limits_source':command.limits_source}
        before=bounds(diagram);axes=[max(10,auto_axis(speed)),max(10,auto_axis(force)),min(0,auto_axis(minimum))]
        diagram.contents[0].values[:2]=axes[:2];diagram.contents[5].values[0]=axes[2]
        return {**result,'limits_source':command.limits_source,'engine_limits':{'maximum_speed_kmh':speed,'maximum_force_kn':force,'minimum_force_kn':minimum},'before':before,'after':bounds(diagram)}
    raise APIError('ENGINE_POINT_OPERATION','Unsupported point/scale action.',command.action)


def state(points,curve,limits):
    speeds=set();duplicate=negative=wrong=unknown=outside=0;ordered=True;previous=None
    for point in points:
        speed,force,kind=values(point);duplicate+=speed in speeds;speeds.add(speed);negative+=speed<0;wrong+=force<0 if curve=='traction' else force>0;unknown+=kind not in [1,2]
        if previous is not None and speed<=previous:ordered=False
        outside+=not(limits['minimum_speed_kmh']<=speed<=limits['maximum_speed_kmh'] and limits['minimum_force_kn']<=force<=limits['maximum_force_kn'])
        previous=speed
    return {'point_count':len(points),'strictly_increasing_speeds':ordered,'duplicate_speed_count':duplicate,'negative_speed_count':negative,'force_sign_mismatch_count':wrong,'unknown_interpolation_count':unknown,'outside_scale_point_count':outside}


class PointReader:
    def __init__(self,service):self.service=service

    def read(self,args):
        from opentrack_train_schema import engine_items
        from .engine_diagrams import diagrams,selection_index,systems
        p=self.service.project(args);matches=[engine for engine in engine_items(p.data['depot']) if w.string(engine.contents[1].value)==args.engine_name]
        if len(matches)!=1:raise APIError('ENGINE_SELECTION','Engine name is missing or ambiguous.',{'engine':args.engine_name,'matches':len(matches)})
        engine=matches[0];saved_diagram=selection_index(diagrams(engine),args.index)
        from .stock_versions import decoded_copy
        diagram=decoded_copy(saved_diagram) if saved_diagram.clazz.version<3 else saved_diagram
        if w.kind(diagram)!='OTDDiagram' or diagram.clazz.version not in [2,3] or len(diagram.contents)!={2:7,3:8}[diagram.clazz.version]:raise APIError('ENGINE_DIAGRAM_VERSION','Unsupported saved diagram layout.')
        arrays={curve:array(diagram,curve) for curve in CURVES};curves=list(CURVES) if args.curve=='both' else [args.curve];total=sum(len(arrays[c]) for c in curves);items=[];at=0
        for curve in curves:
            points=arrays[curve];start=max(0,args.offset-at);end=min(len(points),args.offset+args.limit-at)
            for index in range(start,end):
                speed,force,kind=values(points[index]);items.append({'curve':curve,'point_index':index,'speed_kmh':speed,'force_kn':force,'flag':kind,'interpolation':{1:'linear',2:'hyperbolic'}.get(kind,'unknown')})
            at+=len(points)
        return {'project':str(p.project),'source_digest':p.source_digest,'engine_name':args.engine_name,'index':args.index,
            'description':w.string(diagram.contents[6].value) if diagram.contents[6].value else '',
            'archive_class_version':saved_diagram.clazz.version,'decoded_class_version':diagram.clazz.version,'bounds':bounds(diagram),'color':color_record(diagram.contents[4].value),'power_system_codes':systems(diagram),
            'engine_limits':{'maximum_speed_kmh':engine.contents[7].value,'maximum_force_kn':engine.contents[6].value,'minimum_force_kn':engine.contents[17].value if len(engine.contents)>17 else None,'maximum_power_kw':engine.contents[8].value},
            'curve_state':{curve:state(points,curve,bounds(diagram)) for curve,points in arrays.items()},'total_count':total,'offset':args.offset,'has_more':args.offset+args.limit<total,'items':items,
            'point_order_preserved':True,'native_application_started':False,'scope':'Saved point data and editable-state diagnostics. Valid point records do not establish native simulation readiness.'}
