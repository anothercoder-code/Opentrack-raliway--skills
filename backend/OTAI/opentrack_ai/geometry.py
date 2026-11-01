"""Native DVG geometry edits, independent of the OpenTrack process.

Coordinates are drawing coordinates; lengths are integer metres. Every change
is applied to an in-memory archive copy and later persisted as an immutable
draft. Manual chapters 3.3--3.6 and audited encodeWithCoder layouts are the
contracts; this module does not claim complete original editor parity.
"""
import copy
import re
import uuid

from .archive import APIError,w,END_KINDS
from .drafts import set_text,text
from .operations import Definitions,clone


KINDS={'create_document','create_vertex','move_vertex','vertex_attributes','create_edge','edge_attributes',
    'reverse_edge','create_signal','link_connectors','unlink_connector','merge_elements','reset_elements',
    'exclusion_link','delete_graphic','split_edge','worksheet_attributes','signal_attributes'}


def put(obj,index,value):obj.contents[index].values[0]=value


class Geometry:
    def __init__(self,project):
        from .legacy_geometry_guard import reject
        reject()  
        self.p=project;self.definitions=Definitions(project);self.aliases={}

    def pool(self,document):
        if document not in self.p.docs:raise APIError('DOCUMENT_NOT_FOUND','Unknown infrastructure document.',document)
        return self.p.models[document]

    def sync(self,document):
        w.set_elements(self.p.docs[document].contents[2].value,self.p.models[document]);self.p._graph=None

    def allocate(self,document):
        state=self.p.scenario.setdefault('editor_state',{}).setdefault('next_graphic_id',{})
        value=max(state.get(document,0),max((o.contents[0].value+1 for o in self.pool(document)),default=0))
        if value>=2147483647:raise APIError('GRAPHIC_ID_EXHAUSTED','Native signed 32-bit graphic ID space is exhausted.')
        state[document]=value+1;return value

    def object(self,document,ident,kinds=None):
        found=[o for o in self.pool(document) if o.contents[0].value==ident]
        if len(found)!=1:raise APIError('GRAPHIC_NOT_FOUND','Expected exactly one local graphic ID.',{'document':document,'id':ident})
        if kinds and w.kind(found[0]) not in kinds:raise APIError('GRAPHIC_TYPE','Graphic has a different class.',{'document':document,'id':ident,'class':w.kind(found[0])})
        return found[0]

    def end(self,reference):
        if hasattr(reference,'vertex_key'):
            alias=(reference.document,reference.vertex_key)
            if alias not in self.aliases:raise APIError('VERTEX_KEY_NOT_FOUND','A batch vertex_key must be created earlier in the same edit.',alias)
            ident=self.aliases[alias][reference.side]
        else:ident=reference.end_id
        return reference.document,self.object(reference.document,ident,END_KINDS)

    def edge(self,reference):return self.object(reference.document,reference.edge_id,{'OTEdgeModel'})

    def wrapper(self,kind,items=()):
        obj=clone(self.definitions.template(kind));put(obj,0,self.definitions.array(items));return obj

    def graphic(self,kind,document):
        obj=clone(self.definitions.template(kind));put(obj,0,self.allocate(document))
        for index,value in [(1,0.),(2,0.),(3,0.),(4,0),(5,0),(6,None)]:put(obj,index,value)
        return obj

    def element(self,document,members=()):
        obj=self.graphic('OTElement',document);put(obj,7,self.definitions.array(members));self.pool(document).append(obj);return obj

    def replace(self,document,old,new):
        
        
        for root in list(w.objects(self.p.docs[document])):
            for group in root.contents:
                group.values=[new if value is old else value for value in group.values]
        self.p.models[document]=[new if value is old else value for value in self.pool(document)]
        self.sync(document)

    def merge(self,document,elements):
        unique={id(o):o for o in elements};selected=list(unique.values())
        if not selected:return None
        target=min(selected,key=lambda o:o.contents[0].value);members={}
        for element in selected:
            for end in w.elements(element.contents[7].value):members[id(end)]=end
        for end in members.values():put(end,7,target)
        put(target,7,self.definitions.array(sorted(members.values(),key=lambda o:o.contents[0].value)))
        removed={id(o) for o in selected if o is not target}
        self.p.models[document]=[o for o in self.pool(document) if id(o) not in removed]
        self.sync(document);return target

    def apply(self,args):
        result=getattr(self,args.kind)(args)
        for document in self.p.docs:self.sync(document)
        return {'kind':args.kind,**result,'native_editor_parity_verified':False}

    def create_document(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        p=self.p
        if args.document.casefold() in {name.casefold() for name in p.docs}:raise APIError('DOCUMENT_EXISTS','Document filename already exists, including a Windows case alias.',args.document)
        if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]',args.document,re.I):raise APIError('DOCUMENT_NAME','Reserved Windows document filename.')
        if len(p.docs)>=100:raise APIError('PROJECT_SIZE','At most 100 infrastructure documents are supported.')
        document=clone(self.definitions.template('OTDocument'));put(document,2,self.definitions.array())
        put(document,5,self.wrapper('OTMutableArray'));put(document,12,self.wrapper('OTOccInfoList'));put(document,13,None)
        for index in [8,9,10]:document.contents[index].values=[0.,0.,args.width,args.height]
        put(document,11,1.);set_text(document,19,'');set_text(document,20,'')
        set_text(document,18,'OTAI-'+uuid.uuid4().hex.upper())
        path=p.project/'OTDocuments'/(args.document+'.opentrack');version=p.versions[str(next(iter(p.doc_paths.values()))) ]
        p.docs[args.document]=document;p.doc_paths[args.document]=path;p.versions[str(path)]=version;p.models[args.document]=[]
        return {'document':args.document,'width':args.width,'height':args.height}

    def create_vertex(self,args):
        document=args.document;self.pool(document)
        alias=(document,args.vertex_key)
        if args.vertex_key and alias in self.aliases:raise APIError('VERTEX_KEY_EXISTS','Batch vertex_key must be unique within its document.',alias)
        ends=[self.graphic('OTEndModel',document) for _ in range(2)];ids=[e.contents[0].value for e in ends]
        for side,end in enumerate(ends):
            for index,value in [(1,float(args.angle_degrees)),(2,args.x),(3,args.y),(4,side+1),(8,ids[1-side]),
                    (9,None),(10,None),(11,None),(12,None),(13,None),(14,-99999.),(19,0),(20,0),(21,0.),(22,0)]:put(end,index,value)
            for index,kind in [(15,'OTRouteList'),(16,'OTShuntingList'),(17,'OTPathList')]:put(end,index,self.wrapper(kind))
            end.contents[23].values=[0,0];set_text(end,18,args.names[side] if side<len(args.names) else '')
            element=self.element(document,[end]);put(end,7,element)
        self.pool(document).extend(ends)
        if args.vertex_key:self.aliases[alias]=ids
        return {'document':document,'end_ids':ids,'vertex_key':args.vertex_key,'x':args.x,'y':args.y}

    def worksheet_attributes(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        self.pool(args.document);doc=self.p.docs[args.document];fields={}
        for name,index in [('grid_x',3),('grid_y',4)]:
            value=getattr(args,name)
            if value is not None:fields[name]={'before':doc.contents[index].value,'after':value};put(doc,index,value)
        for name,bit in [('show_grid',4),('show_edge_direction',1),('big_vertices',2)]:
            value=getattr(args,name)
            if value is not None:
                flags=doc.contents[1].value;fields[name]={'before':bool(flags&bit),'after':value}
                put(doc,1,flags|bit if value else flags&~bit)
        for name,index in [('width',2),('height',3)]:
            value=getattr(args,name)
            if value is not None:
                fields[name]={'before':doc.contents[9].values[index],'after':value}
                doc.contents[9].values[index]=value;doc.contents[10].values[index]=value
        return {'document':args.document,'fields':fields}

    def signal_attributes(self,args):
        obj=self.object(args.document,args.signal_id,{'OTSignalModel'});fields={}
        if args.name is not None:fields['name']={'before':w.string(obj.contents[13].value),'after':args.name};set_text(obj,13,args.name)
        for name,index,slot in [('signal_type',8,0),('main_signal_type',8,1),('sight_distance_m',9,1),('release_speed_kmh',9,3),('delay_s',16,0)]:
            value=getattr(args,name)
            if value is not None:
                fields[name]={'before':obj.contents[index].values[slot],'after':value};obj.contents[index].values[slot]=value
        return {'document':args.document,'signal_id':args.signal_id,'end_id':obj.contents[7].value.contents[0].value,'fields':fields}

    def move_vertex(self,args):
        document,end=self.end(args.end);pair=self.object(document,end.contents[8].value,END_KINDS)
        before=[end.contents[2].value,end.contents[3].value,end.contents[1].value]
        for obj in [end,pair]:
            put(obj,2,args.x);put(obj,3,args.y)
            if args.angle_degrees is not None:put(obj,1,float(args.angle_degrees))
            signal=obj.contents[11].value
            if signal:
                put(signal,2,args.x);put(signal,3,args.y)
                if args.angle_degrees is not None:put(signal,1,float(args.angle_degrees))
        return {'document':document,'end_ids':[end.contents[0].value,pair.contents[0].value],'before':before,'after':[args.x,args.y,end.contents[1].value]}

    def vertex_attributes(self,args):
        document,end=self.end(args.end);changed={}
        fields={'kilometre_point':14,'station_reference_type':20,'switch_time_s':21,'default_second_leg':22}
        if args.name is not None:changed['name']={'before':w.string(end.contents[18].value),'after':args.name};set_text(end,18,args.name)
        for name,index in fields.items():
            value=getattr(args,name)
            if value is not None:
                value=int(value) if name=='default_second_leg' else value
                changed[name]={'before':end.contents[index].value,'after':value};put(end,index,value)
        for name,index in [('insulated_joint',0),('axle_counter',1)]:
            value=getattr(args,name)
            if value is not None:
                changed[name]={'before':end.contents[23].values[index],'after':int(value)};end.contents[23].values[index]=int(value)
        return {'document':document,'end_id':end.contents[0].value,'fields':changed}

    def speeds(self,edge,entries):
        names=[entry.train_type for entry in entries]
        if len(set(names))!=len(names):raise APIError('DUPLICATE_TRAIN_TYPE','Speed table keys must be unique.')
        keys=[];pairs=[]
        for entry in entries:
            key=text(edge,entry.train_type);speed=clone(self.definitions.template('OTSpeed'))
            speed.contents[0].values=[key];put(speed,1,entry.forward_kmh);put(speed,2,entry.reverse_kmh);put(speed,3,0)
            keys.append(key);pairs.extend([w.ar.TypedValue(b'@',key),w.ar.TypedValue(b'@',speed)])
        dictionary=clone(self.definitions.template('NSMutableDictionary'));dictionary.contents=[w.ar.TypedValue(b'i',len(keys)),*pairs]
        put(edge,15,self.definitions.array(keys));put(edge,16,dictionary)

    def create_edge(self,args):
        document,first=self.end(args.first);second_document,second=self.end(args.second)
        if second_document!=document:raise APIError('EDGE_DOCUMENT','Edges stay within one document; use reciprocal connectors between documents.')
        if first is second or first.contents[8].value==second.contents[0].value:raise APIError('EDGE_LOOP','An Edge cannot connect a half-vertex to itself or its related half.')
        for end in [first,second]:
            if w.kind(end)=='OTConnModel':raise APIError('CONNECTOR_SIDE','The connector half must remain free of Edges.')
            if all(end.contents[i].value is not None for i in [9,10]):raise APIError('VERTEX_DEGREE','A DVG half can have at most two incident Edges.',end.contents[0].value)
        if any(first.contents[i].value and second in [first.contents[i].value.contents[j].value for j in [7,8]] for i in [9,10]):
            raise APIError('EDGE_EXISTS','The two half-vertices already have a direct Edge.')
        edge=self.graphic('OTEdgeModel',document);put(edge,7,first);put(edge,8,second)
        edge.contents[9].values=[1,args.length_m,args.radius_m,args.gradient_per_mille,1,1]
        edge.contents[10].values=[100.,0.];put(edge,11,int(all(s.forward_kmh==s.reverse_kmh for s in args.speeds)))
        for i in [13,14,17,18]:put(edge,i,None)
        for i,value in [(12,''),(19,args.track_name or ''),(20,args.line_name or '')]:set_text(edge,i,value)
        self.speeds(edge,args.speeds)
        for end in [first,second]:put(end,9 if end.contents[9].value is None else 10,edge)
        self.pool(document).append(edge);element=self.merge(document,[first.contents[7].value,second.contents[7].value])
        return {'document':document,'edge_id':edge.contents[0].value,'end_ids':[first.contents[0].value,second.contents[0].value],
            'length_m':args.length_m,'element_id':element.contents[0].value}

    def edge_attributes(self,args):
        edge=self.edge(args.edge);before={'length_m':edge.contents[9].values[1],'radius_m':edge.contents[9].values[2],'gradient_per_mille':edge.contents[9].values[3]}
        for name,index in [('length_m',1),('radius_m',2),('gradient_per_mille',3)]:
            value=getattr(args,name)
            if value is not None:edge.contents[9].values[index]=value
        for name,bit in [('equal_speed',1),('rack_rail',2)]:
            value=getattr(args,name)
            if value is not None:put(edge,11,(edge.contents[11].value|bit) if value else (edge.contents[11].value&~bit))
        for name,index in [('contact_wire_mm2',0),('tunnel_m2',1)]:
            value=getattr(args,name)
            if value is not None:edge.contents[10].values[index]=value
        if args.speeds is not None:self.speeds(edge,args.speeds)
        if args.equal_speed is True:
            for speed in w.objects(edge.contents[16].value):
                if w.kind(speed)=='OTSpeed':put(speed,2,speed.contents[1].value)
        for name,index in [('track_name',19),('line_name',20)]:
            value=getattr(args,name)
            if value is not None:set_text(edge,index,value)
        return {'document':args.edge.document,'edge_id':args.edge.edge_id,'before':before,'after':{
            'length_m':edge.contents[9].values[1],'radius_m':edge.contents[9].values[2],'gradient_per_mille':edge.contents[9].values[3]}}

    def reverse_edge(self,args):
        edge=self.edge(args.edge);first,second=edge.contents[7].value,edge.contents[8].value
        put(edge,7,second);put(edge,8,first);edge.contents[9].values[3]=-edge.contents[9].values[3]
        for speed in w.objects(edge.contents[16].value):
            if w.kind(speed)=='OTSpeed':speed.contents[1].values,speed.contents[2].values=speed.contents[2].values,speed.contents[1].values
        return {'document':args.edge.document,'edge_id':args.edge.edge_id,'end_ids':[second.contents[0].value,first.contents[0].value],'gradient_per_mille':edge.contents[9].values[3]}

    def create_signal(self,args):
        document,end=self.end(args.end);pair=self.object(document,end.contents[8].value,END_KINDS)
        if w.kind(end)=='OTConnModel' or w.kind(pair)=='OTConnModel':raise APIError('CONNECTOR_SIGNAL','Signals cannot be attached to a connector or its related half.')
        if end.contents[11].value:raise APIError('SIGNAL_EXISTS','The directional half already has a Signal.')
        signal=self.graphic('OTSignalModel',document)
        for index in [1,2,3]:put(signal,index,end.contents[index].value)
        put(signal,4,end.contents[4].value);put(signal,7,end)
        signal.contents[8].values=[args.signal_type,args.main_signal_type,2]
        signal.contents[9].values=[2,args.sight_distance_m,640,args.release_speed_kmh]
        put(signal,10,self.definitions.indications(signal,[0]));put(signal,11,0);put(signal,12,7);set_text(signal,13,args.name)
        for i in [14,15]:put(signal,i,self.definitions.array())
        put(signal,16,args.delay_s);put(end,11,signal);self.pool(document).append(signal)
        return {'document':document,'end_id':end.contents[0].value,'signal_id':signal.contents[0].value,'name':args.name,'display_system':'metric'}

    def link_connectors(self,args):
        first_document,first=self.end(args.first);second_document,second=self.end(args.second)
        if first is second or first_document==second_document and first.contents[8].value==second.contents[0].value:raise APIError('CONNECTOR_SELF','Connectors must belong to different DVG vertices.')
        for document,end in [(first_document,first),(second_document,second)]:
            pair=self.object(document,end.contents[8].value,END_KINDS)
            if any(end.contents[i].value for i in [9,10,11]) or pair.contents[11].value:raise APIError('CONNECTOR_OCCUPIED_SIDE','The connector half needs no Edge/Signal, and its related half needs no Signal.')
            if w.kind(end)=='OTConnModel':raise APIError('CONNECTOR_ALREADY_LINKED','Unlink the existing connector before relinking.')
        originals=[(first_document,first,second_document,second),(second_document,second,first_document,first)]
        for document,end,remote,other in originals:
            connector=clone(self.definitions.template('OTConnModel'));connector.contents[:24]=clone(end).contents
            set_text(connector,24,document);set_text(connector,25,remote);put(connector,26,other.contents[0].value);put(connector,27,0)
            self.replace(document,end,connector)
        return {'connectors':[[first_document,first.contents[0].value],[second_document,second.contents[0].value]]}

    def unlink_pair(self,document,connector):
        remote=w.string(connector.contents[25].value);target=self.object(remote,connector.contents[26].value,{'OTConnModel'})
        if w.string(target.contents[25].value)!=document or target.contents[26].value!=connector.contents[0].value:raise APIError('CONNECTOR_PAIR','The connector link is not reciprocal.')
        for owner,old in [(document,connector),(remote,target)]:
            new=clone(self.definitions.template('OTEndModel'));new.contents=clone(old).contents[:24];self.replace(owner,old,new)
        return [[document,connector.contents[0].value],[remote,target.contents[0].value]]

    def unlink_connector(self,args):
        document,end=self.end(args.end)
        if w.kind(end)!='OTConnModel':raise APIError('NOT_CONNECTOR','Selected half is not a connector.')
        self.dependencies({(document,end.contents[0].value)},set(),False)
        return {'connectors':self.unlink_pair(document,end)}

    def selected_elements(self,args):
        ends=[self.object(args.document,i,END_KINDS) for i in args.end_ids]
        for ident in args.edge_ids:
            edge=self.object(args.document,ident,{'OTEdgeModel'});ends.extend(edge.contents[i].value for i in [7,8])
        if not ends:raise APIError('EMPTY_SELECTION','Select at least one End or Edge.')
        return list({id(e.contents[7].value):e.contents[7].value for e in ends}.values())

    def merge_elements(self,args):
        elements=self.selected_elements(args);before=sorted(o.contents[0].value for o in elements);result=self.merge(args.document,elements)
        return {'document':args.document,'before_element_ids':before,'element_id':result.contents[0].value}

    def reset_elements(self,args):
        document=args.document;selected=self.selected_elements(args);element_ids={id(o) for o in selected}
        members={id(e):e for o in selected for e in w.elements(o.contents[7].value)};parent={ident:ident for ident in members}
        def find(ident):
            while parent[ident]!=ident:parent[ident]=parent[parent[ident]];ident=parent[ident]
            return ident
        for edge in self.pool(document):
            if w.kind(edge)!='OTEdgeModel':continue
            a,b=(id(edge.contents[i].value) for i in [7,8])
            if a in parent and b in parent:parent[find(a)]=find(b)
        groups={}
        for ident,end in members.items():groups.setdefault(find(ident),[]).append(end)
        self.p.models[document]=[o for o in self.pool(document) if id(o) not in element_ids];result=[]
        for ends in sorted(groups.values(),key=lambda items:min(e.contents[0].value for e in items)):
            element=self.element(document,ends);result.append(element.contents[0].value)
            for end in ends:put(end,7,element)
        return {'document':document,'element_ids':result,'default_component_count':len(groups)}

    def exclusion_link(self,args):
        document=args.edge.document;edge=self.edge(args.edge);target=self.edge(args.target) if args.target else None
        if target and args.target.document!=document:raise APIError('EXCLUSION_DOCUMENT','Native direct exclusion links stay within one document.')
        if target is edge:raise APIError('EXCLUSION_SELF','An Edge cannot exclude itself.')
        if target and target.contents[14].value not in [None,edge]:raise APIError('EXCLUSION_TARGET_USED','Target already has an incoming native exclusion link.')
        old=edge.contents[13].value
        if old:put(old,14,None)
        put(edge,13,target)
        if target:put(target,14,edge)
        return {'document':document,'edge_id':args.edge.edge_id,'target_id':target.contents[0].value if target else None}

    def dependencies(self,removed_ends,removed_edges,cascade,shunting_ends=None):
        from .topology import Topology
        topology=Topology(self.p);records=topology.route_records()
        shunting_records=topology.shunting_records();shunting_ends=removed_ends if shunting_ends is None else shunting_ends
        affected_shuntings=[r for r in shunting_records if any(tuple(n) in shunting_ends for n in r['nodes']) or any((e['document'],e['edge_id']) in removed_edges for e in r['edges'])]
        overlap_keys={(r['document'],r['start_id'],r['name']) for r in affected_shuntings}
        affected=[r for r in records if any(tuple(n) in removed_ends for n in r['nodes']) or
            any((e['document'],e['edge_id']) in removed_edges for e in r['edges']) or
            any(tuple(n) in removed_ends for boundary in r['boundaries'] for n in boundary) or
            any((doc,obj.contents[9].value,w.string(obj.contents[7].value)) in overlap_keys for doc,obj in [(r['document'],r['_object']),*([(r['end'][0],r['_companion'])] if r['_companion'] else [])])]
        affected.extend(affected_shuntings)
        keys={(r['document'],r['start_id'],r['name']) for r in affected};traces=self.p.graph()[2]
        paths={name for name,trace in traces.items() if any((*tuple(r['start']),r['name']) in keys for r in trace['routes'])}
        infos=w.elements(self.p.data['dest'].contents[0].value)
        itineraries={w.string(info.contents[1].value) for info in infos if any(w.string(ext.contents[0].value) in paths for ext in w.elements(info.contents[4].value))}
        courses={self.p.service(course)['course_id'] for course in self.p.courses() if itineraries.intersection(self.p.service(course)['itineraries'])}
        result={'routes':sorted(keys),'paths':sorted(paths),'itineraries':sorted(itineraries),'courses':sorted(courses)}
        if any(result.values()) and not cascade:raise APIError('GRAPHIC_IN_USE','Review the dependent definitions/services; explicit cascade deletes them only in the new draft.',result)
        if not any(result.values()):return result
        removed_route_objects={id(o) for r in affected for o in [r['_object'],r['_companion']] if o is not None}
        for document,items in self.p.models.items():
            for end in items:
                if w.kind(end) not in END_KINDS:continue
                array=end.contents[15].value.contents[0].value;w.set_elements(array,[r for r in w.elements(array) if id(r) not in removed_route_objects])
                if end.contents[16].value:
                    array=end.contents[16].value.contents[0].value;removed_paths={id(r['_path']) for r in affected_shuntings}
                    w.set_elements(array,[path for path in w.elements(array) if id(path) not in removed_paths])
                array=end.contents[17].value.contents[0].value;w.set_elements(array,[p for p in w.elements(array) if w.string(p.contents[1].value) not in paths])
            destinations=self.p.docs[document].contents[5].value.contents[0].value
            w.set_elements(destinations,[d for d in w.elements(destinations) if w.string(d.contents[1].value) not in itineraries])
        w.set_elements(self.p.data['dest'].contents[0].value,[i for i in infos if w.string(i.contents[1].value) not in itineraries])
        from opentrack_course_schema import course_array
        w.set_elements(course_array(self.p.data['courses']),[c for c in self.p.courses() if w.string(c.contents[0].value) not in courses])
        table=self.p.data['timetable'];groups=table.contents[1:];kept=[]
        for index in range(0,len(groups),2):
            if w.string(groups[index+1].value.contents[1].value) not in courses:kept.extend(groups[index:index+2])
        table.contents=[w.ar.TypedValue(b'i',len(kept)//2),*kept];self.p._graph=None
        return result

    def delete_graphic(self,args):
        document=args.document;obj=self.object(document,args.object_id);kind=w.kind(obj)
        if kind not in END_KINDS|{'OTEdgeModel','OTSignalModel'}:raise APIError('DELETE_CLASS_UNSUPPORTED','This geometry operation handles vertices, Edges and Signals; other worksheet objects require their own dependency rules.',kind)
        removed={id(obj):obj};ends=[];edges=[];signals=[]
        if kind in END_KINDS:
            ends=[obj,self.object(document,obj.contents[8].value,END_KINDS)]
            for end in ends:
                edges.extend(end.contents[i].value for i in [9,10] if end.contents[i].value)
                if end.contents[11].value:signals.append(end.contents[11].value)
                if end.contents[13].value:raise APIError('MEASURING_INSTRUMENT_DEPENDENCY','Detach the vertex measuring instrument before deleting this vertex.')
        elif kind=='OTEdgeModel':edges=[obj]
        else:signals=[obj]
        removed.update({id(o):o for o in [*ends,*edges,*signals]})
        affected={(document,e.contents[0].value) for e in ends}
        affected.update((document,s.contents[7].value.contents[0].value) for s in signals)
        dependencies=self.dependencies(affected,{(document,e.contents[0].value) for e in edges},args.cascade_definitions_and_services,{(document,e.contents[0].value) for e in ends})
        for end in ends:
            if w.kind(end)=='OTConnModel':self.unlink_pair(document,end)
        
        removed_end_ids={e.contents[0].value for e in ends}
        for end in self.pool(document):
            if w.kind(end) not in END_KINDS:continue
            for index in [9,10,11]:
                if id(end.contents[index].value) in removed:put(end,index,None)
        for edge in edges:
            for index,opposite in [(13,14),(14,13)]:
                other=edge.contents[index].value
                if other:put(other,opposite,None)
        labels={id(o.contents[6].value) for o in removed.values() if o.contents[6].value}
        self.p.models[document]=[o for o in self.pool(document) if id(o) not in removed and id(o) not in labels and
            not (w.kind(o) in END_KINDS and o.contents[0].value in removed_end_ids)]
        remaining={id(e) for e in self.pool(document) if w.kind(e) in END_KINDS};empty=set()
        for element in self.pool(document):
            if w.kind(element)!='OTElement':continue
            members=[e for e in w.elements(element.contents[7].value) if id(e) in remaining]
            put(element,7,self.definitions.array(members))
            if not members:empty.add(id(element))
        self.p.models[document]=[o for o in self.pool(document) if id(o) not in empty]
        return {'document':document,'removed_ids':sorted({o.contents[0].value for o in removed.values()}),'deleted_dependencies':dependencies}

    def split_edge(self,args):
        from .models import CreateVertex
        document=args.edge.document;edge=self.edge(args.edge);length=edge.contents[9].values[1]
        if args.first_length_m>=length:raise APIError('EDGE_SPLIT_LENGTH','Both resulting Edges need positive integer lengths.')
        if edge.contents[13].value or edge.contents[14].value:raise APIError('EDGE_SPLIT_EXCLUSION','Split of a native direct exclusion link needs an explicit link redistribution; it is not inferred.')
        first,last=(edge.contents[i].value for i in [7,8]);fraction=args.first_length_m/length
        x=args.x if args.x is not None else first.contents[2].value*(1-fraction)+last.contents[2].value*fraction
        y=args.y if args.y is not None else first.contents[3].value*(1-fraction)+last.contents[3].value*fraction
        made=self.create_vertex(CreateVertex(document=document,x=x,y=y,vertex_key=args.vertex_key,kind='create_vertex'))
        left,right=[self.object(document,i,END_KINDS) for i in made['end_ids']]
        new=clone(edge);put(new,0,self.allocate(document));put(new,6,None)
        put(edge,8,left);put(new,7,right);put(new,8,last)
        edge.contents[9].values[1]=args.first_length_m;new.contents[9].values[1]=length-args.first_length_m
        for index in [15,16]:put(new,index,copy.deepcopy(edge.contents[index].value))
        for index in [9,10]:
            if last.contents[index].value is edge:put(last,index,new)
        put(left,9,edge);put(right,9,new);self.pool(document).append(new)
        
        
        self.merge(document,[first.contents[7].value,last.contents[7].value,left.contents[7].value,right.contents[7].value])
        updated=[]
        for owner in self.pool(document):
            if w.kind(owner) not in END_KINDS:continue
            routes=w.elements(owner.contents[15].value.contents[0].value)
            shunting_paths=w.elements(owner.contents[16].value.contents[0].value) if owner.contents[16].value else []
            shuntings=[w.elements(path.contents[0].value)[0] for path in shunting_paths]
            for route in [*routes,*shuntings]:
                old=w.elements(route.contents[0].value);revised=[]
                if old and old[0] is last and owner.contents[8].value==first.contents[0].value:revised.append(left)
                elif old and old[0] is first and owner.contents[8].value==last.contents[0].value:revised.append(right)
                for index,end in enumerate(old):
                    if index:
                        prior=old[index-1]
                        if end is last and prior.contents[8].value==first.contents[0].value:revised.append(left)
                        elif end is first and prior.contents[8].value==last.contents[0].value:revised.append(right)
                    revised.append(end)
                if len(revised)!=len(old):
                    put(route,0,self.definitions.array(revised))
                    if route.contents[5].values[4]>=0:route.contents[5].values[4]=len(revised)
                    updated.append(w.string(route.contents[1].value))
        return {'document':document,'original_edge_id':args.edge.edge_id,'new_edge_id':new.contents[0].value,
            'end_ids':made['end_ids'],'lengths_m':[args.first_length_m,length-args.first_length_m],
            'routes_updated':updated,'safety_policy':'Original exclusive element preserved; reset_elements can explicitly recompute default components.'}
