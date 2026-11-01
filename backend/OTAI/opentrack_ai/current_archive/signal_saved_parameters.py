"""Signal11 raw dispatch and four independently encoded bool parameters.

This independent domain leaves the earlier type-edit eligibility guard intact.
No operational enum, physical safety, type transition or runtime claim.
"""
from . import writer as w,path_functions as f,route_factory as rf
from .graph_references import incoming
from .zero_generation import native_signal_routes as n
from .signal_type_workflow.local_core import document as local_document,unique
from .signal_type_workflow.core import MAIN,ROLES,strict,sha
need=rf.require
BITS={'balise_release_at_balise_position':0x20,'acceleration_forbidden':0x40,'keep_closed_for_station_stop':0x100,'balise_control_all_braking_actions':0x200}
DOCUMENT4=['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@','ffff','iii','ff','@','@','@','@']
def document(data):
 root,v,models=local_document(data)
 need([b"".join(g.encodings).decode("ascii")for g in root.contents]==DOCUMENT4,'Unknown Document4 field layout')
 need(all(len(g.encodings)==len(g.values)for g in root.contents),'Malformed Document4 groups')
 return root,v,models
def i32(v):need(type(v)is int and -(2**31)<=v<2**31,'Exact signed int32 required');return v
def target(root,models,selector):
 strict(selector,['model_index','signal_id','end_id','signal_name'])
 s=models[n.integer(selector['model_index'],0,len(models)-1)]
 rf.layout(s,'OTSignalModel',11,rf.SIGNAL,graphic=True);unique(models,s)
 need(i32(selector['signal_id'])==s.contents[0].value,'Signal index/ID mismatch')
 need(type(selector['signal_name'])is str and f.string(s.contents[13].value)==selector['signal_name'],'Signal name mismatch')
 e=s.contents[7].value;rf.layout(e,'OTEndModel',7,rf.END,graphic=True);unique(models,e)
 need(i32(selector['end_id'])==e.contents[0].value and e.contents[11].value is s,'Signal/End identity mismatch')
 related=[m for m in models if m.contents[0].value==e.contents[8].value]
 need(len(related)==1 and w.kind(related[0])=='OTEndModel','Selected related End ambiguous/external/connector')
 other=related[0];rf.layout(other,'OTEndModel',7,rf.END,graphic=True)
 need(other is not e and other.contents[8].value==e.contents[0].value,'Related End is not reciprocal')
 elem=e.contents[7].value;rf.layout(elem,'OTElement',0,['i','f','f','f','i','i','@','@'],graphic=True);unique(models,elem)
 need(f.mutable_array(elem.contents[7].value).count(e)==1,'SafetyElement ownership mismatch');f.guard_counter_references(root,e)
 typ,role,location=s.contents[8].values
 need(typ in MAIN and role in ROLES.values() and location in(1,2),'Known local main-family profile required')
 show,sight,flags,release=s.contents[9].values
 need(show==2 and release==0,'Only existing show2/release0 profiles supported');i32(flags);i32(s.contents[12].value)
 n.integer(sight,1,100000);delay=s.contents[16].value
 need(type(delay)in(int,float)or isinstance(delay,w.WireFloat),'Numeric delay required');n.number(float(delay),0,86400)
 need(s.contents[11].value in(-1,0)and type(s.contents[11].value)is int,'Known warning profile required')
 need(s.contents[6].value is None,'Unknown graphic observer')
 need(not f.mutable_array(s.contents[14].value) and not f.mutable_array(s.contents[15].value),'Performance/coasting arrays outside this domain')
 inds=rf.wrapper(s.contents[10].value,'OTSigIndList');need(len(inds)==1,'One existing indication required');rf.layout(inds[0],'OTSigInd',0,['i','@'])
 need(inds[0].contents[0].value==0 and inds[0].contents[1].value is e,'Indication owner/code unsupported');need(incoming(root,s)==2,'Unknown Signal observer/alias')
 return s

def values(s):
 flags=s.contents[9].values[2]
 return {'raw_dispatch_code':s.contents[12].value,'raw_flags':flags,'bits':{k:bool(flags&mask)for k,mask in BITS.items()}}
def inspect(data,selector):
 need(type(data)is bytes,'Immutable archive bytes required');root,v,models=document(data);s=target(root,models,selector)
 return {'target':dict(selector),'values':values(s),'business_dispatch_enum_verified':False,'native_execution':False,'saved':False}
def update(data,selector,changes):
 need(type(data)is bytes and type(changes)is dict and changes and not set(changes)-({'raw_dispatch_code'}|set(BITS)),'Explicit known parameter changes required')
 for key,value in changes.items():
  if key=='raw_dispatch_code':i32(value)
  else:need(type(value)is bool,'Exact bool required')
 root,v,models=document(data);s=target(root,models,selector);before=values(s);fingerprint=w.fingerprint(root)
 for key,value in changes.items():
  if key=='raw_dispatch_code':s.contents[12].value=value
  else:
   flags=s.contents[9].values[2]&0xffffffff
   flags=(flags|BITS[key])if value else(flags&(~BITS[key]&0xffffffff))
   s.contents[9].values[2]=flags if flags<2**31 else flags-2**32
 after=values(s);output=data if after==before else w.dump_verified(root,v)
 fresh,fv,fmodels=document(output);saved=target(fresh,fmodels,selector);need(values(saved)==after,'Fresh parameter readback mismatch')
 saved.contents[12].value=before['raw_dispatch_code'];saved.contents[9].values[2]=before['raw_flags']
 need(w.fingerprint(fresh)==fingerprint,'Non-target graph/alias changed')
 changed_mask=sum(BITS[k]for k in changes if k in BITS)
 need((before['raw_flags']&~changed_mask)==(after['raw_flags']&~changed_mask),'Untargeted flag bits changed')
 return output,{'target':dict(selector),'before':before,'after':after,'changed_fields':sorted(changes),'input_sha256':sha(data),'output_sha256':sha(output),'untargeted_bits_preserved':True,'fresh_reload_verified':True,'reverse_full_graph_verified':True,'business_dispatch_enum_verified':False,'saved':False,'native_execution':False}
