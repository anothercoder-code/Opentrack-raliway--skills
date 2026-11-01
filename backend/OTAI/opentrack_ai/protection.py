"""Original Shunting/Overlap wrappers and Route protection data edits."""
from .archive import APIError,w
from .drafts import set_text
from .network_records import upgrade_security_records,route_properties,shunting_paths,shunting_properties
from .operations import clone
from .topology import Topology,key


def define_shunting(d,args):
    p=d.project;topology=Topology(p);nodes=[key(n) for n in args.nodes]
    if len(set(nodes))!=len(nodes):raise APIError('SHUNTING_CYCLE','A Shunting/Overlap must be a simple directed movement.')
    walk=topology.describe_walk(nodes)
    if walk['boundaries']:raise APIError('SHUNTING_DOCUMENT_BOUNDARY','Cross-document Shunting-wrapper persistence is not yet audited; this operation requires one document.')
    if args.name in d.paths():raise APIError('PATH_EXISTS','A Shunting creates a same-name automatic Path; choose a unique Path name.',args.name)
    migrated=upgrade_security_records(p);document,start=nodes[0];end=topology.ends[nodes[0]]
    obj=clone(d.template('OTShunting'));shunting_properties(obj)
    obj.contents[0].values[0]=d.array([topology.ends[node] for node in nodes]);set_text(obj,1,args.name);set_text(obj,3,args.description)
    obj.contents[2].values=[-1,-1];obj.contents[4].values[0]=d.indications(obj,[])
    obj.contents[5].values=[0,0,args.release_time_s,args.reservation_time_s,-1,0];obj.contents[6].values=[0,40.,0.]
    set_text(obj,7,'');obj.contents[8].values=[0.,0.];obj.contents[9].values[0]=-1;obj.contents[10].values=[5000,0,0];obj.contents[11].values[0]=args.speed_kmh
    path=clone(d.template('OTPath'));set_text(path,1,args.name);set_text(path,3,args.description)
    path.contents[0].values[0]=d.array([obj]);path.contents[2].values=[d.next_id(end),start]
    info=clone(d.template('OTArrayInfo'));set_text(info,0,args.name);info.contents[1].values=[-1,-1];path.contents[4].values[0]=d.array([info])
    if end.contents[16].value is None:
        wrapper=clone(d.template('OTShuntingList'));wrapper.contents[0].values[0]=d.array();end.contents[16].values[0]=wrapper
    d.append(end.contents[16].value.contents[0].value,path);p._graph=None
    return {'kind':'define_shunting','name':args.name,'document':document,'start_id':start,'end_id':nodes[-1][1],
        'automatic_path_id':path.contents[2].values[0],'automatic_path_name':args.name,'distance_m':walk['distance_m'],
        'properties':shunting_properties(obj),'security_arrays_upgraded':migrated,'native_simulation_verified':False}


def configure_protection(d,record,args,only_supplied=False):
    p=d.project;nodes=[tuple(n) for n in record['nodes']];topology=Topology(p)
    parts=[(record['document'],record['_object'])]
    if record['_companion'] is not None:parts.append((nodes[-1][0],record['_companion']))
    changed=lambda field:not only_supplied or field in args.model_fields_set
    if changed('release_group_boundaries'):
        selected=[key(n) for n in args.release_group_boundaries] if args.release_group_boundaries is not None else None
        if selected is not None:
            positions=[nodes.index(n) if n in nodes else -1 for n in selected]
            if positions[0]!=0 or positions[-1]!=len(nodes)-1 or any(i<0 for i in positions) or any(b<=a for a,b in zip(positions,positions[1:])):
                raise APIError('RELEASE_GROUP_BOUNDARIES','Use ordered unique movement Ends, including the Route start and end.')
        for document,part in parts:
            local=w.elements(part.contents[0].value)
            if selected is None:boundaries=local[:1]+([local[-1]] if part.contents[5].values[4]<0 and len(local)>1 else [])
            else:boundaries=[end for end in local if (document,end.contents[0].value) in selected]
            if not boundaries or boundaries[0] is not local[0]:boundaries.insert(0,local[0])
            part.contents[12].values[0]=d.array(boundaries)
    if changed('slow_speed_zone'):
        for _,part in parts:part.contents[12].values[1:]=[None,None]
        if args.slow_speed_zone is not None:
            if len(parts)>1:raise APIError('SLOW_ZONE_CONTINUATION','Slow-speed zone persistence through a document continuation is not yet audited.')
            start=key(args.slow_speed_zone.start);end=key(args.slow_speed_zone.end)
            if start not in nodes or end not in nodes or nodes.index(start)>=nodes.index(end):raise APIError('SLOW_ZONE_BOUNDARIES','Choose increasing distinct Ends on this Route.')
            parts[0][1].contents[12].values[1:]=[topology.ends[start],topology.ends[end]]
    if changed('overlap'):
        for _,part in parts:set_text(part,7,'');part.contents[9].values[0]=-1
        if args.overlap is not None:
            reference=args.overlap;matches=[row for row in shunting_paths(p) if row['document']==reference.document and row['start_id']==reference.start_id and row['name']==reference.name]
            if len(matches)!=1 or (reference.document,reference.start_id)!=nodes[-1]:raise APIError('OVERLAP_BINDING','Select one exact Shunting/Overlap beginning at the Route terminal End.',reference.model_dump())
            if any(tuple(node) in nodes[:-1] for node in matches[0]['nodes'][1:]):raise APIError('OVERLAP_CYCLE','The Overlap re-enters the preceding Route.')
            set_text(parts[-1][1],7,reference.name);parts[-1][1].contents[9].values[0]=reference.start_id
    return [{'document':document,'properties':route_properties(part)} for document,part in parts]
