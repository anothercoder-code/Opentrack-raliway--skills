"""Rebuilt, preview-only local Shunting/Overlap adapter."""
from typing import Any, Literal
from .tools import Input, ArchiveTools, sha
from .bundle_tools import Source
from ..errors import APIError

class PreviewCurrentShunting(Input):
    source: Source
    operation: Literal['inspect', 'inspect_inventory', 'update_parameters', 'create', 'bind_overlap', 'unbind_overlap', 'delete']
    spec: dict[str, Any]
    preview_only: Literal[True] = True

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
    return [('opentrack_preview_current_shunting','Read-only inspect_inventory of documented Document3/4 local Shunting records (without expanding create/delete scope; update_parameters separately supports exact local known layouts for speed/release/reservation only), or inspect/preview local current Document4 Shunting creation/deletion and Route Overlap binding/unbinding (default route_terminal; opt-in same_document_explicit, no prior-Route reentry or recursive Overlap). Correct automatic Path/body reference records, simple directed End chains and fresh RSP allocator; hashes/readback only, no source writes or native execution.',PreviewCurrentShunting,service.preview)]
