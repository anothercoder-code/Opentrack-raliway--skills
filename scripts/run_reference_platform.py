"""Run an isolated, published reference-platform case with the verified original."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from ot import check_python, locate_backend
from verify_reference_platform_run import STOCK_EXE_SHA, checked, digest, verify


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def run(args):
    check_python()
    checked(sys.platform == 'win32', 'The verified original launcher requires Windows')
    root = args.root.resolve()
    import os

    _, backend = locate_backend(Path(__file__).with_name('ot.py'), os.environ)
    sys.path.insert(0, str(backend.parent))
    from opentrack_ai.license_authorization import require_authorization
    from opentrack_ai.registry import Registry
    from opentrack_ai.service import Service
    from opentrack_ai.current_archive.prepare_contract.auxiliary import records

    require_authorization(root)
    prepared = json.loads(args.receipt.read_bytes())
    request = json.loads(args.request.read_bytes())
    checked(prepared.get('saved') is True and prepared.get('tool') == 'opentrack_build_reference_platform_corridor',
            'A published reference-platform receipt is required')
    project = (root / prepared['target_directory']).resolve()
    execution_root = Path(request['spec']['network']['execution_root']).resolve()
    checked(project == execution_root and project.is_relative_to(root), 'Project identity differs from request')
    exe = args.exe.resolve()
    checked(digest(exe) == STOCK_EXE_SHA, 'Original OpenTrack executable fingerprint differs')
    evidence = args.evidence.resolve()
    checked(evidence.is_relative_to(root) and not evidence.is_relative_to(project)
            and not project.is_relative_to(evidence), 'Use a separate fresh evidence directory in the data root')
    output = project / 'output'
    checked(output.is_dir() and not any(output.iterdir()), 'Use the project’s fresh empty output directory')
    hashes = {name: meta['sha256'] for name, meta in prepared['files'].items()}
    run_file, = [name for name in hashes if Path(name).suffix == '.run']
    preflight = Registry(Service(root, False, False), profile='all').envelope(
        'opentrack_preflight_simulation_prepare',
        {'domain': 'multi_document', 'source_project': {
            'project_directory': project.relative_to(root).as_posix(), 'files': hashes,
            'complete_project_inventory': True, 'run_file': run_file, 'execution_root': project.as_posix(),
        }},
    )
    checked(preflight['ok'] and preflight['result']['passed_static_subset'],
            f'Saved project failed original-run preflight: {preflight.get("error") or preflight.get("result", {}).get("errors")}')
    inputs = {name: (project / name).read_bytes() for name in hashes}
    checked({name: hashlib.sha256(raw).hexdigest() for name, raw in inputs.items()} == hashes,
            'Published project members changed before launch')
    settings = {key: value for key, value, _ in records(inputs[run_file])}
    checked(settings.get('Break Time') == '00:00:00' and settings.get('Delay Scenario') == '0'
            and Path(settings['OutputPath']).resolve() == output,
            'Bound deterministic original-run controls and local output are required')
    command = [str(exe), '-scriptinit', '-runfile=' + (project / run_file).as_posix()]
    checked(all(part.isascii() for part in command), 'The original requires ASCII executable and run paths')
    checked(1 <= args.timeout <= 1800, 'Timeout must be 1 to 1800 seconds')
    process_count = subprocess.check_output(
        ['powershell.exe', '-NoProfile', '-Command', "@(Get-Process -Name 'OpenTrack*' -ErrorAction SilentlyContinue).Count"],
        text=True,
    ).strip()
    checked(process_count == '0', 'An existing OpenTrack session is active')
    evidence.mkdir(parents=True, exist_ok=False)
    write_json(evidence / 'preflight.json', preflight)
    for name, raw in inputs.items():
        backup = evidence / 'inputs' / name
        backup.parent.mkdir(parents=True, exist_ok=True)
        with backup.open('xb') as file:
            file.write(raw)
    prefs = Path.home() / 'Library/OpenTrack/OpenTrack.pref'
    prior_prefs = digest(prefs) if prefs.is_file() else None
    write_json(evidence / 'before.json', {
        'started_utc': datetime.now(timezone.utc).isoformat(), 'command': command,
        'executable_sha256': STOCK_EXE_SHA, 'input_sha256': hashes,
    })
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    with (evidence / 'stdout.txt').open('xb') as stdout, (evidence / 'stderr.txt').open('xb') as stderr:
        process = subprocess.Popen(command, cwd=exe.parent, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, startupinfo=startup)
        print(f'Original OpenTrack PID {process.pid}', flush=True)
        try:
            process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=30)
            write_json(evidence / 'timeout.json', {'owned_pid': process.pid, 'simulator_exited': True})
            raise
    write_json(evidence / 'process.json', {
        'exit_code': process.returncode, 'pid': process.pid, 'output_directory': str(output),
        'output_files': sorted(file.name for file in output.iterdir()),
        'input_writebacks': {name: value for name in hashes
                             if (value := digest(project / name)) != hashes[name]},
        'prefs_file_changed': (digest(prefs) if prefs.is_file() else None) != prior_prefs,
    })
    result = verify(project, request, prepared, evidence)
    write_json(evidence / 'platform-verification.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=180)
    run(parser.parse_args())
