"""Course identity and reference edits in selected original-format archives.

These are disk operations. Native reset means pruning unavailable Itineraries;
the native temporary edit object's reset() must never erase a saved Course ID.
"""
from collections import Counter

from .archive import APIError,w
from .native_records import native_string
from opentrack_course_schema import course_array


KINDS={'rename_courses','delete_courses','reset_course_itineraries'}


def pairs(obj):
    if w.kind(obj) not in ['NSDictionary','NSMutableDictionary'] or not obj.contents or obj.contents[0].encodings!=[b'i'] or obj.contents[0].value*2+1!=len(obj.contents):
        raise APIError('COURSE_REFERENCE_SCHEMA','Expected a native counted dictionary.')
    result=[]
    for i in range(1,len(obj.contents),2):
        key=obj.contents[i].value
        if obj.contents[i].encodings!=[b'@'] or not isinstance(key,w.ar.GenericArchivedObject) or w.kind(key)!='NSString':
            raise APIError('COURSE_REFERENCE_SCHEMA','Course-related dictionary keys must be native strings.')
        result.append((w.string(key),obj.contents[i+1].value))
    if len({key for key,_ in result})!=len(result):raise APIError('COURSE_REFERENCE_COLLISION','A selected dictionary already has duplicate keys.')
    return result


def set_pairs(obj,values):
    template=next((value for value in w.objects(obj) if w.kind(value)=='NSString'),None) if values else None
    if values and template is None:raise APIError('COURSE_REFERENCE_SCHEMA','A nonempty dictionary needs a native string-key shape.')
    obj.contents=[w.ar.TypedValue(b'i',len(values))]+[group for key,value in values for group in [w.ar.TypedValue(b'@',native_string(template,key)),w.ar.TypedValue(b'@',value)]]


def string_slot(obj,index):
    if len(obj.contents)<=index or obj.contents[index].encodings!=[b'@']:
        raise APIError('COURSE_REFERENCE_SCHEMA','Audited Course reference field is missing.',{'class':w.kind(obj),'index':index})
    value=obj.contents[index].value
    if value is None:return ''
    if not isinstance(value,w.ar.GenericArchivedObject) or w.kind(value)!='NSString':
        raise APIError('COURSE_REFERENCE_SCHEMA','Expected an original NSString Course reference.',{'class':w.kind(obj),'index':index})
    return w.string(value)


def write_slot(obj,index,value):obj.contents[index].values[0]=native_string(obj,value)


class CourseLifecycleOperations:
    def __init__(self,operations):self.operations=operations;self.p=operations.p

    def select(self,ids):
        if len(ids)!=len(set(ids)):raise APIError('DUPLICATE_COURSE_ID','A selection must not repeat Course IDs.')
        if any(cid in ['0','-1'] for cid in ids):raise APIError('COURSE_RESERVED_ID','Reserved IDs cannot be safely rebound because native no-Course sentinels use the same strings.')
        items=self.p.courses();lookup={w.string(obj.contents[0].value):obj for obj in items}
        if len(items)!=len(lookup):raise APIError('DUPLICATE_COURSE_ID','Existing Course IDs are ambiguous.')
        missing=[cid for cid in ids if cid not in lookup]
        if missing:raise APIError('COURSE_NOT_FOUND','Selected Courses do not exist.',{'course_ids':missing[:50],'count':len(missing)})
        self.operations.course_update_targets+=len(ids)
        if self.operations.course_update_targets>10000:raise APIError('GENERATION_SIZE','One draft supports at most 10000 requested Course edit targets.')
        return lookup

    def objects(self):
        seen=set();result=[]
        for root in [*self.p.data.values(),*self.p.docs.values(),*self.p.corridors.values()]:
            for obj in w.objects(root):
                if id(obj) not in seen:seen.add(id(obj));result.append(obj)
        return result

    def references(self):
        """Return typed slots and dictionary-key roles, never text substitutions."""
        slots=[];dictionaries=[];objects=self.objects()
        for obj in objects:
            cls=w.kind(obj);version=obj.clazz.version
            if cls=='OTTimetable':
                if version not in [7,8,9] or len(obj.contents)!={7:17,8:18,9:19}[version]:raise APIError('TIMETABLE_SCHEMA','Course lifecycle requires audited Timetable v7-v9 records.')
                slots.extend((obj,index,role,string_slot(obj,index)) for index,role in [(1,'timetable_owner'),(2,'interval_reference')])
            elif cls=='OTConnection':
                lengths={0:4,1:5,2:5,3:6,4:7,5:8,6:9}
                if version not in lengths or len(obj.contents)!=lengths[version]:raise APIError('CONNECTION_SCHEMA','Course lifecycle found an unaudited Connection layout.')
                slots.extend((obj,index,role,string_slot(obj,index)) for index,role in [(0,'connection_owner'),(1,'connection_target')])
            elif cls=='OTIncident':
                if not 0<=version<=12:raise APIError('INCIDENT_SCHEMA','The original Incident Course-reference prefix is audited for versions 0-12.')
                slots.append((obj,1,'incident',string_slot(obj,1)))
            elif cls=='OTConflict':
                if version not in [0,1] or len(obj.contents)!={0:3,1:4}[version]:raise APIError('CONFLICT_SCHEMA','Course lifecycle requires original Conflict v0/v1 records.')
                slots.append((obj,0,'diagram_conflict',string_slot(obj,0)))
            elif cls=='OTTCorridorSimController':
                if version not in [0,1,2] or len(obj.contents)!=(5 if version==2 else 4):raise APIError('CORRIDOR_REFERENCE_SCHEMA','Course lifecycle requires audited corridor controller v0-v2 records.')
                for index,group in enumerate(obj.contents):
                    if group.encodings!=[b'@']:raise APIError('CORRIDOR_REFERENCE_SCHEMA','Expected a dictionary field in the native corridor controller.')
                    if group.value is not None:dictionaries.append((group.value,'diagram_conflict' if index==0 else 'diagram_course'))
        return slots,dictionaries,objects

    def rename_courses(self,args):
        mapping={row.course_id:row.new_id for row in args.renames};lookup=self.select([row.course_id for row in args.renames])
        targets=list(mapping.values())
        if len(targets)!=len(set(targets)):raise APIError('COURSE_EXISTS','Rename destinations must be unique.')
        collisions=set(targets)&(set(lookup)-set(mapping))
        if collisions:raise APIError('COURSE_EXISTS','Rename destination already belongs to an unselected Course.',sorted(collisions))
        slots,dictionaries,_=self.references();plans=[];counts=Counter()
        
        for dictionary,role in [(self.p.data['timetable'],'timetable_key'),*dictionaries]:
            values=[]
            for key,value in pairs(dictionary):
                new_key=key
                if role=='timetable_key':
                    cid=string_slot(value,1)
                    if cid in mapping:
                        if key!=cid+'#'+str(value.contents[3].value):raise APIError('TIMETABLE_KEY','Rename refuses inconsistent timetable keys.',key)
                        new_key=mapping[cid]+'#'+str(value.contents[3].value)
                elif role=='diagram_course':new_key=mapping.get(key,key)
                else:
                    if w.kind(value)!='OTConflict':raise APIError('CONFLICT_SCHEMA','Conflict dictionary contains an unexpected record.')
                    cid=string_slot(value,0)
                    if cid in mapping:
                        if not key.endswith('#'+cid):raise APIError('CORRIDOR_REFERENCE_SCHEMA','Conflict key does not end in its exact Course ID.',key)
                        new_key=key[:-len(cid)]+mapping[cid]
                if new_key!=key:counts[role]+=1
                values.append((new_key,value))
            if len({key for key,_ in values})!=len(values):raise APIError('COURSE_REFERENCE_COLLISION','Rename would merge native dictionary keys.',role)
            plans.append((dictionary,values))
        for obj,index,role,cid in slots:
            if cid in mapping and mapping[cid]!=cid:write_slot(obj,index,mapping[cid]);counts[role]+=1
        for cid,target in mapping.items():
            if cid!=target:write_slot(lookup[cid],0,target);counts['course_id']+=1
        for dictionary,values in plans:set_pairs(dictionary,values)
        self.operations.changed_timetables.update(mapping.values())
        return {'course_ids':list(mapping),'renames':[row.model_dump() for row in args.renames],'references_changed':dict(counts),'courses_renamed':counts['course_id']}

    def delete_courses(self,args):
        selected=set(args.course_ids);lookup=self.select(args.course_ids);slots,dictionaries,objects=self.references();counts=Counter();references=[]
        table=list(self.p.table().items());rows_deleted={id(row) for _,row in table if string_slot(row,1) in selected}
        connections_deleted={id(obj) for _,row in table for obj in w.elements(row.contents[9].value) if id(row) in rows_deleted or string_slot(obj,0) in selected or string_slot(obj,1) in selected}
        incidents_deleted={id(obj) for obj,index,role,cid in slots if role=='incident' and cid in selected}
        conflicts_deleted={id(obj) for obj,index,role,cid in slots if role=='diagram_conflict' and cid in selected}
        for obj,index,role,cid in slots:
            if cid not in selected:continue
            if role=='interval_reference' and id(obj) not in rows_deleted:references.append({'kind':role,'owner':string_slot(obj,1),'course_id':cid})
            elif role=='connection_target' and string_slot(obj,0) not in selected:references.append({'kind':role,'owner':string_slot(obj,0),'course_id':cid})
            elif role in ['incident','diagram_conflict']:references.append({'kind':role,'course_id':cid})
        for dictionary,role in dictionaries:
            for key,value in pairs(dictionary):
                if role=='diagram_course' and key in selected:references.append({'kind':role,'course_id':key})
        if references and args.reference_policy=='reject':raise APIError('COURSE_REFERENCED','Selected Courses have dependencies. Review these or explicitly use reference_policy=detach.',{'count':len(references),'references':references[:50]})
        removed=incidents_deleted|conflicts_deleted|connections_deleted
        
        for owner in objects:
            if id(owner) in removed or id(owner) in rows_deleted:continue
            if w.kind(owner) in ['NSArray','NSMutableArray','NSDictionary','NSMutableDictionary']:continue
            for group in owner.contents:
                if any(isinstance(v,w.ar.GenericArchivedObject) and id(v) in removed for v in group.values):raise APIError('COURSE_REFERENCE_CONTAINER','A dependent record has an unaudited direct owner.',w.kind(owner))
        plans=[]
        for dictionary,role in [(self.p.data['timetable'],'timetable'),*dictionaries]:
            values=[]
            for key,value in pairs(dictionary):
                drop=(id(value) in rows_deleted) if role=='timetable' else (key in selected if role=='diagram_course' else id(value) in conflicts_deleted)
                if drop:counts[role+'_entries_removed']+=1
                else:values.append((key,value))
            plans.append((dictionary,values))
        for obj,index,role,cid in slots:
            if role=='interval_reference' and cid in selected and id(obj) not in rows_deleted:write_slot(obj,index,'0');counts['interval_references_reset']+=1
        for obj in objects:
            if w.kind(obj) in ['NSArray','NSMutableArray']:
                old=w.elements(obj);kept=[item for item in old if id(item) not in removed]
                if len(kept)!=len(old):w.set_elements(obj,kept)
            elif w.kind(obj) in ['NSDictionary','NSMutableDictionary'] and any(id(g.value) in removed for g in obj.contents[1:]):
                values=[(key,value) for key,value in pairs(obj) if id(value) not in removed];set_pairs(obj,values)
        for dictionary,values in plans:set_pairs(dictionary,values)
        w.set_elements(course_array(self.p.data['courses']),[obj for cid,obj in lookup.items() if cid not in selected])
        counts.update({'connections_removed':len(connections_deleted),'incidents_removed':len(incidents_deleted),'diagram_conflicts_removed':len(conflicts_deleted)})
        self.operations.changed_timetables.update(string_slot(row,1) for _,row in table if id(row) not in rows_deleted)
        return {'course_ids':list(args.course_ids),'courses_deleted':len(selected),'reference_policy':args.reference_policy,'dependencies':references,'references_changed':dict(counts)}

    def reset_course_itineraries(self,args):
        lookup=self.select(args.course_ids)
        from .operations import itinerary_owners
        owners=itinerary_owners(self.p)
        active={w.string(info.contents[1].value) for info in w.elements(self.p.data['dest'].contents[0].value)}&set(owners)
        changes=[]
        for cid in args.course_ids:
            obj=lookup[cid];array=obj.contents[2].value;old=w.elements(array) if array else [];names=[w.string(value) for value in old]
            kept=[value for value in old if w.string(value) in active]
            if len(kept)!=len(old):w.set_elements(array,kept)
            changes.append({'course_id':cid,'before':names,'after':[w.string(value) for value in kept],'removed':[name for name in names if name not in active]})
        return {'course_ids':list(args.course_ids),'courses_updated':len(changes),'courses_changed':sum(row['before']!=row['after'] for row in changes),'itinerary_resets':changes,'availability_scope':'Exact Itinerary definitions in the selected project documents and destination catalog; no GUI open-window state is inspected.'}
