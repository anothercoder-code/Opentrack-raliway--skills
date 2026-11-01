"""Bounded native Itinerary inspector data commands; see itinerary-controls.md.

Uses explicit names/Path selections instead of native UI state. Original
first-occurrence Course renaming, copy defaults, Add and replacement borders
are preserved. Cache refresh is an explicit composition with fillArrayInfo.
"""
import copy
from pathlib import Path

from .archive import APIError,w
from .drafts import set_text,text

KINDS={'edit_itinerary_margins','edit_itinerary','rename_itinerary','duplicate_itinerary','delete_itineraries',
       'reset_itinerary_catalog','append_itinerary','replace_itinerary_paths'}


def definitions(project):
    result={}
    for document,root in project.docs.items():
        for dest in w.elements(root.contents[5].value.contents[0].value):
            if w.kind(dest)!='OTDest':raise APIError('ITINERARY_LAYOUT','Unexpected document Itinerary record.')
            name=w.string(dest.contents[1].value)
            if name in result:raise APIError('DUPLICATE_ITINERARY_NAME','Document Itinerary names must be unique.',name)
            result[name]=(document,dest)
    return result


def catalog_infos(project):
    result={}
    for info in w.elements(project.data['dest'].contents[0].value):
        if w.kind(info)!='OTDestInfo':raise APIError('ITINERARY_LAYOUT','Unexpected catalog Itinerary record.')
        name=w.string(info.contents[1].value)
        if name in result:raise APIError('DUPLICATE_ITINERARY_NAME','Catalog Itinerary names must be unique.',name)
        result[name]=info
    return result


def course_usage(project):
    result={}
    for course in project.courses():
        for index,value in enumerate(w.elements(course.contents[2].value) if course.contents[2].value else []):
            result.setdefault(w.string(value),[]).append({'course_id':w.string(course.contents[0].value),'index':index})
    return result


def path_references(dest):
    return [{'name':w.string(info.contents[0].value),'path_id':info.contents[1].values[0],
        'start_end_id':info.contents[1].values[1],'document':Path(w.string(info.contents[2].value)).stem}
        for info in w.elements(dest.contents[4].value)]


class Itineraries:
    def __init__(self,project):
        from .operations import Definitions
        self.project=project;self.builder=Definitions(project)
        self.defs=definitions(project);self.infos=catalog_infos(project)
        self.available=self.builder.paths();self._traces=None

    def require(self,name):
        if name not in self.defs:raise APIError('ITINERARY_NOT_LOADED','A loaded document definition is required.',name)
        return self.defs[name]

    def fresh(self,name):
        if name in self.defs or name in self.infos:raise APIError('ITINERARY_EXISTS','Use a fresh unique Itinerary name.',name)

    def resolve(self,names):
        result=[]
        for name in names:
            if name not in self.available:raise APIError('PATH_NOT_FOUND','Unknown loaded Path.',name)
            result.append(self.available[name])
        return result

    def names(self,dest):
        refs=path_references(dest)
        if not refs:raise APIError('ITINERARY_EMPTY','A loaded Itinerary must have Path references.')
        for ref in refs:
            _,end,path=self.resolve([ref['name']])[0];document=self.available[ref['name']][0]
            if (ref['document'],ref['start_end_id'],ref['path_id'])!=(document,end.contents[0].value,path.contents[2].values[0]):
                raise APIError('ITINERARY_PATH_REFERENCE','Saved Path identity does not match its exact loaded definition.',ref)
        return [ref['name'] for ref in refs]

    def traces(self):
        if self._traces is None:
            self._traces=dict(self.project.graph()[2])
            from .network_records import shunting_paths
            for row in shunting_paths(self.project):
                self._traces[row['name']]={'routes':[{'start':row['nodes'][0],'end':row['nodes'][-1],'nodes':row['nodes']}]}
        return self._traces

    def first(self,name):return tuple(self.traces()[name]['routes'][0]['start'])
    def last(self,name):return tuple(self.traces()[name]['routes'][-1]['end'])

    def related(self,node):
        from .topology import Topology
        topology=Topology(self.project);end=topology.require(node);other=(node[0],end.contents[8].value);pair=topology.require(other)
        if w.kind(pair)=='OTConnModel':
            if pair.contents[25].value is None:raise APIError('CONNECTOR_PAIR','Missing remote connector document.')
            remote=(Path(w.string(pair.contents[25].value)).stem,pair.contents[26].value);connector=topology.require(remote)
            if w.kind(connector)!='OTConnModel':raise APIError('CONNECTOR_PAIR','Remote object is not a connector.')
            other=(remote[0],connector.contents[8].value);topology.require(other)
        return other

    def chain(self,names):
        self.resolve(names);reversals=[]
        if len(names)>1000:raise APIError('ITINERARY_SIZE','One Itinerary supports at most 1000 Paths.')
        for first,second in zip(names,names[1:]):
            if self.available[first][2] is self.available[second][2]:raise APIError('ITINERARY_REPEAT_PATH','Native continuation excludes the immediately preceding Path.',first)
            finish=self.last(first);start=self.first(second)
            if finish==start:continue
            related=self.related(start);nodes=[tuple(node) for node in self.traces()[first]['routes'][-1]['nodes']]
            if related not in nodes or nodes.index(related)==len(nodes)-1:
                raise APIError('ITINERARY_DISCONNECTED','Next Path must start at the previous last End, or set back within its final Route.',{'first':first,'second':second})
            reversals.append({'previous_path':first,'next_path':second,'at':list(related),'next_direction':list(start),
                'last_route_index':nodes.index(related)})
        return reversals

    def ext(self,names):
        from .operations import clone
        result=[]
        for name in names:
            document,_,path=self.available[name];info=clone(self.builder.template('OTArrayExtInfo'))
            set_text(info,0,name);info.contents[1].values=list(path.contents[2].values);set_text(info,2,document);result.append(info)
        return result

    def write_paths(self,dest,names):
        dest.contents[0].values[0]=self.builder.array([self.available[names[0]][2]])
        dest.contents[4].values[0]=self.builder.array(self.ext(names))

    def sync(self,name,document,dest):
        from .operations import clone
        info=self.infos.get(name)
        if info is None:
            info=clone(self.builder.template('OTDestInfo'));self.builder.append(self.project.data['dest'].contents[0].value,info);self.infos[name]=info
        names=self.names(dest);set_text(info,1,name);set_text(info,2,str(self.project.project/'OTDocuments'/(document+'.opentrack')))
        info.contents[3].values[0]=self.first(names[0])[1]
        
        info.contents[4].values[0]=self.builder.array(copy.deepcopy(w.elements(dest.contents[4].value)))
        return info

    def move(self,name,old,new,dest):
        if old==new:return
        array=self.project.docs[old].contents[5].value.contents[0].value
        w.set_elements(array,[item for item in w.elements(array) if item is not dest])
        self.builder.append(self.project.docs[new].contents[5].value.contents[0].value,dest);self.defs[name]=(new,dest)

    def apply(self,args):
        if args.kind=='edit_itinerary_margins':
            from .itinerary_margins import edit
            return edit(self.project,args)
        kind=args.kind;result={'kind':kind,'native_simulation_verified':False,'evidence':['itinerary-controls-contract','itinerary-controls-functions']}
        if kind=='reset_itinerary_catalog':
            old=set(self.infos);w.set_elements(self.project.data['dest'].contents[0].value,[]);self.infos={}
            for name,(document,dest) in sorted(self.defs.items()):self.sync(name,document,dest)
            return {**result,'itinerary_count':len(self.defs),'removed_inactive':sorted(old-set(self.defs)),'added_active':sorted(set(self.defs)-old),'definitions_preserved':True,'course_references_preserved':True}
        if kind=='delete_itineraries':
            used=course_usage(self.project);names=([name for name in self.infos if name not in used] if args.selection=='unused' else args.names)
            for name in names:
                if name not in self.defs and name not in self.infos:raise APIError('ITINERARY_NOT_FOUND','Unknown Itinerary.',name)
            selected=set(names);dependencies=[{'itinerary':name,'references':used[name]} for name in names if name in used]
            for document,root in self.project.docs.items():
                array=root.contents[5].value.contents[0].value;w.set_elements(array,[obj for obj in w.elements(array) if w.string(obj.contents[1].value) not in selected])
            array=self.project.data['dest'].contents[0].value;w.set_elements(array,[info for info in w.elements(array) if w.string(info.contents[1].value) not in selected])
            return {**result,'names':names,'itinerary_count':len(names),'selection':args.selection,'dependencies':dependencies,'course_references_preserved':True}
        document,dest=self.require(args.name);result.update(name=args.name,document=document)
        if kind=='rename_itinerary':
            if args.name==args.new_name:return {**result,'new_name':args.new_name,'course_replacements':[],'unchanged':True}
            self.fresh(args.new_name);replacements=[]
            for course in self.project.courses():
                array=course.contents[2].value;values=w.elements(array) if array else []
                index=next((i for i,value in enumerate(values) if w.string(value)==args.name),None)
                if index is not None:
                    values[index]=text(course,args.new_name);w.set_elements(array,values)
                    replacements.append({'course_id':w.string(course.contents[0].value),'index':index})
            set_text(dest,1,args.new_name)
            if args.name in self.infos:set_text(self.infos[args.name],1,args.new_name)
            return {**result,'new_name':args.new_name,'course_replacements':replacements,'replacement_rule':'first_occurrence_in_each_course'}
        if kind=='duplicate_itinerary':
            from .operations import clone
            self.fresh(args.new_name);names=self.names(dest);duplicate=clone(dest)
            set_text(duplicate,1,args.new_name);set_text(duplicate,3,'');duplicate.contents[2].values=[-1,-1]
            from .itinerary_margins import rows as margin_rows,make_point
            self.write_paths(duplicate,names)
            margins=clone(dest.contents[5].value);margins.contents[0].values[0]=self.builder.array([make_point(row) for row in margin_rows(dest)])
            duplicate.contents[5].values[0]=margins
            owner=self.available[names[0]][0];self.builder.append(self.project.docs[owner].contents[5].value.contents[0].value,duplicate)
            self.sync(args.new_name,owner,duplicate)
            return {**result,'new_name':args.new_name,'document':owner,'paths':names,'description':'','safety_margin_count':len(w.elements(duplicate.contents[5].value.contents[0].value)),'course_references_preserved':True}
        names=self.names(dest);before={'description':w.string(dest.contents[3].value),'paths':names,'document':document};reversals=[]
        if kind=='edit_itinerary':
            after=names if args.paths is None else args.paths
            if args.paths is not None:reversals=self.chain(after);self.write_paths(dest,after)
            if args.description is not None:set_text(dest,3,args.description)
            owner=self.available[after[0]][0];self.move(args.name,document,owner,dest)
        elif kind=='append_itinerary':
            if args.name==args.source:raise APIError('ITINERARY_SELF_APPEND_UNVERIFIED','Native self-Add mutation behavior is not yet verified; use explicit Path editing.')
            _,source=self.require(args.source);extra=self.names(source)
            if self.last(names[-1])!=self.first(extra[0]):raise APIError('ITINERARY_APPEND_BOUNDARY','Original Add requires the exact same document and directional End at the boundary.')
            after=names+extra
            if len(after)>1000:raise APIError('ITINERARY_SIZE','One Itinerary supports at most 1000 Paths.')
            self.write_paths(dest,after);owner=document
        else:
            if args.start_index+args.count>len(names):raise APIError('ITINERARY_PATH_RANGE','Selected interval exceeds the Itinerary.')
            old=names[args.start_index:args.start_index+args.count];self.resolve(args.paths);reversals=self.chain(args.paths)
            
            
            index=names.index(old[0])
            if index!=args.start_index:raise APIError('ITINERARY_AMBIGUOUS_SELECTION','Native indexOfObject aliases an earlier repeated Path; choose an unambiguous interval.',{'requested_index':args.start_index,'native_first_index':index})
            if old[0]!=names[0] and self.first(old[0])!=self.first(args.paths[0]):raise APIError('ITINERARY_REPLACE_START','Interior replacement must retain the selected first End.')
            if old[-1]!=names[-1] and self.last(old[-1])!=self.last(args.paths[-1]):raise APIError('ITINERARY_REPLACE_END','Interior replacement must retain the selected last End.')
            after=names[:index]+args.paths+names[index+args.count:];reversals=self.chain(after)
            self.write_paths(dest,after);owner=self.available[after[0]][0];self.move(args.name,document,owner,dest)
            result.update(start_index=index,count=args.count)
        sync='refresh_selected' if kind=='append_itinerary' else args.catalog_sync
        if sync=='refresh_selected':self.sync(args.name,owner,dest)
        result.update(before=before,after={'description':w.string(dest.contents[3].value),'paths':after,'document':owner},
            reversals=reversals,catalog_sync=sync,safety_margins_preserved=True,course_references_preserved=True)
        return result


def catalog_rows(project,args):
    rows=project.catalog('itineraries');used=course_usage(project)
    if args.itinerary_usage!='all':rows=[row for row in rows if (row['name'] in used)==(args.itinerary_usage=='used')]
    if args.query:
        import json
        rows=[row for row in rows if args.query.casefold() in (json.dumps(row,ensure_ascii=False) if args.itinerary_query_field=='all' else (row[args.itinerary_query_field] or '')).casefold()]
    if args.include_itinerary_details:
        defs=definitions(project)
        for row in rows:
            dest=defs.get(row['name']);refs=path_references(dest[1]) if dest else None
            from .itinerary_margins import rows as margin_rows
            margins=margin_rows(dest[1]) if dest else None
            row.update(course_references=used.get(row['name'],[]),used=row['name'] in used,definition_paths=refs,
                safety_margins=margins[:20] if margins is not None else None,safety_margin_count=len(margins) if margins is not None else None,
                safety_margins_truncated=len(margins)>20 if margins is not None else False,
                catalog_paths_match_definition=refs==row['paths'] if dest else None)
    return rows
