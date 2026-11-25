import json
from xml.etree import ElementTree

import pytest

from opentrack_ai.current_archive import dispatching_rules_otd as otd
from opentrack_ai.current_archive.multi_document.core import Project, sha
from opentrack_ai.current_archive.native_job_inputs import FrozenJobInputs
from opentrack_ai.current_archive.native_run_evaluation import read_receipts
from opentrack_ai.current_archive.zero_generation.native_signal_routes import string
from opentrack_ai import native_execution as native
from opentrack_ai.simulation_evidence import Control

from test_saved_multi_document_reroute import chain


@pytest.fixture
def project(chain):
    docs, paths, _, _ = chain
    return Project(docs, document_paths=paths, expected_hashes={name: sha(data) for name, data in docs.items()},
                   complete_document_set=True)


def route(document, end, name):
    return {'document': document, 'start_end_id': end, 'route_name': name}


def ruleset(applies_to=None, conditions=None, rule_name='Rules & checks'):
    apply = route('A', 8, 'R:A-B') if applies_to is None else applies_to
    condition = {'route': route('B', 8, 'R:B-C'), 'reservation': 'free'}
    return otd.RuleSet.model_validate({'name': rule_name, 'applies_to': [apply], 'rules': [
        {'kind': 'conditions', 'conditions': [condition] if conditions is None else conditions},
        {'kind': 'capacity', 'maximum_other_trains': 2,
         'reserved_routes': [route('B', 8, 'R:B-C'), route('B', 9, 'R:B-A')]},
    ]})


def test_writes_original_external_conditions_and_capacity_with_route_closure(project):
    watch = route('B', 8, 'R:B-C')
    length = route('B', 9, 'R:B-A')
    dwell = route('C', 9, 'R:C-B')
    rules = ruleset(conditions=[{'route': watch, 'reservation': 'free'}, {'route': length, 'minimum_length_m': 120},
                                {'route': dwell, 'stop_code': 'extendedDwell', 'extended_dwell_s': 30.5}])
    data, report = otd.dispatching_rules(project, [rules], 'compound')
    assert data.startswith(otd.PROLOGUE)
    assert b'Rules &amp; checks' in data
    document = ElementTree.fromstring(data)
    sets, routes = document
    definition, = sets
    assert definition.tag == 'routeRuleSet' and definition.attrib == {'id': 'Rules & checks'}
    conditions, capacity = definition
    assert [row.attrib for row in conditions] == [
        {'routeID': 'B-8-R:B-C', 'routeReservationState': 'free'},
        {'routeID': 'B-9-R:B-A', 'minimalLength': '120'},
        {'routeID': 'C-9-R:C-B', 'stopCode': 'extendedDwell', 'extendedDwellTime': '30.5'},
    ]
    assert capacity.attrib == {'maximalNumberOfTrains': '2'}
    assert [item.attrib for item in capacity] == [{'routeID': 'B-8-R:B-C'}, {'routeID': 'B-9-R:B-A'}]
    assert [item.attrib for item in routes] == [{'id': 'A-8-R:A-B', 'routeRuleSetID': 'Rules & checks'}]
    assert report == [{'name': 'Rules & checks', 'applies_to': ['A-8-R:A-B'], 'rule_count': 2}]


def test_rejects_unresolved_route_and_double_assignment(project):
    with pytest.raises(ValueError, match='does not identify a saved main Route'):
        otd.dispatching_rules(project, [ruleset(applies_to=route('A', 9, 'R:A-B'))], 'compound')
    with pytest.raises(ValueError, match='only one OTD ruleset'):
        otd.dispatching_rules(project, [ruleset(), ruleset(rule_name='Second')], 'compound')


def test_name_only_identifiers_reject_duplicate_names_across_documents(project):
    root_route = next(item for item in project.routes if project.owners[id(item)] == ('B', 8))
    root_route.contents[1].value = string('R:A-B')
    assert otd.route_ids(project, 'compound')[('B', 8, 'R:A-B')] == 'B-8-R:A-B'
    with pytest.raises(ValueError, match='Ambiguous native OTD Route ID'):
        otd.route_ids(project, 'route_name')


@pytest.mark.parametrize('fields', [
    {'reservation': 'free', 'minimum_length_m': 500},
    {'stop_code': 'extendedDwell'},
    {'stop_code': 'unplannedStop', 'extended_dwell_s': 30},
])
def test_requires_one_unambiguous_condition_mode(fields):
    with pytest.raises(ValueError):
        otd.RuleCondition.model_validate({'route': route('A', 8, 'R:A-B'), **fields})


@pytest.fixture
def launch_bundle(tmp_path, project, chain):
    docs, _, _, _ = chain
    source = tmp_path / 'source'
    inputs = {f'network/{name}.opentrack': data for name, data in docs.items()}
    run = 'test.run'
    inputs[run] = ''.join(f'Infrastructure Document#{(source / name).as_posix()}#\n' for name in inputs).encode()
    rules, _ = otd.dispatching_rules(project, [ruleset()], 'route_name')

    def binding(name):
        return {'path': f'source/{name}', 'sha256': sha(inputs[name])}

    files = {otd.XML_FILE: rules, otd.LAUNCH_FILE: json.dumps({
        'format': otd.LAUNCH_FORMAT, 'launch_path_is_relative_to_bundle': False, 'route_id_mode': 'route_name',
        'use_with_project_run': binding(run), 'original_startup_options': ['-unrelated-unapproved-argument'],
        'document_sources': {name: binding(f'network/{name}.opentrack') for name in docs},
        'xml_sha256': sha(rules), 'xml_bytes': len(rules),
    }).encode()}
    reference = {'path': f'bundle/{otd.LAUNCH_FILE}', 'sha256': sha(files[otd.LAUNCH_FILE])}
    native.store_members(tmp_path / 'bundle', files)
    return source, run, inputs, reference, files


def test_runner_enables_only_staged_native_otd_options(tmp_path, launch_bundle):
    project, run, inputs, reference, files = launch_bundle
    args = Control(action='start', project_directory='source', run_file=run, job_directory='job',
                   dispatching_rules=reference)
    frozen, binding = native.capture_dispatching_rules(tmp_path, project, run, inputs, args.dispatching_rules.model_dump())
    assert frozen == files
    native.store_members(tmp_path / 'job' / native.OTD_DIRECTORY, frozen)
    # The worker rechecks the job copy even if the source bundle is no longer readable.
    (tmp_path / 'bundle' / otd.XML_FILE).unlink()
    assert native.capture_dispatching_rules(tmp_path, project, run, inputs, reference,
                                            frozen=tmp_path / 'job' / native.OTD_DIRECTORY) == (frozen, binding)
    scenario = tmp_path / 'job' / 'runs' / '0' / 'project'
    exe = tmp_path / 'OpenTrack.exe'
    cmd = native.scenario_command(exe, scenario, {'run_file': run}, {})
    assert cmd == [str(exe), '-scriptinit', '-runfile=' + (scenario / run).as_posix()]
    members = {native.OTD_RULE_MEMBER: frozen[otd.XML_FILE]}
    request = {'run_file': run, 'dispatching_rules': binding}
    assert native.scenario_command(exe, scenario, request, members) == cmd + [
        '-dispatchingrules', '-dispatchingrulesfile=' + (scenario / native.OTD_RULE_MEMBER).as_posix(),
        '-routeidtype=routename',
    ]
    with pytest.raises(ValueError, match='exact frozen OTD rule copy'):
        native.scenario_command(exe, scenario, request, {native.OTD_RULE_MEMBER: b'edited'})


def test_runner_binds_exact_run_and_complete_worksheet_hashes(tmp_path, launch_bundle):
    project, run, inputs, reference, files = launch_bundle
    cases = [({**inputs, run: inputs[run] + b'// edited\n'}, files, 'source .run'),
             ({**inputs, 'network/A.opentrack': b'changed'}, files, 'worksheet paths or SHA-256'),
             (inputs, {**files, otd.XML_FILE: b'edited'}, 'manifest size and SHA-256')]
    for chosen, bundle, expected in cases:
        with pytest.raises(ValueError, match=expected):
            native.bind_dispatching_rules(tmp_path, project, run, chosen, reference, bundle)
    with pytest.raises(ValueError, match='manifest SHA-256'):
        native.bind_dispatching_rules(tmp_path, project, run, inputs, {**reference, 'sha256': '0' * 64}, files)


def test_each_scenario_keeps_a_separate_hashed_rules_copy(tmp_path, launch_bundle, monkeypatch):
    project, run, inputs, reference, files = launch_bundle
    rules = files[otd.XML_FILE]
    binding = native.bind_dispatching_rules(tmp_path, project, run, inputs, reference, files)

    def relocate(*args, **kwargs):
        return {run: b'frozen run', 'test.timetable': b'frozen timetable'}, {
            'catalog_paths': {'timetable': 'test.timetable'},
        }

    monkeypatch.setattr(native, 'relocate_project', relocate)
    monkeypatch.setattr(native, 'batch_runfile', lambda data, *args, **kwargs: data)
    monkeypatch.setattr(native, 'reset_copied_actuals', lambda data: (data, 0))
    monkeypatch.setattr(native.preflight, 'check', lambda *args: {'passed_static_subset': True, 'errors': []})
    request = {'run_file': run, 'dispatching_rules': binding,
               'source_sha256': {name: sha(data) for name, data in inputs.items()}}
    for scenario in (0, 17):
        working, evidence, effective = native.prepare_scenario(tmp_path / 'job', project, inputs, request, scenario,
                                                                dispatching_xml=rules)
        assert (working / native.OTD_RULE_MEMBER).read_bytes() == rules
        assert (evidence / 'inputs' / native.OTD_RULE_MEMBER).read_bytes() == rules
        assert effective[native.OTD_RULE_MEMBER] == rules
        receipt = native.read_json(evidence / 'relocation.json')
        assert receipt['dispatching_rules'] == binding
        assert receipt['effective_input_sha256'][native.OTD_RULE_MEMBER] == sha(rules)
    with pytest.raises(ValueError, match='Missing or modified frozen OTD XML'):
        native.prepare_scenario(tmp_path / 'job', project, inputs, request, 9)


def test_aggregate_binding_checks_control_and_treatment_launches(tmp_path, launch_bundle):
    source, run, inputs, ref, files = launch_bundle
    job = tmp_path / 'evidence-job'
    native.store_members(job / 'source', inputs)
    native.store_members(job / native.OTD_DIRECTORY, files)
    binding = native.bind_dispatching_rules(tmp_path, source, run, inputs, ref, files)
    request = {'run_file': run, 'source_sha256': {name: sha(data) for name, data in inputs.items()},
               'executable': 'OpenTrack.exe', 'dispatching_rules': binding}
    frozen = FrozenJobInputs(tmp_path, job, source, request, None)
    without_rules = FrozenJobInputs(tmp_path, job, source, {**request, 'dispatching_rules': None}, None)
    for scenario, headway in ((0, None), (17, None), (0, 90)):
        trial = job / 'runs' / str(headway if headway is not None else scenario)
        project, evidence = trial / 'project', trial / 'evidence'
        evidence.mkdir(parents=True)
        command = native.scenario_command(frozen.exe, project, request, {native.OTD_RULE_MEMBER: frozen.dispatching_xml})
        manifest = dict(frozen.effective_inventory)
        receipt = {'execution_root': project.as_posix(), 'run_file': run, 'delay_scenario': scenario,
                   'planned_departure_headway_s': headway, 'source_sha256': frozen.inventory,
                   'dispatching_rules': binding, 'effective_input_sha256': manifest}
        native.write_json(evidence / 'relocation.json', receipt)
        before = {'input_sha256': manifest, 'command': command, 'dispatching_rules': binding,
                  'executable_sha256': native.STOCK_EXE_SHA}
        native.write_json(evidence / 'before.json', before)
        process = {'input_writebacks': {}}
        native.write_json(evidence / 'process.json', process)
        launch = read_receipts(evidence)
        frozen.validate_launch(project, launch, scenario, headway_s=headway)
        with pytest.raises(ValueError, match='exact owned native launch'):
            without_rules.validate_launch(project, {**launch, 'input_sha256': frozen.inventory,
                                                     'dispatching_rules': None}, scenario, headway_s=headway)
        for changed, error in (
            ({'command': command[:3]}, 'exact owned native launch'),
            ({'command': command[:-1] + ['-routeidtype=other']}, 'exact owned native launch'),
            ({'command': command[:4] + ['-dispatchingrulesfile=D:/Foreign.xml'] + command[5:]}, 'exact owned native launch'),
            ({'executable_sha256': '0' * 64}, 'original fingerprint'),
            ({'dispatching_rules': None}, 'launch binding'),
            ({'input_writebacks': {native.OTD_RULE_MEMBER: '0' * 64}}, 'modified OTD rules'),
            ({'input_sha256': {**manifest, native.OTD_RULE_MEMBER: '0' * 64}}, 'modified OTD rules'),
        ):
            with pytest.raises(ValueError, match=error):
                frozen.validate_launch(project, {**launch, **changed}, scenario, headway_s=headway)
        with pytest.raises(ValueError, match='relocation receipt'):
            frozen.validate_launch(project, launch, scenario + 1, headway_s=headway)
        native.write_json(evidence / 'process.json', {**process, 'command': command[:3]})
        with pytest.raises(ValueError, match='conflicts with the recorded launch'):
            read_receipts(evidence)
    (job / native.OTD_DIRECTORY / otd.XML_FILE).write_bytes(b'changed')
    with pytest.raises(ValueError, match='manifest size and SHA-256'):
        FrozenJobInputs(tmp_path, job, source, request, None)
    (job / 'source' / run).write_bytes(b'changed')
    with pytest.raises(ValueError, match='source members differ'):
        FrozenJobInputs(tmp_path, job, source, request, None)
