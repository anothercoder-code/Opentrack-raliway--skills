"""SHA-bound finite itinerary data preview, no persistence or execution."""
from typing import Annotated, Literal
from pydantic import Field
from .tools import Input, ArchiveTools, PathText, sha
from .bundle_tools import Source
from .multi_document_tools import Name, Ref
from ..errors import APIError

class PreviewFiniteItinerary(Input):
    domain: Literal['finite_explicit_itinerary']
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    document_paths: Annotated[dict[Name, PathText], Field(min_length=1, max_length=100)]
    dest_catalog: Source
    complete_document_set: Literal[True]
    name: Name
    paths: Annotated[list[Ref], Field(min_length=1, max_length=1000)]
    preview_only: Literal[True] = True

class FiniteItineraryTools(ArchiveTools):
    def preview(self, args):
        from .finite_itinerary_workflow import create_finite_itinerary
        if '$dest_catalog' in args.documents or set(args.documents)!=set(args.document_paths):
            raise APIError('FINITE_ITINERARY_BINDING','Document keys and exact native path keys must match; reserved catalog role cannot be a document name')
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
    return [('opentrack_preview_finite_explicit_itinerary','Create an in-memory finite itinerary with explicit ordered Path occurrences, including revisits. Exact document/name/ID bindings, continuous endpoints, bounded expansion; existing Route/Path guards unchanged. No save, export or native execution.',PreviewFiniteItinerary,service.preview)]
