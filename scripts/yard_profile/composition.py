"""Compose and validate the complete bounded seventeen-member yard in memory."""
import copy
from . import services, topology, graphics as pg, text as text_graphics
from opentrack_ai.current_archive import writer as w, catalogs as c, course_factories as cf
from opentrack_ai.current_archive.prepare_contract import auxiliary as aux
from opentrack_ai.current_archive.zero_operations import run_bundle as rb
NORMAL_RUN = 'eighttracks.run'
FAILURE_RUN = 'failure.run'
NORMAL_CATALOGS = dict(services.CATALOGS)
FAILURE_CATALOGS = {role: 'OTData/failure.' + role for role in rb.CATALOG_KEYS}
RECTS = tuple((580., y, 240., 16.) for y in (82., 182., 322., 422.))
BREAKS = {'normal': '00:00:00', 'failure': '00:00:00'}
def need(ok, message):
    if not ok:
        raise ValueError(message)

def manifest(files):
    return services.manifest(files)

def append_islands(blob):
    root, version, models, byid = pg._read(blob)
    need(len(models) == 209 and not any(w.kind(obj) == 'OTRectModel' for obj in w.objects(root)),
         'Expected expanded209-model railway without preexisting rectangles')
    color = pg._palette(root)
    start = max(byid) + 1
    added = [pg._rectangle(start + i, rect, color) for i, rect in enumerate(RECTS)]
    array = root.contents[2].value
    array.contents[0].value = len(models) + 4
    array.contents.extend(w.TypedGroup([b'@'], [model]) for model in added)
    output = w.dump_verified(root, version)
    checked, cv, members, _ = pg._read(output)
    rects = [obj for obj in members if w.kind(obj) == 'OTRectModel']
    need(len(members) == 213 and rects == members[-4:] and
         [obj.contents[0].value for obj in rects] == list(range(start, start + 4)),
         'Exactly four new suffix island graphics required')
    validation = [pg._inspect_rect(obj, rect) for obj, rect in zip(rects, RECTS)]
    need({id(obj) for obj in w.objects(checked) if w.kind(obj) == 'OTRectModel'} == {id(obj) for obj in rects},
         'Hidden rectangle reference outside model collection')
    checked_array = checked.contents[2].value
    checked_array.contents = checked_array.contents[:-4]
    checked_array.contents[0].value = len(models)
    need(w.dump_verified(checked, cv) == blob, 'Stripping only the four added Rects must restore exact original bytes')
    return output, {'input_sha256': services.sha(blob), 'output_sha256': services.sha(output),
        'new_ids': list(range(start, start + 4)), 'visible_rects': [list(rect) for rect in RECTS],
        'validation': validation, 'stripping_rects_restores_exact_input_bytes': True,
        'railway_fields_or_objects_changed': False, 'native_visibility_runtime_verified': False}

def label_entries(sign):
    return ([{'key': 'station', 'text': sign, 'rect': [570, 565, 260, 35]}] +
        [{'key': 'track_' + lane['name'], 'text': 'Track ' + lane['name'],
          'rect': [600, lane['y'] + 8, 100, 27]} for lane in topology.LANES] +
        [{'key': 'platform_' + str(i + 1), 'text': 'Platform P' + str(i + 1),
          'rect': [710, rect[1] - 6, 100, 27]} for i, rect in enumerate(RECTS)] +
        [{'key': 'down_main', 'text': 'Down Main', 'rect': [20, 240, 180, 27]},
         {'key': 'up_main', 'text': 'Up Main', 'rect': [20, 340, 180, 27]}])

def append_drawings(blob, sign, header):
    with_rects, rectangles = append_islands(blob)
    output, labels = text_graphics.add_labels(with_rects, label_entries(sign), template_document=header)
    restored_rects, labels_inverse = text_graphics.strip_labels(output, labels)
    need(restored_rects == with_rects, 'Removing fifteen native Labels must recover exact four-Rect bytes')
    checked, version, models, _ = pg._read(restored_rects)
    array = checked.contents[2].value
    array.contents = array.contents[:-4]
    array.contents[0].value = len(models) - 4
    need(w.dump_verified(checked, version) == blob, 'Removing only added Labels and Rects must recover exact209-model railway bytes')
    return output, {'rectangles': rectangles, 'labels': labels, 'labels_inverse': labels_inverse,
        'native_label_count': 15, 'native_rectangle_count': 4, 'final_models': 228,
        'stripping_all_drawings_restores_exact_railway_bytes': True,
        'input_sha256': services.sha(blob), 'output_sha256': services.sha(output),
        'railway_fields_or_objects_changed': False, 'native_visibility_runtime_verified': False}

def validate_drawing_positions(blob, sign):
    root, version, models, byid = pg._read(blob)
    need(len(models) == 228, 'Each final station needs exactly209 railway models+4Rect+15Label')
    labels = [model for model in models if w.kind(model) == 'OTLabelModel']
    expected = {item['text']: text_graphics._entry(item) for item in label_entries(sign)}
    need(len(labels) == 15, 'Exactly fifteen English native Labels required')
    seen = set()
    for model in labels:
        payload = text_graphics._data(model.contents[7].value)
        need(payload.startswith(text_graphics.RTF_PREFIX) and payload.endswith(text_graphics.RTF_SUFFIX),
             'Actual Label rich-text profile differs')
        text = payload[len(text_graphics.RTF_PREFIX):-len(text_graphics.RTF_SUFFIX)].decode('ascii')
        need(text in expected and text not in seen, 'Unknown or duplicate station/track/platform/main text')
        text_graphics._inspect(model, expected[text], model.contents[0].value)
        seen.add(text)
    need(seen == set(expected), 'The complete exact English drawing-label set is required')
    projected, labels_proof = text_graphics.strip_yard_labels(blob)
    no_labels, cv, rm, _ = pg._read(projected)
    rects = [model for model in rm if w.kind(model) == 'OTRectModel']
    need(len(rm) == 213 and rects == rm[-4:], 'Four island rectangles must precede the Label suffix')
    rect_proof = [pg._inspect_rect(rect, geometry) for rect, geometry in zip(rects, RECTS)]
    return {'label_count': 15, 'exact_text_and_frames_verified': True,
            'labels_projection': labels_proof, 'rectangles': rect_proof}

def rewrite_run(run, changes, additions=()):
    """Exact key/value edits with byte-preserved unrelated records and ordering."""
    rows = aux.records(run)
    need(type(changes) is dict and all(type(key) is str and type(value) is tuple and len(value) == 2
                                     for key, value in changes.items()), 'Explicit old/new typed value map required')
    seen, output, journal = set(), [], []
    for key, value, raw in rows:
        if key not in changes:
            output.append(raw)
            continue
        old, new = changes[key]
        need(value == old and key not in seen, 'Expected exact singleton typed old value: ' + str(key))
        seen.add(key)
        newline = b'\r\n' if raw.endswith(b'\r\n') else b'\n'
        updated = (key + '#' + new + '#').encode('ascii') + newline
        output.append(updated)
        if old != new:
            journal.append({'key': key, 'old': old, 'new': new})
    need(seen == set(changes), 'Missing explicitly rebound typed keys')
    existing = {key for key, value, raw in rows if key is not None}
    added_keys = set()
    for key, value in additions:
        need(key not in existing and key not in added_keys, 'Added native key already exists')
        output.append((key + '#' + value + '#\n').encode('ascii'))
        added_keys.add(key)
        journal.append({'key': key, 'old': None, 'new': value})
    result = b''.join(output)
    after = aux.records(result)
    need(b''.join(raw for key, value, raw in rows if key not in changes) ==
         b''.join(raw for key, value, raw in after if key not in changes and key not in added_keys),
         'Unrelated typed records changed')
    return result, journal

def with_break(run, clock):
    need(clock == '00:00:00',
         'This unattended recipe has no in-window breakpoint')
    existing = {key for key, value, raw in aux.records(run)}
    added = ('Delay Scenario', 'Break Day Offset', 'Break Time')
    need(not any(key in existing for key in added),
         'Source run must not contain an unexpected scenario counter or breakpoint')
    
    
    
    rows = aux.records(run)
    inserted, output = False, []
    for key, value, raw in rows:
        if not inserted and key in rb.TARGET_KEYS:
            output.extend((b'Delay Scenario#0#\n', b'Break Day Offset#0#\n',
                           ('Break Time#' + clock + '#\n').encode('ascii')))
            inserted = True
        output.append(raw)
    need(inserted, 'A canonical target binding block is required for a native breakpoint')
    result = b''.join(output)
    after = aux.records(result)
    need(b''.join(raw for key, value, raw in after if key not in added) == run,
         'Adding typed Scenario/Break Day/Time changed another run byte')
    return result, [{'key': 'Delay Scenario', 'old': None, 'new': '0'},
                    {'key': 'Break Day Offset', 'old': None, 'new': '0'},
                    {'key': 'Break Time', 'old': None, 'new': clock}]

def catalog_changes(spec, before, after):
    return {rb.CATALOG_KEYS[role]: (spec['execution_root'] + '/' + before[role],
                                  spec['execution_root'] + '/' + after[role]) for role in rb.CATALOG_KEYS}

def _closure(files, spec, scenario):
    catalogs = NORMAL_CATALOGS if scenario == 'normal' else FAILURE_CATALOGS
    run = NORMAL_RUN if scenario == 'normal' else FAILURE_RUN
    documents = ['OTDocuments/' + row['id'] + '.opentrack' for row in spec['stations']]
    names = {*catalogs.values(), *documents, run}
    return {name: files[name] for name in names}, catalogs, run, documents

def service_alias_projection(actual, spec, scenario):
    """Bijective key/path aliasing; no archive object/field normalization."""
    actual_files, catalogs, run, documents = _closure(actual, spec, scenario)
    alias = {name: actual_files[name] for name in documents}
    for role, name in catalogs.items():
        alias[services.CATALOGS[role]] = actual_files[name]
    alias_run, journal = rewrite_run(actual_files[run], catalog_changes(spec, catalogs, services.CATALOGS))
    alias[services.RUN] = alias_run
    output_directory = 'output' if scenario == 'normal' else 'output-failure'
    incidents = () if scenario == 'normal' else (services.INCIDENT,)
    validation = services.validate(alias, spec, output_directory=output_directory, incident_names=incidents)
    
    reversed_files = {name: alias[name] for name in documents}
    for role, name in catalogs.items():
        reversed_files[name] = alias[services.CATALOGS[role]]
    reversed_files[run], _ = rewrite_run(alias[services.RUN], catalog_changes(spec, services.CATALOGS, catalogs))
    need(reversed_files == actual_files, 'Service alias projection did not restore all ten actual bytes')
    return {'typed_catalog_alias_changes': journal,
            'projected_members': manifest(alias), 'all_ten_actual_bytes_restored_by_reverse_alias': True,
            'validation': validation}

def validate_seventeen(files, spec):
    topology.configuration(spec)
    documents = ['OTDocuments/' + row['id'] + '.opentrack' for row in spec['stations']]
    expected = {*documents, *NORMAL_CATALOGS.values(), *FAILURE_CATALOGS.values(), NORMAL_RUN, FAILURE_RUN}
    need(type(files) is dict and len(files) == 17 and set(files) == expected,
         'Exactly three common documents, twelve catalogs and two run files required')
    need(len({name.casefold() for name in files}) == 17, 'Case-insensitive actual member collision')
    for name, blob in files.items():
        rb.relative(name)
        need(type(blob) is bytes and 0 < len(blob) <= 20 * 1024 * 1024, 'Bounded immutable actual input required')
    drawing_positions = {row['id']: validate_drawing_positions(
        files['OTDocuments/' + row['id'] + '.opentrack'], row['id']) for row in spec['stations']}
    result = {}
    closures = {}
    for scenario in ('normal', 'failure'):
        selected, catalogs, run_name, docs = _closure(files, spec, scenario)
        closures[scenario] = set(selected)
        rows = aux.records(selected[run_name])
        values = {key: value for key, value, raw in rows if key is not None}
        for role, key in rb.CATALOG_KEYS.items():
            need(values.get(key) == spec['execution_root'] + '/' + catalogs[role], 'Actual scenario catalog path is not exact: ' + key)
        need([value for key, value, raw in rows if key == 'Infrastructure Document'] == [spec['execution_root'] + '/' + doc for doc in docs],
             'Actual three common infrastructure bindings differ')
        need(not any(key in ('Train Diagram Document', 'Document Set Document', 'Document Set Name') for key, value, raw in rows),
             'Auxiliary outside-project inputs are not part of the17-member closure')
        output_directory = 'output' if scenario == 'normal' else 'output-failure'
        need(values.get('OutputPath') == spec['execution_root'] + '/' + output_directory,
             'Exact scenario output directory required')
        need(values.get('Break Day Offset') == '0' and values.get('Break Time') == BREAKS[scenario],
             'Explicit scenario native Break Day/Time differs')
        need([value for key, value, raw in rows if key == 'Delay Scenario'] == ['0'],
             'Explicit singleton Delay Scenario0 is required to avoid native CLI-script auto-increment')
        need([value for key, value, raw in rows if key == 'TrainType'] == [services.SPEED_TYPE],
             'Actual speed-type binding differs')
        selected_incidents = [value for key, value, raw in rows if key == 'Incident']
        need(selected_incidents == ([] if scenario == 'normal' else [services.INCIDENT]),
             'Actual scenario Incident selection differs')
        
        archives = {name: blob for name, blob in selected.items() if name != run_name}
        core_run = aux.core_bytes(rows)
        run_validation = rb.verify_run(core_run, archives, catalog_paths=catalogs,
            document_paths=docs, execution_root=spec['execution_root'], path_style='windows',
            output_directory=output_directory, train_types=[services.SPEED_TYPE], **services.WINDOW)
        archive_bindings = rb.verify_archive_bindings(core_run, archives,
            catalog_paths=catalogs, document_paths=docs)
        incident_bindings = aux.incident_bindings(selected[catalogs['courses']], selected_incidents)
        projection = service_alias_projection(files, spec, scenario)
        result[scenario] = {'actual_run': run_name, 'actual_members': manifest(selected),
            'actual_catalog_paths': catalogs, 'actual_output_directory': spec['execution_root'] + '/' + output_directory,
            'native_break_day_offset': 0, 'native_break_time': BREAKS[scenario], 'delay_scenario': 0,
            'actual_run_binding_validation': run_validation, 'actual_archive_bindings': archive_bindings,
            'actual_incident_bindings': incident_bindings, 'service_alias_projection': projection}
    need(closures['normal'] & closures['failure'] == set(documents) and
         closures['normal'] | closures['failure'] == set(files), 'The two actual closures must share only three documents')
    for role in rb.CATALOG_KEYS:
        if role == 'courses':
            need(files[NORMAL_CATALOGS[role]] != files[FAILURE_CATALOGS[role]], 'Failure needs its actual separate Incident CourseList')
        else:
            need(files[NORMAL_CATALOGS[role]] == files[FAILURE_CATALOGS[role]],
                 'Unrelated failure catalog content changed: ' + role)
    return {'schema': 'seventeen-input-two-run-validation/1', 'member_count': 17,
            'common_documents': documents, 'exact_actual_run_closures_verified': True,
            'native_drawing_positions': drawing_positions,
            'rb_validators_used_without_relaxation': True, 'scenarios': result,
            'native_application_executed': False, 'native_runtime_verified': False}


def build(sources, spec):
    """Generate from six actual donors, without prior projects or receipts."""
    topology.configuration(spec)
    network, topology_receipt = topology.generate(sources, spec)
    normal, normal_receipt = services.compose(sources, network, spec, topology_receipt)
    first = spec['stations'][0]['id']
    targets = [item for item in topology_receipt['signals'][first]
               if item['name'] == 'S_' + first + '_D_B2']
    need(len(targets) == 1, 'Exact first-station shared Down B2 target required')
    failure, failure_receipt = services.make_failure_case(
        normal, spec, normal_receipt['plans'], targets[0]['signal_id'], document=first)
    drawings = {}
    for station in spec['stations']:
        member = 'OTDocuments/' + station['id'] + '.opentrack'
        document, drawings[station['id']] = append_drawings(
            normal[member], station['id'], sources['header'])
        normal[member] = failure[member] = document
    normal[NORMAL_RUN], _ = with_break(normal[NORMAL_RUN], BREAKS['normal'])
    failure[NORMAL_RUN], _ = with_break(failure[NORMAL_RUN], BREAKS['failure'])
    files = dict(normal)
    files.update({path: failure[services.CATALOGS[role]]
                  for role, path in FAILURE_CATALOGS.items()})
    files[FAILURE_RUN], rebinding = rewrite_run(failure[NORMAL_RUN],
        catalog_changes(spec, services.CATALOGS, FAILURE_CATALOGS))
    validation = validate_seventeen(files, spec)
    receipt = {
        'schema': 'three-station-yard-candidate/1',
        'recipe': copy.deepcopy(spec), 'members': manifest(files),
        'source_sha256': {role: services.sha(blob) for role, blob in sources.items()},
        'from_empty_graph': True, 'member_count': 17,
        'station_document_count': 3, 'platform_tracks_per_station': 8,
        'island_drawings_per_station': 4, 'native_labels_per_station': 15,
        'real_turnouts_per_station': 12, 'running_mains_per_station': 2,
        'itinerary_count': 8, 'courses_per_scenario': 9,
        'timetable_rows_per_scenario': 27, 'journey_distance_m': 10000,
        'normal_run': NORMAL_RUN, 'failure_run': FAILURE_RUN,
        'breakpoints': dict(BREAKS), 'delay_scenario': 0,
        'plans': normal_receipt['plans'],
        'topology': topology_receipt, 'normal_services': normal_receipt,
        'failure_services': failure_receipt, 'drawings': drawings,
        'failure_catalog_rebinding': rebinding, 'validation': validation,
        'physical_model_calibrated': False,
        'saved': False, 'native_application_executed': False,
        'native_runtime_verified': False,
    }
    return files, receipt
