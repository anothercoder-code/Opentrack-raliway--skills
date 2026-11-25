"""Apply bounded edits to an existing native Itinerary and its catalog entry."""
import math
from pathlib import Path
import struct
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from ..errors import APIError
from . import path_functions as paths, route_factory, writer
from .bundle_tools import CourseBundles, Source
from .current_shunting_workflow import core as shunting_core
from .finite_itinerary_workflow import (
    MAX_EXPANDED_ENDS, MAX_PATH_REFERENCES, FiniteItineraryProject, create_finite_itinerary,
)
from .graph_references import incoming_counts
from .multi_document.core import ident, layout, need, ref
from .multi_document.generate import inf
from .multi_document.operations import exact_reference
from .multi_document_tools import Ref
from .next_tools import NextFunctions, Save
from .operation_tools import Name
from .tools import Input, PathText, sha
from .zero_generation.native_signal_routes import obj


Description = Annotated[StrictStr, Field(max_length=4096, pattern=r'^[ -~]*$')]


class EditDescription(Save):
    action: Literal['set_description']
    source: Source
    name: Name
    description: Description


MarginValue = Annotated[StrictFloat | StrictInt, Field(
    ge=-3.4028234663852886e38, le=3.4028234663852886e38, allow_inf_nan=False)]


class SafetyMarginRow(Input):
    position_m: MarginValue
    safety_margin_m: MarginValue


class EditSafetyMargins(Save):
    action: Literal['set_safety_margins']
    source: Source
    name: Name
    rows: Annotated[list[SafetyMarginRow], Field(max_length=10000)]


class ProjectItineraryEdit(Input):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    catalog: Source
    name: Name
    paths: Annotated[list[Ref], Field(min_length=1, max_length=MAX_PATH_REFERENCES)]
    description: Description | None = None
    preview_only: StrictBool = True
    target_directory: PathText | None = None

    @model_validator(mode='after')
    def explicit_target(self):
        if not self.preview_only and self.target_directory is None:
            raise ValueError('Saving requires an explicit fresh target_directory')
        if 'description' in self.model_fields_set and self.description is None:
            raise ValueError('Omit an unchanged description or provide a string')
        return self


class ReplacePaths(ProjectItineraryEdit):
    action: Literal['replace_paths']


class CreateItinerary(ProjectItineraryEdit):
    action: Literal['create_itinerary']


class EditItinerary(Input):
    edit: Annotated[EditDescription | EditSafetyMargins | ReplacePaths | CreateItinerary, Field(discriminator='action')]


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _runscope(err_message):
    return APIError('ITINERARY_DOCUMENT_SCOPE', err_message)


def bound_dest_catalog(service, runpath, runblob, catalog_path):
    entries = [fields for fields in _run_rows(runblob) if fields[0] == 'DestInfoFile']
    if len(entries) != 1 or len(entries[0]) != 3 or entries[0][2]:
        raise _runscope('Run requires exactly one DestInfoFile binding')
    raw = entries[0][1]
    relative = Path(raw)
    if (not raw or '%' in raw or '$' in raw or '\\' in raw
            or '..' in relative.parts or relative.suffix != '.dest'):
        raise _runscope('Expected an explicit portable .dest path in the run file')
    project = runpath.parent
    candidate = relative if relative.is_absolute() else project / relative
    if not candidate.is_relative_to(project):
        raise _runscope('Run DestInfoFile must be inside the selected project')
    actual = service.path(candidate.relative_to(service.root).as_posix())
    if actual != catalog_path:
        raise _runscope('Supplied catalog does not match the run DestInfoFile')


def run_infrastructure_paths(runblob):
    return {Path(fields[1]).stem: fields[1] for fields in _run_rows(runblob)
            if fields[0] == 'Infrastructure Document'}


def _run_rows(runblob):
    return [line.split('#') for line in runblob.decode('ascii').splitlines()]


def _definition(root, name):
    route_factory.document(root)
    result = paths.select(root, 'OTDest', name)
    wrapper = route_factory.layout(root.contents[5].value, 'OTMutableArray', 0, ['@'])
    definitions = paths.mutable_array(wrapper.contents[0].value)
    _require(definitions.count(result) == 1, 'Itinerary must appear once in the selected Document Itinerary list')
    return result


class EditableItineraryProject(FiniteItineraryProject):
    """Validate mixed train/overlap documents while retaining ordinary Path lookup."""

    def __init__(self, documents, *, document_paths, expected_hashes, complete_document_set):
        self.shunting_movements = {}
        self._shunting_paths = {}
        self._shunting_bodies = set()
        super().__init__(documents, document_paths=document_paths, expected_hashes=expected_hashes,
                         complete_document_set=complete_document_set)

    def _owned_shuntings(self, end):
        items = route_factory.wrapper(end.contents[16].value, 'OTShuntingList')
        owner = self.key(end)
        dn, _ = owner
        for item in items:
            paths.shape(item, 'OTPath')
            name = paths.string(item.contents[1].value)
            need(name and (owner, name) not in self.shunting_movements, 'Empty/ambiguous Shunting name at its End')
            bodies = paths.mutable_array(item.contents[0].value)
            need(len(bodies) == 1 and writer.kind(bodies[0]) == 'OTShunting',
                 'Expected one known Shunting body in the automatic Path')
            body = bodies[0]
            need(id(body) not in self._shunting_bodies, 'Shared Shunting body in multiple automatic Paths')
            self._shunting_bodies.add(id(body))
            version = body.clazz.superclass.version
            need(version in (5, 6), 'Unknown Shunting security layout')
            chain = [('OTShunting', 0), ('OTSecurityArray', version), *shunting_core.CHAIN[2:]]
            groups = shunting_core.ENC if version == 6 else shunting_core.ENC[:10] + ['f']
            layout(body, chain, groups)
            refs = paths.mutable_array(item.contents[4].value)
            need(len(refs) == 1, 'Expected one saved Shunting body reference')
            route_factory.layout(refs[0], 'OTArrayInfo', 0, ['@', 'ii'])
            need(shunting_core.identity(body)['name'] == name and paths.string(refs[0].contents[0].value) == name
                 and refs[0].contents[1].values == body.contents[2].values, 'Shunting body lookup mismatch')
            need(body.contents[5].values[4] == -1, 'Cross-document Shunting outside this edit profile')
            need(paths.string(body.contents[7].value) == '' and body.contents[9].value == -1,
                 'Recursive Shunting/Overlap outside this edit profile')
            nodes = paths.mutable_array(body.contents[0].value)
            need(len(nodes) >= 2 and nodes[0] is end and all(writer.kind(node) == 'OTEndModel' for node in nodes),
                 'Shunting start or directional End layout mismatch')
            keys = tuple(self.key(node) for node in nodes)
            need(all(key[0] == dn for key in keys) and len(set(keys)) == len(keys),
                 'Shunting must use nonrepeated Ends in its own document')
            for first, second in zip(keys, keys[1:]):
                self.edge_between(first, second)
            self.shunting_movements[owner, name] = keys
            self._shunting_paths[id(item)] = (owner, name)
        return items

    def itinerary_path(self, key, reference):
        end = self.model(key)
        ordinary = route_factory.wrapper(end.contents[17].value, 'OTPathList')
        shunting = route_factory.wrapper(end.contents[16].value, 'OTShuntingList')
        if any(ident(item)[0] == reference[0] or ident(item)[1:] == reference[1:] for item in ordinary):
            return super().itinerary_path(key, reference)
        matches = [item for item in shunting if ident(item) == reference]
        need(len(matches) == 1
             and sum(ident(item)[0] == reference[0] for item in shunting) == 1
             and sum(ident(item)[1:] == reference[1:] for item in shunting) == 1,
             'Unresolved exact OTPath or automatic Shunting Path reference')
        return matches[0]

    def path_view(self, path):
        marker = self._shunting_paths.get(id(path))
        if marker is None:
            return super().path_view(path)
        return list(self.shunting_movements[marker]), [(marker[0][0], {'kind': 'shunting', **ref(path)})]

    def _validate_route_overlap(self, route, owner, expanded_keys):
        name = paths.string(route.contents[7].value)
        start_id = route.contents[9].value
        if name == '' and start_id == -1:
            return
        need(name and type(start_id) is int and start_id >= -1, 'Incomplete saved Route Overlap reference')
        terminal = expanded_keys[-1]
        start = terminal if start_id == -1 else (terminal[0], start_id)
        if route.contents[5].values[4] != -1:
            need(terminal[0] != owner[0] and start == terminal,
                 'A continued primary Route must use a reviewed overlap at its expanded terminal End')
        keys = self.shunting_movements.get((start, name))
        need(keys is not None, 'Unresolved exact Route Overlap Shunting reference')
        need(not set(keys).intersection(expanded_keys[:-1]), 'Overlap re-enters its preceding Route')


def _project(documents, document_paths, catalog):
    result = EditableItineraryProject(
        documents, document_paths=document_paths,
        expected_hashes={name: sha(data) for name, data in documents.items()},
        complete_document_set=True,
    )
    result.check_dest_catalog(catalog)
    return result


def _select_dest(project, name):
    matches = [dest for dest in project.dests if paths.string(dest.contents[1].value) == name]
    _require(len(matches) == 1, 'Expected one exact Itinerary name in the project')
    return matches[0]


def _ordered_paths(project, references, start):
    _require(1 <= len(references) <= MAX_PATH_REFERENCES, 'Bounded nonempty Path reference sequence required')
    selected = []
    movement = [start]
    for reference in references:
        document, identity = exact_reference(reference)
        _require((document, identity[2]) == movement[-1], 'Path sequence does not join at the exact directional End')
        path = project.itinerary_path(movement[-1], identity)
        _require(not selected or path is not selected[-1][1], 'Consecutively repeated Path outside the supported domain')
        nodes, _ = project.path_view(path)
        movement.extend(nodes[1:])
        _require(len(movement) <= MAX_EXPANDED_ENDS, 'Itinerary exceeds expanded End limit')
        selected.append((document, path))
    return selected, movement


def _route_sequence(project, selected):
    return [route for _, path in selected for route in project.path_view(path)[1]]


def _station_references(project, movement):
    # A stronger stable-identity check than comparing display names or station
    # codes. The same stop reference must be encountered in the same sequence.
    return [end for end in movement if project.model(end).contents[12].value is not None]


def _margin_members(definition):
    wrapper = route_factory.layout(definition.contents[5].value, 'OTSafetyMarginArray', 0, ['@'], mutable=True)
    array = wrapper.contents[0].value
    kind = writer.kind(array)
    _require(kind in ('NSArray', 'NSMutableArray'), 'Unknown Itinerary safety-margin array')
    base = [('NSArray', 0), ('NSObject', 0)]
    paths.hierarchy(array, [('NSMutableArray', 0), *base] if kind == 'NSMutableArray' else base)
    members = writer.elements(array)
    _require(len(members) <= 10000, 'Safety-margin row count exceeds supported range')
    for member in members:
        route_factory.layout(member, 'OTSafetyMargin', 0, ['ff'])
    return wrapper, array, members


def _margin_values(members):
    values = [member.contents[0].values for member in members]
    return [{'position_m': float(position), 'safety_margin_m': float(margin)} for position, margin in values]


def _float32(value):
    _require(type(value) in (int, float) and math.isfinite(value), 'Finite safety-margin values required')
    return struct.unpack('<f', struct.pack('<f', value))[0]


def set_safety_margins(data, name, rows):
    root, version = writer.load_next_compatible(data)
    definition = _definition(root, name)
    counts = incoming_counts(root)
    _require(counts[id(definition)] == 1, 'Edited Itinerary has shared ownership')
    wrapper, array, members = _margin_members(definition)
    shared = counts[id(wrapper)] > 1 or counts[id(array)] > 1 or any(counts[id(member)] > 1 for member in members)
    before = _margin_values(members)
    _require(all(math.isfinite(value) for row in before for value in row.values()),
             'Stored safety-margin values must be finite')
    points = [(_float32(row['position_m']), _float32(row['safety_margin_m'])) for row in rows]
    _require(len(points) <= 10000 and all(first[0] <= second[0] for first, second in zip(points, points[1:])),
             'Supply safety-margin positions in nondecreasing stored order')
    baseline = writer.fingerprint(root)
    replacement_array = paths.clone(array)
    writer.set_elements(replacement_array, [obj([('OTSafetyMargin', 0), ('NSObject', 0)], [('ff', list(point))])
                                            for point in points])
    replacement_wrapper = paths.clone(wrapper)
    replacement_wrapper.contents[0].value = replacement_array
    definition.contents[5].value = replacement_wrapper
    output = writer.dump_verified(root, version)
    fresh, _ = writer.load_next_compatible(output)
    saved = _definition(fresh, name)
    after = _margin_values(_margin_members(saved)[2])
    _require([struct.pack('<ff', row['position_m'], row['safety_margin_m']) for row in after]
             == [struct.pack('<ff', *point) for point in points], 'Fresh safety-margin profile differs from saved values')
    _require(paths.info(saved) == paths.info(definition), 'Itinerary definition changed outside its safety margins')
    definition.contents[5].value = wrapper
    _require(writer.fingerprint(root) == baseline, 'Unexpected mutation outside the selected safety-margin profile')
    return output, {'operation': 'set_itinerary_safety_margins', 'name': name, 'before': before, 'after': after,
                    'old_profile_contained_shared_objects': shared, 'native_gui_or_simulation_verified': False}


def replace_paths(documents, catalog, document_paths, name, references, description=None):
    project = _project(documents, document_paths, catalog)
    dest = _select_dest(project, name)
    owner, _ = project.owners[id(dest)]
    root, version = project.roots[owner], project.versions[owner]
    before = paths.info(dest)
    original_movement, _ = project.dest_view(dest)
    original_selection, _ = _ordered_paths(project, before['saved_references'], original_movement[0])
    selected, movement = _ordered_paths(project, references, original_movement[0])
    _require(movement[-1] == original_movement[-1], 'Path replacement must preserve the last directional End')
    _require(_station_references(project, movement) == _station_references(project, original_movement),
             'Path replacement must preserve the ordered Station references')

    margins = route_factory.wrapper(dest.contents[5].value, 'OTSafetyMarginArray')
    _require(not margins or movement == original_movement,
             'Replacements on a different movement require reviewing the distance-based safety margins')
    running_time_revalidation_required = _route_sequence(project, original_selection) != _route_sequence(project, selected)

    cat_root, cat_version = writer.load_next_compatible(catalog)
    entries = route_factory.wrapper(cat_root, 'OTDestInfoList')
    row, = [entry for entry in entries if paths.string(entry.contents[1].value) == name]
    counts = incoming_counts(cat_root)
    _require(counts[id(cat_root)] == 0 and counts[id(row)] == 1,
             'Edited DestInfo catalog entry has shared ownership')

    document_baseline = writer.fingerprint(root)
    catalog_baseline = writer.fingerprint(cat_root)
    old_first, old_description, old_refs = (dest.contents[g].value for g in (0, 3, 4))
    old_catalog_refs = row.contents[4].value
    document_counts = incoming_counts(root)
    _require(document_counts[id(dest)] == 1, 'Edited Itinerary has shared ownership')
    _require(document_counts[id(old_first)] == 1 and document_counts[id(old_refs)] == 1
             and counts[id(old_catalog_refs)] == 1, 'Edited Itinerary arrays have shared ownership')

    # Native OTDest encodes only the first Path object. Both independent roots
    # keep the complete ordered OTArrayExtInfo list with their own object graphs.
    dest.contents[0].value = paths.array_like(old_first, [selected[0][1]])
    dest.contents[4].value = paths.array_like(old_refs, [inf(path, doc) for doc, path in selected])
    row.contents[4].value = paths.array_like(old_catalog_refs, [inf(path, doc) for doc, path in selected])
    if description is not None:
        dest.contents[3].value = paths.fresh_string(old_description, description)

    modified_document = writer.dump_verified(root, version)
    modified_catalog = writer.dump_verified(cat_root, cat_version)
    checked = _project({**documents, owner: modified_document}, document_paths, modified_catalog)
    saved = _select_dest(checked, name)
    after = paths.info(saved)
    expected = {**before, 'saved_references': references,
                'description': before['description'] if description is None else description}
    _require(after == expected and checked.dest_view(saved)[0] == movement,
             'Fresh Itinerary definition/references differ from the proposed edit')

    dest.contents[0].value = old_first
    dest.contents[3].value = old_description
    dest.contents[4].value = old_refs
    row.contents[4].value = old_catalog_refs
    _require(writer.fingerprint(root) == document_baseline and writer.fingerprint(cat_root) == catalog_baseline,
             'Unexpected mutation beyond the requested definition and catalog references')
    report = {'operation': 'replace_itinerary_paths', 'owner_document': owner,
              'before': before, 'after': after, 'movement_ends_preserved': True,
              'station_order_preserved': True, 'safety_margin_count': len(margins),
              'catalog_bindings_verified': True, 'native_gui_or_simulation_verified': False,
              'running_time_revalidation_required': running_time_revalidation_required}
    return modified_document, modified_catalog, report


class ItineraryEditTools(NextFunctions, CourseBundles):
    def edit(self, request):
        args = request.edit
        return self.edit_project(args) if isinstance(args, ProjectItineraryEdit) else self.edit_document(args)

    def edit_document(self, args):
        path, blob, root, _ = self.checked(args.source)
        if path.suffix != '.opentrack' or (args.target_path is not None and self.path(args.target_path).suffix != '.opentrack'):
            raise APIError('CURRENT_ITINERARY_EDIT', 'Source and target must use the .opentrack extension')
        try:
            if args.action == 'set_safety_margins':
                output, report = set_safety_margins(blob, args.name, [row.model_dump() for row in args.rows])
            else:
                definition = _definition(root, args.name)
                _require(incoming_counts(root)[id(definition)] == 1, 'Edited Itinerary has shared ownership')
                output, report = paths.set_description(blob, 'OTDest', args.name, args.description)
        except (ValueError, TypeError, IndexError, OverflowError) as error:
            raise APIError('CURRENT_ITINERARY_EDIT', str(error)[:500]) from error
        return self.finish(args, path, blob, output, report)

    def edit_project(self, args):
        inputs = {key: self.checked(source) for key, source in args.documents.items()}
        catalog_path, catalog, _, _ = self.checked(args.catalog)
        paths_by_key = {key: item[0] for key, item in inputs.items()}
        self.same_project([catalog_path, *paths_by_key.values()])
        if len({catalog_path, *paths_by_key.values()}) != len(inputs) + 1:
            raise _runscope('Each source role requires a distinct archive file')
        runpath, runblob, scope_check, scope_evidence = self.checked_document_list(args, inputs)
        bound_dest_catalog(self, runpath, runblob, catalog_path)
        if args.target_directory is not None:
            target = self.path(args.target_directory)
            if target.is_relative_to(runpath.parent):
                raise _runscope('Publish the fresh archive bundle outside the verified input project')
        documents = {key: value[1] for key, value in inputs.items()}
        native_paths = run_infrastructure_paths(runblob)
        references = [item.model_dump() for item in args.paths]
        try:
            if args.action == 'replace_paths':
                document_output, catalog_output, report = replace_paths(
                    documents, catalog, native_paths, args.name, references, args.description)
            else:
                bundle, report = create_finite_itinerary(
                    documents, catalog, document_paths=native_paths,
                    expected_hashes={**{key: sha(blob) for key, blob in documents.items()}, '$dest_catalog': sha(catalog)},
                    complete_document_set=True, name=args.name, paths=references,
                    description=args.description or '', project_type=EditableItineraryProject)
                document_output = bundle['documents'][report['owner_document']]
                catalog_output = bundle['catalog']
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            raise APIError('CURRENT_ITINERARY_EDIT', str(error)[:500]) from error

        docfile = paths_by_key[report['owner_document']]
        members = {docfile.name: document_output, catalog_path.name: catalog_output}
        dependencies = {runpath: runblob, catalog_path: catalog,
                        **{file: data for file, data, _, _ in inputs.values()}}
        manifest = {
            'format': 'opentrack-current-itinerary-edit-increment-v1',
            'files': {name: {'sha256': sha(data), 'bytes': len(data)} for name, data in members.items()},
            'sources': {str(file.relative_to(self.root)): {'sha256': sha(data)}
                        for file, data in dependencies.items()},
            'replacement_for': {file.name: str(file.relative_to(self.root)) for file in (docfile, catalog_path)},
            'document_scope': scope_evidence,
            'complete_relocated_project': False,
        }
        result = {'preview_only': args.preview_only, 'saved': False, 'manifest': manifest,
                  'bundle_type': 'Itinerary document and DestInfo catalog increment',
                  'change_report': report, 'fresh_archive_reload_verified': True,
                  'native_application_started': False, 'complete_relocated_project': False}
        return self.publish_bundle(inputs=dependencies, members=members, manifest=manifest, result=result,
                                   target_directory=args.target_directory, scope_check=scope_check,
                                   windows_publication=True)


def tool_definitions(root):
    service = ItineraryEditTools(root)
    return [('opentrack_edit_current_itinerary',
             'Create an Itinerary from a finite ordered Path sequence, edit an existing description or safety-margin rows, '
             'or replace its Path references with a continuous chain preserving directional endpoints and station order in '
             'the supported project profile, including validated Shunting/Overlap references. Verify the source and reload the new bytes. Preview or save a '
             'fresh document copy or document/DestInfo pair. Never modifies the source or executes OpenTrack.',
             EditItinerary, service.edit, False, False)]
