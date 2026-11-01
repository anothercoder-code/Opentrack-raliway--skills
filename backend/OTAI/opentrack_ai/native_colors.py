"""Audited NSColor v0 archive payloads; preserve unknown native spaces."""
import copy
import math
from .archive import APIError,w


def color_record(value):
 if value is None:return None
 version=value.clazz.version;tag=value.contents[0].value if value.contents else None
 if w.kind(value)=='NSColor' and version==0 and len(value.contents)==2:
  group=value.contents[1]
  if tag==1 and group.encodings==[b'f']*4 and len(group.values)==4 and all(math.isfinite(x) for x in group.values):
   return dict(space='calibrated_rgb',**dict(zip(['red','green','blue','alpha'],group.values)))
  if tag==3 and group.encodings==[b'f']*2 and len(group.values)==2 and all(math.isfinite(x) for x in group.values):return dict(space='calibrated_white',white=group.values[0],alpha=group.values[1])
 return {'space':'unsupported_native','native_class':w.kind(value),'class_version':version,'native_tag':tag,'writable':False}


def make_color(definitions,args):
 color=copy.deepcopy(definitions.template('NSColor'))
 if color.clazz.version!=0:raise APIError('COLOR_VERSION','Only the audited NSColor v0 representation is writable.')
 if args.space=='calibrated_rgb':tag=1;values=[args.red,args.green,args.blue,args.alpha]
 else:tag=3;values=[args.white,args.alpha]
 color.contents=[w.ar.TypedValue(b'c',tag),w.ar.TypedGroup([b'f']*len(values),values)]
 return color
