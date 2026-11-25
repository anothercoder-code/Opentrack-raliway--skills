"""Local Shunting/Overlap preview and native archive edits."""
from typing import Annotated, Any, Literal
from pydantic import Field, StrictFloat, StrictInt, StrictStr, model_validator

from .tools import Input, ArchiveTools, sha
from .bundle_tools import Source
from .next_tools import NextFunctions, Save
from .operation_tools import Changes, I32, Name, RouteSelector
from ..errors import APIError

class PreviewCurrentShunting(Input):
    source: Source
    operation: Literal['inspect', 'inspect_inventory', 'update_parameters', 'create', 'bind_overlap', 'unbind_overlap', 'delete']
    spec: dict[str, Any]
    preview_only: Literal[True] = True


ShuntingSpeed = Annotated[StrictFloat | StrictInt, Field(gt=0, le=1000, allow_inf_nan=False)]


class ShuntingChanges(Changes):
    speed_kmh: ShuntingSpeed | None = None
    release_time_s: I32 | None = None
    reservation_time_s: I32 | None = None


class EditCurrentShunting(Save):
    source: Source
    shunting: RouteSelector
    changes: ShuntingChanges


Description = Annotated[StrictStr, Field(max_length=4096, pattern=r'^[ -~]*$')]
NewShuntingName = Annotated[StrictStr, Field(min_length=1, max_length=200, pattern=r'^[ -~]+$')]
EndSequence = Annotated[list[I32], Field(min_length=2, max_length=1000)]


class CreateShunting(Input):
    action: Literal['create']
    name: NewShuntingName
    description: Description = ''
    end_ids: EndSequence
    speed_kmh: ShuntingSpeed
    release_time_s: I32
    reservation_time_s: I32
    rsp_id_policy: Literal['wrapper_only', 'original_first_save'] = 'wrapper_only'


class DeleteShunting(Input):
    action: Literal['delete']
    shunting: RouteSelector


class ReplaceShuntingMovement(Input):
    action: Literal['replace_movement']
    shunting: RouteSelector
    end_ids: EndSequence
    description: Description | None = None

    @model_validator(mode='after')
    def explicit_description(self):
        if 'description' in self.model_fields_set and self.description is None:
            raise ValueError('Omit description to retain the existing value')
        return self


class BindShuntingOverlap(Input):
    action: Literal['bind_overlap']
    route: RouteSelector
    shunting: RouteSelector
    selection_policy: Literal['route_terminal', 'same_document_explicit'] = 'route_terminal'


class UnbindShuntingOverlap(Input):
    action: Literal['unbind_overlap']
    route: RouteSelector


class EditShuntingStructure(Save):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    target_document: Name
    dest_catalog: Source
    operation: Annotated[CreateShunting | DeleteShunting | ReplaceShuntingMovement | BindShuntingOverlap |
                         UnbindShuntingOverlap, Field(discriminator='action')]


class ShuntingParameterEdits(NextFunctions):
    def edit(self, args):
        from .current_shunting_workflow.parameters import update_parameters

        if self.path(args.source.path).suffix != '.opentrack':
            raise APIError('DOCUMENT_SCOPE', 'A current .opentrack source is required')
        if not args.preview_only and self.path(args.target_path).suffix != '.opentrack':
            raise APIError('DOCUMENT_SCOPE', 'A fresh .opentrack target is required')
        path, original, _, _ = self.checked(args.source)
        spec = {
            'shunting': args.shunting.model_dump(),
            'changes': args.changes.model_dump(exclude_unset=True),
        }
        try:
            output, verified = update_parameters(original, spec)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_SHUNTING_INVALID', 'Outside local Shunting parameter edit contract', str(exc)[:500]) from exc
        if verified['output_sha256'] != sha(output):
            raise APIError('CURRENT_ARCHIVE_VERIFY', 'Shunting edit output hash mismatch')
        report = {
            'operation': verified['operation'],
            'details': verified['details'],
            'complete_project_validated': False,
        }
        return self.finish(args, path, original, output, report)


    def edit_structure(self, args):
        from .current_shunting_workflow.structure import edit_structure
        from .itinerary_edit_tools import bound_dest_catalog

        if not args.preview_only and self.path(args.target_path).suffix != '.opentrack':
            raise APIError('DOCUMENT_SCOPE', 'A fresh .opentrack target is required')
        inputs = {name: self.checked(source) for name, source in args.documents.items()}
        if args.target_document not in inputs or len({row[0] for row in inputs.values()}) != len(inputs):
            raise APIError('DOCUMENT_SCOPE', 'Supply distinct project documents including the target document')
        run_path, run_bytes, scope_check, scope = self.checked_document_list(args, inputs)
        catalog_path, catalog_bytes, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run_path, run_bytes, catalog_path)
        source_path, original, _, _ = inputs[args.target_document]
        documents = {name: row[1] for name, row in inputs.items()}
        spec = args.operation.model_dump(exclude={'action'}, exclude_none=True)
        try:
            output, verified = edit_structure(documents, catalog_bytes, args.target_document,
                                              args.operation.action, spec)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_SHUNTING_INVALID', 'Outside native Shunting structure edit scope', str(exc)[:500]) from exc
        if verified['output_sha256'] != sha(output):
            raise APIError('CURRENT_ARCHIVE_VERIFY', 'Shunting structure output hash mismatch')
        report = {'operation': verified['operation'], 'details': verified['details'],
                  'document_scope': scope, 'run_source_sha256': sha(run_bytes),
                  'dest_catalog_sha256': sha(catalog_bytes), 'native_runtime_verified': False}
        dependencies = {run_path: run_bytes, catalog_path: catalog_bytes,
                        **{row[0]: row[1] for name, row in inputs.items() if name != args.target_document}}
        return self.finish(args, source_path, original, output, report, dependencies, scope_check)


class CurrentShuntingTools(ArchiveTools):
    def preview(self,args):
        if args.preview_only is not True:
            raise APIError('PREVIEW_ONLY','Only in-memory Shunting/Overlap data preview is available.')
        from .current_shunting_workflow import core
        p=self.path(args.source.path);data=self.secure_bytes(p)
        if sha(data)!=args.source.sha256:raise APIError('SOURCE_CHANGED','Source SHA binding differs')
        try:
            spec=args.spec
            if args.operation=='inspect_inventory':
                if spec:raise ValueError('Inventory spec must be empty')
                from .current_shunting_workflow.inventory import inspect_inventory
                result=inspect_inventory(data);out=None
            elif args.operation=='update_parameters':
                from .current_shunting_workflow.parameters import update_parameters
                out,result=update_parameters(data,spec)
            elif args.operation=='inspect':
                if spec:raise ValueError('Inspection spec must be empty')
                result=core.inspect(data);out=None
            elif args.operation=='create':out,result=core.create(data,spec)
            elif args.operation=='bind_overlap':
                if set(spec) not in ({'route','shunting'},{'route','shunting','selection_policy'}) or spec['shunting'] is None:raise ValueError('Exact route and non-null shunting references required; use unbind_overlap to clear')
                out,result=core.bind_overlap(data,spec['route'],spec['shunting'],spec.get('selection_policy','route_terminal'))
            elif args.operation=='unbind_overlap':
                if set(spec)!={'route'}:raise ValueError('Exact route reference required')
                out,result=core.bind_overlap(data,spec['route'],None)
            else:out,result=core.delete(data,spec)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:
            raise APIError('CURRENT_SHUNTING_INVALID','Outside local current Shunting/Overlap data contract',str(exc)[:500])from exc
        if self.secure_bytes(p)!=data:raise APIError('SOURCE_CHANGED','Source changed during preview')
        if out is not None and result.get('output_sha256')!=sha(out):raise APIError('PREVIEW_MANIFEST','Output hash mismatch')
        result.update(tool='opentrack_preview_current_shunting',source_binding=args.source.model_dump(),preview_only=True,saved=False,publication_review_pending=True,native_execution=False)
        return result

def tool_definitions(root):
    service=CurrentShuntingTools(root)
    edits = ShuntingParameterEdits(root)
    return [
        ('opentrack_preview_current_shunting','Read-only inspect_inventory of documented Document3/4 local Shunting records (without expanding create/delete scope; update_parameters separately supports exact local known layouts for speed/release/reservation only), or inspect/preview local current Document4 Shunting creation/deletion and Route Overlap binding/unbinding (default route_terminal; opt-in same_document_explicit, no prior-Route reentry or recursive Overlap). Correct automatic Path/body reference records, simple directed End chains and fresh RSP allocator. To save, use opentrack_edit_current_shunting or opentrack_edit_current_shunting_structure with its project bindings.',PreviewCurrentShunting,service.preview),
        (
            'opentrack_edit_current_shunting',
            'Edit speed_kmh, release_time_s or reservation_time_s of one local saved Shunting '
            'identified by its automatic Path name, array_id and start_id. Requires a SHA-bound '
            'Document3/4; verifies ownership, preserves IDs and references, and reloads the native '
            'archive. Preview by default; save only to an explicit fresh copy.',
            EditCurrentShunting,
            edits.edit,
            False,
            False,
        ),
        (
            'opentrack_edit_current_shunting_structure',
            'Create, delete or change the movement of an existing local Shunting, or bind/unbind a Route Overlap. '
            'Requires current Document4, the SHA-bound run document set and DestInfo catalog. Checks connected '
            'directional Ends, native identities and saved dependencies. For new Shunting, original_first_save '
            'advances the End RSP counter twice, as the original first save does. Preview or save a new .opentrack copy.',
            EditShuntingStructure,
            edits.edit_structure,
            False,
            False,
        ),
    ]
