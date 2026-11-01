"""Narrow explicit area-aware domain, separate from frozen point-only wave11.
Pure immutable bytes in/out. Does not run or emulate simulator movement.
"""
import hashlib
from opentrack_ai.current_archive import writer as w, catalogs as c, route_factory as rf, path_functions as pf
from opentrack_ai.current_archive.graph_references import incoming
from opentrack_ai.current_archive.zero_operations import station_binding as sb
from opentrack_ai.current_archive.zero_generation import native_signal_routes as sr
from opentrack_ai.current_archive.graphic_alignment import validate_placement

class AreaError(ValueError): pass
def need(ok,msg):
    if not ok: raise AreaError(msg)
def sha(blob):return hashlib.sha256(blob).hexdigest()
def exact_int(v):need(type(v)is int and 0<=v<2147483647,'Exact nonnegative int32 required');return v

def spec_domain(specs):
    need(type(specs)is list and 1<=len(specs)<=1000,'Explicit bounded area spec list required')
    required={'sign','name','reference_end_id','ordinary_end_ids','placement','station_type_raw','interlock_type_raw','icon_show_type_raw','timing_point','stop'}
    signs=set();selected=set()
    for spec in specs:
        need(type(spec)is dict and set(spec)==required,'Unknown/missing area spec fields')
        sign=sb.text(spec['sign']);sb.text(spec['name']);need(sign not in signs,'Duplicate station sign');signs.add(sign)
        exact_int(spec['reference_end_id'])
        ids=spec['ordinary_end_ids'];need(type(ids)is list and len(ids)<=1,'Only zero or one ordinary double vertex per station area')
        for i in ids:exact_int(i)
        pick=[spec['reference_end_id']]+ids;need(len(set(pick))==len(pick) and not selected.intersection(pick),'Area vertex overlap');selected.update(pick)
        need(all(type(spec[k])is int for k in ('station_type_raw','interlock_type_raw','icon_show_type_raw')) and (spec['station_type_raw'],spec['interlock_type_raw'],spec['icon_show_type_raw'])==(2,4,1),'Observed Station profile 2/4/1 only')
        need(spec['timing_point'] is True,'Timing catalog reference required')
        p=validate_placement(spec['placement'])
        for key in ('x','y','angle'):sb.number(p[key])
        stop=spec['stop']
        if not ids:need(stop is None,'Pass-only StationVertex has no stopping area')
        else:
            need(type(stop)is dict and set(stop)=={'entry_end_id','exit_end_id','area_edge_id','length_m','exit_signal_name','direction'},'Explicit single Edge stop contract required')
            for key in ('entry_end_id','exit_end_id','area_edge_id','length_m'):exact_int(stop[key])
            need(stop['entry_end_id']==ids[0] and stop['exit_end_id']==spec['reference_end_id'],'Stop direction must be explicit entry-to-reference')
            need(stop['length_m']>0 and stop['direction']=='forward_only','Only positive-length forward stopping profile')
            sb.text(stop['exit_signal_name'])
    return signs

def read_document(blob,specs):
    signs=spec_domain(specs)
    need(type(blob)is bytes,'Immutable archive bytes required')
    root,version=w.load_next_compatible(blob);rf.layout(root,'OTDocument',4,sb.DOC)
    need(root.contents[0].value==17,'Current Document marker17 required')
    models,byid=rf.document(root)
    need(incoming(root,root)==0 and incoming(root,root.contents[2].value)==1,'Aliased root/model array unsupported')
    allowed={'OTEndModel','OTEdgeModel','OTElement','OTSignalModel','OTStationModel'}
    need(all(w.kind(m) in allowed for m in models),'Unsupported graphic/connector schema')
    for mid in byid:exact_int(mid)
    sm={}
    for m in models:
        k=w.kind(m)
        if k=='OTEndModel':rf.layout(m,k,7,rf.END,graphic=True)
        elif k=='OTEdgeModel':rf.layout(m,k,3,rf.EDGE,graphic=True)
        elif k=='OTSignalModel':rf.layout(m,k,11,rf.SIGNAL,graphic=True)
        elif k=='OTElement':rf.layout(m,k,0,['i','f','f','f','i','i','@','@'],graphic=True)
        else:
            rf.layout(m,k,1,sb.MODEL,graphic=True);sign=c.text(m.contents[7].value)
            need(sign not in sm,'Duplicate StationModel sign');sm[sign]=m
            need(m.contents[8].values==[2,4] and m.contents[9].values==[1,0],'Unknown StationModel raw profile')
    need(set(sm)==signs,'Exact StationModel/spec identity domain required')
    need(all(o in sm.values() for o in w.objects(root) if w.kind(o)=='OTStationModel'),'Hidden StationModel refused')
    expected={}
    for spec in specs:
        for selected,ty in [(spec['reference_end_id'],2)]+[(i,1)for i in spec['ordinary_end_ids']]:
            e=byid.get(selected);need(e is not None and w.kind(e)=='OTEndModel','Selected End absent')
            r=byid.get(e.contents[8].value)
            need(r is not None and r is not e and w.kind(r)=='OTEndModel' and r.contents[8].value==selected,'Reciprocal pair required')
            for half in (e,r):
                eid=half.contents[0].value;need(eid not in expected,'Overlapping logical station pairs')
                expected[eid]=(sm[spec['sign']],ty)
        stop=spec['stop']
        if stop:
            entry,exit=byid[stop['entry_end_id']],byid[stop['exit_end_id']]
            er=byid[entry.contents[8].value];xr=byid[exit.contents[8].value];edge=byid.get(stop['area_edge_id'])
            need(edge is not None and w.kind(edge)=='OTEdgeModel','Actual area Edge absent')
            need((edge.contents[7].value is er and edge.contents[8].value is exit) or (edge.contents[8].value is er and edge.contents[7].value is exit),'Wrong stopping approach/direction')
            need(edge in (er.contents[9].value,er.contents[10].value) and edge in (exit.contents[9].value,exit.contents[10].value),'Area Edge backreference absent')
            need(all(len([e.contents[i].value for i in (9,10)if e.contents[i].value is not None])==1 for e in (entry,er,exit,xr)),'Stopping area must be unbranched on both halves')
            need(type(edge.contents[9].values[1])is int and edge.contents[9].values[1]==stop['length_m'],'Area actual/spec length mismatch')
            signal=exit.contents[11].value
            need(signal in models and w.kind(signal)=='OTSignalModel' and signal.contents[7].value is exit,'Missing actual directional exit signal')
            need(signal.contents[8].values[:2]==[1,4] and c.text(signal.contents[13].value)==stop['exit_signal_name'],'Not documented ExitSignal type1/main4/name')
            need(entry.contents[11].value is None and er.contents[11].value is None and xr.contents[11].value is None,'No reverse/entry stopping signal in this narrow profile')
    for m in models:
        if w.kind(m)!='OTEndModel':continue
        eid=m.contents[0].value;pair=byid.get(m.contents[8].value)
        need(pair is not None and pair is not m and w.kind(pair)=='OTEndModel' and pair.contents[8].value==eid,'Broken paired End')
        need(type(m.contents[20].value)is int and m.contents[20].value in (1,2),'Unknown Station End type')
        want_station,want_type=expected.get(eid,(None,1))
        need(m.contents[12].value is want_station and m.contents[20].value==want_type,'Unexpected station association/reference type outside explicit area domain')
        need(pair.contents[12].value is m.contents[12].value and pair.contents[20].value==m.contents[20].value,'Pair station/type conflict')
    sr.validate_topology(root)
    return root,version,models,byid

def bind_areas(document_blob,specs):
    """Fresh-only binding. Returns doc, station catalog, receipt, point-only baseline."""
    spec_domain(specs);sb.read_document(document_blob) 
    points=[]
    for spec in specs:
        points.append({k:v for k,v in spec.items()if k not in ('reference_end_id','ordinary_end_ids','stop')}|{'end_ids':[spec['reference_end_id']]})
    point_doc,stations,point_receipt=sb.bind_stations(document_blob,points)
    doc,version,models,byid=sb.read_document(point_doc,True)
    for spec in specs:
        station=byid[spec['reference_end_id']].contents[12].value
        for eid in spec['ordinary_end_ids']:
            e=byid.get(eid);need(e is not None and w.kind(e)=='OTEndModel','Missing ordinary area End')
            for half in (e,byid[e.contents[8].value]):
                pf.guard_counter_references(doc,half)
                need(half.contents[12].value is None and half.contents[20].value==1,'Ordinary pair overlaps existing reference')
                half.contents[12].value=station
    output=w.dump_verified(doc,version);check,cv,cm,ci=read_document(output,specs)
    catalog,_=w.load_next_compatible(stations);need(set(c.station_items(catalog))=={s['sign']for s in specs},'Catalog station closure')
    for m in cm:
        if w.kind(m)=='OTEndModel' and m.contents[12].value is not None:m.contents[12].value=None;m.contents[20].value=1
    w.set_elements(check.contents[2].value,[m for m in cm if w.kind(m)!='OTStationModel'])
    original,ov=w.load_next_compatible(document_blob)
    need(w.dump_verified(check,cv)==w.dump_verified(original,ov),'Original non-target graph/header changed')
    return output,stations,{'source_sha256':sha(document_blob),'output_sha256':sha(output),'stations_sha256':sha(stations),'station_count':len(specs),'stop_area_count':sum(s['stop']is not None for s in specs),'profile':'explicit single-unbranched-Edge area; ordinary type1 never emits station visit','restored_whole_original_graph':True,'point_binding_receipt':point_receipt,'native_simulation_executed':False},point_doc
