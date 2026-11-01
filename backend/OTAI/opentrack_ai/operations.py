"""Native Route/Path/Itinerary construction from independently checked graphs.

Serialization layouts follow the audited builder. Class-shape fixtures are a
fallback for empty lists; their infrastructure is never copied into a network.
"""
import copy
from pathlib import Path

from .archive import APIError,w,END_KINDS
from .drafts import set_text,text
from .topology import Topology,key
from .network_records import upgrade_security_records,route_properties,shunting_paths


def clone(obj):
    return w.ar.GenericArchivedObject(obj.clazz,None,[w.ar.TypedValue(g.encodings[0],g.values[0]) if len(g.encodings)==1 else w.ar.TypedGroup(list(g.encodings),list(g.values)) for g in obj.contents])


class Definitions:
    def __init__(self,project):
        self.project=project;self.templates={}
        for root in [*project.docs.values(),*project.data.values()]:
            for obj in w.objects(root):self.templates.setdefault(w.kind(obj),obj)

    def template(self,name):
        if name not in self.templates:
            from .resources import templates
            shapes,_=templates(self.project.root)
            for kind,obj in shapes.items():self.templates.setdefault(kind,obj)
        if name not in self.templates:raise APIError('ARCHIVE_TEMPLATE_MISSING','Verified serialization class shape is unavailable.',name)
        return self.templates[name]

    def array(self,items=()):
        obj=clone(self.template('NSMutableArray'));w.set_elements(obj,list(items));return obj

    def append(self,array,value):w.set_elements(array,w.elements(array)+[value])

    def next_id(self,end):
        used=[obj.contents[2].values[0] for index in [15,16,17] if end.contents[index].value for obj in w.elements(end.contents[index].value.contents[0].value)]
        value=max([end.contents[19].value,*[v+1 for v in used],0])
        if value>=2147483647:raise APIError('ARRAY_ID_EXHAUSTED','Native signed 32-bit array-ID space is exhausted at this End.')
        end.contents[19].values[0]=value+1;return value

    def indications(self,route,aspects):
        result=clone(self.template('OTSigIndList'));items=[]
        for code in aspects:
            item=clone(self.template('OTSigInd'));item.contents[0].values[0]=code;item.contents[1].values[0]=route;items.append(item)
        result.contents[0].values[0]=self.array(items);return result

    def define_shunting(self,args):
        from .protection import define_shunting
        return define_shunting(self,args)

    def set_route_protection(self,args):
        from .protection import configure_protection
        migrated=upgrade_security_records(self.project);record=self.select_route(args.route,Topology(self.project).route_records())
        parts=configure_protection(self,record,args,True);self.project._graph=None
        return {'kind':'set_route_protection','name':record['name'],'parts':parts,'security_arrays_upgraded':migrated,'native_simulation_verified':False}

    def define_route(self,args):
        p=self.project;topology=Topology(p);nodes=[key(n) for n in args.nodes]
        if len(set(nodes))!=len(nodes):raise APIError('ROUTE_CYCLE','An ordinary Route must be a simple directed movement.')
        if not topology.is_main(nodes[0]) or not topology.is_main(nodes[-1]):raise APIError('NOT_MAIN_SIGNAL','Ordinary Routes begin/end at main-signal Ends.')
        if any(topology.is_main(node) for node in nodes[1:-1]):raise APIError('INTERMEDIATE_MAIN_SIGNAL','A Route must stop at the next main signal; use a Path for multiple Routes.')
        if any(row['name']==args.name for row in topology.route_records()):raise APIError('ROUTE_EXISTS','Route name already exists.',args.name)
        walk=topology.describe_walk(nodes)
        if len(walk['boundaries'])>1:raise APIError('ROUTE_CONTINUATION_CHAIN','Persistence of a Route through more than one document boundary is not yet verified; split at main signals.')
        migrated=upgrade_security_records(p)
        owner=nodes[0];end=topology.ends[owner];route=clone(self.template('OTRoute'));ident=self.next_id(end)
        route_properties(route)
        aspects=args.signal_aspects
        if aspects is None:
            old=w.elements(end.contents[15].value.contents[0].value)
            if old:aspects=[o.contents[0].value for o in w.elements(old[0].contents[4].value.contents[0].value)]
            elif end.contents[11].value.contents[9].values[0]==2:aspects=[0]
            else:raise APIError('SIGNAL_ASPECTS_REQUIRED','Supply explicit aspect codes for a signal system without verified existing Route defaults.')
        local=[topology.ends[node] for node in nodes if node[0]==owner[0]]
        set_text(route,1,args.name);set_text(route,3,args.description)
        route.contents[0].values[0]=self.array(local);route.contents[2].values=[ident,owner[1]]
        route.contents[4].values[0]=self.indications(route,aspects)
        route.contents[5].values=[args.release_point_m,args.advance_notice_m,args.release_time_s,args.reservation_time_s,-1,0]
        occupied=sum(bit for flag,bit in [(args.allow_occupied_entry,1),(args.occupied_entry_use_speed,2),(args.occupied_entry_use_time,4),(args.discrete_for_moving_block,8)] if flag)
        route.contents[6].values=[occupied,args.occupied_entry_speed_kmh,args.occupied_entry_wait_s]
        set_text(route,7,'');route.contents[8].values=[args.approach_zone_length_m,args.approach_zone_speed_kmh]
        route.contents[9].values[0]=-1
        route.contents[10].values=[args.reservation_point_m,int(args.use_reservation_point),int(args.use_release_point if args.use_release_point is not None else args.release_point_m>0)]
        route.contents[11].values[0]=int(args.reserve_with_previous)+2*int(args.slow_speed_only_for_head)
        groups=local[:1]+([local[-1]] if not walk['boundaries'] and len(local)>1 else [])
        route.contents[12].values=[self.array(groups),None,None]
        companion=None
        if walk['boundaries']:
            remote=tuple(walk['boundaries'][0][1]);remote_nodes=[topology.ends[node] for node in nodes if node[0]==remote[0]]
            route.contents[5].values[4]=len(local);companion=clone(route)
            companion.contents[0].values[0]=self.array(remote_nodes);companion.contents[4].values[0]=self.indications(companion,aspects)
            companion.contents[5].values=list(route.contents[5].values);companion.contents[5].values[4]=-1
            remote_groups=remote_nodes[:1]+([remote_nodes[-1]] if len(remote_nodes)>1 else [])
            companion.contents[12].values=[self.array(remote_groups),None,None]
            self.append(topology.ends[remote].contents[15].value.contents[0].value,companion)
        self.append(end.contents[15].value.contents[0].value,route);p._graph=None
        from .protection import configure_protection
        protection=configure_protection(self,{'document':owner[0],'nodes':walk['nodes'],'_object':route,'_companion':companion},args)
        return {'kind':'define_route','name':args.name,'document':owner[0],'start_id':owner[1],'route_id':ident,
            'distance_m':walk['distance_m'],'document_boundaries':len(walk['boundaries']),'signal_aspects':aspects,
            'properties':route_properties(route),'protection_parts':protection,'security_arrays_upgraded':migrated,'native_simulation_verified':False}

    def select_route(self,reference,records):
        matches=[row for row in records if row['document']==reference.document and row['start_id']==reference.start_id and
            (row['route_id']==reference.route_id if reference.route_id is not None else row['name']==reference.name)]
        if len(matches)!=1:raise APIError('ROUTE_REFERENCE','Expected exactly one matching primary Route.',reference.model_dump())
        return matches[0]

    def define_path(self,args):
        p=self.project;topology=Topology(p);_,_,known=p.graph()
        if args.name in known:raise APIError('PATH_EXISTS','Path name already exists.',args.name)
        records=topology.route_records();chain=[self.select_route(reference,records) for reference in args.routes]
        for first,second in zip(chain,chain[1:]):
            if first['end']!=second['start']:raise APIError('PATH_DISCONNECTED','Successive Routes must share the same directional End.',{'first':first['name'],'second':second['name']})
        owner=tuple(chain[0]['start']);end=topology.ends[owner];ident=self.next_id(end)
        path=clone(self.template('OTPath'));path.contents[0].values[0]=self.array([chain[0]['_object']]);set_text(path,1,args.name)
        path.contents[2].values=[ident,owner[1]];set_text(path,3,args.description)
        infos=[]
        for route in chain:
            info=clone(self.template('OTArrayInfo'));info.contents[0].values[0]=route['_object'].contents[1].value
            info.contents[1].values=list(route['_object'].contents[2].values);infos.append(info)
        path.contents[4].values[0]=self.array(infos);self.append(end.contents[17].value.contents[0].value,path);p._graph=None
        return {'kind':'define_path','name':args.name,'document':owner[0],'start_id':owner[1],'path_id':ident,
            'routes':len(chain),'distance_m':sum(r['distance_m'] for r in chain),'native_simulation_verified':False}

    def paths(self):
        result={}
        for document,items in self.project.models.items():
            for end in items:
                if w.kind(end) not in END_KINDS:continue
                for path in w.elements(end.contents[17].value.contents[0].value) if end.contents[17].value else []:
                    name=w.string(path.contents[1].value)
                    if name in result:raise APIError('DUPLICATE_PATH_NAME','Path name must be unambiguous.',name)
                    result[name]=(document,end,path)
        for row in shunting_paths(self.project):
            if row['name'] in result:raise APIError('DUPLICATE_PATH_NAME','Automatic Shunting Path name is ambiguous.',row['name'])
            end=next(end for end in self.project.models[row['document']] if w.kind(end) in END_KINDS and end.contents[0].value==row['start_id'])
            result[row['name']]=(row['document'],end,row['_path'])
        return result

    def define_itinerary(self,args):
        p=self.project;existing=w.elements(p.data['dest'].contents[0].value)
        if any(w.string(row.contents[1].value)==args.name for row in existing):raise APIError('ITINERARY_EXISTS','Itinerary name already exists.',args.name)
        from .itinerary_controls import Itineraries
        controls=Itineraries(p);available=self.paths();selected=[];extended=[];reversals=controls.chain(args.paths)
        for name in args.paths:
            if name not in available:raise APIError('PATH_NOT_FOUND','Itinerary references an unknown Path.',name)
            document,end,path=available[name];info=clone(self.template('OTArrayExtInfo'))
            set_text(info,0,name);info.contents[1].values=list(path.contents[2].values);set_text(info,2,document)
            selected.append(path);extended.append(info)
        document,end,_=available[args.paths[0]];destination=clone(self.template('OTDest'))
        
        
        
        destination.contents[0].values[0]=self.array(selected[:1]);set_text(destination,1,args.name);destination.contents[2].values=[-1,-1]
        set_text(destination,3,args.description);destination.contents[4].values[0]=self.array(extended)
        from .itinerary_margins import make_point,native_sort
        margin_values=native_sort([{'position_m':point.position_m,'safety_margin_m':point.safety_margin_m} for point in args.safety_margins]) if args.safety_margins else []
        margins=clone(self.template('OTSafetyMarginArray'));margins.contents[0].values[0]=self.array([make_point(point) for point in margin_values]);destination.contents[5].values[0]=margins
        self.append(p.docs[document].contents[5].value.contents[0].value,destination)
        info=clone(self.template('OTDestInfo'));set_text(info,1,args.name);set_text(info,2,str(p.project/'OTDocuments'/(document+'.opentrack')))
        info.contents[3].values[0]=end.contents[0].value;info.contents[4].values[0]=self.array(extended)
        self.append(p.data['dest'].contents[0].value,info)
        return {'kind':'define_itinerary','name':args.name,'paths':args.paths,'reversals':reversals,'document':document,'safety_margin_count':len(margin_values),'native_simulation_verified':False}


def itinerary_owners(project):
    owners={}
    for document,doc in project.docs.items():
        for destination in w.elements(doc.contents[5].value.contents[0].value):
            if w.kind(destination)!='OTDest':continue
            name=w.string(destination.contents[1].value)
            if name in owners:raise APIError('DUPLICATE_ITINERARY_NAME','Itinerary has more than one native document definition.',name)
            owners[name]=document
    return owners


def rebase_itinerary_documents(project,base):
    owners=itinerary_owners(project);changes=[]
    for info in w.elements(project.data['dest'].contents[0].value):
        name=w.string(info.contents[1].value)
        if name not in owners:continue
        old=w.string(info.contents[2].value);new=str(Path(base)/'OTDocuments'/(owners[name]+'.opentrack'))
        if old.replace('\\','/')!=new.replace('\\','/'):
            set_text(info,2,new);changes.append({'itinerary':name,'before':old,'after':new})
    return changes
