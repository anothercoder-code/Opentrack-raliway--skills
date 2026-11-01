from typing import Literal
"""Read-only, SHA-bound finite native signal type configuration preview.
No save, GUI invocation, simulation, publication or complete signal-system claim.
"""
from typing import Any
from pydantic import StrictBool
from .tools import Input, ArchiveTools, sha
from .bundle_tools import Source
from ..errors import APIError

class PreviewSignalType(Input):
    source: Source
    configuration: dict[str, Any]
    preview_only: Literal[True] = True

class SignalTypeTools(ArchiveTools):
    def preview(self, args):
        if args.preview_only is not True:
            raise APIError('PREVIEW_ONLY','Only an in-memory signal-data preview is available; no save or publication')
        path=self.path(args.source.path)
        data=self.secure_bytes(path)
        if sha(data)!=args.source.sha256:
            raise APIError('SOURCE_CHANGED','Archive differs from its explicit SHA binding')
        from .signal_type_workflow.core import preview
        try:
            output, receipt=preview(data,args.configuration)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
            raise APIError('SIGNAL_TYPE_INVALID','Outside the finite current-signal configuration domain',str(exc)[:500]) from exc
        if self.secure_bytes(path)!=data:
            raise APIError('SOURCE_CHANGED','Archive changed during preview')
        if type(output)is not bytes or type(receipt)is not dict or receipt.get('input_sha256')!=sha(data) or receipt.get('output_sha256')!=sha(output):
            raise APIError('PREVIEW_MANIFEST','Signal receipt does not match actual input/output bytes')
        return {'tool':'opentrack_preview_signal_type_configuration','preview_only':True,'saved':False,
                'native_runtime_ready':False,'publication_review_pending':True,
                'source_binding':args.source.model_dump(),'output':{'sha256':sha(output),'bytes':len(output)},
                'receipt':receipt,
                'limitations':['Finite stored configuration only; not a complete signal system or control/safety equivalence.',
                               'No GUI refresh, simulation, saving or publication is performed.',
                               'Only named types and combinations accepted by the audited core are available.']}

def tool_definitions(root):
    service=SignalTypeTools(root)
    return [('opentrack_preview_signal_type_configuration',
             'Read-only current-format native signal inspection/configuration preview from an explicit SHA-bound document. Strict generated-graph actions plus SHA/index/ID/name-selected local MAIN-family inspect/configure actions; preserves non-target graph, does not validate the whole project or resolve external connections. No save, GUI or simulation.',
             PreviewSignalType,service.preview)]
