import hashlib
import json
from pathlib import Path
import re
import sys
import threading

CODE_ROOT=Path(__file__).resolve().parents[2]
VENDOR=CODE_ROOT/'OTAI/vendor'
LEGACY=CODE_ROOT/'OTUndo/tools'
if not LEGACY.is_dir():LEGACY=VENDOR/'legacy'
if (VENDOR/'python').is_dir():sys.path.insert(0,str(VENDOR/'python'))
sys.path.insert(0,str(LEGACY))
import typedstream_writer as w
from opentrack_course_schema import course_items
from opentrack_train_schema import train_items,engine_items,bound_engine_names
from opentrack_station_schema import station_items
from hsr_capacity_graph import graph_from_documents,END_KINDS

from .errors import APIError, LOCK 
KINDS={'DestInfoFile':'dest','DepotFile':'depot','TrainFile':'trains','CourseFile':'courses','StationFile':'stations','TimetableFile':'timetable'}
MAX_ARCHIVE_BYTES=20*1024*1024



def digest(data):return hashlib.sha256(data).hexdigest()


def inside(path,bases):
    path=Path(path).resolve()
    if not any(path==base.resolve() or path.is_relative_to(base.resolve()) for base in bases):
        raise APIError('PATH_OUTSIDE_SCOPE','Path must remain inside the configured project/data directories.',str(path))
    return path


def parse_run(blob):
    result={}
    try:lines=blob.decode('ascii').splitlines()
    except UnicodeDecodeError as e:raise APIError('RUN_ENCODING','Audited .run files use ASCII paths and parameters.') from e
    for line in lines:
        if not line.strip() or line.startswith('//'):continue
        parts=line.split('#')
        if len(parts)!=3:raise APIError('RUN_FORMAT','Expected key#value# line.',line[:160])
        result.setdefault(parts[0],[]).append(parts[1])
    return result


def clock(seconds):
    if not 0<=seconds<86400:raise APIError('TIME_OUT_OF_RANGE','This editor supports times within one day (00:00:00–23:59:59).')
    return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'


def seconds(text):
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d',text):raise APIError('TIME_FORMAT','Expected HH:MM:SS within one day.',text)
    h,m,s=map(int,text.split(':'));return h*3600+m*60+s


def page(rows,limit,offset):
    return {'items':rows[offset:offset+limit],'total_count':len(rows),'offset':offset,
        'has_more':offset+limit<len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None}


def ref(value):
    if hasattr(value,'clazz'):
        kind=w.kind(value)
        if kind=='NSString':return w.string(value)
        if kind in ['NSArray','NSMutableArray']:return {'class':kind,'count':len(w.elements(value))}
        result={'class':kind}
        if value.contents and len(value.contents[0].values)==1 and isinstance(value.contents[0].value,int):result['id']=value.contents[0].value
        return result
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    if isinstance(value,bytes):return {'bytes':len(value),'hex_prefix':value[:32].hex()}
    return str(value)[:240]


class Project:
    def __init__(self,root,project='OTProjects/BJTU',run_file=None):
        self.root=Path(root).resolve()
        self.project=inside(self.root/project if not Path(project).is_absolute() else project,
            [self.root/'OTProjects',self.root/'OTAI/workspaces'])
        if not self.project.is_dir():raise APIError('PROJECT_NOT_FOUND','Project directory does not exist.',str(self.project))
        self.read_bases=[self.root/'OTProjects',self.root/'OTData',self.root/'OTAI/workspaces']
        self.sources={};self.versions={};self.native_length_errors={}
        metadata=self.project/'opentrack-project.json'
        settings=json.loads(self.read(metadata).decode('utf8')) if metadata.is_file() else None
        if settings is not None and not isinstance(settings,dict):raise APIError('PROJECT_METADATA','Project metadata must be a JSON object.')
        if run_file:
            p=Path(run_file);self.run_file=self.resolve(p if p.is_absolute() else self.project/p)
        else:
            if settings is not None:
                selected=settings.get('default_run')
                if not isinstance(selected,str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.run',selected):
                    raise APIError('PROJECT_METADATA','default_run must be a simple .run filename.')
                self.run_file=self.resolve(self.project/selected)
            else:
                candidate=self.project/'BJTU-demo.run';self.run_file=candidate if candidate.is_file() else None
        self.parameters=parse_run(self.read(self.run_file)) if self.run_file else {}
        self.data={};self.data_paths={}
        for key,kind in KINDS.items():
            options=self.parameters.get(key,[])
            if len(options)>1:raise APIError('DUPLICATE_RUN_KEY','Catalog key occurs more than once.',key)
            p=self.resolve(options[0]) if options else self.project/'OTData'/('empty.'+kind)
            self.data_paths[kind]=p;self.data[kind]=self.load(p)
        self.canonical_differences=[]
        for kind,selected in self.data_paths.items():
            canonical=self.project/'OTData'/('empty.'+kind)
            if canonical.is_file() and canonical.resolve()!=selected.resolve():
                raw=self.read(canonical)
                if digest(raw)!=digest(self.sources[str(selected)]):self.canonical_differences.append(kind)
        doc_options=self.parameters.get('Infrastructure Document',[])
        doc_paths=[self.resolve(p) for p in doc_options] if doc_options else sorted((self.project/'OTDocuments').glob('*.opentrack'))
        if not doc_paths:raise APIError('NO_INFRASTRUCTURE','No infrastructure documents were selected.')
        if len(doc_paths)>100:raise APIError('PROJECT_SIZE','At most 100 infrastructure documents are supported per request.')
        if len({p.stem for p in doc_paths})!=len(doc_paths):raise APIError('DUPLICATE_DOCUMENT_NAME','Connector document names must be unambiguous.')
        self.docs={p.stem:self.load(p) for p in doc_paths}
        self.doc_paths={p.stem:p for p in doc_paths}
        self.corridors={}
        for value in self.parameters.get('Train Diagram Document',[]):
            p=self.resolve(value)
            if p.name in self.corridors:raise APIError('DUPLICATE_CORRIDOR_NAME','Selected corridor filenames must be unambiguous.',p.name)
            self.corridors[p.name]=self.load(p)
        scenario=self.project/'demo-scenario.json'
        self.scenario=json.loads(self.read(scenario).decode('utf8')) if scenario.exists() else {}
        self.models={name:w.elements(doc.contents[2].value) for name,doc in self.docs.items()}
        self._graph=None
        
        
        if any(digest(Path(p).read_bytes())!=digest(data) for p,data in self.sources.items()):
            raise APIError('SOURCE_CHANGED','A selected input changed during reading; retry after saving or exiting OpenTrack.')

    def resolve(self,path):
        p=Path(path)
        if not p.is_absolute():p=self.project/p
        return inside(p,self.read_bases)

    def read(self,path):
        path=inside(path,self.read_bases)
        try:
            if path.stat().st_size>MAX_ARCHIVE_BYTES:raise APIError('FILE_TOO_LARGE','Input exceeds the 20 MiB per-file bound.',str(path))
            blob=path.read_bytes()
        except OSError as e:raise APIError('INPUT_UNREADABLE','Selected input is missing or cannot be read.',str(path)) from e
        self.sources[str(path)]=blob
        return blob

    def load(self,path):
        path=self.resolve(path);blob=self.read(path)
        try:obj,version=w.load_next_compatible(blob)
        except (ValueError,w.stream.InvalidTypedStreamError) as e:
            
            
            
            try:obj,version=w.load(blob)
            except Exception as permissive_error:
                raise APIError('ARCHIVE_DECODE','Both native-compatible and permissive typedstream decoding failed.',{'path':str(path),'reason':str(e)[:240]}) from permissive_error
            self.native_length_errors[str(path)]=str(e)
        self.versions[str(path)]=version
        return obj

    @property
    def source_digest(self):
        return digest(json.dumps(self.source_hashes,sort_keys=True,separators=(',',':')).encode('utf8'))

    @property
    def source_hashes(self):return {p:digest(blob) for p,blob in sorted(self.sources.items())}

    def graph(self):
        if self._graph is None:
            from .topology import Topology
            topology=Topology(self)
            if topology.problems:raise APIError('TOPOLOGY_INVALID','Graph tracing requires valid directional references.',topology.problems[:100])
            self._graph=graph_from_documents(self.docs,require_unique_path_names=True)
        return self._graph

    def courses(self):return course_items(self.data['courses'])
    def table(self):
        obj=self.data['timetable']
        if obj.contents[0].value!=(len(obj.contents)-1)//2:raise APIError('TIMETABLE_COUNT','Timetable dictionary count is inconsistent.')
        keys=[w.string(obj.contents[i].value) for i in range(1,len(obj.contents),2)]
        if len(keys)!=len(set(keys)):raise APIError('DUPLICATE_TIMETABLE_KEY','Timetable dictionary contains duplicate course/index keys.')
        return {w.string(obj.contents[i].value):obj.contents[i+1].value for i in range(1,len(obj.contents),2)}

    def service(self,obj):
        from .course_records import course_record
        return course_record(obj)

    def timetable_row(self,key,obj):
        from .native_records import timetable_record
        return timetable_record(key,obj)

    def catalog(self,kind,include_curves=False):
        if kind=='services':return [self.service(c) for c in self.courses()]
        if kind=='shuntings':
            from .topology import Topology
            return [{key:value for key,value in row.items() if not key.startswith('_')} for row in Topology(self).shunting_records()]
        if kind=='itineraries':
            definitions={}
            for document,root in self.docs.items():
                for obj in w.elements(root.contents[5].value.contents[0].value):
                    name=w.string(obj.contents[1].value)
                    if name in definitions:raise APIError('DUPLICATE_ITINERARY_NAME','Itinerary has multiple document definitions.',name)
                    definitions[name]=(document,obj)
            rows=[]
            for info in w.elements(self.data['dest'].contents[0].value):
                name=w.string(info.contents[1].value);definition=definitions.get(name)
                rows.append({'name':name,'document_file':w.string(info.contents[2].value),'start_end_id':info.contents[3].value,
                    'document':definition[0] if definition else None,'description':w.string(definition[1].contents[3].value) if definition else None,
                    'paths':[{'name':w.string(item.contents[0].value),'path_id':item.contents[1].values[0],
                        'start_end_id':item.contents[1].values[1],'document':w.string(item.contents[2].value)} for item in w.elements(info.contents[4].value)]})
            return rows
        if kind=='trains':
            from .rolling_stock import formation_record
            return [formation_record(obj) for obj in train_items(self.data['trains'])]
        if kind=='engines':
            from .rolling_stock import engine_record
            return [engine_record(obj,include_curves) for obj in engine_items(self.data['depot'])]
        if kind=='categories':
            from .rolling_stock import category_record
            return [category_record(obj) for obj in w.elements(self.data['trains'].contents[1].value)]
        if kind=='stations':return [{'sign':s,'name':w.string(v.contents[2].value),'timing_station':bool(v.contents[7].value)} for s,v in station_items(self.data['stations']).items()]
        if kind=='timetable':return [self.timetable_row(k,v) for k,v in self.table().items()]
        raise APIError('UNKNOWN_CATALOG','Unsupported catalog kind.',kind)
