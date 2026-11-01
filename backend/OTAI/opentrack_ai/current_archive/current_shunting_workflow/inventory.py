"""Read-only inventory of explicitly known historical/current Shunting layouts.
Read acceptance never expands the mutation contract in core.py.
"""
from .. import writer as w, path_functions as f, route_factory as rf
from . import core
need=rf.require
DOC3=['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@','ffff','iii','ff','@','@']

def layout(obj,chain,groups):
    f.hierarchy(obj,chain)
    need([b''.join(g.encodings).decode('ascii')for g in obj.contents]==groups,'Unknown inventory layout')
    need(all(len(g.encodings)==len(g.values)for g in obj.contents),'Malformed inventory groups')

def end_layout(owner):
    kind=w.kind(owner)
    need(kind in('OTEndModel','OTConnModel','OTStationEndModel'),'Unknown End subclass')
    ev=owner.clazz.version if kind=='OTEndModel'else owner.clazz.superclass.version
    need(ev in(6,7),'Unknown End inventory version')
    chain=[('OTEndModel',ev),('OTGraphicModel',1),('NSObject',0)]
    enc=rf.END if ev==7 else rf.END[:-1]
    if kind=='OTConnModel':chain=[('OTConnModel',1)]+chain;enc=enc+['@','@','i','i']
    elif kind=='OTStationEndModel':chain=[('OTStationEndModel',0)]+chain
    layout(owner,chain,enc)
    return ev

def inspect_inventory(data):
    root,version=w.load(data);dv=root.clazz.version
    need(dv in(3,4),'Only documented Document3/4 inventory layouts supported')
    layout(root,[('OTDocument',dv),('NSObject',0)],DOC3+(['@','@']if dv==4 else[]))
    models=f.mutable_array(root.contents[2].value);rows=[]
    modelids=[m.contents[0].value for m in models]
    need(all(type(x)is int for x in modelids)and len(modelids)==len(set(modelids)),'Invalid/duplicate document model identity')
    for owner in models:
        if w.kind(owner)not in('OTEndModel','OTConnModel','OTStationEndModel'):continue
        ev=end_layout(owner)
        container=owner.contents[16].value
        if container is None:continue
        paths=rf.wrapper(container,'OTShuntingList')
        for path in paths:
            f.shape(path,'OTPath');bodies=f.mutable_array(path.contents[0].value)
            need(len(bodies)==1 and w.kind(bodies[0])=='OTShunting','Unknown Shunting-list member representation')
            body=bodies[0];sv=body.clazz.superclass.version
            need(sv in(5,6),'Unknown SecurityArray inventory version')
            groups=core.ENC if sv==6 else core.ENC[:10]+['f']
            layout(body,[('OTShunting',0),('OTSecurityArray',sv),('OTOrgArray',2),('OTMutableArray',0),('NSObject',0)],groups)
            nodes=f.mutable_array(body.contents[0].value)
            for node in nodes:end_layout(node)
            refs=[]
            for info in f.mutable_array(path.contents[4].value):
                rf.layout(info,'OTArrayInfo',0,['@','ii']);refs.append({'name':f.string(info.contents[0].value),'array_id':info.contents[1].values[0],'start_id':info.contents[1].values[1]})
            inds=[]
            for ind in rf.wrapper(body.contents[4].value,'OTSigIndList'):
                rf.layout(ind,'OTSigInd',0,['i','@']);inds.append({'code':ind.contents[0].value,'points_to_this_body':ind.contents[1].value is body})
            rows.append({'owner_end_id':owner.contents[0].value,'owner_end_version':ev,'path':core.identity(path),'body':core.identity(body),'body_class_version':0,'security_array_version':sv,'saved_references':refs,'end_ids':[n.contents[0].value for n in nodes],'all_nodes_in_local_model_array':all(n in models for n in nodes),'first_foreign_index':body.contents[5].values[4],'overlap_name':f.string(body.contents[7].value),'overlap_start_id':body.contents[9].value,'speed_kmh':body.contents[11 if sv==6 else 10].value,'release_time_s':body.contents[5].values[2],'reservation_time_s':body.contents[5].values[3],'indications':inds,'editable':False,'edit_scope':'existing preview-only current mutation API; never native runtime approval','edit_reasons':[]})
    
    
    try:
        _,_,_,eligible=core.load(data)
        refs=[core.identity(r[0])for r in eligible]
        for row in rows:
            row['editable']=row['path']in refs
            if not row['editable']:row['edit_reasons']=['Not selected by current mutation contract']
    except (ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:
        for row in rows:row['edit_reasons']=['Outside current mutation domain: '+str(exc)[:300]]
    return {'input_sha256':core.sha(data),'document_version':dv,'archive_system_version':version,'shuntings':rows,'count':len(rows),'read_only':True,'source_modified':False,'native_execution':False,'scope':'Actual local End.ShuntingList ownership only, including documented legacy record layouts; embedded unowned graph objects excluded.'}
