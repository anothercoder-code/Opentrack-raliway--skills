"""MCP stdio, local REST and JSON CLI frontends; never launch OpenTrack."""
import sys
if sys.version_info[:2] != (3, 13):
    sys.stderr.write("OpenTrack zeroaccept1 requires Python 3.13.x.\n")
    raise SystemExit(2)

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf8')
if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf8')
from opentrack_ai.errors import APIError
from opentrack_ai.registry import Registry
from opentrack_ai.service import Service


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,help='Explicit authorized data root, separate from the Skill directory')
    parser.add_argument('--allow-apply',action='store_true',help='Legacy compatibility flag only; does not remove quarantine or software-authorization requirements. Current fresh publishers use their own contracts.')
    parser.add_argument('--runtime-read',action='store_true',help='Enable explicitly authorized read-only train/Step process inspection')
    parser.add_argument('--profile',choices=['all','generation','simulation-evidence'],default='all',help='generation registers a compact operational-data toolset; all retains full inspection/editing tools')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('stdio',help='Official SDK MCP stdio server')
    commands.add_parser('tools',help='Print MCP-compatible tool descriptions/schemas as JSON')
    call=commands.add_parser('call',help='Invoke one tool and print one JSON envelope')
    call.add_argument('tool');inputs=call.add_mutually_exclusive_group()
    inputs.add_argument('--args-file',type=Path);inputs.add_argument('--json')
    http=commands.add_parser('http',help='Serve the optional REST interface on loopback only')
    http.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    registry=Registry(Service(args.root,args.allow_apply,args.runtime_read),profile=args.profile)
    if args.command=='tools':print(json.dumps({'tools':registry.list()},ensure_ascii=False));return
    if args.command=='call':
        try:
            body=args.args_file.read_text(encoding='utf-8-sig') if args.args_file else (args.json if args.json is not None else ('{}' if sys.stdin.isatty() else sys.stdin.read() or '{}'))
            result=registry.envelope(args.tool,json.loads(body))
        except (OSError,ValueError) as e:result={'ok':False,'error':{'code':'ARGUMENTS_UNREADABLE','message':str(e)}}
        print(json.dumps(result,ensure_ascii=False,allow_nan=False));raise SystemExit(0 if result['ok'] else 2)
    if args.command=='stdio':
        from opentrack_ai.transports import run_mcp
        asyncio.run(run_mcp(registry));return
    if not 1<=args.port<=65535:parser.error('port must be between 1 and 65535')
    import uvicorn
    from opentrack_ai.transports import create_http
    uvicorn.run(create_http(registry),host='127.0.0.1',port=args.port)


if __name__=='__main__':
    try:main()
    except APIError as e:
        print(json.dumps({'ok':False,'error':e.as_dict()},ensure_ascii=False),file=sys.stderr if 'stdio' in sys.argv else sys.stdout);raise SystemExit(2)
