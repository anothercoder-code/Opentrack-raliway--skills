"""Lazy service facade: schemas and independent tools need no archive vendor."""
from pathlib import Path
import os
from .lazy_native import LazyComponent

class Service:
    def __init__(self, root, allow_apply=False, allow_runtime=False):
        
        
        self.root=Path(os.path.abspath(root)) if os.name=='nt' else Path(root).resolve()
        self.allow_apply=allow_apply
        self.allow_runtime=allow_runtime
        self.work=self.root/'OTAI/workspaces'
        self._native=LazyComponent('.native_service', 'Service', self.root, allow_apply, allow_runtime)

    def __getattr__(self, name):
        return getattr(self._native, name)

    def function_coverage(self, args):
        from .coverage import read_coverage
        return read_coverage(self.root,args)

    def replica_status(self, args):
        """Read packaged data-function requirements without a legacy decoder."""
        import json
        from .errors import APIError
        path=Path(__file__).resolve().parents[1]/'replica/requirements.json'
        if not path.is_file():raise APIError('REQUIREMENTS_UNAVAILABLE','Packaged requirements are unavailable')
        data=json.loads(path.read_text(encoding='utf8'));rows=data['requirements']
        if args.query:rows=[row for row in rows if args.query.casefold() in json.dumps(row,ensure_ascii=False).casefold()]
        return {**{k:v for k,v in data.items() if k!='requirements'},'items':rows[args.offset:args.offset+args.limit],
                'total_count':len(rows),'offset':args.offset,'has_more':args.offset+args.limit<len(rows),
                'next_offset':args.offset+args.limit if args.offset+args.limit<len(rows) else None}

    def schemas(self, args):
        from .catalog import SCHEMAS, EXPECTED_EXE_SHA256
        from .errors import APIError
        if args.name is None:return {'contracts':SCHEMAS,'audited_executable_sha256':EXPECTED_EXE_SHA256}
        if args.name not in SCHEMAS:raise APIError('SCHEMA_NOT_FOUND','Choose one of the exposed audited contracts.',list(SCHEMAS))
        return {'name':args.name,**SCHEMAS[args.name]}

    def capabilities(self, args):
        from .errors import APIError
        from . import __version__
        from .catalog import TARGET_BASELINE
        try:
            result=self._native.capabilities(args)
            from .legacy_geometry_guard import BLOCKED_TOOLS, CODE
            result['legacy_geometry_mutation']={'status':'blocked','code':CODE,'tools':sorted(BLOCKED_TOOLS),'independent_of_missing_dependencies':True}
            return self._host_capability_report(result)
        except APIError as error:
            if error.code!='NATIVE_DEPENDENCY_MISSING':raise
            result={'version':__version__,'root':str(self.root),'native_archive_status':'partial_current_archive_available','legacy_project_status':'blocked','legacy_geometry_mutation':{'status':'blocked','code':'LEGACY_GEOMETRY_DISABLED','independent_of_missing_dependencies':True},
                    'target_baseline':{**TARGET_BASELINE,'stock_file_verified':False,'stock_runtime_acceptance':False},
                    'legacy_project_blocker':error.as_dict(),'native_archive_status_scope':'Current allowlisted file and catalog-bundle operations',
                    'current_archive':{'codec':'independent stdlib implementation','inspect_current_catalogs':True,'engine_speed_copy_save_reload':True,'stock_scalar_setters':True,'explicit_engine_clone':True,'description_and_local_path':True,'course_timetable_catalog_bundle':True,'existing_timetable_eight_primitive_setters':True,'formation_raw_append_remove':True,'guarded_local_path_append':True,'path_scope':'actual project inventory + selected run list + resolved supplied external labels; not universal project integrity','station_existing_raw_setters':True,'route_same_movement_template_factory':True,'incident12_train_archive_create_edit':True,'incident_scope':'run CourseFile/TrainFile binding and selected enabled Course to actual Train; not runtime dependency closure','full_project_graph':False},
                    'independent_information_generation':True,
                    'native_simulation_verified':False,'full_replica_complete':False,
                    'apply_enabled':self.allow_apply,'runtime_read_enabled':self.allow_runtime,
                    'gui_operations':False,'runtime_memory_writes':False,
                    'validation_boundary':'Current archive actions verify allowlisted fields, archive references and fresh saved-file reload; catalog bundles disclose external documents. JSON preparation alone is not archive persistence. Neither establishes runtime simulation.'}

            return self._host_capability_report(result)

    @staticmethod
    def _host_capability_report(result):
        """Separate registered code domains from this host's filesystem support.

        This only reports prerequisites. It does not enable a fallback or certify
        native Windows, publication, a kernel syscall or the target filesystem.
        """
        import sys
        from .current_archive.platform_support import filesystem_capabilities
        result=dict(result)
        archive=dict(result.get('current_archive',{}))
        
        
        operations={k:v for k,v in archive.items() if type(v)is bool}
        archive={k:v for k,v in archive.items() if type(v)is not bool}
        archive['registered_operations']=operations
        archive['registration_is_host_availability']=False
        fs=filesystem_capabilities()
        
        
        archive.update({k:False for k in operations})
        if 'inspect_current_catalogs' in operations:
            archive['inspect_current_catalogs']=bool(operations['inspect_current_catalogs'] and fs['secure_read_available'])
        archive['legacy_boolean_scope']='Compatibility keys retained; false for mixed or unverified host operations. Use registered_operations for implementation inventory and host_availability for filesystem prerequisites.'
        linux=sys.platform.startswith('linux')
        archive['host_availability']={
            'filesystem_primitives':fs,
            'archive_inspection_and_file_backed_preview':{
                'available':fs['secure_read_available'],
                'scope':'Existing ArchiveTools secure input reading only; individual domain checks still apply'},
            'fresh_copy_save':{
                'primitives_available':fs['save_copy_primitives_available'],
                'publication_or_filesystem_acceptance_verified':False},
            'atomic_catalog_bundle_save':{
                'linux_only_implementation':True,
                'host_is_linux':linux,
                'platform_prerequisites_present':linux and fs['save_copy_primitives_available'],
                'available_on_this_host':None if linux and fs['save_copy_primitives_available'] else False,
                'runtime_commit_verified':False,
                'requirements':'Linux libc renameat2 plus target filesystem atomic no-replace support; checked during normal save'},
            'pure_in_memory_byte_cores':{
                'filesystem_guard_applies':False,
                'native_windows_execution_verified':False},
            'complete_initialization_project_publish':{
                'available_on_this_host':bool(fs.get('nested_project_publication_available',False)),
                'tool':'opentrack_initialize_project',
                'scope':'Fresh Windows x64 local NTFS single-document eight-member project; exact target bindings, atomic no-replace commit and actual byte/reference reload. Native runtime validation is separate.'},
            'multi_document_project_inventory':{
                'available_on_this_host':bool(fs.get('complete_project_inventory_available',False)),
                'scope':'Complete bounded native-handle tree inventory plus per-member SHA input reading; no native simulation certification'},
            'complete_station_documents_project_publish':{
                'available_on_this_host':bool(fs.get('nested_project_publication_available',False)),
                'tool':'opentrack_initialize_station_documents_project',
                'scope':'Fresh Windows x64 local NTFS bounded linear station-document project; one station per document, shared catalogs, explicit forward final-stop plan'},
            'new_preview_interface_export_enabled':False,
            'unsafe_filesystem_fallback_enabled':False}
        result['current_archive']=archive
        archive['graphic_placement_generation_contract']={
            'fields':['x','y','angle','alignment_x','alignment_y'],
            'reviewed_alignment_pairs':[[0,0],[1,0],[2,0],[0,3],[0,4]],
            'full_native_enum_domain_recovered':False,
            'legacy_width_height_placement_keys':'rejected_with_explicit_migration_guidance',
            'new_station_signal_profile':[0,0],
            'native_gui_signal_creation_default_verified':False,
            'existing_native_alignment':'preserved_by_generic_read_and_source_clone',
            'genuine_canvas_dimensions_changed':False}
        result['native_inspector_guard']={
            'component':'separate English-only native artifact',
            'automatic_skill_or_mcp_launch':False,
            'check_mode':'strict_PE_file_validation_only',
            'launch_mode':'future_explicit_new_child_only',
            'hook_scope':'WH_GETMESSAGE_on_the_new_child_own_verified_thread_only',
            'attach_existing_pid_supported':False,
            'runtime_verified':False}
        result['current_revision_validation']={
            'scope':'static and offline only; no OpenTrack process started or operated',
            'native_application_executed':False,
            'native_gui_editing_safety_verified':False,
            'historical_winmulti1_scope':'journey observations retained; later station double-click Inspector crash prevents GUI editing safety acceptance'}
        result['capability_reporting_scope']='Registered implementation inventory is not host filesystem availability, publication approval or native runtime certification. apply_enabled/runtime_read_enabled are configured permissions only.'
        return result
