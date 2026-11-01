"""Read-only native-format series decoding. Parsing never proves a simulation ran."""
import hashlib, math, re

class ResultError(ValueError): pass
def need(ok,msg):
    if not ok: raise ResultError(msg)
def sha(b): return hashlib.sha256(b).hexdigest()
MAX_BYTES=8*1024*1024
MAX_POINTS=100000
FORMATS={
 'OT_vs':('OT_Plot','Speed/Distance of Course', {'km','mi'}, {'km/h','mph'}, 'distance','speed'),
 'OT_vt':('OT_TimeXPlot','Speed/Time of Course', {'s'}, {'km/h','mph'}, 'time','speed'),
 'OT_Wis':('OT_Plot','Energy In/Distance of Course', {'km','mi'}, {'MJ'}, 'distance','energy_in'),
}
NUM=re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z')
def finite(x):
    need(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x),'Nonfinite or nonnumeric series value');return float(x)
def summary(points):
    need(points,'Empty series cannot produce statistics')
    xs=[p[0] for p in points];ys=[p[1] for p in points]
    return {'point_count':len(points),'x_min':min(xs),'x_max':max(xs),'y_min':min(ys),'y_max':max(ys),'first':points[0],'last':points[-1], 'x_nondecreasing':all(a<=b for a,b in zip(xs,xs[1:]))}
def base(blob,fmt):
    return {'format':fmt,'source_sha256':sha(blob),'source_bytes':len(blob),'read_only':True,'saved':False,'native_execution':False,'native_success':False,'run_completion_verified':False,'requires_native_validation':True,'source_provenance_verified':False,'planned_or_actual_verified':False,'limitation':'Decoding a supplied file does not authenticate its origin, course completion or this task\'s simulation.'}
def text_result(blob,encoding,whitelist):
    need(encoding in ('utf-8','ascii','cp1252'),'Unsupported explicit text encoding')
    try: text=blob.decode(encoding,errors='strict')
    except UnicodeError as e: raise ResultError('Invalid bytes for declared encoding') from e
    need(text and text.endswith('\n'),'Missing final newline; possible truncation')
    need('\ufeff' not in text and all(ord(ch)>=32 or ch in '\t\r\n' for ch in text),'Unsupported control character/BOM')
    headers={};comments=[];points=[];data_started=False
    for line in text.splitlines():
        need(len(line)<=16384,'Overlong line')
        if line.startswith('//'):
            need(not data_started,'Comments after data are outside supported writer format')
            comments.append(line)
            prefixes={'// Type    : ':'Type','// Desc.   : ':'Desc.','// x-Legend: ':'x-Legend','// y-Legend: ':'y-Legend'}
            for prefix,key in prefixes.items():
                if line.startswith(prefix):
                    val=line[len(prefix):];need(val==val.strip(),'Malformed structural header value')
                    need(key not in headers,'Duplicate structural header');headers[key]=val
            continue
        need(line!='','Unexpected empty/non-comment record')
        data_started=True
        cols=line.split('\t');need(len(cols)==2 and all(NUM.fullmatch(v)for v in cols),'Expected exactly two numeric tab-separated columns')
        points.append([finite(float(v))for v in cols]);need(len(points)<=MAX_POINTS,'Point limit exceeded')
    need(set(headers)=={'Type','Desc.','x-Legend','y-Legend'},'Missing structural headers')
    desc=headers['Desc.'];need(desc in FORMATS,'Unsupported native plot descriptor')
    typ,title,xunits,yunits,xkind,ykind=FORMATS[desc]
    need(headers['Type']==typ,'Descriptor/type mismatch')
    units=[]
    for key,allowed in [('x-Legend',xunits),('y-Legend',yunits)]:
        m=re.fullmatch(r'\[([^\[\]]+)\]',headers[key]);need(m and m[1] in allowed,'Unsupported explicit axis unit');units.append(m[1])
    if desc=='OT_vs':need(tuple(units)in (('km','km/h'),('mi','mph')),'Mixed distance/speed unit systems')
    titles=[]
    for line in comments:
        m=re.fullmatch(r'// '+re.escape(title)+r'\s*:\s*(.+)',line)
        if m: titles.append(m[1])
    need(len(titles)==1 and titles[0].strip()==titles[0] and len(titles[0])<=256,'Missing or ambiguous Course header')
    course=titles[0];need(not any(ord(c)<32 for c in course),'Invalid course identifier')
    need(any(c.startswith('// Produced by OpenTrack: ')for c in comments),'Missing producer header')
    if whitelist is not None: need(course in whitelist,'Course not in supplied whitelist')
    need(points,'Header-only output is not data')
    need(all(p[0]>=0 and p[1]>=0 for p in points),'Negative values outside supported forward series domain')
    need(all(a[0]<=b[0]for a,b in zip(points,points[1:])),'Nonmonotone forward x')
    result=base(blob,'ot_plot_text');result.update({'native_descriptor':desc,'encoding':encoding,'course_id_from_header':course,'course_mapping':'caller_whitelist_checked'if whitelist is not None else 'unverified_header_only','axis_units':units,'axis_quantities':[xkind,ykind],'points':points,'summary':summary(points),'evidence_basis':'native_writer_format_strings; text fixtures are synthetic, no original output text sample available','comments':comments,'warnings':['Complete-row truncation cannot be detected: these formats have no verified completion marker.','Min/max are observed samples only; no average speed, energy consumption delta or completion is inferred.','Distance may include output offset; energy rows must not be summed as total consumption.']})
    return result

def parse_result(blob,format,encoding='utf-8',course_whitelist=None):
    need(type(blob)is bytes and 0<len(blob)<=MAX_BYTES,'Input must be nonempty bytes <=8MiB')
    need(type(format)is str,'Explicit format required')
    if course_whitelist is not None:
        need(type(course_whitelist)is list and 0<len(course_whitelist)<=10000,'Whitelist requires nonempty bounded list')
        need(all(type(x)is str and 0<len(x)<=256 and x.strip()==x and not any(ord(c)<32 for c in x)for x in course_whitelist),'Invalid course whitelist')
        need(len(set(course_whitelist))==len(course_whitelist),'Duplicate course whitelist')
    if format=='ot_plot_text':return text_result(blob,encoding,course_whitelist)
    if format=='ot_plot_archive':return archive_result(blob,encoding,course_whitelist)
    raise ResultError('Unsupported result format')

def archive_result(blob,encoding,whitelist):
    need(encoding=='utf-8','Archive labels currently require UTF-8')
    need(whitelist is None,'Raw archive series names are not verified Course identifiers')
    from opentrack_ai.current_archive import writer as w, catalogs as c
    from opentrack_ai.current_archive.graph_references import reference_inventory
    root,_=w.load_next_compatible(blob)
    def hierarchy(o):
        h=[];cl=o.clazz
        while cl:h.append((cl.name,cl.version));cl=cl.superclass
        return h
    need(root.clazz.name==b'OTDocument' and root.clazz.version==1,'Only original OTDocument1 output archives supported')
    need(hierarchy(root)==[(b'OTDocument',1),(b'NSObject',0)],'Unsupported document inheritance')
    def shape(obj,name,version,encodings):
        need(obj.clazz.name==name.encode() and obj.clazz.version==version,'Class/version mismatch')
        need([g.encodings for g in obj.contents]==[[bytes([x])for x in enc.encode()]for enc in encodings],'Unsupported exact field layout')
    shape(root,'OTDocument',1,['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@'])
    objects,_=reference_inventory(root);models=[];total=0
    for obj in objects:
        if obj.clazz.name!=b'OTPlotModel':continue
        need(hierarchy(obj)==[(b'OTPlotModel',3),(b'OTResizeModel',0),(b'OTGraphicModel',0),(b'NSObject',0)],'Unsupported plot inheritance')
        shape(obj,'OTPlotModel',3,['i','f','f','f','i','i','if','ff','ff','@','@','@','@','@','@','@','@','@','ff','ffff','ii','@','i','@','@','@','@'])
        need(obj.contents[11].encodings==[b'@'] and obj.contents[24].encodings==[b'@'] and obj.contents[25].encodings==[b'@'],'PlotModel series/label layout mismatch')
        series=[]
        for plot in c.array(obj.contents[11].value):
            need(hierarchy(plot)==[(b'OTPlot',0),(b'NSObject',0)],'Unsupported plot series inheritance')
            shape(plot,'OTPlot',0,['@','@','ffff','fi','@'])
            points=[]
            for point in c.array(plot.contents[0].value):
                need(hierarchy(point)==[(b'OTPlotPoint',0),(b'NSObject',0)],'Unsupported point inheritance')
                shape(point,'OTPlotPoint',0,['ff']);points.append([finite(v)for v in point.contents[0].values]);total+=1;need(total<=MAX_POINTS,'Point limit exceeded')
            series.append({'name_raw':c.text(plot.contents[1].value),'points':points,'summary':summary(points)if points else {'point_count':0},'course_id':None,'axis_units':None,'planned_or_actual':'unknown'})
        models.append({'x_label_raw':c.text(obj.contents[24].value),'y_label_raw':c.text(obj.contents[25].value),'series':series})
    need(models and total>0,'No nonempty supported plot series')
    result=base(blob,'ot_plot_archive');result.update({'models':models,'model_count':len(models),'point_count':total,'evidence_basis':'original historical Demo Output1 archive plus native coder layouts','warnings':['Raw series labels are not validated Course mapping or units.','Historical stored plots do not prove this task ran, or contain a complete simulation.']});return result
