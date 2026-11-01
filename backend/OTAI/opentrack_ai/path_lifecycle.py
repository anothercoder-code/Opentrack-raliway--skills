"""Original Delete all Paths: document/End scope and whole-Itinerary removal.

OTDocument 0x49f48c, OTEndModel 0x4c4d1c and OTDestInspector 0x48abc0.
Course strings survive native destHasChanged -> OTCourseController.update.
"""
from pathlib import Path

from .archive import APIError,w,END_KINDS
from .topology import Topology


def delete_all_paths(project,args):
    if args.document not in project.docs:raise APIError('DOCUMENT_NOT_FOUND','The selected document is not loaded.',args.document)
    topology=Topology(project)
    
    
    for ident in args.end_ids:topology.require((args.document,ident))
    chosen=set(args.end_ids);targets=[];arrays=[]
    for end in project.models[args.document]:
        if w.kind(end) not in END_KINDS:continue
        ident=end.contents[0].value
        if chosen and ident not in chosen or not topology.is_main((args.document,ident)):continue
        wrapper=end.contents[17].value
        if wrapper is None:continue
        if w.kind(wrapper)!='OTPathList':raise APIError('PATH_LIST_LAYOUT','Expected the original End Path list.',ident)
        array=wrapper.contents[0].value;items=w.elements(array);arrays.append(array)
        for path in items:
            if w.kind(path)!='OTPath' or len(path.contents)!=5 or path.contents[2].values[1]!=ident:
                raise APIError('PATH_OWNER','A saved Path does not match its owning End.',ident)
            targets.append({'document':args.document,'start_id':ident,'path_id':path.contents[2].values[0],
                'name':w.string(path.contents[1].value),'_object':path})
    if len(targets)>10000:raise APIError('PATH_LIFECYCLE_SIZE','One command supports at most 10000 Paths.')
    identities={id(row['_object']) for row in targets}
    keys={(row['document'],row['start_id'],row['path_id'],row['name']) for row in targets}
    def references(ext):
        if w.kind(ext)!='OTArrayExtInfo':raise APIError('PATH_LIFECYCLE_REFERENCE','An Itinerary Path reference has an unexpected class.')
        return (Path(w.string(ext.contents[2].value)).stem,ext.contents[1].values[1],ext.contents[1].values[0],w.string(ext.contents[0].value)) in keys
    affected={};definitions={}
    for document,root in project.docs.items():
        for destination in w.elements(root.contents[5].value.contents[0].value):
            name=w.string(destination.contents[1].value)
            if name in definitions:raise APIError('DUPLICATE_ITINERARY_NAME','Itinerary definitions must have unique names.',name)
            definitions[name]=(document,destination)
            if any(id(path) in identities for path in w.elements(destination.contents[0].value)) or any(references(ext) for ext in w.elements(destination.contents[4].value)):
                affected[name]=document
    infos=w.elements(project.data['dest'].contents[0].value);info_names=[w.string(info.contents[1].value) for info in infos]
    if len(set(info_names))!=len(info_names):raise APIError('DUPLICATE_ITINERARY_NAME','Itinerary catalog names must be unique.')
    for info in infos:
        name=w.string(info.contents[1].value)
        if any(references(ext) for ext in w.elements(info.contents[4].value)):
            if name not in definitions:raise APIError('PATH_LIFECYCLE_REFERENCE','A dependent catalog Itinerary lacks its document definition.',name)
            affected[name]=definitions[name][0]
    if len(affected)>10000:raise APIError('PATH_LIFECYCLE_SIZE','One command supports at most 10000 dependent Itineraries.')
    dependencies=[]
    for course in project.courses():
        names=[w.string(value) for value in w.elements(course.contents[2].value)] if course.contents[2].value else []
        used=[name for name in names if name in affected]
        if used:dependencies.append({'course_id':w.string(course.contents[0].value),'itineraries':used})
    paths=[{k:v for k,v in row.items() if k!='_object'} for row in targets]
    if affected and args.dependent_itineraries=='reject':
        raise APIError('PATHS_IN_USE','Original deletion removes each affected whole Itinerary. Select dependent_itineraries=delete to stage that consequence.',
            {'path_count':len(paths),'itinerary_count':len(affected),'itineraries':sorted(affected)[:50],
                'course_count':len(dependencies),'courses':dependencies[:20],'course_references_preserved':True})
    
    for array in arrays:w.set_elements(array,[path for path in w.elements(array) if id(path) not in identities])
    for document,root in project.docs.items():
        array=root.contents[5].value.contents[0].value
        w.set_elements(array,[obj for obj in w.elements(array) if w.string(obj.contents[1].value) not in affected])
    w.set_elements(project.data['dest'].contents[0].value,[info for info in infos if w.string(info.contents[1].value) not in affected])
    project._graph=None
    return {'kind':'delete_all_paths','document':args.document,'end_ids':list(args.end_ids),
        'selection_scope':'selected_ends' if chosen else 'all_route_start_ends_in_document',
        'paths_deleted':paths,'path_count':len(paths),'itineraries_deleted':[{'name':name,'document':document} for name,document in affected.items()],
        'itinerary_count':len(affected),'dependent_courses':dependencies,'dependent_course_count':len(dependencies),
        'dependent_itineraries':args.dependent_itineraries,'course_references_preserved':True,
        'native_simulation_verified':False,'evidence':['path-lifecycle-contract','path-lifecycle-functions']}
