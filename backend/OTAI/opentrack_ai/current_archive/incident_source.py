"""Shared immutable-graph IncidentSet ownership validation; no circular workflow imports."""
from . import writer as w, catalogs as c
from .graph_references import incoming_counts
class IncidentSourceError(ValueError): pass

def need(ok,msg):
    if not ok: raise IncidentSourceError(msg)
def name(x):
    need(type(x)is str and 0<len(x)<=120 and all(32<=ord(y)<127 for y in x) and '#'not in x,'Nonempty printable ASCII name without #, max120 required');return x
def chain(obj,expected):
    q=obj.clazz; got=[]
    while q is not None:got.append((q.name.decode(),q.version));q=q.superclass
    need(got==expected,'Unsupported class/version inheritance')
def mutable(obj):
    chain(obj,[('NSMutableArray',0),('NSArray',0),('NSObject',0)])
    return c.array(obj)
def validate_set_graph(root):
    """Validate ownership and finite Set metadata without mutation or scenario imports."""
    c.course_items(root)
    incidents=mutable(root.contents[1].value);sets=mutable(root.contents[2].value)
    need(len(incidents)<=10000 and len(sets)<=1000,'Source domain size exceeded')
    ids={id(o)for o in incidents};need(len(ids)==len(incidents),'Duplicate incident objects')
    counts=incoming_counts(root);expected={i:1 for i in ids};lookup={}
    need(counts.get(id(root),0)==0,'Root back reference')
    for arr in (root.contents[1].value,root.contents[2].value):need(counts.get(id(arr),0)==1,'Shared owner array')
    for s in sets:
        chain(s,[('OTIncidentSet',0),('OTOrgArray',2),('OTMutableArray',0),('NSObject',0)])
        need(len(s.contents)==4 and all(g.encodings==[bytes([b])for b in e] and len(g.values)==len(e)for g,e in zip(s.contents,[b'@',b'@',b'ii',b'@'])),'Invalid Set field groups')
        need(counts.get(id(s),0)==1,'Shared Set owner')
        n=name(c.text(s.contents[1].value));need(n not in lookup,'Duplicate Set name');lookup[n]=s
        need(s.contents[2].values==[-1,-1],'Only initialized Set ID fields supported')
        need(c.text(s.contents[3].value)=='','Only empty Set description supported')
        a=s.contents[0].value;members=mutable(a);need(counts.get(id(a),0)==1,'Shared member array')
        need(len({id(o)for o in members})==len(members),'Duplicate Set membership')
        for o in members:
            need(id(o)in ids,'Dangling/foreign Incident member');expected[id(o)]+=1
    need({id(o)for o in w.objects(root)if w.kind(o)=='OTIncidentSet'}=={id(o)for o in sets},'Set outside designated owner')
    need({id(o)for o in w.objects(root)if w.kind(o)=='OTIncident'}==ids,'Incident outside owner')
    for o in incidents:need(counts.get(id(o),0)==expected[id(o)],'Unknown Incident sharing')
    return incidents,lookup
