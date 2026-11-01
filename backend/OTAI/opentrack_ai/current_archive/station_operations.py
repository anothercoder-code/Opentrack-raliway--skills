"""Current OTStation v3 archive setters, not simulation or cross-catalog rename.

The caller owns source SHA verification and atomic fresh-copy publication. This
module never touches files. Evidence/contracts accompany this integration unit.
"""
from . import writer as w, catalogs as c

class StationError(ValueError):
    pass

FIELDS = {
    'display_name': (2, 0, '0x664170'),
    'altitude_raw': (3, 0, '0x6641e8'),
    'coord_x_raw': (5, 0, '0x664258'),
    'coord_y_raw': (5, 1, '0x664274'),
    'timing_point': (7, 0, '0x66429c'),
}

def _integer(value, lo=-(2**31), hi=2**31-1):
    if type(value) is not int or not lo <= value <= hi:
        raise StationError('Exact native integer required; no float/bool/string coercion')
    return value

def _children(value):
    if isinstance(value, w.GenericArchivedObject):
        return [v for g in value.contents for v in g.values]
    if isinstance(value, w.Array):
        return [] if isinstance(value.elements, bytes) else list(value.elements)
    if isinstance(value, w.GenericStruct):
        return list(value.fields)
    if isinstance(value, (list, tuple)):
        return list(value)
    return []

def _graph(root):
    from .graph_references import reference_inventory
    return reference_inventory(root)

def _snapshot(root):
    def value(v):
        if isinstance(v,w.GenericArchivedObject):return ('object',id(v))
        if isinstance(v,w.WireFloat):return ('floatbits',v.encoding,v.bits,v.byte_order)
        if isinstance(v,w.Array):return ('array',v.elements if isinstance(v.elements,bytes) else tuple(value(x) for x in v.elements))
        if isinstance(v,w.GenericStruct):return ('struct',v.name,tuple(value(x) for x in v.fields))
        if isinstance(v,w.SharedString):return ('sharedstring',v.data)
        if isinstance(v,w.CString):return ('cstring',v.token.data)
        if isinstance(v,(list,tuple)):return (type(v).__name__,tuple(value(x) for x in v))
        return (type(v).__name__,repr(v))
    return {(id(o),i,j):(g.encodings[j],value(v)) for o in _graph(root)[0]
            for i,g in enumerate(o.contents) for j,v in enumerate(g.values)}

def _state(blob, station_sign):
    if type(blob) is not bytes:raise StationError('Immutable bytes required')
    if type(station_sign) is not str or not station_sign:raise StationError('Exact nonempty Station dictionary key required')
    root,version=w.load_next_compatible(blob)
    stations=c.station_items(root)
    if station_sign not in stations:raise StationError('Station dictionary key not found')
    selected=stations[station_sign]
    _,incoming=_graph(root)
    if incoming.get(id(root),0)!=0 or incoming.get(id(selected),0)!=1:
        raise StationError('Shared Station or parent dictionary: independent edit refused')
    for station in stations.values():
        if station.contents[0].value!=17:raise StationError('Only current encoder marker 17 is supported')
        for g in (3,4,5,7):
            for value in station.contents[g].values:_integer(value)
        for g in (2,6,8,9):
            if station.contents[g].value is not None:c.text(station.contents[g].value)
    return root,version,selected

def patch_station_archive(blob, station_sign, changes):
    """Patch only supplied fields. display_name=None encodes native nil.

    Coordinates and altitude are raw int32, units unproven by setters/coder.
    timing_point accepts bool or exact signed char; coder stores nonzero as 1.
    No stationSign, dictionary-key, IDs, district or line-reference changes.
    """
    if type(changes) is not dict or not changes or any(k not in FIELDS for k in changes):
        raise StationError('Nonempty known Station field changes required')
    normalized={}
    for field,value in changes.items():
        if field=='display_name':
            if value is not None:
                if type(value) is not str:raise StationError('Display name requires string or native nil')
                try:value.encode('utf-8')
                except UnicodeError as e:raise StationError('Display name must be valid Unicode') from e
            normalized[field]=value
        elif field=='timing_point':
            raw=int(value) if type(value) is bool else _integer(value,-128,127)
            normalized[field]=int(raw!=0)
        else:normalized[field]=_integer(value)
    root,version,selected=_state(blob,station_sign)
    before=_snapshot(root); allowed=set(); report=[]
    for field,value in normalized.items():
        group,slot,address=FIELDS[field]
        old=selected.contents[group].values[slot]
        if field=='display_name':
            old=None if old is None else c.text(old)
            
            obj=None if value is None else w.GenericArchivedObject(
                w.Class(b'NSString',1,w.Class(b'NSObject',0)),None,
                [w.TypedValue(b'+',value.encode('utf-8'))])
            selected.contents[group].values[slot]=obj
        else:selected.contents[group].values[slot]=value
        allowed.add((id(selected),group,slot))
        report.append({'field':field,'setter':address,'before':old,'input':changes[field],'stored':value})
    after=_snapshot(root); live={id(o) for o in _graph(root)[0]}
    for key,value in before.items():
        if key[0] in live and key not in allowed and after.get(key)!=value:
            raise StationError('Unrelated field/reference changed')
    output=w.dump_verified(root,version)
    fresh,_=w.load_next_compatible(output)
    if w.fingerprint(fresh)!=w.fingerprint(root):raise StationError('Fresh archive graph mismatch')
    return output,{'operation':'patch_station','station_sign':station_sign,'changes':report,
        'fresh_reload_verified':True,'unrelated_fields_and_references_preserved':True,
        'station_identity_unchanged':True,'coordinate_and_altitude_units':'raw_native_integers_unverified_units',
        'native_application_tested':False,'simulation_tested':False}
