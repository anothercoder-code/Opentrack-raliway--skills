"""Independent current catalog accessors from audited fields and native fixtures.

Returns original graph objects, not copied JSON. No graph/runtime fallback and
no migration. Supported application record versions are deliberately explicit.
"""
from . import writer as w

class CatalogSchemaError(ValueError):
    pass

LAYOUTS={
 'OTCourse':(11,['@','f','@','@','@','i','i','ff','i','i','@','@','ff','@','@']),
 'OTTrain':(16,['@','iif','@@@','@','f','fff','i','fff','ff','f','fff','i','if','ff','f','i','ff','i','i','f','f','iff','f']),
 'OTEngine':(2,['i','@','iiifif','i','f','i','i','i','i','i','i','i','i','i','f','f','@','i']),
 'OTStation':(3,['i','@','@','i','iii','ii','@','i','@','@']),
 'OTTrainEngine':(0,['@','i']),
}

def fail(message): raise CatalogSchemaError(message)


PARENTS={
 'OTCourseList':[('OTMutableArray',0),('NSObject',0)],
 'OTTrainList':[('OTMutableArray',0),('NSObject',0)],
 'OTEngine':[('OTVehicle',0),('NSObject',0)],
 'NSMutableArray':[('NSArray',0),('NSObject',0)],
 'NSMutableDictionary':[('NSDictionary',0),('NSObject',0)],
}
def hierarchy(obj):
    name=w.kind(obj);expected=PARENTS.get(name,[('NSObject',0)])
    current=obj.clazz.superclass
    for parent,version in expected:
        if current is None or current.name!=parent.encode('ascii') or current.version!=version:
            fail(f'Unsupported {name} inheritance chain')
        current=current.superclass
    if current is not None:fail(f'Unsupported {name} trailing/cyclic superclass')

def shape(obj,name,version,encodings):
    if w.kind(obj)!=name or obj.clazz.version!=version:
        fail(f'Unsupported {name} class/version; requires {name} v{version}')
    hierarchy(obj)
    expected=[[bytes([c]) for c in e.encode('ascii')] for e in encodings]
    if len(obj.contents)!=len(expected) or any(g.encodings!=e or len(g.values)!=len(e) for g,e in zip(obj.contents,expected)):
        fail(f'Unsupported {name} field-group encoding')
    return obj

def record(obj,name):
    version,encodings=LAYOUTS[name]
    return shape(obj,name,version,encodings)

def text(obj):
    if w.kind(obj)!='NSString' or obj.clazz.version!=1:
        fail('Expected current NSString v1')
    hierarchy(obj)
    try:value=w.string(obj)
    except (ValueError,TypeError,UnicodeError) as e:raise CatalogSchemaError('Invalid native string') from e
    if not isinstance(value,str):fail('Expected non-nil string')
    return value

def array(obj):
    if w.kind(obj) not in ('NSArray','NSMutableArray') or obj.clazz.version!=0:
        fail('Expected current NSArray/NSMutableArray v0')
    hierarchy(obj)
    try:return w.elements(obj)
    except (ValueError,TypeError,IndexError) as e:raise CatalogSchemaError('Invalid native array') from e

def named(rows,name,slot):
    seen=set()
    for row in rows:
        record(row,name);key=text(row.contents[slot].value)
        if not key or key in seen:fail(f'Empty or duplicate {name} identity')
        seen.add(key)
    return rows

def course_array(root):
    shape(root,'OTCourseList',3,['i','@','@','@','@'])
    for i in (1,2,3,4):array(root.contents[i].value)
    named(array(root.contents[4].value),'OTCourse',0)
    return root.contents[4].value

def course_items(root):
    return array(course_array(root))

def train_items(root):
    shape(root,'OTTrainList',3,['i','@','@','@'])
    for i in (1,2,3):array(root.contents[i].value)
    return named(array(root.contents[3].value),'OTTrain',0)

def engine_items(root):
    return named(array(root),'OTEngine',1)

def bound_engine_names(train):
    record(train,'OTTrain')
    refs=array(train.contents[2].values[1])
    result=[]
    for ref in refs:
        record(ref,'OTTrainEngine');name=text(ref.contents[0].value)
        if not name:fail('Empty Engine reference')
        result.append(name)
    return result

def station_items(root):
    if w.kind(root) not in ('NSDictionary','NSMutableDictionary') or root.clazz.version!=0:
        fail('Expected current NSDictionary/NSMutableDictionary v0')
    hierarchy(root)
    if not root.contents or root.contents[0].encodings!=[b'i'] or len(root.contents[0].values)!=1:
        fail('Invalid station dictionary count encoding')
    count=root.contents[0].value
    if type(count) is not int or count<0 or len(root.contents)!=1+2*count:
        fail('Station dictionary count mismatch')
    result={}
    for i in range(1,len(root.contents),2):
        key,value=root.contents[i:i+2]
        if key.encodings!=[b'@'] or value.encodings!=[b'@'] or len(key.values)!=1 or len(value.values)!=1:
            fail('Invalid station dictionary entry encoding')
        sign=text(key.value);station=record(value.value,'OTStation')
        if not sign or sign in result:fail('Empty or duplicate station key')
        if text(station.contents[1].value)!=sign:fail('Station dictionary key/sign mismatch')
        result[sign]=station
    return result

def native_strings(root):
    """Every unique string graph object, cycle-safe; preserves object identity."""
    return [obj for obj in w.objects(root) if w.kind(obj) in ('NSString','NSMutableString') and _valid_string(obj)]

def _valid_string(obj):
    text(obj)
    return True
