"""Create blank native projects from sanitized class shapes, not a rail template."""
import copy
import json
from types import SimpleNamespace
import re
import uuid

from .archive import APIError,Project,inside
from .drafts import DraftManager,set_text
from .resources import templates


class ProjectFactory:
    def __init__(self,service):self.service=service

    def create(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        s=self.service;s.check_build()
        for name in [args.project_name,*args.documents]:
            if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]',name,re.I):raise APIError('PROJECT_NAME','Reserved Windows file/directory name.',name)
        if len(set(name.casefold() for name in args.documents))!=len(args.documents):raise APIError('DUPLICATE_DOCUMENT_NAME','Document filenames must be unique, including Windows case aliases.')
        target=inside(s.root/'OTProjects'/args.project_name,[s.root/'OTProjects'])
        if target.exists():raise APIError('PROJECT_EXISTS','Choose a new project name; existing projects are never overwritten.',str(target))
        shapes,version=templates(s.root);folder=s.work/('create-'+uuid.uuid4().hex[:16]);staging=folder/'project'
        folder.mkdir(parents=True,exist_ok=False)
        catalog_types={'dest':'OTDestInfoList','depot':'NSMutableArray','trains':'OTTrainList','courses':'OTCourseList','stations':'NSMutableDictionary','timetable':'NSMutableDictionary'}
        data={kind:copy.deepcopy(shapes[clazz]) for kind,clazz in catalog_types.items()}
        docs={name:copy.deepcopy(shapes['OTDocument']) for name in args.documents}
        for document in docs.values():
            for index in [8,9,10]:document.contents[index].values=[0.,0.,args.width,args.height]
            set_text(document,17,'A4')
            set_text(document,18,'OTAI-'+uuid.uuid4().hex.upper())
        data_paths={kind:staging/'OTData'/('empty.'+kind) for kind in data};doc_paths={name:staging/'OTDocuments'/(name+'.opentrack') for name in docs}
        p=SimpleNamespace(project=staging,root=s.root,data=data,docs=docs,corridors={},data_paths=data_paths,doc_paths=doc_paths,
            versions={str(path):version for path in [*data_paths.values(),*doc_paths.values()]},native_length_errors={},parameters={},
            scenario={'editor_state':{'next_graphic_id':{name:0 for name in args.documents}}})
        DraftManager(s).write_project(p,staging,{})
        validation=s.validate_project(Project(s.root,str(staging)))
        if not validation['valid']:raise APIError('EMPTY_PROJECT_VALIDATION','Blank project failed archive checks; isolated staging retained.',{'staging':str(staging),'errors':validation['errors']})
        run=(staging/'BJTU-demo.run').read_bytes().replace(str(staging).replace('\\','/').encode('ascii'),str(target).replace('\\','/').encode('ascii'))
        run_name=args.project_name+'.run';(staging/run_name).write_bytes(run);(staging/'BJTU-demo.run').write_bytes(run)
        (staging/'opentrack-project.json').write_text(json.dumps({'default_run':run_name,'created_by':'OTAI blank native project factory'},indent=2),encoding='utf8')
        target.parent.mkdir(parents=True,exist_ok=True);staging.rename(target);folder.rmdir()
        final=Project(s.root,str(target));validation=s.validate_project(final)
        if not validation['valid']:raise APIError('EMPTY_PROJECT_VALIDATION','New isolated project needs inspection; no existing project was changed.',validation)
        return {'project':str(target),'run_file':str(target/run_name),'documents':list(final.docs),'catalog_counts':{key:len(final.catalog(key)) for key in ['services','trains','engines','stations','timetable']},
            'source_digest':final.source_digest,'validation':validation,'copied_template_infrastructure':False,
            'original_executable_required':False,'native_simulation_verified':False}
