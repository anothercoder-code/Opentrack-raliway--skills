"""Original local connection and compound Turnround data commands."""
import copy
import math

from .archive import APIError,clock,w
from .course_lifecycle import string_slot,write_slot
from .railml_values import f32
from .rolling_stock import require_current_category
from .timetable_editing import identity,row_record
from opentrack_train_schema import train_items


def native_wait_string(value):
    value=f32(value)
    if not math.isfinite(value):raise APIError('CONNECTION_DEFAULT_TIME','The Category connection time must be finite.')
    if value<0:return 'HH:MM:SS'
    
    return clock(math.trunc(f32(math.fmod(value,86400)))%86400)


class ConnectionCommands:
    def __init__(self,operations):
        self.ops=operations;self.o=operations.o;self.p=operations.p
        self.before={};self.touched={};self.created=0;self.deleted=0;self.defaults={}

    def touch(self,row):
        key=identity(row)
        if key not in self.before:self.before[key]=row_record(row);self.touched[key]=row

    def wait(self,cid):
        if cid not in self.defaults:
            course=next((c for c in self.p.courses() if string_slot(c,0)==cid),None)
            train=next((t for t in train_items(self.p.data['trains']) if course is not None and string_slot(t,0)==string_slot(course,3)),None)
            category=next((c for c in w.elements(self.p.data['trains'].contents[1].value) if train is not None and string_slot(c,1)==string_slot(train,3)),None)
            if category is None:self.defaults[cid]=('00:07:00',{'source':'native_no_category_fallback','seconds':420})
            else:
                require_current_category(category);value=category.contents[20].value
                self.defaults[cid]=(native_wait_string(value),{'source':'category','category':string_slot(category,1),'seconds':value})
        return self.defaults[cid]

    def find(self,row,target):
        return next(((c,index) for index,c in enumerate(w.elements(row.contents[9].value)) if string_slot(c,1)==target),(None,None))

    def shell(self,row):
        self.ops.budget(0,1);self.touch(row);obj=copy.deepcopy(self.o.d.template('OTConnection'))
        for slot,value in [(0,'0'),(1,'0'),(6,'')]:write_slot(obj,slot,value)
        for slot in [2,3,5]:obj.contents[slot].values[0]=None
        obj.contents[4].values[0]=0;obj.contents[7].values[0]=0;obj.contents[8].values[0]=0.
        connections=w.elements(row.contents[9].value);index=len(connections);connections.append(obj);w.set_elements(row.contents[9].value,connections)
        self.created+=1;return obj,index

    def finish(self,obj,row,target,nil_max=False):
        cid,_=identity(row);station=string_slot(row,5);minimum,provenance=self.wait(cid)
        for slot,value in [(0,cid),(1,target),(2,station),(3,minimum),(6,station)]:write_slot(obj,slot,value)
        if nil_max:obj.contents[5].values[0]=None
        else:write_slot(obj,5,'HH:MM:SS')
        return provenance

    def helper(self,row,target,style):
        self.touch(row);obj,index=self.find(row,target);created=obj is None;provenance=None
        if created:
            obj,index=self.shell(row);provenance=self.finish(obj,row,target,nil_max=style=='start')
        if style=='join':obj.contents[4].values[0]|=1
        elif style in ['split','split_end']:obj.contents[4].values[0]|=2
        return obj,index,created,provenance

    def turnround(self,row,target,direction,groups):
        station=string_slot(row,5);target_rows=groups.get(target,[])
        if not target_rows:raise APIError('CONNECTION_TARGET_TIMETABLE','Turnround requires the target timetable before this command.',target)
        matching=[r for r in target_rows if string_slot(r,5)==station]
        if not matching:raise APIError('CONNECTION_TARGET_STATION','Turnround target has no timetable visit at the effective source station.',{'target_course_id':target,'station_sign':station})
        obj,index=self.find(row,target);created=obj is None;self.touch(row)
        if created:obj,index=self.shell(row)
        for slot in [2,6]:write_slot(obj,slot,station)
        obj.contents[4].values[0]&=~12
        if direction=='turnround_to':
            if string_slot(target_rows[0],5)==station:counter=target_rows[0];style='start';flags=2
            else:counter=matching[0];style='join';flags=1
        else:
            if string_slot(target_rows[-1],5)==station:counter=target_rows[-1];style='split_end'
            else:counter=matching[0];style='split'
            flags=0
        self.ops.budget(1)
        other,other_index,other_created,other_default=self.helper(counter,identity(row)[0],style)
        obj.contents[4].values[0]=(obj.contents[4].value&~3)|flags
        provenance=self.finish(obj,row,target) if created else None
        return {'connection_index':index,'created':created,'default_wait':provenance,
            'counterpart':{'row':identity(counter),'connection_index':other_index,'created':other_created,'style':style,'default_wait':other_default}}

    def run(self,args):
        table,groups=self.ops.load();self.ops.budget(len(args.commands));lookup={identity(r):r for r in table.values()};actions=[]
        for number,command in enumerate(args.commands):
            key=(command.row.course_id,command.row.index);selected=lookup.get(key)
            if selected is None:raise APIError('TIMETABLE_ROW_NOT_FOUND','The command selected a missing timetable row.',key)
            rows=groups[key[0]];action=command.action;row=selected
            if action in ['insert','turnround_to','turnround_from'] and key[0] in ['','0','-1']:
                raise APIError('COURSE_RESERVED_ID','The original insertion command requires a valid owner Course ID.',key[0])
            if action in ['turnround_to','add_end','split_at_end']:row=rows[-1]
            elif action in ['turnround_from','add_start']:row=rows[0]
            elif action in ['join_at_station','split_at_station']:row=next(r for r in rows if string_slot(r,5)==string_slot(selected,5))
            if action!='delete' and not string_slot(row,5):raise APIError('TIMETABLE_STATION','The insertion command needs a nonempty station sign.',identity(row))
            item={'command_index':number,'action':action,'selected_row':key,'effective_row':identity(row),'target_course_id':command.target_course_id}
            if action=='delete':
                connections=w.elements(row.contents[9].value)
                if command.connection_index>=len(connections):raise APIError('CONNECTION_INDEX','Delete index is outside the current connection array.',{'row':key,'count':len(connections)})
                self.touch(row);connections.pop(command.connection_index);w.set_elements(row.contents[9].value,connections);self.deleted+=1
                item.update(deleted=True,connection_index=command.connection_index)
            elif action in ['turnround_to','turnround_from']:item.update(self.turnround(row,command.target_course_id,action,groups))
            else:
                style={'add_start':'start','add_end':'end','join_at_station':'join','split_at_station':'split','split_at_end':'split_end'}.get(action,'insert')
                obj,index,created,provenance=self.helper(row,command.target_course_id or '0',style)
                item.update(created=created,connection_index=index,default_wait=provenance)
            actions.append(item)
        pending=sum(string_slot(c,1)=='0' for row in self.touched.values() for c in w.elements(row.contents[9].value))
        return {'commands_executed':len(actions),'connections_created':self.created,'connections_deleted':self.deleted,
            'pending_connection_count':pending,'connection_actions':actions,**self.ops.changes(self.before,list(self.touched.values())),
            'scope':'Original local insertion/deletion and Turnround/helper data behavior. Native coupling and simulation are not executed.'}
