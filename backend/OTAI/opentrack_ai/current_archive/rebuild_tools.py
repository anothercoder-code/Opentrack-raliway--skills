"""Explicit rebuilt data-tool registration; no native execution hooks."""
from importlib import import_module

MODULES = ('multi_document_tools', 'multistation_operating_tools', 'consist_workflow_tools', 'project_workflow_tools', 'signal_protection_tools', 'branch_network_tools', 'shunting_workflow_tools', 'multistation_timetable_tools', 'disturbance_tools', 'simulation_run_tools', 'native_result_tools', 'incident_set_tools', 'infrastructure_incident_tools', 'signal_type_tools', 'full_multidoc_grid_tools', 'shunting_spatial_tools', 'current_shunting_tools', 'finite_itinerary_tools', 'finite_topology_tools', 'saved_reference_tools', 'infrastructure_chain_tools', 'operating_chain_tools', 'final_stop_tools', 'signal_saved_parameter_tools', 'project_initialization_tools', 'project_publication_tools', 'station_documents_tools', 'movement_edit_tools', 'route_edit_tools', 'itinerary_edit_tools', 'segmented_shunting_tools', 'overlap_composition_tools')
MODULES += (
    'empty_project_tools',
    'route_lifecycle_tools',
    'path_lifecycle_tools',
    'itinerary_lifecycle_tools',
    'native_itinerary_import_tools',
    'shunting_lifecycle_tools',
    'railml_timetable_tools',
    'movement_application_tools',
    'native_editor_tools',
    'geometry_edit_candidate_tools',
    'station_candidate_workflow',
    'operating_plan_edit_tools',
    'native_course_platform_rebind',
    'timetable_exchange_import',
    'native_timetable_import_tools',
    'native_service_import_tools',
    'rolling_stock_exchange_import',
    'native_rolling_stock_import_tools',
    'network_operating_plan',
    'saved_geometry_tools',
    'station_reference_edit',
    'saved_plot_tools',
    'saved_page_layout',
    'saved_worksheet_images',
    'saved_rich_labels',
    'saved_temporary_labels',
    'native_monitoring_tools',
    'worksheet_finder_tools',
    'native_occupation_groups_tools',
    'native_interlocking_tools',
    'native_otd_reservation_effect',
    'native_join_entry_mode',
    'native_platform_choice_tools',
    'native_timetable_visit_tools',
    'native_circulation_tools',
    'native_headway_tools',
    'native_headway_sweep_tools',
    'native_delay_batch_tools',
    'native_preferences_tools',
    'station_exchange_tools',
    'native_topology_description_tools',
    'infrastructure_railml_tools',
    'infrastructure_ivt_tools',
    'route_discovery_tools',
    'route_fetch_tools',
    'dispatching_rules_otd',
    'pathfinding_tools',
    'signal_operating_tools',
)

def tool_definitions(root):
    definitions = []
    for module in MODULES:
        definitions.extend(import_module("." + module, __package__).tool_definitions(root))
    names = [row[0] for row in definitions]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate rebuilt data-tool names")
    return definitions
