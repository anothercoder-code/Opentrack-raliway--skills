"""Original operational record layouts verified against stock coder methods.

Offsets below are archive indices, not runtime ivar byte offsets. Native input
objects are preserved; these functions return bounded typed data only.
"""
import copy

from .archive import APIError,clock,seconds,w

DAY_SECONDS=86400
MAX_DAY=366


def split_time(value):
    day,within=divmod(value,DAY_SECONDS)
    if not -MAX_DAY<=day<=MAX_DAY:raise APIError('DAY_OFFSET_RANGE','Generated times support day offsets -366 through 366.',day)
    return int(day),clock(within)


def absolute_time(text,day=0):return int(day)*DAY_SECONDS+seconds(text)


def number(text):
    return float(text) if text else 0.


def native_string(obj,value):
    sample=next(item for item in w.objects(obj) if w.kind(item)=='NSString')
    return w.ar.GenericArchivedObject(sample.clazz,None,[w.ar.TypedValue(b'+',value.encode('ascii'))])


def upgrade_records(root,kind):
    """Upgrade audited old record layouts using defaults in the native decoder.

    All records of a class in that catalog are upgraded together; do not write
    incompatible class versions/shapes under one class name into an archive.
    """
    count=0
    for obj in w.objects(root):
        if w.kind(obj)!=kind:continue
        version=obj.clazz.version
        if kind=='OTTrailer':
            if version==3 and len(obj.contents)==7:continue
            expected={0:4,1:5,2:6}
            if version not in expected or len(obj.contents)!=expected[version]:raise APIError('TRAILER_SCHEMA','Unsupported original Trailer layout; cannot infer a migration.',version)
            if version<1:obj.contents.append(w.ar.TypedValue(b'i',1000))
            if version<2:obj.contents.append(w.ar.TypedValue(b'f',0.))
            obj.contents.append(w.ar.TypedValue(b'f',0.));target=3
        elif kind=='OTTimetable':
            if version==9 and len(obj.contents)==19:continue
            expected={7:17,8:18}
            if version not in expected or len(obj.contents)!=expected[version]:raise APIError('TIMETABLE_SCHEMA','Only audited Timetable v7/v8 -> v9 migration is supported.',version)
            if version<8:obj.contents.append(w.ar.TypedValue(b'f',0.))
            obj.contents.append(w.ar.TypedValue(b'@',native_string(obj,'')))
            obj.contents[0].values[0]=17;target=9
        elif kind=='OTConnection':
            if version==6 and len(obj.contents)==9:continue
            expected={0:4,1:5,2:5,3:6,4:7,5:8}
            if version not in expected or len(obj.contents)!=expected[version]:raise APIError('CONNECTION_SCHEMA','Unsupported original Connection layout; cannot infer a migration.',version)
            if version<1:obj.contents.append(w.ar.TypedValue(b'i',0))
            if version<3:obj.contents.append(w.ar.TypedValue(b'@',native_string(obj,'HH:MM:SS')))
            if version<4:obj.contents.append(w.ar.TypedValue(b'@',native_string(obj,w.string(obj.contents[2].value))))
            if version<5:obj.contents.append(w.ar.TypedValue(b'i',0))
            obj.contents.append(w.ar.TypedValue(b'f',0.));target=6
        else:raise APIError('RECORD_UPGRADE','No audited record migration is defined.',kind)
        obj.clazz=copy.deepcopy(obj.clazz);obj.clazz.version=target;count+=1
    return count


def trailer_record(obj):
    if w.kind(obj)!='OTTrailer' or len(obj.contents)<4:raise APIError('TRAILER_SCHEMA','Expected an audited original OTTrailer record.')
    dimensions=obj.contents[2].values;placement=obj.contents[3].values
    return {'name':w.string(obj.contents[1].value),'position':placement[1],'number_of_items':placement[2],
        'mass_t':dimensions[1],'length_m':dimensions[2],'rotating_mass_factor':dimensions[3],
        'number_of_axles':dimensions[4],'maximum_speed_kmh':obj.contents[4].value if len(obj.contents)>4 else 1000,
        'power_loss_kw':obj.contents[5].value if len(obj.contents)>5 else 0.,
        'power_loss_delta_load_factor_kw_per_t':obj.contents[6].value if len(obj.contents)>6 else 0.,
        'archive_class_version':obj.clazz.version}


def engine_reference_names(train):
    array=train.contents[2].values[1];refs=w.elements(array) if array is not None else []
    if any(w.kind(ref)!='OTTrainEngine' or len(ref.contents)!=2 for ref in refs):raise APIError('FORMATION_SCHEMA','Expected native Engine reference records.')
    names=[w.string(ref.contents[0].value) for ref in refs]
    if any(not name for name in names):raise APIError('FORMATION_SCHEMA','An Engine reference has an empty name.')
    return names


def connection_record(obj):
    if w.kind(obj)!='OTConnection' or len(obj.contents)<4:raise APIError('CONNECTION_SCHEMA','Expected an audited original OTConnection record.')
    flags=obj.contents[4].value if len(obj.contents)>4 else 0
    return {'course_id':w.string(obj.contents[0].value),'target_course_id':w.string(obj.contents[1].value),
        'station_sign':w.string(obj.contents[2].value),'minimum_wait':w.string(obj.contents[3].value),
        'maximum_wait':w.string(obj.contents[5].value) if len(obj.contents)>5 and obj.contents[5].value is not None else 'HH:MM:SS',
        **({'maximum_wait_is_nil':True} if len(obj.contents)>5 and obj.contents[5].value is None else {}),
        'target_station_sign':w.string(obj.contents[6].value) if len(obj.contents)>6 else w.string(obj.contents[2].value),
        'join':bool(flags&1),'split':bool(flags&2),'entry_connection':bool(flags&4),'dispo_connection':bool(flags&8),
        'time_reference_type':obj.contents[7].value if len(obj.contents)>7 else 0,
        'dispatching_distance_km':obj.contents[8].value if len(obj.contents)>8 else 0.}


def timetable_record(key,obj):
    if w.kind(obj)!='OTTimetable' or len(obj.contents)<17:raise APIError('TIMETABLE_SCHEMA','Expected an audited original OTTimetable record.')
    days=obj.contents[15].values
    return {'key':key,'course_id':w.string(obj.contents[1].value),'index':obj.contents[3].value,'last_index':obj.contents[4].value,
        'station_sign':w.string(obj.contents[5].value),'arrival':w.string(obj.contents[6].value),'departure':w.string(obj.contents[7].value),
        'arrival_day_offset':days[0],'departure_day_offset':days[1],'actual_arrival_day_offset':days[2],'actual_departure_day_offset':days[3],
        'actual_arrival':w.string(obj.contents[13].value),'actual_departure':w.string(obj.contents[14].value),
        'track_id':w.string(obj.contents[18].value) if len(obj.contents)>18 else '',
        'dwell_s':number(w.string(obj.contents[8].value)),'stop_at_station':bool(obj.contents[10].value&1),
        'timing_station':bool(obj.contents[10].value&2),'interval_reference_course_id':w.string(obj.contents[2].value),
        'interval_offset_s':obj.contents[11].value,'mean_delay_s':number(w.string(obj.contents[12].value)),
        'distribution_name':w.string(obj.contents[16].value),'delta_mass_t':obj.contents[17].value if len(obj.contents)>17 else 0.,
        'connections':[connection_record(c) for c in w.elements(obj.contents[9].value)]}
