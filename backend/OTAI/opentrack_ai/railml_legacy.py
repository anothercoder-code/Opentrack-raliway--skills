"""Original 1.00/1.03 rolling-stock exporter, not a generic legacy importer."""
from collections import Counter

from .stock_versions import arrays
from .archive import APIError,w
from .engine_diagrams import diagram_record,diagrams,KNOWN_SYSTEMS,point_rows,systems
from .native_records import trailer_record
from .railml_values import f32,speed_max
from .railml_export import formation_caption,native_id,xml_text
from .rolling_stock import engine_record


def loss_rows(bands,maximum,field):
    if not bands:return [(0.,0.),(float(maximum),0.)]
    rows=[]
    for index,band in enumerate(bands):
        start=f32(band['from_speed_kmh'])
        if index:start=f32(start+.001)
        end=float(bands[index+1]['from_speed_kmh'] if index+1<len(bands) else maximum)
        value=f32(band[field]);rows.extend([(start,value),(end,value)])
    return rows


def render(engines,trains,dataset_name,version,max_rows=100000):
    if version not in ['1.00','1.03']:raise APIError('ROLLING_STOCK_XML_FORMAT','Unsupported original legacy export version.')
    lines=['<?xml version="1.0" encoding="UTF-8"?>','<!-- Produced by OTAI; original OpenTrack legacy rolling-stock layout -->',
        '<railml xmlns:xsi="http://www.w3.org/2000/10/XMLSchema-instance" xsi:noNamespaceSchemaLocation="rollingstock.xsd">',
        f'\t<rollingstock version="{version}" rollingstockID="{native_id(dataset_name)}">','\t\t<vehicles>']
    vehicle_ids=[];formation_ids=[];warnings=[];ownership=[];total=0
    for index,obj in engines:
        engine=engine_record(obj);name=engine['name'];vehicle_ids.append(name)
        lines.append(f'\t\t\t<vehicle vehicleID="{xml_text(name)}" length="{engine["length_m"]}" speed="{engine["maximum_speed_kmh"]}" bruttoWeight="{engine["mass_t"]}" bruttoadhWeight="{engine["adhesion_mass_t"]}">')
        if version=='1.03':
            lines.append('\t\t\t\t<engine>')
            for number,diagram in enumerate(diagrams(obj)):
                record=diagram_record(diagram);codes=systems(diagram);maximum=speed_max(point_rows(diagram,1));bands=record['loss_function']
                if not codes:warnings.append({'kind':'unassigned_diagram_omitted','engine':name,'diagram_index':number})
                for code in codes:
                    lines.extend([f'\t\t\t\t\t<propulsion transmission="" engine="" power="" supply="{xml_text(KNOWN_SYSTEMS.get(code,"other"))}" >','\t\t\t\t\t\t<auxSupply nomPower="">'])
                    for tag,y_name,unit,field in [('mechPowerFactor','factor','1','loss_factor'),('power','power','kW','fixed_loss_kw')]:
                        rows=loss_rows(bands,maximum,field);total+=len(rows)
                        if total>max_rows:raise APIError('GENERATION_SIZE','Legacy rolling-stock exports support at most 100000 auxiliary value rows; select fewer records.')
                        lines.append(f'\t\t\t\t\t\t\t<{tag} xValueName="speed" xValueUnit="km/h" yValueName="{y_name}" yValueUnit="{unit}">')
                        for speed,value in rows:
                            lines.extend([f'\t\t\t\t\t\t\t\t<valueLine xValue="{speed:.3f}">',f'\t\t\t\t\t\t\t\t<values yValue="{value:.3f}"/>','\t\t\t\t\t\t\t\t</valueLine>'])
                        lines.append(f'\t\t\t\t\t\t\t</{tag}>')
                    lines.extend(['\t\t\t\t\t\t</auxSupply>','\t\t\t\t\t</propulsion>'])
                    ownership.append({'engine':name,'engine_index':index,'diagram_index':number,'system_code':code})
            lines.append('\t\t\t\t</engine>')
        lines.append('\t\t\t</vehicle>')
    for index,train in trains:
        for obj in arrays(train.contents[2].values[2]):
            row=trailer_record(obj);identifier=row['name']+'.'+str(index)+'.'+str(row['position']);vehicle_ids.append(identifier)
            lines.extend([f'\t\t\t<vehicle vehicleID="{xml_text(identifier)}" length="{row["length_m"]}" speed="{row["maximum_speed_kmh"]}" bruttoWeight="{row["mass_t"]}">',
                f'\t\t\t\t<wagon auxPowerConsumption="{row["power_loss_kw"]:.3f}"/>','\t\t\t</vehicle>'])
    lines.extend(['\t\t</vehicles>','\t\t<formations>']);known={w.string(obj.contents[1].value) for _,obj in engines}
    for index,train in trains:
        caption=formation_caption(w.string(train.contents[0].value));formation_ids.append(caption)
        trailers=arrays(train.contents[2].values[2]);delta=trailer_record(trailers[0])['power_loss_delta_load_factor_kw_per_t'] if trailers else 0.
        extra=f' auxPowerDeltaLoadFactor="{delta:.3f}"' if version=='1.03' else ''
        lines.extend([f'\t\t\t<formation formationID="{caption}"{extra}>','\t\t\t\t<trainOrder>'])
        for ref in arrays(train.contents[2].values[1]):
            name=w.string(ref.contents[0].value)
            if name not in known:warnings.append({'kind':'native_legacy_missing_engine_reference_preserved','formation':caption,'engine':name})
            lines.append(f'\t\t\t\t\t<vehicleType orderNumber="{ref.contents[1].value}" vehicleID="{xml_text(name)}" vehicleCount="1"/>')
        for obj in trailers:
            row=trailer_record(obj);identifier=row['name']+'.'+str(index)+'.'+str(row['position'])
            lines.append(f'\t\t\t\t\t<vehicleType orderNumber="{row["position"]}" vehicleID="{xml_text(identifier)}" vehicleCount="1"/>')
        lines.extend(['\t\t\t\t</trainOrder>','\t\t\t</formation>'])
    lines.extend(['\t\t</formations>','\t</rollingstock>','</railml>'])
    for kind,values in [('vehicleID',vehicle_ids),('formationID',formation_ids)]:
        for value,count in Counter(values).items():
            if count>1:warnings.append({'kind':'native_legacy_id_collision','field':kind,'id':value,'count':count})
    warnings.extend([
        {'kind':'original_legacy_export_omits_traction','details':'The original 1.00/1.03 exporter does not write tractive-effort curves. Version 1.03 propulsion content carries auxiliary-loss tables, with empty nominal power attributes.'},
        {'kind':'original_legacy_omitted_saved_fields','fields':['Engine rotating mass, axles, flags, stored power and braking','Train Category, braking and resistance parameters','Trailer rotating mass and number_of_items']},
        {'kind':'original_legacy_import_entry_is_todo','details':'The generic original import menu is a ToDo stub. Do not feed legacy vehicleID/vehicleType data to the original 2.2-style importer.'},
    ])
    return ('\r\n'.join(lines)+'\r\n').encode('ascii'),warnings,ownership,total
