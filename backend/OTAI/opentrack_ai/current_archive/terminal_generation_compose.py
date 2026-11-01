"""Pure composition for explicitly selected terminal-area profile.
No filesystem writes; existing shared atomic publisher owns the only commit.
"""
from .network_generation_tools import NetworkGeneration
from .tools import sha
from . import writer as w,course_factories as cf
from .zero_operations import vehicle_catalogs as vehicles,speed_preferences,run_bundle
from .zero_terminal import terminal_areas,area_operations,circulation

def compose_terminal(args,blobs):
    profile=args.terminal_profile
    if profile is None:raise ValueError('Explicit terminal profile required')
    members,network=NetworkGeneration.compose(args,blobs)
    filename=args.document_name+'.opentrack';ids=network['topology']['vertex_end_ids'];edges=network['topology']['edge_ids']
    def end(ref):
        if ref.vertex not in ids:raise ValueError('Unknown symbolic terminal EndRef')
        return ids[ref.vertex][ref.side]
    specs=[]
    for station in profile.stations:
        spec=station.model_dump(exclude={'reference_end','ordinary_ends','stop'})
        spec.update(reference_end_id=end(station.reference_end),ordinary_end_ids=[end(x)for x in station.ordinary_ends],stop=None)
        if station.stop:
            stop=station.stop
            if stop.area_edge not in edges:raise ValueError('Unknown symbolic terminal area Edge')
            spec['stop']={'entry_end_id':end(stop.entry),'exit_end_id':end(stop.exit),'area_edge_id':edges[stop.area_edge],'length_m':stop.length_m,'exit_signal_name':stop.exit_signal_name,'direction':stop.direction}
        specs.append(spec)
    doc,station_blob,area_report,_point_baseline=terminal_areas.bind_areas(members[filename],specs)
    vehicle,vehicle_report=vehicles.generate_vehicle_catalogs(blobs['depot_template'],blobs['trains_template'],args.vehicles.model_dump())
    plan=[p.model_dump()for p in profile.plan];chains=[p.model_dump()for p in profile.chains];dest=members[args.catalog_filename]
    services,service_report=area_operations.generate_service_catalogs({'courses_template':blobs['courses_template'],'timetable_template':blobs['timetable_template'],'trains':vehicle['trains'],'depot':vehicle['depot'],'stations':station_blob,'document':doc,'dest':dest,'run_template':blobs['run_template']},area_specs=specs,course_template_id=args.course_template_id,timetable_template_key=args.timetable_template_key,document_name=args.document_name,plan=plan,speed_type=args.speed_type)
    dependencies={'document':doc,'dest':dest,**vehicle,**services,'stations':station_blob,'connection_template':blobs['connection_template'],'run_template':blobs['run_template']}
    final_tt,connection_report=circulation.bind_turnrounds(dependencies,expected_hashes={k:sha(b)for k,b in dependencies.items()},area_specs=specs,chains=chains,document_name=args.document_name)
    actual={k:connection_report[k]for k in ('courses','chains','pairs','connection_records','roots','tails','internal_courses')}
    decoded_rows=cf.timetable(w.load_next_compatible(final_tt)[0])
    actual.update(timetable_rows=len(decoded_rows),terminal_stops=sum(bool(row.contents[10].value&1)for row in decoded_rows.values()))
    if actual!=profile.expected_counts.model_dump():raise ValueError('Decoded terminal connection/visit counts differ from explicit expectation')
    if any(x['minimum_turnround_s']!=profile.minimum_turnround_s for x in connection_report['chains_detail']):raise ValueError('Actual Category minimum turnround differs from explicit reviewed 420-second profile')
    all_times=[v['absolute_seconds']for p in plan for v in p['visits']]
    if min(all_times)<profile.window_start_s or max(all_times)>=profile.window_end_s:raise ValueError('Terminal planned visits outside declared single-day window')
    services['timetable']=final_tt;members[filename]=doc
    members.update({args.operating_prefix+'.'+key:value for key,value in {**vehicle,**services,'stations':station_blob}.items()})
    report={'station_profile':'terminal_area','network':network,'station_binding':area_report,'area_specs':specs,'vehicle_types':vehicle_report,'services':service_report,'circulation':connection_report,'expected_counts':profile.expected_counts.model_dump(),'chains':chains,'planned_window_seconds':[min(all_times),max(all_times)],
        'counts':{**network['counts'],'stations':len(specs),'train_definitions':len(args.vehicles.train_names),**actual},
        'run_file_generated':False,'run_train_types_required':speed_preferences.read_train_types(blobs['run_template']),'physical_fleet_circulation_proven':False,'platform_stops_supported':False,'terminal_stop_static_configuration_checked':True,'actual_terminal_stops_observed':False,'calibrated_vehicle_dynamics':False,'native_simulation_executed':False,'complete_project_validated':False,'complete_runtime_configuration':False,'execution_root_verified':False}
    if args.run_configuration:
        cfg=args.run_configuration
        catalog_paths={key:args.operating_prefix+'.'+key for key in ('depot','trains','stations','courses','timetable')};catalog_paths['dest']=args.catalog_filename
        run,run_report=run_bundle.build_run(members,catalog_paths=catalog_paths,document_paths=[filename],train_types=speed_preferences.read_train_types(blobs['run_template']),**cfg.model_dump(exclude={'run_filename'}))
        if run_report['window']['start_seconds']!=profile.window_start_s or run_report['window']['stop_seconds']!=profile.window_end_s:raise ValueError('Terminal profile run must exactly match declared 0..86400 window')
        static=run_bundle.verify_archive_bindings(run,members,catalog_paths=catalog_paths,document_paths=[filename]);run_bundle.verify_manifest(run,members,run_report)
        members[cfg.run_filename]=run;report.update(run_file_generated=True,run_binding=run_report,run_archive_bindings=static,output_directory_created_on_save=cfg.output_directory)
    return members,report
