"""Original Engine/diagram/Train decoder defaults, without running native code."""
from collections import Counter
import copy
from pathlib import Path

from .archive import APIError,w
from .resources import templates

TRAIN_FIELDS=[
    (1,'@',None),(1,'f',[3.]),(2,'fff',[1.5,.003,.00085]),(3,'i',[0]),
    (4,'fff',[3.3,.02422,.000552]),(4,'ff',[100.,131.]),(5,'f',[0.]),
    (6,'fff',[.01,-.1,-1.5]),(6,'i',[0]),(7,'if',[0,100.]),(7,'ff',[.069,.006]),
    (8,'f',[1000.]),(9,'i',[0]),(10,'ff',[0.,0.]),(11,'i',[0]),(12,'i',[1]),
    (13,'f',[100.]),(14,'f',[0.]),(15,'iff',[0,0.,0.]),(16,'f',[0.]),
]


def group(types,values):
    encodings=[char.encode('ascii') for char in types]
    return w.ar.TypedValue(encodings[0],values[0]) if len(encodings)==1 else w.ar.TypedGroup(encodings,list(values))


class Factory:
    def __init__(self):self.shapes,_=templates(Path(__file__).resolve().parents[2])
    def template(self,name):return self.shapes[name]
    def array(self,items=()):
        obj=copy.deepcopy(self.shapes['NSMutableArray']);w.set_elements(obj,list(items));return obj
    def string(self,value):
        obj=copy.deepcopy(self.shapes['NSString']);obj.contents=[w.ar.TypedValue(b'+',value.encode('ascii'))];return obj
    def efficiency(self):
        obj=copy.deepcopy(self.shapes['OTEfficiencyArray']);obj.contents[0].values[0]=self.array();return obj
    def generic_system(self):
        obj=copy.deepcopy(self.shapes['NSNumber']);obj.contents=[w.ar.TypedValue(b'*',b'i'),w.ar.TypedValue(b'i',1)];return self.array([obj])
    def black(self):
        from .models import CalibratedWhite
        from .native_colors import make_color
        return make_color(self,CalibratedWhite(white=0))


def check(obj,expected):
    actual=[''.join(value.decode('ascii') for value in cell.encodings) for cell in obj.contents]
    if actual!=expected:
        raise APIError('ROLLING_STOCK_SCHEMA','Record groups do not match the original decoder branch.',{'class':w.kind(obj),'version':obj.clazz.version,'expected':expected,'actual':actual})


def arrays(value):
    if value is None:return []
    if w.kind(value) not in ['NSArray','NSMutableArray']:raise APIError('ROLLING_STOCK_SCHEMA','Expected a native stock array.',w.kind(value))
    return w.elements(value)


def set_version(obj,version):obj.clazz=copy.deepcopy(obj.clazz);obj.clazz.version=version


def upgrade_engine(obj,factory):
    version=obj.clazz.version
    if not 0<=version<=2:raise APIError('ROLLING_STOCK_VERSION','Unsupported Engine archive version.',version)
    check(obj,['i','@','iiifif','i','f','i','i','i','i','i','i','i','i','i','f','f','@']+(['i'] if version>=2 else []))
    if version==2:return False
    if version==0:
        diagram=obj.contents[16].value
        if diagram is None or w.kind(diagram)!='OTDDiagram':raise APIError('ROLLING_STOCK_SCHEMA','Original Engine v0 requires its single saved diagram.')
        obj.contents[16].values[0]=factory.array([diagram])
    remaining=obj.contents[11].value&0xffffffff;flags=0
    for bit in [8,4,2,1]:
        if remaining>=bit:flags+=bit;remaining-=bit
    obj.contents[11].values[0]=flags
    obj.contents.append(group('i',[0]));set_version(obj,2);return True


def upgrade_diagram(obj,factory):
    version=obj.clazz.version
    if not 0<=version<=3:raise APIError('ENGINE_DIAGRAM_VERSION','Unsupported diagram archive version.',version)
    expected=['iiiiii','@'] if version==0 else ['iiiiiii','@','@','@','@']
    if version>=2:expected+=['i','@']
    if version>=3:expected+=['@']
    check(obj,expected)
    if version==3:return False
    if version==0:
        obj.contents[0]=group('iiiiiii',[*obj.contents[0].values,1])
        obj.contents.extend([group('@',[factory.array()]),group('@',[factory.generic_system()]),group('@',[factory.black()])])
    if version<2:obj.contents.extend([group('i',[-200]),group('@',[factory.string('')])])
    obj.contents[0].values[6]=int(obj.contents[0].values[6]!=0)
    for index in [1,2,3]:
        if obj.contents[index].value is None:obj.contents[index].values[0]=factory.array()
    obj.contents.append(group('@',[factory.efficiency()]));set_version(obj,3);return True


def upgrade_train(obj,factory):
    version=obj.clazz.version
    if not 0<=version<=16:raise APIError('ROLLING_STOCK_VERSION','Unsupported Train archive version.',version)
    expected=['@','iif','@@@']+[types for introduced,types,_ in TRAIN_FIELDS if introduced<=version]
    check(obj,expected)
    if version==16:return False
    train_type=obj.contents[1].values[0]
    for introduced,types,values in TRAIN_FIELDS:
        if introduced<=version:continue
        if types=='@':values=[factory.string({0:'Category 1',1:'Category 2'}.get(train_type,'Category 3'))]
        elif introduced==2 and train_type==2:values=[1.5,.003,.0016]
        obj.contents.append(group(types,values))
    if version<13:
        position=1
        for ref in arrays(obj.contents[2].values[1]):
            if w.kind(ref)!='OTTrainEngine':raise APIError('ROLLING_STOCK_SCHEMA','Expected an original Engine reference.')
            ref.contents[1].values[0]=position;position+=1
        for trailer in arrays(obj.contents[2].values[2]):trailer.contents[3].values[1]=position;position+=1
    
    raw=obj.contents[15].value&0xffffffff;hold=raw>=2;remaining=raw-2 if hold else raw
    obj.contents[15].values[0]=(2 if hold else 0)+(1 if remaining>=1 else 0)
    obj.contents[11].values[0]=1 if obj.contents[11].value>=1 else 0
    set_version(obj,16);return True


def migrate(roots,entities=('engines','formations'),factory=None):
    factory=factory or Factory();counts=Counter();seen=set();objects=[]
    for root in roots:
        for obj in w.objects(root):
            if id(obj) not in seen:seen.add(id(obj));objects.append(obj)
    wanted={'OTEngine','OTDDiagram'} if 'engines' in entities else set()
    if 'formations' in entities:wanted.update(['OTTrain','OTTrailer'])
    selected=[obj for obj in objects if w.kind(obj) in wanted]
    if len(selected)>20000:raise APIError('GENERATION_SIZE','At most 20000 stock/diagram objects can be migrated in one operation.')
    for obj in selected:
        kind=w.kind(obj)
        if kind=='OTTrailer':continue
        changed={'OTEngine':upgrade_engine,'OTDDiagram':upgrade_diagram,'OTTrain':upgrade_train}[kind](obj,factory)
        if changed:counts[kind]+=1
    if 'formations' in entities:
        from .native_records import upgrade_records
        for root in roots:counts['OTTrailer']+=upgrade_records(root,'OTTrailer')
    return {kind:value for kind,value in counts.items() if value}


def decoded_copy(obj):
    result=copy.deepcopy(obj);kind=w.kind(result)
    migrate([result],('engines',) if kind in ['OTEngine','OTDDiagram'] else ('formations',))
    return result
