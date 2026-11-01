"""Template-backed empty-graph project initialization; pure bytes, never publication.

The caller supplies six separately named SHA-bound resources. No bundled donor,
filesystem access, native execution, inferred timetable or physical calibration.
"""
import copy
from . import writer as w, catalogs as c, course_factories as cf
from .zero_generation import topology as tp
from .multi_document import core as cd
from .operating_chain_workflow import compose_operating_chain, SOURCE_KEYS
from .final_stop_workflow import compose_final_stop_chain
from .zero_operations import run_bundle as rb
from .graphic_alignment import validate_generated_signal_alignment

PROJECT_KEYS = {'infrastructure','vehicles','course_template_id','timetable_template_key',
                'train_types','speed_type','plan','run_configuration'}
PROFILES = {'single_document_pass': compose_operating_chain,
            'single_document_final_stop': compose_final_stop_chain}

def need(ok, message):
    if not ok:
        raise ValueError(message)

def validate_candidate(members, *, project, chain_receipt):
    """Check eight-member layout, seven archive roles and the distinct text run.

    Pure in-memory data contract. Not a filesystem/publisher safety review.
    Nested archive members remain valid; no flattening or persistence occurs.
    """
    need(type(members) is dict and len(members)==8, 'Exactly eight candidate members required')
    cfg = dict(project['run_configuration'])
    run_name = cfg.pop('run_filename')
    doc = 'OTDocuments/'+project['infrastructure']['document_name']+'.opentrack'
    catalogs = {role:'OTData/infrastructure.'+role for role in rb.CATALOG_KEYS}
    roles = {doc:'document', **{path:role for role,path in catalogs.items()}}
    need(run_name not in roles, 'Run member aliases an archive role')
    roles[run_name] = 'run'
    need(set(members)==set(roles), 'Candidate names do not match exact eight roles')
    folded=[]
    for name,blob in members.items():
        rb.relative(name)
        need(type(blob) is bytes and bool(blob), 'Nonempty immutable candidate member required')
        folded.append(name.casefold())
    need(len(set(folded))==8, 'Candidate case-insensitive member collision')
    need(not any(b.startswith(a+'/') for a in folded for b in folded if a!=b),
         'Candidate file/directory collision')
    rb.relative(cfg['output_directory']); out=cfg['output_directory'].casefold()
    need(all(out!=p and not out.startswith(p+'/') and not p.startswith(out+'/') for p in folded),
         'Output directory overlaps candidate member')
    archives = {name:blob for name,blob in members.items() if name!=run_name}
    document,_=w.load_next_compatible(archives[doc])
    for model in c.array(document.contents[2].value):
        if w.kind(model)=='OTSignalModel':
            validate_generated_signal_alignment(model)
    run = members[run_name]
    
    rb.records(run)
    fresh_run = rb.verify_run(run, archives, catalog_paths=catalogs, document_paths=[doc],
                              train_types=project['train_types'], **cfg)
    bindings = rb.verify_archive_bindings(run, archives, catalog_paths=catalogs, document_paths=[doc])
    rb.verify_manifest(run, archives, chain_receipt['run'])
    manifest={name:{'sha256':cd.sha(blob),'bytes':len(blob)} for name,blob in members.items()}
    need(chain_receipt['output_sha256']=={name:r['sha256'] for name,r in manifest.items()},
         'Eight-member chain receipt mismatch')
    need(chain_receipt['counts']['members']==8, 'Chain receipt must count run plus seven archives')
    need(chain_receipt['cross_file_bindings']==bindings, 'Chain dependency receipt mismatch')
    return {'member_roles':roles,'members':manifest,'archive_member_count':7,'total_member_count':8,
            'run_member':run_name,'run_format':'native_ascii_records',
            'archive_manifest':fresh_run['members'],'dependency_bindings':bindings,
            'run_validation':'dedicated record/configuration/archive-binding validation',
            'saved':False,'filesystem_safety_review':False,'native_runtime_verified':False}

def initialize_project(sources, *, expected_hashes, profile, project):
    """Return (eight immutable member bytes, unified initialization receipt).

    project has exactly PROJECT_KEYS, using the selected existing chain contract.
    Physical model acceptance remains explicit in project['vehicles']; source
    paths belong to the external SHA-binding adapter, never this pure function.
    """
    need(type(profile) is str and profile in PROFILES, 'Unknown initialization profile')
    need(type(sources) is dict and set(sources)==SOURCE_KEYS and
         all(type(v) is bytes for v in sources.values()), 'Six immutable resource roles required')
    actual = {k:cd.sha(v) for k,v in sources.items()}
    need(type(expected_hashes) is dict and expected_hashes==actual,
         'Exact complete resource SHA bindings required')
    need(type(project) is dict and set(project)==PROJECT_KEYS, 'Exact complete project contract required')
    
    selected = copy.deepcopy(project)
    builder = tp.Builder(sources['shapes'])
    blank, version, removed = tp.blank_container(sources['header'], builder)
    blank_bytes = w.dump_verified(blank, version)
    fresh_blank,_ = w.load_next_compatible(blank_bytes)
    tp.doc_layout(fresh_blank)
    need(not c.array(fresh_blank.contents[2].value), 'Derived shell is not empty')
    
    depot,_ = w.load_next_compatible(sources['depot_template'])
    trains,_ = w.load_next_compatible(sources['trains_template'])
    courses,_ = w.load_next_compatible(sources['courses_template'])
    table,_ = w.load_next_compatible(sources['timetable_template'])
    engine_rows = c.engine_items(depot); train_rows = c.train_items(trains)
    course_rows = c.course_items(courses); tt_rows = cf.timetable(table)
    need(engine_rows and train_rows and course_rows and tt_rows, 'Nonempty typed template roles required')
    need(selected['course_template_id'] in [c.text(o.contents[0].value) for o in course_rows],
         'Explicit Course template identity missing')
    need(selected['timetable_template_key'] in tt_rows, 'Explicit Timetable template key missing')
    vehicle_spec = selected['vehicles']
    for key, rows, slot in (('engine_template', engine_rows, 1), ('train_template', train_rows, 0),
                            ('category_template', c.array(trains.contents[1].value), 1)):
        need(vehicle_spec[key] in [c.text(o.contents[slot].value) for o in rows],
             'Explicit vehicle template identity missing: '+key)
    resource_roots = {'header':fresh_blank,'shapes':w.load_next_compatible(sources['shapes'])[0],
                      'depot_template':depot,'trains_template':trains,
                      'courses_template':courses,'timetable_template':table}
    selections = {'header':{'selection':'opaque header only; old graph discarded'},
                  'shapes':{'selection':'required native class prototypes'},
                  'depot_template':{'engine':vehicle_spec['engine_template']},
                  'trains_template':{'train':vehicle_spec['train_template'],'category':vehicle_spec['category_template']},
                  'courses_template':{'course_id':selected['course_template_id']},
                  'timetable_template':{'key':selected['timetable_template_key']}}
    resources = {k:{'sha256':actual[k],'bytes':len(sources[k]),
                    'root_class':w.kind(root),'root_class_version':root.clazz.version,
                    'selected_identity':selections[k]} for k,root in resource_roots.items()}
    
    
    members, detail = PROFILES[profile](sources, expected_hashes=actual, **selected)
    need(type(members) is dict and len(members)==8 and all(type(v) is bytes for v in members.values()),
         'Initialization requires eight immutable members')
    candidate = validate_candidate(members, project=selected, chain_receipt=detail)
    manifest = candidate['members']
    need(detail['output_sha256']=={k:r['sha256'] for k,r in manifest.items()}, 'Member receipt mismatch')
    need(detail['fresh_archive_reload_verified'] is True and detail['saved'] is False,
         'Only verified unsaved chain candidates allowed')
    need({k:cd.sha(v) for k,v in sources.items()}==actual and project==selected,
         'Caller resources or project specification changed')
    return members, {
        'schema':'project-initialization/1','profile':profile,'source_sha256':actual,
        'resource_manifest':resources,
        'member_roles':candidate['member_roles'],
        'candidate_validation':candidate,
        'dependency_bindings':copy.deepcopy(detail['cross_file_bindings']),
        'physical_inheritance':copy.deepcopy(detail['vehicles']),
        'next_write_contract':{'state':'not_enabled_pending_independent_publication_review',
            'input':'the actual eight member bytes returned by this function, not receipt hashes',
            'required_members':manifest,
            'execution_root':selected['run_configuration']['execution_root'],
            'path_style':selected['run_configuration']['path_style'],
            'run_member':selected['run_configuration']['run_filename'],
            'requirements':['independently reviewed member/path mapping and failure handling',
                'explicit fresh target; preserve source resources',
                'save and reload all eight bytes with catalog/document/run references',
                'authorized native load/run acceptance remains separate']},
        'resource_roles':{
            'header':'opaque native Document header; old graph removed in derived copy',
            'shapes':'native class/shape prototypes; no source geometry retained',
            'depot_template':'explicit Engine physical type donor',
            'trains_template':'explicit Train/Category and inherited whole-train model',
            'courses_template':'explicit Course record structure donor',
            'timetable_template':'explicit Timetable row structure donor'},
        'initialization':{'from_empty_graph':True,'template_free':False,
            'derived_empty_shell_sha256':cd.sha(blank_bytes),'source_graph_objects_removed':removed,
            'opaque_header_preserved':True,'physical_model':'explicitly accepted template inheritance',
            'physical_calibration_verified':False,'user_layout_inferred':False},
        'counts':dict(detail['counts']),'members':manifest,'chain_receipt':detail,
        'source_bytes_unchanged':True,'project_specification_unchanged':True,
        'fresh_archive_reload_verified':True,'saved':False,'publication_review_pending':True,
        'native_application_executed':False,'native_runtime_ready':False,
        'scope':'Single-document explicit project candidate; empty graph with native templates, not zero-byte/template-free creation or simulation completion'}
