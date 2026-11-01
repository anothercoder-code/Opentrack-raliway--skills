"""Audited stock Engine/Train/Category archive fields, not runtime physics."""
import math

from .archive import APIError,w
from .native_records import trailer_record

ENGINE_SCALARS={'strahl_resistance_factor':(4,0),'adhesion_code':(5,0),'minimum_force_kn':(17,0),
    'drive_type_code':(12,0),'voltage_type_code':(13,0),'cross_section_girth_m':(14,0),'cross_section_area_m2':(15,0),'maximum_power_kw':(8,0)}
ENGINE_FLAGS={'understands_balise':1,'understands_loop':2,'understands_radio':4,'rack_and_pinion':8}
TRAIN_SCALARS={'train_type_code':(1,0),'acceleration_delay_s':(9,0),'maximum_drawbar_force_kn':(14,0),
    'braking_delay_s':(16,0),'braking_release_speed_kmh':(16,1),'braking_delay_type_code':(17,0),
    'resistance_formula_code':(6,0),'curve_resistance_formula_code':(18,0),'curve_resistance_percent':(19,0),
    'acceleration_delay_at_stop_s':(22,0),'minimum_time_to_hold_speed_s':(20,0)}
CATEGORY_FLAGS={'enabled':1,'use_initial_delay':2,'use_station_delay':4,'use_on_time_performance':8,'use_delayed_performance':16,'stop_at_every_station':32}
CATEGORY_SCALARS={'dispatching_priority':(3,0),'look_ahead_distance_m':(3,1),'look_ahead_time_s':(6,0),
    'dispatching_type_code':(11,0),'initial_delay_mean_s':(4,0),'initial_delay_maximum_s':(4,1),
    'initial_delay_probability_percent':(4,2),'maximum_station_delay_s':(5,0),'station_delay_probability_percent':(8,0),
    'initial_delay_distribution_code':(9,0),'delay_limit_small_s':(7,0),'delay_limit_medium_s':(7,1),'delay_limit_large_s':(7,2)}
CATEGORY_SCALARS.update({'stop_at_every_station_time_s':(15,0),'timing_stations_type_code':(16,0),
    'dwell_variation_early':(18,0),'dwell_variation_delayed':(18,1),
    'dwell_variation_early_unit_code':(18,2),'dwell_variation_delayed_unit_code':(18,3),
    'delay_add_type_code':(19,0),'default_connection_time_s':(20,0),'departure_process_time_s':(21,0),
    'track_name_creation_type_code':(23,0),'dwell_variation_early_delay_offset_s':(24,0),'dwell_variation_delayed_delay_offset_s':(24,1)})
CATEGORY_ADVANCED_FIELDS={field for field,(index,_) in CATEGORY_SCALARS.items() if index>=15}|{'foreground_color','background_color','departure_process_starts_at_departure_time'}
CATEGORY_TABLES={'initial_delay_intervals':(10,'OTDelayIntervalArray','OTDelayInterval'),
    'delay_priorities':(12,'OTDelayPriorityArray','OTDelayPriority'),
    'on_time_performance':(13,'OTPerformanceIntervalArray','OTPerformanceInterval'),
    'delayed_performance':(14,'OTPerformanceIntervalArray','OTPerformanceInterval')}


def finite(value):return value if not isinstance(value,float) or math.isfinite(value) else None


def peak_power_kw(points,segment_types=None):
    """Peak v*F on the supplied piecewise-linear force curve, in kW."""
    candidates=[v*f/3.6 for v,f in points]
    for index,((a,fa),(b,fb)) in enumerate(zip(points,points[1:])):
        if segment_types is not None and segment_types[index+1]!=1:continue
        slope=(fb-fa)/(b-a)
        if slope>=0:continue
        intercept=fa-slope*a;vertex=-intercept/(2*slope)
        if a<vertex<b:candidates.append(vertex*(slope*vertex+intercept)/3.6)
    return round(max(candidates))


def set_scalars(obj,args,mapping):
    for field,(index,slot) in mapping.items():
        value=getattr(args,field)
        if value is None:continue
        if index>=len(obj.contents):raise APIError('ROLLING_STOCK_VERSION','Selected record version lacks this field; use a compatible template or an audited migration.',{'class':w.kind(obj),'field':field,'version':obj.clazz.version})
        obj.contents[index].values[slot]=value


def engine_record(obj,include_curves=False):
    source_version=obj.clazz.version
    if source_version>2:raise APIError('ROLLING_STOCK_VERSION','Unsupported Engine archive version.',source_version)
    if source_version<2:
        from .stock_versions import decoded_copy
        obj=decoded_copy(obj)
    result={'name':w.string(obj.contents[1].value),'mass_t':obj.contents[2].values[1],'length_m':obj.contents[2].values[2],
        'maximum_speed_kmh':obj.contents[7].value,'maximum_force_kn':obj.contents[6].value,'maximum_power_kw':obj.contents[8].value,
        'adhesion_mass_t':obj.contents[3].value,'rotating_mass_factor':obj.contents[2].values[3],
        'number_of_axles':obj.contents[2].values[4],'cw_value':obj.contents[2].values[5],
        'driven_axles':obj.contents[9].value,'traction_motors':obj.contents[10].value,'archive_class_version':source_version}
    if source_version<2:result['decoded_class_version']=2
    result.update({field:finite(obj.contents[index].values[slot]) if index<len(obj.contents) else None for field,(index,slot) in ENGINE_SCALARS.items()})
    result.update({field:bool(obj.contents[11].value&bit) for field,bit in ENGINE_FLAGS.items()})
    diagrams=w.elements(obj.contents[16].value) if obj.contents[16].value else []
    result['tractive_effort_diagram_count']=len(diagrams)
    if include_curves:
        from .engine_diagrams import diagram_record
        result['tractive_effort_diagrams']=[diagram_record(diagram) for diagram in diagrams]
    return result


def formation_record(obj):
    source_version=obj.clazz.version
    if source_version>16:raise APIError('ROLLING_STOCK_VERSION','Unsupported Train archive version.',source_version)
    if source_version<16:
        from .stock_versions import decoded_copy
        obj=decoded_copy(obj)
    refs=w.elements(obj.contents[2].values[1]) if obj.contents[2].values[1] else []
    trailers=w.elements(obj.contents[2].values[2]) if obj.contents[2].values[2] else []
    brake_wrapper=obj.contents[2].values[0];brakes=w.elements(brake_wrapper.contents[0].value) if brake_wrapper and brake_wrapper.contents[0].value else []
    from .native_records import engine_reference_names
    result={'name':w.string(obj.contents[0].value),'engines':engine_reference_names(obj),
        'engine_positions':[item.contents[1].value for item in refs],
        'trailers':[trailer_record(item) for item in trailers],
        'category':w.string(obj.contents[3].value),'maximum_acceleration_mps2':obj.contents[4].value,
        'average_native_deceleration_mps2':finite(obj.contents[1].values[2]),'archive_class_version':source_version,
        'braking_formula_code':obj.contents[12].values[0],
        'braking_points':[dict(zip(['speed_kmh','native_deceleration_mps2','native_secondary_deceleration_mps2'],p.contents[0].values)) for p in brakes],
        'resistance_coefficients_excl':[finite(v) for v in obj.contents[5].values],
        'resistance_coefficients_incl':[finite(v) for v in obj.contents[7].values],
        'use_maximum_drawbar_force':bool(obj.contents[15].value&1),'use_minimum_time_to_hold_speed':bool(obj.contents[15].value&2)}
    result.update({field:finite(obj.contents[index].values[slot]) if index<len(obj.contents) else None for field,(index,slot) in TRAIN_SCALARS.items()})
    if source_version<16:result['decoded_class_version']=16
    return result


def require_current_category(obj):
    from .stock_versions import check
    if obj.clazz.version!=19:raise APIError('CATEGORY_VERSION','Category controls require the current original 1.7 v19 record; no old Category migration is performed.',obj.clazz.version)
    check(obj,['ii','@','@','ii','fff','f','f','fff','f','i','@','i','@','@','@','f','i','@','ffii','i','f','f','i','i','ff'])


def set_category_extended(obj,args,definitions):
    from .native_colors import make_color
    if any(getattr(args,field) is not None for field in CATEGORY_ADVANCED_FIELDS):require_current_category(obj)
    for field,index in [('foreground_color',2),('background_color',17)]:
        value=getattr(args,field)
        if value is not None:obj.contents[index].values[0]=make_color(definitions,value)
    if args.departure_process_starts_at_departure_time is not None:
        obj.contents[22].values[0]=int(not args.departure_process_starts_at_departure_time)


def category_record(obj):
    source_version=obj.clazz.version
    if source_version>19:raise APIError('CATEGORY_VERSION','Unsupported original Category archive version.',source_version)
    if source_version<11:raise APIError('CATEGORY_VERSION','This Category layout is outside the current controls scope.',source_version)
    if source_version==19:require_current_category(obj)
    from .native_colors import color_record
    result={'name':w.string(obj.contents[1].value),'archive_class_version':source_version}
    result.update({field:finite(obj.contents[index].values[slot]) if index<len(obj.contents) else None for field,(index,slot) in CATEGORY_SCALARS.items()})
    result.update({field:bool(obj.contents[0].values[1]&bit) for field,bit in CATEGORY_FLAGS.items()})
    for field,(index,_,_) in CATEGORY_TABLES.items():
        wrapper=obj.contents[index].value
        rows=w.elements(wrapper.contents[0].value) if wrapper and wrapper.contents[0].value else []
        keys=['delay_s','priority'] if field=='delay_priorities' else ['minimum','maximum','probability_percent']
        result[field]=[dict(zip(keys,p.contents[0].values)) for p in rows]
    result.update({'foreground_color':color_record(obj.contents[2].value),'background_color':color_record(obj.contents[17].value) if len(obj.contents)>17 else None,
        'departure_process_starts_at_departure_time':obj.contents[22].value<1 if len(obj.contents)>22 else None})
    result['pre_departure_process_time_s']=None if result['departure_process_starts_at_departure_time'] is None else 0. if result['departure_process_starts_at_departure_time'] else finite(result['departure_process_time_s'])
    for period in ['early','delayed']:
        result['dwell_variation_'+period+'_unit']={0:'seconds',1:'percent'}.get(result['dwell_variation_'+period+'_unit_code'])
    return result
