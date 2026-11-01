"""Current OTDistribution v1 within OTCourseList v3; pure graph/bytes operations.
No filesystem writes, simulation, native application execution, or reference renames.
"""
import math
import struct
from collections import Counter
from opentrack_ai.current_archive import writer as w, catalogs as c

class DistributionError(ValueError): pass
FIELDS = ('lower_s', 'upper_s', 'percentage')
POLICIES = ('native_setter', 'piecewise_linear_guard')

def require(ok, message):
    if not ok: raise DistributionError(message)

def clone(obj):
    out = w.GenericArchivedObject(obj.clazz, None, [w.TypedGroup(g.encodings, g.values, getattr(g, '_token', None)) for g in obj.contents])
    for key in ('_archive_header', '_root_token'):
        if hasattr(obj, key): setattr(out, key, getattr(obj, key))
    return out

def graph_incoming(root):
    """Count ALL edges, including nested Array/Struct containers; reject cycles.
    Traversal once per container, but every incoming edge counted. No recursion
    through writer.objects (which cannot itself bound recursive Array/Struct).
    """
    from .graph_references import reference_inventory
    _, counts = reference_inventory(root)
    require(counts[id(root)] == 0, 'Aliased distribution document root unsupported')
    
    
    
    seen, active = set(), set()
    def acyclic(value):
        if isinstance(value, w.GenericArchivedObject): children = [v for g in value.contents for v in g.values]
        elif isinstance(value, w.Array): children = [] if isinstance(value.elements, bytes) else value.elements
        elif isinstance(value, w.GenericStruct): children = value.fields
        elif isinstance(value, (list, tuple)): children = value
        else: return
        require(id(value) not in active, 'Cyclic archive/container graph unsupported')
        if id(value) in seen: return
        active.add(id(value)); seen.add(id(value))
        for child in children: acyclic(child)
        active.remove(id(value))
    acyclic(root)
    counts[id(root)] += 1
    return counts

def interval_array(obj):
    require(w.kind(obj) == 'OTDelayIntervalArray' and obj.clazz.version == 0, 'Expected OTDelayIntervalArray v0')
    chain = obj.clazz.superclass
    for name, version in [('OTMutableArray', 0), ('NSObject', 0)]:
        require(chain is not None and chain.name == name.encode() and chain.version == version, 'Unsupported interval-array hierarchy')
        chain = chain.superclass
    require(chain is None and len(obj.contents) == 1 and obj.contents[0].encodings == [b'@'] and len(obj.contents[0].values)==1, 'Unsupported interval-array layout')
    arr = obj.contents[0].value
    rows = c.array(arr)
    for row in rows: c.shape(row, 'OTDelayInterval', 0, ['fff'])
    return arr, rows

def catalog(root):
    graph_incoming(root)
    c.course_array(root)
    arr = root.contents[3].value
    result = {}
    for obj in c.array(arr):
        c.shape(obj, 'OTDistribution', 1, ['@', 'i', '@'])
        name = c.text(obj.contents[0].value)
        require(name and name not in result, 'Empty/duplicate distribution name')
        require(type(obj.contents[1].value) is int and -(2**31)<=obj.contents[1].value<2**31, 'Invalid function int32')
        interval_array(obj.contents[2].value)
        result[name] = obj
    return result

def exclusive(root, obj):
    counts = graph_incoming(root)
    arr, rows = interval_array(obj.contents[2].value)
    for node in [root.contents[3].value, obj, obj.contents[2].value, arr] + rows:
        require(counts[id(node)] == 1, 'Shared mutable distribution owner/interval is unsupported')

def float32(value):
    require(isinstance(value, (int, float)) and not isinstance(value, bool), 'Expected finite float32 number')
    try:
        require(math.isfinite(value), 'Expected finite float32 number')
        out = struct.unpack('<f', struct.pack('<f', value))[0]
    except (OverflowError, struct.error): raise DistributionError('Number outside finite float32 range')
    require(math.isfinite(out), 'Number outside finite float32 range')
    return out

def safe_float(value):
    require(isinstance(value, (int,float)) and not isinstance(value,bool), 'Invalid source float')
    if isinstance(value, w.WireFloat):
        bits = value.bits if value.byte_order == 'little' else value.bits[::-1]
    else: bits = struct.pack('<f',value)
    return {'value': float(value) if math.isfinite(value) else None,
            'classification': 'finite' if math.isfinite(value) else ('nan' if math.isnan(value) else ('positive_infinity' if value > 0 else 'negative_infinity')),
            'ieee754_float32_hex': bits[::-1].hex()}

def validity(rows):
    """API-only guard, NOT native setter acceptance or sampling certification.
    Absolute sum tolerance is sum(0.5 ulp32(stored p)), min 1e-6 percentage
    points. This bounds independent round-to-nearest storage errors, not a
    relative tolerance that accidentally permits materially unnormalised mass.
    """
    issues = []
    if not rows: issues.append('empty_table')
    finite = all(all(math.isfinite(v) for v in row) for row in rows)
    if not finite: return {'passes_api_guard': False, 'issues': ['nonfinite_source'], 'stored_total_percentage': None, 'sum_tolerance_percentage_points': None, 'sampling_validated': False}
    previous = None
    for lower, upper, p in rows:
        if lower < 0 or upper < lower: issues.append('negative_or_reversed_bounds')
        if p < 0 or p > 100: issues.append('percentage_outside_0_100')
        if previous is not None and lower < previous: issues.append('unsorted_or_overlapping')
        previous = upper
    total = math.fsum(row[2] for row in rows)
    tolerance = max(1e-6, math.fsum(2.0**(-150 if p == 0 else max(-149, math.frexp(abs(p))[1]-24)-1) for _,_,p in rows))
    if abs(total-100) > tolerance: issues.append('total_not_100_within_float32_rounding')
    return {'passes_api_guard': not issues, 'issues': sorted(set(issues)), 'stored_total_percentage': total, 'sum_tolerance_percentage_points': tolerance, 'sampling_validated': False}

def details(root):
    return [{'name': name, 'function_code': obj.contents[1].value,
             'business_supported': obj.contents[1].value == 1,
             'intervals': [{k:safe_float(v) for k,v in zip(FIELDS,row.contents[0].values)} for row in interval_array(obj.contents[2].value)[1]],
             'table_guard': validity([row.contents[0].values for row in interval_array(obj.contents[2].value)[1]])}
            for name,obj in catalog(root).items()]

def parse_rows(rows):
    require(type(rows) is list and len(rows)<=10000, 'Expected list of at most 10000 intervals')
    result=[]
    for row in rows:
        require(type(row) is dict and set(row)==set(FIELDS), 'Interval requires exactly lower_s/upper_s/percentage')
        result.append([float32(row[k]) for k in FIELDS])
    return result

def validate_policy(values, policy):
    require(policy in POLICIES, 'Explicit supported validation policy required')
    if policy == 'piecewise_linear_guard':
        require(validity(values)['passes_api_guard'], 'Table fails piecewise-linear API guard: '+','.join(validity(values)['issues']))

def replace(root, name, rows, *, policy):
    lookup=catalog(root);require(name in lookup, 'Unknown exact distribution name')
    obj=lookup[name];exclusive(root,obj)
    require(obj.contents[1].value==1, 'Named business editing supports only function code 1')
    values=parse_rows(rows);validate_policy(values,policy)
    wrapper=obj.contents[2].value;arr,old=interval_array(wrapper)
    
    clazz=old[0].clazz if old else w.Class(b'OTDelayInterval',0,w.Class(b'NSObject',0))
    newrows=[w.GenericArchivedObject(clazz,None,[w.TypedGroup([b'f']*3,v)]) for v in values]
    newarr=clone(arr);w.set_elements(newarr,newrows)
    newwrapper=clone(wrapper);newwrapper.contents[0].value=newarr
    newobj=clone(obj);newobj.contents[2].value=newwrapper
    out=clone(root);library=clone(root.contents[3].value)
    w.set_elements(library,[newobj if item is obj else item for item in c.array(library)])
    out.contents[3].value=library
    return out

def edit_interval(root, name, index, changes, *, policy):
    lookup=catalog(root);require(name in lookup,'Unknown exact distribution name')
    rows=interval_array(lookup[name].contents[2].value)[1]
    require(type(index) is int and 0<=index<len(rows),'Interval index out of range')
    require(type(changes) is dict and changes and set(changes)<=set(FIELDS),'Unknown/empty interval changes')
    
    exclusive(root,lookup[name]);require(lookup[name].contents[1].value==1,'Named business editing supports only function code 1')
    values=[list(r.contents[0].values) for r in rows]
    for field,value in changes.items(): values[index][FIELDS.index(field)]=float32(value)
    validate_policy(values,policy)
    return _replace_values(root,lookup[name],values)

def _replace_values(root,obj,values):
    wrapper=obj.contents[2].value;arr,old=interval_array(wrapper)
    clazz=old[0].clazz if old else w.Class(b'OTDelayInterval',0,w.Class(b'NSObject',0))
    newarr=clone(arr);w.set_elements(newarr,[w.GenericArchivedObject(clazz,None,[w.TypedGroup([b'f']*3,v)]) for v in values])
    wrapper2=clone(wrapper);wrapper2.contents[0].value=newarr
    obj2=clone(obj);obj2.contents[2].value=wrapper2
    out=clone(root);lib=clone(root.contents[3].value);w.set_elements(lib,[obj2 if x is obj else x for x in c.array(lib)]);out.contents[3].value=lib
    return out

def change_interval_count(root,name,*,action,index,interval=None,policy):
    lookup=catalog(root);require(name in lookup,'Unknown exact distribution name');obj=lookup[name]
    exclusive(root,obj);require(obj.contents[1].value==1,'Named business editing supports only function code 1')
    values=[list(r.contents[0].values) for r in interval_array(obj.contents[2].value)[1]]
    require(action in ('insert','delete'),'Expected insert/delete action')
    require(type(index) is int and 0<=index<(len(values)+int(action=='insert')),'Interval index out of range')
    if action=='insert':
        require(len(values)<10000,'Interval limit exceeded');values.insert(index,parse_rows([interval])[0])
    else:
        require(interval is None,'delete cannot supply interval');values.pop(index)
    validate_policy(values,policy);return _replace_values(root,obj,values)

def create(root, *, template_name, new_name, current_class, mode, intervals=None, policy):
    """mode copy: independent deep named graph. mode new: explicit table required.
    A template API composition, not an implementation-count claim for init/copy.
    """
    require(current_class=='OTDistribution:1','Explicit current_class OTDistribution:1 required')
    require(type(new_name) is str and 0<len(new_name)<=200 and all(32<=ord(ch)<127 for ch in new_name) and '#' not in new_name,'Expected unique printable ASCII name 1..200 without #')
    lookup=catalog(root);require(template_name in lookup,'Explicit existing named template required');require(new_name not in lookup,'Distribution name conflict')
    obj=lookup[template_name];exclusive(root,obj);require(obj.contents[1].value==1,'Template must use piecewise-linear code 1')
    require(mode in ('copy','new'),'Expected copy/new mode')
    if mode=='copy':
        require(intervals is None,'copy inherits intervals; use new for explicit replacement')
        values=[list(r.contents[0].values) for r in interval_array(obj.contents[2].value)[1]]
    else:
        require(intervals is not None,'New template-based distribution requires explicit intervals');values=parse_rows(intervals)
    validate_policy(values,policy)
    temporary=_replace_values(root,obj,values);newobj=catalog(temporary)[template_name]
    newobj.contents[0].value=w.GenericArchivedObject(obj.contents[0].value.clazz,None,[w.TypedValue(b'+',new_name.encode('ascii'))])
    out=clone(root);lib=clone(root.contents[3].value);w.set_elements(lib,c.array(lib)+[newobj]);out.contents[3].value=lib
    return out

def transform(blob, operation, **kwargs):
    """Return (actual .courses bytes, JSON-safe report). Source is never modified.
    Reader verification is independent codec structural acceptance, NOT native GUI.
    """
    dispatch={'replace_intervals':replace,'edit_interval':edit_interval,'change_interval_count':change_interval_count,'create':create}
    require(operation in dispatch,'Unsupported operation')
    root,version=w.load_next_compatible(blob);before=w.fingerprint(root)
    out=dispatch[operation](root,**kwargs)
    require(w.fingerprint(root)==before,'Unexpected source graph mutation')
    data=w.dump_verified(out,version);fresh,_=w.load_next_compatible(data)
    require(root.contents[0].value==fresh.contents[0].value, 'CourseList header changed')
    for index in (1,2,4):
        require(w.fingerprint(root.contents[index].value)==w.fingerprint(fresh.contents[index].value), 'Unrelated CourseList graph changed')
    untouched=[];after=catalog(fresh)
    for name,obj in catalog(root).items():
        if operation!='create' and name==kwargs.get('name'): continue
        require(name in after and w.fingerprint(obj)==w.fingerprint(after[name]), 'Unrelated distribution graph changed')
        untouched.append(name)
    return data,{'operation':operation,'source_graph_unchanged':True,'codec_fresh_reload':True,'native_application_reload':False,
                'protected_courselist_groups_verified':[0,1,2,4], 'unchanged_distribution_names':untouched,
                'validation_policy':kwargs.get('policy'), 'distributions':details(fresh)}
