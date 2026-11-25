"""Keep a persistent history of reviewed edits to saved native projects."""

from contextlib import contextmanager
import json
import os
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from ..errors import APIError
from . import catalogs, course_factories, writer
from .bundle_tools import Source
from .itinerary_edit_tools import EditableItineraryProject
from .movement_application_tools import FORMATS, MovementApplicationTools, PrepareMovementApplication, unique_json_keys
from .multi_document_tools import Hash, Inventory, MultiDocumentTools
from .pre_service_project import validate_pre_service_project
from .project_candidate_publication import ProjectSave, project_target, publish_candidate
from .project_workflow.relocation import relocate_project
from .station_candidate_workflow import StationCandidateTools
from .tools import Input, PathText, sha
from .windows_publish import publish_project
from .zero_generation.empty_project import worksheet_header_fingerprint


MAX_REVISION = 9999
SCHEMA = 'opentrack-native-editor-event/1'
OPERATING_INCREMENT = 'opentrack-operating-plan-increment-v1'
Label = Annotated[StrictStr, Field(min_length=1, max_length=200, pattern=r'^[^\x00\r\n]+$')]
Revision = Annotated[StrictInt, Field(ge=0, le=MAX_REVISION)]


class EditorLocation(Input):
    session_directory: PathText


class StartNativeEditor(EditorLocation):
    source_project: Inventory
    label: Label = 'Initial snapshot'
    preview_only: StrictBool = True


class ExpectedEditor(EditorLocation):
    expected_revision: Revision
    expected_event_sha256: Hash


class EditNativeEditor(ExpectedEditor):
    action: Literal['stage', 'undo', 'redo']
    bundle_manifests: Annotated[list[Source], Field(max_length=32)] = Field(default_factory=list)
    label: Label | None = None
    preview_only: StrictBool = True

    @model_validator(mode='after')
    def edit_inputs(self):
        if (self.action == 'stage') != bool(self.bundle_manifests):
            raise ValueError('Provide one or more bundle manifests when staging native changes')
        return self


class PublishNativeEditor(ExpectedEditor, ProjectSave):
    snapshot_revision: Revision | None = None


def require(condition, message, *, code='NATIVE_EDITOR_INVALID'):
    if not condition:
        raise APIError(code, message)


def external(first, second):
    return not (first.is_relative_to(second) or second.is_relative_to(first))


def event_folder(session, revision):
    return session / 'history' / f'{revision:04d}'


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')


@contextmanager
def session_transaction(session):
    require(os.name == 'nt', 'Writing an editor revision requires Windows NTFS publication',
            code='UNSUPPORTED_SECURE_FILESYSTEM')
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    name = 'Local\\OpenTrackSkillEditor-' + sha(session.as_posix().casefold().encode('utf-8'))
    lock = kernel.CreateMutexW(None, False, name)
    require(lock, 'Could not acquire the native editor transaction mutex', code='NATIVE_EDITOR_LOCK')
    owned = kernel.WaitForSingleObject(lock, 0) in (0, 0x80)
    try:
        require(owned, 'Another writer is committing a native editor revision', code='NATIVE_EDITOR_BUSY')
        yield
    finally:
        if owned:
            kernel.ReleaseMutex(lock)
        kernel.CloseHandle(lock)


def read_snapshot_scope(tools, path, revision):
    """Recognize an editor revision as a normal run-bound project read scope."""
    try:
        event = json.loads(tools.secure_bytes(path), object_pairs_hook=unique_json_keys)
        snapshot = Inventory.model_validate(event['snapshot'])
        expected = path.parent / 'project'
        require(event['schema'] == SCHEMA and type(event['revision']) is int and event['revision'] == int(revision)
                and event['action'] in ('start', 'stage')
                and tools.path(snapshot.project_directory) == expected
                and snapshot.execution_root == expected.as_posix(),
                'The native editor event has no project snapshot at this scope')
    except (KeyError, TypeError, ValueError) as exc:
        raise APIError('NATIVE_EDITOR_INVALID', 'The native editor snapshot scope is invalid', str(exc)[:500]) from exc


class NativeEditorTools(MultiDocumentTools):
    def _session_action(self, args, operation):
        session = self.path(args.session_directory)
        if args.preview_only:
            return operation(args, session)
        with session_transaction(session):
            return operation(args, session)

    def _actual_project(self, inventory):
        state = self.load_project(inventory, minimum_documents=1)
        require(state['root'] == state['base'].as_posix(), 'Bind the selected native run to its actual project root')
        return state

    def _validate_snapshot(self, files, report, target, run):
        def catalogue(role):
            return writer.load_next_compatible(files[report['catalog_paths'][role]])[0]

        courses = catalogue('courses')
        timetable = catalogue('timetable')
        if not catalogs.course_items(courses) and not course_factories.timetable(timetable):
            return {'mode': 'pre_service',
                    'readback': validate_pre_service_project(files, run_file=run, execution_root=target.as_posix())}
        return {'mode': 'scheduled', 'readback': StationCandidateTools(self.root)._preflight(target, run, files)}

    def _move(self, state, updated, run, target):
        members, relocation = relocate_project(
            updated, source_root=state['root'], target_root=target.as_posix(), run_file=run,
            expected_hashes={name: sha(blob) for name, blob in updated.items()}, project_type=EditableItineraryProject,
        )
        validation = self._validate_snapshot(members, relocation, target, run)
        inventory = Inventory(project_directory=target.relative_to(self.root).as_posix(), execution_root=target.as_posix(),
                              run_file=run, complete_project_inventory=True,
                              files={name: sha(blob) for name, blob in members.items()})
        return members, inventory, validation, relocation

    def _event(self, session, revision, action, parent, label=None, snapshot=None, source=None, changed=()):
        event = {'schema': SCHEMA, 'revision': revision, 'action': action, 'parent_sha256': parent,
                 'label': label, 'changed_members': list(changed)}
        if snapshot is not None:
            event['snapshot'] = snapshot.model_dump()
            require(self.path(snapshot.project_directory) == event_folder(session, revision) / 'project',
                    'A snapshot must live in its own immutable editor event')
        if source is not None:
            event['source_project'] = source.model_dump()
        return event

    def _load(self, session):
        history, snapshots, cursor = [], {}, -1
        source, tip, digest = None, None, None
        for revision in range(MAX_REVISION + 1):
            folder = event_folder(session, revision)
            if not folder.exists():
                break
            data = self.secure_bytes(folder / 'event.json')
            try:
                event = json.loads(data, object_pairs_hook=unique_json_keys)
                action = event['action']
                require(event['schema'] == SCHEMA and type(event['revision']) is int
                        and event['revision'] == revision and event['parent_sha256'] == digest,
                        'Saved editor event order or fingerprint chain differs')
                if revision == 0:
                    require(action == 'start', 'Editor history must start with an initial snapshot')
                    source = Inventory.model_validate(event['source_project'])
                else:
                    require(action in ('stage', 'undo', 'redo'), 'Unexpected editor event action')
                if action in ('start', 'stage'):
                    snapshot = Inventory.model_validate(event['snapshot'])
                    require(self.path(snapshot.project_directory) == folder / 'project'
                            and snapshot.execution_root == (folder / 'project').as_posix()
                            and snapshot.run_file == source.run_file,
                            'Editor snapshot points outside its selected native project')
                    history = [*history[:cursor + 1], revision]
                    snapshots[revision] = snapshot
                    cursor += 1
                else:
                    require('snapshot' not in event, 'A history selection may not change snapshot files')
                    cursor += -1 if action == 'undo' else 1
                    require(0 <= cursor < len(history), 'Saved editor event crosses the history boundary')
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise APIError('NATIVE_EDITOR_INVALID', 'Saved editor event is invalid', str(exc)[:500]) from exc
            tip, digest = event, sha(data)
        require(tip is not None, 'Native editor session does not exist', code='NATIVE_EDITOR_NOT_FOUND')
        return tip, digest, source, snapshots, history, cursor

    def _expected(self, session, args):
        loaded = self._load(session)
        event, digest, *_ = loaded
        require((event['revision'], digest) == (args.expected_revision, args.expected_event_sha256),
                'Read the current editor revision before retrying', code='NATIVE_EDITOR_REVISION_CONFLICT')
        return loaded

    def _view(self, session, loaded):
        event, digest, source, snapshots, history, cursor = loaded
        return {'session_directory': session.relative_to(self.root).as_posix(), 'revision': event['revision'],
                'event_sha256': digest, 'action': event['action'], 'label': event['label'],
                'snapshot_revision': history[cursor], 'current_project': snapshots[history[cursor]].model_dump(),
                'source_project': source.model_dump(), 'active_history': history,
                'preserved_snapshot_revisions': list(snapshots), 'undo_available': cursor > 0,
                'redo_available': cursor + 1 < len(history), 'original_application_started': False}

    def _publish_event(self, target, event, recheck, members=None, *, initial=False):
        prefix = 'history/0000/' if initial else ''
        payload = {prefix + 'event.json': encode(event)}
        directories = ()
        if members is not None:
            payload.update({prefix + 'project/' + name: data for name, data in members.items()})
            directories = (prefix + 'project/output',)

        def validate(actual):
            require(actual == payload, 'Published editor event differs from its reviewed bytes')

        return publish_project(self.root, target, payload, recheck=recheck, validate_bundle=validate,
                               empty_directories=directories)

    def start(self, args):
        return self._session_action(args, self._start)

    def _start(self, args, session):
        source = self._actual_project(args.source_project)
        require(external(session, source['base']), 'Select an editor session directory separate from the source project')
        selected = {name: source['files'][name] for name in source['selected']}
        try:
            members, snapshot, validation, relocation = self._move(
                source, selected, args.source_project.run_file, event_folder(session, 0) / 'project')
        except (IndexError, KeyError, OverflowError, TypeError, ValueError) as exc:
            raise APIError('NATIVE_EDITOR_INVALID', 'Source project could not be frozen', str(exc)[:500]) from exc
        event = self._event(session, 0, 'start', None, args.label, snapshot, args.source_project)
        loaded = event, sha(encode(event)), args.source_project, {0: snapshot}, [0], 0
        self.recheck(source)
        result = {**self._view(session, loaded), 'preview_only': args.preview_only, 'saved': False,
                  'validation': validation, 'relocation': relocation,
                  'unbound_source_member_count': len(source['files']) - len(selected)}
        if args.preview_only:
            return result
        receipt = self._publish_event(session, event, lambda: self.recheck(source), members, initial=True)
        self.read(args)
        return {**result, 'saved': True, 'publication': receipt}

    def read(self, args):
        session = self.path(args.session_directory)
        loaded = self._load(session)
        _, _, _, snapshots, history, cursor = loaded
        selected = self._actual_project(snapshots[history[cursor]])
        self.recheck(selected)
        return self._view(session, loaded)

    def _operating_replacements(self, source, data, manifest, state, run):
        members, targets = manifest['files'], manifest['replacement_for']
        require(manifest['complete_relocated_project'] is False and isinstance(members, dict)
                and isinstance(targets, dict) and 1 <= len(members) <= 7 and members.keys() == targets.keys(),
                'Invalid operating archive replacement inventory')
        allowed = {state['roles'][role] for role in ('stations', 'depot', 'trains', 'courses', 'timetable')} | {run}
        inputs = {source: data}
        updated = {}
        for name, old in targets.items():
            target = self.path(old)
            require(target.name == name and target.is_relative_to(state['base']), 'Operating edit has an unrelated target')
            relative = target.relative_to(state['base']).as_posix()
            require(relative in allowed and relative not in updated, 'Select a distinct run-bound operating archive')
            details = members[name]
            require(details['before_sha256'] == sha(state['files'][relative]),
                    'Operating archive preimage differs from the editor snapshot', code='SOURCE_CHANGED')
            replacement = source.parent / name
            require(external(source.parent, state['base']), 'Operating replacement bundle must be outside the snapshot')
            blob = self.secure_bytes(replacement)
            require(type(details['bytes']) is int and (len(blob), sha(blob)) == (details['bytes'], details['sha256']),
                    'Operating replacement fingerprint differs', code='SOURCE_CHANGED')
            updated[relative], inputs[replacement] = blob, blob

        def recheck():
            for path, blob in inputs.items():
                require(self.secure_bytes(path) == blob, 'Operating bundle changed during staging', code='SOURCE_CHANGED')

        return updated, recheck

    def _bundle(self, binding, state, run):
        manifest_path = self.path(binding.path)
        raw = self.secure_bytes(manifest_path)
        require(manifest_path.name == 'bundle-manifest.json' and sha(raw) == binding.sha256,
                'Select the exact bundle-manifest.json fingerprint', code='SOURCE_CHANGED')
        manifest = json.loads(raw, object_pairs_hook=unique_json_keys)
        if manifest.get('format') == OPERATING_INCREMENT:
            return self._operating_replacements(manifest_path, raw, manifest, state, run)
        require(manifest.get('format') in FORMATS, 'Unsupported native editor bundle format')
        run_source = Source(path=(state['base'] / run).relative_to(self.root).as_posix(), sha256=sha(state['files'][run]))
        _, _, material, recheck, _ = MovementApplicationTools(self.root).review(
            PrepareMovementApplication(project_run=run_source, bundle_manifest=binding))
        updated = {path.relative_to(state['base']).as_posix(): blob for path, blob in material.items()}
        for name, blob in updated.items():
            if name in state['document_members'].values():
                original, _ = writer.load_next_compatible(state['files'][name])
                saved, _ = writer.load_next_compatible(blob)
                require(worksheet_header_fingerprint(original) == worksheet_header_fingerprint(saved),
                        'Editor movement bundles must preserve the worksheet header')
        return updated, recheck

    def edit(self, args):
        return self._session_action(args, self._edit)

    def _edit(self, args, session):
        tip, digest, source, snapshots, history, cursor = self._expected(session, args)
        revision = tip['revision'] + 1
        require(revision <= MAX_REVISION, 'The editor history has reached its revision limit')
        previous = self._actual_project(snapshots[history[cursor]])
        bundle_checks, members, snapshot, validation = [], None, None, None
        change = {}
        if args.action == 'stage':
            run = snapshots[history[cursor]].run_file
            try:
                for binding in args.bundle_manifests:
                    proposed, recheck = self._bundle(binding, previous, run)
                    require(not change.keys() & proposed.keys(), 'Review a single replacement per member in this editor revision')
                    change.update(proposed)
                    bundle_checks.append(recheck)
                require(change and all(blob != previous['files'][name] for name, blob in change.items()),
                        'Staging must change each declared archive')
                members, snapshot, validation, _ = self._move(previous, {**previous['files'], **change}, run,
                                                               event_folder(session, revision) / 'project')
            except (AttributeError, IndexError, KeyError, OverflowError, TypeError, ValueError) as exc:
                raise APIError('NATIVE_EDITOR_INVALID', 'Native editor batch failed readback', str(exc)[:500]) from exc
            next_history, selected = [*history[:cursor + 1], revision], cursor + 1
            snapshots = {**snapshots, revision: snapshot}
        else:
            next_history = history
            selected = cursor + (-1 if args.action == 'undo' else 1)
            require(0 <= selected < len(history), f'No revision is available for {args.action}',
                    code='NATIVE_EDITOR_HISTORY_BOUNDARY')
        chosen = None if snapshot is not None else self._actual_project(snapshots[next_history[selected]])
        event = self._event(session, revision, args.action, digest, args.label, snapshot, changed=sorted(change))
        event_bytes = encode(event)
        target = event_folder(session, revision)

        def recheck():
            if target.exists():
                parent = event_folder(session, args.expected_revision) / 'event.json'
                require(sha(self.secure_bytes(parent)) == args.expected_event_sha256
                        and self.secure_bytes(target / 'event.json') == event_bytes,
                        'Another editor event won the reviewed revision', code='NATIVE_EDITOR_REVISION_CONFLICT')
            else:
                self._expected(session, args)
            self.recheck(previous)
            if chosen is not None:
                self.recheck(chosen)
            for check in bundle_checks:
                check()

        recheck()
        loaded = event, sha(event_bytes), source, snapshots, next_history, selected
        result = {**self._view(session, loaded), 'preview_only': args.preview_only, 'saved': False,
                  'changed_members': sorted(change), 'validation': validation}
        if args.preview_only:
            return result
        receipt = self._publish_event(target, event, recheck, members)
        return {**result, 'saved': True, 'publication': receipt}

    def publish(self, args):
        return self._session_action(args, self._publish)

    def _publish(self, args, session):
        tip, _, original, snapshots, history, cursor = self._expected(session, args)
        revision = args.snapshot_revision if args.snapshot_revision is not None else history[cursor]
        require(revision in snapshots, 'Select a saved editor snapshot revision')
        source = self._actual_project(snapshots[revision])
        target = project_target(self, args)
        require(target is not None and external(target, session)
                and external(target, self.path(original.project_directory)),
                'Select a fresh publication target separate from the session and source project')
        try:
            members, inventory, validation, relocation = self._move(source, source['files'], snapshots[revision].run_file, target)
        except (IndexError, KeyError, OverflowError, TypeError, ValueError) as exc:
            raise APIError('NATIVE_EDITOR_INVALID', 'Selected editor snapshot failed publication preflight', str(exc)[:500]) from exc

        def recheck():
            self._expected(session, args)
            self.recheck(source)

        recheck()
        result = {'preview_only': args.preview_only, 'saved': False, 'source_editor_revision': tip['revision'],
                  'snapshot_revision': revision, 'candidate_project': inventory.model_dump(), 'validation': validation,
                  'relocation': relocation, 'original_application_started': False}
        if args.preview_only:
            return result
        return publish_candidate(self, target, members, result, recheck)


def tool_definitions(root):
    service = NativeEditorTools(root)
    return [
        ('opentrack_start_native_editor', 'Preview or save an isolated native project editing session with immutable revisions.',
         StartNativeEditor, service.start, False, False),
        ('opentrack_read_native_editor', 'Read the current native editor revision, snapshot inventory and available history.',
         EditorLocation, service.read, True, False),
        ('opentrack_edit_native_editor', 'Stage reviewed native movement and operating bundles together, or undo or redo a revision.',
         EditNativeEditor, service.edit, False, False),
        ('opentrack_publish_native_editor', 'Publish a selected immutable native editor snapshot to a fresh project.',
         PublishNativeEditor, service.publish, False, False),
    ]
