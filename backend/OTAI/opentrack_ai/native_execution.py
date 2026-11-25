"""Owned OpenTrack 1.7 script jobs with fresh, individually frozen scenario inputs."""

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
from statistics import mean, median
import subprocess
import sys
from time import monotonic, sleep
from xml.etree import ElementTree as xml

from .current_archive import dispatching_rules_otd as otd
from .current_archive.prepare_contract import auxiliary, preflight
from .current_archive.project_workflow.relocation import relocate_project
from .current_archive.zero_operations import run_bundle
from .license_authorization import require_authorization


STOCK_EXE_SHA = 'f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104'
TERMINAL_STATES = {'completed', 'failed', 'stopped', 'timed_out'}
OTD_DIRECTORY = 'otd-rules'
OTD_RULE_MEMBER = f'{OTD_DIRECTORY}/{otd.XML_FILE}'
OTD_MANIFEST_LIMIT = 4 * 1024 * 1024
REQUIRED_OUTPUTS = (
    'Output Timetable (Text)', 'Output Speed/Time', 'Output Distance/Time',
    'Output Messages (Text)', 'Output Simulation Protocol', 'Output Route Occ.',
    'Output Course & Station Statistics', 'Output Timetable & Delay Statistics',
)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def child_path(parent, value):
    """Accept only a canonical relative name with no redirected path component."""
    value = run_bundle.relative(value)
    path = parent / value
    require(path.resolve() == path, f'Path is redirected from its declared location: {value}')
    return path


def output_hashes(output):
    hashes = {}
    for path in sorted(path for path in output.iterdir() if path.is_file()):
        require(path.resolve(strict=True) == path, f'Native output was redirected: {path.name}')
        before = path.stat()
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            require((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino),
                    f'Native output changed before hashing: {path.name}')
            hashes[path.name] = file_digest(stream, 'sha256').hexdigest()
        after = path.stat()
        require(path.resolve(strict=True) == path and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
                f'Native output changed while hashing: {path.name}')
    return hashes


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    # Readers of state.json can briefly hold a Windows handle that denies
    # replacement. Keep the old complete state visible during those reads.
    for attempt in range(6):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            sleep(0.05)


def store_members(directory, members):
    for name, data in members.items():
        path = child_path(directory, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)


def capture_source(project, run_name):
    run_path = child_path(project, run_name)
    require(run_path.suffix.lower() == '.run', 'Expected an explicit .run file')
    with run_path.open('rb') as stream:
        raw = stream.read(1048577)
    prefix = project.as_posix() + '/'
    members = {run_name: raw}
    total = len(raw)

    def bound_reader(absolute):
        require(absolute.startswith(prefix), f'Input outside chosen source project: {absolute}')
        name = absolute[len(prefix):]
        require(name not in members, f'Repeated source path: {name}')
        path = child_path(project, name)
        with path.open('rb') as stream:
            members[name] = stream.read(preflight.MAX_MEMBER_BYTES + 1)
        return members[name]

    for key, path, _ in auxiliary.records(raw):
        if key in run_bundle.PATH_KEYS and key not in {'OutputPath', 'Document Set Document'}:
            value = bound_reader(path.replace('\\', '/'))
            require(0 < len(value) <= preflight.MAX_MEMBER_BYTES, f'Invalid source member length: {path}')
            total += len(value)
            require(total <= preflight.MAX_PROJECT_BYTES, 'Selected project exceeds the supported snapshot size')
    # Relocation validates the entire closure again and rebinds the embedded
    # .dest owner paths. The original is never launched against source paths.
    return members


def read_bounded(path, limit):
    require(path.is_file(), f'Expected a regular input file: {path.name}')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, f'Input file is empty or exceeds its byte limit: {path.name}')
    return raw


def bind_dispatching_rules(root, project, run_name, inputs, source, files):
    relative = run_bundle.relative(source['path'])
    require(Path(relative).name == otd.LAUNCH_FILE, f'Select an exported {otd.LAUNCH_FILE}')
    manifest_raw = files[otd.LAUNCH_FILE]
    require(digest(manifest_raw) == source['sha256'], 'OTD launch manifest SHA-256 differs')
    manifest = json.loads(manifest_raw)
    require(isinstance(manifest, dict) and manifest.get('format') == otd.LAUNCH_FORMAT
            and manifest.get('launch_path_is_relative_to_bundle') is False,
            'Expected a published original OTD launch manifest')
    mode = manifest.get('route_id_mode')
    require(mode in ('compound', 'route_name'), 'Unknown original OTD Route ID mode')

    def source_record(member):
        return {'path': (project / member).relative_to(root).as_posix(), 'sha256': digest(inputs[member])}

    def normalized_record(record):
        require(isinstance(record, dict) and set(record) == {'path', 'sha256'}
                and isinstance(record['path'], str), 'Invalid OTD project source record')
        path = run_bundle.relative(record['path'].replace('\\', '/'))
        return {**record, 'path': path}

    require(normalized_record(manifest.get('use_with_project_run')) == source_record(run_name),
            'OTD rules were bound to a different source .run path or SHA-256')
    prefix = project.as_posix() + '/'
    documents = {}
    for key, path, _ in auxiliary.records(inputs[run_name]):
        if key != 'Infrastructure Document':
            continue
        path = path.replace('\\', '/')
        require(path.startswith(prefix) and path[len(prefix):] in inputs,
                'OTD rule binding requires each selected infrastructure source')
        member = path[len(prefix):]
        name = Path(member).stem
        require(name not in documents, 'OTD rule binding requires unique worksheet stems')
        documents[name] = source_record(member)
    bindings = manifest.get('document_sources')
    require(documents and isinstance(bindings, dict)
            and {name: normalized_record(record) for name, record in bindings.items()} == documents,
            'OTD worksheet paths or SHA-256 differ from the complete selected infrastructure')

    rules = files[otd.XML_FILE]
    rules_sha = digest(rules)
    require(manifest.get('xml_sha256') == rules_sha and manifest.get('xml_bytes') == len(rules),
            'OTD XML does not match the bound manifest size and SHA-256')
    require(rules.startswith(otd.PROLOGUE), 'OTD XML requires the original exporter declaration')
    body = rules[len(otd.PROLOGUE):]
    require(body.isascii() and b'<!' not in body and b'<?' not in body,
            'OTD XML body must use the original standalone rule format')
    try:
        tree = xml.fromstring(body)
    except xml.ParseError as exc:
        raise ValueError(f'Invalid original OTD XML: {exc}') from exc
    require(tree.tag == 'otd' and [child.tag for child in tree] == ['routeRuleSets', 'routes']
            and all(len(section) for section in tree), 'Expected original OTD rulesets and Route assignments')
    return {'manifest_source': source, 'xml_sha256': rules_sha, 'route_id_mode': mode,
            'scenario_member': OTD_RULE_MEMBER}


def capture_dispatching_rules(root, project, run_name, inputs, source, *, frozen=None):
    relative = run_bundle.relative(source['path'])
    require(Path(relative).name == otd.LAUNCH_FILE, f'Select an exported {otd.LAUNCH_FILE}')
    directory = child_path(root, relative).parent if frozen is None else frozen
    files = {name: read_bounded(child_path(directory, name), limit) for name, limit in (
        (otd.LAUNCH_FILE, OTD_MANIFEST_LIMIT), (otd.XML_FILE, otd.XML_LIMIT))}
    return files, bind_dispatching_rules(root, project, run_name, inputs, source, files)


def interactive_break(raw):
    from .current_archive.runfile_parameters import time_seconds

    rows = auxiliary.records(raw)
    clocks = [value for key, value, _ in rows if key == 'Break Time']
    days = [value for key, value, _ in rows if key == 'Break Day Offset']
    require(len(clocks) == 1 and len(days) <= 1, 'Interactive mode requires one saved Break Time')
    values = {key: value.encode('ascii') for key, value, _ in rows if key is not None}
    require(all(prefix + ' Time' in values and prefix + ' Day Offset' in values for prefix in ('Start', 'Stop')),
            'Interactive mode requires an explicit saved run window')
    start, stop = (time_seconds(values[prefix + ' Time'], values[prefix + ' Day Offset'])
                   for prefix in ('Start', 'Stop'))
    paused = time_seconds(clocks[0].encode('ascii'), days[0].encode('ascii') if days else b'0')
    require(start < paused < stop, 'Interactive Break Time must lie strictly within the run window')
    return paused


def batch_runfile(raw, scenario, *, interactive=False, expectations=None):
    overrides = dict.fromkeys(REQUIRED_OUTPUTS, '1')
    overrides['Delay Scenario'] = str(scenario)
    if expectations:
        if expectations.get('expected_physical_peaks'):
            overrides['Output Time/Dist./Speed/Power'] = '1'
        if expectations.get('expected_signal_reservation_headways'):
            overrides['Output Station- & Signalpositions'] = '1'
    if interactive:
        interactive_break(raw)
        overrides.update(dict.fromkeys(('Multithreaded', 'Show Current Time', 'Show Train', 'Show Train ID', 'Show Messages'), '1'))
    else:
        overrides.update({'Break Time': '00:00:00', 'Break Day Offset': '0'})
    emitted = []
    for key, _, record in auxiliary.records(raw):
        if key not in overrides:
            emitted.append(record)
            continue
        newline = '\r\n' if record.endswith(b'\r\n') else '\n'
        emitted.append(f'{key}#{overrides.pop(key)}#{newline}'.encode('ascii'))
    emitted.extend(f'{key}#{value}#\n'.encode('ascii') for key, value in overrides.items())
    updated = b''.join(emitted)
    auxiliary.records(updated)
    return updated


def reset_copied_actuals(raw):
    from .current_archive import catalogs, course_factories, writer

    root, version = writer.load_next_compatible(raw)
    reset = 0
    for row in course_factories.timetable(root).values():
        actuals = [catalogs.text(row.contents[slot].value) for slot in (13, 14)]
        if actuals != ['HH:MM:SS', 'HH:MM:SS'] or row.contents[15].values[2:] != [0, 0]:
            course_factories.settext(row, 13, 'HH:MM:SS')
            course_factories.settext(row, 14, 'HH:MM:SS')
            row.contents[15].values[2:] = [0, 0]
            reset += 1
    return (writer.dump_verified(root, version) if reset else raw), reset


def process_is_open():
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-Command',
         "@(Get-Process -Name 'OpenTrack*' -ErrorAction SilentlyContinue).Count"],
        capture_output=True, text=True, timeout=15, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return int(result.stdout.strip()) > 0


def process_identity(pid):
    """Distinguish the worker from a later process that reused its PID."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x101000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    if not handle:
        return None
    try:
        created, exited, cpu_kernel, cpu_user = (wintypes.FILETIME() for _ in range(4))
        if (kernel.WaitForSingleObject(handle, 0) == 0x102 and
                kernel.GetProcessTimes(handle, created, exited, cpu_kernel, cpu_user)):
            return {'pid': pid, 'created_100ns': (created.dwHighDateTime << 32) | created.dwLowDateTime}
        return None
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def native_lock():
    """Serialize owned original sessions across jobs started by this account."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    lock = kernel.CreateMutexW(None, False, 'Local\\OpenTrackSkillOriginalSession')
    if not lock:
        raise ctypes.WinError(ctypes.get_last_error())
    owned = kernel.WaitForSingleObject(lock, 0) in (0, 0x80)
    try:
        require(owned, 'Another skill job owns the original OpenTrack session')
        require(not process_is_open(), 'An existing OpenTrack session is active')
        yield
    finally:
        if owned:
            kernel.ReleaseMutex(lock)
        kernel.CloseHandle(lock)


def headway_source_blobs(project, configured, inputs):
    prefix = project.as_posix() + '/'
    paths = {role: configured[key].replace('\\', '/') for role, key in run_bundle.CATALOG_KEYS.items()}
    require(all(path.startswith(prefix) and path[len(prefix):] in inputs for path in paths.values()),
            'Headway catalog paths must name bound members of the selected project')
    return {role: inputs[path[len(prefix):]] for role, path in paths.items()}


@dataclass
class NativeJobPlan:
    executable: Path
    project: Path
    job: Path
    inputs: dict
    request: dict
    dispatching_files: dict


def plan_start(root, args):
    """Resolve and verify exact launch inputs without creating a job or starting a process."""
    executable = child_path(root, args.executable)
    require(digest(executable.read_bytes()) == STOCK_EXE_SHA, 'Original OpenTrack fingerprint differs')
    project = child_path(root, args.project_directory)
    job = child_path(root, args.job_directory)
    require(not job.is_relative_to(project) and not project.is_relative_to(job),
            'Use a fresh job directory separate from the source project')
    require(job.as_posix().isascii() and executable.as_posix().isascii(),
            'Original executable and job paths must be ASCII')
    require(not job.exists(), 'Job directory already exists')
    inputs = capture_source(project, args.run_file)
    hashes = {name: digest(data) for name, data in inputs.items()}
    require(args.source_sha256 is None or hashes == args.source_sha256,
            'Selected source bytes differ from the supplied complete manifest')
    rule_source = getattr(args, 'dispatching_rules', None)
    rule_files = {}
    if rule_source is not None:
        require('=' not in job.as_posix(), 'The original OTD launch path cannot contain an equals sign')
        rule_files, rule_binding = capture_dispatching_rules(root, project, args.run_file, inputs,
                                                            rule_source.model_dump())
    configured = dict((key, value) for key, value, _ in auxiliary.records(inputs[args.run_file]))
    scenarios = args.scenarios or [int(configured.get('Delay Scenario', '0'))]
    headway = getattr(args, 'headway_sweep', None)
    if headway is not None:
        from .native_headway_plan import course_pair, headway_shift, require_shared_block, sweep_courses

        scenarios = [0]
        study = headway.model_dump()
        pair = sweep_courses(args.expectations, study)
        blobs = headway_source_blobs(project, configured, inputs)
        courses = course_pair(blobs['courses'], [item['course_id'] for item in pair], headway.comparison_mode)
        if headway.comparison_mode == 'shared_fixed_block':
            require_shared_block(project, inputs[args.run_file], inputs, blobs['dest'], courses)
        headway_shift(blobs, study, headway.minimum_s)
        headway_shift(blobs, study, headway.maximum_s)
    require(len(set(scenarios)) == len(scenarios) and all(-1 <= item <= 2147483647 for item in scenarios),
            'Delay scenarios must be unique original integers: -1 for Defined, 0 for None, or a positive scenario')
    mode = getattr(args, 'mode', 'batch')
    require(mode in ('batch', 'interactive'), 'Unknown native simulation job mode')
    if mode == 'interactive':
        require(len(scenarios) == 1, 'Interactive mode runs one scenario at a time')
        interactive_break(inputs[args.run_file])
    request = {
        'project_directory': args.project_directory, 'executable': args.executable,
        'run_file': args.run_file, 'scenarios': scenarios, 'timeout_s': args.timeout_s,
        'expectations': args.expectations, 'source_sha256': hashes, 'mode': mode,
    }
    if headway is not None:
        request['headway_sweep'] = headway.model_dump()
    if rule_source is not None:
        request['dispatching_rules'] = rule_binding
    return NativeJobPlan(executable, project, job, inputs, request, rule_files)


def start(root, args):
    require(sys.platform == 'win32', 'Original OpenTrack job control requires Windows')
    require_authorization(root)
    plan = plan_start(root, args)
    job, request = plan.job, plan.request

    job.mkdir(parents=True, exist_ok=False)
    write_json(job / 'state.json', {'state': 'preparing', 'updated_utc': now(), 'runs': []})
    try:
        store_members(job / 'source', plan.inputs)
        if plan.dispatching_files:
            store_members(job / OTD_DIRECTORY, plan.dispatching_files)
        write_json(job / 'request.json', request)
        with (job / 'worker.log').open('xb') as log:
            worker = subprocess.Popen(
                [sys.executable, '-B', '-m', 'opentrack_ai.native_execution', str(root), args.job_directory],
                cwd=Path(__file__).resolve().parent.parent, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        write_json(job / 'submission.json', {'worker_pid': worker.pid,
                                             'worker_identity': process_identity(worker.pid)})
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        write_json(job / 'state.json', {'state': 'failed', 'updated_utc': now(), 'error': str(exc), 'runs': []})
        raise
    return {'state': 'submitted', 'executed': True, 'job_directory': args.job_directory, 'mode': request['mode'],
            'worker_pid': worker.pid, 'scenarios': request['scenarios'], 'source_sha256': request['source_sha256'],
            **{key: request[key] for key in ('headway_sweep', 'dispatching_rules') if key in request},
            'native_simulation_verified': False}


def job_control(root, args):
    require(sys.platform == 'win32', 'Original OpenTrack job control requires Windows')
    require_authorization(root)
    job = child_path(root, args.job_directory)
    require(child_path(job, 'submission.json').is_file(), 'No submitted native job at the selected path')
    state = read_json(child_path(job, 'state.json'))
    identity = read_json(child_path(job, 'submission.json'))['worker_identity']
    worker_alive = identity is not None and process_identity(identity['pid']) == identity
    cancel_flag = child_path(job, 'cancel.request')
    if state['state'] not in TERMINAL_STATES and not worker_alive:
        # The worker may have committed its final state between the two reads.
        state = read_json(child_path(job, 'state.json'))
        if state['state'] not in TERMINAL_STATES:
            state = {**state, 'last_recorded_state': state['state'], 'state': 'worker_lost'}
    if args.action == 'stop' and state['state'] not in TERMINAL_STATES and worker_alive:
        # The worker retains the child handle. A cancellation never targets a PID
        # obtained from disk, so a replaced or unrelated process cannot be stopped.
        cancel_flag.touch(exist_ok=True)
    mode = read_json(child_path(job, 'request.json')).get('mode', 'batch')
    return {**state, 'job_directory': args.job_directory, 'requested_action': args.action, 'mode': mode,
            'worker_alive': worker_alive, 'cancel_requested': cancel_flag.is_file()}


def scenario_members(source, project, inputs, request, scenario, *, headway_s=None, dispatching_xml=None):
    from .current_archive.itinerary_edit_tools import EditableItineraryProject

    members, relocation = relocate_project(
        inputs, source_root=source.as_posix(), target_root=project.as_posix(),
        run_file=request['run_file'], expected_hashes=request['source_sha256'],
        discard_unrelated_destinations=True, project_type=EditableItineraryProject,
    )
    run_name = request['run_file']
    members[run_name] = batch_runfile(members[run_name], scenario, interactive=request.get('mode') == 'interactive',
                                     expectations=request.get('expectations'))
    timetable_name = relocation['catalog_paths']['timetable']
    members[timetable_name], reset = reset_copied_actuals(members[timetable_name])
    if headway_s is not None:
        from .native_headway_plan import headway_shift

        blobs = {role: members[name] for role, name in relocation['catalog_paths'].items()}
        members[timetable_name] = headway_shift(blobs, request['headway_sweep'], headway_s)
    binding = request.get('dispatching_rules')
    if binding is not None:
        require(dispatching_xml is not None and digest(dispatching_xml) == binding['xml_sha256'],
                'Missing or modified frozen OTD XML for the scenario')
        require(not any(name.split('/')[0].casefold() == OTD_DIRECTORY for name in members),
                'The frozen OTD directory conflicts with a selected project member')
        members[OTD_RULE_MEMBER] = dispatching_xml
    return members, relocation, reset


def preview_scenario(job, source, inputs, request, scenario, *, headway_s=None, dispatching_xml=None):
    """Construct the exact prospective run and check its closure entirely in memory."""
    trial = job / 'runs' / str(scenario if headway_s is None else headway_s)
    project = trial / 'project'
    evidence = trial / 'evidence'
    members, relocation, reset = scenario_members(source, project, inputs, request, scenario, headway_s=headway_s,
                                                  dispatching_xml=dispatching_xml)
    run_name = request['run_file']
    prefix = project.as_posix() + '/'

    def bound_reader(path):
        require(path.startswith(prefix), f'Invalid relocated binding: {path}')
        return members[path[len(prefix):]]

    checked = preflight.check(members[run_name], bound_reader)
    require(checked['passed_static_subset'], f'Saved project preflight failed: {checked["errors"]}')
    return project, evidence, members, relocation, reset, checked


def prepare_scenario(job, source, inputs, request, scenario, *, headway_s=None, dispatching_xml=None):
    project, evidence, members, relocation, reset, checked = preview_scenario(
        job, source, inputs, request, scenario, headway_s=headway_s, dispatching_xml=dispatching_xml)
    binding = request.get('dispatching_rules')
    (project / 'output').mkdir(parents=True, exist_ok=False)
    evidence.mkdir(exist_ok=False)
    store_members(project, members)
    store_members(evidence / 'inputs', members)
    write_json(evidence / 'preflight.json', checked)
    write_json(evidence / 'relocation.json', {
        **relocation, 'reset_actual_timetable_rows': reset, 'delay_scenario': scenario,
        **({'planned_departure_headway_s': headway_s} if headway_s is not None else {}),
        **({'dispatching_rules': binding} if binding is not None else {}),
        'effective_input_sha256': {name: digest(raw) for name, raw in members.items()},
    })
    return project, evidence, members


def scenario_command(exe, project, request, members):
    run_file = child_path(project, request['run_file'])
    command = [str(exe), '-scriptinit', '-runfile=' + run_file.as_posix()]
    binding = request.get('dispatching_rules')
    if binding is not None:
        mode = binding['route_id_mode']
        require(mode in ('compound', 'route_name') and binding['scenario_member'] == OTD_RULE_MEMBER
                and OTD_RULE_MEMBER in members and digest(members[OTD_RULE_MEMBER]) == binding['xml_sha256'],
                'The original launch must use the exact frozen OTD rule copy')
        path = child_path(project, OTD_RULE_MEMBER).as_posix()
        require(path.isascii() and path.isprintable() and '=' not in path,
                'The original OTD launch requires a printable ASCII path with no equals sign')
        command.extend(('-dispatchingrules', '-dispatchingrulesfile=' + path))
        if mode == 'route_name':
            command.append('-routeidtype=routename')
    return command


def run_scenario(exe, project, evidence, members, job, request):
    command = scenario_command(exe, project, request, members)
    original_hashes = {name: digest(data) for name, data in members.items()}
    require(all(digest(child_path(project, name).read_bytes()) == value for name, value in original_hashes.items()),
            'Relocated bytes changed before original launch')
    require(digest(exe.read_bytes()) == STOCK_EXE_SHA, 'Original OpenTrack changed before launch')
    require(not process_is_open(), 'An existing OpenTrack session is active')
    preference = Path.home() / 'Library/OpenTrack/OpenTrack.pref'
    preference_before = digest(preference.read_bytes()) if preference.is_file() else None
    before = {'started_utc': now(), 'command': command, 'input_sha256': original_hashes,
              'executable_sha256': STOCK_EXE_SHA, 'prefs_sha256_before': preference_before,
              **({'dispatching_rules': request['dispatching_rules']} if request.get('dispatching_rules') else {})}
    write_json(evidence / 'before.json', before)
    output = project / 'output'
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 1 if request.get('mode') == 'interactive' else 0
    outcome = 'exited'
    with (evidence / 'stdout.txt').open('xb') as stdout, (evidence / 'stderr.txt').open('xb') as stderr:
        with subprocess.Popen(command, cwd=exe.parent, stdin=subprocess.DEVNULL,
                              stdout=stdout, stderr=stderr, startupinfo=startup) as process:
            write_json(evidence / 'child.json', {'pid': process.pid, 'launched_utc': now()})
            deadline = monotonic() + request['timeout_s']
            while process.poll() is None:
                if (job / 'cancel.request').is_file():
                    outcome = 'stopped'
                elif monotonic() >= deadline:
                    outcome = 'timed_out'
                if outcome != 'exited':
                    process.terminate()
                    process.wait(timeout=15)
                    break
                try:
                    process.wait(timeout=0.4)
                except subprocess.TimeoutExpired:
                    pass
    preference_after = digest(preference.read_bytes()) if preference.is_file() else None
    hashes = output_hashes(output) if outcome == 'exited' and process.returncode == 0 else {}
    result = {'outcome': outcome, 'pid': process.pid, 'exit_code': process.returncode,
              'output_directory': str(output), 'output_files': list(hashes) if hashes else
              sorted(path.name for path in output.iterdir() if path.is_file()), 'output_sha256': hashes,
              'prefs_sha256_before': preference_before, 'prefs_sha256_after': preference_after,
              'prefs_file_changed': preference_after != preference_before,
              'input_writebacks': {}}
    for name, expected in original_hashes.items():
        path = child_path(project, name)
        actual = digest(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            result['input_writebacks'][name] = actual
    write_json(evidence / 'process.json', result)
    return before, result


def summarize_delays(evaluations):
    groups = defaultdict(list)
    included = []
    unverified = []
    for scenario, evaluation in evaluations:
        if not evaluation['native_run_verified']:
            unverified.append(scenario)
            continue
        included.append(scenario)
        for course in evaluation['courses']:
            occurrences = defaultdict(int)
            for event in course['events']:
                if event.get('delay_s') is None:
                    continue
                identity = (course['course_id'], event['station'], event['kind'], event['planned_s'])
                occurrences[identity] += 1
                groups[(*identity, occurrences[identity])].append((scenario, event['delay_s']))
    stations = []
    for (course_id, station, kind, planned, occurrence), samples in sorted(groups.items()):
        delays = [value for _, value in samples]
        stations.append({
            'course_id': course_id, 'station': station, 'event': kind, 'planned_s': planned,
            'occurrence': occurrence, 'scenarios': [scenario for scenario, _ in samples],
            'sample_count': len(delays), 'min_delay_s': min(delays), 'max_delay_s': max(delays),
            'mean_delay_s': mean(delays), 'median_delay_s': median(delays),
            'late_count': sum(delay > 0 for delay in delays),
        })
    return {'source': 'Frozen actual native .tt events from verified scenarios',
            'included_scenarios': included, 'unverified_scenarios': unverified, 'events': stations}


def worker(root, job_name):
    job = child_path(root, job_name)
    results = []
    evaluations = []

    def set_state(state, **details):
        write_json(job / 'state.json', {'state': state, 'updated_utc': now(), 'runs': results,
                                        'native_simulation_verified': False, **details})

    try:
        require_authorization(root)
        request = read_json(job / 'request.json')
        source = child_path(root, request['project_directory'])
        exe = child_path(root, request['executable'])
        inputs = {name: child_path(job / 'source', name).read_bytes() for name in request['source_sha256']}
        dispatching_xml = None
        binding = request.get('dispatching_rules')
        if binding is not None:
            rule_files, checked_binding = capture_dispatching_rules(root, source, request['run_file'], inputs,
                                                                   binding['manifest_source'],
                                                                   frozen=job / OTD_DIRECTORY)
            require(checked_binding == binding, 'Frozen OTD launch binding changed after submission')
            dispatching_xml = rule_files[otd.XML_FILE]
        sweep = request.get('headway_sweep')
        if sweep is not None:
            from .simulation_evidence import HeadwaySweep

            sweep = HeadwaySweep.model_validate(sweep).model_dump()
            request['headway_sweep'] = sweep
        trials = ((value, None) for value in request['scenarios']) if sweep is None else (
            (0, value) for value in range(sweep['minimum_s'], sweep['maximum_s'] + 1))
        with native_lock():
            for scenario, headway_s in trials:
                if (job / 'cancel.request').is_file():
                    set_state('stopped')
                    return
                active = {'active_scenario': scenario}
                if headway_s is not None:
                    active['active_headway_s'] = headway_s
                set_state('preparing', **active)
                project, evidence, members = prepare_scenario(job, source, inputs, request, scenario,
                                                              headway_s=headway_s, dispatching_xml=dispatching_xml)
                if (job / 'cancel.request').is_file():
                    set_state('stopped')
                    return
                set_state('running', **active)
                before, process = run_scenario(exe, project, evidence, members, job, request)
                summary = {'scenario': scenario, **{key: value for key, value in process.items() if key != 'output_sha256'},
                           'evidence_directory': evidence.relative_to(root).as_posix(),
                           'native_simulation_verified': False}
                if headway_s is not None:
                    summary['planned_departure_headway_s'] = headway_s
                results.append(summary)
                if process['outcome'] != 'exited':
                    set_state(process['outcome'])
                    return
                require(process['exit_code'] == 0, f'Original OpenTrack exited with code {process["exit_code"]}')
                if request['expectations']:
                    from .current_archive.native_run_evaluation import evaluate_run
                    evaluated = evaluate_run(project / 'output', request['expectations'],
                                             {**before, **process, 'evidence_directory': evidence})
                    write_json(evidence / 'evaluation.json', evaluated)
                    evaluations.append((scenario, evaluated))
                    summary['native_simulation_verified'] = evaluated['native_run_verified'] is True
            if evaluations and sweep is None:
                write_json(job / 'delay-summary.json', summarize_delays(evaluations))
            set_state('completed', native_simulation_verified=all(row['native_simulation_verified'] for row in results))
    except Exception as exc:
        set_state('failed', error=str(exc), error_type=type(exc).__name__)
        raise


if __name__ == '__main__':
    worker(Path(sys.argv[1]).resolve(), sys.argv[2])
