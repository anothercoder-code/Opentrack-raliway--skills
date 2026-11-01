"""Narrow current archive Z/V editor; bytes in/out, no filesystem or GUI actions."""
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.graph_references import reference_inventory
from opentrack_ai.engine_curve_exchange import parse_text

class CurveError(ValueError): pass
DIAGRAM=['iiiiiii','@','@','@','@','i','@','@']

def integer(x):
    if type(x) is not int or not -(2**31)<=x<2**31: raise CurveError('Exact signed int32 required; floats, bool, NaN and coercion refused')
    return x

def point_row(p):
    c.shape(p,'OTDPoint',0,['iii'])
    row=tuple(integer(v) for v in p.contents[0].values)
    if row[0]<0 or row[2] not in (1,2):raise CurveError('Only nonnegative speed and point types 1/2 audited')
    return row

def select(root,name,index):
    if type(name) is not str or not name:raise CurveError('Exact Engine name required')
    engines=c.engine_items(root)
    engine=next((e for e in engines if c.text(e.contents[1].value)==name),None)
    if engine is None:raise CurveError('Engine not found')
    ds=c.array(engine.contents[16].value)
    if type(index) is not int or not 0<=index<len(ds):raise CurveError('Existing diagram index required')
    for d in ds:
        c.shape(d,'OTDDiagram',3,DIAGRAM)
        for slot in (1,2):
            rows=[point_row(p) for p in c.array(d.contents[slot].value)]
            if any((r[1]<0)!=(slot==2) for r in rows):raise CurveError('Existing curve has wrong force sign')
            if len({r[0] for r in rows})!=len(rows):raise CurveError('Existing duplicate speeds unsupported')
    return engine,ds,ds[index]

def patch_archive(blob,name,index,*,content=None,points=None,mode='replace',preview=False):
    """points=[(speed_kmh, force_kn, saved_point_type)]; text H is NEXT-row type.
    Returns (None, report) for preview, otherwise (verified archive bytes, report).
    Caller owns atomic persistence. No new diagram/Engine or implicit templates.
    """
    if type(blob) is not bytes:raise CurveError('Immutable archive bytes required')
    if type(preview) is not bool:raise CurveError('preview must be bool')
    if mode not in ('replace','append'):raise CurveError('Only replace/append supported')
    if (content is None)==(points is None):raise CurveError('Supply exactly text or structured points')
    if content is not None:rows,loss=parse_text(content)
    else:
        if type(points) is not list or len(points)>100000:raise CurveError('points must be a list of at most 100000 rows')
        rows=[]
        for row in points:
            if type(row) not in (tuple,list) or len(row)!=3:raise CurveError('Each point requires speed, force, saved type')
            x,y,t=(integer(v) for v in row)
            if x<0 or t not in (1,2):raise CurveError('Nonnegative speed and point type 1/2 required')
            rows.append((x,y,t))
        loss={'parsed_points':len(rows),'flag_semantics':'Structured type is saved point type; no H lag conversion.'}
    root,version=w.load_next_compatible(blob)
    engine,ds,d=select(root,name,index)
    _,counts=reference_inventory(root)
    corridor=[root,engine,engine.contents[16].value,d,d.contents[1].value,d.contents[2].value]
    for obj in corridor:
        if counts[id(obj)]+int(obj is root)!=1:raise CurveError('Shared ownership corridor refused: '+str(w.kind(obj)))
    originals={slot:c.array(d.contents[slot].value) for slot in (1,2)}
    for p in originals[1]+originals[2]:
        if counts[id(p)]!=1:raise CurveError('Shared point refused')
    templates=originals[1]+originals[2]
    if rows and not templates:raise CurveError('Selected diagram must supply an existing OTDPoint template')
    result={slot:list(originals[slot]) if mode=='append' else [] for slot in (1,2)}
    speeds={slot:{point_row(p)[0] for p in result[slot]} for slot in (1,2)}
    skipped=[];split={1:0,2:0};sort_changed=False
    for position,row in enumerate(rows):
        row=tuple(integer(v) for v in row)
        slot=2 if row[1]<0 else 1;split[slot]+=1
        if row[0] in speeds[slot]:skipped.append(position);continue
        speeds[slot].add(row[0])
        result[slot].append(w.GenericArchivedObject(templates[0].clazz,contents=[w.TypedGroup([b'i']*3,row)]))
    for slot in (1,2):
        before=[point_row(p)[0] for p in result[slot]]
        result[slot].sort(key=lambda p:point_row(p)[0]);sort_changed|=before!=sorted(before)
        w.set_elements(d.contents[slot].value,result[slot])
    
    traction=[point_row(p) for diagram in ds for p in c.array(diagram.contents[1].value)]
    braking=[point_row(p) for diagram in ds for p in c.array(diagram.contents[2].value)]
    derived={6:max([0]+[r[1] for r in traction]),7:max([0]+[r[0] for r in traction]),17:min([0]+[r[1] for r in braking])}
    changes=[]
    for slot,value in derived.items():
        changes.append({'group':slot,'before':engine.contents[slot].value,'after':value})
        engine.contents[slot].value=value
    report={'engine':name,'diagram_index':index,'mode':mode,'input':loss,'duplicate_source_indices_skipped':skipped,'sort_changed':sort_changed,
        'sign_split_source_counts':{'traction':split[1],'braking':split[2]},'result_points':{str(slot):[point_row(p) for p in result[slot]] for slot in (1,2)},
        'derived_fields':changes,'powerMax_policy':'Preserved: 004cc798 does not update powerMax',
        'display_axes_policy':'Preserved: no native UI auto-scale', 'native_application_tested':False}
    output=w.dump_verified(root,version)
    fresh,_=w.load_next_compatible(output);actual,_,diagram=select(fresh,name,index)
    if any(actual.contents[k].value!=v for k,v in derived.items()):raise CurveError('Derived reload mismatch')
    for slot in (1,2):
        if [point_row(p) for p in c.array(diagram.contents[slot].value)]!=[point_row(p) for p in result[slot]]:raise CurveError('Point reload mismatch')
    report['fresh_reload_verified']=True
    return (None if preview else output),report
