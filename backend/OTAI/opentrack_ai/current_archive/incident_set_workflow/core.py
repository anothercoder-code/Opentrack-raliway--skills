"""Native IncidentSet data lifecycle; pure bytes, no UI, sampling or execution."""
import hashlib
from opentrack_ai.current_archive import writer as w, catalogs as c, incident_operations as inc
from opentrack_ai.current_archive.disturbance_workflow import core as scenario
from opentrack_ai.current_archive.graph_references import incoming_counts

from opentrack_ai.current_archive.incident_source import (IncidentSourceError as SetError, need, name, chain, mutable, validate_set_graph)

def state(blob):
    root,v,_=scenario.state(blob)
    incidents,lookup=validate_set_graph(root)
    return root,v,incidents,lookup

def make_set(root,n,members):
    arr=w.GenericArchivedObject(root.contents[1].value.clazz,[]);w.set_elements(arr,members)
    cls=w.Class(b'OTIncidentSet',0,w.Class(b'OTOrgArray',2,w.Class(b'OTMutableArray',0,w.Class(b'NSObject',0))))
    return w.GenericArchivedObject(cls,[w.TypedValue(b'@',arr),w.TypedValue(b'@',inc.string(n)),w.TypedGroup([b'i',b'i'],[-1,-1]),w.TypedValue(b'@',inc.string(''))])

def plan(blob,spec, *, validator=None):
    check_state = state if validator is None else validator
    need(type(spec)is dict and set(spec)=={'actions'},'Exact actions spec required')
    actions=spec['actions'];need(type(actions)is list and 1<=len(actions)<=100,'1..100 actions required')
    root,v,incidents,sets=check_state(blob)
    before_inc={c.text(o.contents[0].value):w.fingerprint(o)for o in incidents}
    before_flags={c.text(o.contents[0].value):o.contents[7].value for o in incidents}
    for act in actions:
        need(type(act)is dict and type(act.get('action'))is str,'Action object required')
        op=act['action']
        schemas={'create_from_enabled':{'action','name'},'update_from_enabled':{'action','names'},'use':{'action','names'},'unuse':{'action','names'},'rename':{'action','name','new_name'},'delete':{'action','names'},'delete_incident':{'action','name'},'set_incident_use':{'action','incident_names','enabled'}}
        need(op in schemas and set(act)==schemas[op],'Unsupported action or fields')
        chosen=[]
        if 'names'in act:
            ns=act['names'];need(type(ns)is list and 1<=len(ns)<=1000,'Nonempty Set names required')
            for n in ns:name(n)
            need(len(set(ns))==len(ns) and all(n in sets for n in ns),'Duplicate/unknown Set selection');chosen=[sets[n]for n in ns]
        if op=='create_from_enabled':
            n=name(act['name']);need(n not in sets and len(sets)<1000,'Set name collision or limit')
            members=[o for o in incidents if o.contents[7].value & 1];need(members,'Save Set requires enabled incidents')
            sets[n]=make_set(root,n,members)
        elif op=='update_from_enabled':
            members=[o for o in incidents if o.contents[7].value & 1]
            for s in chosen:w.set_elements(s.contents[0].value,members)
        elif op in ('use','unuse'):
            if op=='use':
                for o in incidents:o.contents[7].value &= ~1
            for s in chosen:
                for o in c.array(s.contents[0].value):o.contents[7].value=(o.contents[7].value & ~1)|int(op=='use')
        elif op=='rename':
            n=name(act['name']);new=name(act['new_name']);need(n in sets and (new==n or new not in sets),'Unknown Set or collision')
            s=sets.pop(n);s.contents[1].value=inc.string(new);sets[new]=s
        elif op=='delete':
            for n in act['names']:del sets[n]
        elif op=='set_incident_use':
            ns=act['incident_names'];need(type(ns)is list and 1<=len(ns)<=10000,'Incident names required')
            for n in ns:name(n)
            lookup={c.text(o.contents[0].value):o for o in incidents}
            need(len(set(ns))==len(ns) and all(n in lookup for n in ns) and type(act['enabled'])is bool,'Unique known incidents and boolean required')
            for n in ns:lookup[n].contents[7].value=(lookup[n].contents[7].value & ~1)|int(act['enabled'])
        elif op=='delete_incident':
            n=name(act['name']);matches=[o for o in incidents if c.text(o.contents[0].value)==n];need(len(matches)==1,'Exact incident required')
            target=matches[0]
            for s in sets.values():w.set_elements(s.contents[0].value,[o for o in c.array(s.contents[0].value)if o is not target])
            incidents=[o for o in incidents if o is not target]
        w.set_elements(root.contents[1].value,incidents);w.set_elements(root.contents[2].value,[sets[n]for n in sorted(sets)])
    out=w.dump_verified(root,v);fresh,_,afterinc,aftersets=check_state(out)
    source,_=w.load_next_compatible(blob)
    
    check,_=w.load_next_compatible(out)
    for graph in (source,check):
        w.set_elements(graph.contents[1].value,[]);w.set_elements(graph.contents[2].value,[])
    need(w.fingerprint(check)==w.fingerprint(source),'Non-target graph changed')
    for o in afterinc:
        n=c.text(o.contents[0].value);flag=o.contents[7].value
        need((flag & ~1)==(before_flags[n] & ~1),'Incident flags changed beyond Use')
        o.contents[7].value=before_flags[n]
        need(w.fingerprint(o)==before_inc[n],'Incident fields changed beyond Use')
        o.contents[7].value=flag
    return out,{'source_sha256':hashlib.sha256(blob).hexdigest(),'output_sha256':hashlib.sha256(out).hexdigest(),'sets':[{ 'name':n,'members':[c.text(o.contents[0].value)for o in c.array(s.contents[0].value)]}for n,s in aftersets.items()],'enabled_incidents':[c.text(o.contents[0].value)for o in afterinc if o.contents[7].value & 1],'incident_count':len(afterinc),'native_storage_class':'OTIncidentSet/OTOrgArray2','use_semantics':'disable all then enable union of selected sets','unuse_semantics':'disable only selected members','update_semantics':'replace membership with current enabled incidents; UI selection gate not modeled','scope':'current Train Incident12 type1; initialized Set metadata; data only','runtime_validated':False,'sampling_executed':False,'native_execution':False,'saved':False}
