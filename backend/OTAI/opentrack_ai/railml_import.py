"""Original rolling-stock XML event/state semantics in an atomic saved draft."""
from collections import Counter
import copy
from pathlib import Path
from xml.parsers import expat

from .archive import APIError,digest,w
from .drafts import set_text
from .engine_diagrams import account_rows,diagrams,put,recompute_limits,set_systems
from .native_colors import make_color
from .native_records import upgrade_records
from .railml_values import checked_int,f32,float_text,i32,imported_points,int_text
from .resources import templates
from .rolling_stock import engine_record,formation_record
from opentrack_train_schema import engine_items,train_items

MAX_BYTES=20*1024*1024
KINDS={'import_rolling_stock_xml'}


def source_snapshot(project,args):
    if args.content is not None:blob=args.content.encode('utf8');source='inline UTF-8 bytes'
    else:
        path=project.resolve(args.file_path)
        if path.stat().st_size>MAX_BYTES:raise APIError('ROLLING_STOCK_XML_SIZE','Rolling-stock XML exceeds 20 MB.')
        blob=path.read_bytes()
        if blob!=path.read_bytes():raise APIError('ROLLING_STOCK_XML_CHANGED','XML changed during snapshot capture.')
        source=str(path)
    if len(blob)>MAX_BYTES:raise APIError('ROLLING_STOCK_XML_SIZE','Rolling-stock XML exceeds 20 MB.')
    return blob,{'source':source,'bytes':len(blob),'sha256':digest(blob),'snapshot_semantics':'Consumed once into the ordered draft; later external XML changes do not change generated records.'}


def archive_text(obj,index,value):
    try:value.encode('ascii')
    except UnicodeEncodeError as error:raise APIError('ROLLING_STOCK_XML_ENCODING','Imported saved captions currently require the audited ASCII archive encoding.',value[:100]) from error
    if '\0' in value:raise APIError('ROLLING_STOCK_XML_TEXT','Embedded NUL is not accepted in saved captions.')
    set_text(obj,index,value)


class StockConstructors:
    """Serialization shapes plus reviewed original init/reset values."""
    def __init__(self,operations):self.o=operations;self.d=operations.d;self.shapes,_=templates(operations.p.root)

    def shape(self,name):return copy.deepcopy(self.shapes[name])

    def vehicle(self,name):
        obj=self.shape(name);put(obj,0,17);archive_text(obj,1,'');obj.contents[2].values=[0,0,0,f32(1.06),4,1.0]
        return obj

    def engine(self):
        obj=self.vehicle('OTEngine')
        for index,value in [(3,0),(4,f32(3.3)),(5,0),(6,0),(7,0),(8,0),(9,4),(10,4),(11,7),(12,1),(13,1),(14,0.),(15,0.),(16,self.d.array()),(17,0)]:put(obj,index,value)
        return obj

    def trailer(self):
        obj=self.vehicle('OTTrailer');obj.contents[3].values=[0,0,5]
        for index,value in [(4,1000),(5,0.),(6,0.)]:put(obj,index,value)
        return obj

    def diagram(self):
        from .models import CalibratedWhite
        obj=self.shape('OTDDiagram');obj.contents[0].values=[250,400,150,125,80,1,1]
        for index in [1,2,3]:put(obj,index,self.d.array())
        put(obj,4,make_color(self.d,CalibratedWhite(white=0)));put(obj,5,-200);archive_text(obj,6,'')
        wrapper=self.shape('OTEfficiencyArray');put(wrapper,0,self.d.array());put(obj,7,wrapper)
        return obj

    def train(self,category):
        obj=self.shape('OTTrain');archive_text(obj,0,'');obj.contents[1].values=[0,0,f32(-0.6)]
        point=self.shape('OTDeceleration');point.contents[0].values=[0,f32(-0.6),f32(-0.6)]
        brakes=self.shape('OTDecelerationArray');put(brakes,0,self.d.array([point]));obj.contents[2].values=[brakes,self.d.array(),self.d.array()]
        archive_text(obj,3,category or 'Untitled')
        for index,values in {4:[3.],5:[1.5,.003,.00085],6:[0],7:[3.3,.02422,.000552],8:[100.,131.],9:[0.],10:[.01,-.1,-1.5],11:[0],12:[0,100.],13:[.069,.006],14:[1000.],15:[0],16:[0.,0.],17:[0],18:[1],19:[100.],20:[0.],21:[0,0.,0.],22:[0.]}.items():obj.contents[index].values=values
        return obj


class RollingStockImporter:
    def __init__(self,operations,args):
        self.o=operations;self.p=operations.p;self.d=operations.d;self.args=args;self.new=StockConstructors(operations)
        self.engine=self.new.engine();self.trailer=self.new.trailer();self.diagram=self.new.diagram();self.train=self.new.train(args.category)
        self.engine_ids={};self.trailer_ids={};self.scaled_trailers=set();self.vehicle_id='';self.active=False;self.ready=True;self.traction_active=False;self.trailer_only=True
        self.order=0;self.count=0;self.ref='';self.x=self.y=0.;self.x_name=self.y_name='';self.plot=[]
        self.counts=Counter();self.ignored=Counter();self.warnings=[];self.changes=[];self.depth=0;self.elements=0

    def require_versions(self):
        self.o.prepare_stock_versions()
        for catalog in [self.p.data['depot'],self.p.data['trains']]:
            for obj in w.objects(catalog):
                kind=w.kind(obj)
                expected={'OTEngine':(2,18),'OTDDiagram':(3,8),'OTTrain':(16,23)}.get(kind)
                if expected and (obj.clazz.version,len(obj.contents))!=expected:
                    raise APIError('ROLLING_STOCK_XML_VERSION','Importing fresh 1.7 objects requires the current audited stock layouts; migrate this older catalog first.',{'class':kind,'version':obj.clazz.version,'groups':len(obj.contents),'expected':expected})
        count=upgrade_records(self.p.data['trains'],'OTTrailer')
        if count:self.o.migrations['OTTrailer']=self.o.migrations.get('OTTrailer',0)+count

    def budget(self,field,limit):
        value=getattr(self.o,field,0)+1;setattr(self.o,field,value)
        if value>limit:raise APIError('GENERATION_SIZE','Rolling-stock XML operations exceed their shared '+field+' budget.',limit)

    def store(self,entity,obj):
        index=1 if entity=='engines' else 0;array=self.p.data['depot'] if entity=='engines' else self.p.data['trains'].contents[3].value
        name=w.string(obj.contents[index].value);items=w.elements(array);matches=[old for old in items if w.string(old.contents[index].value)==name]
        if len(matches)>1:raise APIError('DUPLICATE_STOCK_NAME','Existing stock names are ambiguous.',{'entity':entity,'name':name})
        if matches and self.args.on_conflict=='error':raise APIError('ENTITY_EXISTS','Choose an explicit XML collision policy.',{'entity':entity,'name':name})
        if matches and self.args.on_conflict=='keep':self.counts[entity+'_kept']+=1;return
        record=engine_record if entity=='engines' else formation_record
        before=record(matches[0],True) if matches and entity=='engines' else record(matches[0]) if matches else None
        self.o.store(array,copy.deepcopy(obj),name,index,True);self.counts[entity+'_stored']+=1
        if entity=='formations':self.counts['trailer_records_stored']+=len(w.elements(obj.contents[2].values[2]))
        after=record(obj,True) if entity=='engines' else record(obj)
        self.changes.append({'entity':entity,'name':name,'before':before,'after':after})

    def start(self,tag,attrs):
        self.depth+=1;self.elements+=1
        if self.depth>128 or self.elements>500000:raise APIError('ROLLING_STOCK_XML_SIZE','XML nesting/element budget exceeded.')
        if tag=='rollingstock':
            if attrs.get('version') in ['1.00','1.03']:raise APIError('ROLLING_STOCK_XML_FORMAT','This is an original legacy export, not a 2.2 import layout; its vehicleID/vehicleType fields are not interchangeable.')
            self.active=True;self.counts['rollingstock_blocks']+=1;self.engine_ids={};self.trailer_ids={};self.scaled_trailers=set();self.vehicle_id=''
            for entity in self.args.clear_catalogs:
                array=self.p.data['depot'] if entity=='engines' else self.p.data['trains'].contents[3].value
                items=w.elements(array)
                for obj in items:
                    record=engine_record(obj,True) if entity=='engines' else formation_record(obj)
                    self.changes.append({'entity':entity,'name':record['name'],'before':record,'after':None})
                self.counts[entity+'_cleared']+=len(items);w.set_elements(array,[])
        elif tag=='formation' and self.active:
            self.budget('xml_stock_records',10000);self.train=self.new.train(self.args.category);self.ready=True;self.order=self.count=0;self.ref=''
        elif tag=='vehicle':
            self.budget('xml_stock_records',10000);self.engine=self.new.engine();self.trailer=self.new.trailer();self.trailer_only=True
        elif tag=='propulsion':self.diagram=self.new.diagram()
        elif tag=='tractiveEffort':self.traction_active=True;self.plot=[];self.x_name=self.y_name=''
        elif tag=='valueLine':self.x=self.y=0.
        if self.ready:
            for key,value in attrs.items():self.attribute(tag,key,value)

    def attribute(self,tag,key,value):
        if tag=='formation' and key=='name':archive_text(self.train,0,value)
        elif not self.active:return
        elif tag=='vehicle':
            if key=='id':self.vehicle_id=value
            elif key=='name':archive_text(self.engine,1,value);archive_text(self.trailer,1,value)
            elif key in ['length','bruttoWeight']:
                slot=2 if key=='length' else 1;number=int_text(value)
                self.engine.contents[2].values[slot]=number;self.trailer.contents[2].values[slot]=number
            elif key=='speed':put(self.engine,7,int_text(value));put(self.trailer,4,int_text(value))
            elif key=='bruttoAdhesionWeight':put(self.engine,3,int_text(value))
            else:self.ignored[tag+'.'+key]+=1
        elif tag=='propulsion':
            if key=='powerType':set_systems(self.d,self.diagram,[1 if value=='electric' else 20])
            elif key=='rotationMassFactor':self.engine.contents[2].values[3]=float_text(value)
            elif key=='description':archive_text(self.diagram,6,value)
            elif key!='id':self.ignored[tag+'.'+key]+=1
        elif tag=='wagon':
            if key=='auxiliaryPowerConsumption':put(self.trailer,5,f32(float_text(value)/1000.0))
            elif key=='rotationMassFactor':self.trailer.contents[2].values[3]=float_text(value)
            else:self.ignored[tag+'.'+key]+=1
        elif tag=='vehicleRef':
            if key=='orderNumber':self.order=int_text(value)
            elif key=='vehicleCount':self.count=int_text(value)
            elif key=='vehicleRef':self.ref=value
            else:self.ignored[tag+'.'+key]+=1
        elif self.traction_active:
            if tag=='valueTable' and key=='xValueName':self.x_name=value
            elif tag=='valueTable' and key=='yValueName':self.y_name=value
            elif tag=='valueTable' and key in ['xValueUnit','yValueUnit']:pass 
            elif tag=='valueLine' and key=='xValue':self.x=float_text(value)
            elif tag=='values' and key=='yValue':self.y=float_text(value)

    def end(self,tag):
        if tag=='rollingstock':self.active=False
        elif tag=='propulsion':
            
            
            if not w.elements(self.diagram.contents[3].value):set_systems(self.d,self.diagram,[1])
            values=diagrams(self.engine)+[copy.deepcopy(self.diagram)]
            if len(values)>64:raise APIError('ENGINE_DIAGRAM_COUNT','At most 64 imported propulsions are supported per Engine.')
            account_rows(self.o,[self.diagram]);put(self.engine,16,self.d.array(values));self.counts['propulsions']+=1
        elif tag=='engine':
            if self.args.recompute_limits:recompute_limits(self.engine,diagrams(self.engine))
            self.store('engines',self.engine)
            if self.vehicle_id in self.engine_ids:self.warnings.append({'kind':'duplicate_engine_id_last_wins','id':self.vehicle_id})
            self.engine_ids[self.vehicle_id]=self.engine;self.engine=self.new.engine();self.trailer_only=False
        elif tag=='vehicle' and self.trailer_only:
            if self.vehicle_id in self.trailer_ids:self.warnings.append({'kind':'duplicate_trailer_id_last_wins','id':self.vehicle_id})
            self.trailer_ids[self.vehicle_id]=self.trailer;self.trailer=self.new.trailer()
        elif tag=='vehicleRef':self.vehicle_reference()
        elif tag=='tractiveEffort':self.traction_active=False
        elif tag=='valueLine':
            self.budget('xml_source_points',100000);self.plot.append((self.x,self.y))
        elif tag=='valueTable':
            rows,skipped=imported_points(self.plot,self.x_name,self.y_name);self.counts['adjacent_rounded_speed_duplicates_skipped']+=skipped
            if self.x_name.lower() in ['m/s','ms'] or self.y_name.lower()=='kn':self.counts['name_field_unit_conversions']+=1
            values=w.elements(self.diagram.contents[1].value)
            for row in rows:
                obj=self.new.shape('OTDPoint');obj.contents[0].values=list(row);values.append(obj)
            put(self.diagram,1,self.d.array(values));self.counts['traction_points']+=len(rows)
        elif tag=='formation' and self.active:
            positions=[obj.contents[1].value for obj in w.elements(self.train.contents[2].values[1])]+[obj.contents[3].values[1] for obj in w.elements(self.train.contents[2].values[2])]
            duplicates=[position for position,count in Counter(positions).items() if count>1]
            if duplicates:self.warnings.append({'kind':'native_duplicate_consist_positions_preserved','formation':w.string(self.train.contents[0].value),'positions':duplicates})
            self.store('formations',self.train);self.ready=False
        self.depth-=1

    def vehicle_reference(self):
        position=self.order if self.order>0 else len(w.elements(self.train.contents[2].values[1]))+len(w.elements(self.train.contents[2].values[2]))+1
        if self.ref in self.engine_ids:
            self.budget('xml_vehicle_references',10000);ref=self.new.shape('OTTrainEngine');archive_text(ref,0,w.string(self.engine_ids[self.ref].contents[1].value));put(ref,1,position)
            w.set_elements(self.train.contents[2].values[1],w.elements(self.train.contents[2].values[1])+[ref])
            if self.count not in [0,1]:self.warnings.append({'kind':'native_engine_vehicle_count_not_expanded','id':self.ref,'vehicle_count':self.count})
        elif self.ref in self.trailer_ids:
            self.budget('xml_vehicle_references',10000);source=self.trailer_ids[self.ref]
            if self.ref in self.scaled_trailers:self.warnings.append({'kind':'native_reused_scaled_trailer','id':self.ref,'vehicle_count':self.count,'prior_mass_t':source.contents[2].values[1],'prior_length_m':source.contents[2].values[2]})
            if self.count<2:source.contents[3].values[2]=1
            else:
                source.contents[2].values[1]=i32(source.contents[2].values[1]*self.count);source.contents[2].values[2]=i32(source.contents[2].values[2]*self.count)
                put(source,5,f32(source.contents[5].value*self.count));source.contents[3].values[2]=self.count
                self.scaled_trailers.add(self.ref)
            obj=copy.deepcopy(source);obj.contents[3].values[1]=position
            existing=w.elements(self.train.contents[2].values[2])
            if existing:put(obj,6,existing[0].contents[6].value)
            w.set_elements(self.train.contents[2].values[2],existing+[obj])
        else:self.warnings.append({'kind':'native_undefined_vehicle_reference_skipped','id':self.ref})

    def run(self):
        self.require_versions();blob,provenance=source_snapshot(self.p,self.args)
        self.o.xml_import_bytes=getattr(self.o,'xml_import_bytes',0)+len(blob)
        if self.o.xml_import_bytes>MAX_BYTES:raise APIError('GENERATION_SIZE','XML imports share a 20 MB source-byte budget per batch.')
        parser=expat.ParserCreate();parser.StartElementHandler=self.start;parser.EndElementHandler=self.end
        def prohibited(*unused):raise APIError('ROLLING_STOCK_XML_DTD','DTD/custom entities and external XML resources are not accepted.')
        parser.StartDoctypeDeclHandler=prohibited;parser.EntityDeclHandler=prohibited;parser.ExternalEntityRefHandler=prohibited
        try:parser.Parse(blob,True)
        except expat.ExpatError as error:raise APIError('ROLLING_STOCK_XML_PARSE','XML is not well formed.',{'line':error.lineno,'column':error.offset,'message':str(error)}) from error
        if not self.counts['rollingstock_blocks']:raise APIError('ROLLING_STOCK_XML_EMPTY','No original rollingstock element was recognized; stock 2.2 import uses unprefixed element names.')
        self.warnings.append({'kind':'native_import_unrepresented_fields','details':'Native import ignores propulsion power and genericizes supplies; Category/braking/resistance use constructor defaults. Only name-based unit gates, truncation and consecutive-speed de-duplication are applied.'})
        return {'format':'railml_2_2','source_snapshot':provenance,'on_conflict':self.args.on_conflict,'clear_catalogs':self.args.clear_catalogs,'recompute_limits':self.args.recompute_limits,
            'counts':dict(self.counts),'stock_changes':self.changes,'xml_warnings':self.warnings,'ignored_fields':dict(self.ignored),'native_application_started':False}
