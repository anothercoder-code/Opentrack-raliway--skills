"""SHA-bound finite itinerary preview and publication of the changed archives."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .tools import ArchiveTools, PathText, sha
from .bundle_tools import Source
from .multi_document_tools import Name, Ref
from .project_candidate_publication import ProjectSave
from ..errors import APIError

class PreviewFiniteItinerary(ProjectSave):
    domain: Literal['finite_explicit_itinerary']
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    document_paths: Annotated[dict[Name, PathText], Field(min_length=1, max_length=100)]
    dest_catalog: Source
    complete_document_set: Literal[True]
    name: Name
    paths: Annotated[list[Ref], Field(min_length=1, max_length=1000)]
    project_run: Source | None = None

    @model_validator(mode='after')
    def bound_run_for_publication(self):
        if not self.preview_only and self.project_run is None:
            raise ValueError('Saving requires the complete project .run and its exact SHA-256')
        return self

class FiniteItineraryTools(ArchiveTools):
    def preview(self, args):
        from .finite_itinerary_workflow import create_finite_itinerary
        if '$dest_catalog' in args.documents or set(args.documents)!=set(args.document_paths):
            raise APIError('FINITE_ITINERARY_BINDING','Document keys and exact native path keys must match; reserved catalog role cannot be a document name')
        if not args.preview_only:
            from .itinerary_edit_tools import CreateItinerary, ItineraryEditTools, run_infrastructure_paths
            run_path = self.path(args.project_run.path)
            run = self.secure_bytes(run_path)
            if sha(run) != args.project_run.sha256:
                raise APIError('SOURCE_CHANGED','Project run differs from its supplied SHA-256')
            try:
                configured_paths = run_infrastructure_paths(run)
            except (IndexError, ValueError) as exc:
                raise APIError('FINITE_ITINERARY_BINDING','Invalid project .run document bindings') from exc
            if args.document_paths != configured_paths:
                raise APIError('FINITE_ITINERARY_BINDING','The document_paths mapping must equal the project .run bindings')
            request = CreateItinerary(action='create_itinerary',project_run=args.project_run,
                documents=args.documents,catalog=args.dest_catalog,name=args.name,paths=args.paths,
                preview_only=False,target_directory=args.target_directory)
            result = ItineraryEditTools(self.root).edit_project(request)
            return {**result,'tool':'opentrack_preview_finite_explicit_itinerary',
                    'publication_review_pending':False,'native_runtime_ready':False}
        inputs = {}; docs = {}; total_bytes = 0
        for role, source in {**args.documents, '$dest_catalog': args.dest_catalog}.items():
            path = self.path(source.path); data = self.secure_bytes(path)
            if sha(data) != source.sha256:
                raise APIError('SOURCE_CHANGED','Input differs from exact SHA binding',role)
            if path in inputs:
                raise APIError('FINITE_ITINERARY_BINDING','Document/catalog roles require distinct source files')
            total_bytes += len(data)
            if total_bytes > 256*1024*1024:
                raise APIError('FINITE_ITINERARY_SIZE','Complete input set exceeds 256 MiB')
            inputs[path] = data
            if role == '$dest_catalog': catalog = data
            else: docs[role] = data
        hashes = {**{k:sha(v)for k,v in docs.items()},'$dest_catalog':sha(catalog)}
        try:
            output, receipt = create_finite_itinerary(docs,catalog,document_paths=args.document_paths,
                expected_hashes=hashes,complete_document_set=args.complete_document_set,
                name=args.name,paths=[r.model_dump()for r in args.paths])
            actual = {**{k:sha(v)for k,v in output['documents'].items()},'$dest_catalog':sha(output['catalog'])}
            if receipt['input_sha256'] != hashes or receipt['output_sha256'] != actual:
                raise ValueError('Receipt does not match actual input/output hashes')
        except (ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:
            raise APIError('FINITE_ITINERARY_INVALID','Outside the finite explicit itinerary data domain',str(exc)[:500])from exc
        for path,data in inputs.items():
            if self.secure_bytes(path) != data:
                raise APIError('SOURCE_CHANGED','Input changed during finite itinerary preview')
        return {'tool':'opentrack_preview_finite_explicit_itinerary','preview_only':True,'saved':False,
                'publication_review_pending':True,'native_runtime_ready':False,'fresh_archive_reload_verified':True,
                'source_bindings':{'documents':{k:v.model_dump()for k,v in args.documents.items()},'dest_catalog':args.dest_catalog.model_dump()},
                'output_sha256':actual,'receipt':receipt,
                'limitations':['Each Route and Path still requires the existing simple continuous-chain domain.',
                               'Only finite explicit Path occurrences; no infinite loop, automatic turnback, nested connector continuation or runtime feasibility guarantee.',
                               'No archive bytes are written or exported; native execution belongs to OpenTrack.']}

def tool_definitions(root):
    service=FiniteItineraryTools(root)
    return [('opentrack_preview_finite_explicit_itinerary','Create a finite itinerary from explicit continuous Path occurrences, including revisits. Preview from the supplied inventory or publish a fresh changed document and .dest pair using a matching SHA-bound project .run. No native execution.',PreviewFiniteItinerary,service.preview,False,False)]
