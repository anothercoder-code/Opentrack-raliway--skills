"""Bounded Train16 identity update and closed Course11 reverse references.

Pure bytes in/out. No file publication or native execution. Complete run selection
and catalog bindings are caller-owned; unknown same-name graph uses fail closed.
"""
import hashlib
from . import writer as w, catalogs as c
from .course_factories import name
from .graph_references import reference_inventory

def need(ok,message):
    if not ok:raise ValueError(message)
def digest(blob):return hashlib.sha256(blob).hexdigest()
def reject_unclassified_literals(objects,old_name):
    """Unknown inline/string token representations cannot silently hide a name."""
    raw=old_name.encode("ascii")
    def visit(value):
        if isinstance(value,w.GenericArchivedObject):return
        if isinstance(value,w.CString):need(value.token.data!=raw,"Unclassified C-string identity")
        elif type(value)is bytes:need(value!=raw,"Unclassified inline identity bytes")
        elif type(value)is str:need(value!=old_name,"Unclassified inline identity text")
        elif isinstance(value,w.TypedGroup):
            for child in value.values:visit(child)
        elif isinstance(value,w.Array):visit(value.elements)
        elif isinstance(value,w.GenericStruct):visit(value.fields)
        elif isinstance(value,(list,tuple)):
            for child in value:visit(child)
    for obj in objects:
        if w.kind(obj)!="NSString":
            for group in obj.contents:visit(group)

def rename_train(archives,*,train_member,course_member,old_name,new_name):
    name(old_name);name(new_name);need(old_name!=new_name,'Distinct exact names required')
    need(type(archives)is dict and train_member!=course_member and {train_member,course_member}<=archives.keys(),'Distinct bound Train and Course archives required')
    roots={};versions={}
    for member,blob in archives.items():
        need(type(blob)is bytes,'Immutable archive bytes required')
        roots[member],versions[member]=w.load_next_compatible(blob)
    trains=c.train_items(roots[train_member]);courses=c.course_items(roots[course_member])
    names={c.text(x.contents[0].value)for x in trains}
    need(old_name in names and new_name not in names,'Unknown Train or name collision')
    need(all(c.text(x.contents[3].value)in names for x in courses),'Unbound Course Train reference')
    train=next(x for x in trains if c.text(x.contents[0].value)==old_name)
    affected=[x for x in courses if c.text(x.contents[3].value)==old_name]
    allowed={train_member:[(train,0)],course_member:[(x,3)for x in affected]}
    before={n:w.fingerprint(r)for n,r in roots.items()};restorations={};out=dict(archives)
    for member,root in roots.items():
        slots=allowed.get(member,[]);objects,counts=reference_inventory(root)
        reject_unclassified_literals(objects,old_name)
        candidates=[o for o in objects if w.kind(o)=='NSString' and c.text(o)==old_name]
        for obj in candidates:
            positions=[(owner,index)for owner,index in slots if owner.contents[index].value is obj]
            need(len(positions)==counts[id(obj)] and positions,'Unclassified same-name saved reference in '+member)
        replacements={};restore=[]
        for owner,index in slots:
            original=owner.contents[index].value
            if id(original)not in replacements:
                replacements[id(original)]=w.GenericArchivedObject(original.clazz,None,[w.TypedValue(b'+',new_name.encode('ascii'))])
            owner.contents[index].value=replacements[id(original)];restore.append((owner,index,original))
        if slots:
            out[member]=w.dump_verified(root,versions[member])
            fresh,_=w.load_next_compatible(out[member])
            if member==train_member:
                frows=c.train_items(fresh);fs=[(next(x for x in frows if c.text(x.contents[0].value)==new_name),0)]
            else:
                frows=c.course_items(fresh);ids={c.text(x.contents[0].value)for x in affected}
                fs=[(x,3)for x in frows if c.text(x.contents[0].value)in ids]
            need(len(fs)==len(slots),'Fresh reverse-reference count mismatch')
            reverse={}
            for owner,index in fs:
                string=owner.contents[index].value;need(c.text(string)==new_name,'Fresh identity mismatch')
                if id(string)not in reverse:reverse[id(string)]=w.GenericArchivedObject(string.clazz,None,[w.TypedValue(b'+',old_name.encode('ascii'))])
                owner.contents[index].value=reverse[id(string)]
            need(w.fingerprint(fresh)==before[member],'Unrelated graph or sharing changed on fresh reload')
        for owner,index,original in restore:owner.contents[index].value=original
        need(w.fingerprint(root)==before[member],'Original graph was not restored')
    ft,_=w.load_next_compatible(out[train_member]);fc,_=w.load_next_compatible(out[course_member])
    fn={c.text(x.contents[0].value)for x in c.train_items(ft)}
    need(all(c.text(x.contents[3].value)in fn for x in c.course_items(fc)),'Output Course Train closure failed')
    return out,{'operation':'closed_train_name_update','old_name':old_name,'new_name':new_name,'updated_course_ids':[c.text(x.contents[0].value)for x in affected], 'changed_members':[n for n in out if out[n]!=archives[n]],'fresh_reload_verified':True,'unrelated_graph_restoration_verified':True,'native_execution':False,'saved':False,'source_hashes':{n:digest(b)for n,b in archives.items()},'output_hashes':{n:digest(b)for n,b in out.items()}}
