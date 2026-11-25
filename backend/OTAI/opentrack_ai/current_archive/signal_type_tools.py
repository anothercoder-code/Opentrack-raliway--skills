"""SHA-bound finite native signal configuration and fresh-document publication."""
from typing import Any
from .tools import ArchiveTools, sha
from .next_tools import Save
from .bundle_tools import Source
from ..errors import APIError

class PreviewSignalType(Save):
    source: Source
    configuration: dict[str, Any]

class SignalTypeTools(ArchiveTools):
    def preview(self, args):
        if not args.preview_only and args.configuration.get('action') in ('inspect', 'inspect_local'):
            raise APIError('SIGNAL_TYPE_READ_ONLY','Inspection actions produce no signal configuration change')
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
        result = {'tool':'opentrack_preview_signal_type_configuration','preview_only':args.preview_only,'saved':False,
                'native_runtime_ready':False,'publication_review_pending':args.preview_only,
                'source_binding':args.source.model_dump(),'output':{'sha256':sha(output),'bytes':len(output)},
                'receipt':receipt,
                'limitations':['Finite stored configuration only; not a complete signal system or control/safety equivalence.',
                               'GUI refresh and native simulation require separate verification.',
                               'Only named types and combinations accepted by the audited core are available.']}
        if args.preview_only:
            return result
        if self.path(args.target_path).suffix.lower() != '.opentrack':
            raise APIError('SIGNAL_TARGET','The fresh signal document must use .opentrack')
        return self.save_copy(path,data,output,result,args.target_path)

def tool_definitions(root):
    service=SignalTypeTools(root)
    return [('opentrack_preview_signal_type_configuration',
             'Inspect, preview configuration, or publish a fresh .opentrack copy from an exact SHA-bound source. Uses bounded generated-graph and local MAIN-family actions; preserves the non-target graph. GUI and simulation are separate.',
             PreviewSignalType,service.preview,False,False)]
