"""Stock security-array v5/v6 fields and audited draft-only migration.

OTRoute inherits these groups. v6 inserts a group before the Route flags and
release-zone references; indexing a v5 Route as v6 corrupts those references.
"""
from .archive import APIError,w,END_KINDS


def security_class(obj):
    clazz=obj.clazz
    while clazz:
        if clazz.name==b'OTSecurityArray':return clazz
        clazz=clazz.superclass
    return None


def security_version(obj):
    clazz=security_class(obj)
    if clazz is None or clazz.version not in [5,6]:
        raise APIError('SECURITY_ARRAY_VERSION','Only audited original OTSecurityArray v5/v6 layouts are supported.',clazz.version if clazz else None)
    expected={4:[b'@'],5:[b'i']*6,6:[b'i',b'f',b'f'],7:[b'@'],8:[b'f',b'f'],9:[b'i']}
    if clazz.version==6:expected[10]=[b'i']*3
    if any(i>=len(obj.contents) or obj.contents[i].encodings!=enc for i,enc in expected.items()):
        raise APIError('SECURITY_ARRAY_LAYOUT','Security-array groups do not match their declared original version.')
    return clazz.version


def security_properties(obj):
    version=security_version(obj)
    release,announce,release_time,reserve_time,_,_=obj.contents[5].values
    occupied,speed,wait=obj.contents[6].values;approach_length,approach_speed=obj.contents[8].values
    point,use_reserve,use_release=obj.contents[10].values if version==6 else [5000,0,int(release>0)]
    return {'security_array_version':version,'description':w.string(obj.contents[3].value),
        'release_point_m':release,'advance_notice_m':announce,'release_time_s':release_time,'reservation_time_s':reserve_time,
        'reservation_point_m':point,'use_reservation_point':bool(use_reserve),'use_release_point':bool(use_release),
        'allow_occupied_entry':bool(occupied&1),'occupied_entry_use_speed':bool(occupied&2),'occupied_entry_use_time':bool(occupied&4),
        'discrete_for_moving_block':bool(occupied&8),'occupied_entry_speed_kmh':speed,'occupied_entry_wait_s':wait,
        'approach_zone_length_m':approach_length,'approach_zone_speed_kmh':approach_speed,
        'overlap_name':w.string(obj.contents[7].value),'overlap_start_end_id':obj.contents[9].value,
        'signal_aspects':[item.contents[0].value for item in w.elements(obj.contents[4].value.contents[0].value)] if obj.contents[4].value else []}


def route_properties(obj):
    properties=security_properties(obj);flags_index=11 if properties['security_array_version']==6 else 10
    if w.kind(obj)!='OTRoute' or obj.clazz.version!=0 or len(obj.contents)!=flags_index+2 or obj.contents[flags_index].encodings!=[b'i'] or obj.contents[flags_index+1].encodings!=[b'@']*3:
        raise APIError('ROUTE_LAYOUT','Expected original OTRoute v0 with an audited security parent.')
    flags=obj.contents[flags_index].value;release,start,end=obj.contents[flags_index+1].values
    end_id=lambda node:node.contents[0].value if node is not None and w.kind(node) in END_KINDS else None
    return {**properties,'reserve_with_previous':bool(flags&1),'slow_speed_only_for_head':bool(flags&2),
        'release_group_end_ids':[end_id(node) for node in w.elements(release)],
        'slow_speed_zone_end_ids':[end_id(start),end_id(end)] if start and end else None}


def shunting_properties(obj):
    properties=security_properties(obj);index=11 if properties['security_array_version']==6 else 10
    if w.kind(obj)!='OTShunting' or obj.clazz.version!=0 or len(obj.contents)!=index+1 or obj.contents[index].encodings!=[b'f']:
        raise APIError('SHUNTING_LAYOUT','Expected original OTShunting v0 with its speed tail.')
    return {**properties,'speed_kmh':obj.contents[index].value}


def shunting_paths(project):
    """End group 16 holds OTPath wrappers, each with exactly one OTShunting."""
    result=[]
    for document,items in project.models.items():
        for end in items:
            if w.kind(end) not in END_KINDS:continue
            wrapper=end.contents[16].value
            if wrapper is None:continue
            for path in w.elements(wrapper.contents[0].value):
                if w.kind(path)!='OTPath' or len(path.contents)!=5:raise APIError('SHUNTING_PATH_LAYOUT','Shunting lists contain native automatic Path wrappers.')
                objects=w.elements(path.contents[0].value);infos=w.elements(path.contents[4].value)
                if len(objects)!=1 or w.kind(objects[0])!='OTShunting' or len(infos)!=1:raise APIError('SHUNTING_PATH_LAYOUT','Expected one Shunting and its single OTArrayInfo reference.')
                obj=objects[0];name=w.string(path.contents[1].value);nodes=w.elements(obj.contents[0].value)
                if not nodes or nodes[0] is not end or path.contents[2].values[1]!=end.contents[0].value:raise APIError('SHUNTING_OWNER','Automatic Path is stored at a different starting End.')
                if name!=w.string(obj.contents[1].value) or infos[0].contents[1].values!=obj.contents[2].values or w.string(infos[0].contents[0].value)!=name:
                    raise APIError('SHUNTING_PATH_REFERENCE','Automatic Path name or embedded Shunting reference differs.')
                result.append({'document':document,'start_id':end.contents[0].value,'name':name,'path_id':path.contents[2].values[0],
                    'nodes':[[document,node.contents[0].value] for node in nodes],'properties':shunting_properties(obj),'_path':path,'_object':obj,'_companion':None})
    return result


def protection_errors(project):
    """Validate persisted protection references without simulating dispatch."""
    shuntings=shunting_paths(project);errors=[]
    for document,root in project.docs.items():
        for route in w.objects(root):
            if w.kind(route)!='OTRoute':continue
            properties=route_properties(route);nodes=w.elements(route.contents[0].value);positions={id(node):i for i,node in enumerate(nodes)}
            group_index=12 if properties['security_array_version']==6 else 11
            groups,start,end=route.contents[group_index].values
            boundaries=w.elements(groups);indices=[positions.get(id(node),-1) for node in boundaries]
            details={'document':document,'route':w.string(route.contents[1].value)}
            if any(node is None or w.kind(node) not in END_KINDS for node in boundaries) or any(i<0 for i in indices) or any(b<=a for a,b in zip(indices,indices[1:])):
                errors.append({'code':'RELEASE_GROUP_REFERENCE','details':details})
            if (start is None)!=(end is None) or start is not None and (id(start) not in positions or id(end) not in positions or positions[id(start)]>positions[id(end)]):
                errors.append({'code':'SLOW_ZONE_REFERENCE','details':details})
            if properties['overlap_name']:
                matches=[row for row in shuntings if row['document']==document and row['start_id']==properties['overlap_start_end_id'] and row['name']==properties['overlap_name']]
                if len(matches)!=1 or not nodes or matches[0]['start_id']!=nodes[-1].contents[0].value:errors.append({'code':'OVERLAP_BINDING','details':details})
    return errors


def upgrade_security_records(project):
    """Insert the native v6 defaults in every v5 descendant, preserving aliases.

    Gather all old class versions before changing shared class objects. Both
    Routes and Shuntings can share the security parent in a single archive.
    """
    pending=[];seen=set()
    for root in [*project.docs.values(),*project.data.values(),*project.corridors.values()]:
        for obj in w.objects(root):
            if id(obj) in seen:continue
            seen.add(id(obj));clazz=security_class(obj)
            if clazz is None:continue
            version=security_version(obj)
            if version==5:pending.append((obj,clazz))
    for obj,_ in pending:
        obj.contents.insert(10,w.ar.TypedGroup([b'i']*3,[5000,0,int(obj.contents[5].values[0]>0)]))
    for _,clazz in pending:clazz.version=6
    return len(pending)
