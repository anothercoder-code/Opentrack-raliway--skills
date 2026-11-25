"""Explicit application and restoration of a closed run-bound native file set."""

import json
import re
from typing import Annotated, Literal

from pydantic import Field

from ..errors import APIError
from ..native_execution import native_lock
from . import catalogs, course_factories, writer
from .bundle_tools import Source
from .multi_document_tools import Hash
from .native_rolling_stock_import_tools import validate_saved_stock
from .pre_service_project import validate_pre_service_project
from .prepare_contract import preflight
from .reviewed_movement_apply import ReviewedWorksheetTools, _closed
from .tools import Input, PathText, sha
from .windows_project_rotation import apply_images, recover_images
from .windows_publish import publish_project
from .zero_generation.empty_project import worksheet_header_fingerprint
from .movement_application_tools import unique_json_keys


FORMAT = 'opentrack-run-bound-file-recovery/1'
MAX_TRANSACTION_BYTES = 128 * 1024 * 1024
MAX_UNCHANGED_BYTES = 256 * 1024 * 1024


class Replacement(Input):
    before: Source
    after: Source


class ApplyReviewedProjectFiles(Input):
    project_run: Source
    replacements: Annotated[list[Replacement], Field(min_length=2, max_length=32)]
    unchanged_sha256: Annotated[dict[PathText, Hash], Field(min_length=1, max_length=200)]
    recovery_directory: PathText
    consent: Literal['apply_reviewed_project_files']


class RollbackReviewedProjectFiles(Input):
    transaction: Source
    consent: Literal['restore_reviewed_project_files']


def _need(condition, message):
    if not condition:
        raise APIError('REVIEWED_PROJECT_FILES_INVALID', message)


def _read_archive(data):
    return writer.load_next_compatible(data)[0]


def _validate(base, run, paths, banks, changed):
    courses = catalogs.course_items(_read_archive(paths[banks['courses']]))
    timetable = course_factories.timetable(_read_archive(paths[banks['timetable']]))
    if not courses and not timetable:
        members = {path.relative_to(base).as_posix(): data for path, data in paths.items()}
        validate_pre_service_project(members, run_file=run.name, execution_root=base.as_posix())
        mode = 'pre_service'
    else:
        bound = {path.as_posix(): data for path, data in paths.items()}
        report = preflight.check(paths[run], bound.__getitem__)
        _need(report['passed_static_subset'], f'Native schedule and dependent bindings failed: {report["errors"]}')
        mode = 'scheduled'
    if changed & {banks['depot'], banks['trains']}:
        validate_saved_stock(paths[banks['depot']], paths[banks['trains']])
    return mode


def _bindings(row, index):
    result = row.get('rotation')
    _need(isinstance(result, dict) and set(result) == {'stage', 'vault_name', 'before_identity', 'after_identity'},
          'Recovery requires the exact native location and identity binding')
    staged = result['stage']
    _need(isinstance(staged, str) and re.fullmatch(r'\.otai-project-[0-9a-f]{32}-staged', staged)
          and result['vault_name'] == f'{index:04d}.native', 'Invalid reserved recovery file name')
    old, new = result['before_identity'], result['after_identity']
    for identity in (old, new):
        _need(isinstance(identity, dict) and set(identity) == {'volume', 'file_id'}
              and type(identity['volume']) is int and 0 <= identity['volume'] < 2**64
              and isinstance(identity['file_id'], str) and re.fullmatch(r'[0-9a-f]{32}', identity['file_id']),
              'Malformed recovery file identity')
    _need(old != new and old['volume'] == new['volume'], 'Recovery requires two distinct identities on one volume')
    return result


class ReviewedProjectFiles(ReviewedWorksheetTools):
    def _peers(self, peers, sources, declared):
        _need(isinstance(declared, dict)
              and set(declared) == {path.relative_to(self.root).as_posix() for path in peers - set(sources)},
              'Review exact SHA values for every other run-bound source member')
        unchanged = {}
        total = 0
        for path in sorted(peers - set(sources)):
            data = self.secure_bytes(path)
            total += len(data)
            _need(total <= MAX_UNCHANGED_BYTES, 'Unchanged run-bound files exceed the 256 MiB transaction limit')
            unchanged[path] = data
        if self._digests(unchanged) != declared:
            raise APIError('SOURCE_CHANGED', 'An unchanged run-bound source differs from the reviewed SHA')
        return unchanged

    def _digests(self, members):
        return {path.relative_to(self.root).as_posix(): sha(data) for path, data in members.items()}

    def _validate_pair(self, base, run, docs, banks, unchanged, entries):
        changed = {path for path, _, _ in entries}
        _need(changed <= set(docs) | set(banks.values()), 'Only existing run-bound worksheets and catalogues can change')
        _need(sum(len(before) + len(after) for _, before, after in entries) <= MAX_TRANSACTION_BYTES,
              'Reviewed images exceed the 128 MiB transaction limit')
        for path, before, after in entries:
            _need(before != after, 'Every approved replacement must change its exact raw bytes')
            if path in docs:
                _need(worksheet_header_fingerprint(_read_archive(before)) == worksheet_header_fingerprint(_read_archive(after)),
                      'A scoped worksheet change must retain its native non-collection header')
        try:
            before = _validate(base, run, {**unchanged, **{p: b for p, b, _ in entries}}, banks, changed)
            after = _validate(base, run, {**unchanged, **{p: a for p, _, a in entries}}, banks, changed)
        except (IndexError, KeyError, TypeError, ValueError, OverflowError) as error:
            raise APIError('REVIEWED_PROJECT_FILES_INVALID', 'An original or candidate archive set failed native closure',
                           str(error)[:700]) from error
        return {'before_mode': before, 'after_mode': after}

    def _journal(self, location, plan, entries, bindings, recheck):
        files = {}
        rows = []
        for index, ((path, before, after), binding) in enumerate(zip(entries, bindings, strict=True)):
            files[f'before/{index:04d}.archive'] = before
            files[f'after/{index:04d}.archive'] = after
            rows.append({'target': path.relative_to(self.root).as_posix(), 'before_sha256': sha(before),
                         'after_sha256': sha(after), 'rotation': binding})
        raw = (json.dumps({**plan, 'format': FORMAT, 'files': rows}, indent=2) + '\n').encode('ascii')
        files['transaction.json'] = raw

        def verify(actual):
            _need(actual == files, 'Staged recovery journal differs from its reviewed full image set')

        publication = publish_project(self.root, location, files, recheck=recheck, validate_bundle=verify,
                                      empty_directories=('before-held', 'after-held'))
        return {'path': (location / 'transaction.json').relative_to(self.root).as_posix(),
                'sha256': sha(raw), 'committed': publication['commit_completed']}

    def apply_files(self, args):
        self.authorize()
        _closed()
        with native_lock():
            base, docs, banks, peers = self.project_paths(args.project_run)
            run = self.path(args.project_run.path)
            entries, replacements = {}, {}
            total = 0
            for row in args.replacements:
                target = self.path(row.before.path)
                source = self.path(row.after.path)
                _need(target in set(docs) | set(banks.values()) and target not in entries,
                      'Approve each exact run-bound mutable member once')
                _need(source.suffix == target.suffix and not source.is_relative_to(base) and source not in replacements,
                      'Supply a distinct matching native replacement outside the reviewed project')
                _, before = self.bytes_for(row.before)
                _, after = self.bytes_for(row.after)
                total += len(before) + len(after)
                _need(total <= MAX_TRANSACTION_BYTES, 'Reviewed images exceed the 128 MiB transaction limit')
                entries[target] = (target, before, after)
                replacements[source] = after
            ordered = [entries[path] for path in sorted(entries)]
            location = self.recovery_target(args, base, *(path.parent for path in replacements))
            unchanged = self._peers(peers, entries, args.unchanged_sha256)
            validation = self._validate_pair(base, run, docs, banks, unchanged, ordered)

            def recheck():
                self.check_peers({**unchanged, **replacements})

            def record(bindings):
                plan = {'project_run': args.project_run.model_dump(), 'unchanged_sha256': self._digests(unchanged),
                        'reviewed_inputs': [item.model_dump() for item in args.replacements], 'validation': validation}
                return self._journal(location, plan, ordered, bindings, recheck)

            journal = apply_images(self.root, ordered, location, authorize=recheck, journal=record,
                                   dependencies={**unchanged, **replacements})
        return {'applied': True, 'journal': journal, 'files': self._digests({p: a for p, _, a in ordered}),
                'validation': validation, 'native_application_started': False, 'atomic_project_update': False}

    def rollback_files(self, args):
        self.authorize()
        _closed()
        with native_lock():
            path, raw = self.bytes_for(args.transaction)
            plan = json.loads(raw, object_pairs_hook=unique_json_keys)
            _need(path.name == 'transaction.json' and isinstance(plan, dict) and plan.get('format') == FORMAT,
                  'Select an exact multi-file native recovery journal')
            rows = plan.get('files')
            _need(isinstance(rows, list) and 2 <= len(rows) <= 32
                  and all(isinstance(row, dict) and isinstance(row.get('target'), str) for row in rows),
                  'Recovery journal has an invalid file inventory')
            targets = [self.path(row['target']) for row in rows]
            _need(targets == sorted(set(targets)), 'Recovery inventory contains an alias or unordered member')
            run_source = Source.model_validate(plan['project_run'])
            base, docs, banks, peers = self.project_paths(run_source, vacant_targets=targets)
            _need(not path.is_relative_to(base) and not base.is_relative_to(path.parent),
                  'Place recovery files and their vault outside the exact native source project')
            _need(set(targets) <= set(docs) | set(banks.values()), 'Recovery includes an unbound or immutable member')
            unchanged = self._peers(peers, targets, plan['unchanged_sha256'])
            entries = []
            journal_inputs = {path: raw}
            total = 0
            for index, (target, row) in enumerate(zip(targets, rows, strict=True)):
                (old_path, before), (new_path, after) = (self.bytes_for(Source(
                    path=(path.parent / side / f'{index:04d}.archive').relative_to(self.root).as_posix(),
                    sha256=row[f'{side}_sha256'])) for side in ('before', 'after'))
                journal_inputs[old_path] = before
                journal_inputs[new_path] = after
                total += len(before) + len(after)
                _need(total <= MAX_TRANSACTION_BYTES, 'Reviewed images exceed the 128 MiB transaction limit')
                entries.append((target, before, after, _bindings(row, index)))
            validation = self._validate_pair(base, self.path(run_source.path), docs, banks, unchanged,
                                             [(p, b, a) for p, b, a, _ in entries])
            recover_images(self.root, entries, path.parent, authorize=lambda: self.check_peers(unchanged),
                           dependencies={**unchanged, **journal_inputs})
        return {'restored': True, 'journal': args.transaction.model_dump(),
                'files': self._digests({p: b for p, b, _, _ in entries}),
                'original_file_identities_restored': True, 'validation': validation,
                'native_application_started': False, 'atomic_project_update': False}


def tool_definitions(service):
    tools = ReviewedProjectFiles(service.root, service.allow_apply)
    return [
        ('opentrack_apply_reviewed_project_files', 'Apply two to 32 reviewed run-bound worksheet or catalogue '
         'replacements while OpenTrack is closed. Authorize explicitly and retain the complete recovery journal.',
         ApplyReviewedProjectFiles, tools.apply_files, False, True),
        ('opentrack_rollback_reviewed_project_files', 'Restore exact original bytes and native file identities '
         'from a reviewed project recovery journal. Requires explicit apply authorization and a closed application.',
         RollbackReviewedProjectFiles, tools.rollback_files, False, True),
    ]
