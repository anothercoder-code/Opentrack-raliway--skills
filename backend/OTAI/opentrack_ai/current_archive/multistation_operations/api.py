"""Explicit pure-byte entrypoint for later Skill/MCP adapters.

This module has no save/commit API. Files returned here are review candidates.
"""
from .topology import generate_terminal_project
from .operations import compose_services,need,sha

SOURCE_KEYS={'header_document','shapes','depot_template','trains_template','courses_template','timetable_template','connection_template'}
SPEC_KEYS={'schema','execution_root','vehicle','course_template_id','timetable_template_key','plan','bind_connections'}

def generate_from_spec(sources,spec):
    need(type(sources)is dict and set(sources)==SOURCE_KEYS and all(type(b)is bytes for b in sources.values()),'Seven explicit immutable source archives required')
    need(type(spec)is dict and set(spec)==SPEC_KEYS and spec['schema']=='two-station-operating-plan/1','Exact versioned operational specification required')
    donors={k:sources[k+'_template']for k in ('depot','trains','courses','timetable')}
    files,topology=generate_terminal_project(sources['header_document'],sources['shapes'],donors,execution_root=spec['execution_root'])
    stops={sign:{k:s[k]for k in ('document','entry_end_id','exit_end_id','length_m','area_edge_id','departure_end_id')}for sign,s in topology['stops'].items()}
    out,report=compose_services(files,document_paths=topology['document_paths'],stop_specs=stops,vehicle_sources={k:donors[k]for k in ('depot','trains')},vehicle_spec=spec['vehicle'],course_template=sources['courses_template'],timetable_template=sources['timetable_template'],connection_template=sources['connection_template'],course_template_id=spec['course_template_id'],timetable_template_key=spec['timetable_template_key'],plan=spec['plan'],bind_connections=spec['bind_connections'])
    return out,{'schema':'two-station-operating-result/1','source_sha256':{k:sha(b)for k,b in sources.items()},'topology':topology,'operations':report,'files':{k:{'sha256':sha(b),'bytes':len(b)}for k,b in out.items()},'preview_only':True,'saved':False,'native_runtime_ready':False,'publication_review_pending':True}
