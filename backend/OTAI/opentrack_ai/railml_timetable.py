"""Read-only RailML 2.2 timetable inventory, based on original analyzer functions.

Raw XML fields and structural diagnostics are independent of native import UI
ordering, string conversion and trainPart object aliasing. No archive writes.
"""
from collections import Counter,defaultdict
from xml.parsers import expat

from .archive import APIError,Project,page
from .timetable_exchange import input_text

NS='http://www.railml.org/schemas/2013'
SECTIONS=('stations','formations','train_parts','trains','train_groups','rows','times','references','diagnostics')
PARENTS={'ocp':'operationControlPoints','formation':'formations','trainPart':'trainParts','train':'trains','trainGroup':'trainGroups',
    'ocpTT':'ocpsTT','times':'ocpTT','formationTT':'trainPart','connection':'connections','trainPartRef':'trainPartSequence','trainRef':'trainGroup'}
CONTAINERS={'railml','infrastructure','operationControlPoints','rollingstock','formations','timetable','trainParts','ocpsTT','connections','trains','trainGroups','trainPartSequence','stopDescription','stopTimes'}


class RailMLTimetableInventory:
    def __init__(self):
        self.data={key:[] for key in SECTIONS};self.stack=[];self.elements=0;self.namespace=None;self.prefixes=set();self.ignored=Counter()
        self.part=None;self.train=None;self.group=None;self.row=None;self.ids=defaultdict(list);self.clock=0

    def diagnostic(self,code,**data):
        if len(self.data['diagnostics'])>=10000:raise APIError('RAILML_TIMETABLE_SIZE','More than 10000 diagnostics; inspect a smaller XML document.')
        self.data['diagnostics'].append({'code':code,**data})

    def add(self,section,record):
        if len(self.data[section])>=10000:raise APIError('RAILML_TIMETABLE_SIZE','An inventory section exceeds 10000 records.',section)
        self.data[section].append(record);return record

    def local(self,name):
        uri,_,local=name.rpartition('}')
        return local if uri==self.namespace else None

    def start(self,name,attrs):
        self.elements+=1;self.clock+=1
        if self.elements>50000 or len(self.stack)>=64:raise APIError('RAILML_TIMETABLE_SIZE','XML exceeds 50000 elements or 64 nesting levels.')
        if len(attrs)>64 or any(len(v)>4096 for v in attrs.values()):raise APIError('RAILML_TIMETABLE_SIZE','XML element attributes exceed the bounded inventory contract.')
        if not self.stack:
            uri,_,tag=name.rpartition('}')
            if tag!='railml' or uri not in ['',NS]:raise APIError('RAILML_TIMETABLE_FORMAT','Expected RailML 2.2 <railml> with its 2013 namespace or no namespace.')
            if attrs.get('version')!='2.2':raise APIError('RAILML_TIMETABLE_VERSION','This inventory targets original RailML 2.2.',attrs.get('version'))
            self.namespace=uri
        tag=self.local(name);parent=self.stack[-1] if self.stack else None
        
        if self.stack and parent is None:tag=None
        if tag in PARENTS and parent!=PARENTS[tag]:raise APIError('RAILML_TIMETABLE_STRUCTURE','Unexpected parent for a timetable element.',{'element':tag,'parent':parent})
        if tag not in PARENTS and tag not in CONTAINERS:
            self.ignored[name]+=1;tag=None
        self.stack.append(tag)
        if tag in ['ocp','formation','trainPart','train','trainGroup']:
            section={'ocp':'stations','formation':'formations','trainPart':'train_parts','train':'trains','trainGroup':'train_groups'}[tag]
            record={'id':attrs.get('id',''),'attributes':dict(attrs),'document_order':self.clock}
            self.add(section,record)
            if record['id']:self.ids[record['id']].append((section,record))
            else:self.diagnostic('MISSING_ID',kind=section,document_order=self.clock)
            if tag=='trainPart':self.part=record;record.update(row_count=0,formation_ref_count=0)
            elif tag=='train':self.train=record;record['part_ref_count']=0
            elif tag=='trainGroup':self.group=record;record['train_ref_count']=0
        elif tag=='ocpTT':
            if self.part is None:raise APIError('RAILML_TIMETABLE_STRUCTURE','ocpTT requires a trainPart.')
            self.row=self.add('rows',{'part_id':self.part['id'],'part_order':self.part['document_order'],'index':self.part['row_count'],'ocp_ref':attrs.get('ocpRef',''),
                'attributes':dict(attrs),'time_block_count':0,'connection_count':0})
            self.part['row_count']+=1;self.reference('stations',attrs.get('ocpRef',''),'ocpRef',part_id=self.part['id'],row_index=self.row['index'])
        elif tag=='times':
            if self.row is None:raise APIError('RAILML_TIMETABLE_STRUCTURE','times requires an ocpTT.')
            self.add('times',{'part_id':self.part['id'],'part_order':self.part['document_order'],'row_index':self.row['index'],
                'scope':attrs.get('scope',''),'scope_attribute_present':'scope' in attrs,'attributes':dict(attrs)})
            self.row['time_block_count']+=1
        elif tag=='formationTT':
            if self.part is None:raise APIError('RAILML_TIMETABLE_STRUCTURE','formationTT requires a trainPart.')
            self.part['formation_ref_count']+=1;self.reference('formations',attrs.get('formationRef',''),'formationRef',part_id=self.part['id'])
        elif tag=='trainPartRef':
            if self.train is None:raise APIError('RAILML_TIMETABLE_STRUCTURE','trainPartRef requires a train.')
            self.train['part_ref_count']+=1;self.reference('train_parts',attrs.get('ref',''),'ref',train_id=self.train['id'],train_order=self.train['document_order'])
        elif tag=='trainRef':
            if self.group is None:raise APIError('RAILML_TIMETABLE_STRUCTURE','trainRef requires a trainGroup.')
            self.group['train_ref_count']+=1;self.reference('trains',attrs.get('ref',''),'ref',group_id=self.group['id'],sequence=attrs.get('sequence'))
        elif tag=='connection':
            if self.row is None:raise APIError('RAILML_TIMETABLE_STRUCTURE','connection requires an ocpTT.')
            self.row['connection_count']+=1
            context={'part_id':self.part['id'],'row_index':self.row['index'],'connection_index':self.row['connection_count']-1}
            for attr,kind in [('trainRef','trains'),('trainPartRef','train_parts'),('ocpRef','stations')]:
                if attr in attrs:self.reference(kind,attrs[attr],attr,**context)
            if not any(k in attrs for k in ['trainRef','trainPartRef']):self.diagnostic('CONNECTION_WITHOUT_TRAIN_REFERENCE',**context)

    def reference(self,kind,target,attribute,**context):
        self.add('references',{'target_kind':kind,'target_id':target,'attribute':attribute,'document_order':self.clock,**context})

    def end(self,name):
        tag=self.stack.pop()
        if tag=='trainPart':self.part=None
        elif tag=='train':self.train=None
        elif tag=='trainGroup':self.group=None
        elif tag=='ocpTT':self.row=None

    def parse(self,content):
        if len(content.encode('utf8'))>2000000:raise APIError('RAILML_TIMETABLE_SIZE','XML input exceeds 2 MB.')
        parser=expat.ParserCreate(namespace_separator='}')
        parser.StartElementHandler=self.start;parser.EndElementHandler=self.end
        parser.StartNamespaceDeclHandler=lambda prefix,uri:self.prefixes.add(prefix) if prefix and uri==NS else None
        def entity(*args):raise APIError('RAILML_TIMETABLE_ENTITY','Entity declarations are outside the supported inventory contract.')
        parser.EntityDeclHandler=entity;parser.ExternalEntityRefHandler=lambda *args:1
        parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        try:parser.Parse(content,True)
        except expat.ExpatError as error:raise APIError('RAILML_TIMETABLE_PARSE','Malformed or unbound-prefix XML.',{'line':error.lineno,'column':error.offset}) from error
        return self

    def analyze(self,project):
        for section,key in [('trains','type'),('times','scope')]:
            values={item['attributes'].get(key,'') for item in self.data[section]}
            if len(values)>64 or any(len(value)>80 for value in values):raise APIError('RAILML_TIMETABLE_SIZE','Selection inventory supports at most 64 values per kind, each at most 80 characters.',key)
        known={'stations':{r['sign'] for r in project.catalog('stations')},'formations':{r['name'] for r in project.catalog('trains')},'trains':{r['course_id'] for r in project.catalog('services')}}
        by_kind={kind:defaultdict(list) for kind in ['stations','formations','trains','train_parts','train_groups']}
        for kind in by_kind:
            for item in self.data[kind]:by_kind[kind][item['id']].append(item)
        for identifier,items in self.ids.items():
            if len(items)>1:self.diagnostic('DUPLICATE_XML_ID',id=identifier,occurrences=len(items),kinds=sorted({kind for kind,_ in items}))
        
        
        for item in self.data['stations']:
            attrs=item['attributes'];higher='abbrevation' if 'abbrevation' in attrs else 'code' if 'code' in attrs else 'name'
            candidate=attrs.get(higher,'');ambiguous=higher!='name' and not candidate and bool(attrs.get('name'))
            if ambiguous:self.diagnostic('OCP_ATTRIBUTE_ORDER_AMBIGUOUS',id=item['id'],empty_attribute=higher)
            if 'abbreviation' in attrs:self.diagnostic('NATIVE_IGNORES_CORRECTLY_SPELLED_ABBREVIATION',id=item['id'])
            verified=not ambiguous and candidate.isascii()
            item.update(analyzer_station_sign=candidate if verified else None,raw_candidate=candidate,mapping_verified=verified,existing_project_binding=candidate in known['stations'] if verified else None)
            if not candidate and not ambiguous:self.diagnostic('EMPTY_STATION_MAPPING',id=item['id'])
            if candidate and not candidate.isascii():self.diagnostic('NONASCII_STATION_CONVERSION_UNVERIFIED',id=item['id'])
        for item in self.data['formations']:
            item['analyzer_train_name']=item['attributes'].get('name','');item['existing_project_binding']=item['analyzer_train_name'] in known['formations']
        for item in self.data['trains']:
            item['analyzer_course_id']=item['attributes'].get('trainNumber','');item['existing_project_binding']=item['analyzer_course_id'] in known['trains']
        for ref in self.data['references']:
            candidates=by_kind[ref['target_kind']].get(ref['target_id'],[])
            ref['resolution']='unique' if len(candidates)==1 else 'ambiguous' if candidates else 'missing'
            if ref['resolution']!='unique':self.diagnostic('REFERENCE_'+ref['resolution'].upper(),**{key:ref[key] for key in ['target_kind','target_id','document_order']})
            if ref['target_kind']=='train_parts' and 'train_order' in ref and len(candidates)==1 and candidates[0]['document_order']>ref['document_order']:
                self.diagnostic('TRAIN_PART_DEFINED_AFTER_REFERENCE',train_id=ref['train_id'],part_id=ref['target_id'])
            if ref['attribute']=='trainPartRef' and not any(t['analyzer_course_id'] for t in by_kind['trains'].get(ref['target_id'],[])):
                self.diagnostic('NATIVE_CONNECTION_PART_REF_NOT_IN_TRAIN_ID_MAP',part_id=ref.get('part_id'),target_id=ref['target_id'])
        rows=defaultdict(list);refs=defaultdict(list);uses=defaultdict(list)
        for row in self.data['rows']:rows[row['part_order']].append(row)
        for ref in self.data['references']:
            if 'train_order' in ref:refs[ref['train_order']].append(ref);uses[ref['target_id']].append(ref)
        for part_id,part_uses in uses.items():
            if len(part_uses)>1:self.diagnostic('TRAIN_PART_REUSED_NATIVE_ALIAS_RISK',part_id=part_id,reference_count=len(part_uses))
        for train in self.data['trains']:
            first_course=None;previous=None;candidate_rows=0
            for ref in refs[train['document_order']]:
                parts=by_kind['train_parts'].get(ref['target_id'],[])
                if len(parts)!=1:continue
                part=parts[0];part_rows=rows[part['document_order']]
                if not part_rows:continue
                first=part_rows[0]['ocp_ref'];last=part_rows[-1]['ocp_ref']
                
                
                def station(identifier):
                    values=by_kind['stations'].get(identifier,[])
                    if len(values)==1:
                        mapped=values[0]['analyzer_station_sign'];return identifier if mapped=='' else mapped
                    return identifier if not values else None
                a=station(previous) if previous is not None else None;b=station(first)
                if previous is not None and (a is None or b is None):self.diagnostic('PART_BOUNDARY_UNVERIFIED',train_id=train['id'],part_id=part['id'])
                elif previous is not None and a!=b:
                    self.diagnostic('PART_BOUNDARY_MISMATCH_NATIVE_SKIPS_PART',train_id=train['id'],part_id=part['id'],previous_ocp_ref=previous,next_ocp_ref=first);continue
                if first_course is None:first_course=part['attributes'].get('trainNumber','')
                candidate_rows+=len(part_rows)-(1 if previous is not None else 0);previous=last
            train.update(candidate_course_id=train['analyzer_course_id'] or first_course or train['id'],candidate_row_count=candidate_rows,
                candidate_is_native_import_result=False)
        self.diagnostic('CALCULATED_SCOPE_IMPORTS_INTO_PLANNED_FIELDS') if any(t['scope']=='calculated' for t in self.data['times']) else None
        if self.prefixes:self.diagnostic('PREFIX_NORMALIZATION_NATIVE_PARITY_UNVERIFIED')
        if self.ignored:self.diagnostic('IGNORED_XML_EXTENSIONS',elements=sum(self.ignored.values()),distinct_names=len(self.ignored))
        return self


class RailMLTimetableInspector:
    def __init__(self,service):self.service=service

    def inspect(self,args):
        project=self.service.project(args);before=project.source_hashes
        content,provenance=input_text(project,args)
        if 'snapshot_semantics' in provenance:provenance['snapshot_semantics']='These exact bytes were inspected; no file or archive was written.'
        inventory=RailMLTimetableInventory().parse(content).analyze(project);data=inventory.data
        trains=[item for item in data['trains'] if args.train_type is None or item['attributes'].get('type','')==args.train_type]
        times=[item for item in data['times'] if args.scope is None or item['scope']==args.scope]
        if Project(project.root,str(project.project),str(project.run_file) if project.run_file else None).source_hashes!=before:
            raise APIError('SOURCE_CHANGED','The selected project changed during RailML inspection.')
        items=[] if args.section=='summary' else trains if args.section=='trains' else times if args.section=='times' else data[args.section]
        return {'format':'railml_22','input':provenance,'project':str(project.project),'source_files_unchanged':True,
            'counts':{key:len(value) for key,value in data.items()},'elements':inventory.elements,
            'selection_inventory':{'train_types':sorted({item['attributes'].get('type','') for item in data['trains']}),
                'time_scopes':sorted({item['scope'] for item in data['times']}),'scope_missing_count':sum(not item['scope_attribute_present'] for item in data['times']),
                'native_ui_choice_order_reproduced':False},
            'selection':{'train_type':args.train_type,'scope':args.scope,'matching_trains':len(trains),'matching_time_blocks':len(times),'filters_independent':True},
            'diagnostic_counts':dict(Counter(item['code'] for item in data['diagnostics'])),'section':args.section,**page(items,args.limit,args.offset),
            'import_implemented':False,'export_implemented':True,'schema_validation_performed':False,'native_application_started':False,
            'scope_note':'Read-only raw-field inventory and static reference diagnostics. No timetable assembly, time conversion, native UI selection or import acceptance is certified.',
            'evidence':['railml-timetable-analysis-contract','railml-timetable-analysis-functions']}
