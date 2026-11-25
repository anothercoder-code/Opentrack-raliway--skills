"""SHA-bound infrastructure Incident12 previews and fresh Course catalog publication."""
from typing import Any, Annotated
from pathlib import PurePosixPath
import re
from pydantic import StrictStr, Field
from .tools import Input, ArchiveTools, sha, PathText
from .bundle_tools import Source
from .next_tools import Save
from .operating_candidate_publication import save_candidate
from ..errors import APIError

HashText=Annotated[StrictStr,Field(pattern=r'^[0-9a-f]{64}$')]
class DocumentSource(Input):
    name: Annotated[StrictStr,Field(min_length=1,max_length=200)]
    path: PathText
    sha256: HashText
    native_path: PathText
class InfrastructureIncidentSources(Save):
    source: Source
    project_run: Source
    trains: Source
    depot: Source
    native_train_path: PathText
    native_depot_path: PathText
    native_course_path: PathText
    documents: Annotated[list[DocumentSource],Field(min_length=1,max_length=32)]


class PreviewInfrastructureIncidents(InfrastructureIncidentSources):
    spec: dict[str,Any]


class ImportIncidentText(InfrastructureIncidentSources):
    incident_text: Source


class ExportIncidentText(Save):
    source: Source


class InfrastructureIncidentTools(ArchiveTools):
    def preview(self,args):
        return self.plan(args, args.spec)

    def import_text(self, args):
        from .incident_text import rows, to_item

        path = self.path(args.incident_text.path)
        raw = self.secure_bytes(path)
        if sha(raw) != args.incident_text.sha256:
            raise APIError('SOURCE_CHANGED', 'Incident text differs from its SHA-256')
        try:
            items = [to_item(row) for row in rows(raw)]
        except (ValueError, KeyError, OverflowError) as exc:
            raise APIError('INCIDENT_TEXT_FORMAT', 'Cannot apply the selected original incident rows', str(exc)) from exc
        result = self.plan(args, {'incidents': items, 'set_actions': []}, extra_dependencies={path: raw})
        return dict(result, tool='opentrack_import_native_incident_text', incident_text_sha256=sha(raw))

    def export_text(self, args):
        from .incident_text import encode_catalog, rows

        path = self.path(args.source.path)
        raw = self.secure_bytes(path)
        if sha(raw) != args.source.sha256:
            raise APIError('SOURCE_CHANGED', 'Incident catalog differs from its SHA-256')
        if path.suffix.casefold() != '.courses':
            raise APIError('ARCHIVE_TARGET_EXTENSION', 'Choose an original .courses input')
        try:
            encoded = encode_catalog(raw)
        except (ValueError, KeyError, OverflowError) as exc:
            raise APIError('INCIDENT_TEXT_FORMAT', 'The original text has no lossless representation for the source', str(exc)) from exc
        result = {'saved': False, 'source_sha256': sha(raw), 'output_sha256': sha(encoded),
                  'incidents': len(rows(encoded, allow_empty=True)), 'text': encoded.decode('ascii'),
                  'native_application_started': False}
        if args.preview_only:
            if self.secure_bytes(path) != raw:
                raise APIError('SOURCE_CHANGED', 'Incident catalog changed during export')
            return result
        if self.path(args.target_path).suffix.casefold() != '.txt':
            raise APIError('ARCHIVE_TARGET_EXTENSION', 'Use a fresh .txt target')
        return self.save_copy(path, raw, encoded, result, args.target_path,
                              validate_output=lambda data: rows(data, allow_empty=True))

    def plan(self,args,spec,*,extra_dependencies=None):
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
            output,receipt=plan(sources['courses'],{n:sources[n]for n in names},spec,document_paths={d.name:d.native_path for d in args.documents},run_bytes=sources['run'],course_path=args.native_course_path,trains_blob=sources['trains'],depot_blob=sources['depot'],train_path=args.native_train_path,depot_path=args.native_depot_path)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
            raise APIError('INFRASTRUCTURE_INCIDENT_INVALID','Outside the finite infrastructure Incident storage contract',str(exc)[:500])from exc
        for key,p in paths.items():
            if self.secure_bytes(p)!=sources[key]:raise APIError('SOURCE_CHANGED','Source changed during preview',key)
        if (receipt.get('source_sha256') != sha(sources['courses']) or receipt.get('output_sha256') != sha(output)
                or receipt.get('run_sha256') != sha(sources['run'])
                or receipt.get('document_sha256') != {name: sha(sources[name]) for name in names}):
            raise APIError('PREVIEW_MANIFEST', 'Incident receipt differs from source/output bytes')
        result = dict(tool='opentrack_preview_infrastructure_incidents',preview_only=args.preview_only,saved=False,
                    native_runtime_ready=False,publication_review_pending=args.preview_only,sampling_executed=False,
                    sources={key:{'sha256':sha(b),'bytes':len(b)}for key,b in sources.items()},
                    output={'sha256':sha(output),'bytes':len(output)},infrastructure_incidents=receipt,
                    limitations=['Incident12 records, including kilometre/Route spans, periodic parameters, and existing distribution references. Course/TrainFile/DepotFile bindings check initial formation and static speed limits.',
                                 'No native triggering, sampling, interlocking correctness or complete simulation readiness.',
                                 'Publication creates a Course catalog copy bound to the supplied project dependencies.'])
        dependencies = {path: sources[key] for key, path in paths.items() if key != 'courses'}
        for path, data in (extra_dependencies or {}).items():
            if path in paths.values() or self.secure_bytes(path) != data:
                raise APIError('SOURCE_CHANGED', 'Imported text changed or aliases an original member')
            dependencies[path] = data
        return save_candidate(self, args, paths['courses'], sources['courses'], output, result,
                              extension='.courses', dependencies=dependencies)

def tool_definitions(root):
    from .native_incident_effects import EffectStudy, EffectTools

    service=InfrastructureIncidentTools(root)
    effects=EffectTools(root)
    return [
        ('opentrack_preview_infrastructure_incidents','Preview or save a fresh .courses archive with supported infrastructure Incident12 data, including signal/edge, kilometre ranges, and Route/Path controls. Requires SHA-bound .run, documents and stock dependencies. No native execution.',PreviewInfrastructureIncidents,service.preview,False,False),
        ('opentrack_import_native_incident_text', 'Decode stock English incident TSV and append validated events to a fresh native .courses copy.', ImportIncidentText,service.import_text,False,False),
        ('opentrack_export_native_incident_text', 'Render supported saved Incident12 rows as original OpenTrack incident TSV without silently dropping unsupported values.', ExportIncidentText,service.export_text,False,False),
        ('opentrack_compare_native_incident_effect',
         'Compare sealed original simulations differing only in one named deterministic incident. Recover its frozen '
         'Path speed, Train power, tractive effort or fixed signal stop at a booked departure. '
         'Bind original activation and physical behavior. Read only.',
         EffectStudy,effects.compare),
    ]
