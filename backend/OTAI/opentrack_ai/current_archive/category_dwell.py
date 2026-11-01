"""Current Category v19 native archive setters; integration candidate, not MCP."""
import math
import struct
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT

class CategoryDwellError(ValueError):
    pass


FIELDS = {
 'stop_at_every_station_time_s': (15,0,'f','006c4420','006c4414','nonnegative'),
 'dwell_variation_early': (18,0,'f','006c48e0','006c48d0','identity'),
 'dwell_variation_delayed': (18,1,'f','006c4904','006c48f4','identity'),
 'dwell_variation_early_unit_code': (18,2,'i','006c4928','006c4918','identity'),
 'dwell_variation_delayed_unit_code': (18,3,'i','006c494c','006c493c','identity'),
 'dwell_variation_early_delay_offset_s': (24,0,'f','006c4970','006c4960','at_most_minus_one'),
 'dwell_variation_delayed_delay_offset_s': (24,1,'f','006c49b0','006c49a0','at_least_one'),
}

def normalize(field, value):
    spec = FIELDS[field]
    if spec[2] == 'i':
        if type(value) is not int or not -(2**31) <= value <= 2**31-1:
            raise CategoryDwellError('Unit code requires signed int32; bool/coercion forbidden')
        return value
    if type(value) not in (int,float):
        raise CategoryDwellError('Finite binary32 numeric input required; bool/coercion forbidden')
    try:
        value = float(value)
        if not math.isfinite(value): raise CategoryDwellError('NaN/infinity outside supported finite domain')
        value = struct.unpack('<f',struct.pack('<f',value))[0]
    except (OverflowError,struct.error) as exc:
        raise CategoryDwellError('Outside binary32 domain') from exc
    if not math.isfinite(value): raise CategoryDwellError('Outside finite binary32 domain')
    if spec[5]=='nonnegative': return 0.0 if value < 0.0 else value
    if spec[5]=='at_most_minus_one': return value if value <= -1.0 else -1.0
    if spec[5]=='at_least_one': return value if value >= 1.0 else 1.0
    return value

def select(root,name):
    if type(name) is not str or not name or '\0' in name: raise CategoryDwellError('Exact nonempty NUL-free name required')
    c.train_items(root) 
    cats = c.array(root.contents[1].value)
    by_name = {}
    for cat in cats:
        c.shape(cat,'OTTrainCategory',19,CATEGORY_LAYOUT)
        key=c.text(cat.contents[1].value)
        if not key or key in by_name: raise CategoryDwellError('Empty/ambiguous Category identity')
        by_name[key]=cat
        
        for group,cls in [(10,'OTDelayIntervalArray'),(12,'OTDelayPriorityArray'),(13,'OTPerformanceIntervalArray'),(14,'OTPerformanceIntervalArray')]:
            table=cat.contents[group].value
            if w.kind(table)!=cls or table.clazz.version!=0: raise CategoryDwellError('Missing/unsupported Category table')
            chain=[];cl=table.clazz
            while cl is not None:
                if len(chain)>3: raise CategoryDwellError('Unsupported table hierarchy')
                chain.append((cl.name,cl.version));cl=cl.superclass
            if chain!=[(cls.encode(),0),(b'OTMutableArray',0),(b'NSObject',0)]: raise CategoryDwellError('Unsupported table hierarchy')
            if len(table.contents)!=1 or table.contents[0].encodings!=[b'@'] or len(table.contents[0].values)!=1: raise CategoryDwellError('Incomplete Category table')
            c.array(table.contents[0].value)
    if name not in by_name: raise CategoryDwellError('Selected Category not found')
    selected=by_name[name]
    from .graph_references import incoming_counts
    counts=incoming_counts(root)
    def incoming(target): return counts[id(target)]
    if incoming(selected)!=1 or incoming(root.contents[1].value)!=1:
        raise CategoryDwellError('Shared Category or catalog owner; independent edit refused')
    return selected

def read_archive(blob,name):
    if type(blob) is not bytes: raise CategoryDwellError('Immutable native archive bytes required')
    root,_=w.load_next_compatible(blob);obj=select(root,name)
    result={f:obj.contents[s[0]].values[s[1]] for f,s in FIELDS.items()}
    for period in ('early','delayed'):
        code=result['dwell_variation_'+period+'_unit_code']
        result['dwell_variation_'+period+'_unit']={0:'seconds',1:'percent_of_planned_dwell'}.get(code)
    raw=obj.contents[0].values[1]
    result.update(flags_raw=raw,unknown_flags=(raw & 0xffffffff) & ~0x3f,
                  native_application_tested=False,runtime_cache_fields_included=False)
    return result

def patch_archive(blob,name,changes):
    if type(blob) is not bytes: raise CategoryDwellError('Immutable native archive bytes required')
    if type(changes) is not dict or not changes: raise CategoryDwellError('Nonempty explicit changes required')
    if any(f not in FIELDS for f in changes): raise CategoryDwellError('Unknown/unimplemented field')
    values={f:normalize(f,v) for f,v in changes.items()}
    root,version=w.load_next_compatible(blob);obj=select(root,name);report=[]
    for field,value in values.items():
        group,slot,encoding,setter,getter,_=FIELDS[field]
        before=obj.contents[group].values[slot];obj.contents[group].values[slot]=value
        report.append(dict(field=field,requested=changes[field],before_native=before,after_native=value,group=group,slot=slot,encoding=encoding,setter='0x'+setter,getter='0x'+getter))
    output=w.dump_verified(root,version);fresh,_=w.load_next_compatible(output);actual=select(fresh,name)
    for field,value in values.items():
        g,s,e,*_=FIELDS[field]
        if struct.pack('<'+e,actual.contents[g].values[s])!=struct.pack('<'+e,value): raise CategoryDwellError('Fresh reload bit mismatch')
    return output,dict(name=name,changes=report,fresh_reload_verified=True,native_application_tested=False,reference_changes=False,runtime_cache_recomputed=False,mcp_integrated=False)
