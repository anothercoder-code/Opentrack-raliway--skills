"""Typed .run wrappers: pure value edits; all publication uses shared transaction."""
import re
from typing import Annotated, Literal
from pydantic import Field, StrictStr
from .tools import ArchiveTools, Input, PathText, sha
from .bundle_tools import Source
from .next_tools import Save
from . import runfile_parameters as pure
from ..errors import APIError
from ..json_safe import checked_json

RunKey=Literal['Start Day Offset','Start Time','Stop Day Offset','Stop Time','Step']
class InspectRunfile(Input):
    source_path:PathText
class EditRunfile(Save):
    source:Source
    changes:Annotated[dict[RunKey,Annotated[StrictStr,Field(min_length=1,max_length=100)]],Field(min_length=1,max_length=5)]

def independent_records(blob):
    """Separate exact byte-record decoder, not the pure module's scanner."""
    records=[]
    for line in blob.split(b'\n'):
        if line.endswith(b'\r'):line=line[:-1]
        if not line or line.startswith(b'//'):continue
        match=re.fullmatch(rb'([^#\r\n]+)#([^#\r\n]*)#',line)
        if match is None:raise ValueError('Independent run record decode failed')
        records.append((match[1],match[2]))
    return records

def verify_output(blob):
    independent_records(blob)
    report=pure.inspect_runfile(blob)
    if not report['editable']:raise ValueError('Edited run failed independent/fresh validation')

def text_report(report):
    return {'editable':report['editable'],'issues':report['issues'],
            'parameters':{k.decode('ascii'):None if v is None else v.decode('ascii') for k,v in report['parameters'].items()},
            'readonly':[{'key':k.decode('ascii'),'value':v.decode('ascii')} for k,v in report['readonly']],
            'numeric':report['numeric']}

class RunfileTools(ArchiveTools):
    def read_run(self,value):
        path=self.path(value)
        if path.suffix!='.run':raise APIError('RUNFILE_PATH','Use an explicit .run source or target')
        return path,self.secure_bytes(path)
    def inspect_run(self,args):
        path,blob=self.read_run(args.source_path)
        try:report=text_report(pure.inspect_runfile(blob))
        except (ValueError,TypeError,OverflowError) as exc:raise APIError('RUNFILE_FORMAT',str(exc)[:500]) from exc
        if self.secure_bytes(path)!=blob:raise APIError('SOURCE_CHANGED','Run changed during inspection')
        return checked_json({'source_path':args.source_path,'source_sha256':sha(blob),'source_bytes':len(blob),**report,'native_application_started':False})
    def edit_run(self,args):
        path,original=self.read_run(args.source.path)
        if sha(original)!=args.source.sha256:raise APIError('SOURCE_CHANGED','Run differs from inspected SHA-256')
        if args.target_path is not None and self.path(args.target_path).suffix!='.run':raise APIError('RUNFILE_PATH','Target must have .run suffix')
        try:
            changes={k.encode('ascii'):v.encode('ascii') for k,v in args.changes.items()}
            output=pure.edit_runfile(original,changes)
            verify_output(output)
            before=independent_records(original);after=independent_records(output)
            expected=[(k,changes.get(k,v)) for k,v in before]
            if after!=expected:raise ValueError('Independent field preservation check failed')
            
            expected_bytes=original
            for k,v in changes.items():
                old=next(v0 for k0,v0 in before if k0==k)
                
                pattern=rb'(?m)^'+re.escape(k+b'#'+old+b'#')+rb'(?=\r?$)'
                expected_bytes,count=re.subn(pattern,lambda _: k+b'#'+v+b'#',expected_bytes)
                if count!=1:raise ValueError('Independent replacement not unique')
            if output!=expected_bytes:raise ValueError('Non-value byte change detected')
        except (ValueError,TypeError,OverflowError) as exc:raise APIError('RUNFILE_VERIFY',str(exc)[:500]) from exc
        old=dict(before)
        result=checked_json({'preview_only':args.preview_only,'saved':False,'source_path':args.source.path,'source_sha256':sha(original),
            'input_sources':[{'path':args.source.path,'sha256':sha(original)}],
            'output_sha256':sha(output),'output_bytes':len(output),'changes':[{'key':k,'before':old[k.encode()].decode('ascii'),'after':v} for k,v in args.changes.items()],
            'independent_parse_verified':True,'unselected_bytes_unchanged':True,'native_application_started':False,
            'function_evidence':['0x6109d4','0x612998','0x612b6c','0x5dcaa0'],
            'input_domain':'Canonical ASCII times/day offsets and positive float32 step; stricter API guards, not native business limits',
            'simulation_executed':False})
        if args.preview_only:
            if self.secure_bytes(path)!=original:raise APIError('SOURCE_CHANGED','Run changed during preview')
            return result
        return self.save_copy(path,original,output,result,args.target_path,validate_output=verify_output)

def tool_definitions(root):
    service=RunfileTools(root)
    return [
        ('opentrack_inspect_runfile_parameters','Inspect exact .run time parameters and source SHA; no path resolution or simulation.',InspectRunfile,service.inspect_run),
        ('opentrack_edit_runfile_parameters','Preview by default or atomically save a fresh .run copy editing only five proven time keys; values are exact ASCII strings, SHA required. No simulation.',EditRunfile,service.edit_run,False,False),
    ]
