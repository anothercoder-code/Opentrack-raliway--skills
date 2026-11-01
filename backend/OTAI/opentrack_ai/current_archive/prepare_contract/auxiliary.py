"""Read-only auxiliary .run bindings, from native reader/writer evidence."""
from .. import writer as w, catalogs as c, incident_operations
from ..project_workflow.relocation import DIAGRAM, _layout
from ..zero_operations import run_bundle as rb
from .. import runfile_parameters as rp

AUX_KEYS = frozenset({'Train Diagram Document','Document Set Document','Document Set Name','Incident'})


def need(ok,msg):
    if not ok:raise ValueError(msg)


def records(blob):
    """Strict saved records including named events and repeated ordered sets.

    Unlike fresh generation's rb.records, Incident is a *name*, never a path.
    Document Set Name may repeat as a section marker in exported preferences.
    """
    need(type(blob)is bytes and 0<len(blob)<=1048576,'Immutable nonempty run bytes up to 1 MiB required')
    need(blob.endswith(b'\n'),'Terminated native run records required')
    need(all(c<128 and (c>=32 or c in (10,13))for c in blob),'ASCII run with no extra controls required')
    out=[];seen=set()
    repeated=rp.REPEATED|{b'Document Set Name'}
    groups=rp.NATIVE_GROUPS+((b'Document Set Name',b'Document Set Document'),)
    for chunk in blob.split(b'\n')[:-1]:
        raw=chunk+b'\n';need(len(raw)<=1023,'Native run record limit exceeded')
        body=raw[:-2] if raw.endswith(b'\r\n')else raw[:-1]
        need(b'\r'not in body,'Bare CR is not a run terminator')
        if not body or body.startswith(b'//'):out.append((None,None,raw));continue
        bits=body.split(b'#')
        need(len(bits)==3 and bits[2]==b'' and bits[0]in rp.KNOWN,'Unknown/noncanonical run record')
        key,value=bits[:2]
        need(value and value==value.strip()and b'%'not in value and b'$'not in value,'Empty/padded/macro run value')
        need(key not in seen or key in repeated,'Duplicate singleton run record')
        seen.add(key)
        for group in groups:
            hit=next((t for t in group if t in body),None)
            need(hit is None or hit==key,'Native whole-line token collision')
        out.append((key.decode('ascii'),value.decode('ascii'),raw))
    return out


def core_bytes(rows):
    return b''.join(raw for key,value,raw in rows if key not in AUX_KEYS)


def set_bindings(rows, selected_document_paths):
    """Validate exported preference groups; script execution does not load them."""
    groups=[];seen=set();current=None
    for key,value,_ in rows:
        if key=='Document Set Name':
            need(value not in seen,'Duplicate Document Set name')
            need(current is None or current['documents'],'Empty Document Set group')
            current={'name':value,'documents':[]};groups.append(current);seen.add(value)
        elif key=='Document Set Document':
            need(current is not None,'Document Set Document precedes explicit group name')
            need(value in selected_document_paths,'Document Set refers to a document outside selected infrastructure/diagrams')
            need(value not in current['documents'],'Repeated member within Document Set')
            current['documents'].append(value)
    need(current is None or current['documents'],'Empty Document Set group')
    return {'groups':groups,'binding_checked':True,'script_run_reader_applies_groups':False,
            'semantics':'Ordered exported-preferences document groups. They do not replace explicit Infrastructure/Train Diagram declarations in script runs.'}


def incident_bindings(course_blob,names):
    """Exact CourseList.incidentArray names; no event-name-as-file interpretation."""
    need(type(names)is list and len(names)<=10000,'Bounded incident selection list required')
    need(len(set(names))==len(names),'Duplicate Incident selection name')
    root,_=w.load_next_compatible(course_blob);c.course_items(root)
    incidents=c.array(root.contents[1].value)
    byname={}
    for event in incidents:
        c.shape(event,'OTIncident',12,incident_operations.SCHEMA)
        name=c.text(event.contents[0].value)
        byname.setdefault(name,[]).append(event)
    selected=[]
    for name in names:
        need(len(byname.get(name,[]))==1,'Incident name must match exactly one CourseList event: '+name)
        event=byname[name][0]
        selected.append({'name':name,'stored_type':event.contents[5].values[2],'stored_use_flag':event.contents[7].value & 1})
    return {'selected':selected,'binding_checked':True,'source_is_course_catalog':True,
            'external_files_read':0,'use_flags_modified':False,
            'script_semantics':'Original script runner disables all events, then enables every exact name match; this checker only validates unique requested names.',
            'target_and_trigger_semantics_checked':False}


def diagram_binding(blob, declared_path, station_signs):
    need(type(declared_path)is str and declared_path.endswith('.otsimcor'),'Train diagram binding requires .otsimcor extension')
    root,_=w.load_next_compatible(blob)
    _layout(root,'OTCorridorDocument',13,DIAGRAM)
    actual=c.text(root.contents[2].value).replace('\\','/')
    need(actual==declared_path,'Diagram docFileName differs from declared run binding')
    rows=c.array(root.contents[15].value);need(len(rows)<=10000,'Diagram station list too large')
    indices=set();signs=[]
    for item in rows:
        c.shape(item,'OTCorridorStation',0,['@','iiii','iiii'])
        sign=c.text(item.contents[0].value)
        need(sign in station_signs,'Diagram references missing Station: '+sign)
        index=item.contents[1].values[0]
        need(type(index)is int and index>=0 and index not in indices,'Diagram station index invalid or duplicated')
        indices.add(index);signs.append(sign)
    return {'path':declared_path,'class':'OTCorridorDocument','class_version':13,
            'stored_path_matches':True,'station_signs':signs,'station_references_checked':True,
            'plot_result_data_validated':False,'native_loading_verified':False}
