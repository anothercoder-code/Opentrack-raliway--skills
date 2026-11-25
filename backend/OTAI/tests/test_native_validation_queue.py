from pathlib import Path
from types import SimpleNamespace

import pytest

from opentrack_ai import native_execution as native, native_validation_queue as queue


@pytest.fixture
def reviewed_request(tmp_path):
    root = tmp_path.resolve()
    path = root / 'submitted.json'
    arguments = {'action': 'start', 'project_directory': 'source', 'job_directory': 'native-case',
                 'run_file': 'case.run', 'source_sha256': {'case.run': 'a' * 64}, 'expectations': {'courses': ['A']}}
    native.write_json(path, arguments)
    case = {'id': 'test-case', 'request': path.name, 'request_sha256': native.digest(path.read_bytes()), 'focus': 'acceptance'}
    return root, path, arguments, case


def test_dry_review_checks_exact_request_without_submitting_or_creating_jobs(reviewed_request, monkeypatch):
    root, path, arguments, case = reviewed_request
    draft = SimpleNamespace(job=root / 'native-case', project=root / 'source',
                            request={**arguments, 'mode': 'batch', 'scenarios': [0]})
    monkeypatch.setattr(native, 'plan_start', lambda *args: draft)
    monkeypatch.setattr(queue, 'check_trial', lambda *args: {'scenario': 0})
    payload = queue.Queue.model_validate({'schema_version': 1, 'cases': [case]})
    report, = queue.review(root, object(), payload, [])
    assert report['state'] == 'ready' and report['trials'] == [{'scenario': 0}]
    assert not draft.job.exists()
    path.write_bytes(path.read_bytes() + b' ')
    report, = queue.review(root, object(), payload, [])
    assert report['state'] == 'blocked' and 'request SHA-256 differs' in report['reason']


def test_execution_uses_existing_serial_worker_and_stops_before_changed_request(reviewed_request, monkeypatch):
    root, path, arguments, case = reviewed_request
    calls = []

    class Registry:
        def envelope(self, tool, body):
            calls.append((tool, body['action']))
            return {'ok': True, 'result': {'state': 'completed', 'native_simulation_verified': True}}

    monkeypatch.setattr(queue, 'verify_outputs', lambda *args: {'OT_A.tt': 'a' * 64})
    report = {**case, 'arguments': arguments, 'request_path': path.as_posix(), 'mode': 'batch',
              'job_directory': (root / 'native-case').as_posix(), 'trials': [{'scenario': 0}]}
    completed = queue.execute_case(root, Registry(), report, lambda _: None)
    assert completed['automatic_checks_passed']
    assert calls == [(queue.CONTROL_TOOL, 'start'), (queue.CONTROL_TOOL, 'status')]
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='Reviewed request changed'):
        queue.execute_case(root, Registry(), report, lambda _: None)
    assert len(calls) == 2


def test_required_original_output_hash_and_launch_identity(tmp_path):
    root = tmp_path.resolve()
    out, evidence = root / 'output', root / 'evidence'
    out.mkdir()
    evidence.mkdir()
    names = {'OT_Protocol.20261124-1200.txt': b'protocol', 'OT_A.sigpos': b'positions'}
    native.store_members(out, names)
    hashes = {name: native.digest(raw) for name, raw in names.items()}
    trial = {'output_directory': out.as_posix(), 'evidence_directory': evidence.as_posix(),
             'effective_input_sha256': {'case.run': 'a' * 64},
             'required_outputs': ['OT_Protocol.*.txt', 'OT_A.sigpos'], 'command_preview': ['OpenTrack.exe', '-scriptinit']}
    native.write_json(evidence / 'before.json', {'executable_sha256': native.STOCK_EXE_SHA,
        'input_sha256': trial['effective_input_sha256'], 'command': trial['command_preview']})
    native.write_json(evidence / 'process.json', {'exit_code': 0, 'outcome': 'exited',
        'output_directory': out.as_posix(), 'output_sha256': hashes})
    assert queue.verify_outputs(root, trial) == hashes
    with pytest.raises(ValueError, match='reviewed launch'):
        queue.verify_outputs(root, {**trial, 'command_preview': ['wrong.exe']})
    with pytest.raises(ValueError, match='lacks one required output'):
        queue.verify_outputs(root, {**trial, 'required_outputs': ['OT_B.sigpos']})
    (out / Path('OT_A.sigpos')).write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed after completion'):
        queue.verify_outputs(root, trial)


def test_endpoint_signals_need_frozen_hash_labels_and_positions(tmp_path):
    output = 'OT_A.sigpos'
    data = (b'// Produced by OpenTrack: Mon Nov 23 16:41:45 2026\n'
            b'// Signal Positions of Course: A\n// Desc.   : OT_Signals\n// x-Legend: [km]\n'
            b'0.0000\tMS\tA_EXIT\tTS\n4.7250\tMS\tB_EXIT\tTS\n')
    path = tmp_path / output
    path.write_bytes(data)
    check = {'course_id': 'A', 'output': output, 'origin': {'label': 'A_EXIT', 'position_m': 0},
             'terminal': {'label': 'B_EXIT', 'position_m': 4725}}
    hashes = {output: native.digest(data)}
    assert queue.read_endpoint_signals(tmp_path, check, hashes)['terminal']['observed_position_m'] == 4725
    with pytest.raises(ValueError, match='terminal signal differs'):
        queue.read_endpoint_signals(tmp_path, {**check, 'terminal': {'label': 'B_EXIT', 'position_m': 4225}}, hashes)
    path.write_bytes(data + b'\n')
    with pytest.raises(ValueError, match='signal output changed'):
        queue.read_endpoint_signals(tmp_path, check, hashes)


def test_native_instrument_passage_requires_bound_course_scenario_and_direction(tmp_path):
    name = 'OT_Ins_Platform_A_33.ins'
    path = tmp_path / name
    data = (b'// Produced by OpenTrack: Mon Nov 23 16:41:45 2026\n'
            b'// Desc.   : OT_ins\n'
            b'1\t0\t37500.9\t0.4\tA\t1\n'
            b'1\t0\t37500.9\t0.4\tB\t2\n'
            b'1\t17\t37500.9\t0.4\tA\t2\n')
    path.write_bytes(data)
    hashes = {name: native.digest(data)}
    checked = {'course_id': 'A', 'direction_code': 1, 'output': name}
    result, = queue.read_instrument_passages(tmp_path, 0, [checked], hashes)
    assert len(result['observations']) == 1 and result['observations'][0]['time_s'] == 37500.9
    with pytest.raises(ValueError, match='No native instrument record'):
        queue.read_instrument_passages(tmp_path, 0, [{**checked, 'direction_code': 2}], hashes)
    with pytest.raises(ValueError, match='No native instrument record'):
        queue.read_instrument_passages(tmp_path, 17, [checked], hashes)
    path.write_bytes(data + b'\n')
    with pytest.raises(ValueError, match='output changed'):
        queue.read_instrument_passages(tmp_path, 0, [checked], hashes)


def test_frozen_instrument_on_paired_end_uses_original_reverse_direction(monkeypatch):
    nodes = [('West', 4), ('East Yard', 28)]
    itinerary = SimpleNamespace(contents=[None, SimpleNamespace(value='through')])
    project = SimpleNamespace(dests=[itinerary], roots={'East Yard': object()},
                              dest_view=lambda _: (nodes, []),
                              actual_related=lambda end: (end[0], end[1] + 1))
    instrument = {'id': 50, 'end_id': 29, 'edge_ids': [32, 33], 'direction_code': 3, 'name': 'Passage Counter'}
    monkeypatch.setattr(queue, 'frozen_project', lambda *_: project)
    monkeypatch.setattr(queue.native_monitoring, 'records', lambda _: {'instruments': [instrument]})
    monkeypatch.setattr(queue.catalogs, 'text', lambda text: text)
    spec = {'document': 'East Yard', 'instrument_id': 50, 'end_id': 29, 'edge_ids': [32, 33], 'course_id': 'A'}
    courses = {'A': {'itineraries': ['through']}}
    outcomes = [{'course_id': 'A', 'terminal_station': 'End of line'}]
    checked, = queue.check_instrument_passages(
        [queue.InstrumentPassage.model_validate(spec)], {}, {}, courses, outcomes)
    assert checked['direction_code'] == 2
    assert checked['output'] == 'OT_Ins_Passage_Counter_East_Yard_50.ins'
    with pytest.raises(ValueError, match='eligible passage'):
        queue.check_instrument_passages([queue.InstrumentPassage.model_validate({**spec, 'direction_code': 1})],
                                        {}, {}, courses, outcomes)


def test_queued_throat_check_calls_specific_registered_verifier_after_output_binding(reviewed_request, monkeypatch):
    root, path, arguments, case = reviewed_request
    order = []
    check = {'passage': {'course_id': 'A'}}

    class Registry:
        def envelope(self, tool, body):
            if tool == queue.CONTROL_TOOL:
                return {'ok': True, 'result': {'state': 'completed', 'native_simulation_verified': True}}
            order.append(tool)
            assert body == check
            return {'ok': False, 'error': 'Connector traversal mismatch'}

    def matched_outputs(*_):
        order.append('output_sha256')
        return {'OT_A.st1': 'a' * 64}

    monkeypatch.setattr(queue, 'verify_outputs', matched_outputs)
    reviewed = {**case, 'arguments': arguments, 'request_path': path.as_posix(), 'mode': 'batch',
                'job_directory': (root / 'native-case').as_posix(),
                'trials': [{'scenario': 0, 'throat_passage_check': check}]}
    completed = queue.execute_case(root, Registry(), reviewed, lambda _: None)
    assert not completed['automatic_checks_passed']
    assert completed['trials'][0]['reason'] == 'Connector traversal mismatch'
    assert order == ['output_sha256', queue.THROAT_TOOL]


@pytest.mark.parametrize('second_passes', [True, False])
def test_queued_throat_checks_bind_both_directions_to_one_original_trial(reviewed_request, monkeypatch, second_passes):
    root, path, arguments, case = reviewed_request
    observed = []
    checks = [{'passage': {'course_id': course}, 'output_directory': 'same-original-output'} for course in ('A', 'B')]

    class Registry:
        def envelope(self, tool, body):
            if tool == queue.CONTROL_TOOL:
                return {'ok': True, 'result': {'state': 'completed', 'native_simulation_verified': True}}
            assert tool == queue.THROAT_TOOL
            observed.append(body)
            course = body['passage']['course_id']
            if course == 'B' and not second_passes:
                return {'ok': False, 'error': 'Reverse path mismatch'}
            return {'ok': True, 'result': {'native_throat_passage_verified': True, 'course_id': course}}

    def matched_outputs(*_):
        observed.append('bound output hashes')
        return {'OT_A.st1': 'a' * 64, 'OT_B.st1': 'b' * 64}

    monkeypatch.setattr(queue, 'verify_outputs', matched_outputs)
    reviewed = {**case, 'arguments': arguments, 'request_path': path.as_posix(), 'mode': 'batch',
                'job_directory': (root / 'native-case').as_posix(),
                'trials': [{'scenario': 0, 'throat_passage_checks': checks}]}
    completed = queue.execute_case(root, Registry(), reviewed, lambda _: None)
    assert observed == ['bound output hashes', *checks]
    assert completed['automatic_checks_passed'] is second_passes
    if second_passes:
        assert [row['course_id'] for row in completed['trials'][0]['throat_passages']] == ['A', 'B']
    else:
        assert completed['trials'][0]['reason'] == 'Reverse path mismatch'


def test_reviewed_route_protection_runs_after_binding_original_outputs(reviewed_request, monkeypatch):
    root, path, arguments, case = reviewed_request
    requests = []
    check = {'protection': {'course_id': 'A'}}

    class Registry:
        def envelope(self, tool, body):
            if tool == queue.CONTROL_TOOL:
                return {'ok': True, 'result': {'state': 'completed', 'native_simulation_verified': True}}
            requests.append((tool, body))
            return {'ok': True, 'result': {'native_route_protection_verified': True}}

    def verify(*_):
        requests.append('validated outputs')
        return {'OT_A.step2': 'a' * 64}

    monkeypatch.setattr(queue, 'verify_outputs', verify)
    reviewed = {**case, 'arguments': arguments, 'request_path': path.as_posix(), 'mode': 'batch',
                'job_directory': (root / 'native-case').as_posix(),
                'trials': [{'scenario': 0, 'route_protection_check': check}]}
    completed = queue.execute_case(root, Registry(), reviewed, lambda _: None)
    assert completed['automatic_checks_passed']
    assert completed['trials'][0]['route_protection']['native_route_protection_verified']
    assert requests == ['validated outputs', (queue.PROTECTION_TOOL, check)]
