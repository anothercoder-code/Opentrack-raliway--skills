"""Explicit user-approved same-path apply/rollback for one reviewed worksheet."""

from collections import defaultdict
import json
import os
import re
from subprocess import SubprocessError
from typing import Literal

from ..errors import APIError
from ..native_execution import native_lock, process_is_open
from . import writer
from .bundle_tools import Source
from .movement_application_tools import MovementApplicationTools, PrepareMovementApplication, unique_json_keys
from .prepare_contract import auxiliary
from .saved_geometry import project_from
from .tools import Input, PathText, sha
from .windows_publish import publish_project
from .windows_scoped_replace import inspect_current, recover_vacant_name, replace_verified, retained_siblings
from .zero_generation.empty_project import worksheet_header_fingerprint
from .zero_operations.run_bundle import CATALOG_KEYS, EXTENSIONS


FORMAT = 'opentrack-single-worksheet-recovery/1'


class ApplyReviewedWorksheet(Input):
    project_run: Source
    bundle_manifest: Source
    recovery_directory: PathText
    consent: Literal['apply_reviewed_worksheet']


class RollbackReviewedWorksheet(Input):
    transaction: Source
    recovery_directory: PathText
    consent: Literal['restore_reviewed_worksheet']


def _need(condition, message):
    if not condition:
        raise APIError('REVIEWED_WORKSHEET_SCOPE', message)


def _closed():
    try:
        running = process_is_open()
    except (OSError, ValueError, RuntimeError, SubprocessError) as error:
        raise APIError('APPLICATION_STATE_UNVERIFIED', 'Could not confirm that known OpenTrack applications are closed',
                       str(error)[:300]) from error
    if running:
        raise APIError('APPLICATION_RUNNING', 'Close OpenTrack before modifying its existing saved worksheet')


def _rotation_from(plan):
    rotation = plan.get('rotation')
    _need(isinstance(rotation, dict), 'Missing native recovery identity')
    name = rotation.get('original_sibling')
    prefix = re.fullmatch(r'(\.otai-worksheet-[0-9a-f]{32})-original', name) if isinstance(name, str) else None
    _need(prefix and rotation.get('staged_sibling') == prefix[1] + '-staged', 'Unrecognized owned recovery sibling names')
    for key in ('original_identity', 'replacement_identity'):
        identity = rotation.get(key)
        _need(isinstance(identity, dict) and set(identity) == {'volume', 'file_id'}
              and type(identity['volume']) is int and 0 <= identity['volume'] < 2**64
              and isinstance(identity['file_id'], str) and re.fullmatch(r'[0-9a-f]{32}', identity['file_id']),
              'Invalid native recovery file identity')
    _need(rotation['original_identity'] != rotation['replacement_identity']
          and rotation['original_identity']['volume'] == rotation['replacement_identity']['volume'],
          'The original and staging file identities must be distinct and on the same volume')
    return rotation


class ReviewedWorksheetTools(MovementApplicationTools):
    def __init__(self, root, allow_apply):
        super().__init__(root)
        self.allow_apply = allow_apply

    def authorize(self):
        if not self.allow_apply:
            raise APIError('APPLY_DISABLED', 'In-place worksheet changes require explicit --allow-apply authorization')
        if os.name != 'nt':
            raise APIError('UNSUPPORTED_SECURE_FILESYSTEM', 'In-place worksheet changes require Windows x64 on a fixed local NTFS volume')

    def bytes_for(self, spec):
        path = self.path(spec.path)
        data = self.secure_bytes(path)
        if sha(data) != spec.sha256:
            raise APIError('SOURCE_CHANGED', 'A reviewed in-place input no longer matches its exact SHA', spec.path)
        return path, data

    def project_paths(self, run_source, *, vacant_targets=()):
        run, raw = self.bytes_for(run_source)
        scope = self.project_scope(run)
        root_size = 2 if run.relative_to(self.root).parts[0].casefold() == 'otprojects' else 3
        base = self.root.joinpath(*scope)
        _need(len(scope) == root_size and run.parent == base and run.suffix == '.run',
              'Select a named ordinary project, outside any immutable editor snapshot')
        rows = defaultdict(list)
        for key, value, _ in auxiliary.records(raw):
            rows[key].append(value)
        docs = [self.bound_run_path(base, name, '.opentrack') for name in rows['Infrastructure Document']]
        discovered = self.discovered_documents(base)
        expected = set(docs)
        _need(docs and len({path.stem.casefold() for path in docs}) == len(docs)
              and discovered <= expected and expected - discovered <= set(vacant_targets),
              'Review the complete original infrastructure document set')
        catalogs = {}
        for role, key in CATALOG_KEYS.items():
            _need(len(rows[key]) == 1, 'Every native catalogue must be explicitly bound by the reviewed run')
            catalogs[role] = self.bound_run_path(base, rows[key][0], EXTENSIONS[role])
        diagrams = [self.bound_run_path(base, name, '.otsimcor') for name in rows['Train Diagram Document']]
        peers = {run, *docs, *catalogs.values(), *diagrams}
        _need(len(peers) == 1 + len(docs) + len(catalogs) + len(diagrams), 'The reviewed project uses aliased native file roles')
        return base, docs, catalogs, peers

    def peer_images(self, peers, target):
        return {path: self.secure_bytes(path) for path in peers - {target}}

    def check_peers(self, images):
        _closed()
        for path, data in images.items():
            if self.secure_bytes(path) != data:
                raise APIError('SOURCE_CHANGED', 'An unaffected project dependency changed during the in-place operation',
                               path.relative_to(self.root).as_posix())

    def graph_pair(self, docs, dest, images, target, before, after):
        first, _ = writer.load_next_compatible(before)
        second, _ = writer.load_next_compatible(after)
        _need(worksheet_header_fingerprint(first) == worksheet_header_fingerprint(second),
              'The reviewed worksheet must retain its protected and other non-collection header data')
        paths = {path.stem: path.as_posix() for path in docs}
        unchanged = {path.stem: images[path] for path in docs if path != target}
        for blob in (before, after):
            project_from({**unchanged, target.stem: blob}, paths, images[dest])

    def recovery_target(self, args, base, *dependencies):
        location = self.path(args.recovery_directory)
        _need(not any(location.is_relative_to(path) or path.is_relative_to(location) for path in (base, *dependencies)),
              'Use a fresh recovery directory outside the project and all source evidence')
        return location

    def write_journal(self, location, data, before, after, rotation, verify):
        plan = {**data, 'rotation': rotation, 'format': FORMAT, 'before_sha256': sha(before), 'after_sha256': sha(after)}
        raw = (json.dumps(plan, ensure_ascii=True, indent=2) + '\n').encode('ascii')
        members = {'transaction.json': raw, 'before.opentrack': before, 'after.opentrack': after}

        def validate(actual):
            _need(actual == members, 'Durable recovery bytes differ from the reviewed worksheet images')

        publication = publish_project(self.root, location, members, recheck=verify, validate_bundle=validate, empty_directories=())
        return {'path': (location / 'transaction.json').relative_to(self.root).as_posix(),
                'sha256': sha(raw), 'committed': publication['commit_completed']}

    def store(self, target, images, before, after, data, location, *, identity=None):
        def verify():
            self.check_peers(images)

        def journal(rotation):
            return self.write_journal(location, data, before, after, rotation, verify)

        return replace_verified(self.root, target, before, after, authorize=verify, journal=journal,
                                expected_identity=identity)

    def apply(self, args):
        self.authorize()
        base, docs, catalogs, peers = self.project_paths(args.project_run)
        manifest_path, manifest = self.bytes_for(args.bundle_manifest)
        plan = json.loads(manifest, object_pairs_hook=unique_json_keys)
        _need(isinstance(plan, dict) and plan.get('format') == 'opentrack-saved-geometry-v1',
              'This in-place scope accepts only a saved current geometry increment')
        location = self.recovery_target(args, base, manifest_path.parent)
        _closed()
        with native_lock():
            reviewed, copies, changes, recheck, _ = self.review(PrepareMovementApplication(
                project_run=args.project_run, bundle_manifest=args.bundle_manifest,
            ))
            _need(len(changes) == 1 and changes.keys() <= set(docs), 'Apply only one existing run-bound worksheet; leave catalogues unchanged')
            target, after = next(iter(changes.items()))
            before = copies[reviewed['replacements'][0]['before']]
            images = self.peer_images(peers, target)
            self.graph_pair(docs, catalogs['dest'], images, target, before, after)
            recheck()
            data = {'project_run': args.project_run.model_dump(), 'source_bundle': args.bundle_manifest.model_dump(),
                    'worksheet': target.relative_to(self.root).as_posix(),
                    'peer_sha256': {path.relative_to(self.root).as_posix(): sha(blob) for path, blob in images.items()}}
            result = self.store(target, images, before, after, data, location)
        return {**result, 'applied': True, 'worksheet': data['worksheet'], 'original_launched': False}

    def rollback(self, args):
        self.authorize()
        path, raw = self.bytes_for(args.transaction)
        plan = json.loads(raw, object_pairs_hook=unique_json_keys)
        _need(path.name == 'transaction.json' and isinstance(plan, dict) and plan.get('format') == FORMAT,
              'Select an exact scoped worksheet recovery transaction')
        run = Source.model_validate(plan['project_run'])
        target = self.path(plan['worksheet'])
        base, docs, catalogs, peers = self.project_paths(run, vacant_targets=(target,))
        _need(target in docs, 'Recovery worksheet must remain bound to the reviewed original project')
        location = self.recovery_target(args, base, path.parent)
        rotation = _rotation_from(plan)
        before, after = (self.bytes_for(Source(path=(path.parent / f'{name}.opentrack').relative_to(self.root).as_posix(),
                                             sha256=plan[f'{name}_sha256']))[1] for name in ('before', 'after'))
        _need(before != after, 'Recovery must bind distinct original and replacement bytes')
        images = self.peer_images(peers, target)
        _need(plan['peer_sha256'] == {p.relative_to(self.root).as_posix(): sha(blob) for p, blob in images.items()},
              'An original project dependency changed after the reviewed in-place application')
        self.graph_pair(docs, catalogs['dest'], images, target, before, after)
        _closed()
        with native_lock():
            self.check_peers(images)
            state = inspect_current(self.root, target)
            if state is None:
                result = recover_vacant_name(self.root, target, before, after, rotation,
                                             authorize=lambda: self.check_peers(images))
            elif state == (rotation['original_identity'], sha(before)):
                result = {'already_original': True, 'restored_sha256': sha(before),
                          'retained_siblings': retained_siblings(self.root, target, rotation)}
            else:
                remnants = retained_siblings(self.root, target, rotation)
                if remnants:
                    raise APIError('SCOPED_REPLACEMENT_RECOVERY_REQUIRED',
                                   'A worksheet is present alongside interrupted recovery files. All files were preserved.',
                                   {'worksheet': plan['worksheet'], 'retained_siblings': remnants})
                data = {key: plan[key] for key in ('project_run', 'worksheet', 'peer_sha256')}
                data['source_transaction'] = args.transaction.model_dump()
                result = self.store(target, images, after, before, data, location, identity=rotation['replacement_identity'])
        return {**result, 'rolled_back': True, 'worksheet': plan['worksheet'], 'original_launched': False}


def tool_definitions(service):
    tools = ReviewedWorksheetTools(service.root, service.allow_apply)
    return [
        ('opentrack_apply_reviewed_worksheet', 'With explicit apply authorization and OpenTrack closed, apply one '
         'reviewed saved worksheet at its bound original path. Retain a fresh exact-byte recovery journal.',
         ApplyReviewedWorksheet, tools.apply, False, True),
        ('opentrack_rollback_reviewed_worksheet', 'Restore one applied or interrupted worksheet using its exact '
         'journal and verified identities. Requires explicit apply authorization and a closed OpenTrack application.',
         RollbackReviewedWorksheet, tools.rollback, False, True),
    ]
