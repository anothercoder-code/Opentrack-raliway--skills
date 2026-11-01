"""Strict current saved-data cross-document reconstruction. Pure bytes, no runtime.

Only exact identity references are accepted: native fallback-name repairs are
reported as outside this mutation domain, never silently emulated. No foreign
object is inserted into another archive; runtime expansion is a separate view.
"""
from __future__ import annotations
import hashlib,re
from pathlib import PurePosixPath
from opentrack_ai.current_archive import writer as w, path_functions as f, route_factory as rf
from opentrack_ai.current_archive.zero_generation import topology as tp
from opentrack_ai.current_archive.zero_operations import run_bundle as rb

class CrossDocumentError(ValueError): pass

def need(ok,msg):
    if not ok: raise CrossDocumentError(msg)
def sha(b): return hashlib.sha256(b).hexdigest()
def ident(o): return (f.string(o.contents[1].value),*o.contents[2].values)
def ref(o):
    name,aid,start=ident(o);return dict(name=name,array_id=aid,start_id=start)
def info_ref(o): return (f.string(o.contents[0].value),*o.contents[1].values)
def layout(o,chain,enc):
    f.hierarchy(o,chain)
    need([''.join(e.decode() for e in g.encodings) for g in o.contents]==enc and all(len(g.encodings)==len(g.values) for g in o.contents),'Unsupported exact saved layout')
def stem(path):
    
    
    need(type(path)is str and path.endswith('.opentrack'),'Explicit .opentrack filename required')
    try:
        if re.match(r'^[A-Za-z]:/',path):
            need(rb.root_path(path,'windows')==path,'Canonical Windows filename required')
        else:
            rb.relative(path)
    except ValueError as exc:
        raise CrossDocumentError('Invalid document filename: '+str(exc))from exc
    value=PurePosixPath(path).name[:-10]
    need(value,'Invalid document basename')
    return value

class Project:
    """Caller explicitly supplies and hashes the complete infrastructure set.
    document_paths are exact authoritative paths; basename is native docWithName
    namespace. Hashes prevent accidental partial/mixed project input, not proof
    that an unprovided external filesystem has no further files.
    """
    def __init__(self, documents, *, document_paths, expected_hashes, complete_document_set):
        need(complete_document_set is True,'Complete project document inventory must be explicitly attested')
        need(type(documents)is dict and documents and set(documents)==set(document_paths),'Exact complete document/path mapping required')
        need(all(type(k)is str and k and type(v)is bytes for k,v in documents.items()),'Immutable bytes and explicit document keys required')
        need({k:sha(v) for k,v in documents.items()}==expected_hashes,'Document dependency hash mismatch')
        need(all(stem(document_paths[k])==k for k in documents),'Key must equal authoritative native filename basename')
        need(len({k.casefold()for k in documents})==len(documents),'Ambiguous case-insensitive document basename')
        need(len({v.casefold()for v in document_paths.values()})==len(documents),'Ambiguous document path')
        self.blobs=dict(documents);self.paths=dict(document_paths);self.roots={};self.versions={};self.models={};self.byid={};self.where={};self.owners={};self.routes=[];self.paths_objects=[];self.dests=[]
        self.expanded={};self.path_views={};self.dest_views={};self.continuations=[]
        for dn,blob in documents.items():
            root,v=w.load(blob);tp.doc_layout(root)
            self.roots[dn]=root;self.versions[dn]=v
            models=f.mutable_array(root.contents[2].value);self.models[dn]=models;byid={}
            for m in models:
                need(m.contents and m.contents[0].encodings==[b'i'] and type(m.contents[0].value)is int,'Model identity malformed')
                mid=m.contents[0].value;need(0<=mid<=2147483647 and mid not in byid,'Duplicate/invalid local model ID');byid[mid]=m;self.where[id(m)]=(dn,mid)
            self.byid[dn]=byid
        self._topology()
        self._rsp()
        self._assemble()

    def key(self,end):
        need(id(end)in self.where,'End outside selected model collections');return self.where[id(end)]
    def model(self,key):
        dn,mid=key;need(dn in self.byid and mid in self.byid[dn],'Missing document/local model');return self.byid[dn][mid]
    def ends(self,dn):return [m for m in self.models[dn] if w.kind(m)in ('OTEndModel','OTConnModel')]
    def related(self,key):
        e=self.model(key);return (key[0],e.contents[8].value)
    def block_end(self,key):
        e=self.model(key);need(w.kind(e)=='OTConnModel','Connector expected')
        target=(f.string(e.contents[25].value),e.contents[26].value)
        need(target[0]in self.byid,'Missing connector document: '+target[0]);other=self.model(target)
        need(w.kind(other)=='OTConnModel','Connector target ID is not a connector')
        return target
    def actual_related(self,key):
        local=self.related(key)
        return self.related(self.block_end(local)) if w.kind(self.model(local))=='OTConnModel' else local
    def edge_between(self,a,b):
        actual=self.actual_related(a);need(actual[0]==b[0],'actualRelated does not reach next document')
        half=self.model(actual);target=self.model(b);choices=[]
        for i in (9,10):
            edge=half.contents[i].value
            if edge is not None and target in (edge.contents[7].value,edge.contents[8].value) and edge not in choices:choices.append(edge)
        need(len(choices)==1,'Disconnected/ambiguous directed movement '+str((a,b)))
        return self.key(choices[0])
    def _topology(self):
        for dn in self.roots:
            for e in self.ends(dn):
                conn=w.kind(e)=='OTConnModel'
                layout(e,([('OTConnModel',1)] if conn else [])+[('OTEndModel',7),('OTGraphicModel',1),('NSObject',0)],rf.END+(['@','@','i','i'] if conn else []))
                k=self.key(e);other=self.model(self.related(k))
                need(other is not e and w.kind(other)in ('OTEndModel','OTConnModel') and other.contents[8].value==k[1],'Nonreciprocal local related End')
                for i in (9,10):
                    edge=e.contents[i].value
                    need(edge is None or (edge in self.models[dn] and w.kind(edge)=='OTEdgeModel' and e in [edge.contents[j].value for j in (7,8)]),'End/Edge membership mismatch')
                signal=e.contents[11].value
                need(signal is None or (signal in self.models[dn] and w.kind(signal)=='OTSignalModel'and signal.contents[7].value is e),'End/Signal reverse closure mismatch')
                first,second=e.contents[9].value,e.contents[10].value
                need(first is not None or second is None,'Second Edge without first is noncanonical')
                need(first is None or first is not second,'Duplicate incident Edge in both slots')
                elem=e.contents[7].value
                need(elem in self.models[dn] and w.kind(elem)=='OTElement' and f.mutable_array(elem.contents[7].value).count(e)==1,'Safety Element membership mismatch')
                if conn:
                    need(e.contents[27].value==0,'Internal connector outside bounded external-document profile')
                    target=self.block_end(k);need(target[0]!=dn,'Internal connector outside profile')
                    o=self.model(target)
                    need((f.string(o.contents[25].value),o.contents[26].value)==k,'Unpaired/nonreciprocal connector')
                    f.string(e.contents[24].value) 
                    need(all(e.contents[i].value is None for i in (9,10,11,12)) and e.contents[20].value==1 and w.kind(other)=='OTEndModel' and other.contents[11].value is None,'Connector and related End must be nonsignal; connector must be free/nonstation')
            for elem in (m for m in self.models[dn] if w.kind(m)=='OTElement'):
                rf.layout(elem,'OTElement',0,['i','f','f','f','i','i','@','@'],graphic=True)
                members=f.mutable_array(elem.contents[7].value)
                need(len({id(e)for e in members})==len(members),'Duplicate Safety Element member')
                need(all(e in self.ends(dn) and e.contents[7].value is elem for e in members),'Safety Element reverse closure mismatch')
            for signal in (m for m in self.models[dn] if w.kind(m)=='OTSignalModel'):
                rf.layout(signal,'OTSignalModel',11,rf.SIGNAL,graphic=True)
                owner=signal.contents[7].value
                need(owner in self.ends(dn) and owner.contents[11].value is signal,'Signal/End reverse closure mismatch')
                for ind in rf.wrapper(signal.contents[10].value,'OTSigIndList'):
                    rf.layout(ind,'OTSigInd',0,['i','@']);need(ind.contents[1].value in self.ends(dn),'Signal indication reference must remain a local End; not assumed equal to signal owner')
            for edge in (m for m in self.models[dn] if w.kind(m)=='OTEdgeModel'):
                rf.layout(edge,'OTEdgeModel',3,rf.EDGE,graphic=True)
                need(type(edge.contents[9].values[1])is int and edge.contents[9].values[1]>0,'Positive persisted Edge length required')
                a,b=[edge.contents[i].value for i in (7,8)]
                need(a is not b and all(e in self.ends(dn) and edge in [e.contents[i].value for i in (9,10)] for e in (a,b)),'Edge reverse closure mismatch')
                need(a.contents[7].value is b.contents[7].value,'Edge safety union mismatch')
    def _rsp(self):
        for dn in self.roots:
            for end in self.ends(dn):
                high=end.contents[19].value
                need(type(high)is int and -1<=high<=2147483647,'Invalid highestGivenRspID')
                ordinary=w.kind(end)=='OTEndModel';allocated=[]
                need(not rf.wrapper(end.contents[16].value,'OTShuntingList'),'Nonempty ShuntingList outside audited domain')
                for slot,kind in ((15,'OTRoute'),(17,'OTPath')):
                    items=rf.wrapper(end.contents[slot].value,'OTRouteList' if slot==15 else 'OTPathList');seen=set();names=set()
                    for item in items:
                        f.shape(item,kind);key=ident(item)
                        need(key[0]and all(type(x)is int and 0<=x<=2147483647 for x in key[1:]),'Invalid RSP name/identity')
                        if ordinary:
                            need(key[2]==end.contents[0].value and key[1]<=high,'Ordinary owner RSP identity exceeds highwater or has wrong local owner')
                            allocated.append(key[1])
                        need(id(item)not in self.owners,'Shared/multiple RSP owner')
                        need(key[1:] not in seen and key[0]not in names,'Ambiguous owner RSP ID/name');seen.add(key[1:]);names.add(key[0])
                        self.owners[id(item)]=self.key(end)
                        (self.routes if slot==15 else self.paths_objects).append(item)
                need(len(set(allocated))==len(allocated),'Duplicate R/S/P identity across ordinary owner lists')
            for dest in f.mutable_array(self.roots[dn].contents[5].value.contents[0].value):
                f.shape(dest,'OTDest');self.owners[id(dest)]=(dn,None);self.dests.append(dest)
        for dn,root in self.roots.items():
            for o in w.objects(root):
                if w.kind(o)in ('OTRoute','OTPath','OTDest'):need(id(o)in self.owners,'Orphan/hidden RSP object')
    def owned(self,key,kind,reference):
        end=self.model(key);slot=15 if kind=='OTRoute' else 17
        items=rf.wrapper(end.contents[slot].value,'OTRouteList' if slot==15 else 'OTPathList')
        exact=[o for o in items if ident(o)==reference]
        need(len(exact)==1,'Unresolved exact '+kind+' reference at '+str(key)+': '+str(reference))
        
        need(sum(ident(o)[1:]==reference[1:] for o in items)==1 and sum(ident(o)[0]==reference[0]for o in items)==1,'Ambiguous native lookup')
        return exact[0]
    def route_view(self,route):
        if id(route)in self.expanded:return self.expanded[id(route)]
        need(f.string(route.contents[7].value)=='' and route.contents[9].value==-1,'Overlap route name/start reference outside audited domain')
        owner=self.owners[id(route)];dn=owner[0];nodes=f.mutable_array(route.contents[0].value)
        need(nodes and all(self.key(e)[0]==dn and w.kind(e)=='OTEndModel'for e in nodes),'Route saved nodes must be ordinary local Ends')
        keys=[self.key(e)for e in nodes];is_fragment=w.kind(self.model(owner))=='OTConnModel';idx=route.contents[5].values[4]
        need(type(idx)is int and idx>=-1,'Invalid continuation index')
        if is_fragment:need(idx==-1,'Nested continuation fragment unsupported')
        else:need(keys[0]==owner and ident(route)[2]==owner[1],'Route owner/start mismatch')
        if idx!=-1:
            need(not is_fragment and idx==len(nodes),'Continuation save count/index mismatch')
            conn=self.related(keys[-1]);need(w.kind(self.model(conn))=='OTConnModel','Continuation lastEnd.related is not connector')
            remote=self.block_end(conn);fragment=self.owned(remote,'OTRoute',ident(route))
            tail=self.route_view(fragment);need(all(k[0]==remote[0]for k in tail),'Continuation spans additional document')
            self.continuations.append(dict(source_document=dn,route=ref(route),local_end_ids=[k[1]for k in keys],source_connector=conn[1],target_document=remote[0],target_connector=remote[1],saved_continuation_index=idx,remote_end_ids=[k[1]for k in tail],fragment_object=id(fragment)))
            keys+=tail
        for group in f.mutable_array(route.contents[12].values[0]):
            need(group in nodes,'Route release group outside its saved local nodes')
        need(len({id(x)for x in f.mutable_array(route.contents[12].values[0])})==len(f.mutable_array(route.contents[12].values[0])),'Duplicate Route release group')
        for zone in route.contents[12].values[1:]:need(zone is None or zone in nodes,'Route zone outside saved local nodes')
        for indication in rf.wrapper(route.contents[4].value,'OTSigIndList'):
            rf.layout(indication,'OTSigInd',0,['i','@']);need(indication.contents[1].value is route,'Route indication owner mismatch')
        if not is_fragment:
            need(len(keys)>=2,'Source Route must have at least two expanded Ends')
            for terminal in (keys[0],keys[-1]):
                sig=self.model(terminal).contents[11].value
                need(sig in self.models[terminal[0]] and w.kind(sig)=='OTSignalModel' and sig.contents[7].value is self.model(terminal),'Source Route terminal signal missing/mismatched')
                need(sig.contents[8].values[0]in {1,2,24,25,26},'Source Route terminals must be native main signals, not shunting/distant signals')
            for key in keys[1:-1]:
                sig=self.model(key).contents[11].value
                need(sig is None or sig.contents[8].values[0]not in {1,2,24,25,26},'Intermediate main signal requires a separate Route')
        for a,b in zip(keys,keys[1:]):self.edge_between(a,b)
        need(len(set(keys))==len(keys),'Cyclic/revisited Route outside domain')
        self.expanded[id(route)]=keys;return keys
    def path_view(self,path):
        if id(path)in self.path_views:return self.path_views[id(path)]
        owner=self.owners[id(path)];need(w.kind(self.model(owner))=='OTEndModel'and ident(path)[2]==owner[1],'Path owner mismatch')
        refs=f.info(path)['saved_references'];need(refs,'Empty Path outside profile')
        persisted=f.mutable_array(path.contents[0].value);need(len(persisted)==1,'Path must persist only its first Route')
        at=owner;chain=[];route_refs=[]
        for i,r in enumerate(refs):
            route=self.owned(at,'OTRoute',(r['name'],r['array_id'],r['start_id']))
            if i==0:need(route is persisted[0],'Path first Route/info mismatch')
            nodes=self.route_view(route);need(nodes[0]==at,'Path Route chain disconnected')
            chain+=nodes if i==0 else nodes[1:];route_refs.append((at[0],ref(route)));at=nodes[-1]
        need(len(set(chain))==len(chain),'Cyclic/revisited Path outside domain')
        self.path_views[id(path)]=(chain,route_refs);return self.path_views[id(path)]
    def dest_view(self,dest):
        dn=self.owners[id(dest)][0];refs=f.info(dest)['saved_references'];need(refs,'Empty itinerary outside profile')
        persisted=f.mutable_array(dest.contents[0].value);need(len(persisted)==1,'Itinerary must persist only its first Path')
        at=(dn,refs[0]['start_id']);chain=[];paths=[]
        for i,r in enumerate(refs):
            need(r['document']in self.roots,'Missing ExtInfo document')
            need(r['document']==at[0],'ExtInfo document disagrees with reconstructed previous Path lastEnd')
            path=self.owned(at,'OTPath',(r['name'],r['array_id'],r['start_id']))
            if i==0:need(path is persisted[0],'Itinerary first Path/info mismatch')
            nodes,_=self.path_view(path);need(nodes[0]==at,'Itinerary Path chain disconnected')
            chain+=nodes if i==0 else nodes[1:];paths.append((at[0],ref(path)));at=nodes[-1]
        need(len(set(chain))==len(chain),'Cyclic/revisited itinerary outside domain')
        self.dest_views[id(dest)]=(chain,paths);return chain,paths
    def _assemble(self):
        for r in self.routes:self.route_view(r)
        fragments=[r for r in self.routes if w.kind(self.model(self.owners[id(r)]))=='OTConnModel']
        for r in fragments:need(sum(c['fragment_object']==id(r)for c in self.continuations)==1,'Orphan/shared continuation fragment')
        for p in self.paths_objects:self.path_view(p)
        for d in self.dests:self.dest_view(d)
    def check_dest_catalog(self,blob):
        root,_=w.load(blob);rows=rf.wrapper(root,'OTDestInfoList');defs={}
        for d in self.dests:
            name=f.string(d.contents[1].value);need(name not in defs,'Ambiguous project itinerary name');defs[name]=d
        seen=set()
        for row in rows:
            layout(row,[('OTDestInfo',1),('NSObject',0)],['i','@','@','i','@'])
            name=f.string(row.contents[1].value);need(name in defs and name not in seen,'Missing/duplicate DestInfo definition');seen.add(name)
            dest=defs[name];dn=self.owners[id(dest)][0];need(row.contents[0].value==17 and f.string(row.contents[2].value).replace('\\','/')==self.paths[dn],'DestInfo authoritative file path mismatch')
            refs=f.info(dest)['saved_references'];actual=[]
            for x in f.mutable_array(row.contents[4].value):
                layout(x,[('OTArrayExtInfo',0),('OTArrayInfo',0),('NSObject',0)],['@','ii','@']);n,aid,sid=info_ref(x);actual.append(dict(name=n,array_id=aid,start_id=sid,document=f.string(x.contents[2].value)))
            need(actual==refs and row.contents[3].value==refs[0]['start_id'],'DestInfo Path ExtInfo mismatch')
        need(seen==set(defs),'Incomplete global DestInfo catalog')
        return len(rows)
    def report(self):
        connectors=[]
        for dn in self.roots:
            for e in self.ends(dn):
                if w.kind(e)=='OTConnModel':
                    k=self.key(e);connectors.append(dict(document=dn,id=k[1],related=self.related(k),block_end=self.block_end(k),actual_related_from_local_half=self.actual_related(self.related(k)),drag_filename=f.string(e.contents[24].value)))
        return dict(documents={dn:dict(path=self.paths[dn],sha256=sha(self.blobs[dn]),models=len(self.models[dn])) for dn in self.roots},connectors=connectors,continuations=[{k:v for k,v in c.items()if k!='fragment_object'}for c in self.continuations],paths=[dict(document=self.owners[id(p)][0],**ref(p),runtime_end_keys=self.path_views[id(p)][0],routes=self.path_views[id(p)][1],persisted_route_objects=1)for p in self.paths_objects],itineraries=[dict(document=self.owners[id(d)][0],name=f.string(d.contents[1].value),runtime_end_keys=self.dest_views[id(d)][0],paths=self.dest_views[id(d)][1],persisted_path_objects=1)for d in self.dests],native_runtime_executed=False,scope='strict current exact-reference saved-data reconstruction, not GUI/simulation/runtime cache equivalence')

def inspect(documents,**kwargs): return Project(documents,**kwargs).report()
