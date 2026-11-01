import asyncio
import hmac
import json
import os

from .errors import APIError
from .catalog import SCHEMAS,EVIDENCE
from . import __version__


def create_mcp(registry):
    
    from mcp.server import Server
    import mcp.types as types
    server=Server('opentrack_mcp',version=__version__,instructions='OpenTrack native saved-file tools. Follow each discovered operation contract and guard; metadata reads are not native simulation acceptance. This backend does not drive the GUI or write runtime memory; separately authorized original-app workflows are distinct.')

    @server.list_tools()
    async def list_tools():return [types.Tool(**tool) for tool in registry.list()]

    @server.call_tool()
    async def call_tool(name,arguments):
        result=await asyncio.to_thread(registry.envelope,name,arguments)
        if not result['ok']:raise ValueError(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return [types.TextContent(type='text',text=json.dumps(result,ensure_ascii=False,allow_nan=False))]

    @server.list_resources()
    async def list_resources():
        return [types.Resource(uri='opentrack://contracts',name='Native saved-file contracts',mimeType='application/json'),
            types.Resource(uri='opentrack://evidence-index',name='Registered reverse engineering evidence',mimeType='application/json')]

    @server.read_resource()
    async def read_resource(uri):
        if str(uri)=='opentrack://contracts':return json.dumps(SCHEMAS,ensure_ascii=False)
        if str(uri)=='opentrack://evidence-index':return json.dumps({k:{'path':v[0],'description':v[1]} for k,v in EVIDENCE.items()},ensure_ascii=False)
        raise ValueError('Unknown resource URI')
    return server


async def run_mcp(registry):
    from mcp.server.stdio import stdio_server
    server=create_mcp(registry)
    async with stdio_server() as (reader,writer):
        await server.run(reader,writer,server.create_initialization_options())


def create_http(registry,token=None):
    from fastapi import FastAPI,Request
    from fastapi.responses import JSONResponse
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app=FastAPI(title='OpenTrack AI local API',version=__version__,description='JSON tools for OpenTrack native saved files. This REST endpoint is distinct from the MCP stdio transport.')
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','[::1]'])
    secret=token if token is not None else os.environ.get('OTAI_TOKEN','')

    @app.middleware('http')
    async def local_guard(request:Request,call_next):
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/') not in {f'http://{request.headers.get("host","")}',f'https://{request.headers.get("host","")}'}:
            return JSONResponse({'ok':False,'error':{'code':'ORIGIN_REJECTED'}},status_code=403)
        if secret and request.url.path!='/health' and not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+secret):
            return JSONResponse({'ok':False,'error':{'code':'AUTH_REQUIRED'}},status_code=401)
        if request.method=='POST':
            data=await request.body()
            if len(data)>256*1024:return JSONResponse({'ok':False,'error':{'code':'REQUEST_TOO_LARGE'}},status_code=413)
        return await call_next(request)

    @app.get('/health')
    def health():return {'ok':True,'service':'opentrack_ai','version':__version__}

    @app.get('/v1/tools')
    def tools():return {'tools':registry.list()}

    @app.get('/v1/function-tools')
    def function_tools():
        return {'tools':[{'type':'function','function':{'name':tool['name'],'description':tool['description'],'parameters':tool['inputSchema']}} for tool in registry.list()]}

    @app.post('/v1/tools/{name}')
    def call(name:str,arguments:dict):
        result=registry.envelope(name,arguments)
        return JSONResponse(result,status_code=200 if result['ok'] else 400)
    return app
