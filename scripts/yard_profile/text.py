"""Bounded ASCII yard labels cloned from an actual OTLabelModel1 golden.

There is no evidenced OTTextModel archive class in this profile. The actual
Header contains OTLabelModel1 -> OTGraphicModel1 -> NSObject0 with NSData RTF,
creationRect, nil owner, justification1/labelType0/flags0 and black/white colors.
Only its ID, loc, explicit frame and existing RTF body text change. No I/O/GUI.
"""
from __future__ import annotations

import copy
import hashlib
import math
import re
import struct

from opentrack_ai.current_archive import writer as w, route_factory as rf, catalogs as c

GOLDEN_HEADER_SHA256 = '8323d7f1486c1754c5a1d320ba10e27fe2bfa57cf394cb3753f30742a67d4de6'
GOLDEN_LABEL_ID = 221
GOLDEN_RTF_SHA256 = '56306d8e072ab3fd09fbebd13080e4d83fbe33a4503d8f08ee5a720795754750'
STOCK_EXE_SHA256 = 'f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104'
SOURCE_BANK = '20261027-bank-v027-timetable-export'
SOURCE_SHA256 = {
 'modules/02_infrastructure/classes/OTLabelModel/metadata.json': 'c6a3e2656e51070595645d79e19500499360c85f794fc583070f5664f39ae38d',
 'modules/02_infrastructure/classes/OTLabelModel/functions/00516280.c': 'bd8f9d9c91c9b9525c78acfc5810368021ed5173af35d277f037fac630fd03a6',
 'modules/02_infrastructure/classes/OTLabelModel/functions/00517120.c': 'aff1bdab89bdbbb1c5f7df5256105cdd1ab33dc7335208cdfc2a7bc74a180b38',
 'modules/02_infrastructure/classes/OTLabelModel/functions/00516e30.c': '635c83ec93e6f4d75ac0147b31e3d33aecb872d5c382fe776ff78be046c9bfb9',
 'modules/03_canvas/classes/OTLabelView/metadata.json': '061d330efdf283a5ccf7d3bdc1b865e2a6d461364d5f13c66a5ccc31a12e7cd9',
 'modules/03_canvas/classes/OTLabelView/functions/005177e4.c': '290b14ef3188063d3882879f380d563cbc7ea8a74d398da53b23d588505d0efb',
}
CHAIN = [('OTLabelModel',1),('OTGraphicModel',1),('NSObject',0)]
ENCODINGS = ['i','f','f','f','i','i','@','@','ffff','@','iii','@','@']
GOLDEN_RTF = (b'{\\rtf0\\ansi{\\fonttbl\\f0\\fswiss Helvetica;}\n'
 b'\\pard\\tx560\\tx1120\\tx1680\\tx2240\\tx2800\\tx3360\\tx3920\\tx4480'
 b'\\tx5040\\tx5600\\tx6160\\tx6720\\ql\\qnatural\n\n\\f0\\fs24 \\cf0 \x08\x08Beijing}\n')
RTF_PREFIX, RTF_SUFFIX = GOLDEN_RTF.split(b'Beijing')
YARD_STATIC_TEXT = tuple('Track '+d+str(i) for d in ('D','U') for i in range(1,5)) + \
                   tuple('Platform P'+str(i) for i in range(1,5)) + ('Up Main','Down Main')


class YardTextError(ValueError):pass


def need(ok,message):
    if not ok:raise YardTextError(message)


def sha(blob):return hashlib.sha256(blob).hexdigest()


def _chain(obj):
    out=[];cl=obj.clazz
    while cl is not None:
        out.append((cl.name.decode('ascii'),cl.version));cl=cl.superclass
    return out


def _enc(obj):return [''.join(e.decode('ascii') for e in g.encodings) for g in obj.contents]


def _f32(value):
    need(type(value) in (int,float) and math.isfinite(value) and abs(value)<=1000000,
         'Finite exact drawing number within interface guard +/-1000000 required')
    return struct.unpack('<f',struct.pack('<f',value))[0]


def _text(value):
    need(type(value) is str and 1<=len(value)<=64 and value==value.strip() and
         all(32<=ord(ch)<127 and ch not in '\\{}' for ch in value),
         '1..64 printable ASCII label characters required; RTF braces/backslash and controls are refused')
    return value


def _entry(item):
    need(type(item) is dict and set(item)=={'key','text','rect'}, 'Exact key/text/rect label entry required')
    key=item['key'];need(type(key)is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,39}',key),
                         'Safe ASCII external label key required')
    text=_text(item['text']);rect=item['rect']
    need(type(rect) in (list,tuple) and len(rect)==4,'Explicit native frame x/y/width/height required')
    rect=list(map(_f32,rect))
    need(18<=rect[2]<=100000 and 27<=rect[3]<=100000,
         'Bounded explicit frame requires width18..100000 and height27..100000 for the inherited font profile')
    center=[_f32(rect[0]+rect[2]/2),_f32(rect[1]+rect[3]/2)]
    return {'key':key,'text':text,'rect':rect,'center':center}


def _read(blob):
    need(type(blob)is bytes and bool(blob),'Immutable nonempty document bytes required')
    root,version=w.load_next_compatible(blob);models,byid=rf.document(root)
    need(root.contents[0].value==17,'Current Document marker17 required')
    need(all(type(mid)is int and 0<=mid<=2147483647 for mid in byid),'Nonnegative unique local IDs required')
    need(w.dump_verified(root,version)==blob,'Canonical native bytes required for exact rollback')
    return root,version,models,byid


def _data(obj):
    need(_chain(obj)==[('NSMutableData',0),('NSData',0),('NSObject',0)] and len(obj.contents)==2,
         'Observed NSMutableData0/NSData0 native RTF container required')
    length=obj.contents[0].value
    need(obj.contents[0].encodings==[b'i'] and type(length)is int and 1<=length<=1024,
         'Bounded native data byte count required')
    need(obj.contents[1].encodings==[('['+str(length)+'c]').encode('ascii')] and
         isinstance(obj.contents[1].value,w.Array) and type(obj.contents[1].value.elements)is bytes,
         'Native counted char array layout required')
    raw=obj.contents[1].value.elements
    need(len(raw)==length,'RTF byte count differs')
    return raw


def _color(obj,white):
    need(_chain(obj)==[('NSColor',0),('NSObject',0)] and _enc(obj)==['c','ff'] and
         obj.contents[0].value==3 and obj.contents[1].values==[white,1],
         'Exact observed opaque black/white native color required')


def _inspect(model,entry,mid):
    need(_chain(model)==CHAIN and _enc(model)==ENCODINGS and
         all(len(g.encodings)==len(g.values) for g in model.contents),'Exact OTLabelModel1 golden layout required')
    need(model.contents[0].value==mid and model.contents[1].value==0 and
         [model.contents[i].value for i in (2,3)]==entry['center'] and
         [model.contents[i].value for i in (4,5)]==[0,0], 'Label ID/angle/loc/alignment differs')
    need(model.contents[6].value is None and model.contents[9].value is None and
         model.contents[10].values==[1,0,0], 'Only nil-owner standalone non-simulation label profile supported')
    need(list(model.contents[8].values)==entry['rect'],'Saved native creationRect differs')
    _color(model.contents[11].value,0);_color(model.contents[12].value,1)
    need(_data(model.contents[7].value)==RTF_PREFIX+entry['text'].encode('ascii')+RTF_SUFFIX,
         'Label is outside the exact inherited RTF font/body profile')
    return {'model_id':mid,**entry,'native_class':'OTLabelModel','business_object_attachment':False}


def _template(blob):
    need(type(blob)is bytes and sha(blob)==GOLDEN_HEADER_SHA256,'Exact SHA-bound Header golden required')
    root,version,models,byid=_read(blob)
    label=byid.get(GOLDEN_LABEL_ID)
    need(label is not None and _data(label.contents[7].value)==GOLDEN_RTF and
         sha(GOLDEN_RTF)==GOLDEN_RTF_SHA256,'Observed Header label RTF must match the native golden')
    _inspect(label,_entry({'key':'golden','text':'Beijing','rect':list(map(float,label.contents[8].values))}),GOLDEN_LABEL_ID)
    return label


def validate_labels(blob,receipt):
    need(type(receipt)is dict and receipt.get('schema')=='yard-native-labels/1' and
         sha(blob)==receipt.get('output_sha256'),'Label receipt must bind these exact immutable bytes')
    root,version,models,byid=_read(blob)
    entries=receipt['entries'];ids=receipt['new_model_ids']
    need(type(entries)is list and 1<=len(entries)<=160 and type(ids)is list and len(ids)==len(entries),
         'Bounded exact label entries and IDs required')
    need(ids==list(range(ids[0],ids[0]+len(ids))) and
         [m.contents[0].value for m in models[-len(ids):]]==ids,'New Labels must be the contiguous model-array suffix')
    rows=[]
    for item,mid in zip(entries,ids):
        entry=_entry({k:item[k] for k in ('key','text','rect')})
        need(item==entry,'Receipt placement is not canonical float32')
        rows.append(_inspect(byid[mid],entry,mid))
    need({id(o) for o in w.objects(root) if w.kind(o)=='OTLabelModel' and o.contents[0].value in ids}==
         {id(byid[mid]) for mid in ids},'Hidden or aliased new native Label refused')
    return {'passed':True,'count':len(rows),'labels':rows,'native_application_executed':False,
            'font_fitting_and_visibility_runtime_verified':False,'saved':False}


def strip_labels(blob,receipt):
    validation=validate_labels(blob,receipt)
    root,version,models,byid=_read(blob);count=len(receipt['new_model_ids'])
    array=root.contents[2].value
    array.contents=array.contents[:-count];array.contents[0].value=len(models)-count
    output=w.dump_verified(root,version)
    need(sha(output)==receipt['input_sha256'],'Stripping only new labels did not exactly restore input bytes')
    return output,{'passed':True,'removed_ids':receipt['new_model_ids'],
        'output_sha256':sha(output),'exact_input_bytes_restored':True,'label_validation':validation}


def add_labels(document,entries,*,template_document):
    need(type(entries)is list and 1<=len(entries)<=160,'Explicit 1..160 label entries required')
    normalized=[_entry(item) for item in entries]
    need(len({e['key'] for e in normalized})==len(normalized),'External label keys must be unique')
    template=_template(template_document)
    root,version,models,byid=_read(document);start=max(byid,default=-1)+1
    need(start+len(entries)-1<=2147483647,'Fresh model ID range exhausted')
    added=[]
    for index,entry in enumerate(normalized):
        model=copy.deepcopy(template);model.contents[0].value=start+index
        model.contents[2].value,model.contents[3].value=entry['center']
        model.contents[8].values=list(entry['rect'])
        payload=RTF_PREFIX+entry['text'].encode('ascii')+RTF_SUFFIX
        data=model.contents[7].value
        data.contents[0].value=len(payload)
        data.contents[1]=w.TypedGroup([('['+str(len(payload))+'c]').encode('ascii')],[w.Array(payload)])
        _inspect(model,entry,start+index);added.append(model)
    array=root.contents[2].value
    
    
    array.contents[0].value=len(models)+len(added)
    array.contents.extend(w.TypedGroup([b'@'],[model]) for model in added)
    output=w.dump_verified(root,version)
    receipt={'schema':'yard-native-labels/1','input_sha256':sha(document),'output_sha256':sha(output),
        'template_header_sha256':sha(template_document),'template_label_id':GOLDEN_LABEL_ID,
        'new_model_ids':list(range(start,start+len(added))),'entries':normalized,
        'source_bank':SOURCE_BANK,'source_sha256':copy.deepcopy(SOURCE_SHA256),
        'stock_executable_sha256':STOCK_EXE_SHA256,'rtf_golden_sha256':GOLDEN_RTF_SHA256,
        'native_class':'OTLabelModel','native_application_executed':False,'saved':False,
        'runtime_visibility_verified':False,'text_is_ascii':True,'inherited_font':'Helvetica12',
        'draws_background':False,'simulation_labels':False,'native_class_fields_invented':False}
    receipt['validation']=validate_labels(output,receipt)
    restored,rollback=strip_labels(output,receipt)
    need(restored==document,'Exact add/strip byte rollback failed')
    receipt['exact_add_strip_rollback_verified']=True
    return output,receipt


def strip_yard_labels(blob):
    """Strict no-receipt business projection for a complete new yard label set.

    Zero labels are unchanged. Otherwise exactly15 reviewed Labels must form a
    model suffix: actual Station sign/title, eight Track labels, four Platform
    labels and two Main labels. This does not remove rectangle graphics.
    """
    root,version,models,byid=_read(blob)
    labels=[m for m in models if w.kind(m)=='OTLabelModel']
    if not labels:return blob,{'passed':True,'count':0,'labels_absent':True,'exact_reappend_rollback_verified':True}
    need(len(labels)==15,'Only the complete15-label yard drawing profile can be projected')
    stations=[m for m in models if w.kind(m)=='OTStationModel']
    need(len(stations)==1,'Yard label projection requires exactly one actual StationModel')
    sign=c.text(stations[0].contents[7].value)
    items=[];texts=[];ids=[m.contents[0].value for m in labels]
    for index,model in enumerate(labels):
        payload=_data(model.contents[7].value)
        need(payload.startswith(RTF_PREFIX) and payload.endswith(RTF_SUFFIX),'Unknown yard label rich text refused')
        text=payload[len(RTF_PREFIX):-len(RTF_SUFFIX)].decode('ascii')
        entry=_entry({'key':'label'+str(index),'text':text,'rect':list(map(float,model.contents[8].values))})
        _inspect(model,entry,ids[index]);items.append(entry);texts.append(text)
    need(len(set(texts))==15 and set(YARD_STATIC_TEXT)<=set(texts) and
         list(set(texts)-set(YARD_STATIC_TEXT)) in ([sign],[sign.title()]),
         'Yard text set must exactly label this actual station,8tracks,4platforms and2mains')
    need(models[-15:]==labels and ids==list(range(ids[0],ids[0]+15)),
         'Yard label IDs and objects must form the contiguous drawing suffix')
    need({id(o) for o in w.objects(root) if w.kind(o)=='OTLabelModel'}=={id(o) for o in labels},
         'Hidden yard Label objects refused')
    array=root.contents[2].value
    array.contents=array.contents[:-15];array.contents[0].value=len(models)-15
    output=w.dump_verified(root,version)
    
    
    check,cv,cm,ci=_read(output);ca=check.contents[2].value
    ca.contents[0].value=len(cm)+15
    ca.contents.extend(w.TypedGroup([b'@'],[copy.deepcopy(model)]) for model in labels)
    need(w.dump_verified(check,cv)==blob,'Yard label projection failed exact reappend rollback')
    return output,{'passed':True,'count':15,'removed_ids':ids,'texts':texts,
        'exact_reappend_rollback_verified':True,'native_application_executed':False}
