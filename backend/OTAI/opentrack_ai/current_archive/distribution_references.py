"""Read-only named Distribution reference audit. No file I/O or mutations.

Named library is CourseList3/group3; Category interval tables are NOT this library.
No claim of complete project/runtime closure; rename/delete deliberately fail closed.
"""
import hashlib
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.course_factories import timetable
from opentrack_ai.current_archive.incident_operations import SCHEMA as INCIDENT_SCHEMA
from opentrack_ai.current_archive.graph_references import reference_inventory

class ReferenceAuditError(ValueError): pass
class LifecycleBlocked(ReferenceAuditError): pass

CATALOG_KEYS = {'courses': 'CourseFile', 'timetable': 'TimetableFile'}
FIELDS = {'OTTimetable': {16: 'distributionName'}, 'OTIncident': {
    18: 'durationDistributionName', 21: 'beginDistributionName',
    23: 'signalStopDurationDistributionName'}}

KNOWN_CLASSES = {'OTCourseList', 'OTCourse', 'OTTimetable', 'OTIncident',
    'OTDistribution', 'OTDelayIntervalArray', 'OTDelayInterval', 'OTConnection',
    'NSArray', 'NSMutableArray', 'NSDictionary', 'NSMutableDictionary', 'NSString'}


def sha(blob): return hashlib.sha256(blob).hexdigest()
def need(ok, message):
    if not ok: raise ReferenceAuditError(message)


def inspect_references(*, run_bytes, catalogs, name=None):
    """Audit exact supplied catalog bytes, explicitly bound to raw run references.

    catalogs maps roles to {run_path, bytes, sha256}. Only courses/timetable roles
    accepted. Missing roles are reported, not inferred or discovered via filesystem.
    Hash mismatches / ambiguous run bindings fail before parsing archive bytes.
    name=None reports all nonempty references; exact name includes matching nil-free
    fields only. Non-reference same-name strings are never reclassified or changed.
    A dependency receipt must not be reused as write authorization.
    """
    need(type(run_bytes) is bytes, 'Immutable run bytes required')
    need(type(catalogs) is dict and not set(catalogs)-CATALOG_KEYS.keys(), 'Unknown catalog role')
    need(name is None or type(name) is str, 'Exact string name or None required')
    try: lines=run_bytes.decode('utf-8-sig').splitlines()
    except UnicodeError as exc: raise ReferenceAuditError('Run must be UTF-8 text') from exc
    bindings={}; boundaries=[]
    for role,key in CATALOG_KEYS.items():
        matches=[line.split('#') for line in lines if line.split('#')[0]==key]
        need(len(matches)<=1, 'Ambiguous run binding: '+key)
        if not matches: boundaries.append('Missing run binding: '+key);continue
        pieces=matches[0]
        need(len(pieces)==3 and pieces[2]=='' and bool(pieces[1]), 'Malformed run binding: '+key)
        bindings[role]=pieces[1]
    receipt={'run_sha256':sha(run_bytes),'catalogs':{}}
    for role,spec in catalogs.items():
        need(type(spec)is dict and set(spec)=={'run_path','bytes','sha256'}, 'Exact catalog descriptor required')
        need(type(spec['bytes'])is bytes, 'Immutable catalog bytes required')
        need(role in bindings and spec['run_path']==bindings[role], 'Catalog does not match exact run binding: '+role)
        need(spec['sha256']==sha(spec['bytes']), 'Source SHA mismatch: '+role)
        receipt['catalogs'][role]={'run_path':spec['run_path'],'sha256':spec['sha256']}
    refs=[]; library=[]; inspected=[]; library_complete=False
    for role in CATALOG_KEYS:
        if role not in catalogs:
            boundaries.append('Missing related catalog: '+role);continue
        try:
            root,_=w.load_next_compatible(catalogs[role]['bytes'])
            objects,counts=reference_inventory(root)
            unknown=sorted({w.kind(o) for o in objects}-KNOWN_CLASSES)
            if unknown:boundaries.append(role+': unknown consumer classes '+','.join(unknown))
            if counts[id(root)]:boundaries.append(role+': root has incoming reference')
            rows=[]
            shared=sorted({w.kind(o) for o in objects if counts[id(o)]>1 and w.kind(o)!='NSString'})
            if shared:boundaries.append(role+': shared incoming objects '+','.join(shared))
            if role=='courses':
                c.course_items(root)
                if root.contents[0].value!=17: boundaries.append('CourseList internal marker is not 17; inspection only')
                for obj in c.array(root.contents[3].value):
                    c.shape(obj,'OTDistribution',1,['@','i','@'])
                    library.append(c.text(obj.contents[0].value))
                if len(library)!=len(set(library)) or any(not x for x in library):
                    boundaries.append('Empty/duplicate Distribution library name')
                else: library_complete=True
                
                inspected.append({'catalog':role,'class':'OTCourse','result':'No named Distribution field in v11 encoder'})
                for index,obj in enumerate(c.array(root.contents[1].value)):
                    try:
                        c.shape(obj,'OTIncident',12,INCIDENT_SCHEMA)
                        rows.append((str(index),obj,c.text(obj.contents[0].value)))
                    except (ValueError,TypeError,IndexError) as exc:
                        boundaries.append('courses incident '+str(index)+': '+str(exc))
            else:
                rows=[(key,obj,key) for key,obj in timetable(root).items()]
            declared={id(obj) for _,obj,_ in rows}
            for obj in objects:
                if w.kind(obj) in FIELDS and id(obj) not in declared:
                    boundaries.append(role+': consumer outside validated catalog rows: '+w.kind(obj))
            for key,obj,identity in rows:
                klass=w.kind(obj)
                for group,field in FIELDS[klass].items():
                    try:
                        val=obj.contents[group].value
                        value=None if val is None else c.text(val)
                        inspected.append({'catalog':role,'object_key':key,'class':klass,'group':group,'field':field})
                        if value not in (None,'') and (name is None or value==name):
                            refs.append({'catalog':role,'object_key':key,'identity':identity,'class':klass,'group':group,'field':field,'name':value})
                    except (ValueError,TypeError,IndexError) as exc:
                        boundaries.append(role+' '+key+' '+field+': '+str(exc))
        except (ValueError,TypeError,IndexError) as exc:
            boundaries.append(role+': '+str(exc))
    
    boundaries.append('Full project consumer closure and additional run catalogs are not certified; no lifecycle write authorization')
    return {'references':refs,'library_names':library,'library_complete':library_complete,'inspected_fields':inspected,
        'unresolved_reference_names':sorted({x['name'] for x in refs}-set(library)) if library_complete else None,
        'boundaries':boundaries,'complete':False,'rename_supported':False,'delete_supported':False,
        'dependency_receipt':receipt,'outputs':{}}


def rename_distribution(*args, **kwargs):
    raise LifecycleBlocked('Rename blocked: complete consumer scope not certified; original rename does not cascade')


def delete_distribution(*args, **kwargs):
    raise LifecycleBlocked('Delete blocked: complete consumer scope not certified; references and unknown scope must be resolved')
