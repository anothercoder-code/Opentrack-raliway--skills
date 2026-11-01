"""Local main-signal storage editing without traversing native connector closures.
Does not repair source graphs or resolve native runtime/external dependencies.
"""
from opentrack_ai.current_archive import writer as w,path_functions as f,route_factory as rf
from opentrack_ai.current_archive.graph_references import incoming
from opentrack_ai.current_archive.zero_generation import native_signal_routes as n
from .core import TYPES,MAIN,COMBINED,ROLES,strict,sha
require=rf.require

def document(data):
 root,version=w.load(data)
 f.hierarchy(root,[('OTDocument',4),('NSObject',0)])
 require(len(root.contents)==21 and root.contents[2].encodings==[b'@'],'Current document4 required')
 models=f.mutable_array(root.contents[2].value)
 require(incoming(root,root)==0 and incoming(root,root.contents[2].value)==1,'Document/model array ownership unsupported')
 require(len({id(x) for x in models})==len(models),'Repeated model object in graphicArray')
 for m in models:require(m.contents and m.contents[0].encodings==[b'i'] and type(m.contents[0].value)is int,'Model numeric identity required')
 return root,version,models

def unique(models,obj):
 require(sum(m.contents[0].value==obj.contents[0].value for m in models)==1,'Target dependency ID ambiguous under native first-match lookup')
 require(sum(m is obj for m in models)==1,'Target dependency outside graphicArray')

def target(root,models,selector):
 strict(selector,['model_index','signal_id','end_id','signal_name'])
 index=n.integer(selector['model_index'],0,len(models)-1);s=models[index]
 rf.layout(s,'OTSignalModel',11,rf.SIGNAL,graphic=True)
 require(type(selector['signal_id'])is int and s.contents[0].value==selector['signal_id'],'Signal index/ID mismatch')
 require(type(selector['signal_name'])is str and f.string(s.contents[13].value)==selector['signal_name'],'Signal name mismatch')
 unique(models,s);e=s.contents[7].value
 rf.layout(e,'OTEndModel',7,rf.END,graphic=True);unique(models,e)
 require(type(selector['end_id'])is int and e.contents[0].value==selector['end_id'] and e.contents[11].value is s,'Signal/End identity mismatch')
 
 related=[m for m in models if m.contents[0].value==e.contents[8].value]
 require(len(related)==1 and w.kind(related[0])=='OTEndModel','Selected signal related End ambiguous/external/connector')
 other=related[0];rf.layout(other,'OTEndModel',7,rf.END,graphic=True)
 require(other is not e and other.contents[8].value==e.contents[0].value,'Selected related End not reciprocal')
 elem=e.contents[7].value;rf.layout(elem,'OTElement',0,['i','f','f','f','i','i','@','@'],graphic=True)
 require(sum(m is elem for m in models)==1 and f.mutable_array(elem.contents[7].value).count(e)==1,'Target SafetyElement membership mismatch')
 f.guard_counter_references(root,e)
 typ,role,location=s.contents[8].values
 require(typ in MAIN and role in ROLES.values() and location in (1,2),'Local only main-family and observed location1/2')
 show,sight,flags,release=s.contents[9].values
 require(show==2 and release==0 and type(flags)is int and flags & ~(4|8|128|512)==0,'Only default inactive auxiliary flags/show2/release0')
 n.integer(sight,1,100000);delay=s.contents[16].value
 require(isinstance(delay,(int,float)) and not isinstance(delay,bool),'Numeric delay required');n.number(float(delay),0,86400)
 require(type(s.contents[11].value)is int and s.contents[11].value in (-1,0),'Finite source warning required')
 require(s.contents[6].value is None and s.contents[12].value==7,'Static dispatch7 required')
 require(not f.mutable_array(s.contents[14].value) and not f.mutable_array(s.contents[15].value),'Auxiliary arrays unsupported')
 inds=rf.wrapper(s.contents[10].value,'OTSigIndList')
 require(len(inds)==1,'One indication required');rf.layout(inds[0],'OTSigInd',0,['i','@'])
 require(inds[0].contents[0].value==0 and inds[0].contents[1].value is e,'Foreign indication owner/code unsupported; no repair')
 require(incoming(root,s)==2,'Unknown Signal observer')
 return s

def selector(models,index):
 s=models[index];rf.layout(s,'OTSignalModel',11,rf.SIGNAL,graphic=True)
 return {'model_index':index,'signal_id':s.contents[0].value,'end_id':s.contents[7].value.contents[0].value,'signal_name':f.string(s.contents[13].value)}

def preview(data,configuration):
 require(type(data)is bytes and type(configuration)is dict,'Bytes and configuration required')
 root,v,models=document(data);action=configuration.get('action')
 if action=='inspect_local':
  strict(configuration,['action']);items=[]
  for i,s in enumerate(models):
   if w.kind(s)!='OTSignalModel':continue
   row={'model_index':i}
   try:
    row['target']=selector(models,i);target(root,models,row['target']);row['eligible']=True
   except (ValueError,TypeError,KeyError,IndexError)as exc:row.update(eligible=False,reason=str(exc))
   items.append(row)
  return data,{'action':action,'input_sha256':sha(data),'output_sha256':sha(data),'signals':items,'namespace':'source SHA and graphicArray index with explicit Signal/End IDs/name','whole_project_validated':False,'external_connections_resolved':False}
 strict(configuration,['action','target','signal_type','main_role','warning_speed_kmh']);require(action=='configure_local','Unknown local action')
 s=target(root,models,configuration['target']);name=configuration['signal_type'];role=configuration['main_role'];warning=configuration['warning_speed_kmh']
 require(type(name)is str and name in TYPES and TYPES[name] in MAIN,'Local configuration must preserve main/route-signal classification')
 require(type(role)is str and role in ROLES,'Named main role required')
 if TYPES[name] in COMBINED:require(type(warning)is int and warning in (-1,0),'Combined warning must be -1 or0')
 else:require(warning is None,'Noncombined warning must be null to preserve')
 old8=list(s.contents[8].values);old11=s.contents[11].value
 s.contents[8].values[:2]=[TYPES[name],ROLES[role]]
 if TYPES[name] in COMBINED:s.contents[11].value=warning
 expected8=list(s.contents[8].values);expected11=s.contents[11].value
 output=data if expected8==old8 and expected11==old11 else w.dump_verified(root,v);check,cv,cm=document(output);saved=target(check,cm,configuration['target'])
 require(saved.contents[8].values==expected8 and saved.contents[11].value==expected11,'Local signal readback mismatch')
 saved.contents[8].values[:]=old8;saved.contents[11].value=old11
 original,ov=w.load(data);require(w.dump_verified(check,cv)==w.dump_verified(original,ov),'Non-target full graph/alias changes')
 return output,{'action':action,'input_sha256':sha(data),'output_sha256':sha(output),'target':configuration['target'],'before_type_role_location':old8,'after_type_role_location':expected8,'before_warning_speed_kmh':old11,'after_warning_speed_kmh':expected11,'whole_project_validated':False,'external_connections_resolved':False,'native_runtime_ready':False,'preserved':'all other serialized fields and graph aliases, including external connection metadata; reverse full-graph check','limitations':['Main-family local field update only; no type-class transition/show/indication/route-cleanup side effects.','Unrelated archive topology and external dependencies retained, not validated or repaired.','Selected identity and known observers checked; duplicate target dependency IDs or foreign indication owner reject.','No native runtime, GUI refresh, save or publication.']}
