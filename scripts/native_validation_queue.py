"""Review a native acceptance queue and optionally submit it to the existing workers."""

import argparse
import json
import os
from pathlib import Path
import sys

from ot import check_python, locate_backend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--case', action='append', default=[])
    parser.add_argument('--report', type=Path)
    parser.add_argument('--execute', action='store_true', help='Start the original workers after a successful dry review')
    args = parser.parse_args()
    if args.execute and args.report is None:
        parser.error('--execute requires a fresh --report to record the plan before submission')

    check_python()
    _, backend = locate_backend(Path(__file__).with_name('ot.py'), os.environ)
    sys.path.insert(0, str(backend.parent))
    from opentrack_ai import native_execution as native, native_validation_queue as queue_ops
    from opentrack_ai.license_authorization import require_authorization
    from opentrack_ai.registry import Registry
    from opentrack_ai.service import Service

    root = args.root.resolve(strict=True)
    queue_path = args.queue.resolve(strict=True)
    queue_location, queue_sha, payload = queue_ops.checked_json(root, queue_path.relative_to(root).as_posix())
    registry = Registry(Service(root, False, False), profile='all')
    cases = queue_ops.review(root, registry, queue_ops.Queue.model_validate(payload), args.case)
    path = args.report.resolve() if args.report else None
    if path is not None:
        native.require(path.is_relative_to(root) and not path.exists() and path.parent.is_dir(),
                       'Report must be a new file in an existing data-root directory')
        for case in cases:
            for name in ('job_directory', 'source_directory'):
                native.require(name not in case or not path.is_relative_to(Path(case[name])),
                               'Report must remain separate from all source and work directories')
    report = {'phase': 'dry-run', 'queue_path': queue_location.as_posix(), 'queue_sha256': queue_sha,
              'all_cases_ready': all(case['state'] == 'ready' for case in cases),
              'native_job_submissions_attempted': 0, 'cases': cases}

    def record():
        if path is not None:
            native.write_json(path, report)

    def show():
        summary = report if path is None else {
            'report': path.as_posix(), 'phase': report['phase'], 'all_cases_ready': report['all_cases_ready'],
            'native_job_submissions_attempted': report['native_job_submissions_attempted'],
            'blocked_cases': {case['id']: case['reason'] for case in cases if case['state'] == 'blocked'},
            **{key: report[key] for key in ('all_automatic_checks_passed', 'manual_checks_pending') if key in report},
        }
        print(json.dumps(summary, ensure_ascii=False))

    record()
    if not args.execute or not report['all_cases_ready']:
        show()
        return 0 if report['all_cases_ready'] else 1

    require_authorization(root)
    report['phase'] = 'serial-execution'
    for case in cases:
        report['native_job_submissions_attempted'] += 1
        case['execution'] = {'state': 'about-to-submit'}
        record()
        try:
            case['execution'] = queue_ops.execute_case(root, registry, case,
                lambda message: print(message, file=sys.stderr, flush=True))
        except (ValueError, OSError, KeyError, IndexError, TypeError) as exc:
            case['execution'] = {'automatic_checks_passed': False, 'reason': str(exc)[:900]}
            # A submission or observation error can leave the existing worker active.
            # Return its path in the report and let the owner inspect it before proceeding.
            report['phase'] = 'serial-execution-interrupted'
            record()
            raise
        record()
    report['all_automatic_checks_passed'] = all(case['execution']['automatic_checks_passed'] for case in cases)
    report['manual_checks_pending'] = [case['id'] for case in cases if case['manual_checks']]
    report['phase'] = 'serial-execution-completed'
    record()
    show()
    return 0 if report['all_automatic_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
