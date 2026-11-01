"""Finite current-schema Edge scalar setters. Pure bytes; no GUI or engine.

Global modelID selection deliberately keeps legitimate End/Route observers.
No child mutable tables are changed, so shared speed tables remain untouched.
"""
import math
import struct
from opentrack_ai.current_archive import writer as w, route_factory as rf
from opentrack_ai.current_archive import graph_references as gr
from opentrack_ai.current_archive.station_operations import _snapshot

class EdgeError(ValueError): pass
FIELDS = {'length_m': (1, '0x4baf1c'), 'radius_raw': (2, '0x4bb368'), 'gradient_raw': (3, '0x4bbbc4')}

def require(ok, message):
    if not ok: raise EdgeError(message)

def integer(v):
    require(type(v) is int and -(2**31)<=v<2**31, 'Exact signed int32 required')
    return v

def native_float(v):
    require(type(v) in (int,float), 'Exact int or float required; bool/string refused')
    try:
        require(math.isfinite(v), 'Finite API float required')
        bits=struct.pack('<f',v)
    except (OverflowError,struct.error) as ex: raise EdgeError('Float32 overflow') from ex
    require(math.isfinite(struct.unpack('<f',bits)[0]), 'Finite float32 required')
    return w.WireFloat(bits,b'f','little')

def float_report(v):
    if isinstance(v,float):
        bits=v.bits.hex() if isinstance(v,w.WireFloat) else struct.pack('<f',v).hex()
        return {'value':v if math.isfinite(v) else None,'classification': 'finite' if math.isfinite(v) else ('nan' if math.isnan(v) else 'infinity'), 'float32_bits':bits, 'byte_order':getattr(v,'byte_order','little')}
    return v

def state(blob, model_id):
    require(type(blob) is bytes,'Immutable bytes required')
    integer(model_id)
    root,version=w.load_next_compatible(blob)
    objects,counts=gr.reference_inventory(root)
    require(counts[id(root)]==0,'Aliased document root unsupported')
    
    require(sum(w.kind(o)=='OTDocument' for o in objects)==1,'Multiple document namespaces refused')
    signatures={}
    for o in objects:
        cls=o.clazz; chain=[]
        while cls is not None:
            chain.append((cls.name,cls.version)); cls=cls.superclass
        sig=tuple(chain)
        require(o.clazz.name not in signatures or signatures[o.clazz.name]==sig,'Class namespace collision')
        signatures[o.clazz.name]=sig
    models,by_id=rf.document(root)
    require(model_id in by_id,'modelID absent in this document; no cross-document remapping')
    edge=by_id[model_id]
    rf.layout(edge,'OTEdgeModel',3,rf.EDGE,graphic=True)
    for end in [edge.contents[7].value,edge.contents[8].value]:
        rf.layout(end,'OTEndModel',7,rf.END,graphic=True)
        require(by_id.get(end.contents[0].value) is end,'End mapping outside selected document')
        require(edge in [end.contents[9].value,end.contents[10].value],'End/Edge reciprocal mapping absent')
    for i in (0,1,4,5):integer(edge.contents[9].values[i])
    for i in (2,3): require(isinstance(edge.contents[9].values[i],float),'Source float storage required')
    return root,version,edge

def patch_edge_archive(blob, model_id, changes):
    """Return (new bytes, JSON-safe report). No construction or physical validity claim.

    length_m uses native signed int32 domain (including negative values); this is
    storage/setter equivalence, NOT validation of useful railway geometry.
    radius/gradient physical units are deliberately unclaimed. Finite float32 API
    is narrower than original C float domain; untouched NaN payloads are retained.
    """
    require(type(changes) is dict and changes and set(changes)<=set(FIELDS),'Nonempty supported field dictionary required')
    values={k:integer(v) if k=='length_m' else native_float(v) for k,v in changes.items()}
    root,version,edge=state(blob,model_id)
    before=_snapshot(root); allowed=set(); report=[]
    source_floats={k:float_report(edge.contents[9].values[FIELDS[k][0]]) for k in ('radius_raw','gradient_raw')}
    for k,v in values.items():
        slot,address=FIELDS[k];old=edge.contents[9].values[slot]
        edge.contents[9].values[slot]=v;allowed.add((id(edge),9,slot))
        report.append({'field':k,'setter':address,'before':float_report(old),'stored':float_report(v)})
    after=_snapshot(root)
    require(before.keys()==after.keys() and all(after[k]==v for k,v in before.items() if k not in allowed),'Unexpected graph field/reference change')
    out=w.dump_verified(root,version)
    fresh,_=w.load_next_compatible(out)
    require(w.fingerprint(fresh)==w.fingerprint(root),'Fresh writer graph mismatch')
    return out,{'operation':'patch_edge_archive','model_id':model_id,'changes':report,'source_float_fields':source_floats,'whole_graph_expected_fields_only':True,'native_application_tested':False,'simulation_tested':False}
