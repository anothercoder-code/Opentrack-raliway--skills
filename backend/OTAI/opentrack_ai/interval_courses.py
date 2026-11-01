"""Original sequential interval copies, without native windows or preferences."""
import copy
import math
import re

from pydantic import TypeAdapter,ValidationError

from .archive import APIError,w,seconds
from .course_lifecycle import string_slot,write_slot,set_pairs
from .models import NewCourseId
from .native_records import split_time,timetable_record
from .railml_values import f32
from opentrack_course_schema import course_array

ID=TypeAdapter(NewCourseId)
MAX_NUMBER=2147483647


def advance_course_id(name,step,position):
    """ASCII numeric blocks; absent block appends the original %@.%i suffix."""
    blocks=list(re.finditer(r'[0-9]+',name))
    if position>=len(blocks):result=name+'.'+str(step)
    else:
        match=blocks[position];old=int(match.group());new=old+step
        if old>MAX_NUMBER or new>MAX_NUMBER:raise APIError('INTERVAL_NUMBER_RANGE','Numeric blocks must stay within the supported nonnegative signed-int32 range.',name)
        if new<0:return None
        replacement=str(new)
        if match.group().startswith('0'):replacement=replacement.zfill(len(match.group()))
        result=name[:match.start()]+replacement+name[match.end():]
    try:return ID.validate_python(result)
    except ValidationError:return None


def native_shift_planned(row,step):
    """Native addSecondsToTime: skips undefined/negative inputs and clears negative results."""
    warnings=[]
    for field,index,day_index in [('arrival',6,0),('departure',7,1)]:
        text=string_slot(row,index)
        if text=='HH:MM:SS':continue
        old=f32(f32(row.contents[15].values[day_index]*86400)+seconds(text))
        if old<0:
            warnings.append({'code':'NATIVE_NEGATIVE_TIME_UNSHIFTED','field':field});continue
        shifted=f32(old+step)
        if shifted<0:
            write_slot(row,index,'HH:MM:SS');row.contents[15].values[day_index]=0
            warnings.append({'code':'NATIVE_NEGATIVE_TIME_CLEARED','field':field})
        else:
            day,text=split_time(math.trunc(shifted));write_slot(row,index,text);row.contents[15].values[day_index]=day
    return warnings


def create_intervals(operations,args):
    o=operations.o;p=operations.p;table,groups=operations.load();o.prepare_courses()
    source=args.source_course_id;courses=p.courses();definitions={string_slot(course,0):course for course in courses}
    if len(definitions)!=len(courses):raise APIError('DUPLICATE_COURSE_ID','Interval generation requires unambiguous Course definitions.')
    if source not in definitions:raise APIError('COURSE_NOT_FOUND','Select an existing bound source Course.',source)
    if not groups.get(source):raise APIError('TIMETABLE_EMPTY_SELECTION','The source Course has no saved timetable rows.',source)
    rows=groups[source];row_count=len(rows);connection_count=sum(len(w.elements(row.contents[9].value)) for row in rows)
    operations.budget(row_count*args.count,connection_count*args.count)
    o.timetable_creation_targets+=args.count
    if o.timetable_creation_targets>1000:raise APIError('GENERATION_SIZE','One draft supports at most 1000 requested timetable creation targets.')
    if args.update_courses:
        o.requested_courses+=args.count
        if o.requested_courses>1000:raise APIError('GENERATION_SIZE','One draft supports at most 1000 requested Course definitions, including interval copies.')
    ids=[];current=source
    for _ in range(args.count):
        candidate=advance_course_id(current,args.number_step,args.number_position)
        if candidate is None:raise APIError('INTERVAL_COURSE_ID','Numbering produced an invalid or negative Course ID.',current)
        if candidate==source or candidate in ids:raise APIError('INTERVAL_COURSE_COLLISION','Sequential numbering would overwrite its own source/copies.',candidate)
        ids.append(candidate);current=candidate
    collisions=[cid for cid in ids if groups.get(cid) or args.update_courses and cid in definitions]
    if collisions and not args.replace_existing:raise APIError('INTERVAL_EXISTS','Explicit replace_existing is required for existing target timetable rows or replaced Course definitions.',collisions)
    native_step=math.trunc(f32(args.interval_s));creations=[];changes=[];planned=[];course_plans={};prior_course=definitions[source]
    reference=string_slot(rows[0],2)
    if reference in ['','0','-1']:reference=source
    prior_id=source
    for cid in ids:
        copied=[];warnings=[]
        for old in rows:
            row=copy.deepcopy(old)
            
            
            row.contents[9].values[0]=o.d.array([copy.deepcopy(connection) for connection in w.elements(old.contents[9].value)])
            copied.append(row)
        if native_step!=args.interval_s:warnings.append({'code':'NATIVE_INTERVAL_FLOAT32_STEP','requested_s':args.interval_s,'saved_step_s':native_step})
        for row in copied:
            write_slot(row,1,cid);write_slot(row,2,reference)
            row.contents[0].values[0]=17;row.contents[10].values[0]&=3
            offset=row.contents[11].value
            if not math.isfinite(offset):raise APIError('INTERVAL_OFFSET','The source interval offset must be finite.',prior_id)
            row.contents[11].values[0]=f32(offset+f32(args.interval_s))
            warnings.extend({'index':row.contents[3].value,**item} for item in native_shift_planned(row,native_step))
            for connection in w.elements(row.contents[9].value):
                old_target=string_slot(connection,1);target=advance_course_id(old_target,args.number_step,args.number_position)
                if target is not None:write_slot(connection,1,target)
                else:warnings.append({'code':'NATIVE_CONNECTION_NUMBER_UNCHANGED','index':row.contents[3].value,'target_course_id':old_target})
                write_slot(connection,0,cid);connection.contents[4].values[0]&=15
            changes.append({'course_id':cid,'index':row.contents[3].value,'source_course_id':prior_id,'after':timetable_record(cid+'#'+str(row.contents[3].value),row)})
        if args.update_courses:
            course=copy.deepcopy(prior_course);write_slot(course,0,cid);course_plans[cid]=course;prior_course=course
        planned.append((cid,copied));creations.append({'course_id':cid,'source_course_id':prior_id,'rows':row_count,
            'replaced_rows':len(groups.get(cid,[])),'course_definition_written':args.update_courses,'replaced_course_definition':args.update_courses and cid in definitions,
            'interval_reference_course_id':reference,'first_row_interval_offset_s':copied[0].contents[11].value,'warnings':warnings})
        prior_id=cid;rows=copied
    
    for cid,copied in planned:groups[cid]=copied;o.changed_timetables.add(cid)
    set_pairs(p.data['timetable'],[(cid+'#'+str(row.contents[3].value),row) for cid,values in groups.items() for row in values])
    if args.update_courses:
        retained=[course for course in courses if string_slot(course,0) not in course_plans];retained.extend(course_plans.values())
        w.set_elements(course_array(p.data['courses']),retained)
    return {'course_ids':ids,'source_course_id':source,'courses_generated':len(course_plans),'timetable_rows_created':row_count*args.count,
        'connections_created':connection_count*args.count,'interval_s':args.interval_s,'native_step_s':native_step,'creations':creations,'timetable_changes':changes,
        'unbound_courses':[cid for cid in ids if not args.update_courses and cid not in definitions],
        'actual_data_scope':'Saved actual strings/day offsets are copied unchanged; native transient validity is not recreated or certified.'}
