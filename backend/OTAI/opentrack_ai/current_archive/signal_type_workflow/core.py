"""Finite current Signal11 stored profiles. Pure bytes; no runtime equivalence."""
import hashlib
from opentrack_ai.current_archive import writer as w, path_functions as f, route_factory as rf
from opentrack_ai.current_archive.zero_generation import native_signal_routes as n
from opentrack_ai.current_archive.graph_references import incoming
require=rf.require
TYPES={'main':1,'main_distant':2,'distant':3,'shunting':4,'stop_head':6,'stop_center':21,'stop_tail':20,'main_two_aspect':24,'main_distant_three_aspect':25,'main_distant_four_aspect':26,'distant_two_aspect':27}
for code,meters in [(28,10),(29,20),(30,30),(31,40),(32,50),(33,60),(34,70),(35,80),(36,90),(8,100),(9,200),(10,300),(11,400),(16,500),(17,600),(18,700),(19,800),(37,900),(38,1000)]:TYPES['stop_length_'+str(meters)+'m']=code
MAIN={1,2,24,25,26};COMBINED={2,25,26};ROLES={'home':2,'block':3,'exit':4}
def sha(b):return hashlib.sha256(b).hexdigest()
def strict(d,keys):require(type(d)is dict and set(d)==set(keys),'Exact configuration fields required: '+','.join(keys))
def routes(root):
 for obj in w.objects(root):
  if w.kind(obj)=='OTRoute':
   nodes=f.mutable_array(obj.contents[0].value)
   rf.validate_chain(root,obj,[e.contents[0].value for e in nodes])
def load(data):
 root,v,models,ids=n.document(data);n.validate_topology(root);routes(root)
 return root,v,models,ids
def profile(root,s):
 rf.layout(s,'OTSignalModel',11,rf.SIGNAL,graphic=True)
 typ,role,location=s.contents[8].values
 require(typ in TYPES.values() and role in ROLES.values() and location==2,'Unsupported source type/role/location')
 show,sight,flags,release=s.contents[9].values
 n.integer(sight,1,100000)
 delay=s.contents[16].value
 require(isinstance(delay,(float,int)) and not isinstance(delay,bool),'Numeric stored delay required')
 n.number(float(delay),0,86400)
 require(type(s.contents[11].value)is int and s.contents[11].value in (-1,0),'Source warning outside finite profile')
 require(show==2 and release==0 and type(flags)is int and flags & ~(4|8|128|512)==0,'Only show2/default inactive auxiliary flags/release0 supported')
 require(s.contents[6].value is None and s.contents[12].value==7,'Static dispatch7 profile required')
 require(not f.mutable_array(s.contents[14].value) and not f.mutable_array(s.contents[15].value),'Performance/coasting arrays outside finite domain')
 inds=rf.wrapper(s.contents[10].value,'OTSigIndList')
 require(len(inds)==1 and inds[0].contents[0].value==0 and inds[0].contents[1].value is s.contents[7].value,'Single track-speed indication required')
 require(incoming(root,s)==2,'Unknown signal observer/alias')
 return typ,role

def preview(data,configuration):
 require(type(data)is bytes and type(configuration)is dict,'Bytes and object required')
 if configuration.get('action') in ('inspect_local','configure_local'):
  from .local_core import preview as local_preview
  return local_preview(data,configuration)
 action=configuration.get('action');root,v,models,ids=load(data)
 if action=='inspect':
  strict(configuration,['action']);return data,{'input_sha256':sha(data),'output_sha256':sha(data),'action':action,'catalog':TYPES,'main_roles':ROLES,'signals':[{'model_id':s.contents[0].value,'type_role_location':list(s.contents[8].values),'show_sight_flags_release':list(s.contents[9].values),'warning_speed_kmh':s.contents[11].value} for s in models if w.kind(s)=='OTSignalModel'],'limitations':['Catalog is finite, not all native signal types. Stop-length names are native labels in metres, not verified train stopping behavior.']}
 require(action in ('configure','create'),'Unknown action')
 base=['action','signal_type','main_role','warning_speed_kmh']
 if action=='configure':strict(configuration,base+['signal_id'])
 else:strict(configuration,base+['creation'])
 name=configuration['signal_type'];require(type(name)is str and name in TYPES,'Named supported signal type required');typ=TYPES[name]
 role=configuration['main_role'];require(type(role)is str and role in ROLES,'Named main role required')
 warning=configuration['warning_speed_kmh']
 if typ in COMBINED:require(type(warning)is int and warning in (-1,0),'Only sample-evidenced warning values -1 or 0 supported')
 else:require(warning is None,'Warning speed only applicable to combined signals; use null to preserve')
 initial=data;creation_receipt=None
 if action=='create':
  c=configuration['creation'];strict(c,['end_id','name','model_id','placement','sight_m','delay_s','show_symbol','show_icon'])
  n.integer(c['end_id']);end=ids.get(c['end_id']);require(end is not None and w.kind(end)=='OTEndModel','Current End required')
  for obj in w.objects(root):
   if w.kind(obj) in ('OTRoute','OTShunting'):
    require(end not in list(w.objects(obj)),'Creation on Route/Shunting-referenced End is outside finite domain')
  data,creation_receipt=n.build_main_signal(data,**c);root,v,models,ids=load(data);signal_id=c['model_id']
 else:signal_id=n.integer(configuration['signal_id'])
 s=ids.get(signal_id);require(s is not None and w.kind(s)=='OTSignalModel','Current signal ID required')
 oldtype,oldrole=profile(root,s);end=s.contents[7].value
 
 for obj in w.objects(root):
  if w.kind(obj)=='OTShunting' and oldtype!=typ:require(end not in list(w.objects(obj)),'Shunting-referenced signal type transition unsupported')
  if w.kind(obj)=='OTRoute':
   nodes=f.mutable_array(obj.contents[0].value)
   if end in (nodes[0],nodes[-1]):require(typ in MAIN,'Route endpoint cannot become non-route signal')
   if end in nodes[1:-1]:require(typ not in MAIN,'Route interior cannot become route signal')
 require(typ in MAIN or role==next(k for k,val in ROLES.items() if val==oldrole),'Non-main role must preserve stored role')
 before8=list(s.contents[8].values);before11=s.contents[11].value
 s.contents[8].values[:]=[typ,ROLES[role],2]
 if typ in COMBINED:s.contents[11].value=warning
 n.validate_topology(root);routes(root);output=w.dump_verified(root,v)
 check,cv,cm,ci=load(output);saved=ci[signal_id];profile(check,saved)
 require(saved.contents[8].values==s.contents[8].values and saved.contents[11].value==s.contents[11].value,'Readback mismatch')
 saved.contents[8].values[:]=before8;saved.contents[11].value=before11
 original,ov=w.load(data);require(w.dump_verified(check,cv)==w.dump_verified(original,ov),'Untargeted archive graph changed')
 receipt={'action':action,'input_sha256':sha(initial),'output_sha256':sha(output),'signal_id':signal_id,'signal_type':name,'type_code':typ,'main_role':role,'warning_speed_kmh':s.contents[11].value,'preserved':['End and indication references','showType2 and code0 indication','flags/release/dispatch','performance/coasting arrays','all other archived fields'],'evidence':'Original Signal11 coder and Inspector/static PE labels; current sample profiles 1/4,2/2,25/3. Other finite profiles lack current native golden/runtime validation.','limitations':['Stored configuration only, not complete signal system or train stopping/safety behavior.','Native setter graphic refresh is not reproduced.','Unknown observers, showType transitions, nondefault auxiliary profiles and dependent Route/Shunting changes rejected.','No native runtime, GUI, save or publication.']}
 if creation_receipt:receipt['creation']=creation_receipt
 return output,receipt
