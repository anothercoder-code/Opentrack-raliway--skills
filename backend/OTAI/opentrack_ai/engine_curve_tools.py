"""Inline, no-I/O Agent exchange; legacy atoi parsing is intentionally permissive."""
import hashlib
import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator
from .engine_curve_exchange import parse_text, render_text, LIMIT

Int32=Annotated[StrictInt, Field(ge=-2147483648,le=2147483647)]
class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
class Point(Input):
    speed_kmh:Int32
    force_kn:Int32
    flag:Annotated[StrictInt,Field(ge=1,le=2)]=1
class Diagram(Input):
    description:Annotated[StrictStr,Field(max_length=1022)]
    points:Annotated[list[Point],Field(max_length=100000)]
    braking_points:Annotated[list[Point],Field(max_length=100000)]
    @model_validator(mode='after')
    def budget(self):
        if len(self.points)+len(self.braking_points)>100000:raise ValueError('At most 100000 total points')
        return self
class ParseCurveText(Input):
    content:Annotated[StrictStr,Field(max_length=LIMIT)]
class RenderCurveText(Input):
    engine_name:Annotated[StrictStr,Field(max_length=1022)]=''
    diagram_index:Annotated[StrictInt,Field(ge=0,le=63)]=0
    diagram:Diagram


def compile_rows(rows):
    """Original insertion: sign split, first speed per curve wins, stable sort."""
    curves={'points':[], 'braking_points':[]};seen={key:set() for key in curves};duplicates=0
    for speed,force,flag in rows:
        key='braking_points' if force<0 else 'points'
        if speed in seen[key]:duplicates+=1;continue
        seen[key].add(speed);curves[key].append({'speed_kmh':speed,'force_kn':force,'flag':flag})
    reordered=[]
    for key,points in curves.items():
        if any(b['speed_kmh']<a['speed_kmh'] for a,b in zip(points,points[1:])):reordered.append(key)
        points.sort(key=lambda row:row['speed_kmh'])
    return curves,duplicates,reordered


def parse(args):
    rows,details=parse_text(args.content)
    curves,duplicates,reordered=compile_rows(rows)
    warnings=[]
    if duplicates:warnings.append({'kind':'duplicate_speeds_skipped','count':duplicates})
    if reordered:warnings.append({'kind':'source_order_sorted','curves':reordered})
    for field in ['ignored_noncomment_lines','incomplete_numeric_lines','integer_converted_rows']:
        if details[field]:warnings.append({'kind':field,'count':details[field]})
    
    invalid_force=prefix_conversion=extra_tokens=0
    for line in args.content.replace('\r\n','\n').split('\n'):
        gate=line.lstrip(' ')
        if not gate or gate[0] not in '0123456789':continue
        tokens=line.replace(',','.').split()
        if len(tokens)<2:continue
        invalid_force+=not bool(re.match(r'^[+-]?[0-9]+',tokens[1]))
        prefix_conversion+=any(not re.fullmatch(r'[+-]?[0-9]+',t) for t in tokens[:2])
        extra_tokens+=len(tokens)>3 or (len(tokens)>2 and tokens[2]!='H')
    for kind,count in [('invalid_force_converted_to_zero',invalid_force),('atoi_noninteger_token_conversion',prefix_conversion),('unrecognized_or_extra_tokens_ignored',extra_tokens)]:
        if count:warnings.append({'kind':kind,'count':count})
    return {'diagram':{'description':details['source_diagram_name'] or '',**curves},
        'source_rows':[{'speed_kmh':s,'force_kn':f,'flag':t} for s,f,t in rows],
        'provenance':{'sha256':hashlib.sha256(args.content.encode('ascii')).hexdigest(),'bytes':len(args.content.encode('ascii')),**details},
        'warnings':warnings,'native_application_started':False,'archive_written':False,
        'scope':'Inline text to typed point data; not a complete saved Engine or native load verification.'}


def render(args):
    content,warnings=render_text(args.engine_name,args.diagram_index,args.diagram.model_dump())
    
    
    reparsed=parse(ParseCurveText(content=content))
    intended=args.diagram.model_dump()
    if reparsed['diagram']!=intended:warnings.append({'kind':'export_reimport_changes_diagram','reimported_diagram':reparsed['diagram']})
    warnings.extend(reparsed['warnings'])
    return {'content':content,'sha256':hashlib.sha256(content.encode('ascii')).hexdigest(),'bytes':len(content.encode('ascii')),
        'warnings':warnings,'native_application_started':False,'archive_written':False,
        'format':'OTAI compatible Z/V ASCII text; comments are not native exporter byte identity.'}


def tool_definitions():
    return [
        ('opentrack_parse_engine_curve_text','Parse inline original Z/V text using audited atoi and next-row H semantics. Return source-order rows plus sign-split, first-speed-wins sorted point data and explicit losses. No paths, archive reads/writes or native execution.',ParseCurveText,parse),
        ('opentrack_render_engine_curve_text','Render typed Z/V points to compatible ASCII CRLF text with next-point H markers and export/reimport loss reporting. Not a complete Engine or original exporter header identity. No filesystem or native execution.',RenderCurveText,render),
    ]
