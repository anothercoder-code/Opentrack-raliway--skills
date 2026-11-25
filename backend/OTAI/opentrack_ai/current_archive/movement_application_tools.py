"""Prepare verified backups and replacements for a separately applied movement edit."""
import json
import re
from pathlib import Path

from ..errors import APIError
from . import catalogs, writer
from .bundle_tools import Source
from .itinerary_edit_tools import EditableItineraryProject
from .next_tools import NextFunctions
from .prepare_contract.auxiliary import records
from .project_candidate_publication import ProjectSave, project_target
from .tools import sha

FORMATS = frozenset({
    'opentrack-route-lifecycle-v1', 'opentrack-current-path-lifecycle-v1',
    'opentrack-itinerary-lifecycle-v1', 'opentrack-segmented-shunting-itinerary-v1',
    'opentrack-shunting-linked-edits-v1', 'opentrack-cross-document-route-edit-v1',
    'opentrack-current-itinerary-edit-increment-v1',
    'opentrack-saved-geometry-v1',
    'opentrack-route-fetch-v1',
    'opentrack-route-aspects-v1', 'opentrack-category-signal-v1',
})

DOCUMENT_ONLY_FORMATS = frozenset({
    'opentrack-route-fetch-v1', 'opentrack-route-aspects-v1', 'opentrack-category-signal-v1',
})


class PrepareMovementApplication(ProjectSave):
    project_run: Source
    bundle_manifest: Source


def unique_json_keys(rows):
    values = {}
    for key, value in rows:
        if key in values:
            raise ValueError('Duplicate manifest key')
        values[key] = value
    return values


class MovementApplicationTools(NextFunctions):
    def bound_run_path(self, project, value, suffix):
        if not value or any(char in value for char in '%$\\'):
            raise ValueError('Use explicit project paths in the run file')
        path = Path(value)
        if '..' in path.parts:
            raise ValueError('Run path traversal refused')
        if not path.is_absolute():
            path = project / path
        if not path.is_relative_to(project) or path.suffix != suffix:
            raise ValueError('Run binding must have the expected extension inside the selected project')
        return self.path(path.relative_to(self.root).as_posix())

    def review(self, args):
        run = self.path(args.project_run.path)
        bundle_manifest = self.path(args.bundle_manifest.path)
        project = self.root.joinpath(*self.project_scope(run))
        if run.suffix != '.run' or run.parent != project or bundle_manifest.name != 'bundle-manifest.json':
            raise APIError('MOVEMENT_APPLICATION_SCOPE', 'A selected project run and bundle-manifest.json are required')
        bundle = bundle_manifest.parent
        target = project_target(self, args)
        if target is not None and any(target.is_relative_to(p) or p.is_relative_to(target) for p in (project, bundle)):
            raise APIError('MOVEMENT_APPLICATION_SCOPE', 'Backup target must be outside the project and source bundle')
        run_bytes, manifest_bytes = self.secure_bytes(run), self.secure_bytes(bundle_manifest)
        if sha(run_bytes) != args.project_run.sha256 or sha(manifest_bytes) != args.bundle_manifest.sha256:
            raise APIError('SOURCE_CHANGED', 'Run or movement bundle manifest differs from the selected SHA')
        try:
            plan = json.loads(manifest_bytes, object_pairs_hook=unique_json_keys)
            if not isinstance(plan, dict) or plan.get('format') not in FORMATS:
                raise ValueError('Unsupported movement bundle format')
            if plan.get('complete_relocated_project') is not False:
                raise ValueError('Only incremental movement bundles are supported')
            files, replacements, sources = (plan[key] for key in ('files', 'replacement_for', 'sources'))
            if (not all(isinstance(x, dict) for x in (files, replacements, sources))
                    or not 1 <= len(files) <= 63 or files.keys() != replacements.keys()):
                raise ValueError('Bundle members and replacements must have identical bounded keys')
            entries = {}
            for key, value, _ in records(run_bytes):
                entries.setdefault(key, []).append(value)
            docs = [self.bound_run_path(project, value, '.opentrack')
                    for value in entries['Infrastructure Document']]
            def one(key, suffix):
                (value,) = entries[key]
                return self.bound_run_path(project, value, suffix)
            dest, courses = one('DestInfoFile', '.dest'), one('CourseFile', '.courses')
            allowed = {*docs, dest, courses}
            category_train = one('TrainFile', '.trains') if plan['format'] == 'opentrack-category-signal-v1' else None
            allowed_sources = allowed | {run}
            if category_train is not None:
                allowed_sources.add(category_train)
            donors = {}
            if plan['format'] == 'opentrack-saved-geometry-v1':
                for role, suffix in (('StationFile', '.stations'), ('TrainFile', '.trains'),
                                     ('TimetableFile', '.timetable'), ('DepotFile', '.depot')):
                    if role in entries:
                        allowed_sources.add(one(role, suffix))
                for field in ('shape_source', 'drawing_donor_source', 'signal_donor_source'):
                    if field in plan:
                        source = Source.model_validate(plan[field])
                        path = self.path(source.path)
                        if path in donors and source.sha256 != donors[path]:
                            raise ValueError('Conflicting geometry donor bindings')
                        donors[path] = source.sha256
                allowed_sources.update(donors)
            if len(set(docs)) != len(docs) or len({doc.stem.casefold() for doc in docs}) != len(docs):
                raise ValueError('Duplicate document names or bindings')
            bindings = {}
            for name, details in sources.items():
                path = self.path(name)
                digest = details.get('sha256') if isinstance(details, dict) else details
                if (path not in allowed_sources or path in bindings or not isinstance(digest, str)
                        or not re.fullmatch(r'[0-9a-f]{64}', digest)):
                    raise ValueError('Invalid, duplicate or unbound manifest source')
                bindings[path] = digest
            if not {*docs, run, dest} <= bindings.keys() or bindings[run] != args.project_run.sha256:
                raise ValueError('Manifest must bind the selected run, every active document and DestInfo')
            if category_train is not None and category_train not in bindings:
                raise ValueError('A category signal bundle must bind the exact run TrainFile')
            if any(bindings.get(path) != digest for path, digest in donors.items()):
                raise ValueError('Each declared geometry donor must match its reviewed source fingerprint')
            inputs = {run: run_bytes, bundle_manifest: manifest_bytes}
            for path, digest in bindings.items():
                actual = inputs[path] if path in inputs else self.secure_bytes(path)
                if sha(actual) != digest:
                    raise APIError('SOURCE_CHANGED', 'Project dependency differs from bundle preimage',
                                   path.relative_to(self.root).as_posix())
                inputs[path] = actual
            if courses not in inputs:
                inputs[courses] = self.secure_bytes(courses)
            documents = {path.stem: (path, inputs[path], *writer.load_next_compatible(inputs[path]))
                         for path in docs}
            _, _, scope_check, _ = self.checked_document_list(args, documents)
            new = {}
            members = {}
            operations = []
            for name, raw_path in replacements.items():
                path = self.path(raw_path)
                if name != path.name or path not in allowed or path not in bindings or path in new:
                    raise ValueError('Replacement must match a distinct run-bound preimage and its exact filename')
                candidate = bundle / name
                if candidate in inputs or candidate in allowed:
                    raise ValueError('Candidate and project source must be distinct files')
                blob = self.secure_bytes(candidate)
                metadata = files[name]
                if (not isinstance(metadata, dict) or type(metadata.get('bytes')) is not int
                        or metadata['bytes'] != len(blob) or metadata.get('sha256') != sha(blob)):
                    raise APIError('SOURCE_CHANGED', 'Candidate member differs from the reviewed bundle', name)
                inputs[candidate] = new[path] = blob
                before, after = 'before/' + name, 'after/' + name
                members.update({before: inputs[path], after: blob})
                operations.append({'project_file': path.relative_to(self.root).as_posix(),
                                   'before': before, 'before_sha256': bindings[path],
                                   'after': after, 'after_sha256': sha(blob)})
            all_docs = {path.stem: new.get(path, inputs[path]) for path in docs}
            document_only = plan['format'] in DOCUMENT_ONLY_FORMATS
            if document_only and not set(new) <= set(docs):
                raise ValueError('This bundle can replace only run-bound infrastructure documents')
            view = EditableItineraryProject(all_docs, document_paths={path.stem: path.as_posix() for path in docs},
                                            expected_hashes={name: sha(blob) for name, blob in all_docs.items()},
                                            complete_document_set=True)
            view.check_dest_catalog(new.get(dest, inputs[dest]), allow_external=document_only)
            courses_root, _ = writer.load_next_compatible(new.get(courses, inputs[courses]))
            itinerary_names = {catalogs.text(row.contents[1].value) for row in view.dests}
            if any(catalogs.text(name) not in itinerary_names
                   for row in catalogs.course_items(courses_root)
                   for name in catalogs.array(row.contents[2].value)):
                raise ValueError('Candidate Course contains an unresolved Itinerary reference')
        except (IndexError, KeyError, OverflowError, TypeError, ValueError) as exc:
            raise APIError('MOVEMENT_APPLICATION_INVALID', 'Reviewed movement bundle or project bindings failed validation',
                           str(exc)[:500]) from exc

        def recheck():
            scope_check()
            for path, expected in inputs.items():
                if self.secure_bytes(path) != expected:
                    raise APIError('SOURCE_CHANGED', 'Project or candidate changed during preparation',
                                   path.relative_to(self.root).as_posix())

        recheck()
        result = {'schema': 'opentrack-movement-application-preparation/1',
                  'preview_only': args.preview_only, 'saved': False, 'project_changed': False,
                  'run': args.project_run.model_dump(), 'bundle': args.bundle_manifest.model_dump(),
                  'replacements': operations, 'atomic_project_update': False, 'native_reload_verified': False,
                  'project_source_sha256': {path.relative_to(self.root).as_posix(): sha(inputs[path])
                                            for path in (run, *docs, dest, courses)}}
        return result, members, new, recheck, target

    def prepare(self, args):
        result, members, _, recheck, target = self.review(args)
        if args.preview_only:
            return result
        from .windows_publish import publish_project

        members['application-plan.json'] = json.dumps({**result, 'saved': True}, indent=2, ensure_ascii=False).encode('utf8')

        def validate(actual):
            if actual != members:
                raise APIError('MOVEMENT_APPLICATION_INVALID', 'Backup and replacement readback differs')

        publication = publish_project(self.root, target, members, recheck=recheck, validate_bundle=validate,
                                      empty_directories=())
        return {**result, 'saved': True, 'publication': publication, 'target_directory': publication['target_directory']}


def tool_definitions(root):
    service = MovementApplicationTools(root)
    return [(
        'opentrack_prepare_reviewed_movement_application',
        'Review a movement bundle against the bound run and current project preimages. Preview or atomically save '
        'before/after archives and an application plan in a fresh Windows recovery directory. The original project is never modified.',
        PrepareMovementApplication, service.prepare, False, False,
    )]
