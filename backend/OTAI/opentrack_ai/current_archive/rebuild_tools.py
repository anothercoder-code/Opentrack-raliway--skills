"""Explicit rebuilt data-tool registration; no native execution hooks."""
from importlib import import_module

MODULES = ('multi_document_tools', 'multistation_operating_tools', 'consist_workflow_tools', 'project_workflow_tools', 'signal_protection_tools', 'branch_network_tools', 'shunting_workflow_tools', 'multistation_timetable_tools', 'disturbance_tools', 'simulation_run_tools', 'native_result_tools', 'incident_set_tools', 'infrastructure_incident_tools', 'signal_type_tools', 'full_multidoc_grid_tools', 'shunting_spatial_tools', 'current_shunting_tools', 'finite_itinerary_tools', 'finite_topology_tools', 'saved_reference_tools', 'infrastructure_chain_tools', 'operating_chain_tools', 'final_stop_tools', 'signal_saved_parameter_tools', 'project_initialization_tools', 'project_publication_tools', 'station_documents_tools')

def tool_definitions(root):
    definitions = []
    for module in MODULES:
        definitions.extend(import_module("." + module, __package__).tool_definitions(root))
    names = [row[0] for row in definitions]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate rebuilt data-tool names")
    return definitions
