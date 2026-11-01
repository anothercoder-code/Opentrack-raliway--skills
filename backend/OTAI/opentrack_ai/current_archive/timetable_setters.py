"""Pure current Timetable9 persisted setters, not GUI/controller propagation.
Filesystem publish, scope authorization and expected SHA belong to the caller.
"""
import hashlib
import re
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.course_factories import timetable

class TimetableError(ValueError): pass

FIELDS = {
    'arrival': (6, 0, '@', '0x6795c8', '0x6795e0'),
    'departure': (7, 0, '@', '0x679690', '0x6796a8'),
    'arrival_day_offset': (15, 0, 'i', '0x6795b4', None),
    'departure_day_offset': (15, 1, 'i', '0x67967c', None),
    'actual_arrival': (13, 0, '@', '0x679a58', None),
    'actual_departure': (14, 0, '@', '0x679acc', None),
    'actual_arrival_day_offset': (15, 2, 'i', '0x679a3c', None),
    'actual_departure_day_offset': (15, 3, 'i', '0x679ab0', None),
}

def validate(field, value, mode):
    group, slot, encoding, *_ = FIELDS[field]
    if encoding == 'i':
        if type(value) is not int or not -(2**31) <= value < 2**31:
            raise TimetableError('Day offset requires signed int32; no coercion or native clamp')
    elif mode == 'strict':
        if type(value) is not str or (value != 'HH:MM:SS' and not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]', value)):
            raise TimetableError('Strict time requires HH:MM:SS, 00:00:00..23:59:59, or undefined sentinel')
    elif value is not None:
        if type(value) is not str: raise TimetableError('Raw native time requires string or nil')
        try: raw = value.encode('utf-8')
        except UnicodeError as e: raise TimetableError('Invalid Unicode') from e
        if b'\0' in raw or len(raw)>1048576:
            raise TimetableError('API guard: no embedded NUL, at most 1 MiB UTF-8')
    return value

def protected_graph(root, target, fields):
    """Graph/alias signature ignoring only explicitly mutable scalar slots."""
    skip={(FIELDS[f][0],FIELDS[f][1]) for f in fields}; seen={}
    def visit(v):
        if isinstance(v,w.GenericArchivedObject):
            if id(v) in seen:return ('ref',seen[id(v)])
            ident=len(seen);seen[id(v)]=ident;cl=v.clazz;chain=[]
            while cl:chain.append((cl.name,cl.version));cl=cl.superclass
            return ('obj',ident,tuple(chain),tuple((tuple(g.encodings),tuple(('edited',) if v is target and (i,j) in skip else visit(x) for j,x in enumerate(g.values))) for i,g in enumerate(v.contents)))
        if isinstance(v,w.Array):return ('array',visit(v.elements) if isinstance(v.elements,bytes) else tuple(visit(x) for x in v.elements))
        if isinstance(v,w.GenericStruct):return ('struct',v.name,tuple(visit(x) for x in v.fields))
        if isinstance(v,w.WireFloat):return ('floatbits',v.encoding,v.byte_order,v.bits)
        if isinstance(v,w.CString):return ('cstring',v.token.data)
        return v
    return visit(root)

def incoming(root,target):
    from .graph_references import incoming
    return incoming(root,target)


def patch_archive(blob, course_id, index, changes, *, time_mode='strict'):
    """Exact CourseID#index, no interval propagation; actual fields require explicit keys.

    raw mirrors the string-copy setters (including nil), not a time parser.
    strict is a deliberately narrower API and never changes days implicitly.
    """
    if type(blob) is not bytes:raise TimetableError('Immutable archive bytes required')
    if type(course_id) is not str or not course_id or type(index) is not int or index<0:raise TimetableError('Exact CourseID and nonnegative integer index required')
    if time_mode not in ('strict','raw'):raise TimetableError('Unknown time mode')
    if type(changes) is not dict or not changes or set(changes)-FIELDS.keys():raise TimetableError('Nonempty supported field map required')
    values={f:validate(f,v,time_mode) for f,v in changes.items()}
    root,version=w.load_next_compatible(blob);rows=timetable(root);key=course_id+'#'+str(index)
    if key not in rows:raise TimetableError('Selected timetable row not found')
    
    
    for saved in rows.values():
        reference=saved.contents[2].value
        reference=None if reference is None else c.text(reference)
        if reference in (None,'','0','-1') and saved.contents[11].value != 0:
            raise TimetableError('Noncanonical unbound interval offset: native 0x67af18 reload would zero it; repair explicitly first')
    row=rows[key]
    if incoming(root,row)!=1 or incoming(root,root):raise TimetableError('Shared row/container ownership unsupported; explicit owner scope required')
    protected=protected_graph(root,row,changes)
    sample=next((x for x in w.objects(root) if w.kind(x)=='NSString'),None)
    if sample is None:raise TimetableError('Missing current string class')
    c.text(sample);report=[]
    for field,value in values.items():
        group,slot,encoding,address,delegate=FIELDS[field];old=row.contents[group].values[slot]
        before=w.string(old) if encoding=='@' else old
        new=(None if value is None else w.GenericArchivedObject(sample.clazz,None,[w.TypedValue(b'+',value.encode('utf-8'))])) if encoding=='@' else value
        row.contents[group].values[slot]=new
        report.append({'field':field,'before':before,'after':value,'group':group,'slot':slot,'encoding':encoding,'unit':'days' if encoding=='i' else 'raw string','setter':address,'delegate':delegate})
    if protected_graph(root,row,changes)!=protected:raise TimetableError('Protected graph changed')
    output=w.dump_verified(root,version);fresh,_=w.load_next_compatible(output);actual=timetable(fresh)[key]
    if protected_graph(fresh,actual,changes)!=protected:raise TimetableError('Protected graph/alias fresh-reload mismatch')
    for field,value in values.items():
        group,slot,encoding,*_=FIELDS[field];got=actual.contents[group].values[slot]
        if (w.string(got) if encoding=='@' else got)!=value:raise TimetableError('Fresh-reload field mismatch')
    return output,{'row':key,'changes':report,'time_mode':time_mode,'fresh_reload_verified':True,'protected_graph_verified':True,'input_sha256':hashlib.sha256(blob).hexdigest(),'output_sha256':hashlib.sha256(output).hexdigest(),'native_application_tested':False,'interval_reference_and_offset_untouched':True,'runtime_cache_serialized':False}
