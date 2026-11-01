"""Original saved timetable row commands; independent of native UI preferences."""
from collections import defaultdict

from .archive import APIError,clock,seconds,w
from .course_lifecycle import set_pairs,string_slot,write_slot
from .native_records import absolute_time,split_time,timetable_record,connection_record

KINDS={'create_timetable_skeletons','create_interval_courses','plan_timetable_connections','update_timetable_rows','insert_timetable_rows','delete_timetable_rows','shift_timetable_rows','set_timetable_interval','reset_timetable_actual','copy_actual_to_planned','sync_timetable','edit_timetable_connections','import_timetable_text','import_timetable_xml'}
UNSET={'','0','-1'}


def identity(row):return string_slot(row,1),row.contents[3].value


def row_record(row):
    cid,index=identity(row);return timetable_record(cid+'#'+str(index),row)


def time_value(row,field):
    value=string_slot(row,6 if field=='arrival' else 7)
    return None if value=='HH:MM:SS' else absolute_time(value,row.contents[15].values[0 if field=='arrival' else 1])


def set_time(row,field,value):
    index=6 if field=='arrival' else 7;day_index=0 if field=='arrival' else 1
    if value is None:day,text=0,'HH:MM:SS'
    else:
        if int(value)!=value:raise APIError('TIMETABLE_SUBSECOND','An undefined-time interval propagation needs an integral offset at the saved HH:MM:SS resolution.',value)
        day,text=split_time(int(value))
    write_slot(row,index,text);row.contents[15].values[day_index]=day


class TimetableOperations:
    def __init__(self,operations):self.o=operations;self.p=operations.p;self.d=operations.d

    def create_timetable_skeletons(self,args):
        from .timetable_creation import create_skeletons
        return create_skeletons(self,args)

    def create_interval_courses(self,args):
        from .interval_courses import create_intervals
        return create_intervals(self,args)

    def plan_timetable_connections(self,args):
        from .connection_commands import ConnectionCommands
        return ConnectionCommands(self).run(args)

    def load(self,check_indices=True):
        self.o.prepare_timetable();table=self.p.table();groups=defaultdict(list)
        for key,row in table.items():
            cid,index=identity(row)
            if key!=cid+'#'+str(index):raise APIError('TIMETABLE_KEY','Saved timetable key differs from its Course/index.',key)
            groups[cid].append(row)
        for cid,rows in groups.items():
            rows.sort(key=lambda row:row.contents[3].value)
            if check_indices and any(row.contents[3].value!=i or row.contents[4].value!=len(rows)-1 for i,row in enumerate(rows)):
                raise APIError('TIMETABLE_INDEX','Saved Course rows must have contiguous indices and a consistent last index.',cid)
        return table,groups

    def budget(self,rows,connections=0):
        self.o.requested_rows+=rows;self.o.requested_connections+=connections
        if self.o.requested_rows>10000 or self.o.requested_connections>10000:raise APIError('GENERATION_SIZE','One draft supports at most 10000 requested timetable row targets and 10000 requested connections.')

    def select(self,args,groups):
        courses={w.string(c.contents[0].value) for c in self.p.courses()}
        ids=args.course_ids if args.course_ids else list(dict.fromkeys(ref.course_id for ref in args.rows))
        missing=[cid for cid in ids if cid not in courses]
        if missing:raise APIError('COURSE_NOT_FOUND','Selected timetable Courses do not exist.',missing[:50])
        if args.course_ids:result=[row for cid in args.course_ids for row in groups.get(cid,[])]
        else:
            lookup={identity(row):row for rows in groups.values() for row in rows};missing=[(r.course_id,r.index) for r in args.rows if (r.course_id,r.index) not in lookup]
            if missing:raise APIError('TIMETABLE_ROW_NOT_FOUND','Selected Course/index rows do not exist.',missing[:50])
            result=[lookup[(r.course_id,r.index)] for r in args.rows]
        if not result:raise APIError('TIMETABLE_EMPTY_SELECTION','The selected Courses have no timetable rows.')
        return result

    def family(self,source,table):
        cid,index=identity(source);station=string_slot(source,5);reference=string_slot(source,2)
        return [row for row in table.values() if row is source or (row.contents[3].value==index and string_slot(row,5)==station and
            (string_slot(row,2)==cid or (reference not in UNSET and identity(row)[0]!=cid and
                (string_slot(row,2)==reference if string_slot(row,2) not in UNSET else identity(row)[0]==reference))))]

    def write(self,groups):
        values=[]
        for cid,rows in groups.items():
            for index,row in enumerate(rows):
                row.contents[3].values[0]=index;row.contents[4].values[0]=len(rows)-1
                values.append((cid+'#'+str(index),row))
        set_pairs(self.p.data['timetable'],values)

    def changes(self,before,rows):
        after={identity(row):row_record(row) for row in rows};result=[]
        for key in dict.fromkeys([*before,*after]):
            old=before.get(key);new=after.get(key)
            if old!=new:result.append({'course_id':key[0],'index':key[1],'fields':{name:{'before':old.get(name) if old else None,'after':new.get(name) if new else None} for name in sorted(set(old or {})|set(new or {})) if (old or {}).get(name)!=(new or {}).get(name)}})
        self.o.changed_timetables.update(key[0] for key in set(before)|set(after))
        return {'rows_changed':len(result),'timetable_changes':result,'actual_data_scope':'Saved fields only; native runtime validity flags are not serialized or inspected.'}

    def update_timetable_rows(self,args):
        table,groups=self.load();selected=self.select(args,groups);before={identity(row):row_record(row) for row in table.values()};proposals={};target_rows={}
        controls={'kind','course_ids','rows','propagate_interval','propagate_delays','rebind_station_connections'};fields=args.model_fields_set-controls
        def propose(row,field,value):
            key=(identity(row),field)
            if key in proposals and proposals[key]!=value:raise APIError('TIMETABLE_PROPAGATION_CONFLICT','Selected interval origins propose conflicting values for the same row/field.',{'row':key[0],'field':field})
            proposals[key]=value;target_rows[identity(row)]=row
        for source in selected:
            family=self.family(source,table);source_record=before[identity(source)]
            for field in fields-{'arrival','departure','arrival_day_offset','departure_day_offset'}:
                propagate=args.propagate_delays if field in ['mean_delay_s','distribution_name'] else args.propagate_interval and field!='connections'
                value=getattr(args,field)
                if field=='connections':value=[item.model_dump() for item in value]
                for row in family if propagate else [source]:propose(row,field,value)
            for field in ['arrival','departure']:
                day_field=field+'_day_offset'
                if not {field,day_field}&fields:continue
                old=time_value(source,field);text=getattr(args,field) if field in fields else source_record[field]
                if text is None or text=='HH:MM:SS':new=None
                else:new=absolute_time(text,getattr(args,day_field) if day_field in fields else source_record[day_field])
                if day_field in fields and getattr(args,day_field) and new is None:raise APIError('TIMETABLE_TIME','A day offset needs a defined planned time.')
                for row in family if args.propagate_interval else [source]:
                    value=new;target_old=time_value(row,field)
                    if row is not source and new is not None:
                        if old is not None:value=None if target_old is None else target_old+(new-old)
                        elif string_slot(row,2)==identity(source)[0]:value=new+row.contents[11].value
                        elif identity(row)[0]==string_slot(source,2):value=new-source.contents[11].value
                        else:value=new+row.contents[11].value-source.contents[11].value
                    propose(row,field,value)
        connection_count=sum(len(value) for (_,field),value in proposals.items() if field=='connections');self.budget(len(target_rows),connection_count)
        known={item['sign'] for item in self.p.catalog('stations')}
        for (key,field),value in proposals.items():
            row=target_rows[key]
            if field in ['arrival','departure']:set_time(row,field,value)
            elif field=='station_sign':
                if value not in known:raise APIError('TIMETABLE_STATION','Unknown exact station sign.',value)
                write_slot(row,5,value)
                for connection in w.elements(row.contents[9].value):write_slot(connection,2,value)
            elif field in ['track_id','dwell_s','mean_delay_s','distribution_name']:write_slot(row,{'track_id':18,'dwell_s':8,'mean_delay_s':12,'distribution_name':16}[field],str(value))
            elif field=='delta_mass_t':row.contents[17].values[0]=value
            elif field in ['stop_at_station','timing_station']:
                bit=1 if field=='stop_at_station' else 2;row.contents[10].values[0]=(row.contents[10].value|bit) if value else (row.contents[10].value&~bit)
        from .models import ConnectionSpec
        for (key,field),value in proposals.items():
            if field=='connections':
                row=target_rows[key];row.contents[9].values[0]=self.o.make_connections([ConnectionSpec(**item) for item in value],key[0],string_slot(row,5))
        if args.rebind_station_connections:
            remaining=defaultdict(set);moves=defaultdict(set)
            for row in table.values():remaining[identity(row)[0]].add(string_slot(row,5))
            for key,row in target_rows.items():
                if before[key]['station_sign']!=string_slot(row,5):moves[(key[0],before[key]['station_sign'])].add(string_slot(row,5))
            for row in table.values():
                for connection in w.elements(row.contents[9].value):
                    target=(string_slot(connection,1),string_slot(connection,6))
                    if target in moves and target[1] not in remaining[target[0]]:
                        if len(moves[target])!=1:raise APIError('TIMETABLE_REFERENCE_AMBIGUOUS','Moved station visits have multiple possible connection destinations.',target)
                        write_slot(connection,6,next(iter(moves[target])))
        return {'rows_selected':len(selected),'expanded_row_targets':len(target_rows),**self.changes(before,list(table.values()))}

    def insert_timetable_rows(self,args):
        table,groups=self.load()
        if args.course_id not in {w.string(c.contents[0].value) for c in self.p.courses()}:raise APIError('COURSE_NOT_FOUND','Insertion requires an existing Course.',args.course_id)
        rows=groups.setdefault(args.course_id,[]);index=len(rows) if args.before_index is None else args.before_index
        if index>len(rows):raise APIError('TIMETABLE_INDEX','Insertion position is beyond the end of the Course.',index)
        self.budget(len(args.stops),sum(len(stop.connections) for stop in args.stops));before={identity(row):row_record(row) for row in rows}
        known={item['sign'] for item in self.p.catalog('stations')}
        if any(stop.station_sign not in known for stop in args.stops):raise APIError('TIMETABLE_STATION','Inserted rows need exact existing station signs.')
        rows[index:index]=[self.o.make_timetable_row(args.course_id,0,1,stop) for stop in args.stops];self.write(groups)
        return {'course_id':args.course_id,'rows_inserted':len(args.stops),'before_index':index,**self.changes(before,rows)}

    def remove_rows(self,table,groups,removed,policy,removed_course_ids=()):
        kept={key:row for key,row in table.items() if id(row) not in removed};stations=defaultdict(set)
        old_stations={(identity(row)[0],string_slot(row,5)) for row in table.values()}
        for row in kept.values():stations[identity(row)[0]].add(string_slot(row,5))
        dependencies=[]
        for row in kept.values():
            for connection in w.elements(row.contents[9].value):
                target=string_slot(connection,1);station=string_slot(connection,6)
                if station not in stations[target] and ((target,station) in old_stations or target in removed_course_ids):dependencies.append((row,connection))
        if dependencies and policy=='reject':raise APIError('TIMETABLE_REFERENCED','Deleting rows would leave connections without a target station; explicitly detach or edit those connections first.',{'count':len(dependencies),'connections':[connection_record(c) for _,c in dependencies[:20]]})
        drop={id(connection) for _,connection in dependencies}
        for row in kept.values():w.set_elements(row.contents[9].value,[c for c in w.elements(row.contents[9].value) if id(c) not in drop])
        for cid in groups:groups[cid]=[row for row in groups[cid] if id(row) not in removed]
        self.write(groups);return len(drop)

    def delete_timetable_rows(self,args):
        table,groups=self.load();selected=self.select(args,groups);self.budget(len(selected));before={identity(row):row_record(row) for row in table.values()}
        detached=self.remove_rows(table,groups,{id(row) for row in selected},args.reference_policy)
        return {'rows_deleted':len(selected),'connections_detached':detached,**self.changes(before,[row for rows in groups.values() for row in rows])}

    def shift_timetable_rows(self,args):
        table,groups=self.load();selected=self.select(args,groups);targets={id(row):row for source in selected for row in (self.family(source,table) if args.propagate_interval else [source])}
        self.budget(len(targets));before={identity(row):row_record(row) for row in targets.values()}
        for row in targets.values():
            for field in ['arrival','departure']:
                value=time_value(row,field)
                if value is not None:set_time(row,field,value+args.seconds)
        return {'rows_selected':len(selected),'expanded_row_targets':len(targets),'seconds':args.seconds,**self.changes(before,list(targets.values()))}

    def set_timetable_interval(self,args):
        table,groups=self.load();known={w.string(c.contents[0].value) for c in self.p.courses()}
        if any(cid not in known for cid in args.course_ids) or args.reference_course_id is not None and args.reference_course_id not in known:raise APIError('COURSE_NOT_FOUND','Interval references require exact existing Courses.')
        selected=[row for cid in args.course_ids for row in groups.get(cid,[])];self.budget(len(selected));before={identity(row):row_record(row) for row in selected}
        proposed={cid:(args.reference_course_id if cid!=args.reference_course_id else None) for cid in args.course_ids}
        reference_map={cid:{string_slot(row,2) for row in rows if string_slot(row,2) not in UNSET} for cid,rows in groups.items()}
        reference_map.update({cid:({ref} if ref else set()) for cid,ref in proposed.items()})
        for cid in args.course_ids:
            stack=[(cid,False)];active=set();done=set()
            while stack:
                current,leaving=stack.pop()
                if leaving:active.discard(current);done.add(current);continue
                if current in active:raise APIError('INTERVAL_CYCLE','Interval reference binding would create a cycle.',current)
                if current in done:continue
                active.add(current);stack.append((current,True));stack.extend((ref,False) for ref in reference_map.get(current,set()))
        for row in selected:
            reference=proposed[identity(row)[0]]
            write_slot(row,2,reference or '0')
            
            
            
            if reference is None:row.contents[11].values[0]=0.0
            elif args.offset_s is not None:row.contents[11].values[0]=args.offset_s
        return {'course_ids':list(args.course_ids),'reference_course_id':args.reference_course_id,'stored_times_shifted':False,
            'offset_normalization':{'detached_or_root_rows_zeroed':sum(proposed[identity(row)[0]] is None for row in selected),
                'supplied_offset_applies_only_to_referenced_rows':True},**self.changes(before,selected)}

    def reset_timetable_actual(self,args):
        table,groups=self.load();selected=self.select(args,groups);self.budget(len(selected));before={identity(row):row_record(row) for row in selected}
        for row in selected:
            write_slot(row,13,'HH:MM:SS');write_slot(row,14,'HH:MM:SS');row.contents[15].values[2:4]=[0,0]
        return {'rows_selected':len(selected),**self.changes(before,selected)}

    def copy_actual_to_planned(self,args):
        table,groups=self.load();selected=self.select(args,groups);self.budget(len(selected));before={identity(row):row_record(row) for row in selected};copied=0
        for row in selected:
            for actual,planned,actual_day,planned_day in [(13,6,2,0),(14,7,3,1)]:
                value=string_slot(row,actual)
                if value!='HH:MM:SS':write_slot(row,planned,value);row.contents[15].values[planned_day]=row.contents[15].values[actual_day];copied+=1
        return {'rows_selected':len(selected),'saved_actual_times_copied':copied,'runtime_actual_validity_verified':False,**self.changes(before,selected)}

    def sync_timetable(self,args):
        table,groups=self.load(False);known={w.string(c.contents[0].value) for c in self.p.courses()};orphan=[row for row in table.values() if identity(row)[0] not in known]
        self.budget(len(orphan));before={identity(row):row_record(row) for row in table.values()}
        missing_targets={string_slot(c,1) for row in table.values() for c in w.elements(row.contents[9].value)}-known
        detached=self.remove_rows(table,groups,{id(row) for row in orphan},args.reference_policy,missing_targets)
        interval_resets=0
        for rows in groups.values():
            for row in rows:
                if string_slot(row,2) not in known|UNSET:
                    if args.reference_policy=='reject':raise APIError('INTERVAL_REFERENCE','Orphan interval references require explicit detach.',string_slot(row,2))
                    write_slot(row,2,'0');row.contents[11].values[0]=0.0;interval_resets+=1
        return {'orphan_rows_removed':len(orphan),'connections_detached':detached,'interval_references_reset':interval_resets,**self.changes(before,[row for rows in groups.values() for row in rows])}

    def edit_timetable_connections(self,args):
        table,groups=self.load();key=(args.row.course_id,args.row.index);row=next((row for row in table.values() if identity(row)==key),None)
        if row is None:raise APIError('TIMETABLE_ROW_NOT_FOUND','Connection owner row does not exist.',key)
        old=w.elements(row.contents[9].value);indices=[item.index for item in args.updates]+args.delete_indices
        if any(i>=len(old) for i in indices):raise APIError('CONNECTION_INDEX','Connection index is outside the saved row.',{'count':len(old)})
        targets=self.family(row,table) if args.propagate_interval else [row]
        count_propagated=sum(change.index<len(w.elements(target.contents[9].value)) for target in targets if target is not row for change in args.updates)
        self.budget(len(targets),len(args.updates)+len(args.append)+count_propagated);before={identity(target):row_record(target) for target in targets}
        for change in args.updates:
            obj=old[change.index]
            for field,index in [('target_course_id',1),('target_station_sign',6)]:
                if field in change.model_fields_set:write_slot(obj,index,getattr(change,field))
            for field,index in [('minimum_wait_s',3),('maximum_wait_s',5)]:
                if field in change.model_fields_set:write_slot(obj,index,'HH:MM:SS' if getattr(change,field) is None else clock(getattr(change,field)))
            flags=obj.contents[4].value
            for field,bit in [('join',1),('split',2)]:
                if field in change.model_fields_set:flags=flags|bit if getattr(change,field) else flags&~bit
            if change.location is not None:flags=(flags&~12)|{'exit':0,'entry':4,'dispo':8}[change.location]
            obj.contents[4].values[0]=flags
            if change.time_reference_type is not None:obj.contents[7].values[0]=change.time_reference_type
            if change.dispatching_distance_km is not None:obj.contents[8].values[0]=change.dispatching_distance_km
            maximum=string_slot(obj,5)
            if maximum not in ['','HH:MM:SS'] and seconds(maximum)<seconds(string_slot(obj,3)):raise APIError('CONNECTION_WAIT','Maximum connection wait must not be less than minimum.')
        kept=[] if args.clear else [obj for i,obj in enumerate(old) if i not in set(args.delete_indices)]
        kept.extend(w.elements(self.o.make_connections(args.append,key[0],string_slot(row,5))));w.set_elements(row.contents[9].value,kept)
        if args.propagate_interval:
            for target in targets:
                if target is row:continue
                connections=w.elements(target.contents[9].value)
                for change in args.updates:
                    if change.index>=len(connections):continue
                    source=kept[change.index];connection=connections[change.index]
                    
                    
                    for slot in [3,5,6]:
                        if slot==5 and source.contents[slot].value is None:connection.contents[slot].values[0]=None
                        else:write_slot(connection,slot,string_slot(source,slot))
                    connection.contents[4].values[0]=(connection.contents[4].value&~15)|(source.contents[4].value&15)
                    connection.contents[7].values[0]=source.contents[7].value
        return {'row':key,'connections_before':len(old),'connections_after':len(kept),'expanded_row_targets':len(targets),
            'connections_propagated':count_propagated,**self.changes(before,targets)}

    def import_timetable_text(self,args):
        from .timetable_exchange import import_text
        return import_text(self,args)

    def import_timetable_xml(self,args):
        from .timetable_xml import import_xml
        return import_xml(self,args)
