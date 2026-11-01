from typing import Literal
"""SHA-bound infrastructure Incident12 readonly preview. Never saves or executes."""
from typing import Any, Annotated
from pathlib import PurePosixPath
import re
from pydantic import StrictBool, StrictStr, Field
from .tools import Input, ArchiveTools, sha, PathText
from .bundle_tools import Source
from ..errors import APIError

HashText=Annotated[StrictStr,Field(pattern=r'^[0-9a-f]{64}$')]
class DocumentSource(Input):
    name: Annotated[StrictStr,Field(min_length=1,max_length=200)]
    path: PathText
    sha256: HashText
    native_path: PathText
class PreviewInfrastructureIncidents(Input):
    source: Source
    project_run: Source
    trains: Source
    depot: Source
    native_train_path: PathText
    native_depot_path: PathText
    native_course_path: PathText
    documents: Annotated[list[DocumentSource],Field(min_length=1,max_length=32)]
    spec: dict[str,Any]
    preview_only: Literal[True] = True

class InfrastructureIncidentTools(ArchiveTools):
    def preview(self,args):
        if args.preview_only is not True:
            raise APIError('PREVIEW_ONLY','Only read-only preview is supported; no new save, publication or native execution.')
        names=[d.name for d in args.documents]
        if len(set(n.casefold() for n in names))!=len(names):
            raise APIError('DOCUMENT_BINDING','Unique case-unambiguous document names required')
        for n in names:
            if n in ('.','..') or any(ch in n for ch in '/\\:#') or any(ord(ch)<32 or ord(ch)>126 for ch in n) or n!=n.strip():
                raise APIError('DOCUMENT_BINDING','Explicit printable document basenames required')
        bindings=[('courses',args.source.path,args.source.sha256),('run',args.project_run.path,args.project_run.sha256),('trains',args.trains.path,args.trains.sha256),('depot',args.depot.path,args.depot.sha256)]+[(d.name,d.path,d.sha256)for d in args.documents]
        if any(n in ('courses','run','trains','depot') for n in names):raise APIError('DOCUMENT_BINDING','Document name collides with reserved binding role')
        native={'courses':args.native_course_path,'trains':args.native_train_path,'depot':args.native_depot_path,**{d.name:d.native_path for d in args.documents}}
        project_roots=set();native_roots=set()
        for key,rel,_ in bindings:
            parts=PurePosixPath(rel).parts
            base_len=2 if parts and parts[0]=='OTProjects' else 3 if parts[:2]==('OTAI','workspaces') else 0
            if not base_len or len(parts)<=base_len:raise APIError('DOCUMENT_BINDING','Sources must belong to one named project directory')
            project_roots.add(parts[:base_len])
            if key=='run':continue
            suffix=parts[base_len:];raw=native[key];p=PurePosixPath(raw)
            if not re.match(r'^[A-Za-z]:/',raw) or str(p)!=raw or any(ch in raw for ch in '\\#') or ':' in raw[2:] or any(ord(ch)<32 or ord(ch)>126 for ch in raw) or '..' in p.parts:
                raise APIError('DOCUMENT_BINDING','Canonical slash Windows absolute native paths required')
            if len(p.parts)<=len(suffix) or p.parts[-len(suffix):]!=suffix:
                raise APIError('DOCUMENT_BINDING','Native path must preserve the project-relative source path')
            native_roots.add(p.parts[:-len(suffix)])
        if len(project_roots)!=1 or len(native_roots)!=1:raise APIError('DOCUMENT_BINDING','One input project and one consistent native project root required')
        paths={};sources={};seen=set();total=0
        for key,rel,expected in bindings:
            p=self.path(rel)
            if p in seen:raise APIError('DOCUMENT_BINDING','Distinct source paths required')
            seen.add(p);b=self.secure_bytes(p);total+=len(b)
            if total>128*1024*1024:raise APIError('ARCHIVE_SIZE','Aggregate preview inputs exceed 128 MiB')
            if sha(b)!=expected:raise APIError('SOURCE_CHANGED','Input SHA binding mismatch',key)
            paths[key]=p;sources[key]=b
        from .infrastructure_incidents.core import plan
        try:
            output,receipt=plan(sources['courses'],{n:sources[n]for n in names},args.spec,document_paths={d.name:d.native_path for d in args.documents},run_bytes=sources['run'],course_path=args.native_course_path,trains_blob=sources['trains'],depot_blob=sources['depot'],train_path=args.native_train_path,depot_path=args.native_depot_path)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
            raise APIError('INFRASTRUCTURE_INCIDENT_INVALID','Outside the finite infrastructure Incident storage contract',str(exc)[:500])from exc
        for key,p in paths.items():
            if self.secure_bytes(p)!=sources[key]:raise APIError('SOURCE_CHANGED','Source changed during preview',key)
        return dict(tool='opentrack_preview_infrastructure_incidents',preview_only=True,saved=False,
                    native_runtime_ready=False,publication_review_pending=True,sampling_executed=False,
                    sources={key:{'sha256':sha(b),'bytes':len(b)}for key,b in sources.items()},
                    output={'sha256':sha(output),'bytes':len(output)},infrastructure_incidents=receipt,
                    limitations=['Finite Incident12 types1/2/3/4/5/9/10/11/12/14, periodic parameters, typed discrete flags and existing begin/duration/SignalStop table references. Actual selected-run Course/TrainFile/DepotFile dependency binding, including initial formation and finite static speed limits; not runtime physics.',
                                 'No native triggering, sampling, interlocking correctness or complete simulation readiness.',
                                 'Existing tool compatibility is not expanded merely by this preview; no new save or publication.'])

def tool_definitions(root):
    service=InfrastructureIncidentTools(root)
    return [('opentrack_preview_infrastructure_incidents','Read-only SHA-bound actual Course/Train/Engine dependency and typed Incident12 preview for signal/edge, Route/Path speed, groups, headway/stop, Train speed/traction/power, periodic and typed discrete parameters, existing begin/duration/SignalStop distributions and bit-preserving native-set actions. No runtime or saving.',PreviewInfrastructureIncidents,service.preview)]
