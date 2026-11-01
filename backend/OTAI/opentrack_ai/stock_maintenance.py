"""Partial edits and exact identity maintenance for original rolling-stock data."""
import copy
from collections import Counter

from .stock_versions import arrays
from .archive import APIError,w
from .drafts import set_text
from .native_records import native_string
from .rolling_stock import (ENGINE_SCALARS,ENGINE_FLAGS,TRAIN_SCALARS,CATEGORY_SCALARS,
    CATEGORY_FLAGS,CATEGORY_TABLES,set_scalars,engine_record,formation_record,category_record,peak_power_kw)
from .course_lifecycle import CourseLifecycleOperations,string_slot,write_slot
from opentrack_train_schema import engine_items,train_items


KINDS={'update_engines','update_formations','update_categories','rename_engines',
    'rename_formations','rename_categories','delete_engines','delete_formations','delete_categories','edit_engine_diagrams','migrate_rolling_stock'}
RECORDS={'engines':engine_record,'formations':formation_record,'categories':category_record}


def put(obj,index,value):obj.contents[index].values[0]=value


def difference(before,after):
    return {key:{'before':before.get(key),'after':value} for key,value in after.items() if before.get(key)!=value}


def compact_preview(value):
    """Keep full native arrays in artifacts and bound nested response previews."""
    if isinstance(value,list):
        items=[compact_preview(v) for v in value[:3]]
        return {'count':len(value),'items_preview':items,'truncated':True} if len(value)>3 else items
    if isinstance(value,dict):return {key:compact_preview(v) for key,v in value.items()}
    return value


class StockOperations:
    def __init__(self,operations):self.o=operations;self.p=operations.p;self.d=operations.d

    def array(self,entity):
        if entity=='engines':return self.p.data['depot'],1
        return self.p.data['trains'].contents[3 if entity=='formations' else 1].value,0 if entity=='formations' else 1

    def select(self,entity,names,count=True):
        if len(names)!=len(set(names)):raise APIError('DUPLICATE_STOCK_NAME','Selection contains duplicate names.')
        array,index=self.array(entity);items=w.elements(array);lookup={string_slot(obj,index):obj for obj in items}
        if len(lookup)!=len(items):raise APIError('DUPLICATE_STOCK_NAME','Existing native names are ambiguous.',entity)
        missing=[name for name in names if name not in lookup]
        if missing:raise APIError('STOCK_NOT_FOUND','Selected exact native names do not exist.',{'entity':entity,'names':missing})
        if count:self.o.stock_update_targets+=len(names)
        if self.o.stock_update_targets>10000:raise APIError('GENERATION_SIZE','One draft supports at most 10000 rolling-stock edit targets, including cascades.')
        return array,index,lookup

    def apply(self,args):
        if args.kind=='migrate_rolling_stock':return {'entities':args.entities,'migrations':self.o.prepare_stock_versions(args.entities),'stock_changes':[]}
        if args.kind=='edit_engine_diagrams':
            from .engine_diagrams import edit_engine_diagrams
            return edit_engine_diagrams(self,args)
        entity=args.kind.split('_',1)[1]
        if args.kind.startswith('update_'):return self.update(entity,args)
        if args.kind.startswith('rename_'):return self.rename(entity,args)
        return self.delete(entity,args)

    def update(self,entity,args):
        array,index,lookup=self.select(entity,args.names);changes=[];planned=[]
        for name in args.names:
            old=lookup[name];obj=copy.deepcopy(old);before=RECORDS[entity](old)
            getattr(self,'edit_'+entity)(obj,args)
            after=RECORDS[entity](obj)
            
            if entity=='engines' and (args.traction_points is not None or args.nominal_power_kw is not None or args.tractive_effort_diagrams is not None):
                before=engine_record(old,True);after=engine_record(obj,True)
            planned.append((old,obj));changes.append({'entity':entity,'name':name,'fields':difference(before,after)})
        replacements={id(old):obj for old,obj in planned}
        w.set_elements(array,[replacements.get(id(obj),obj) for obj in w.elements(array)])
        return {'entity':entity,'names':args.names,'records_updated':len(changes),
            'records_changed':sum(bool(c['fields']) for c in changes),'stock_changes':changes}

    def edit_engines(self,obj,args):
        direct={'mass_t':(2,1),'length_m':(2,2),'rotating_mass_factor':(2,3),'number_of_axles':(2,4),'cw_value':(2,5),
            'adhesion_mass_t':(3,0),'maximum_force_kn':(6,0),'maximum_speed_kmh':(7,0),'driven_axles':(9,0),'traction_motors':(10,0)}
        set_scalars(obj,args,{**direct,**ENGINE_SCALARS})
        for field,bit in ENGINE_FLAGS.items():
            value=getattr(args,field)
            if value is not None:put(obj,11,obj.contents[11].value|bit if value else obj.contents[11].value&~bit)
        if {'mass_t','adhesion_mass_t'}&args.model_fields_set and obj.contents[3].value>obj.contents[2].values[1]:
            raise APIError('ENGINE_MASS','Adhesion mass cannot exceed the resulting total mass.')
        if {'number_of_axles','driven_axles'}&args.model_fields_set and obj.contents[9].value>obj.contents[2].values[4]:
            raise APIError('ENGINE_AXLES','Driven axles cannot exceed the resulting total axles.')
        if len(obj.contents)>17 and {'minimum_force_kn','maximum_force_kn'}&args.model_fields_set and obj.contents[17].value>obj.contents[6].value:
            raise APIError('ENGINE_FORCE','Minimum force cannot exceed the resulting maximum force.')
        curves=w.elements(obj.contents[16].value) if obj.contents[16].value else []
        if args.tractive_effort_diagrams is not None:
            from .engine_diagrams import replace_diagrams,curve_power_kw
            curves=replace_diagrams(self.o,obj,args.tractive_effort_diagrams);put(obj,8,args.maximum_power_kw if args.maximum_power_kw is not None else curve_power_kw(curves))
        replacing=args.traction_points is not None or args.nominal_power_kw is not None
        if replacing:
            if len(curves)>1:raise APIError('ENGINE_DIAGRAM_SELECTION','A point/proxy edit requires a single diagram. Multiple saved diagrams are preserved; use a separately audited diagram-specific operation.')
            vmax=obj.contents[7].value;fmax=obj.contents[6].value
            if args.traction_points is not None:
                points=[(p.speed_kmh,p.force_kn) for p in args.traction_points];source='explicit user-supplied traction points'
            else:
                points=[(v,min(fmax,round(args.nominal_power_kw*3.6/max(v,1)))) for v in sorted({0,vmax,*range(0,vmax+1,50)})]
                source='uncalibrated constant-power engineering proxy'
            self.check_traction(points,vmax,fmax)
            diagram=copy.deepcopy(curves[0] if curves else self.d.template('OTDDiagram'))
            diagram.contents[0].values[:2]=[vmax,fmax];rows=[]
            for speed,force in points:
                row=copy.deepcopy(self.d.template('OTDPoint'));row.contents[0].values=[speed,force,1];rows.append(row)
            put(diagram,1,self.d.array(rows));set_text(diagram,6,'Edited: '+source)
            
            put(obj,16,self.d.array([diagram]));put(obj,8,args.maximum_power_kw if args.maximum_power_kw is not None else args.nominal_power_kw or peak_power_kw(points));curves=[diagram]
            from .engine_diagrams import account_rows
            account_rows(self.o,curves)
        if {'maximum_speed_kmh','maximum_force_kn'}&args.model_fields_set or args.tractive_effort_diagrams is not None:
            if not curves:raise APIError('TRACTION_COVERAGE','The resulting Engine requires a tractive-effort diagram.')
            from .engine_diagrams import point_rows
            if any(force>obj.contents[6].value for diagram in curves for _,force,_ in point_rows(diagram,1)):raise APIError('TRACTION_FORCE','Preserved diagram forces exceed the resulting Engine maximum.')
            if 'maximum_speed_kmh' in args.model_fields_set and max([speed for diagram in curves for speed,_,_ in point_rows(diagram,1)]+[0])<obj.contents[7].value:
                raise APIError('TRACTION_COVERAGE','The resulting Engine speed exceeds every saved diagram.')

    def check_traction(self,points,vmax,fmax):
        if len(points)<2 or points[0][0]!=0 or points[-1][0]<vmax or any(b[0]<=a[0] for a,b in zip(points,points[1:])):
            raise APIError('TRACTION_COVERAGE','Traction speeds must increase from zero through the resulting Engine maximum.')
        if points[0][1]<=0 or any(force<0 or force>fmax for _,force in points):
            raise APIError('TRACTION_FORCE','Traction forces must fit the resulting maximum; starting force must be positive.')

    def edit_formations(self,obj,args):
        set_scalars(obj,args,{**TRAIN_SCALARS,'maximum_acceleration_mps2':(4,0)})
        for field,index in [('resistance_coefficients_excl',5),('resistance_coefficients_incl',7)]:
            if getattr(args,field) is not None:obj.contents[index].values=list(getattr(args,field))
        for field,bit in [('use_maximum_drawbar_force',1),('use_minimum_time_to_hold_speed',2)]:
            value=getattr(args,field)
            if value is not None:put(obj,15,obj.contents[15].value|bit if value else obj.contents[15].value&~bit)
        if args.category is not None:
            self.select('categories',[args.category],count=False);write_slot(obj,3,args.category)
        consist_changed=args.engines is not None or args.trailers is not None
        if consist_changed:self.consist(obj,args)
        brake_changed=args.braking_points is not None or args.braking_deceleration_mps2 is not None
        if brake_changed or consist_changed:
            engines={string_slot(e,1):e for e in engine_items(self.p.data['depot'])}
            refs=arrays(obj.contents[2].values[1]);trailers=arrays(obj.contents[2].values[2])
            missing=[string_slot(e,0) for e in refs if string_slot(e,0) not in engines]
            if missing:raise APIError('ENGINE_BINDING','Formation references missing exact Engine names.',missing)
            speeds=[engines[string_slot(ref,0)].contents[7].value for ref in refs]+[t.contents[4].value for t in trailers]
            if not speeds:raise APIError('FORMATION_EMPTY','A formation must contain physical units.')
            vmax=max(speeds)
            if brake_changed:
                values=[(p.speed_kmh,p.deceleration_mps2,p.secondary_deceleration_mps2 or p.deceleration_mps2) for p in args.braking_points] if args.braking_points is not None else [(v,args.braking_deceleration_mps2,args.braking_deceleration_mps2) for v in sorted({0,vmax})]
                if values[0][0]!=0 or values[-1][0]<vmax or any(b[0]<=a[0] for a,b in zip(values,values[1:])):
                    raise APIError('BRAKING_COVERAGE','Braking speeds must increase from zero through all resulting unit limits.')
                wrapper=copy.deepcopy(obj.contents[2].values[0] or self.d.template('OTDecelerationArray'));rows=[]
                for speed,primary,secondary in values:
                    row=copy.deepcopy(self.d.template('OTDeceleration'));row.contents[0].values=[speed,-primary,-secondary];rows.append(row)
                put(wrapper,0,self.d.array(rows));obj.contents[2].values[0]=wrapper;obj.contents[12].values[0]=0
                obj.contents[1].values[2]=-values[0][1] if all(row[1]==values[0][1] for row in values) else float('nan')
            elif obj.contents[12].values[0]==0:
                points=w.elements(obj.contents[2].values[0].contents[0].value)
                if not points or points[-1].contents[0].values[0]<vmax:raise APIError('BRAKING_COVERAGE','Preserved braking table does not cover the new consist. Supply explicit braking data.')

    def consist(self,obj,args):
        old_engines=arrays(obj.contents[2].values[1]);old_trailers=arrays(obj.contents[2].values[2])
        keep_engines=old_engines if args.engines is None else [];keep_trailers=old_trailers if args.trailers is None else []
        count=len(keep_engines)+len(keep_trailers)+sum(ref.count for ref in args.engines or [])+sum(t.count for t in args.trailers or [])
        powered=len(keep_engines)+sum(ref.count for ref in args.engines or [])
        if powered<1 or powered>64 or count>1024:raise APIError('FORMATION_SIZE','Consist must have 1-64 powered references and at most 1024 records.')
        occupied=[e.contents[1].value for e in keep_engines]+[t.contents[3].values[1] for t in keep_trailers]
        occupied += [p for spec in [*(args.engines or []),*(args.trailers or [])] for p in spec.positions or []]
        if len(occupied)!=len(set(occupied)) or any(p<1 or p>count for p in occupied):
            raise APIError('FORMATION_POSITIONS','Explicit and preserved positions must be unique within the resulting consist. Edit both lists if shrinking requires repositioning.')
        free=iter(p for p in range(1,count+1) if p not in occupied);engines=list(keep_engines);trailers=list(keep_trailers)
        for spec in args.engines or []:
            for position in spec.positions or [next(free) for _ in range(spec.count)]:
                ref=copy.deepcopy(self.d.template('OTTrainEngine'));write_slot(ref,0,spec.engine_name);put(ref,1,position);engines.append(ref)
        if args.trailers is not None:
            from .native_records import upgrade_records
            upgraded=upgrade_records(self.p.data['trains'],'OTTrailer')
            if upgraded:self.o.migrations['OTTrailer']=self.o.migrations.get('OTTrailer',0)+upgraded
        for spec in args.trailers or []:
            for position in spec.positions or [next(free) for _ in range(spec.count)]:
                trailer=copy.deepcopy(self.d.template('OTTrailer'));write_slot(trailer,1,spec.name)
                trailer.contents[2].values[1:5]=[spec.mass_t,spec.length_m,spec.rotating_mass_factor,spec.number_of_axles]
                if spec.cw_value is not None:trailer.contents[2].values[5]=spec.cw_value
                trailer.contents[3].values=[0,position,spec.number_of_items]
                for index,value in [(4,spec.maximum_speed_kmh),(5,spec.power_loss_kw),(6,spec.power_loss_delta_load_factor_kw_per_t)]:put(trailer,index,value)
                trailers.append(trailer)
        if args.engines is not None:obj.contents[2].values[1]=self.d.array(engines)
        if args.trailers is not None:obj.contents[2].values[2]=self.d.array(trailers)

    def edit_categories(self,obj,args):
        from .rolling_stock import set_category_extended
        set_category_extended(obj,args,self.d)
        set_scalars(obj,args,CATEGORY_SCALARS)
        for field,bit in CATEGORY_FLAGS.items():
            value=getattr(args,field)
            if value is not None:obj.contents[0].values[1]=obj.contents[0].values[1]|bit if value else obj.contents[0].values[1]&~bit
        for field,(index,wrapper_type,point_type) in CATEGORY_TABLES.items():
            values=getattr(args,field)
            if values is None:continue
            if field=='delay_priorities':
                if any(b.delay_s<=a.delay_s for a,b in zip(values,values[1:])):raise APIError('CATEGORY_DISTRIBUTION','Delay-priority thresholds must increase strictly.')
            elif values and (abs(sum(v.probability_percent for v in values)-100)>.001 or any(b.minimum<a.maximum for a,b in zip(values,values[1:]))):
                raise APIError('CATEGORY_DISTRIBUTION','Probability intervals must be ordered, non-overlapping and sum to 100 percent.')
            wrapper=copy.deepcopy(obj.contents[index].value or self.d.template(wrapper_type));rows=[]
            for value in values:
                row=copy.deepcopy(self.d.template(point_type));row.contents[0].values=[value.delay_s,value.priority] if field=='delay_priorities' else [value.minimum,value.maximum,value.probability_percent];rows.append(row)
            put(wrapper,0,self.d.array(rows));put(obj,index,wrapper)
        result=category_record(obj);touched=args.model_fields_set
        if {'initial_delay_mean_s','initial_delay_maximum_s'}&touched and result['initial_delay_mean_s']>result['initial_delay_maximum_s']:
            raise APIError('CATEGORY_DELAY','Resulting initial maximum delay must be at least the mean.')
        if {'delay_limit_small_s','delay_limit_medium_s','delay_limit_large_s'}&touched and not result['delay_limit_small_s']<=result['delay_limit_medium_s']<=result['delay_limit_large_s']:
            raise APIError('CATEGORY_DELAY','Resulting delay thresholds must be ordered.')
        for flag,table in [('use_on_time_performance','on_time_performance'),('use_delayed_performance','delayed_performance')]:
            if {flag,table}&touched and result[flag] and not result[table]:raise APIError('CATEGORY_DISTRIBUTION','An enabled performance distribution needs nonempty intervals.',table)

    def references(self,entity):
        if entity=='engines':
            return [(ref,0,'formation_engine',string_slot(train,0)) for train in train_items(self.p.data['trains']) for ref in arrays(train.contents[2].values[1])]
        if entity=='formations':return [(course,3,'course_train',string_slot(course,0)) for course in self.p.courses()]
        return [(train,3,'formation_category',string_slot(train,0)) for train in train_items(self.p.data['trains'])]

    def hidden_categories(self):
        result=[]
        for name,obj in self.p.corridors.items():
            version=obj.clazz.version
            if 0<=version<=10:continue 
            if version not in [11,12,13] or len(obj.contents)!={11:24,12:25,13:26}[version]:raise APIError('CATEGORY_REFERENCE_SCHEMA','Hidden-category references require audited corridor v11-v13 layouts.',name)
            if obj.contents[23].value is not None:result.append((name,obj.contents[23].value))
        return result

    def rename(self,entity,args):
        names=[row.name for row in args.renames];array,index,lookup=self.select(entity,names)
        mapping={row.name:row.new_name for row in args.renames}
        if len(set(mapping.values()))!=len(mapping):raise APIError('STOCK_EXISTS','Rename destinations must be unique.')
        collisions=set(mapping.values())&(set(lookup)-set(mapping))
        if collisions:raise APIError('STOCK_EXISTS','A rename destination already exists outside the selection.',sorted(collisions))
        refs=self.references(entity);hidden=self.hidden_categories() if entity=='categories' else [];counts=Counter()
        for obj,slot,role,owner in refs:
            name=string_slot(obj,slot)
            if name in mapping and mapping[name]!=name:write_slot(obj,slot,mapping[name]);counts[role]+=1
        for owner,values in hidden:
            for i,value in enumerate(w.elements(values)):
                name=w.string(value)
                if name in mapping and mapping[name]!=name:
                    items=w.elements(values);items[i]=native_string(value,mapping[name]);w.set_elements(values,items);counts['diagram_hidden_category']+=1
        for name,new_name in mapping.items():
            if name!=new_name:write_slot(lookup[name],index,new_name);counts['identity']+=1
        return {'entity':entity,'renames':[row.model_dump() for row in args.renames],'records_renamed':counts['identity'],'references_changed':dict(counts)}

    def category_rules(self,names,lookup):
        deleted={i for i,name in enumerate(lookup) if name in names};plans=[];deps=[]
        for document,objects in self.p.models.items():
            for obj in objects:
                if w.kind(obj)!='OTSignalModel':continue
                version=obj.clazz.version
                if version not in [8,9,10,11] or len(obj.contents)!={8:16,9:16,10:17,11:17}[version]:
                    raise APIError('CATEGORY_REFERENCE_SCHEMA','Category deletion requires audited Signal v8-v11 category arrays.',document)
                indices=([14] if obj.contents[8].values[0]==50 else [])+[15]
                for index in indices:
                    array=obj.contents[index].value
                    if array is None:continue
                    items=w.elements(array)
                    if len(items)>len(lookup):raise APIError('CATEGORY_REFERENCE_SCHEMA','Signal category array exceeds the selected category list.',{'document':document,'signal_id':obj.contents[0].value,'index':index})
                    affected=deleted&set(range(len(items)))
                    if affected:
                        deps.append({'kind':'signal_category_rules','document':document,'signal_id':obj.contents[0].value,'array_index':index,'removed_indices':sorted(affected)})
                        plans.append((array,[value for i,value in enumerate(items) if i not in deleted]))
        return plans,deps

    def delete(self,entity,args):
        array,index,lookup=self.select(entity,args.names);selected=set(args.names)
        if args.replacement is not None and args.replacement not in lookup:raise APIError('STOCK_NOT_FOUND','Replacement exact name does not exist.',args.replacement)
        if entity=='categories' and len(selected)>=len(lookup):raise APIError('CATEGORY_MINIMUM','At least one native Train Category must remain.')
        refs=[(obj,slot,role,owner) for obj,slot,role,owner in self.references(entity) if string_slot(obj,slot) in selected]
        deps=[{'kind':role,'owner':owner,'name':string_slot(obj,slot)} for obj,slot,role,owner in refs]
        hidden=self.hidden_categories() if entity=='categories' else [];rules=[]
        for owner,values in hidden:
            deps.extend({'kind':'diagram_hidden_category','owner':owner,'name':w.string(value)} for value in w.elements(values) if w.string(value) in selected)
        if entity=='categories':
            rules,rule_deps=self.category_rules(selected,lookup);deps+=rule_deps
        if deps and args.replacement is None and args.reference_policy=='reject':
            raise APIError('STOCK_REFERENCED','Selected records have dependencies; provide an exact replacement or explicit reference_policy=cascade.',{'count':len(deps),'dependencies':deps[:50]})
        counts=Counter();cascade=None
        if args.replacement is not None:
            for obj,slot,role,owner in refs:write_slot(obj,slot,args.replacement);counts[role]+=1
        elif refs:
            owners=list(dict.fromkeys(owner for obj,slot,role,owner in refs))
            if entity=='formations':
                from .models import DeleteCourses
                self.o.prepare_courses();cascade=CourseLifecycleOperations(self.o).delete_courses(DeleteCourses(course_ids=owners,reference_policy='detach'))
            else:
                from .models import DeleteStock
                cascade=self.delete('formations',DeleteStock(kind='delete_formations',names=owners,reference_policy='cascade'))
        for owner,values in hidden:
            old=w.elements(values);kept=[];replacement_seen=False
            for value in old:
                name=w.string(value)
                if name in selected:
                    counts['diagram_hidden_category']+=1
                    if args.replacement is None:continue
                    value=native_string(value,args.replacement);name=args.replacement
                if args.replacement is not None and name==args.replacement:
                    if replacement_seen:continue
                    replacement_seen=True
                kept.append(value)
            w.set_elements(values,kept)
        for values,items in rules:w.set_elements(values,items);counts['signal_category_arrays']+=1
        w.set_elements(array,[obj for obj in w.elements(array) if string_slot(obj,index) not in selected])
        return {'entity':entity,'names':args.names,'records_deleted':len(selected),'replacement':args.replacement,
            'reference_policy':args.reference_policy,'dependencies':deps,'references_changed':dict(counts),'cascade':cascade}
