"""Compose continuous saved Shunting segments into one native Route overlap."""

from typing import Annotated

from pydantic import Field

from ..errors import APIError
from .bundle_tools import Source
from .current_shunting_tools import Description, NewShuntingName, ShuntingSpeed
from .current_shunting_workflow import core
from .current_shunting_workflow.structure import edit_structure
from .itinerary_edit_tools import bound_dest_catalog
from .next_tools import NextFunctions, Save
from .operation_tools import I32, Name, RouteSelector
from .tools import sha


class ComposeOverlap(Save):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    target_document: Name
    dest_catalog: Source
    route: RouteSelector
    segments: Annotated[list[RouteSelector], Field(min_length=2, max_length=100)]
    name: NewShuntingName
    description: Description = ''
    speed_kmh: ShuntingSpeed
    release_time_s: I32
    reservation_time_s: I32


def compose_overlap(documents, catalog, target, route, segments, settings):
    """Publish one continuous overlap representation without nested references."""
    source = documents[target]
    _, _, _, rows = core.load(source)
    core.need(2 <= len(segments) <= 100, 'Select at least two existing local Shunting segments')
    chain = []
    original_segments = []
    for reference in segments:
        row = core.select(rows, reference)
        details = core.detail(row)
        original_segments.append(details)
        ends = details['end_ids']
        if chain:
            core.need(chain[-1] == ends[0], 'Overlap segments must meet at the same directional End')
            chain.extend(ends[1:])
        else:
            chain.extend(ends)
        core.need(len(chain) <= 1000, 'Composed overlap exceeds the supported End count')
    core.need(len(set(chain)) == len(chain), 'Composed overlap must not repeat a directional End')

    intermediate, created = edit_structure(documents, catalog, target, 'create',
                                           {**settings, 'end_ids': chain})
    identity = {field: created['details'][field] for field in ('name', 'array_id', 'start_id')}
    output, bound = edit_structure({**documents, target: intermediate}, catalog, target, 'bind_overlap',
                                    {'route': route, 'shunting': identity})
    _, _, _, final_rows = core.load(output)
    overlap = core.detail(core.select(final_rows, identity))
    persisted_segments = [core.detail(core.select(final_rows, ref)) for ref in segments]
    core.need(overlap['end_ids'] == chain and persisted_segments == original_segments,
              'Composed overlap or its source segments differ after reload')
    core.need(overlap['edge_ids'] == [edge for segment in original_segments for edge in segment['edge_ids']],
              'Composed overlap does not cover the ordered original edges')
    return output, {'operation': 'compose_local_route_overlap', 'route': route, 'segments': segments,
                    'previous_overlap': bound['details']['before_overlap'], 'overlap': overlap,
                    'native_overlaps_bound': 1, 'original_segments_preserved': True,
                    'recursive_overlap_written': False, 'native_runtime_verified': False}


class OverlapComposition(NextFunctions):
    def compose(self, args):
        inputs = {name: self.checked(spec) for name, spec in args.documents.items()}
        if args.target_document not in inputs or len({row[0] for row in inputs.values()}) != len(inputs):
            raise APIError('DOCUMENT_SCOPE', 'Supply distinct project documents including the target')
        if not args.preview_only and self.path(args.target_path).suffix != '.opentrack':
            raise APIError('DOCUMENT_SCOPE', 'A fresh .opentrack target is required')
        run, run_bytes, scope_check, scope = self.checked_document_list(args, inputs)
        catalog, catalog_bytes, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run, run_bytes, catalog)
        source, original, _, _ = inputs[args.target_document]
        settings = {field: getattr(args, field) for field in
                    ('name', 'description', 'speed_kmh', 'release_time_s', 'reservation_time_s')}
        try:
            output, report = compose_overlap({name: row[1] for name, row in inputs.items()}, catalog_bytes,
                args.target_document, args.route.model_dump(), [segment.model_dump() for segment in args.segments],
                settings)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_OVERLAP_COMPOSITION', str(exc)[:500]) from exc
        report['document_scope'] = {**scope, 'run_source_sha256': sha(run_bytes),
                                    'dest_catalog_sha256': sha(catalog_bytes)}
        dependencies = {run: run_bytes, catalog: catalog_bytes, **{row[0]: row[1] for name, row in inputs.items()
                                                                 if name != args.target_document}}
        return self.finish(args, source, original, output, report, dependencies, scope_check)


def tool_definitions(root):
    return [('opentrack_compose_current_route_overlap',
             'Compose existing continuous local Shunting segments into one native protection zone and bind '
             'it at the exact terminal End of one Route. Explicit new speed/reservation/release settings, '
             'no nested references, existing segments preserved. Preview or save a fresh .opentrack file.',
             ComposeOverlap, OverlapComposition(root).compose, False, False)]
