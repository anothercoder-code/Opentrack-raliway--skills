"""Current Engine integer setters. Pure archive bytes -> verified bytes, not simulation."""
from opentrack_ai.current_archive import writer as w, catalogs as c

FIELDS={
 'adhesion_load':(3,'0x004cbd60','raw_native_mass_integer'),
 'force_max_kn':(6,'0x004cbde0','kN'),
 'force_min_kn':(17,'0x004cbdf0','kN'),
}
DIAGRAM_LAYOUT=['iiiiiii','@','@','@','@','i','@','@']

class PhysicsError(ValueError):pass
class SharedDiagramError(PhysicsError):
    def __init__(self,owners,references):
        self.owners=owners;self.references=references
        super().__init__('First diagram is shared; native zero setter affects every owner; independent edit refused: '+repr(owners))

def integer(value):
    if type(value) is not int or not -(2**31)<=value<2**31:
        raise PhysicsError('Exact signed int32 required; bool, float, string and overflow forbidden')
    return value

def diagrams(engine):
    
    obj=engine.contents[16].value
    return [] if obj is None else c.array(obj)

def reference_inventory(root,target):
    from .graph_references import reference_inventory as inventory
    try:objects,counts=inventory(root)
    except ValueError as e:raise PhysicsError(str(e)) from e
    
    return objects,counts[id(target)]+int(target is root)

def inspect(root,name):
    if type(name) is not str or not name:raise PhysicsError('Exact nonempty Engine name required')
    items=c.engine_items(root)
    selected=next((e for e in items if c.text(e.contents[1].value)==name),None)
    if selected is None:raise PhysicsError('Engine name not found')
    return items,selected

def patch_archive(blob,name,changes):
    if type(blob) is not bytes:raise PhysicsError('Immutable bytes required')
    if type(changes) is not dict or not changes:raise PhysicsError('Nonempty explicit changes required')
    for field,value in changes.items():
        if field not in FIELDS:raise PhysicsError('Unsupported field: '+str(field))
        integer(value)
    root,version=w.load_next_compatible(blob)
    items,selected=inspect(root,name)
    
    
    for ancestor,label in ((root,'depot root'),(selected,'selected Engine')):
        _,incoming=reference_inventory(root,ancestor)
        if incoming!=1:raise PhysicsError('Shared '+label+' cannot be edited independently; incoming='+str(incoming))
    diagram=None;owners=[];side_effect=None
    if changes.get('adhesion_load')==0:
        ds=diagrams(selected)
        if ds:
            _,array_incoming=reference_inventory(root,selected.contents[16].value)
            diagram=ds[0]
            c.shape(diagram,'OTDDiagram',3,DIAGRAM_LAYOUT)
            
            
            graph_objects,references=reference_inventory(root,diagram)
            for owner in graph_objects:
                if w.kind(owner)=='OTEngine':
                    c.record(owner,'OTEngine')
                    for index,obj in enumerate(diagrams(owner)):
                        if obj is diagram:owners.append({'engine':c.text(owner.contents[1].value),'diagram_index':index})
            if references!=1 or len(owners)!=1:raise SharedDiagramError(owners,references)
            if array_incoming!=1:raise PhysicsError('Shared diagram array cannot be edited independently; incoming='+str(array_incoming))
            side_effect={'class':'OTDDiagram','group':0,'slot':5,'encoding':'i','before':diagram.contents[0].values[5],'after':0,'owners':owners,'setter':'0x00471668'}
    report=[]
    for field,value in changes.items():
        group,address,unit=FIELDS[field]
        report.append({'field':field,'group':group,'slot':0,'encoding':'i','before':selected.contents[group].value,'after':value,'setter':address,'unit':unit})
        selected.contents[group].value=value
    if diagram is not None:diagram.contents[0].values[5]=0
    output=w.dump_verified(root,version)
    fresh,_=w.load_next_compatible(output);_,actual=inspect(fresh,name)
    for field,value in changes.items():
        if actual.contents[FIELDS[field][0]].value!=value:raise PhysicsError('Reload mismatch')
    if diagram is not None and diagrams(actual)[0].contents[0].values[5]!=0:raise PhysicsError('Diagram reload mismatch')
    return output,{'engine':name,'changes':report,'diagram_side_effect':side_effect,'reference_changes':False,'fresh_reload_verified':True,'native_application_tested':False,'scope':'current archive setter semantics; no physics, UI controller or derived recomputation'}
