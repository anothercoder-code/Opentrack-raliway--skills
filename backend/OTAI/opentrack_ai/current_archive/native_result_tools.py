from typing import Literal
"""Single-file, SHA-bound read-only native-result parsing preview."""
from typing import Annotated
from pydantic import StrictBool, StrictStr, Field
from .tools import Input, ArchiveTools, sha
from .bundle_tools import Source
from ..errors import APIError

class PreviewNativeResults(Input):
    source: Source
    format: Annotated[StrictStr, Field(min_length=1,max_length=80)]
    encoding: Annotated[StrictStr, Field(min_length=1,max_length=30)] = 'utf-8'
    course_whitelist: list[Annotated[StrictStr,Field(min_length=1,max_length=200)]] | None = None
    preview_only: Literal[True] = True

class NativeResultTools(ArchiveTools):
    def preview(self,args):
        if args.preview_only is not True:
            raise APIError('PREVIEW_ONLY','No save, publication, launch or native success certification')
        from .native_results_workflow.core import parse_result
        path=self.path(args.source.path); blob=self.secure_bytes(path)
        if sha(blob)!=args.source.sha256:raise APIError('SOURCE_CHANGED','Result-file SHA mismatch')
        try:
            parsed=parse_result(blob,args.format,args.encoding,args.course_whitelist)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError,UnicodeError) as exc:
            raise APIError('RESULT_FORMAT_INVALID','Outside supported result-reader contract',str(exc)[:500]) from exc
        if self.secure_bytes(path)!=blob:raise APIError('SOURCE_CHANGED','Result file changed during preview')
        return dict(tool='opentrack_preview_native_results',preview_only=True,saved=False,native_execution=False,
                    native_success=False,native_runtime_ready=False,blocked=True,goal_complete=False,requires_native_validation=True,
                    publication_review_pending=True,source={'path':args.source.path,'sha256':sha(blob),'bytes':len(blob)},
                    result=parsed,limitations=['Parsing supplied bytes does not prove native execution or completion.',
                    'No output creation, process launch, directory scan, publication or changes to runtime preferences.'])

def tool_definitions(root):
    service=NativeResultTools(root)
    return [('opentrack_preview_native_results','Read one explicitly selected SHA-bound native-result text file using a bounded evidenced schema. Return normalized records and descriptive statistics only; never save, launch, or certify simulation success.',PreviewNativeResults,service.preview)]
