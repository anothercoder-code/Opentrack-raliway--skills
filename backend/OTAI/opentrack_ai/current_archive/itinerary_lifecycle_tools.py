"""Lifecycle edits for native Itinerary definitions and their bound catalogs."""
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr, model_validator

from ..errors import APIError
from . import catalogs, path_functions as paths, route_factory, writer
from .bundle_tools import CourseBundles, Source
from .finite_itinerary_workflow import MAX_PATH_REFERENCES
from .graph_references import incoming_counts
from .itinerary_edit_tools import (
    Description, EditableItineraryProject, SafetyMarginRow, _float32, _margin_members, _margin_values,
    _ordered_paths, _project, _run_rows, _station_references, bound_dest_catalog, run_infrastructure_paths,
)
from .multi_document.generate import inf
from .multi_document_tools import Ref
from .next_tools import NextFunctions
from .operation_tools import Name
from .tools import Input, PathText, sha
from .zero_generation import native_signal_routes as native


NewName = Annotated[StrictStr, Field(pattern=r'^[!-~](?:[ -~]{0,198}[!-~])?$')]


class Rename(Input):
    action: Literal['rename']
    name: Name
    new_name: NewName


class Duplicate(Input):
    action: Literal['duplicate']
    name: Name
    new_name: NewName


class Delete(Input):
    action: Literal['delete']
    name: Name
    replacement_itinerary: Name | None = None


class RebuildCatalog(Input):
    action: Literal['rebuild_dest_catalog']


class Reconfigure(Input):
    action: Literal['reconfigure']
    name: Name
    paths: Annotated[list[Ref], Field(min_length=1, max_length=MAX_PATH_REFERENCES)]
    description: Description | None = None
    safety_margins: Annotated[list[SafetyMarginRow], Field(max_length=10000)] | None = None


class ItineraryLifecycle(Input):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    catalog: Source
    courses: Source
    operation: Annotated[Rename | Duplicate | Delete | RebuildCatalog | Reconfigure, Field(discriminator='action')]
    preview_only: StrictBool = True
    target_directory: PathText | None = None

    @model_validator(mode='after')
    def require_output(self):
        if not self.preview_only and self.target_directory is None:
            raise ValueError('Saving requires a fresh target_directory')
        return self


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _definitions(project):
    definitions = {paths.string(dest.contents[1].value): dest for dest in project.dests}
    _need(len(definitions) == len(project.dests) and all(definitions), 'Itinerary names must be unique and nonempty')
    return definitions


def _course_bindings(root):
    result = {}
    for course in catalogs.course_items(root):
        names = course.contents[2].value
        result[catalogs.text(course.contents[0].value)] = (
            course, names, catalogs.array(names) if names is not None else [],
        )
    return result


def _check_course_references(course_rows, names):
    for course_id, (_, _, values) in course_rows.items():
        absent = {catalogs.text(value) for value in values} - names
        _need(not absent, f'Course {course_id} references missing Itinerary names: {sorted(absent)}')


def _rewrite_courses(root, version, rows, old, new):
    changes = []
    undo = []
    before = {course_id: [catalogs.text(value) for value in values] for course_id, (_, _, values) in rows.items()}
    expected = dict(before)
    counts = incoming_counts(root)
    baseline = writer.fingerprint(root)
    for course_id, (course, array, values) in rows.items():
        indexes = [index for index, value in enumerate(before[course_id]) if value == old]
        if not indexes:
            continue
        _need(counts[id(course)] == 1, f'Course {course_id} definition is aliased')
        rewritten = [paths.fresh_string(value, new) if index in indexes else value for index, value in enumerate(values)]
        replacement = paths.clone(array)
        writer.set_elements(replacement, rewritten)
        undo.append((course, array))
        course.contents[2].value = replacement
        changes.append({'course_id': course_id, 'indexes': indexes})
        expected[course_id] = [new if value == old else value for value in before[course_id]]
    if not changes:
        return None, changes
    output = writer.dump_verified(root, version)
    for course, array in undo:
        course.contents[2].value = array
    _need(writer.fingerprint(root) == baseline, 'Unexpected mutation outside the selected Course Itinerary arrays')
    fresh, _ = writer.load_next_compatible(output)
    _need({course_id: [catalogs.text(value) for value in values]
           for course_id, (_, _, values) in _course_bindings(fresh).items()} == expected,
          'Saved Course bindings differ from the requested ordered replacements')
    return output, changes


def _owner_array(root, dest=None):
    wrapper = route_factory.layout(root.contents[5].value, 'OTMutableArray', 0, ['@'])
    array = wrapper.contents[0].value
    items = paths.mutable_array(array)
    counts = incoming_counts(root)
    _need(counts[id(wrapper)] == counts[id(array)] == 1, 'Itinerary list is aliased')
    if dest is not None:
        _need(items.count(dest) == counts[id(dest)] == 1, 'Itinerary has unexpected owners')
    return array, items


def _catalog_array(root):
    rows = route_factory.wrapper(root, 'OTDestInfoList')
    array = root.contents[0].value
    counts = incoming_counts(root)
    _need(counts[id(root)] == 0 and counts[id(array)] == 1, 'Destination catalog list is aliased')
    return array, rows, counts


def _catalog_row(name, native_path, references):
    rows = [native.obj([('OTArrayExtInfo', 0), ('OTArrayInfo', 0), ('NSObject', 0)], [
        ('@', [native.string(item['name'])]), ('ii', [item['array_id'], item['start_id']]),
        ('@', [native.string(item['document'])])]) for item in references]
    return native.obj([('OTDestInfo', 1), ('NSObject', 0)], [('i', [17]), ('@', [native.string(name)]),
        ('@', [native.string(native_path)]), ('i', [references[0]['start_id']]), ('@', [native.arr(rows)])])


def _copy_margins(dest, rows=None):
    wrapper, array, members = _margin_members(dest)
    if rows is None:
        points = [paths.clone(member) for member in members]
    else:
        values = [(_float32(row['position_m']), _float32(row['safety_margin_m'])) for row in rows]
        _need(all(first[0] <= second[0] for first, second in zip(values, values[1:])),
              'Safety-margin positions must be in nondecreasing order')
        points = [native.obj([('OTSafetyMargin', 0), ('NSObject', 0)], [('ff', list(value))]) for value in values]
    target_array = paths.clone(array)
    writer.set_elements(target_array, points)
    replacement = paths.clone(wrapper)
    replacement.contents[0].value = target_array
    return replacement


def _snapshot(project, dest):
    return {
        'owner': project.owners[id(dest)][0],
        'definition': paths.info(dest),
        'movement': project.dest_view(dest)[0],
        'safety_margins': _margin_values(_margin_members(dest)[2]),
    }


def edit_lifecycle(documents, native_paths, catalog, course_blob, operation):
    action = operation['action']
    if action == 'rebuild_dest_catalog':
        project = EditableItineraryProject(documents, document_paths=native_paths,
            expected_hashes={name: sha(blob) for name, blob in documents.items()}, complete_document_set=True)
    else:
        project = _project(documents, native_paths, catalog)
    definitions = _definitions(project)
    expected = {name: _snapshot(project, dest) for name, dest in definitions.items()}
    course_root, course_version = writer.load_next_compatible(course_blob)
    courses = _course_bindings(course_root)
    _check_course_references(courses, set(definitions))
    cat_root, cat_version = writer.load_next_compatible(catalog)
    cat_array, cat_rows, cat_counts = _catalog_array(cat_root)
    output_docs = dict(documents)
    output_courses, replacements = None, []
    report = {'operation': action}
    if action == 'rebuild_dest_catalog':
        entries = [_catalog_row(name, native_paths[row['owner']], row['definition']['saved_references'])
                   for name, row in sorted(expected.items())]
        writer.set_elements(cat_array, entries)
        report.update(prior_entry_count=len(cat_rows), new_entry_count=len(entries))
    else:
        name = operation['name']
        _need(name in definitions, 'Select an exact saved Itinerary name')
        dest = definitions[name]
        owner, _ = project.owners[id(dest)]
        source = project.roots[owner]
        doc_array, doc_rows = _owner_array(source, dest)
        row, = [item for item in cat_rows if paths.string(item.contents[1].value) == name]
        _need(cat_counts[id(row)] == 1, 'Destination catalog row has an unexpected owner')
        bound = [course_id for course_id, (_, _, values) in courses.items()
                 if any(catalogs.text(value) == name for value in values)]
        report.update(name=name, owner_document=owner, before=expected[name]['definition'], bound_courses=bound)
        changed_docs = {owner}
        if action == 'rename' or action == 'duplicate':
            new = operation['new_name']
            _need(new and new not in definitions, 'Use a new exact Itinerary name')
            if action == 'rename':
                dest.contents[1].value = paths.fresh_string(dest.contents[1].value, new)
                row.contents[1].value = paths.fresh_string(row.contents[1].value, new)
                output_courses, replacements = _rewrite_courses(course_root, course_version, courses, name, new)
                expected[new] = expected.pop(name)
            else:
                fresh = paths.clone(dest)
                fresh.contents[1].value = paths.fresh_string(dest.contents[1].value, new)
                fresh.contents[2].values = [-1, -1]
                fresh.contents[3].value = paths.fresh_string(dest.contents[3].value, '')
                fresh.contents[0].value = paths.array_like(dest.contents[0].value, paths.mutable_array(dest.contents[0].value))
                fresh.contents[4].value = paths.array_like(dest.contents[4].value,
                    [paths.clone(item) for item in paths.mutable_array(dest.contents[4].value)])
                fresh.contents[5].value = _copy_margins(dest)
                writer.set_elements(doc_array, [*doc_rows, fresh])
                writer.set_elements(cat_array, [*cat_rows, _catalog_row(new, native_paths[owner], paths.info(fresh)['saved_references'])])
                expected[new] = {**expected[name], 'definition': {
                    **expected[name]['definition'], 'description': '', 'array_id': -1, 'start_id': -1,
                }}
            expected[new]['definition'] = {**expected[new]['definition'], 'name': new}
            report['new_name'] = new
        elif action == 'delete':
            replacement = operation.get('replacement_itinerary')
            if replacement is not None:
                _need(replacement != name and replacement in definitions, 'Choose a different existing replacement Itinerary')
                other = definitions[replacement]
                _need(project.dest_view(other)[0] == project.dest_view(dest)[0],
                      'Replacement Itinerary must use the same directional movement')
                _need(paths.info(other)['saved_references'] == paths.info(dest)['saved_references'] and
                      [item.contents[0].values for item in _margin_members(other)[2]] ==
                      [item.contents[0].values for item in _margin_members(dest)[2]],
                      'Replacement Itinerary must preserve the path choices and safety margins')
                for course_id in bound:
                    _need(not any(catalogs.text(value) == replacement for value in courses[course_id][2]),
                          f'Course {course_id} already references the replacement Itinerary')
                output_courses, replacements = _rewrite_courses(course_root, course_version, courses, name, replacement)
            else:
                _need(not bound, f'Itinerary is referenced by Courses {bound}; supply an equivalent replacement')
            writer.set_elements(doc_array, [item for item in doc_rows if item is not dest])
            writer.set_elements(cat_array, [item for item in cat_rows if item is not row])
            del expected[name]
            report['replacement_itinerary'] = replacement
        elif action == 'reconfigure':
            references = operation['paths']
            _need(bool(references), 'Supply a nonempty ordered Path sequence')
            first = references[0]
            start = (first['document'], first['start_id'])
            selected, movement = _ordered_paths(project, references, start)
            original, _ = project.dest_view(dest)
            if bound:
                _need(start == original[0] and movement[-1] == original[-1] and
                      _station_references(project, movement) == _station_references(project, original),
                      'Changing endpoints or station order requires an unused Itinerary')
            margins = operation.get('safety_margins')
            _need(margins is not None or movement == original or not _margin_members(dest)[2],
                  'Replace or explicitly clear existing distance-based safety margins when changing the movement')
            moved = paths.clone(dest)
            moved.contents[0].value = paths.array_like(dest.contents[0].value, [selected[0][1]])
            moved.contents[4].value = paths.array_like(dest.contents[4].value, [inf(path, doc) for doc, path in selected])
            new_owner = start[0]
            if margins is not None or new_owner != owner:
                moved.contents[5].value = _copy_margins(dest, margins)
            if operation.get('description') is not None:
                moved.contents[3].value = paths.fresh_string(dest.contents[3].value, operation['description'])
            if owner == new_owner:
                writer.set_elements(doc_array, [moved if item is dest else item for item in doc_rows])
            else:
                other_array, other_rows = _owner_array(project.roots[new_owner])
                writer.set_elements(doc_array, [item for item in doc_rows if item is not dest])
                writer.set_elements(other_array, [*other_rows, moved])
                changed_docs.add(new_owner)
            new_row = _catalog_row(name, native_paths[new_owner], references)
            writer.set_elements(cat_array, [new_row if item is row else item for item in cat_rows])
            expected[name] = {'owner': new_owner, 'definition': paths.info(moved), 'movement': movement,
                              'safety_margins': _margin_values(_margin_members(moved)[2])}
            report.update(new_owner_document=new_owner, before_end_keys=original, after_end_keys=movement,
                          running_time_revalidation_required=movement != original or references != report['before']['saved_references'])
        else:
            raise ValueError('Unsupported Itinerary lifecycle action')
        for doc in changed_docs:
            output_docs[doc] = writer.dump_verified(project.roots[doc], project.versions[doc])
    output_catalog = writer.dump_verified(cat_root, cat_version)
    checked = _project(output_docs, native_paths, output_catalog)
    saved = _definitions(checked)
    _need({name: _snapshot(checked, dest) for name, dest in saved.items()} == expected,
          'Itinerary definitions changed unexpectedly on archive reload')
    _check_course_references(_course_bindings(writer.load_next_compatible(output_courses or course_blob)[0]), set(expected))
    if action in ('rename', 'duplicate', 'reconfigure'):
        report['after'] = expected[operation.get('new_name', operation['name'])]['definition']
    if action == 'reconfigure':
        report['after_safety_margins'] = expected[operation['name']]['safety_margins']
    return output_docs, output_catalog, output_courses, {
        **report, 'course_reference_replacements': replacements, 'catalog_bindings_verified': True,
        'native_runtime_verified': False,
    }


class ItineraryLifecycleTools(NextFunctions, CourseBundles):
    def edit(self, args):
        inputs = {name: self.checked(source) for name, source in args.documents.items()}
        catalog_path, catalog, _, _ = self.checked(args.catalog)
        course_path, course_blob, _, _ = self.checked(args.courses)
        run, run_blob, check_scope, scope = self.checked_document_list(args, inputs)
        bound_dest_catalog(self, run, run_blob, catalog_path)
        self.same_project([run, course_path])
        entries = [fields for fields in _run_rows(run_blob) if fields[0] == 'CourseFile']
        if len(entries) != 1 or len(entries[0]) != 3 or entries[0][2]:
            raise APIError('ITINERARY_DOCUMENT_SCOPE', 'Run requires one explicit CourseFile binding')
        raw = entries[0][1]
        if not raw or any(char in raw for char in ('%', '$', '\\')):
            raise APIError('ITINERARY_DOCUMENT_SCOPE', 'Expected an explicit portable .courses path in the run file')
        specified = Path(raw)
        specified = specified if specified.is_absolute() else run.parent / specified
        if '..' in specified.parts or specified != course_path or course_path.suffix != '.courses':
            raise APIError('ITINERARY_DOCUMENT_SCOPE', 'Supplied .courses must match the run CourseFile inside the project')
        if args.target_directory is not None and self.path(args.target_directory).is_relative_to(run.parent):
            raise APIError('ITINERARY_DOCUMENT_SCOPE', 'Publish the fresh bundle outside the selected project')
        documents = {name: item[1] for name, item in inputs.items()}
        try:
            docs, dest, courses, report = edit_lifecycle(documents, run_infrastructure_paths(run_blob), catalog,
                course_blob, args.operation.model_dump(exclude_none=True))
        except (ValueError, KeyError, TypeError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_ITINERARY_LIFECYCLE', str(exc)[:500]) from exc
        outputs = {inputs[name][0]: blob for name, blob in docs.items() if blob != documents[name]}
        outputs[catalog_path] = dest
        if courses is not None:
            outputs[course_path] = courses
        if len({file.name.casefold() for file in outputs}) != len(outputs):
            raise APIError('ITINERARY_DOCUMENT_SCOPE', 'Bundle output names must be distinct')
        dependencies = {run: run_blob, catalog_path: catalog, course_path: course_blob,
                        **{entry[0]: entry[1] for entry in inputs.values()}}
        manifest = {'format': 'opentrack-itinerary-lifecycle-v1',
                    'files': {file.name: {'sha256': sha(blob), 'bytes': len(blob)} for file, blob in outputs.items()},
                    'sources': {file.relative_to(self.root).as_posix(): {'sha256': sha(blob)} for file, blob in dependencies.items()},
                    'replacement_for': {file.name: file.relative_to(self.root).as_posix() for file in outputs},
                    'document_scope': scope, 'complete_relocated_project': False}
        result = {'preview_only': args.preview_only, 'saved': False, 'manifest': manifest,
                  'bundle_type': 'Itinerary lifecycle archive bundle', 'change_report': report,
                  'fresh_archive_reload_verified': True, 'native_application_started': False}
        return self.publish_bundle(inputs=dependencies, members={file.name: blob for file, blob in outputs.items()},
            manifest=manifest, result=result, target_directory=args.target_directory, scope_check=check_scope,
            windows_publication=True)


def tool_definitions(root):
    return [('opentrack_edit_current_itinerary_lifecycle',
             'Rename, duplicate, delete, reconfigure or rebuild the DestInfo catalog for the exact selected native '
             'project. Rename updates ordered Course references. Delete refuses existing bindings unless supplied '
             'an equivalent replacement. Endpoint/station changes require an unused Itinerary and explicit review '
             'of distance margins. Preview or publish the changed archives in a fresh verified bundle.',
             ItineraryLifecycle, ItineraryLifecycleTools(root).edit, False, False)]
