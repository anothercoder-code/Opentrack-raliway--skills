"""Finite explicit Path occurrences in an itinerary, separate from default domain.

Native ordered info arrays preserve repetitions. This module does not alter
Route/Path topology guards or emulate native simulation/repair behavior.
"""
from .multi_document.core import Project, need, ref, sha, f, w
from .multi_document.operations import exact_reference, exclusive
from .multi_document.generate import inf, wrapped
from .zero_generation import native_signal_routes as ns
from .graph_references import incoming

MAX_PATH_REFERENCES = 1000
MAX_EXPANDED_ENDS = 10000

class FiniteItineraryProject(Project):
    def dest_view(self, dest):
        dn = self.owners[id(dest)][0]
        refs = f.info(dest)['saved_references']
        need(1 <= len(refs) <= MAX_PATH_REFERENCES, 'Bounded explicit nonempty Path reference list required')
        persisted = f.mutable_array(dest.contents[0].value)
        need(len(persisted) == 1, 'Itinerary persists only its first Path')
        at = (dn, refs[0]['start_id']); chain = []; paths = []
        for i, r in enumerate(refs):
            need(r['document'] in self.roots and r['document'] == at[0], 'Missing/disconnected exact Path document')
            path = self.owned(at, 'OTPath', (r['name'], r['array_id'], r['start_id']))
            if i == 0:
                need(path is persisted[0], 'Itinerary first Path/info identity mismatch')
            nodes, _ = self.path_view(path)
            need(nodes[0] == at, 'Itinerary Path chain disconnected')
            chain += nodes if i == 0 else nodes[1:]
            need(len(chain) <= MAX_EXPANDED_ENDS, 'Finite itinerary exceeds expanded-End bound')
            paths.append((at[0], ref(path))); at = nodes[-1]
        self.dest_views[id(dest)] = (chain, paths)
        return chain, paths

def create_finite_itinerary(documents,catalog,*,document_paths,expected_hashes,complete_document_set,name,paths):
    need(type(name)is str and name and '\x00'not in name,'Explicit new itinerary name required')
    need(type(paths)is list and 1<=len(paths)<=1000,'Bounded nonempty exact Path sequence required')
    need(expected_hashes=={**{k:sha(v)for k,v in documents.items()},'$dest_catalog':sha(catalog)},'Complete input hash manifest mismatch')
    p=FiniteItineraryProject(documents,document_paths=document_paths,expected_hashes={k:expected_hashes[k]for k in documents},complete_document_set=complete_document_set);p.check_dest_catalog(catalog)
    selected=[];all_nodes=[];at=None
    for value in paths:
        dn,r=exact_reference(value);need(dn in p.roots,'Missing selected Path document')
        key=(dn,r[2]);need(at is None or key==at,'Path sequence not contiguous after native reconstruction')
        obj=p.owned(key,'OTPath',r);nodes,_=p.path_view(obj);selected.append((dn,obj));all_nodes+=nodes if at is None else nodes[1:];at=nodes[-1]
        need(len(all_nodes)<=MAX_EXPANDED_ENDS,'Finite itinerary exceeds expanded-End bound')
    need(len(all_nodes)<=MAX_EXPANDED_ENDS,'Finite itinerary exceeds expanded-End bound')
    need(not any(f.string(o.contents[1].value)==name for o in p.dests),'Project itinerary name already exists')
    dn=all_nodes[0][0];root=p.roots[dn];version=p.versions[dn];wrapper=root.contents[5].value;exclusive(root,wrapper)
    cr,cv=w.load(catalog);need(incoming(cr,cr)==0 and incoming(cr,cr.contents[0].value)==1,'Shared catalog root/backing refused')
    di=ns.arr([inf(o,d)for d,o in selected])
    dest=ns.obj(f.SHAPES['OTDest'][0],[('@',[ns.arr([selected[0][1]])]),('@',[ns.string(name)]),('ii',[-1,-1]),('@',[ns.string('')]),('@',[di]),('@',[wrapped('OTSafetyMarginArray',[])])])
    
    row=ns.obj([('OTDestInfo',1),('NSObject',0)],[('i',[17]),('@',[ns.string(name)]),('@',[ns.string(document_paths[dn])]),('i',[all_nodes[0][1]]),('@',[ns.arr([inf(o,d)for d,o in selected])])])
    target=wrapper.contents[0].value;old=f.mutable_array(target);oldgroups=list(target.contents);cback=cr.contents[0].value;cold=f.mutable_array(cback);coldgroups=list(cback.contents);baseline=w.dump_verified(root,version);cbaseline=w.dump_verified(cr,cv)
    w.set_elements(target,old+[dest]);w.set_elements(cback,cold+[row])
    output=dict(documents);output[dn]=w.dump_verified(root,version);outcat=w.dump_verified(cr,cv)
    checked=FiniteItineraryProject(output,document_paths=document_paths,expected_hashes={k:sha(v)for k,v in output.items()},complete_document_set=True);checked.check_dest_catalog(outcat)
    saved=next(o for o in checked.dests if f.string(o.contents[1].value)==name);need(checked.dest_view(saved)[0]==all_nodes,'Fresh cross-document itinerary differs')
    target.contents=oldgroups;cback.contents=coldgroups
    need(w.dump_verified(root,version)==baseline and w.dump_verified(cr,cv)==cbaseline,'Unexpected mutation outside new itinerary/catalog membership')
    return {'documents':output,'catalog':outcat},dict(operation='create_finite_explicit_itinerary',name=name,owner_document=dn,ordered_paths=paths,runtime_end_keys=all_nodes,persisted_path_objects=1,full_external_path_infos=len(paths),changed_dependencies=[dn,'$dest_catalog'],all_other_document_bytes_unchanged=True,original_graph_rollback_verified=True,input_sha256=expected_hashes,output_sha256={**{k:sha(v)for k,v in output.items()},'$dest_catalog':sha(outcat)},atomic_group_commit_required=True,native_simulation_executed=False,finite_reference_count=len(paths),repeated_end_occurrences=len(all_nodes)-len(set(all_nodes)),closed_walk=all_nodes[0]==all_nodes[-1],scope='Explicit finite Path occurrences only; Route and Path simple-chain restrictions remain unchanged; no infinite repeat or runtime acceptance claim')
