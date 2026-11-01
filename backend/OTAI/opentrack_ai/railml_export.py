"""Original 1.7 rolling-stock RailML 2.2 export from saved native records."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import uuid

from .stock_versions import arrays
from .archive import APIError,digest,inside,w
from .engine_diagrams import diagrams,point_rows,systems,KNOWN_SYSTEMS
from .native_records import trailer_record,engine_reference_names
from .railml_values import diagram_power_w,sampled_traction,speed_max
from .rolling_stock import engine_record,formation_record
from opentrack_train_schema import engine_items,train_items

NAMESPACE='http://www.railml.org/schemas/2013'
MAX_SAMPLES=100000
ID_REPLACEMENTS=set(' #$%&()+,/:;<=>\\|')


def xml_text(value):
    result=[]
    for char in value:
        code=ord(char)
        if code<32 and char not in '\t\r\n':raise APIError('ROLLING_STOCK_XML_TEXT','An original caption contains an XML-forbidden control character.')
        if code>255 and code not in [0x201c,0x201e]:
            raise APIError('ROLLING_STOCK_XML_ENCODING','The original cString transformation is audited for ASCII, Latin-1 and the two explicit smart quotes only.',value[:80])
        result.append('&#'+str(code)+';' if char in '"&<>' or 160<=code<256 or code in [0x201c,0x201e] else char)
    return ''.join(result)


def native_id(value):return ''.join('_' if char in ID_REPLACEMENTS else char for char in xml_text(value))


def formation_caption(value):
    
    value=xml_text(value).rstrip('\n')
    while len(value)>1 and value.endswith(' '):value=value[:-1]
    return value


def names(objects,index):return [w.string(obj.contents[index].value) for obj in objects]


def render(engines,trains,dataset_name,metadata_date):
    """Indices are original catalog positions, preserved for selected subsets."""
    lines=['<?xml version="1.0" encoding="ISO-8859-1"?>',
        '<railml version="2.2" xmlns="'+NAMESPACE+'" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="'+NAMESPACE+' http://schemas.railml.org/2013/railML-2.2/railML.xsd">',
        '\t<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">','\t\t<dc:source>OTAI - original OpenTrack 1.7 RailML layout</dc:source>',
        '\t\t<dc:date>'+xml_text(metadata_date)+'</dc:date>','\t</metadata>',
        '\t<rollingstock id="rollingstock-'+native_id(dataset_name)+'" version="2.2">','\t\t<vehicles>']
    warnings=[];ownership=[];samples=0;first_index={}
    for index,engine in engines:first_index.setdefault(w.string(engine.contents[1].value),index)
    for index,engine in engines:
        record=engine_record(engine);name=record['name'];engine_diagrams=diagrams(engine)
        lines += [f'\t\t\t<vehicle id="engine-{index}" name="{xml_text(name)}" length="{record["length_m"]}" speed="{record["maximum_speed_kmh"]}" bruttoWeight="{record["mass_t"]}" bruttoAdhesionWeight="{record["adhesion_mass_t"]}">','\t\t\t\t<engine>']
        for number,diagram in enumerate(engine_diagrams,1):
            rows=point_rows(diagram,1);codes=systems(diagram);maximum=speed_max(rows)
            samples+=(maximum+1)*len(codes)
            if samples>MAX_SAMPLES:raise APIError('GENERATION_SIZE','Rolling-stock export supports at most 100000 sampled force rows; select fewer Engines.')
            if not codes:warnings.append({'kind':'unassigned_diagram_omitted','engine':name,'diagram_index':number-1})
            if codes and maximum>record['maximum_speed_kmh']+1:warnings.append({'kind':'native_sampling_clamps_beyond_engine_table','engine':name,'diagram_index':number-1,'engine_maximum_kmh':record['maximum_speed_kmh'],'diagram_maximum_kmh':maximum})
            for supply,code in enumerate(codes,1):
                power_type='diesel' if set(codes)&{20,21} else 'electric'
                description=KNOWN_SYSTEMS.get(code,'other')
                lines += [f'\t\t\t\t\t<propulsion id="propulsion-{index}-{number}-{supply}" powerType="{power_type}" power="{diagram_power_w(rows)}" rotationMassFactor="{record["rotating_mass_factor"]:.3f}" description="{xml_text(description)}">',
                    '\t\t\t\t\t\t<tractiveEffort>','\t\t\t\t\t\t\t<valueTable xValueName="Speed" xValueUnit="km/h" yValueName="Tractive Effort" yValueUnit="N">']
                for speed in range(maximum+1):
                    force=sampled_traction(rows,speed,record['maximum_speed_kmh'])*1000.0
                    lines += [f'\t\t\t\t\t\t\t\t<valueLine xValue="{speed}.0">',f'\t\t\t\t\t\t\t\t<values yValue="{force:.1f}"/>','\t\t\t\t\t\t\t\t</valueLine>']
                lines += ['\t\t\t\t\t\t\t</valueTable>','\t\t\t\t\t\t</tractiveEffort>','\t\t\t\t\t</propulsion>']
                ownership.append({'engine':name,'engine_index':index,'diagram_index':number-1,'system_code':code,'propulsion_id':f'propulsion-{index}-{number}-{supply}'})
        lines += ['\t\t\t\t</engine>','\t\t\t</vehicle>']
    for index,train in trains:
        for number,trailer in enumerate(arrays(train.contents[2].values[2]),1):
            row=trailer_record(trailer)
            lines += [f'\t\t\t<vehicle id="trailer-{index}-{number}" name="{xml_text(row["name"])}" length="{row["length_m"]}" speed="{row["maximum_speed_kmh"]}" bruttoWeight="{row["mass_t"]}">',
                f'\t\t\t\t<wagon auxiliaryPowerConsumption="{row["power_loss_kw"]*1000.0:.1f}" rotationMassFactor="{row["rotating_mass_factor"]:.3f}"/>','\t\t\t</vehicle>']
    lines += ['\t\t</vehicles>','\t\t<formations>'];ids=[]
    for index,train in trains:
        name=w.string(train.contents[0].value);identifier=native_id('fo-'+name);ids.append(identifier)
        lines += [f'\t\t\t<formation id="{identifier}" name="{formation_caption(name)}">','\t\t\t\t<trainOrder>']
        for ref in arrays(train.contents[2].values[1]):
            engine_name=w.string(ref.contents[0].value);target=first_index.get(engine_name)
            if target is None:
                target=engines[0][0] if engines else 1
                warnings.append({'kind':'native_missing_engine_reference_falls_back_to_first','formation':name,'engine':engine_name,'exported_vehicle_ref':'engine-'+str(target)})
            lines.append(f'\t\t\t\t\t<vehicleRef orderNumber="{ref.contents[1].value}" vehicleRef="engine-{target}" vehicleCount="1"/>')
        for number,trailer in enumerate(arrays(train.contents[2].values[2]),1):
            lines.append(f'\t\t\t\t\t<vehicleRef orderNumber="{trailer.contents[3].values[1]}" vehicleRef="trailer-{index}-{number}" vehicleCount="1"/>')
        lines += ['\t\t\t\t</trainOrder>','\t\t\t</formation>']
    lines += ['\t\t</formations>','\t</rollingstock>','</railml>']
    for identifier,count in Counter(ids).items():
        if count>1:warnings.append({'kind':'native_formation_id_collision','id':identifier,'count':count})
    warnings.extend([
        {'kind':'original_railml_2_2_omitted_saved_fields','fields':['Engine axles/flags/adhesion settings/stored power metadata','electrical braking, loss functions, display settings and raw interpolation knots','Train Category/braking/resistance/other parameters','Trailer number_of_items and load-dependent power loss']},
        {'kind':'original_import_is_lossy','details':'Native 2.2 import reduces supplies to generic electric 1 or diesel 20, truncates sampled integer values and leaves stored Engine force/power maxima at reset values. Use explicit recompute_limits/category options for subsequent data preparation.'},
    ])
    return ('\r\n'.join(lines)+'\r\n').encode('ascii'),warnings,ownership,samples


class RollingStockExporter:
    def __init__(self,service):self.service=service

    def export(self,args):
        project=self.service.project(args)
        from .stock_versions import migrate
        import copy
        depot,trains_root=copy.deepcopy([project.data['depot'],project.data['trains']]);decoded_migrations=migrate([depot,trains_root],('engines','formations'))
        all_engines=engine_items(depot);all_trains=train_items(trains_root)
        engine_names=names(all_engines,1);train_names=names(all_trains,0)
        for selected,known,kind in [(args.engine_names,engine_names,'Engine'),(args.formation_names,train_names,'Train')]:
            if selected is not None:
                missing=set(selected)-set(known)
                if missing:raise APIError('STOCK_NOT_FOUND','Selected exact '+kind+' names are missing.',sorted(missing))
        trains=[(i,t) for i,t in enumerate(all_trains,1) if args.formation_names is None or train_names[i-1] in args.formation_names]
        wanted=set(args.engine_names) if args.engine_names is not None else set(engine_names) if args.formation_names is None else {name for _,t in trains for name in engine_reference_names(t)}
        if args.format=='railml_2_2' and any(name not in engine_names for _,t in trains for name in engine_reference_names(t)) and all_engines:wanted.add(engine_names[0])
        omitted={name for _,t in trains for name in engine_reference_names(t) if name in engine_names and name not in wanted}
        if omitted:raise APIError('ROLLING_STOCK_XML_SELECTION','Explicit Engine selection omits dependencies of selected formations.',sorted(omitted))
        engines=[(i,e) for i,e in enumerate(all_engines,1) if engine_names[i-1] in wanted]
        if len(engines)+sum(1+len(arrays(t.contents[2].values[2])) for _,t in trains)>10000:raise APIError('GENERATION_SIZE','One rolling-stock export supports 10000 vehicle/formation records.')
        dataset=args.dataset_name if args.dataset_name is not None else project.project.name
        auxiliary_rows=0
        if args.format=='railml_2_2':blob,warnings,ownership,samples=render(engines,trains,dataset,datetime.now().strftime('%a %b %d %H:%M:%S %Y'))
        else:
            from .railml_legacy import render as render_legacy
            blob,warnings,ownership,auxiliary_rows=render_legacy(engines,trains,dataset,{'railml_1_00':'1.00','railml_1_03':'1.03'}[args.format],MAX_SAMPLES);samples=0
        folder=inside(self.service.work/('export-'+uuid.uuid4().hex[:16]),[self.service.work]);folder.mkdir(parents=True,exist_ok=False)
        path=folder/'rolling-stock.railml';path.write_bytes(blob)
        result={'format':args.format,'source_project':str(project.project),'source_digest':project.source_digest,'engines':len(engines),'formations':len(trains),'sampled_rows':samples,'auxiliary_rows':auxiliary_rows,'decoded_view_migrations':decoded_migrations,
            'file':str(path),'bytes':len(blob),'sha256':digest(blob),'representability_warnings':warnings[:20],'warning_count':len(warnings),
            'source_files_unchanged':all(Path(name).is_file() and digest(Path(name).read_bytes())==digest(raw) for name,raw in project.sources.items()),'native_application_started':False,'xsd_validation_performed':False}
        manifest=folder/'manifest.json';manifest.write_text(json.dumps({**result,'representability_warnings':warnings,'propulsion_ownership':ownership},ensure_ascii=False,indent=2),encoding='utf8')
        return {**result,'manifest':str(manifest)}
