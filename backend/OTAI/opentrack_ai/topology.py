"""Independent directional graph and route-chain search over native records.

No three-station names or drawing coordinates participate in connectivity.
The double-vertex/connector rule follows the audited archive builder and the
manual's main-signal Route boundaries. Native dispatch is not executed.
"""
import collections
import heapq
import itertools

from .archive import APIError,page,w,END_KINDS
from .network_records import route_properties,shunting_paths

MAIN_SIGNAL_TYPES={1,2,24,25,26}


def key(reference):return (reference.document,reference.end_id)


class Topology:
    def __init__(self,project):
        self.project=project;self.ends={};self.edges={};self.kinds={};self.problems=[]
        for document,items in project.models.items():
            for obj in items:
                ident=obj.contents[0].value;kind=w.kind(obj);self.kinds[(document,ident)]=kind
                if kind in END_KINDS:self.ends[(document,ident)]=obj
                elif kind=='OTEdgeModel':self.edges[(document,ident)]=obj
        self._adjacency={}
        for node in self.ends:
            try:self._adjacency[node]=self._steps(node)
            except (AssertionError,IndexError,KeyError,ValueError,APIError) as error:
                self.problems.append({'node':list(node),'reason':str(error)});self._adjacency[node]=[]

    def require(self,node):
        if node not in self.ends:
            actual=self.kinds.get(node)
            raise APIError('END_NOT_FOUND','Use a document and directional End/Connector ID, not a Signal graphic ID.',{'node':list(node),'actual_class':actual})
        return self.ends[node]

    def signal(self,node):
        end=self.require(node);signal=end.contents[11].value
        if signal is not None and w.kind(signal)!='OTSignalModel':raise APIError('SIGNAL_REFERENCE','End does not reference a Signal model.',list(node))
        return {'id':signal.contents[0].value,'type':signal.contents[8].values[0],
            'main':signal.contents[8].values[0] in MAIN_SIGNAL_TYPES} if signal else None

    def is_main(self,node):
        signal=self.signal(node);return bool(signal and signal['main'])

    def _steps(self,node):
        owner,ident=node;end=self.ends[node];other=(owner,end.contents[8].value)
        pair=self.require(other)
        if pair.contents[8].value!=ident:raise APIError('HALF_VERTEX_PAIR','Related End pair is not reciprocal.')
        for endpoint in [end,pair]:
            element=endpoint.contents[7].value
            if element is None or w.kind(element)!='OTElement':raise APIError('ELEMENT_REFERENCE','End has no valid safety Element.')
        boundary=None
        if w.kind(pair)=='OTConnModel':
            if pair.contents[25].value is None:raise APIError('CONNECTOR_PAIR','Connector has no remote document name.')
            remote=(w.string(pair.contents[25].value),pair.contents[26].value);connector=self.require(remote)
            if w.kind(connector)!='OTConnModel' or connector.contents[25].value is None or w.string(connector.contents[25].value)!=owner or connector.contents[26].value!=other[1]:
                raise APIError('CONNECTOR_PAIR','Cross-document connector is not reciprocal.')
            boundary=[list(other),list(remote)];owner=remote[0]
            pair=self.require((owner,connector.contents[8].value))
        result=[];seen=set()
        for index in [9,10]:
            edge=pair.contents[index].value
            if edge is None:continue
            if w.kind(edge)!='OTEdgeModel':raise APIError('EDGE_REFERENCE','End incident reference is not an Edge.')
            edge_key=(owner,edge.contents[0].value)
            if edge_key in seen:continue
            seen.add(edge_key)
            if self.edges.get(edge_key) is not edge:raise APIError('EDGE_REFERENCE','End references an Edge outside its document graphic array.')
            first,second=(edge.contents[i].value for i in [7,8])
            if first is None or second is None:raise APIError('EDGE_REFERENCE','An Edge endpoint is missing.')
            if first is pair:destination=second
            elif second is pair:destination=first
            else:raise APIError('EDGE_REFERENCE','Edge does not reference the traversed End.')
            target=(owner,destination.contents[0].value)
            if self.ends.get(target) is not destination:raise APIError('EDGE_REFERENCE','Edge target is outside its document End array.')
            length=edge.contents[9].values[1]
            if not isinstance(length,int) or length<=0:raise APIError('EDGE_LENGTH','Expected positive integer metres.')
            resources={(owner,'edge',edge_key[1])}
            for endpoint in [first,second]:
                element=endpoint.contents[7].value
                if element is None or w.kind(element)!='OTElement':raise APIError('ELEMENT_REFERENCE','Edge endpoint has no valid safety Element.')
                resources.add((owner,'element',element.contents[0].value))
            linked=edge.contents[13].value if len(edge.contents)>13 else None;visited={id(edge)}
            while linked is not None and id(linked) not in visited:
                visited.add(id(linked));linked_key=(owner,linked.contents[0].value)
                if self.edges.get(linked_key) is not linked:raise APIError('EXCLUSION_REFERENCE','Linked Edge is outside the document graphic array.')
                resources.add((owner,'edge',linked_key[1]))
                for endpoint in [linked.contents[7].value,linked.contents[8].value]:
                    if endpoint is None or endpoint.contents[7].value is None:raise APIError('EXCLUSION_REFERENCE','Linked Edge has a missing End or safety Element.')
                    resources.add((owner,'element',endpoint.contents[7].value.contents[0].value))
                linked=linked.contents[13].value
            result.append({'target':target,'edge':edge_key,'length_m':length,'boundary':boundary,'resources':sorted(resources),
                'switch_choice':{'vertex':(owner,pair.contents[0].value),'leg':index-9} if pair.contents[9].value is not None and pair.contents[10].value is not None else None})
        return sorted(result,key=lambda row:(row['length_m'],row['target'],row['edge']))

    def record(self,node):
        end=self.require(node);station=end.contents[12].value
        return {'document':node[0],'end_id':node[1],'class':w.kind(end),'related_id':end.contents[8].value,
            'signal':self.signal(node),'station_sign':w.string(station.contents[7].value) if station else None,
            'outgoing':[dict(step,target=list(step['target']),edge=list(step['edge'])) for step in self._adjacency[node]]}

    def inspect(self,args):
        rows=[self.record(node) for node in sorted(self.ends) if (not args.document or node[0]==args.document) and (args.end_id is None or node[1]==args.end_id)]
        return {'valid':not self.problems,'problems':self.problems[:100],'documents':len(self.project.docs),'directional_ends':len(self.ends),
            'edges':len(self.edges),'main_signals':sum(self.is_main(node) for node in self.ends),**page(rows,args.limit,args.offset),
            'connectivity_basis':'Related half-vertices, reciprocal connectors and native edge references; never drawing proximity.'}

    def describe_walk(self,nodes):
        if len(nodes)<2:raise APIError('WALK_TOO_SHORT','A movement requires at least two directional Ends.')
        records=[]
        for first,second in zip(nodes,nodes[1:]):
            matches=[step for step in self._adjacency[self.require_key(first)] if step['target']==second]
            if len(matches)!=1:raise APIError('WALK_NOT_CONNECTED','Expected exactly one directed transition.',{'from':first,'to':second,'matches':len(matches)})
            records.append(matches[0])
        return self._candidate(nodes,records)

    def require_key(self,node):self.require(node);return node

    def _candidate(self,nodes,steps):
        return {'nodes':[list(n) for n in nodes],'distance_m':sum(s['length_m'] for s in steps),
            'edges':[{'document':s['edge'][0],'edge_id':s['edge'][1],'length_m':s['length_m']} for s in steps],
            'boundaries':[s['boundary'] for s in steps if s['boundary']],
            'resources':sorted({tuple(resource) for step in steps for resource in step['resources']}),
            'switch_choices':[s['switch_choice'] for s in steps if s['switch_choice']]}

    def route_records(self):
        records=[];identities=set()
        for node,end in sorted(self.ends.items()):
            for route in w.elements(end.contents[15].value.contents[0].value):
                local=w.elements(route.contents[0].value)
                
                
                if not local or local[0] is not end:continue
                identity=(node[0],node[1],route.contents[2].values[0])
                if identity in identities:raise APIError('DUPLICATE_ROUTE_ID','Native Route ID is duplicated at its owner.',identity)
                identities.add(identity);nodes=[(node[0],obj.contents[0].value) for obj in local];companion=None
                if route.contents[5].values[4]>=0:
                    last=self.ends[nodes[-1]];connector=self.ends[(node[0],last.contents[8].value)]
                    remote=(w.string(connector.contents[25].value),connector.contents[26].value)
                    options=[r for r in w.elements(self.ends[remote].contents[15].value.contents[0].value) if r.contents[2].values==route.contents[2].values and w.string(r.contents[1].value)==w.string(route.contents[1].value)]
                    if len(options)!=1:raise APIError('ROUTE_CONTINUATION','Expected one matching remote Route continuation.',identity)
                    companion=options[0]
                    if companion.contents[5].values[4]>=0:raise APIError('ROUTE_CONTINUATION_CHAIN','Recursive continuation decoding remains unverified.')
                    nodes.extend((remote[0],obj.contents[0].value) for obj in w.elements(companion.contents[0].value))
                walk=self.describe_walk(nodes)
                records.append({'document':node[0],'start_id':node[1],'route_id':identity[2],'name':w.string(route.contents[1].value),
                    'start':list(node),'end':list(nodes[-1]),**walk,'properties':route_properties(route),
                    'terminal_properties':route_properties(companion) if companion else route_properties(route),'_object':route,'_companion':companion})
        return records

    def shunting_records(self):
        result=[]
        for row in shunting_paths(self.project):
            nodes=[tuple(node) for node in row['nodes']];walk=self.describe_walk(nodes)
            if walk['boundaries']:raise APIError('SHUNTING_DOCUMENT_BOUNDARY','A stored Shunting unexpectedly crosses a document boundary.')
            result.append({**row,**walk,'start':list(nodes[0]),'end':list(nodes[-1])})
        return result

    def search(self,args):
        start=key(args.start);target=key(args.end) if args.end else None;self.require(start)
        if target:self.require(target)
        if self.problems:raise APIError('TOPOLOGY_INVALID','Repair graph references before searching.',self.problems[:100])
        if args.kind!='topology' and not self.is_main(start):raise APIError('NOT_MAIN_SIGNAL','Ordinary Routes/Paths must start at a main-signal End.',self.record(start))
        if args.kind!='topology' and target and not self.is_main(target):raise APIError('NOT_MAIN_SIGNAL','Ordinary Routes/Paths must end at a main-signal End.',self.record(target))
        if args.kind=='paths' and target is None:raise APIError('TARGET_REQUIRED','Path-chain search requires an end.')
        forbidden={key(n) for n in args.avoid_nodes};blocked={(e.document,e.edge_id) for e in args.avoid_edges};via=[key(n) for n in args.via]
        for n in [*forbidden,*via]:self.require(n)
        if start in forbidden or target in forbidden:raise APIError('ENDPOINT_FORBIDDEN','A search endpoint is also excluded.')
        if args.kind=='paths':
            route_map=collections.defaultdict(list)
            for route in self.route_records():route_map[tuple(route['start'])].append(route)
        counter=itertools.count();queue=[(0,next(counter),start,[start],[],[],0)];solutions=[];expanded=0;hop_cutoff=False
        while queue and len(solutions)<args.limit and expanded<args.max_expansions:
            distance,_,node,nodes,steps,chain,progress=heapq.heappop(queue);expanded+=1
            if progress<len(via) and node==via[progress]:progress+=1
            at_boundary=len(nodes)>1 and args.kind=='routes' and self.is_main(node)
            finished=(node==target if target is not None else at_boundary)
            if finished and progress==len(via) and (args.kind=='topology' or len(nodes)>1):
                result=self._candidate(nodes,steps)
                if chain:result['routes']=[{k:r[k] for k in ['document','start_id','route_id','name']} for r in chain]
                result['native_route_persistence_supported']=len(result['boundaries'])<=1 if args.kind=='routes' else None
                solutions.append(result);continue
            if at_boundary:continue
            if len(nodes)-1>=args.max_hops:
                if self._adjacency[node]:hop_cutoff=True
                continue
            if args.kind=='paths':
                options=[]
                for route in route_map.get(node,[]):
                    extra=[tuple(n) for n in route['nodes'][1:]]
                    if any(n in nodes or n in forbidden for n in extra):continue
                    added=[];cursor=node
                    for dest in extra:
                        match=[s for s in self._adjacency[cursor] if s['target']==dest]
                        if len(match)!=1:raise APIError('ROUTE_TOPOLOGY','Defined Route does not follow native edge references.')
                        added.append(match[0]);cursor=dest
                    if any(s['edge'] in blocked for s in added):continue
                    options.append((extra,added,chain+[route]))
            else:
                options=[([s['target']],[s],chain) for s in self._adjacency[node] if s['target'] not in nodes and s['target'] not in forbidden and s['edge'] not in blocked]
            for extra,added,next_chain in options:
                if len(nodes)+len(extra)-1>args.max_hops:hop_cutoff=True;continue
                next_progress=progress
                for n in extra[:-1]:
                    if next_progress<len(via) and n==via[next_progress]:next_progress+=1
                heapq.heappush(queue,(distance+sum(s['length_m'] for s in added),next(counter),extra[-1],nodes+extra,steps+added,next_chain,next_progress))
        return {'kind':args.kind,'solutions':solutions,'count':len(solutions),'expanded_states':expanded,
            'exhausted':not queue and not hop_cutoff,'truncated':bool(queue) or hop_cutoff,'hop_cutoff':hop_cutoff,'limits':{'solutions':args.limit,'expansions':args.max_expansions,'hops':args.max_hops},
            'source_digest':self.project.source_digest,'native_simulation_verified':False,
            'implementation':'Independent simple directional walk / existing-Route chain search; no native selector execution.'}
