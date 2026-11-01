"""Current-only Engine batch, static factors of original StockOperations.
No runtime source evaluation, migration, factory, Project or graph dependency.
Original update algorithm preserved except deepcopy(old) -> certified shallow
clone(old), keeping untouched child object identities and shared references.
edit_engines is the original scalar/flag prefix with the explicit allowlist.
Engine record is the allowlisted readback projection of original current branch.
Full current Engine layout is validated independently by certified accessors.
"""
import math
from types import SimpleNamespace
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.course_factories import clone
from opentrack_ai.current_archive.graph_references import reference_inventory
from opentrack_ai.errors import APIError


SOURCE_FINGERPRINTS = {'stock_maintenance.py': {'sha256': '57c8559ce37802dec2d1e40721a7a99e7dd3a12b4dfc600034e446962917ceba', 'definitions': {'select': '8c48ad1dbff4a90eab7091e72097bfc707d390f2a053c23af9377c507070d175', 'update': 'cb53da49498ccfec9585a343363c5d6b6355f785f8d1457bfe4e891e36735b5f', 'edit_engines': '78743bb57a20d8256f33d4e0e8861ef682ff712c4beadae03684907abade42ce'}}, 'rolling_stock.py': {'sha256': 'f86222744472ef18ba543553ccd4f7840fe6904349fc6c63bb623720bf45e8eb', 'definitions': {'set_scalars': '0d1b4461507ab592d5ff1c5a5ea2f1cae741fa08e9cfa1c2140fa4f1440b7ac9', 'engine_record': '6c3db128dcd1cc2315b27a492e8df841522ce66275d5cc8026c25e53a03c8bd7'}}, '006df3e8_OTVehicle____instance__setVehicleCwValue___6df3e8.c': {'sha256': 'd00df09d5e9527941d48122ec40fb144f3d1ca220f38c6165bfb9ef2f531611f'}, '004cbe60_OTEngine____instance__setUnderstandsRadioTelegram___4cbe60.c': {'sha256': '3df69c11b4658688b0ae5fa21e287ca2c94959857a8242dbd5173ede8cf032bf'}}

ALLOWED_FIELDS = frozenset({"cw_value", "understands_radio"})
CONTRACT = {
    'cw_value': {'group':2,'slot':5,'encoding':'f','unit':'raw saved cw coefficient; no conversion',
                 'api_domain':'finite numeric 0..100; bool forbidden',
                 'native_setter':'0x006df3e8',
                 'c_api_difference':'Native selector takes int32 then casts to float; batch API accepts floats; not equivalent'},
    'understands_radio': {'group':11,'slot':0,'mask':4,'encoding':'i',
                          'api_domain':'strict bool','native_setter':'0x004cbe60',
                          'c_api_difference':'Native char ivar is represented by current archive flag bit 4'},
    'cstring': 'No b* constructor or systems/diagram replacement is reachable; byte-string mismatch not silently adapted',
    'reuse': 'Original select/update planned-copy/replace/diff; deepcopy replaced with certified shallow clone; scalar and flag prefix factored',
}


ENGINE_FLAGS = {"understands_radio":4}

def string_slot(obj,index): return c.text(obj.contents[index].value)

def put(obj,index,value): obj.contents[index].values[0]=value

def difference(before,after): return {key:{"before":before.get(key),"after":value} for key,value in after.items() if before.get(key)!=value}

def set_scalars(obj, args, mapping):
    for field, (index, slot) in mapping.items():
        value = getattr(args, field)
        if value is None:
            continue
        if index >= len(obj.contents):
            raise APIError('ROLLING_STOCK_VERSION', 'Selected record version lacks this field; use a compatible template or an audited migration.', {'class': w.kind(obj), 'field': field, 'version': obj.clazz.version})
        obj.contents[index].values[slot] = value

def engine_record(obj):
    c.record(obj,'OTEngine')
    return {'name':c.text(obj.contents[1].value), 'cw_value':obj.contents[2].values[5], 'understands_radio':bool(obj.contents[11].value&4)}
RECORDS={'engines':engine_record}


class StockOperations:
    def __init__(self, operations): self.o=operations; self.p=operations.p
    def array(self, entity):
        if entity != "engines": raise ValueError("Engine-only scope")
        return self.p.data["depot"],1
    def select(self, entity, names, count=True):
        if len(names) != len(set(names)):
            raise APIError('DUPLICATE_STOCK_NAME', 'Selection contains duplicate names.')
        array, index = self.array(entity)
        items = w.elements(array)
        lookup = {string_slot(obj, index): obj for obj in items}
        if len(lookup) != len(items):
            raise APIError('DUPLICATE_STOCK_NAME', 'Existing native names are ambiguous.', entity)
        missing = [name for name in names if name not in lookup]
        if missing:
            raise APIError('STOCK_NOT_FOUND', 'Selected exact native names do not exist.', {'entity': entity, 'names': missing})
        if count:
            self.o.stock_update_targets += len(names)
        if self.o.stock_update_targets > 10000:
            raise APIError('GENERATION_SIZE', 'One draft supports at most 10000 rolling-stock edit targets, including cascades.')
        return (array, index, lookup)
    
    def update(self, entity, args):
        array, index, lookup = self.select(entity, args.names)
        changes = []
        planned = []
        for name in args.names:
            old = lookup[name]
            obj = clone(old)
            before = RECORDS[entity](old)
            getattr(self, 'edit_' + entity)(obj, args)
            after = RECORDS[entity](obj)
            if entity == 'engines' and (args.traction_points is not None or args.nominal_power_kw is not None or args.tractive_effort_diagrams is not None):
                before = engine_record(old, True)
                after = engine_record(obj, True)
            planned.append((old, obj))
            changes.append({'entity': entity, 'name': name, 'fields': difference(before, after)})
        replacements = {id(old): obj for old, obj in planned}
        w.set_elements(array, [replacements.get(id(obj), obj) for obj in w.elements(array)])
        return {'entity': entity, 'names': args.names, 'records_updated': len(changes), 'records_changed': sum((bool(c['fields']) for c in changes)), 'stock_changes': changes}
    def edit_engines(self,obj,args):
        set_scalars(obj,args,{'cw_value':(2,5)})
        for field,bit in ENGINE_FLAGS.items():
            value=getattr(args,field)
            if value is not None:put(obj,11,obj.contents[11].value|bit if value else obj.contents[11].value&~bit)


def validate_spec(spec):
    if type(spec) is not dict or set(spec)-({'kind','names'}|ALLOWED_FIELDS):
        raise ValueError('Unknown Engine batch parameter')
    if spec.get('kind')!='update_engines':raise ValueError('Expected update_engines')
    names=spec.get('names')
    if type(names) is not list or not names or len(names)>10000 or any(type(n) is not str or not n or '\0' in n for n in names):
        raise ValueError('Expected 1..10000 exact nonempty NUL-free Engine names')
    if len(names)!=len(set(names)):raise ValueError('Repeated Engine name')
    if not ALLOWED_FIELDS.intersection(spec):raise ValueError('Explicit Engine field required')
    if 'cw_value' in spec:
        value=spec['cw_value']
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100:
            raise ValueError('cw_value requires finite original API numeric range 0..100; not C int-setter equivalence')
    if 'understands_radio' in spec and type(spec['understands_radio']) is not bool:
        raise ValueError('understands_radio requires explicit bool')
    return spec

def apply(context,spec):
    """Mutate private context.data['depot']; caller owns atomic bytes transaction.

    Required real data: depot and trains. No docs/corridors or graph access.
    Returns original update-style compact diff. Unknown fields/null/coercion fail.
    cw_value follows original batch API 0..100 float domain, deliberately NOT
    the native setVehicleCwValue: int32 setter domain (explicit API difference).
    """
    validate_spec(spec)
    root=context.data['depot'];engines=c.engine_items(root)
    known={c.text(e.contents[1].value):e for e in engines}
    if set(spec['names'])-set(known):raise ValueError('Unknown exact Engine name')
    for train in c.train_items(context.data['trains']):
        if set(c.bound_engine_names(train))-set(known):raise ValueError('Formation references missing Engine name')
    _,counts=reference_inventory(root)
    if counts[id(root)]!=0:raise ValueError('Shared depot root')
    for name in spec['names']:
        if counts[id(known[name])]!=1:raise ValueError('Shared selected Engine')
    args=SimpleNamespace(names=list(spec['names']),cw_value=spec.get('cw_value'),understands_radio=spec.get('understands_radio'),traction_points=None,nominal_power_kw=None,tractive_effort_diagrams=None)
    operation=SimpleNamespace(p=context,stock_update_targets=getattr(context,'stock_update_targets',0))
    result=StockOperations(operation).update('engines',args)
    context.stock_update_targets=operation.stock_update_targets
    return result

