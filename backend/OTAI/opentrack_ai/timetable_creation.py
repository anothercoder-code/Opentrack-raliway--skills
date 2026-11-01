"""Original new-timetable station selection and current Category defaults."""
import math

from .archive import APIError,w
from .models import TimetableStop
from .native_records import timetable_record
from .operations import Definitions
from .railml_values import f32
from .rolling_stock import category_record,require_current_category
from .topology import Topology,MAIN_SIGNAL_TYPES
from .drafts import set_text,text
from opentrack_train_schema import train_items
from opentrack_station_schema import station_items

HALT_SIGNAL_TYPES={6,8,9,10,11,16,17,18,19,20,21,*range(28,39),51,52}
MAX_SCANNED_ENDS=100000


def station_sign(end):
    model=end.contents[12].value
    return w.string(model.contents[7].value) if model is not None else ''


def is_station_vertex(end):return w.kind(end)=='OTStationEndModel'


def halt_or_exit(end):
    signal=end.contents[11].value
    if signal is None:return False
    signal_type,main_type=signal.contents[8].values[:2]
    return signal_type in HALT_SIGNAL_TYPES or signal_type in MAIN_SIGNAL_TYPES and main_type==4


def select_station_ends(sequences,ends):
    """Native candidates and backwards duplicate cleanup, preserving revisits."""
    candidates=[];raw_count=0;missing=[]
    if sequences:
        first=sequences[0][0] if sequences[0] else None
        if first is not None and ends[first].contents[12].value is not None:candidates.append(first)
    for sequence in sequences:
        raw_count+=len(sequence)
        if raw_count>MAX_SCANNED_ENDS:raise APIError('GENERATION_SIZE','A timetable station walk supports at most 100000 referenced Ends.')
        for node in sequence:
            end=ends[node]
            if is_station_vertex(end) or station_sign(end) and halt_or_exit(end):candidates.append(node)
    
    
    selected=list(candidates);index=len(selected)-1;last=None
    while index>=0:
        node=selected[index];end=ends[node];sign=station_sign(end)
        if not sign:
            if is_station_vertex(end):missing.append(list(node))
            selected.pop(index)
        elif last is not None and sign==station_sign(ends[last]):
            if is_station_vertex(end):
                same=[at for at,value in enumerate(selected) if ends[value] is ends[last]]
                if same:selected.pop(same[-1])
                last=node
            else:selected.pop(index)
        else:last=node
        index-=1
    warnings=[]
    if missing:warnings.append({'code':'STATION_VERTEX_WITHOUT_SIGN','count':len(missing),'nodes_preview':missing[:20]})
    if not selected:warnings.append({'code':'TIMETABLE_NO_STATIONS','details':'The original station selection produced no rows.'})
    return selected,{'scanned_ends':raw_count,'candidate_count':len(candidates),'selected_rows':len(selected),'warnings':warnings}


def track_id(node,ends,policy):
    end=ends[node];related=ends[(node[0],end.contents[8].value)]
    if policy==1:
        return next((w.string(obj.contents[18].value) for obj in [end,related] if obj.contents[18].value and w.string(obj.contents[18].value)), '')
    if policy==2:
        return next((w.string(edge.contents[19].value) for obj in [end,related] for index in [9,10]
            if (edge:=obj.contents[index].value) is not None and edge.contents[19].value and w.string(edge.contents[19].value)), '')
    return ''


def itinerary_sequences(project,name,traces,definitions):
    matches=[info for info in w.elements(project.data['dest'].contents[0].value) if w.string(info.contents[1].value)==name]
    if len(matches)!=1:raise APIError('ITINERARY_BINDING','The first Course Itinerary is missing or ambiguous.',name)
    sequences=[];names=[]
    for ref in w.elements(matches[0].contents[4].value):
        path_name=w.string(ref.contents[0].value)
        if path_name not in traces or path_name not in definitions:raise APIError('PATH_NOT_FOUND','The Itinerary references an unloaded Path.',path_name)
        document,_,path=definitions[path_name]
        if document!=w.string(ref.contents[2].value) or path.contents[2].values!=ref.contents[1].values:
            raise APIError('ITINERARY_PATH_REFERENCE','Itinerary document/Path identity does not match its definition.',path_name)
        names.append(path_name);sequences.extend([tuple(node) for node in route['nodes']] for route in traces[path_name]['routes'])
    if not sequences or not sequences[0]:raise APIError('ITINERARY_EMPTY','The first Itinerary has no loaded Route movement.',name)
    return sequences,names


def create_skeletons(operations,args):
    o=operations.o;p=operations.p;table,groups=operations.load()
    o.timetable_creation_targets+=len(args.course_ids)
    if o.timetable_creation_targets>1000:raise APIError('GENERATION_SIZE','One draft supports at most 1000 timetable creation targets.')
    courses={w.string(course.contents[0].value):p.service(course) for course in p.courses()}
    missing=set(args.course_ids)-set(courses)
    if missing:raise APIError('COURSE_NOT_FOUND','Timetable creation needs existing exact Course IDs.',sorted(missing))
    collisions=[cid for cid in args.course_ids if groups.get(cid)]
    if collisions and not args.replace_existing:raise APIError('TIMETABLE_EXISTS','Set replace_existing explicitly before replacing saved rows.',collisions)
    topology=Topology(p)
    if topology.problems:raise APIError('TOPOLOGY_INVALID','Timetable derivation requires valid loaded infrastructure.',topology.problems[:20])
    traces=p.graph()[2];definitions=Definitions(p).paths();stations=station_items(p.data['stations'])
    trains={w.string(t.contents[0].value):t for t in train_items(p.data['trains'])}
    categories={w.string(c.contents[1].value):c for c in w.elements(p.data['trains'].contents[1].value)}
    selected_cache={};creations=[];changes=[];planned=[];scanned=0
    for cid in args.course_ids:
        if cid in ['','0']:raise APIError('COURSE_ID_RESERVED','The original new-timetable command rejects the empty/zero Course ID.',cid)
        course=courses[cid]
        if not course['itineraries']:raise APIError('EMPTY_ITINERARY','Timetable creation requires the Course first Itinerary.',cid)
        itinerary=course['itineraries'][0]
        if itinerary not in selected_cache:
            sequences,path_names=itinerary_sequences(p,itinerary,traces,definitions)
            nodes,selection=select_station_ends(sequences,topology.ends);scanned+=selection['scanned_ends']
            if scanned>MAX_SCANNED_ENDS:raise APIError('GENERATION_SIZE','A batch supports 100000 scanned Ends across distinct Itineraries.')
            selected_cache[itinerary]=(nodes,selection,path_names)
        nodes,selection,path_names=selected_cache[itinerary];operations.budget(len(nodes));cfg=None
        train=trains.get(course['train'])
        if train is not None and len(train.contents)<4:raise APIError('VEHICLE_BINDING','The selected Train has no saved Category name.',course['train'])
        category_name=w.string(train.contents[3].value) if train is not None else None
        category=categories.get(category_name)
        warnings=list(selection['warnings'])
        if category is not None:require_current_category(category);cfg=category_record(category)
        else:warnings.append({'code':'CATEGORY_DEFAULTS_UNAVAILABLE','details':'Using original no-Category defaults; binding validation remains separate.'})
        dwell=0.
        if cfg:
            dwell=cfg['stop_at_every_station_time_s']
            if dwell is None or not math.isfinite(dwell):raise APIError('TIMETABLE_CATEGORY_DWELL','Category dwell must be finite.',category_name)
        rows=[];last_sign=None
        for node in nodes:
            if station_sign(topology.ends[node])==last_sign:continue
            index=len(rows);last_sign=station_sign(topology.ends[node])
            sign=station_sign(topology.ends[node]);stop=bool(cfg and cfg['stop_at_every_station']) and index>0
            timing=True if cfg and cfg['timing_stations_type_code']==1 else sign not in stations or bool(stations[sign].contents[7].value)
            spec=TimetableStop(station_sign=sign,track_id=track_id(node,topology.ends,cfg['track_name_creation_type_code'] if cfg else 0),stop_at_station=stop,timing_station=timing)
            row=o.make_timetable_row(cid,index,len(nodes),spec)
            
            set_text(row,8,str(math.trunc(f32(dwell))) if stop and dwell>0 else '0')
            rows.append((cid+'#'+str(index),row));changes.append({'course_id':cid,'index':index,'source_end':{'document':node[0],'end_id':node[1],'class':w.kind(topology.ends[node])},'after':timetable_record(cid+'#'+str(index),row)})
        if len(rows)!=len(nodes):warnings.append({'code':'NATIVE_TIMETABLE_ALIAS_INDICES','details':'Original identity cleanup left adjacent same-station candidates; the row pass suppresses them but retains its original candidate-count last index. Validation reports the resulting native index inconsistency.','candidate_rows':len(nodes),'written_rows':len(rows)})
        planned.append((cid,rows));creations.append({'course_id':cid,'itinerary':itinerary,'paths':path_names,'category':category_name,'rows':len(rows),
            'replaced_rows':len(groups.get(cid,[])),'selection':selection,'warnings':warnings,'planned_times_defined':False})
    for cid,rows in planned:
        table={key:row for key,row in table.items() if w.string(row.contents[1].value)!=cid};table.update(rows);o.changed_timetables.add(cid)
    root=p.data['timetable'];root.contents=[w.ar.TypedValue(b'i',len(table))]
    for key,row in table.items():root.contents.extend([w.ar.TypedValue(b'@',text(row,key)),w.ar.TypedValue(b'@',row)])
    return {'course_ids':args.course_ids,'courses_created':len(planned),'timetable_rows_created':len(changes),'distinct_itineraries_scanned':len(selected_cache),
        'scanned_ends':scanned,'creations':creations,'timetable_changes':changes,'planned_times_defined':False,'scope':'Saved timetable skeletons from the first Itinerary; fill arrival/departure times before simulation preparation.'}
