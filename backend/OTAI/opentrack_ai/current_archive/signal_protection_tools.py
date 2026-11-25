"""Bounded Route protection-data edits and fresh-document publication."""
from typing import Any
from .tools import Input, ArchiveTools, sha
from .next_tools import Save
from .bundle_tools import Source
from ..errors import APIError

class InspectSignalProtection(Input):
    source: Source

class PreviewSignalProtection(InspectSignalProtection,Save):
    configuration: dict[str, Any]

class SignalProtectionTools(ArchiveTools):
    def source(self, binding):
        path=self.path(binding.path); data=self.secure_bytes(path)
        if sha(data)!=binding.sha256:raise APIError('SOURCE_CHANGED','Archive differs from explicit SHA binding')
        return path,data
    def inspect(self,args):
        from .signal_protection.core import inspect_protection
        path,data=self.source(args.source)
        try: report=inspect_protection(data)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:
            raise APIError('PROTECTION_INVALID','Outside the finite single-document protection-data domain',str(exc)[:500])from exc
        if self.secure_bytes(path)!=data:raise APIError('SOURCE_CHANGED','Archive changed during inspection')
        if type(report)is not dict or report.get('input_sha256')!=sha(data):raise APIError('PREVIEW_MANIFEST','Inspection source hash mismatch')
        return {'tool':'opentrack_inspect_signal_protection','read_only':True,'native_runtime_ready':False,'source_binding':args.source.model_dump(),'report':report}
    def preview(self,args):
        from .signal_protection.api import generate_from_spec
        path,data=self.source(args.source)
        try: output,receipt=generate_from_spec(data,{'input_sha256':sha(data),'configuration':args.configuration})
        except (ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:
            raise APIError('PROTECTION_INVALID','Outside the finite Route protection-data configuration domain',str(exc)[:500])from exc
        if self.secure_bytes(path)!=data:raise APIError('SOURCE_CHANGED','Archive changed during preview')
        if type(output)is not bytes or type(receipt)is not dict or receipt.get('input_sha256')!=sha(data) or receipt.get('output_sha256')!=sha(output):raise APIError('PREVIEW_MANIFEST','Protection receipt does not match actual source/output bytes')
        result = {'tool':'opentrack_preview_signal_protection','preview_only':args.preview_only,'saved':False,'native_runtime_ready':False,'publication_review_pending':args.preview_only,'source_binding':args.source.model_dump(),'output':{'sha256':sha(output),'bytes':len(output)},'receipt':receipt,'limitations':['Stored protection parameters and static shared-resource candidates only. Native dispatch and safety behavior require separate verification.','Single-document simple routes only. No unknown overlap/zone or moving-block construction.']}
        if args.preview_only:
            return result
        if self.path(args.target_path).suffix.lower() != '.opentrack':
            raise APIError('SIGNAL_TARGET','The fresh protection document must use .opentrack')
        return self.save_copy(path,data,output,result,args.target_path)

def tool_definitions(root):
    service=SignalProtectionTools(root)
    return [('opentrack_inspect_signal_protection','Read current single-document signal directions, native type codes and Route protection fields, plus conservative shared Edge/SafetyElement pairs. Not a complete conflict or deadlock proof.',InspectSignalProtection,service.inspect),('opentrack_preview_signal_protection','Preview or publish a fresh .opentrack copy with bounded Route protection parameters and release groups from an exact SHA-bound source. No original execution.',PreviewSignalProtection,service.preview,False,False)]
