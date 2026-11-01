"""Nine junction stations using only the native persistent-data components."""
import copy
import hashlib
import sys
from pathlib import Path

from opentrack_ai.current_archive import writer as w, path_functions as pf, route_factory as rf, catalogs as cats
from opentrack_ai.current_archive.zero_generation import topology as tp, native_signal_routes as ns
from opentrack_ai.current_archive.zero_operations import station_binding as sb
from opentrack_ai.current_archive.multi_document import core as cd, generate as g
from yard_profile import graphics, text as labels

PORTS = ('W', 'N', 'E', 'S')
VECTOR = {'W': (-1, 0), 'N': (0, 1), 'E': (1, 0), 'S': (0, -1)}
SIDE = {'W': 0, 'N': 1, 'E': 1, 'S': 0}
OPPOSITE = {'W': 'E', 'E': 'W', 'N': 'S', 'S': 'N'}
STATIONS = tuple(f'J{r}{c}' for r in range(1, 4) for c in range(1, 4))


def sha(b): return hashlib.sha256(b).hexdigest()


def point(port, radius, offset):
    x, y = VECTOR[port]
    return (800 + x * radius - y * offset, 800 + y * radius + x * offset)


def name(port, role): return port + '_' + role


def specification():
    vertices, edges, values, paths = [], [], {}, {}
    def vertex(p, role, radius, offset, outgoing=False):
        key = name(p, role)
        x, y = point(p, radius, offset)
        side = 1 - SIDE[p] if outgoing else SIDE[p]
        values[key] = {'x': x, 'y': y, 'side': side, 'port': p, 'role': role}
        vertices.append(dict(key=key, x=x, y=y,
            orientation='horizontal' if p in 'WE' else 'vertical', names=[key+'_A', key+'_B'],
            insulated_joint=[False, False], axle_counter=[False, False]))
    def edge(a, b, length, track, core=False, curve=False):
        edges.append(dict(key=a+'__'+b, **{'from': [a, 1-values[a]['side']], 'to': [b, values[b]['side']]},
            length_m=length, radius_m=100. if curve else 0., gradient_per_mille=0.,
            track_type=1, loop_type=1, dlink_type=1, equal_speed=True, rack_rail=False,
            speeds=[dict(train_type='0', speed12_kmh=40 if curve else 80, speed21_kmh=40 if curve else 80)],
            remark='Shared junction core' if core else 'Grid junction station', track_name=track,
            line_name='Grid3x3 Teaching Network'))
    for p in PORTS:
        for role, r in [('IN',760),('B3',650),('HOME',535),('FORK',480),('MERGE',220),('I_A',180),('I_B',125)]:
            vertex(p, role, r, 25)
        for lane in (1,2):
            for role, r in [('START',440),('REF',300),('END',250)]:
                vertex(p, f'P{lane}_{role}', r, 25 if lane==1 else 75)
        for role,r in [('O_B',125),('O_A',180),('B1',350),('B2',570),('OUT',760)]:
            vertex(p,role,r,-25,True)
        for a,b,l in [('IN','B3',750),('B3','HOME',750),('HOME','FORK',100)]:
            edge(name(p,a),name(p,b),l,p+'_IN')
        for lane in (1,2):
            seq=[name(p,r) for r in ['FORK',f'P{lane}_START',f'P{lane}_REF',f'P{lane}_END','MERGE']]
            for a,b,l in zip(seq,seq[1:],[100,500,100,100]):edge(a,b,l,p+str(lane))
            paths[(p,lane,'HOME_REF')]=[name(p,r) for r in ['HOME','FORK',f'P{lane}_START',f'P{lane}_REF']]
            paths[(p,lane,'REF_ENTRY')]=[name(p,r) for r in [f'P{lane}_REF',f'P{lane}_END','MERGE','I_A']]
        edge(name(p,'MERGE'),name(p,'I_A'),100,p+'_IN')
        edge(name(p,'I_A'),name(p,'I_B'),100,'JUNCTION',True)
        edge(name(p,'O_B'),name(p,'O_A'),100,'JUNCTION',True)
        for a,b,l in [('O_A','B1',600),('B1','B2',600),('B2','OUT',900)]:edge(name(p,a),name(p,b),l,p+'_OUT')
    
    for p in PORTS:
        for q in PORTS:
            if p==q:continue
            straight=q==OPPOSITE[p]
            a=name(p,'I_A' if straight else 'I_B')
            b=name(q,'O_A' if straight else 'O_B')
            edge(a,b,400 if straight else 200,'JUNCTION',True,not straight)
            paths[(p,q,'CORE')]=[name(p,'I_A')]+([] if straight else[name(p,'I_B'),name(q,'O_B')])+[name(q,'O_A')]
    result={'vertices':vertices,'edges':edges}
    tp.validate_spec(result)
    return result,values,paths


def add_signals(blob,station,ids,values):
    root,ver=w.load_next_compatible(blob)
    models,byid=rf.document(root)
    specs=[]
    for p in PORTS:
        for role,typ,kind in [('B3',25,3),('HOME',1,2),('P1_REF',1,4),('P2_REF',1,4),
                              ('I_A',1,2),('O_A',25,3),('B1',25,3),('B2',25,3)]:
            key=name(p,role); v=values[key]; end=byid[ids[key][v['side']]]
            assert end.contents[11].value is None
            mid=max(byid)+1+len(specs)
            dx,dy=VECTOR[p]
            if v['side']==SIDE[p]:dx,dy=-dx,-dy
            x,y=v['x']-12*dx+10*dy,v['y']-12*dy-10*dx
            ind=ns.obj([('OTSigInd',0),('NSObject',0)],[('i',[0]),('@',[end])])
            signal=ns.obj([('OTSignalModel',11),('OTGraphicModel',1),('NSObject',0)],
                [('i',[mid]),('f',[0.]),('f',[ns.number(x)]),('f',[ns.number(y)]),
                 ('i',[end.contents[4].value]),('i',[end.contents[5].value]),('@',[None]),('@',[end]),
                 ('iii',[typ,kind,2]),('iiii',[2,400 if typ==25 else 500,640 if typ==25 else 644,0]),
                 ('@',[g.wrapped('OTSigIndList',[ind])]),('i',[0]),('i',[7]),
                 ('@',[ns.string('S_'+station+'_'+key)]),('@',[ns.arr()]),('@',[ns.arr()]),('f',[0.])])
            end.contents[11].value=signal;models.append(signal)
            specs.append({'id':mid,'end_id':end.contents[0].value,'vertex':key,'port':p,'role':role,'type':typ})
    w.set_elements(root.contents[2].value,models)
    return w.dump_verified(root,ver),specs


def make_document(sources,station):
    spec,values,sequences=specification()
    blob,base=tp.generate_network(sources['header'],sources['shapes'],spec)
    ids=base['vertex_end_ids']
    blob,signals=add_signals(blob,station,ids,values)
    blob,station_catalog,binding=sb.bind_stations(blob,[dict(sign=station,name='Junction '+station,
        end_ids=[ids[name(p,f'P{i}_REF')][SIDE[p]] for p in PORTS for i in (1,2)],
        placement=g.placement(800,800),station_type_raw=2,interlock_type_raw=4,icon_show_type_raw=1,timing_point=True)])
    root,version=w.load_next_compatible(blob);models,byid=rf.document(root)
    sm=byid[ids['W_P1_REF'][0]].contents[12].value
    for p in PORTS:
        for lane in (1,2):
            for role in ('START','END'):
                for eid in ids[name(p,f'P{lane}_{role}')]:byid[eid].contents[12].value=sm
    
    core_edges=[byid[base['edge_ids'][e['key']]] for e in spec['edges'] if e['track_name']=='JUNCTION']
    elems={id(end.contents[7].value):end.contents[7].value for edge in core_edges for end in (edge.contents[7].value,edge.contents[8].value)}
    target=next(iter(elems.values())); members=[]
    for elem in elems.values():
        for end in pf.mutable_array(elem.contents[7].value):
            assert end not in members
            members.append(end);end.contents[7].value=target
    w.set_elements(target.contents[7].value,members)
    models=[m for m in models if w.kind(m)!='OTElement' or id(m) not in elems or m is target]
    w.set_elements(root.contents[2].value,models)
    for index,rect in {8:[60.,60.,1000.,850.],9:[0.,0.,1600.,1600.],10:[0.,0.,1600.,1600.]}.items():
        root.contents[index].values=rect
    blob=w.dump_verified(root,version)
    root,version,models,byid=graphics._read(blob)
    palette=graphics._palette(root);mid=max(byid)+1;rects=[]
    for p in PORTS:
        a=point(p,440,44);b=point(p,300,56)
        rect=(min(a[0],b[0]),min(a[1],b[1]),abs(a[0]-b[0]),abs(a[1]-b[1]))
        
        obj=graphics._rectangle(mid+len(rects),rect,palette);models.append(obj);rects.append(rect)
    w.set_elements(root.contents[2].value,models)
    blob=w.dump_verified(root,version)
    entries=[dict(key='station',text='Junction '+station,rect=[680,800,250,35])]
    for p in PORTS:
        for lane in (1,2):
            v=values[name(p,f'P{lane}_REF')]
            entries.append(dict(key=p+str(lane),text='Track '+p+str(lane),rect=[v['x']+8,v['y']+8,100,27]))
        x,y=point(p,720,100)
        entries.append(dict(key='port_'+p,text={'W':'WEST','E':'EAST','N':'NORTH','S':'SOUTH'}[p],rect=[x-35,y,90,27]))
    blob,label_receipt=labels.add_labels(blob,entries,template_document=sources['header'])
    item=cats.station_items(w.load_next_compatible(station_catalog)[0])[station]
    return blob,item,{'ids':ids,'base':base,'signals':signals,'core_element_id':target.contents[0].value,
                      'platform_rectangles':rects,'labels':label_receipt,'values':values,'sequences':sequences}


def local_route(root,models,ids,values,sequence,label):
    nodes=[models[ids[key][values[key]['side']]] for key in sequence]
    ns.validate_movement(root,[n.contents[0].value for n in nodes])
    owner=nodes[0];aid=owner.contents[19].value+1
    route=g.route(label,aid,owner.contents[0].value,nodes,-1)
    route.contents[12].values[0]=ns.arr([nodes[0],nodes[-1]])
    backing=owner.contents[15].value.contents[0].value
    w.set_elements(backing,pf.mutable_array(backing)+[route]);owner.contents[19].value=aid
    rf.validate_chain(root,route,[n.contents[0].value for n in nodes])
    return cd.ref(route)
