"""Original saved Z/V diagrams, supply assignments and loss-function data."""
import copy

from .archive import APIError,w
from .drafts import set_text
from .rolling_stock import peak_power_kw
from .native_colors import color_record,make_color
from .engine_points import ACTIONS as POINT_ACTIONS


POINT_TYPES={'linear':1,'hyperbolic':2}
AUTO_SYSTEM_ORDER=[1,20,21,*range(2,13),201,202,*range(101,121)]
KNOWN_SYSTEMS={2:'AC 15kV 16 2/3Hz',3:'AC 10kV 50Hz',4:'AC 25kV 50Hz',5:'AC 50kV 50Hz',
    6:'DC 600V',7:'DC 750V',8:'DC 1200V',9:'DC 1500V',10:'DC 2400V',11:'DC 3000V',
    12:'DC 6000V',13:'AC 11kV 16 2/3Hz',14:'DC 1000V'}


def put(obj,index,value):obj.contents[index].values[0]=value


def diagrams(engine):
    if engine.clazz.version==0:
        value=engine.contents[16].value
        return [value] if value else []
    return w.elements(engine.contents[16].value) if engine.contents[16].value else []


def systems(diagram):
    if len(diagram.contents)<4:return []
    return [int(number.contents[-1].value) for number in w.elements(diagram.contents[3].value)] if diagram.contents[3].value else []


def point_rows(diagram,index):
    if len(diagram.contents)<=index or diagram.contents[index].value is None:return []
    return [tuple(point.contents[0].values) for point in w.elements(diagram.contents[index].value)]


def diagram_record(diagram):
    source_version=diagram.clazz.version
    if source_version<3:
        from .stock_versions import decoded_copy
        diagram=decoded_copy(diagram)
    version=diagram.clazz.version
    if version not in [2,3] or len(diagram.contents)!={2:7,3:8}[version]:
        raise APIError('ENGINE_DIAGRAM_VERSION','Unaudited native Z/V diagram layout.',{'version':version,'groups':len(diagram.contents)})
    def points(index):
        return [{'speed_kmh':v,'force_kn':force,'flag':kind,'interpolation':{1:'linear',2:'hyperbolic'}.get(kind,'unknown')} for v,force,kind in point_rows(diagram,index)]
    bands=[]
    if version>=3 and diagram.contents[7].value is not None:
        array=diagram.contents[7].value.contents[0].value
        for band in w.elements(array) if array else []:
            if band.clazz.version!=0 or len(band.contents)!=1 or band.contents[0].encodings!=[b'i',b'f',b'f']:
                raise APIError('ENGINE_LOSS_SCHEMA','Loss-function rows require the audited OTEfficiency v0 iff layout.')
            speed,factor,fixed=band.contents[0].values
            bands.append({'from_speed_kmh':speed,'loss_factor':factor,'fixed_loss_kw':fixed})
    return {'description':w.string(diagram.contents[6].value) if version>=2 and diagram.contents[6].value else '',
        'archive_class_version':source_version,'axis_maximum_speed_kmh':diagram.contents[0].values[0],
        'axis_maximum_force_kn':diagram.contents[0].values[1],
        'axis_minimum_force_kn':diagram.contents[5].value if version>=2 else None,
        'adhesion_good_percent':diagram.contents[0].values[2],'adhesion_normal_percent':diagram.contents[0].values[3],
        'adhesion_bad_percent':diagram.contents[0].values[4],'adhesion_display_code':diagram.contents[0].values[5],
        'visible':bool(diagram.contents[0].values[6]),'power_system_codes':systems(diagram),
        'power_system_labels':[KNOWN_SYSTEMS.get(code) for code in systems(diagram)],
        'points':points(1),'braking_points':points(2),'loss_function':bands,'color':color_record(diagram.contents[4].value)}


def require_current(diagram):
    if w.kind(diagram)!='OTDDiagram' or diagram.clazz.version!=3 or len(diagram.contents)!=8:
        raise APIError('ENGINE_DIAGRAM_VERSION','Editing requires audited OTDDiagram v3; older diagrams are not silently migrated.')


def set_systems(definitions,diagram,codes):
    if len(codes)!=len(set(codes)):raise APIError('ENGINE_SYSTEM_CONFLICT','Power-system codes within a diagram must be unique.')
    values=[]
    for code in codes:
        number=copy.deepcopy(definitions.template('NSNumber'))
        number.contents=[w.ar.TypedValue(b'*',b'i'),w.ar.TypedValue(b'i',code)];values.append(number)
    put(diagram,3,definitions.array(values))


def configure(definitions,diagram,args,creating=False):
    from .models import TractiveEffortDiagramSpec
    require_current(diagram)
    fields=set(TractiveEffortDiagramSpec.model_fields) if creating else args.model_fields_set-{'action','index'}
    if 'color' in fields and args.color is not None:put(diagram,4,make_color(definitions,args.color))
    if 'description' in fields:set_text(diagram,6,args.description)
    if 'power_system_codes' in fields:set_systems(definitions,diagram,args.power_system_codes)
    for field,index in [('traction_points',1),('braking_points',2)]:
        if field not in fields:continue
        values=getattr(args,field);rows=[]
        if any(b.speed_kmh<=a.speed_kmh for a,b in zip(values,values[1:])):raise APIError('ENGINE_CURVE_ORDER','Curve speeds must increase strictly.')
        if any(point.force_kn<0 if index==1 else point.force_kn>0 for point in values):raise APIError('ENGINE_CURVE_SIGN','Traction forces must be nonnegative; electrical braking forces must be nonpositive.')
        for point in values:
            obj=copy.deepcopy(definitions.template('OTDPoint'));obj.contents[0].values=[point.speed_kmh,point.force_kn,POINT_TYPES[point.interpolation]];rows.append(obj)
        put(diagram,index,definitions.array(rows))
    if 'loss_function' in fields:
        bands=args.loss_function
        if any(b.from_speed_kmh<=a.from_speed_kmh for a,b in zip(bands,bands[1:])):raise APIError('ENGINE_LOSS_ORDER','Loss thresholds must increase strictly.')
        wrapper=copy.deepcopy(diagram.contents[7].value or definitions.template('OTEfficiencyArray'));rows=[]
        for band in bands:
            point=copy.deepcopy(definitions.template('OTEfficiency'));point.contents[0].values=[band.from_speed_kmh,band.loss_factor,band.fixed_loss_kw];rows.append(point)
        put(wrapper,0,definitions.array(rows));put(diagram,7,wrapper)
    defaults={'axis_maximum_speed_kmh':max([v for v,_,_ in point_rows(diagram,1)]+[1]),
        'axis_maximum_force_kn':max([force for _,force,_ in point_rows(diagram,1)]+[1]),
        'axis_minimum_force_kn':min([force for _,force,_ in point_rows(diagram,2)]+[0])}
    for field,index,slot in [('axis_maximum_speed_kmh',0,0),('axis_maximum_force_kn',0,1),('axis_minimum_force_kn',5,0),
        ('adhesion_good_percent',0,2),('adhesion_normal_percent',0,3),('adhesion_bad_percent',0,4),('adhesion_display_code',0,5)]:
        if field in fields:
            value=getattr(args,field)
            if value is not None:diagram.contents[index].values[slot]=value
            elif creating:diagram.contents[index].values[slot]=defaults[field]
    if 'visible' in fields:diagram.contents[0].values[6]=int(args.visible)


def validate_assignments(values):
    if not 1<=len(values)<=64:raise APIError('ENGINE_DIAGRAM_COUNT','An Engine must retain 1-64 diagrams.')
    assigned={}
    for index,diagram in enumerate(values):
        codes=systems(diagram)
        if len(codes)!=len(set(codes)):raise APIError('ENGINE_SYSTEM_CONFLICT','A diagram repeats a power-system code.',index)
        for code in codes:
            if code<=0:continue
            if code in assigned:raise APIError('ENGINE_SYSTEM_CONFLICT','Each power system can belong to at most one diagram.',{'code':code,'first_index':assigned[code],'second_index':index})
            assigned[code]=index
    return assigned


def curve_power_kw(values):
    return max([peak_power_kw([(v,f) for v,f,_ in point_rows(diagram,1)],
        [kind for _,_,kind in point_rows(diagram,1)]) for diagram in values if point_rows(diagram,1)]+[0])


def record_count(values):
    count=0
    for diagram in values:
        count+=sum(len(w.elements(diagram.contents[i].value)) if diagram.contents[i].value else 0 for i in [1,2,3])
        if len(diagram.contents)>7 and diagram.contents[7].value:
            loss=diagram.contents[7].value.contents[0].value
            count+=len(w.elements(loss)) if loss else 0
    return count


def requested_rows(args):
    """Preflight explicit expanded rows before loading/staging large batches."""
    count=0;commands=0;text_bytes=0
    def spec_rows(spec):
        return len(spec.traction_points)+len(spec.braking_points)+len(spec.loss_function)+len(spec.power_system_codes)
    for spec in args.engines:
        count+=sum(spec_rows(diagram) for diagram in spec.tractive_effort_diagrams or [])+len(spec.traction_points or [])
    for operation in args.rolling_stock_operations:
        factor=len(operation.names) if hasattr(operation,'names') else 0
        if operation.kind=='update_engines':
            count+=factor*(sum(spec_rows(diagram) for diagram in operation.tractive_effort_diagrams or [])+len(operation.traction_points or []))
        elif operation.kind=='edit_engine_diagrams':
            commands+=factor*len(operation.edits)
            for edit in operation.edits:
                if edit.action=='add':count+=factor*spec_rows(edit.diagram)
                elif edit.action=='update':count+=factor*sum(len(getattr(edit,key) or []) for key in ['traction_points','braking_points','loss_function','power_system_codes'])
                elif edit.action=='duplicate':count+=factor*len(edit.power_system_codes or [])
                elif edit.action in POINT_ACTIONS:
                    count+=factor*(len(edit.points) if edit.action=='delete_points' else 1 if edit.action in ['add_point','update_point','move_point'] else 0)
                elif edit.action=='import_text' and edit.content is not None:
                    from .engine_curve_exchange import parse_text
                    rows,_=parse_text(edit.content);count+=factor*len(rows);text_bytes+=len(edit.content.encode('utf8'))
    if text_bytes>2000000:raise APIError('GENERATION_SIZE','Curve exchange operations share a 2 MB source-text budget.')
    if count>100000 or commands>10000:raise APIError('GENERATION_SIZE','Diagram requests share a 100000 explicit row and 10000 expanded command budget.',{'rows':count,'commands':commands})


def account_rows(operations,values):
    operations.requested_diagram_rows+=record_count(values)
    if operations.requested_diagram_rows>100000:raise APIError('GENERATION_SIZE','At most 100000 processed diagram point/loss/system rows are supported per draft.')


def replace_diagrams(operations,engine,specs):
    values=[]
    for spec in specs:
        diagram=copy.deepcopy(operations.d.template('OTDDiagram'));configure(operations.d,diagram,spec,True);values.append(diagram)
    validate_assignments(values);account_rows(operations,values);put(engine,16,operations.d.array(values))
    return values


def recompute_limits(engine,values):
    if len(engine.contents)<=17:raise APIError('ROLLING_STOCK_VERSION','Recomputing limits requires an Engine layout with the audited minimum-force field.')
    traction=[row for diagram in values for row in point_rows(diagram,1)];braking=[row for diagram in values for row in point_rows(diagram,2)]
    put(engine,7,max([v for v,_,_ in traction]+[0]));put(engine,6,max([force for _,force,_ in traction]+[0]))
    put(engine,17,min([force for _,force,_ in braking]+[0]))


def selection_index(values,index):
    if not 0<=index<len(values):raise APIError('ENGINE_DIAGRAM_INDEX','Diagram index is outside the current ordered list.',{'index':index,'count':len(values)})
    return values[index]


def edit_engine_diagrams(stock,args):
    from .stock_maintenance import difference
    from .rolling_stock import engine_record
    operations=stock.o;array,index,lookup=stock.select('engines',args.names)
    operations.requested_diagram_commands+=len(args.edits)*len(args.names)
    if operations.requested_diagram_commands>10000:raise APIError('GENERATION_SIZE','At most 10000 expanded diagram commands are supported per draft.')
    imports={};source_bytes=0
    from .engine_curve_exchange import input_text,import_points
    for number,edit in enumerate(args.edits):
        if edit.action=='import_text':
            rows,provenance=input_text(stock.p,edit);imports[number]=(rows,provenance);source_bytes+=provenance['bytes']
    operations.requested_curve_source_bytes=getattr(operations,'requested_curve_source_bytes',0)+source_bytes
    if operations.requested_curve_source_bytes>2000000:raise APIError('GENERATION_SIZE','Curve imports share a 2 MB source-text budget per draft.')
    if sum(len(rows) for rows,_ in imports.values())*len(args.names)>100000:raise APIError('GENERATION_SIZE','Expanded imported point rows exceed the shared 100000-row budget.')
    replacements={};changes=[];import_results=[];point_results=[];initial_point_work=getattr(operations,'requested_point_work',0)
    for name in args.names:
        old=lookup[name];engine=copy.deepcopy(old);values=diagrams(engine)
        for diagram in values:require_current(diagram)
        for number,edit in enumerate(args.edits):
            if edit.action=='update':configure(stock.d,selection_index(values,edit.index),edit)
            elif edit.action in ['add','duplicate']:
                if len(values)>=64:raise APIError('ENGINE_DIAGRAM_COUNT','At most 64 diagrams are supported per Engine.')
                at=len(values) if edit.before_index is None else edit.before_index
                if at>len(values):raise APIError('ENGINE_DIAGRAM_INDEX','Insertion index exceeds the current diagram count.')
                if edit.action=='add':
                    value=copy.deepcopy(stock.d.template('OTDDiagram'));configure(stock.d,value,edit.diagram,True)
                else:
                    value=copy.deepcopy(selection_index(values,edit.index));codes=edit.power_system_codes
                    if codes is None:
                        used={code for diagram in values for code in systems(diagram)}
                        available=next((code for code in AUTO_SYSTEM_ORDER if code not in used),None)
                        if available is None:raise APIError('ENGINE_SYSTEM_EXHAUSTED','No native automatic system remains; supply explicit unused codes or an empty unassigned list.')
                        codes=[available]
                    set_systems(stock.d,value,codes)
                    if edit.description is not None:set_text(value,6,edit.description)
                values.insert(at,value)
            elif edit.action=='import_text':
                rows,provenance=imports[number];import_results.append({'engine':name,'input':provenance,**import_points(stock,values,edit,rows,provenance)})
            elif edit.action in POINT_ACTIONS:
                from .engine_points import execute
                point_results.append({'engine':name,'command_index':number,**execute(stock,engine,values,edit)})
            elif edit.action=='delete':
                selection_index(values,edit.index)
                if len(values)==1:raise APIError('ENGINE_DIAGRAM_COUNT','The original Engine editor retains at least one diagram.')
                values.pop(edit.index)
            else:raise APIError('ENGINE_DIAGRAM_OPERATION','This diagram action is not implemented by the current backend.',edit.action)
        validate_assignments(values);account_rows(operations,values);put(engine,16,stock.d.array(values))
        if args.recompute_engine_limits:recompute_limits(engine,values)
        replacements[id(old)]=engine;changes.append({'entity':'engines','name':name,
            'fields':difference(engine_record(old,True),engine_record(engine,True))})
    w.set_elements(array,[replacements.get(id(obj),obj) for obj in w.elements(array)])
    return {'entity':'engines','names':args.names,'records_updated':len(changes),
        'expanded_diagram_commands':len(args.edits)*len(args.names),'engine_limits_recomputed':args.recompute_engine_limits or any(e.action=='auto_scale' and e.limits_source=='curves' for e in args.edits),
        'nominal_power_preserved':True,'curve_text_imports':import_results,'point_command_results':point_results,
        'point_rows_touched':getattr(operations,'requested_point_work',0)-initial_point_work,'stock_changes':changes}
