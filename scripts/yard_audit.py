"""Capture inputs or verify actual native outputs for the bounded yard profile.

Writes only explicit workspace evidence. Never launches OpenTrack or edits its
project, and never equates file results with a visible lamp/GUI observation.
"""
import argparse,json
from pathlib import Path
from yard import require_software_authorization

def main(arguments=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('capture','verify'))
    p.add_argument('--root',required=True)
    p.add_argument('--project',required=True,help='Existing project relative to the authorized data root')
    p.add_argument('--evidence',required=True,help='Evidence directory below OTAI/workspaces, outside the project')
    p.add_argument('--label',required=True)
    p.add_argument('--scenario',choices=('normal','failure'),required=True)
    p.add_argument('--receipt',type=Path,help='yard.py JSON receipt; required for capture')
    p.add_argument('--reference',help='Frozen generated17 directory relative to root; defaults to project at capture')
    p.add_argument('--allow-break-control-changes',action='store_true',
        help='Explicitly attribute only Break Time changes, preserving all other native run bytes')
    p.add_argument('--producer-offset',default='+08:00',help='Actual native header wall-clock offset')
    p.add_argument('--max-header-span-s',type=float,default=60.)
    args=p.parse_args(arguments)
    try:
        require_software_authorization(args.root)
        from yard_profile import output_io as io,output_review as review
        io.need(0<args.max_header_span_s<=600,'Explicit header span must be between0 and600s')
        io.zone(args.producer_offset)
        result=review.capture(args) if args.command=='capture' else review.verify(args)
        print(json.dumps(result,ensure_ascii=True));return 0
    except Exception as exc:
        print(json.dumps({'passed':False,'error_type':type(exc).__name__,'error':str(exc),'code':getattr(exc,'code',None),
            'native_application_started':False,'project_modified':False,'GUI_operated':False},ensure_ascii=True))
        return 2

if __name__=='__main__':raise SystemExit(main())
