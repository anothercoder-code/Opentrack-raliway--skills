"""Current Train16 same-formation template clone. No IO, migration or simulator."""
import hashlib
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.graph_references import reference_inventory
from opentrack_ai.current_archive.formation_operations import trailer, position, snapshot
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT

class TrainFactoryError(ValueError): pass

def require(ok, message):
    if not ok: raise TrainFactoryError(message)

def name(value):
    require(type(value) is str and bool(value.strip()) and all(ord(x)>=32 and ord(x)!=127 for x in value),'Nonempty control-free exact name required')
    try: encoded=value.encode('utf8')
    except UnicodeError as e: raise TrainFactoryError('Invalid UTF8 name') from e
    require(len(encoded)<=200,'Name exceeds API limit of 200 UTF8 bytes')
    return value

def wrapper(obj):
    require(w.kind(obj)=='OTDecelerationArray' and obj.clazz.version==0,'Current deceleration wrapper required')
    cl=obj.clazz.superclass
    require(cl is not None and cl.name==b'OTMutableArray' and cl.version==0 and cl.superclass is not None and cl.superclass.name==b'NSObject' and cl.superclass.version==0 and cl.superclass.superclass is None,'Unsupported deceleration ancestry')
    require(len(obj.contents)==1 and obj.contents[0].encodings==[b'@'] and len(obj.contents[0].values)==1,'Invalid deceleration wrapper')
    for point in c.array(obj.contents[0].value):c.shape(point,'OTDeceleration',1,['iff'])

def validate_template(train):
    c.record(train,'OTTrain');c.text(train.contents[0].value);c.text(train.contents[3].value)
    wrapper(train.contents[2].values[0])
    engines=c.array(train.contents[2].values[1]);trailers=c.array(train.contents[2].values[2])
    for ref in engines:c.record(ref,'OTTrainEngine');name(c.text(ref.contents[0].value))
    for ref in trailers:trailer(ref)
    positions=[position(x) for x in engines+trailers]
    require(0<len(positions)<=1024 and all(type(x)is int for x in positions) and sorted(positions)==list(range(1,len(positions)+1)),'Template requires complete unique 1..N formation positions')
    
    allowed={'OTTrain','NSString','NSArray','NSMutableArray','OTTrainEngine','OTTrailer','OTDecelerationArray','OTDeceleration'}
    require(all(w.kind(o) in allowed for o in w.objects(train)),'Unknown owned template class')
    return engines,trailers

def clone_owned(obj, memo=None):
    """Clone validated owned objects; immutable NSString and Class identities retained."""
    if memo is None:memo={}
    if not isinstance(obj,w.GenericArchivedObject):return obj
    if w.kind(obj)=='NSString':return obj
    if id(obj) in memo:return memo[id(obj)]
    out=w.GenericArchivedObject(obj.clazz,None,[]);memo[id(obj)]=out
    out.contents=[w.TypedGroup(g.encodings,[clone_owned(v,memo) for v in g.values]) for g in obj.contents]
    return out

def clone_train_archive(train_blob,depot_blob,*,template_name,new_name):
    """bytes + bytes -> (new trains bytes, receipt). Same-project check is caller-owned."""
    require(type(train_blob)is bytes and type(depot_blob)is bytes,'Immutable train and depot bytes required')
    name(template_name);name(new_name)
    root,version=w.load_next_compatible(train_blob);depot,_=w.load_next_compatible(depot_blob)
    rows=c.train_items(root);require(root.contents[0].value==17,'Only TrainList internal format 17 supported')
    lookup={c.text(t.contents[0].value):t for t in rows}
    require(template_name in lookup,'Explicit existing template required');require(new_name not in lookup,'Train name already exists')
    _,counts=reference_inventory(root);parent=root.contents[3].value
    require(counts[id(root)]==0 and counts[id(parent)]==1,'Shared root or Train parent array rejected')
    template=lookup[template_name];engines,trailers=validate_template(template)
    known={c.text(e.contents[1].value) for e in c.engine_items(depot)}
    engine_names=[c.text(e.contents[0].value) for e in engines]
    require(set(engine_names)<=known,'Engine dependency missing from supplied depot')
    categories={}
    for cat in c.array(root.contents[1].value):
        c.shape(cat,'OTTrainCategory',19,CATEGORY_LAYOUT);key=c.text(cat.contents[1].value)
        require(key and key not in categories,'Empty/duplicate Category identity');categories[key]=cat
    category=c.text(template.contents[3].value);require(category in categories,'Category dependency missing from supplied TrainList')
    before=w.fingerprint(root);old_snapshot=snapshot(root)
    created=clone_owned(template)
    created.contents[0].value=w.GenericArchivedObject(template.contents[0].value.clazz,None,[w.TypedValue(b'+',new_name.encode('utf8'))])
    old_ids={id(o) for o in w.objects(root)}
    require(not any(id(o) in old_ids and w.kind(o)!='NSString' for o in w.objects(created)),'Owned clone alias leaked')
    parent.contents[0].value=len(rows)+1
    parent.contents.append(w.TypedValue(b'@',created))
    after=snapshot(root)
    require(all(after.get(k)==v for k,v in old_snapshot.items() if k[0]!=id(parent)),'Original graph changed')
    output=w.dump_verified(root,version);fresh,_=w.load_next_compatible(output);freshrows=c.train_items(fresh)
    require(len(freshrows)==len(rows)+1 and c.text(freshrows[-1].contents[0].value)==new_name,'Fresh append mismatch')
    validate_template(freshrows[-1]);fresh.contents[3].value.contents.pop()
    fresh.contents[3].value.contents[0].value=len(rows)
    require(w.fingerprint(fresh)==before,'Original objects/references changed on reload')
    return output,{'operation':'same_formation_template_clone','template_name':template_name,'new_name':new_name,'category':category,'engine_names':engine_names,'train_count_before':len(rows),'train_count_after':len(rows)+1,'source_sha256':{'trains':hashlib.sha256(train_blob).hexdigest(),'depot':hashlib.sha256(depot_blob).hexdigest()},'output_sha256':hashlib.sha256(output).hexdigest(),'owned_mutable_objects_isolated':True,'original_graph_restoration_verified':True,'fresh_reload_verified':True,'native_application_tested':False,'same_project_verified':False,'physical_recomputation':False,'original_copyWithZone_equivalent':False}
