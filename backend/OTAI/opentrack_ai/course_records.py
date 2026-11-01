"""Original Course v0-v11 fields, menu tags, priority order and migration."""
import copy

from .archive import APIError,w
from .native_records import native_string

SPACING_CODES={'discrete':0,'moving':2,'moving_cbtc':3}
COURSE_LENGTHS={0:5,1:6,2:7,3:7,4:8,5:9,6:10,7:11,8:12,9:13,10:14,11:15}
COURSE_ENCODINGS=[[b'@'],[b'f'],[b'@'],[b'@'],[b'@'],[b'i'],[b'i'],[b'f',b'f'],[b'i'],[b'i'],[b'@'],[b'@'],[b'f',b'f'],[b'@'],[b'@']]
COURSE_SCALARS={'enabled':(5,0),'acceleration_percent':(6,0),'delayed_acceleration_percent':(9,0),'output_offset_m':(7,0),
    'additional_reservation_time_s':(12,0),'additional_release_time_s':(12,1)}
COURSE_STRINGS={'train':3,'speed_type':4,'description':10,'comment':11,'train_number':13,'course_type':14}


def course_version(obj):
    version=obj.clazz.version
    if w.kind(obj)!='OTCourse' or version not in COURSE_LENGTHS or len(obj.contents)!=COURSE_LENGTHS[version] or any(group.encodings!=enc for group,enc in zip(obj.contents,COURSE_ENCODINGS)):
        raise APIError('COURSE_SCHEMA','Course class version or typed groups differ from the audited original v0-v11 contract.',version)
    return version


def course_record(obj):
    version=course_version(obj);itineraries=[w.string(item) for item in w.elements(obj.contents[2].value)] if obj.contents[2].value else []
    acceleration=obj.contents[6].value if version>=2 else 100
    code=obj.contents[8].value if version>=5 else 0
    return {'course_id':w.string(obj.contents[0].value),'train':w.string(obj.contents[3].value),'itineraries':itineraries,
        'itinerary_preferences':[{'itinerary':name,'priority':index+1} for index,name in enumerate(itineraries)],
        'enabled':obj.contents[5].value>0 if version>=1 else True,'speed_type':w.string(obj.contents[4].value),
        'description':w.string(obj.contents[10].value) if version>=7 else '',
        'comment':w.string(obj.contents[11].value) if version>=8 else '',
        'train_number':w.string(obj.contents[13].value) if version>=10 else '',
        'course_type':w.string(obj.contents[14].value) if version>=11 else '',
        'acceleration_percent':acceleration,'delayed_acceleration_percent':obj.contents[9].value if version>=6 else acceleration,
        'entering_speed_kmh':obj.contents[1].value*3.6,'output_offset_m':obj.contents[7].values[0] if version>=4 else 0.,
        'spacing_mode_code':code,'spacing_mode':next((name for name,value in SPACING_CODES.items() if value==code),None),
        'additional_reservation_time_s':obj.contents[12].values[0] if version>=9 else 0.,
        'additional_release_time_s':obj.contents[12].values[1] if version>=9 else 0.,'archive_class_version':version}


def upgrade_course_records(root):
    records=[obj for obj in w.objects(root) if w.kind(obj)=='OTCourse'];versions=[course_version(obj) for obj in records]
    array=next((obj for obj in w.objects(root) if w.kind(obj)=='NSMutableArray'),None)
    count=0
    for obj,version in zip(records,versions):
        if version==11:continue
        if obj.contents[2].value is None:
            if array is None:raise APIError('COURSE_ARRAY_TEMPLATE','A nil legacy Itinerary list needs a native mutable-array shape.')
            empty=w.ar.GenericArchivedObject(array.clazz,None,[]);w.set_elements(empty,[]);obj.contents[2].values[0]=empty
        if version<1:obj.contents.append(w.ar.TypedValue(b'i',1))
        if version<2:obj.contents.append(w.ar.TypedValue(b'i',100))
        if version<4:obj.contents.append(w.ar.TypedGroup([b'f',b'f'],[0.,0.]))
        if version<5:obj.contents.append(w.ar.TypedValue(b'i',0))
        if version<6:obj.contents.append(w.ar.TypedValue(b'i',obj.contents[6].value))
        if version<7:obj.contents.append(w.ar.TypedValue(b'@',native_string(obj,'')))
        if version<8:obj.contents.append(w.ar.TypedValue(b'@',native_string(obj,'')))
        if version<9:obj.contents.append(w.ar.TypedGroup([b'f',b'f'],[0.,0.]))
        if version<10:obj.contents.append(w.ar.TypedValue(b'@',native_string(obj,'')))
        if version<11:obj.contents.append(w.ar.TypedValue(b'@',native_string(obj,'')))
        obj.clazz=copy.deepcopy(obj.clazz);obj.clazz.version=11;count+=1
    return count
