"""Optimized stock-format operational data generation; no simulator or GUI."""
import copy
import csv
import io
import json
from pathlib import Path

from .archive import APIError,clock,seconds,w,END_KINDS
from .drafts import set_text,text
from .operations import Definitions
from .native_records import absolute_time,split_time,trailer_record,upgrade_records
from .rolling_stock import ENGINE_SCALARS,ENGINE_FLAGS,TRAIN_SCALARS,CATEGORY_SCALARS,CATEGORY_FLAGS,CATEGORY_TABLES,set_scalars,category_record,peak_power_kw
from .course_records import SPACING_CODES,COURSE_SCALARS,COURSE_STRINGS,course_record,upgrade_course_records
from opentrack_course_schema import course_array
from opentrack_train_schema import engine_items,train_items
from opentrack_station_schema import station_items


KINDS={'define_engine','define_category','define_formation','define_station','define_course','service_pattern','set_timetable','update_courses','rename_courses','delete_courses','reset_course_itineraries','update_timetable_rows','insert_timetable_rows','delete_timetable_rows','shift_timetable_rows','set_timetable_interval','reset_timetable_actual','copy_actual_to_planned','sync_timetable','edit_timetable_connections','import_timetable_text'}
from .stock_maintenance import KINDS as STOCK_KINDS
KINDS |= STOCK_KINDS
from .railml_import import KINDS as XML_STOCK_KINDS
KINDS |= XML_STOCK_KINDS
from .timetable_editing import KINDS as TIMETABLE_KINDS
KINDS |= TIMETABLE_KINDS


def put(obj,index,value):obj.contents[index].values[0]=value


class OperationalData:
    def __init__(self,project):
        self.p=project;self.d=Definitions(project);self.changed_timetables=set();self.requested_rows=0;self.requested_connections=0
        self.migrations={};self.upgraded_timetable=False;self.upgraded_courses=False;self.course_update_targets=0;self.requested_courses=0
        self.stock_update_targets=0
        self.timetable_creation_targets=0
        self.stock_prepared_entities=set()
        self.requested_diagram_rows=0;self.requested_diagram_commands=0

    def template(self,kind,pool=(),name=None,index=0):
        if name is not None:
            result=next((obj for obj in pool if w.string(obj.contents[index].value)==name),None)
            if result is None:raise APIError('GENERATION_TEMPLATE_NOT_FOUND','The explicitly selected native template is missing.',{'class':kind,'name':name})
            return copy.deepcopy(result)
        result=next(iter(pool),None)
        return copy.deepcopy(result if result is not None else self.d.template(kind))

    def store(self,array,obj,name,index,replace):
        items=w.elements(array);matches=[i for i,old in enumerate(items) if w.string(old.contents[index].value)==name]
        if len(matches)>1:raise APIError('DUPLICATE_NAME','Existing native names are ambiguous.',name)
        if matches and not replace:raise APIError('ENTITY_EXISTS','Use a fresh name or explicitly set replace_existing.',name)
        if matches:items[matches[0]]=obj
        else:items.append(obj)
        w.set_elements(array,items);return bool(matches)

    def apply(self,args):
        from .course_lifecycle import KINDS as LIFECYCLE_KINDS,CourseLifecycleOperations
        from .timetable_editing import KINDS as TIMETABLE_KINDS,TimetableOperations
        if args.kind in STOCK_KINDS|{'define_engine','define_formation','import_rolling_stock_xml'} and args.kind!='migrate_rolling_stock':self.prepare_stock_versions()
        if args.kind in STOCK_KINDS:
            from .stock_maintenance import StockOperations
            result=StockOperations(self).apply(args)
        elif args.kind in LIFECYCLE_KINDS:
            self.prepare_courses();result=getattr(CourseLifecycleOperations(self),args.kind)(args)
        elif args.kind in TIMETABLE_KINDS:result=getattr(TimetableOperations(self),args.kind)(args)
        else:result=getattr(self,args.kind)(args)
        return {'kind':args.kind,**result,'native_simulation_verified':False}

    def prepare_stock_versions(self,entities=('engines','formations')):
        pending=set(entities)-self.stock_prepared_entities
        if not pending:return {}
        from .stock_versions import migrate
        counts=migrate([self.p.data['depot'],self.p.data['trains']],pending)
        for kind,count in counts.items():self.migrations[kind]=self.migrations.get(kind,0)+count
        self.stock_prepared_entities.update(pending)
        return counts

    def import_rolling_stock_xml(self,args):
        from .railml_import import RollingStockImporter
        return RollingStockImporter(self,args).run()

    def define_engine(self,args):
        engines=engine_items(self.p.data['depot']);engine=self.template('OTEngine',engines,args.template_name,1)
        set_text(engine,1,args.name);engine.contents[2].values=list(engine.contents[2].values)
        engine.contents[2].values[1:5]=[args.mass_t,args.length_m,args.rotating_mass_factor,args.number_of_axles]
        for index,value in [(3,args.adhesion_mass_t or args.mass_t),(6,args.maximum_force_kn),(7,args.maximum_speed_kmh),(9,args.driven_axles),(10,args.traction_motors)]:put(engine,index,value)
        set_scalars(engine,args,ENGINE_SCALARS)
        if args.cw_value is not None:engine.contents[2].values[5]=args.cw_value
        for field,bit in ENGINE_FLAGS.items():
            value=getattr(args,field)
            if value is not None:put(engine,11,engine.contents[11].value|bit if value else engine.contents[11].value&~bit)
        if args.tractive_effort_diagrams is not None:
            from .engine_diagrams import replace_diagrams,curve_power_kw,point_rows,systems
            values=replace_diagrams(self,engine,args.tractive_effort_diagrams)
            if any(force>args.maximum_force_kn for diagram in values for _,force,_ in point_rows(diagram,1)):
                raise APIError('TRACTION_FORCE','Diagram forces exceed the declared Engine maximum.')
            put(engine,8,args.maximum_power_kw if args.maximum_power_kw is not None else curve_power_kw(values))
            if args.minimum_force_kn is None:put(engine,17,min([force for diagram in values for _,force,_ in point_rows(diagram,2)]+[0]))
            replaced=self.store(self.p.data['depot'],engine,args.name,1,args.replace_existing)
            complete=any(systems(diagram) and point_rows(diagram,1) and max(row[0] for row in point_rows(diagram,1))>=args.maximum_speed_kmh for diagram in values)
            return {'engine':args.name,'replaced':replaced,'maximum_speed_kmh':args.maximum_speed_kmh,
                'mass_t':args.mass_t,'length_m':args.length_m,'diagram_count':len(values),
                'traction_source':'explicit per-system curve data','curve_data_covers_declared_speed':complete,
                'curve_warning':None if complete else 'Saved diagram data does not provide an assigned curve through the declared Engine speed; simulation preparation is incomplete.'}
        if args.traction_points is not None:
            points=[(p.speed_kmh,p.force_kn) for p in args.traction_points];source='explicit user-supplied traction points'
        else:
            speeds=sorted({0,args.maximum_speed_kmh,*range(0,args.maximum_speed_kmh+1,50)})
            points=[(v,min(args.maximum_force_kn,round(args.nominal_power_kw*3.6/max(v,1)))) for v in speeds]
            source='uncalibrated constant-power engineering proxy'
        if points[0][0]!=0 or points[-1][0]<args.maximum_speed_kmh or any(b[0]<=a[0] for a,b in zip(points,points[1:])):
            raise APIError('TRACTION_COVERAGE','Traction speeds must increase strictly from 0 through the declared engine maximum.',args.name)
        if points[0][1]<=0 or any(force>args.maximum_force_kn for _,force in points):raise APIError('TRACTION_FORCE','Starting force must be positive and no point may exceed maximum_force_kn.',args.name)
        put(engine,8,args.maximum_power_kw if args.maximum_power_kw is not None else args.nominal_power_kw if args.nominal_power_kw is not None else peak_power_kw(points))
        if args.minimum_force_kn is None:put(engine,17,min(engine.contents[17].value,args.maximum_force_kn))
        old=w.elements(engine.contents[16].value) if engine.contents[16].value else []
        diagram=copy.deepcopy(old[0] if old else self.d.template('OTDDiagram'));diagram.contents[0].values[0]=args.maximum_speed_kmh;diagram.contents[0].values[1]=args.maximum_force_kn
        records=[]
        for speed,force in points:
            point=copy.deepcopy(self.d.template('OTDPoint'));point.contents[0].values=[speed,force,1];records.append(point)
        put(diagram,1,self.d.array(records));put(diagram,2,self.d.array())
        if diagram.contents[3].value is None or not w.elements(diagram.contents[3].value):put(diagram,3,self.d.array([copy.deepcopy(self.d.template('NSNumber'))]))
        if diagram.contents[7].value is None:put(diagram,7,copy.deepcopy(self.d.template('OTEfficiencyArray')))
        set_text(diagram,6,'Generated: '+source);put(engine,16,self.d.array([diagram]))
        from .engine_diagrams import account_rows
        account_rows(self,[diagram])
        replaced=self.store(self.p.data['depot'],engine,args.name,1,args.replace_existing)
        return {'engine':args.name,'replaced':replaced,'maximum_speed_kmh':args.maximum_speed_kmh,'mass_t':args.mass_t,'length_m':args.length_m,'traction_points':len(points),'traction_source':source}

    def define_category(self,args):
        array=self.p.data['trains'].contents[1].value;items=w.elements(array)
        from .rolling_stock import require_current_category
        for existing in items:require_current_category(existing)
        obj=self.template('OTTrainCategory',items,args.template_name,1);set_text(obj,1,args.name)
        require_current_category(obj)
        set_scalars(obj,args,CATEGORY_SCALARS)
        from .rolling_stock import set_category_extended
        set_category_extended(obj,args,self.d)
        for field,bit in CATEGORY_FLAGS.items():
            flags=obj.contents[0].values[1];obj.contents[0].values[1]=flags|bit if getattr(args,field) else flags&~bit
        for field,(index,wrapper_type,point_type) in CATEGORY_TABLES.items():
            values=getattr(args,field);wrapper=copy.deepcopy(obj.contents[index].value or self.d.template(wrapper_type))
            if wrapper.contents[0].value is None:put(wrapper,0,self.d.array())
            if values is not None:
                rows=[]
                for value in values:
                    point=copy.deepcopy(self.d.template(point_type))
                    point.contents[0].values=[value.delay_s,value.priority] if field=='delay_priorities' else [value.minimum,value.maximum,value.probability_percent]
                    rows.append(point)
                put(wrapper,0,self.d.array(rows))
            put(obj,index,wrapper)
        for enabled,table in [('use_on_time_performance','on_time_performance'),('use_delayed_performance','delayed_performance')]:
            if getattr(args,enabled) and not category_record(obj)[table]:raise APIError('CATEGORY_DISTRIBUTION','Enabled performance distribution needs nonempty intervals.',table)
        replaced=self.store(array,obj,args.name,1,args.replace_existing)
        return {'category':args.name,'replaced':replaced,'dispatching_priority':args.dispatching_priority,'priority_direction':'smaller number is higher priority','record':category_record(obj)}

    def category(self,name):
        array=self.p.data['trains'].contents[1].value;items=w.elements(array)
        if any(w.string(o.contents[1].value)==name for o in items):return False
        from .rolling_stock import require_current_category
        for existing in items:require_current_category(existing)
        obj=self.template('OTTrainCategory',items);set_text(obj,1,name)
        for index,kind in [(10,'OTDelayIntervalArray'),(12,'OTDelayPriorityArray'),(13,'OTPerformanceIntervalArray'),(14,'OTPerformanceIntervalArray')]:
            if obj.contents[index].value is None:put(obj,index,copy.deepcopy(self.d.template(kind)))
        w.set_elements(array,items+[obj]);return True

    def define_formation(self,args):
        if args.trailers:
            upgraded=upgrade_records(self.p.data['trains'],'OTTrailer')
            if upgraded:self.migrations['OTTrailer']=self.migrations.get('OTTrailer',0)+upgraded
        engines={w.string(o.contents[1].value):o for o in engine_items(self.p.data['depot'])}
        missing=[ref.engine_name for ref in args.engines if ref.engine_name not in engines]
        if missing:raise APIError('ENGINE_BINDING','Formation references missing exact Engine names.',missing)
        units=[ref.engine_name for ref in args.engines for _ in range(ref.count)]
        if len(units)>64:raise APIError('FORMATION_SIZE','At most 64 powered references are supported per generated formation.')
        size=len(units)+sum(item.count for item in args.trailers)
        if size>1024:raise APIError('FORMATION_SIZE','At most 1024 powered/trailer records are supported per formation.')
        explicit=[position for item in [*args.engines,*args.trailers] for position in (item.positions or [])]
        if len(explicit)!=len(set(explicit)) or any(p>size for p in explicit):raise APIError('FORMATION_POSITIONS','Positions must be unique and within the complete 1-based consist.',explicit)
        free=iter(position for position in range(1,size+1) if position not in explicit)
        engine_positions=[position for ref in args.engines for position in (ref.positions or [next(free) for _ in range(ref.count)])]
        trailer_placements=[(spec,position) for spec in args.trailers for position in (spec.positions or [next(free) for _ in range(spec.count)])]
        vehicles=train_items(self.p.data['trains']);train=self.template('OTTrain',vehicles,args.template_name)
        set_text(train,0,args.name);references=[]
        for position,name in zip(engine_positions,units):
            ref=copy.deepcopy(self.d.template('OTTrainEngine'));set_text(ref,0,name);put(ref,1,position);references.append(ref)
        trailers=[]
        for spec,position in trailer_placements:
            obj=copy.deepcopy(self.d.template('OTTrailer'));set_text(obj,1,spec.name)
            obj.contents[2].values[1:5]=[spec.mass_t,spec.length_m,spec.rotating_mass_factor,spec.number_of_axles]
            if spec.cw_value is not None:obj.contents[2].values[5]=spec.cw_value
            obj.contents[3].values=[0,position,spec.number_of_items]
            for index,value in [(4,spec.maximum_speed_kmh),(5,spec.power_loss_kw),(6,spec.power_loss_delta_load_factor_kw_per_t)]:put(obj,index,value)
            trailers.append(obj)
        brakes=copy.deepcopy(train.contents[2].values[0] or self.d.template('OTDecelerationArray'));points=[]
        speeds=[engines[name].contents[7].value for name in units]+[spec.maximum_speed_kmh for spec,_ in trailer_placements];vmax=max(speeds)
        curve=[(p.speed_kmh,p.deceleration_mps2,p.secondary_deceleration_mps2 or p.deceleration_mps2) for p in args.braking_points] if args.braking_points is not None else [(v,args.braking_deceleration_mps2,args.braking_deceleration_mps2) for v in sorted({0,vmax})]
        if curve[0][0]!=0 or curve[-1][0]<vmax or any(b[0]<=a[0] for a,b in zip(curve,curve[1:])):raise APIError('BRAKING_COVERAGE','Braking speeds must increase strictly from zero through all unit speed limits.')
        for speed,primary,secondary in curve:
            point=copy.deepcopy(self.d.template('OTDeceleration'));point.contents[0].values=[speed,-primary,-secondary];points.append(point)
        put(brakes,0,self.d.array(points));train.contents[2].values=[brakes,self.d.array(references),self.d.array(trailers)]
        train.contents[1].values[2]=-curve[0][1] if all(row[1]==curve[0][1] for row in curve) else float('nan')
        train.contents[12].values[0]=0;put(train,4,args.maximum_acceleration_mps2)
        set_scalars(train,args,TRAIN_SCALARS)
        for field,index in [('resistance_coefficients_excl',5),('resistance_coefficients_incl',7)]:
            if getattr(args,field) is not None:train.contents[index].values=list(getattr(args,field))
        for field,bit in [('use_maximum_drawbar_force',1),('use_minimum_time_to_hold_speed',2)]:
            value=getattr(args,field)
            if value is not None:put(train,15,train.contents[15].value|bit if value else train.contents[15].value&~bit)
        category=args.category or w.string(train.contents[3].value) or 'Category 1';created=self.category(category);set_text(train,3,category)
        replaced=self.store(self.p.data['trains'].contents[3].value,train,args.name,0,args.replace_existing)
        return {'formation':args.name,'replaced':replaced,'category':category,'category_created':created,'powered_units':len(units),
            'engine_references':[{'name':name,'position':position} for name,position in zip(units,engine_positions)],
            'trailers':[trailer_record(obj) for obj in trailers],
            'length_m':sum(engines[name].contents[2].values[2] for name in units)+sum(spec.length_m for spec,_ in trailer_placements),
            'mass_t':sum(engines[name].contents[2].values[1] for name in units)+sum(spec.mass_t for spec,_ in trailer_placements),
            'maximum_speed_kmh':min(speeds),'scope':'Explicit powered/trailer records with unique 1-based consist positions. No simulation executed.'}

    def define_station(self,args):
        known=station_items(self.p.data['stations']);existing=known.get(args.sign)
        if existing and not args.replace_existing:raise APIError('ENTITY_EXISTS','Station sign already exists; set replace_existing explicitly.',args.sign)
        station=copy.deepcopy(existing or self.d.template('OTStation'));set_text(station,1,args.sign);set_text(station,2,args.name);known[args.sign]=station
        if args.timing_station is not None:put(station,7,int(args.timing_station))
        root=self.p.data['stations'];root.contents=[w.ar.TypedValue(b'i',len(known))]
        for sign,item in known.items():root.contents.extend([w.ar.TypedValue(b'@',item.contents[1].value),w.ar.TypedValue(b'@',item)])
        if args.end_ids and not args.document:raise APIError('STATION_DOCUMENT_REQUIRED','Station End assignments require a document.')
        assigned=0
        if args.document:
            from .geometry import Geometry
            geometry=Geometry(self.p);pool=geometry.pool(args.document)
            model=next((o for o in pool if w.kind(o)=='OTStationModel' and w.string(o.contents[7].value)==args.sign),None)
            if model is None:
                model=geometry.graphic('OTStationModel',args.document);set_text(model,7,args.sign);pool.append(model)
            for ident in args.end_ids:
                end=geometry.object(args.document,ident,END_KINDS);put(end,12,model);assigned+=1
            geometry.sync(args.document)
        return {'station':args.sign,'name':args.name,'timing_station':bool(station.contents[7].value),'assigned_ends':assigned,'station_area_assigned':bool(assigned)}

    def prepare_timetable(self):
        if not self.upgraded_timetable:
            for kind in ['OTTimetable','OTConnection']:
                count=upgrade_records(self.p.data['timetable'],kind)
                if count:self.migrations[kind]=count
            self.upgraded_timetable=True

    def make_connections(self,specs,course_id,station_sign):
        connections=[]
        for spec in specs:
            obj=copy.deepcopy(self.d.template('OTConnection'))
            for slot,value in [(0,course_id),(1,spec.target_course_id),(2,station_sign),(3,clock(spec.minimum_wait_s)),(5,clock(spec.maximum_wait_s) if spec.maximum_wait_s is not None else 'HH:MM:SS'),(6,spec.target_station_sign or station_sign)]:set_text(obj,slot,value)
            put(obj,4,int(spec.join)+2*int(spec.split)+4*int(spec.entry_connection)+8*int(spec.dispo_connection));put(obj,7,spec.time_reference_type);put(obj,8,spec.dispatching_distance_km);connections.append(obj)
        return self.d.array(connections)

    def make_timetable_row(self,course_id,index,count,stop):
        row=copy.deepcopy(self.d.template('OTTimetable'))
        for slot,value in [(1,course_id),(2,stop.interval_reference_course_id or '0'),(5,stop.station_sign),(6,stop.arrival or 'HH:MM:SS'),(7,stop.departure or 'HH:MM:SS'),(8,str(stop.dwell_s)),(12,str(stop.mean_delay_s)),(13,'HH:MM:SS'),(14,'HH:MM:SS'),(16,stop.distribution_name),(18,stop.track_id)]:set_text(row,slot,value)
        put(row,3,index);put(row,4,count-1);put(row,9,self.make_connections(stop.connections,course_id,stop.station_sign));put(row,10,int(stop.stop_at_station)+2*int(stop.timing_station));put(row,11,stop.interval_offset_s)
        row.contents[15].values=[stop.arrival_day_offset,stop.departure_day_offset,0,0];put(row,17,stop.delta_mass_t)
        return row

    def set_timetable(self,args):
        self.prepare_timetable()
        if args.course_id not in {w.string(c.contents[0].value) for c in self.p.courses()}:raise APIError('COURSE_NOT_FOUND','Timetable rows need an existing Course.',args.course_id)
        known=station_items(self.p.data['stations']);previous=float('-inf');rows=[];count=len(args.stops)
        self.requested_rows+=count;self.requested_connections+=sum(len(stop.connections) for stop in args.stops)
        if self.requested_rows>10000 or self.requested_connections>10000:raise APIError('GENERATION_SIZE','One batch supports at most 10000 requested timetable rows and 10000 connections.')
        from .operation_bundle import validate_timetable
        validate_timetable(args)
        for index,stop in enumerate(args.stops):
            if stop.station_sign not in known:raise APIError('TIMETABLE_STATION','Unknown exact station sign.',stop.station_sign)
            if stop.arrival is None and stop.departure is None:raise APIError('TIMETABLE_TIME','Each generated stop needs at least one time.',{'course':args.course_id,'index':index})
            for field in ['arrival','departure']:
                value=getattr(stop,field)
                if value is not None:
                    current=absolute_time(value,getattr(stop,field+'_day_offset'))
                    if current<previous:raise APIError('TIMETABLE_ORDER','Arrival/departure times must be chronological.',{'course':args.course_id,'index':index})
                    previous=current
            if stop.stop_at_station and stop.arrival and stop.departure and absolute_time(stop.departure,stop.departure_day_offset)-absolute_time(stop.arrival,stop.arrival_day_offset)<stop.dwell_s:raise APIError('TIMETABLE_DWELL','Scheduled dwell is shorter than dwell_s.',{'course':args.course_id,'index':index})
            row=self.make_timetable_row(args.course_id,index,count,stop)
            rows.append((args.course_id+'#'+str(index),row))
        table=self.p.table();table={key:row for key,row in table.items() if w.string(row.contents[1].value)!=args.course_id};table.update(rows)
        root=self.p.data['timetable'];root.contents=[w.ar.TypedValue(b'i',len(table))]
        for key,row in table.items():root.contents.extend([w.ar.TypedValue(b'@',text(row,key)),w.ar.TypedValue(b'@',row)])
        self.changed_timetables.add(args.course_id)
        return {'course_id':args.course_id,'timetable_rows':count,'first_departure':args.stops[0].departure,'last_arrival':args.stops[-1].arrival,
            'first_departure_day_offset':args.stops[0].departure_day_offset,'last_arrival_day_offset':args.stops[-1].arrival_day_offset}

    def finalize(self):
        if not self.changed_timetables:return
        from .native_records import timetable_record
        ids={w.string(c.contents[0].value) for c in self.p.courses()};stations={}
        rows=[timetable_record(key,obj) for key,obj in self.p.table().items()]
        for row in rows:stations.setdefault(row['course_id'],set()).add(row['station_sign'])
        for row in rows:
            if row['course_id'] not in self.changed_timetables:continue
            reference=row['interval_reference_course_id']
            if reference not in ['','0','-1'] and reference not in ids:raise APIError('INTERVAL_REFERENCE','Missing exact interval reference Course.',reference)
            for connection in row['connections']:
                target=connection['target_course_id']
                if target=='0':continue 
                if target not in ids:raise APIError('CONNECTION_COURSE','Connection references a missing exact Course.',target)
                if connection['target_station_sign'] not in stations.get(target,set()):raise APIError('CONNECTION_STATION','Connection target Course has no matching station timetable row.',connection)

    def prepare_courses(self):
        if self.upgraded_courses:return
        count=upgrade_course_records(self.p.data['courses'])
        if count:self.migrations['OTCourse']=count
        self.upgraded_courses=True

    def course_bindings(self,train=None,itineraries=None):
        if train is not None and train not in {w.string(obj.contents[0].value) for obj in train_items(self.p.data['trains'])}:
            raise APIError('VEHICLE_BINDING','Course references a missing exact formation name.',train)
        if itineraries is not None:
            if len(set(itineraries))!=len(itineraries):raise APIError('DUPLICATE_ITINERARY','A Course preference list must not repeat an Itinerary.')
            destinations={w.string(obj.contents[1].value) for obj in w.elements(self.p.data['dest'].contents[0].value)}
            missing=[name for name in itineraries if name not in destinations]
            if missing:raise APIError('ITINERARY_BINDING','Course references missing exact Itinerary names.',missing)

    def update_courses(self,args):
        self.course_update_targets+=len(args.course_ids)
        if self.course_update_targets>10000:raise APIError('GENERATION_SIZE','One draft supports at most 10000 requested Course update targets.')
        self.prepare_courses();items=self.p.courses();lookup={w.string(obj.contents[0].value):obj for obj in items}
        if len(lookup)!=len(items):raise APIError('DUPLICATE_COURSE_ID','Course IDs are ambiguous in the selected catalog.')
        missing=[cid for cid in args.course_ids if cid not in lookup]
        if missing:raise APIError('COURSE_NOT_FOUND','Selected Courses do not exist.',{'course_ids':missing[:50],'count':len(missing)})
        self.course_bindings(args.train,args.itineraries);changes=[]
        fields=args.model_fields_set-{'kind','course_ids','invert_enabled'}
        if args.invert_enabled:fields=fields|{'enabled'}
        for cid in args.course_ids:
            obj=lookup[cid];before=course_record(obj)
            for field,(index,position) in COURSE_SCALARS.items():
                value=getattr(args,field)
                if value is not None:obj.contents[index].values[position]=int(value) if field=='enabled' else value
            for field,index in COURSE_STRINGS.items():
                value=getattr(args,field)
                if value is not None:set_text(obj,index,value)
            if args.entering_speed_kmh is not None:put(obj,1,args.entering_speed_kmh/3.6)
            if args.spacing_mode is not None:put(obj,8,SPACING_CODES[args.spacing_mode])
            if args.invert_enabled:put(obj,5,int(not before['enabled']))
            names=list(args.itineraries) if args.itineraries is not None else list(before['itineraries'])
            if args.itinerary_move is not None:
                move=args.itinerary_move
                if names.count(move.name)!=1:raise APIError('ITINERARY_ORDER','Move requires exactly one matching Itinerary in every selected Course.',{'course_id':cid,'itinerary':move.name})
                names.remove(move.name);names.insert(min(move.priority-1,len(names)),move.name)
            if args.itineraries is not None or args.itinerary_move is not None:put(obj,2,self.d.array([text(obj,name) for name in names]))
            after=course_record(obj);keys=(fields-{'itinerary_move'})|({'itineraries','itinerary_preferences'} if args.itinerary_move or args.itineraries is not None else set())
            changes.append({'course_id':cid,'fields':{field:{'before':before[field],'after':after[field]} for field in sorted(keys) if before[field]!=after[field]}})
        return {'courses_updated':len(changes),'courses_changed':sum(bool(row['fields']) for row in changes),'course_ids':list(args.course_ids),'course_changes':changes,'timetable_rows_changed':0}

    def define_course(self,args):
        self.requested_courses+=1
        if self.requested_courses>1000:raise APIError('GENERATION_SIZE','One draft supports at most 1000 requested Course definitions, including imported and cloned Courses.')
        self.prepare_courses();self.course_bindings(args.train,args.itineraries)
        courses=self.p.courses();course=self.template('OTCourse',courses,args.template_id)
        for slot,value in [(0,args.course_id),(3,args.train),(4,args.speed_type),(10,args.description),(11,args.comment),(13,args.train_number),(14,args.course_type)]:set_text(course,slot,value)
        put(course,2,self.d.array([text(course,name) for name in args.itineraries]));put(course,5,int(args.enabled));put(course,6,args.acceleration_percent)
        put(course,1,args.entering_speed_kmh/3.6);put(course,9,args.delayed_acceleration_percent);course.contents[7].values[0]=args.output_offset_m
        put(course,8,SPACING_CODES[args.spacing_mode]);course.contents[12].values=[args.additional_reservation_time_s,args.additional_release_time_s]
        replaced=self.store(course_array(self.p.data['courses']),course,args.course_id,0,args.replace_existing)
        table=self.set_timetable(args)
        return {**table,'train':args.train,'itineraries':list(args.itineraries),'enabled':args.enabled,'replaced':replaced}

    def service_pattern(self,args):
        from .operation_bundle import expand_pattern
        generated=[self.define_course(course) for course in expand_pattern(args)]
        return {'pattern_prefix':args.id_prefix,'courses_generated':len(generated),'course_ids':[row['course_id'] for row in generated],
            'first_departure':args.first_departure,'interval_s':args.interval_s,'timetable_rows':sum(row['timetable_rows'] for row in generated)}


class Generation:
    def __init__(self,service):self.service=service

    def generate(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        from .drafts import DraftManager
        from .models import Stage,MAX_BATCH_OPERATIONS
        from .engine_diagrams import requested_rows
        requested_rows(args)
        changes=[]
        for field,kind in [('stations','define_station'),('engines','define_engine'),('categories','define_category'),('rolling_stock_imports','import_rolling_stock_xml'),('formations','define_formation'),('shuntings','define_shunting'),('routes','define_route'),('route_protection_updates','set_route_protection'),('paths','define_path'),('itineraries','define_itinerary'),('courses','define_course'),('patterns','service_pattern'),('timetables','set_timetable'),('course_updates','update_courses')]:
            changes.extend({**item.model_dump(exclude_unset=kind in ['set_route_protection','update_courses']),'kind':kind} for item in getattr(args,field))
        changes.extend(item.model_dump() for item in args.network_operations)
        changes.extend(item.model_dump() for item in args.course_lifecycle)
        changes.extend({'kind':item.kind,**item.model_dump(exclude_unset=True)} for item in args.rolling_stock_operations)
        
        
        changes.extend({'kind':item.kind,**item.model_dump(exclude_unset=True)} for item in args.timetable_operations)
        stock_targets=sum(len(item.renames) if hasattr(item,'renames') else len(getattr(item,'names',[])) for item in args.rolling_stock_operations)
        if stock_targets>10000:raise APIError('GENERATION_SIZE','At most 10000 rolling-stock edit targets are supported per draft.')
        if not changes:raise APIError('EMPTY_GENERATION','Supply at least one entity or service pattern.')
        if len(changes)>MAX_BATCH_OPERATIONS:raise APIError('GENERATION_SIZE','One atomic batch supports at most 1000 definition/update operations before pattern expansion.',{'definition_update_operations':len(changes)})
        update_targets=sum(len(item.course_ids) for item in args.course_updates)+sum(len(item.renames) if item.kind=='rename_courses' else len(item.course_ids) for item in args.course_lifecycle)
        if update_targets>10000:raise APIError('GENERATION_SIZE','One batch supports at most 10000 requested Course update targets.',{'course_update_targets':update_targets})
        courses=len(args.courses)+sum(pattern.count for pattern in args.patterns)
        rows=sum(len(course.stops) for course in args.courses)+sum(pattern.count*len(pattern.stops) for pattern in args.patterns)+sum(len(table.stops) for table in args.timetables)
        connections=sum(len(stop.connections) for course in [*args.courses,*args.timetables] for stop in course.stops)+sum(pattern.count*sum(len(stop.connections) for stop in pattern.stops) for pattern in args.patterns)
        if courses>1000 or rows>10000 or connections>10000:raise APIError('GENERATION_SIZE','One batch supports at most 1000 Courses, 10000 timetable rows and 10000 connections.',{'courses':courses,'rows':rows,'connections':connections})
        explicit_targets=sum(len(getattr(item,'rows',[])) if hasattr(item,'rows') else len(item.stops) if item.kind=='insert_timetable_rows' else 1 if item.kind=='edit_timetable_connections' else 0 for item in args.timetable_operations)
        explicit_connections=sum(len(item.append)+len(item.updates) if item.kind=='edit_timetable_connections' else sum(len(stop.connections) for stop in item.stops) if item.kind=='insert_timetable_rows' else len(item.rows)*len(item.connections or []) if item.kind=='update_timetable_rows' else 0 for item in args.timetable_operations)
        if rows+explicit_targets>10000 or connections+explicit_connections>10000:raise APIError('GENERATION_SIZE','Definitions and timetable operations share 10000 requested row/connection budgets.')
        result=DraftManager(self.service).stage(Stage(project=args.project,run_file=args.run_file,label=args.label,changes=changes,validation_scope='generation'))
        from .archive import Project
        p=Project(self.service.root,result['draft_project']);csv_text=io.StringIO(newline='');writer=csv.writer(csv_text)
        writer.writerow(['course_id','index','station_sign','arrival','departure','arrival_day_offset','departure_day_offset','track_id','train','itineraries','spacing_mode','spacing_mode_code','additional_reservation_time_s','additional_release_time_s'])
        services={row['course_id']:row for row in p.catalog('services')}
        for row in p.catalog('timetable'):
            service=services.get(row['course_id'],{});writer.writerow([row['course_id'],row['index'],row['station_sign'],row['arrival'],row['departure'],row['arrival_day_offset'],row['departure_day_offset'],row['track_id'],service.get('train',''),';'.join(service.get('itineraries',[])),service.get('spacing_mode',''),service.get('spacing_mode_code',''),service.get('additional_reservation_time_s',''),service.get('additional_release_time_s','')])
        preview=Path(result['draft_project']).parent/'timetable-preview.csv';preview.write_text(csv_text.getvalue(),encoding='utf-8-sig')
        update_rows=[row for item in result['changes'] if item['kind']=='update_courses' for row in item['course_changes']]
        update_preview=None
        if update_rows:
            update_preview=Path(result['draft_project']).parent/'course-updates.json';update_preview.write_text(json.dumps(update_rows,ensure_ascii=False,indent=2),encoding='utf8')
        from .course_lifecycle import KINDS as LIFECYCLE_KINDS
        from .itinerary_controls import KINDS as ITINERARY_KINDS
        network_rows=[item for item in result['changes'] if item['kind'] in ITINERARY_KINDS|{'delete_all_paths'}];network_preview=None
        if network_rows:
            network_preview=Path(result['draft_project']).parent/'network-changes.json';network_preview.write_text(json.dumps(network_rows,ensure_ascii=False,indent=2),encoding='utf8')
        lifecycle_rows=[item for item in result['changes'] if item['kind'] in LIFECYCLE_KINDS];lifecycle_preview=None
        if lifecycle_rows:
            lifecycle_preview=Path(result['draft_project']).parent/'course-lifecycle.json';lifecycle_preview.write_text(json.dumps(lifecycle_rows,ensure_ascii=False,indent=2),encoding='utf8')
        from .timetable_editing import KINDS as TIMETABLE_KINDS
        timetable_diffs=[item for item in result['changes'] if item['kind'] in TIMETABLE_KINDS];timetable_diff_file=None
        if timetable_diffs:
            timetable_diff_file=Path(result['draft_project']).parent/'timetable-changes.json';timetable_diff_file.write_text(json.dumps(timetable_diffs,ensure_ascii=False,indent=2),encoding='utf8')
        from .timetable_exchange import render
        stock_changes=[item for item in result['changes'] if item['kind'] in STOCK_KINDS|XML_STOCK_KINDS];stock_preview=None
        if stock_changes:
            stock_preview=Path(result['draft_project']).parent/'rolling-stock-changes.json';stock_preview.write_text(json.dumps(stock_changes,ensure_ascii=False,indent=2),encoding='utf8')
        native_export=None;native_export_error=None;export_warnings=[]
        try:
            native_text,export_warnings=render(p.catalog('timetable'),'opentrack_17');native_export=Path(result['draft_project']).parent/'timetable-opentrack-17.txt';native_export.write_text(native_text,encoding='ascii',newline='')
        except APIError as error:native_export_error=error.as_dict()
        for item in result['changes']:
            if item['kind'] in ITINERARY_KINDS:
                if 'shared_profile_changes' in item:
                    details=item.pop('shared_profile_changes');item['shared_profile_change_count']=len(details)
                    item['shared_profile_changes_preview']=[{'name':row['name'],'document':row['document'],'before_row_count':len(row['before_margins']),'after_row_count':len(row['after_margins'])} for row in details[:10]]
                    item['shared_profile_changes_truncated']=len(details)>10
                for field in ['course_replacements','dependencies','names','removed_inactive','added_active','paths','reversals','before_margins','after_margins','before_margin_aliases','after_margin_aliases','shared_profiles_before','shared_profiles_after','margin_commands','imports']:
                    if field in item:
                        values=item.pop(field);item[field+'_count']=len(values);item[field+'_preview']=values[:10];item[field+'_truncated']=len(values)>10
                        if field in ['before_margin_aliases','after_margin_aliases']:item[field+'_preview']=[{'indices_preview':group[:20],'reference_count':len(group),'truncated':len(group)>20} for group in values[:10]]
                        if field=='margin_commands':item[field+'_preview']=[{**row,'resulting_indices':row['resulting_indices'][:20],'resulting_reference_count':len(row['resulting_indices'])} if 'resulting_indices' in row else row for row in values[:10]]
                for field in ['before','after']:
                    if field in item:
                        values=item[field].pop('paths');item[field].update(path_count=len(values),paths_preview=values[:10],paths_truncated=len(values)>10)
            if item['kind']=='delete_all_paths':
                for field in ['paths_deleted','itineraries_deleted','dependent_courses']:
                    values=item.pop(field);item[field+'_preview']=values[:10];item[field+'_truncated']=len(values)>10
            if item['kind'] in STOCK_KINDS|XML_STOCK_KINDS:
                for field in ['stock_changes','renames','dependencies','names','curve_text_imports','point_command_results','xml_warnings']:
                    if field in item:
                        from .stock_maintenance import compact_preview
                        values=item.pop(field);item[field+'_preview']=[compact_preview(value) for value in values[:10]];item[field+'_truncated']=len(values)>10
                if 'ignored_fields' in item:
                    ignored=item.pop('ignored_fields');item['ignored_field_count']=len(ignored);item['ignored_fields_preview']=dict(list(ignored.items())[:20])
                if item.get('cascade'):
                    cascade=item.pop('cascade');item['cascade_summary']={key:cascade[key] for key in ['entity','records_deleted','courses_deleted','references_changed'] if key in cascade}
            if item['kind']=='update_courses':
                course_diffs=item.pop('course_changes');item['course_changes_preview']=course_diffs[:10];item['course_changes_truncated']=len(course_diffs)>10
            if 'course_ids' in item and len(item['course_ids'])>20:item['course_ids_preview']=item.pop('course_ids')[:20];item['course_ids_truncated']=True
            if item['kind'] in LIFECYCLE_KINDS:
                for field in ['renames','dependencies','itinerary_resets']:
                    if field in item:
                        details=item.pop(field);item[field+'_preview']=details[:10];item[field+'_truncated']=len(details)>10
            if item['kind'] in ['create_timetable_skeletons','create_interval_courses']:
                from .stock_maintenance import compact_preview
                creations=item.pop('creations');item['creations_preview']=[compact_preview(c) for c in creations[:10]];item['creations_truncated']=len(creations)>10
            if item['kind']=='plan_timetable_connections':
                from .stock_maintenance import compact_preview
                actions=item.pop('connection_actions');item['connection_actions_preview']=[compact_preview(row) for row in actions[:10]];item['connection_actions_truncated']=len(actions)>10
            if item['kind'] in TIMETABLE_KINDS:
                if 'xml_warnings' in item:
                    values=item.pop('xml_warnings');item['xml_warnings_preview']=values[:10];item['xml_warnings_truncated']=len(values)>10
                details=item.pop('timetable_changes',[]);item['timetable_changes_preview']=copy.deepcopy(details[:10]);item['timetable_changes_truncated']=len(details)>10
                if item['kind']=='create_interval_courses':
                    from .stock_maintenance import compact_preview
                    item['timetable_changes_preview']=[compact_preview(row) for row in item['timetable_changes_preview']]
                for row in item['timetable_changes_preview']:
                    connection_diff=row.get('fields',{}).get('connections')
                    if connection_diff:
                        for side in ['before','after']:
                            if isinstance(connection_diff[side],list):
                                values=connection_diff[side];connection_diff[side+'_count']=len(values);connection_diff[side]=values[:3];connection_diff[side+'_truncated']=len(values)>3
                if 'unbound_courses' in item and len(item['unbound_courses'])>20:item['unbound_courses_preview']=item.pop('unbound_courses')[:20];item['unbound_courses_truncated']=True
        result['validation']=copy.deepcopy(result['validation'])
        for warning in result['validation']['warnings']:
            if warning['code']=='NATIVE_RUN_REQUIRED':warning['code']='NATIVE_RUN_NOT_PERFORMED';warning['details']='Generation is checked statically. A native run is needed only for a separate requested simulation-acceptance claim.'
        imported=[item for item in result['changes'] if item['kind'] in XML_STOCK_KINDS]
        imported_trailers=sum(item['counts'].get('trailer_records_stored',0) for item in imported)
        intervals=[item for item in result['changes'] if item['kind']=='create_interval_courses']
        connection_plans=[item for item in result['changes'] if item['kind']=='plan_timetable_connections']
        timetable_imports=[item for item in result['changes'] if item['kind'] in ['import_timetable_text','import_timetable_xml']]
        return {**result,'generation_summary':{'engines':len(args.engines)+sum(item['counts'].get('engines_stored',0) for item in imported),'categories':len(args.categories),'formations':len(args.formations)+sum(item['counts'].get('formations_stored',0) for item in imported),'rolling_stock_imports':len(imported),'trailers':sum(item.count for formation in args.formations for item in formation.trailers)+imported_trailers,'shuntings':len(args.shuntings),'routes':len(args.routes),'route_protection_updates':len(args.route_protection_updates),'paths':len(args.paths),'itineraries':len(args.itineraries),'courses':courses+sum(item['courses_generated'] for item in intervals)+sum(item['courses_created'] for item in timetable_imports),'timetable_rows':rows+sum(item.get('timetable_rows_created',0) for item in result['changes'])+sum(item['imported_rows'] for item in timetable_imports),'connections':connections+sum(item['connections_created'] for item in [*intervals,*connection_plans])+sum(item['imported_connections'] for item in timetable_imports)},
            'rolling_stock_update_targets':stock_targets,'rolling_stock_changes_json':str(stock_preview) if stock_preview else None,
            'course_update_targets':update_targets,'course_updates_json':str(update_preview) if update_preview else None,'course_lifecycle_json':str(lifecycle_preview) if lifecycle_preview else None,'network_changes_json':str(network_preview) if network_preview else None,
            'timetable_changes_json':str(timetable_diff_file) if timetable_diff_file else None,'timetable_opentrack_text':str(native_export) if native_export else None,'native_timetable_export_error':native_export_error,'native_timetable_export_warning_count':len(export_warnings),'native_timetable_export_warnings':export_warnings[:20],
            'timetable_preview_csv':str(preview),'native_simulation_started':False,'generation_task_boundary':'Static native-format generation, binding/chronology checks and exports complete the information-generation task; simulation trials are separate and only needed when requested.',
            'verification_scope':'Atomic original-format generation, bindings and static checks; no replacement simulator or full-run acceptance.'}
