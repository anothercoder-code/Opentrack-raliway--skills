"""Edit local Shunting objects referenced by native Itineraries and Overlaps."""

from typing import Annotated

from pydantic import Field, StrictBool, model_validator

from ..errors import APIError
from . import path_functions as path, route_factory, writer
from .bundle_tools import CourseBundles, Source
from .current_shunting_tools import Description, EndSequence, NewShuntingName
from .graph_references import incoming_counts
from .itinerary_edit_tools import bound_dest_catalog, run_infrastructure_paths
from .movement_edits import _linked_itineraries, _movement_project, _path_references, verify_itinerary_movements
from .multi_document.core import ref
from .multi_document.operations import exclusive
from .next_tools import NextFunctions
from .operation_tools import Name, RouteSelector
from .tools import Input, PathText, sha


class ShuntingSelection(Input):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    target_document: Name
    dest_catalog: Source
    shunting: RouteSelector
    preview_only: StrictBool = True
    target_directory: PathText | None = None

    @model_validator(mode='after')
    def require_target(self):
        if not self.preview_only and self.target_directory is None:
            raise ValueError('Saving requires an explicit fresh target directory')
        return self


class RenameShunting(ShuntingSelection):
    new_name: NewShuntingName


class RerouteShunting(ShuntingSelection):
    end_ids: EndSequence
    description: Description | None = None


def _find(project, document, reference):
    owner_key = (document, reference['start_id'])
    owner = project.model(owner_key)
    found = project.itinerary_path(owner_key, (reference['name'], reference['array_id'], reference['start_id']))
    rows = route_factory.wrapper(owner.contents[16].value, 'OTShuntingList')
    route_factory.require(sum(item is found for item in rows) == 1, 'Reference must select an actual Shunting Path')
    return found


def _owned_body(project, target, reference, document):
    root = project.roots[document]
    exclusive(root, project.model((document, reference['start_id'])).contents[16].value)
    body, = path.mutable_array(target.contents[0].value)
    own_info, = path.mutable_array(target.contents[4].value)
    indications = route_factory.wrapper(body.contents[4].value, 'OTSigIndList')
    counts = incoming_counts(root)
    for indication in indications:
        route_factory.layout(indication, 'OTSigInd', 0, ['i', '@'])
        route_factory.require(indication.contents[1].value is body, 'Shunting indication owner mismatch')
    route_factory.require(counts[id(body)] == 1 + len(indications) and counts[id(own_info)] == 1
                          and counts[id(body.contents[0].value)] == 1 and counts[id(target.contents[4].value)] == 1,
                          'Shared Shunting body, End sequence or private Path reference')
    return root, body, own_info


def rename_shunting(documents, document_paths, dest_catalog, target_document, reference, new_name):
    require = route_factory.require
    require(new_name.strip() == new_name and new_name and new_name.isascii() and new_name.isprintable()
            and new_name.casefold() != reference['name'].casefold(), 'Use a distinct printable ASCII name')
    project = _movement_project(documents, document_paths, dest_catalog)
    selected = _find(project, target_document, reference)
    movement, _ = project.path_view(selected)
    dependents = _linked_itineraries(project, dest_catalog, target_document, selected, reference)
    catalog, catalog_version = writer.load_next_compatible(dest_catalog)
    _, body, own_info = _owned_body(project, selected, reference, target_document)
    for graph in [*project.roots.values(), catalog]:
        for obj in writer.objects(graph):
            kind = writer.kind(obj)
            if kind in ('OTRoute', 'OTPath', 'OTShunting'):
                require(path.string(obj.contents[1].value).casefold() != new_name.casefold(), 'Movement name already exists')
                if kind != 'OTPath':
                    require(path.string(obj.contents[7].value).casefold() != new_name.casefold(),
                            'New name would capture an existing Overlap')
            if kind in ('OTArrayInfo', 'OTArrayExtInfo'):
                require(path.string(obj.contents[0].value).casefold() != new_name.casefold(),
                        'New name would capture a saved movement reference')

    edits = {target_document: [(selected, 1), (body, 1), (own_info, 0)]}
    overlaps = []
    for route in project.routes:
        if path.string(route.contents[7].value) != reference['name']:
            continue
        last = project.route_view(route)[-1]
        start_id = route.contents[9].value
        resolved = last if start_id < 0 else (last[0], start_id)
        if resolved != (target_document, reference['start_id']):
            continue
        document, _ = project.owners[id(route)]
        edits.setdefault(document, []).append((route, 7))
        overlaps.append({'document': document, **ref(route)})
    for document, graph in project.roots.items():
        for info in _path_references(graph, project.roots, target_document, reference):
            edits.setdefault(document, []).append((info, 0))
    catalog_edits = [(info, 0) for info in _path_references(catalog, project.roots, target_document, reference)]

    def edited_bytes(graph, version, operations):
        original = writer.fingerprint(graph)
        # Preserve aliases between edited NSString references and never mutate
        # strings shared with a field which is outside this operation.
        strings = {}
        snapshots = []
        for obj, index in operations:
            group = obj.contents[index]
            old = group.value
            if id(old) not in strings:
                strings[id(old)] = path.fresh_string(old, new_name)
            snapshots.append((group, old))
            group.value = strings[id(old)]
        result = writer.dump_verified(graph, version)
        for group, old in snapshots:
            group.value = old
        require(writer.fingerprint(graph) == original, 'Unexpected Shunting rename graph change')
        return result

    outputs = {doc: edited_bytes(project.roots[doc], project.versions[doc], operations)
               for doc, operations in edits.items()}
    new_catalog = edited_bytes(catalog, catalog_version, catalog_edits) if catalog_edits else dest_catalog
    checked = _movement_project({**documents, **outputs}, document_paths, new_catalog)
    renamed_ref = {**reference, 'name': new_name}
    renamed = _find(checked, target_document, renamed_ref)
    require(checked.path_view(renamed)[0] == movement and
            _linked_itineraries(checked, new_catalog, target_document, renamed, renamed_ref) == dependents,
            'Shunting movement or dependent Itineraries differ after readback')
    reloaded_catalog, _ = writer.load_next_compatible(new_catalog)
    require(not any(path.string(info.contents[0].value) == reference['name']
                    for graph in (*checked.roots.values(), reloaded_catalog)
                    for info in _path_references(graph, checked.roots, target_document, reference)),
            'A stale Shunting Path name remains')
    return outputs, new_catalog, {'operation': 'rename_native_shunting', 'before': reference, 'after': renamed_ref,
        'dependent_itineraries': sorted(dependents), 'bound_route_overlaps': overlaps,
        'native_runtime_verified': False}


def reroute_shunting(documents, document_paths, dest_catalog, target_document, reference, end_ids, description):
    require = route_factory.require
    original = _movement_project(documents, document_paths, dest_catalog)
    # A separate graph retains the original station identities and safety data for comparison.
    edited = _movement_project(documents, document_paths, dest_catalog)
    old_path = _find(original, target_document, reference)
    selected = _find(edited, target_document, reference)
    dependents = _linked_itineraries(edited, dest_catalog, target_document, selected, reference)
    root, body, _ = _owned_body(edited, selected, reference, target_document)
    before, _ = original.path_view(old_path)
    planned = [(target_document, end_id) for end_id in end_ids]
    require(len(set(planned)) == len(planned), 'Shunting movement cannot repeat a directional End')
    nodes = [edited.model(key) for key in planned]
    require(all(writer.kind(node) == 'OTEndModel' for node in nodes), 'Shunting movement uses ordinary local Ends')
    edges = [edited.edge_between(first, second) for first, second in zip(planned, planned[1:])]
    require(planned[0] == before[0] and planned[-1] == before[-1], 'Preserve the two directional Shunting endpoints')
    body.contents[0].value = path.array_like(body.contents[0].value, nodes)
    if description is not None:
        old_body_text, old_path_text = body.contents[3].value, selected.contents[3].value
        selected.contents[3].value = path.fresh_string(old_path_text, description)
        body.contents[3].value = (selected.contents[3].value if old_body_text is old_path_text
                                  else path.fresh_string(old_body_text, description))
    output = writer.dump_verified(root, edited.versions[target_document])
    checked = _movement_project({**documents, target_document: output}, document_paths, dest_catalog)
    saved = _find(checked, target_document, reference)
    require(checked.path_view(saved)[0] == planned, 'Changed Shunting movement differs after archive reload')
    if description is not None:
        saved_body, = path.mutable_array(saved.contents[0].value)
        require(path.string(saved.contents[3].value) == path.string(saved_body.contents[3].value) == description,
                'Changed Shunting description differs after archive reload')
    changed = verify_itinerary_movements(original, checked)
    return {target_document: output}, dest_catalog, {'operation': 'reroute_native_linked_shunting',
        'shunting': reference, 'dependent_itineraries': sorted(dependents), 'changed_itineraries': changed,
        'previous_end_ids': [key[1] for key in before], 'end_ids': end_ids,
        'edge_ids': [key[1] for key in edges], 'native_runtime_verified': False}


class ShuntingLifecycle(NextFunctions, CourseBundles):
    def rename(self, args):
        return self._edit(args, rename_shunting, args.new_name)

    def reroute(self, args):
        return self._edit(args, reroute_shunting, args.end_ids, args.description)

    def _edit(self, args, edit, *details):
        inputs = {key: self.checked(value) for key, value in args.documents.items()}
        catalog_path, catalog, _, _ = self.checked(args.dest_catalog)
        source_paths = {row[0] for row in inputs.values()}
        if args.target_document not in inputs or len(source_paths | {catalog_path}) != len(inputs) + 1:
            raise APIError('DOCUMENT_SCOPE', 'Provide distinct run-bound documents and a destination catalog')
        runpath, run, scope_check, scope_evidence = self.checked_document_list(args, inputs)
        bound_dest_catalog(self, runpath, run, catalog_path)
        if args.target_directory is not None and self.path(args.target_directory).is_relative_to(runpath.parent):
            raise APIError('DOCUMENT_SCOPE', 'Use a fresh target outside the source project')
        try:
            outputs, catalog_output, report = edit({key: row[1] for key, row in inputs.items()},
                run_infrastructure_paths(run), catalog, args.target_document, args.shunting.model_dump(), *details)
        except (ValueError, TypeError, IndexError, KeyError, OverflowError) as error:
            raise APIError('CURRENT_SHUNTING_LINKED_EDIT', str(error)[:500]) from error
        members = {inputs[key][0].name: output for key, output in outputs.items()}
        replacements = {inputs[key][0].name: inputs[key][0].relative_to(self.root).as_posix() for key in outputs}
        if catalog_output != catalog:
            members[catalog_path.name] = catalog_output
            replacements[catalog_path.name] = catalog_path.relative_to(self.root).as_posix()
        dependencies = {runpath: run, catalog_path: catalog, **{row[0]: row[1] for row in inputs.values()}}
        manifest = {'format': 'opentrack-shunting-linked-edits-v1', 'replacement_for': replacements,
            'files': {key: {'sha256': sha(blob), 'bytes': len(blob)} for key, blob in members.items()},
            'sources': {file.relative_to(self.root).as_posix(): sha(blob) for file, blob in dependencies.items()},
            'document_scope': scope_evidence, 'complete_relocated_project': False}
        result = {'preview_only': args.preview_only, 'saved': False, 'manifest': manifest,
            'change_report': report, 'fresh_archive_reload_verified': True, 'native_application_started': False}
        return self.publish_bundle(inputs=dependencies, members=members, manifest=manifest, result=result,
            target_directory=args.target_directory, scope_check=scope_check, windows_publication=True)


def tool_definitions(root):
    service = ShuntingLifecycle(root)
    return [('opentrack_rename_current_shunting',
             'Rename a local native Shunting and its automatic Path while preserving identities. Synchronize '
             'exact Itinerary, DestInfo, and Route Overlap references; preview or atomically save fresh archives.',
             RenameShunting, service.rename, False, False),
            ('opentrack_replace_current_linked_shunting_movement',
             'Reroute a local Shunting referenced by an Itinerary or Overlap while preserving directional endpoints, '
             'ordered stations and the validity of Overlap references. Itineraries with distance margins require '
             'review before changing their movement. Preview or atomically publish the native document.',
             RerouteShunting, service.reroute, False, False)]
