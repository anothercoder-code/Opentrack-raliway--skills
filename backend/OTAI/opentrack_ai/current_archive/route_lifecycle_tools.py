"""Transactionally edit saved Routes and their one optional continuation."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from ..errors import APIError
from . import path_functions as path, route_factory, writer
from .bundle_tools import CourseBundles, Source
from .graph_references import incoming_counts
from .itinerary_edit_tools import bound_dest_catalog, run_infrastructure_paths
from .movement_edits import _movement_project
from .multi_document.core import ident, ref
from .next_tools import NextFunctions
from .operation_tools import I32, Name, RouteSelector
from .route_edit_tools import _affected_movements, _indications, _route_shape, _zone_nodes
from .tools import Input, PathText, sha


require = route_factory.require


class RenameRoute(Input):
    action: Literal['rename']
    new_name: Name


class DeleteRoute(Input):
    action: Literal['delete']


class RouteSegment(Input):
    document: Name
    end_ids: Annotated[list[I32], Field(min_length=1, max_length=1000)]
    release_group_end_ids: Annotated[list[I32], Field(max_length=1000)]
    slow_speed_zone_end_ids: Annotated[list[I32], Field(min_length=2, max_length=2)] | None = None
    clear_slow_speed_zone: StrictBool = False

    @model_validator(mode='after')
    def check_zone(self):
        if self.clear_slow_speed_zone and self.slow_speed_zone_end_ids is not None:
            raise ValueError('Specify a slow-speed zone or clear it')
        return self


class ReplaceRouteExtent(Input):
    action: Literal['replace_extent']
    segments: Annotated[list[RouteSegment], Field(min_length=1, max_length=2)]


class EditRouteLifecycle(Input):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    target_document: Name
    dest_catalog: Source
    courses: Source | None = None
    route: RouteSelector
    operation: Annotated[RenameRoute | DeleteRoute | ReplaceRouteExtent, Field(discriminator='action')]
    preview_only: StrictBool = True
    target_directory: PathText | None = None

    @model_validator(mode='after')
    def verify_output(self):
        if self.target_document not in self.documents:
            raise ValueError('The primary Route document must be supplied')
        if not self.preview_only and self.target_directory is None:
            raise ValueError('Saving requires a fresh bundle directory')
        return self


def _identity(reference):
    return reference['name'], reference['array_id'], reference['start_id']


def _owner_array(project, key, counts):
    document, _ = key
    root = project.roots[document]
    holder = project.model(key).contents[15].value
    route_factory.wrapper(holder, 'OTRouteList')
    array = holder.contents[0].value
    require(counts[document][id(root)] == 0 and counts[document][id(holder)] == 1
            and counts[document][id(array)] == 1, 'Shared Route ownership list')
    return array


def _dependent_paths(project, owner, reference, selected, counts):
    dependencies = []
    for movement in project.paths_objects:
        document, _ = project.owners[id(movement)]
        linked = project.path_view(movement)[1]
        refs = path.mutable_array(movement.contents[4].value)
        for index, (route_doc, item) in enumerate(linked):
            if route_doc != owner[0] or item != reference:
                continue
            row = refs[index]
            require(counts[document][id(row)] == 1, 'Saved Route metadata of a dependent Path is shared')
            if index == 0:
                first = movement.contents[0].value
                require(path.mutable_array(first) == [selected] and counts[document][id(first)] == 1,
                        'Dependent Path first Route object is shared or mismatched')
            dependencies.append((document, movement, index, row))
    return dependencies


def _guard_identity(project, owner, reference, dependencies, new_name=None, new_owner=None, new_id=None):
    audited = {id(row) for _, _, _, row in dependencies}
    known_movement_refs = {id(info) for item in [*project.paths_objects, *project.dests]
                           for info in path.mutable_array(item.contents[4].value)}
    for document, root in project.roots.items():
        for item in writer.objects(root):
            kind = writer.kind(item)
            if kind == 'OTRoute' and new_name is not None:
                require(ident(item)[0].casefold() != new_name.casefold(), 'New Route name already exists')
            if kind in ('OTRouteExclusionCondition', 'OTRouteRuleSet'):
                raise path.Unsupported('Saved Route exclusion rules require a rule-aware identity edit')
            if kind not in ('OTArrayInfo', 'OTArrayExtInfo') or id(item) in audited:
                continue
            name = path.string(item.contents[0].value).casefold()
            require(new_name is None or name != new_name.casefold(),
                    'New Route name would capture a saved reference')
            if id(item) in known_movement_refs:
                continue
            if kind == 'OTArrayExtInfo' or document == owner[0]:
                require(name != reference['name'].casefold() and
                        item.contents[1].values != [reference['array_id'], owner[1]],
                        'An unaudited saved reference uses the selected Route identity')
            if new_owner is not None and document == new_owner[0]:
                require(item.contents[1].values != [new_id, new_owner[1]],
                        'New Route ID would capture a saved reference')


def _guard_incidents(courses, keys, route_names=()):
    if courses is None:
        return
    root, _ = writer.load_next_compatible(courses)
    require(writer.kind(root) == 'OTCourseList', 'Expected the run-bound CourseList archive')
    for incident in writer.objects(root):
        if writer.kind(incident) != 'OTIncident':
            continue
        require(0 <= incident.clazz.version <= 12 and len(incident.contents) > 5
                and incident.contents[2].encodings == [b'@']
                and incident.contents[5].encodings == [b'i', b'i', b'i'],
                'Unknown saved Incident target encoding')
        array_id, start_id, incident_type = incident.contents[5].values
        if incident_type == 4:
            document = path.string(incident.contents[2].value).casefold()
            require((document, start_id, array_id) not in keys,
                    'A saved Route-speed Incident references this Route identity')
        if incident_type == 13 and route_names:
            require(len(incident.contents) > 11 and all(incident.contents[i].encodings == [b'@'] for i in (10, 11)),
                    'Unknown saved route-relative Incident target encoding')
            names = {path.string(incident.contents[i].value) for i in (10, 11)
                     if incident.contents[i].value is not None}
            require(names.isdisjoint(route_names),
                    'A saved route-relative Incident references the selected Route name or extent')


def _replace_fragment(route, template, nodes, releases, zone, continuation_index):
    protection = _route_shape(template) + 1
    route.contents[0].value = path.array_like(template.contents[0].value, nodes)
    route.contents[5].values[4] = continuation_index
    route.contents[protection].values[:] = [
        path.array_like(template.contents[protection].values[0], releases), *zone,
    ]


def _segments(project, requested, old_fragments):
    require(1 <= len(requested) <= 2,
            'A native Route crosses at most one document boundary. Join multiple Routes in a Path')
    keys, pieces = [], []
    for segment in requested:
        document = segment['document']
        ends = [(document, value) for value in segment['end_ids']]
        require(ends, 'Each Route fragment needs at least one directional End')
        nodes = [project.model(key) for key in ends]
        require(all(writer.kind(node) == 'OTEndModel' for node in nodes), 'Choose ordinary directional Ends')
        releases = _zone_nodes(nodes, segment['release_group_end_ids'])
        zone_ids = segment.get('slow_speed_zone_end_ids')
        original = old_fragments.get(document, [None, None])
        if zone_ids is None and not segment.get('clear_slow_speed_zone') and any(end is not None for end in original):
            require(all(end in nodes for end in original),
                    'Specify or clear the slow-speed zone when its Ends leave this fragment')
            zone_ids = [project.key(end)[1] for end in original]
        zone = _zone_nodes(nodes, zone_ids) if zone_ids is not None else [None, None]
        require(len(zone) == 2, 'A slow-speed zone needs two ordered Ends')
        pieces.append((nodes, releases, zone))
        keys.extend(ends)
    require(len(keys) >= 2 and len(keys) == len(set(keys)), 'Use a simple directed Route with distinct Ends')
    boundaries = [project.key(end) for _, releases, _ in pieces for end in releases]
    require(boundaries and boundaries[0] == keys[0] and boundaries[-1] == keys[-1],
            'Release boundaries must cover the Route start and terminal End')
    for first, second in zip(keys, keys[1:]):
        project.edge_between(first, second)
    receiving = None
    if len(pieces) == 2:
        require(requested[0]['document'] != requested[1]['document'], 'Local Routes use one saved fragment')
        source = project.related(project.key(pieces[0][0][-1]))
        receiving = project.block_end(source)
        require(receiving[0] == requested[1]['document'], 'Selected continuation is outside the reciprocal receiving document')
    return keys, pieces, receiving


def _verify_new_start(selected, old_end, new_end):
    old_signal = old_end.contents[11].value
    new_signal = new_end.contents[11].value
    require(new_signal is not None and old_signal.contents[8].values[0] == new_signal.contents[8].values[0]
            and old_signal.contents[9].values[0] == new_signal.contents[9].values[0],
            'Relocating the Route start requires a compatible main signal type and indication mode')
    if new_signal.contents[9].values[0] != 2:
        existing = route_factory.wrapper(new_end.contents[15].value, 'OTRouteList')
        known = {item.contents[0].value for route in existing for item in _indications(route)[1]}
        require(all(item.contents[0].value in known for item in _indications(selected)[1]),
                'New main signal must already use the Route aspect codes')


def _clone_fragment(template, *, keep_indications):
    fragment = path.clone(template)
    old_holder, indications = _indications(template)
    holder = path.clone(old_holder)
    rows = []
    if keep_indications:
        for indication in indications:
            item = path.clone(indication)
            item.contents[1].value = fragment
            rows.append(item)
    holder.contents[0].value = path.array_like(old_holder.contents[0].value, rows)
    fragment.contents[4].value = holder
    return fragment


def _has_overlap(route):
    return bool(path.string(route.contents[7].value)) or route.contents[9].value != -1


def edit_route_lifecycle(documents, document_paths, catalog, target_document, reference, operation, courses=None):
    project_options = {'allow_external_destinations': operation['action'] == 'rename'}
    project = _movement_project(documents, document_paths, catalog, **project_options)
    before = _movement_project(documents, document_paths, catalog, **project_options)
    owner = (target_document, reference['start_id'])
    identity = _identity(reference)
    selected = project.owned(owner, 'OTRoute', identity)
    require(writer.kind(project.model(owner)) == 'OTEndModel', 'Select the primary Route at its main signal')
    old_keys = project.route_view(selected)
    record = next((row for row in project.continuations if row['source_document'] == target_document
                   and row['route'] == reference), None)
    old_receiving = (record['target_document'], record['target_connector']) if record else None
    old_fragment = project.owned(old_receiving, 'OTRoute', identity) if old_receiving else None
    counts = {doc: incoming_counts(graph) for doc, graph in project.roots.items()}
    _owner_array(project, owner, counts)
    dependencies = _dependent_paths(project, owner, reference, selected, counts)
    linked = [{'document': doc, **ref(item)} for doc, item, _, _ in dependencies]
    require(counts[target_document][id(selected)] == 1 + len(_indications(selected)[1])
            + sum(index == 0 for _, _, index, _ in dependencies),
            'Selected Route has unexpected direct saved references')
    if old_fragment is not None:
        _owner_array(project, old_receiving, counts)
        require(counts[old_receiving[0]][id(old_fragment)] == 1 + len(_indications(old_fragment)[1]),
                'Continuation has other direct saved references')

    undo = []
    touched = set()

    def replace_group(document, group, values):
        previous = list(group.values)
        undo.append(lambda: group.values.__setitem__(slice(None), previous))
        group.values[:] = values
        touched.add(document)

    def replace_items(key, array, items):
        previous = array.contents
        undo.append(lambda: setattr(array, 'contents', previous))
        writer.set_elements(array, items)
        touched.add(key[0])

    action = operation['action']
    new_owner, new_identity, new_keys, receiving = owner, identity, old_keys, old_receiving
    pieces = None
    if action == 'rename':
        new_name = operation['new_name']
        require(new_name and new_name.isprintable() and new_name.strip() == new_name
                and new_name.casefold() != identity[0].casefold(), 'Use a distinct printable Route name')
        _guard_identity(project, owner, reference, dependencies, new_name=new_name)
        _guard_incidents(courses, set(), {identity[0], new_name})
        names = [(target_document, selected.contents[1])]
        if old_fragment is not None:
            names.append((old_receiving[0], old_fragment.contents[1]))
        names.extend((document, row.contents[0]) for document, _, _, row in dependencies)
        fresh = {}
        for document, group in names:
            key = document, id(group.value)
            if key not in fresh:
                fresh[key] = path.fresh_string(group.value, new_name)
            replace_group(document, group, [fresh[key]])
        new_identity = (new_name, *identity[1:])
    elif action == 'delete':
        require(not dependencies, f'Remove or replace this Route in dependent Paths first: {linked}')
        _guard_identity(project, owner, reference, dependencies)
        _guard_incidents(courses, {(target_document.casefold(), identity[2], identity[1])}, {identity[0]})
        for key, route in [(owner, selected), (old_receiving, old_fragment)]:
            if route is not None:
                array = _owner_array(project, key, counts)
                replace_items(key, array, [item for item in path.mutable_array(array) if item is not route])
        new_owner = new_identity = receiving = None
        new_keys = []
    else:
        require(action == 'replace_extent', 'Unknown Route lifecycle operation')
        old_fragments = {target_document: selected}
        if old_fragment is not None:
            old_fragments[old_receiving[0]] = old_fragment
        zones = {document: item.contents[_route_shape(item) + 1].values[1:]
                 for document, item in old_fragments.items()}
        requested = {piece['document'] for piece in operation['segments']}
        require(not any(any(end is not None for end in zone) for document, zone in zones.items()
                        if document not in requested),
                'Clear the old slow-speed zone before removing its document from the Route')
        new_keys, pieces, receiving = _segments(project, operation['segments'], zones)
        if new_keys != old_keys:
            _guard_incidents(courses, set(), {identity[0]})
        new_owner = new_keys[0]
        if new_owner != owner:
            require(not dependencies, f'Replace this Route in dependent Paths before changing its start: {linked}')
            end = project.model(new_owner)
            new_id = end.contents[19].value + 1
            require(new_id <= 2147483647, 'New Route owner exhausted its saved R/S/P ID counter')
            _guard_identity(project, owner, reference, dependencies, new_owner=new_owner, new_id=new_id)
            _guard_incidents(courses, {(target_document.casefold(), identity[2], identity[1]),
                                       (new_owner[0].casefold(), new_owner[1], new_id)})
            new_identity = (identity[0], new_id, new_owner[1])
        final_old = old_fragment if old_fragment is not None else selected
        has_overlap = _has_overlap(selected) or _has_overlap(final_old)
        require(not has_overlap or (old_keys[-1] == new_keys[-1]
                and bool(old_receiving) == bool(receiving)),
                'An extent change that moves a bound Overlap requires an explicit Overlap edit')
        new_primary = _clone_fragment(selected, keep_indications=True) if new_owner != owner else path.clone(selected)
        primary_index = len(pieces[0][0]) if receiving is not None else -1
        _replace_fragment(new_primary, selected, *pieces[0], primary_index)
        new_primary.contents[2].values[:] = list(new_identity[1:])
        if new_owner == owner:
            for index in (0, 5, _route_shape(selected) + 1):
                replace_group(target_document, selected.contents[index], new_primary.contents[index].values)
        else:
            _verify_new_start(selected, project.model(owner), project.model(new_owner))
            original_array = _owner_array(project, owner, counts)
            new_array = _owner_array(project, new_owner, counts)
            replace_items(owner, original_array, [item for item in path.mutable_array(original_array) if item is not selected])
            replace_items(new_owner, new_array, [*path.mutable_array(new_array), new_primary])
            replace_group(new_owner[0], project.model(new_owner).contents[19], [new_identity[1]])
        if old_fragment is not None and receiving != old_receiving:
            old_array = _owner_array(project, old_receiving, counts)
            replace_items(old_receiving, old_array,
                          [item for item in path.mutable_array(old_array) if item is not old_fragment])
        if receiving is not None:
            template = old_fragment if old_fragment is not None else selected
            fragment = (path.clone(template) if receiving == old_receiving else
                        _clone_fragment(template, keep_indications=old_fragment is not None))
            _replace_fragment(fragment, template, *pieces[1], -1)
            fragment.contents[2].values[:] = list(new_identity[1:])
            if receiving == old_receiving:
                for index in (0, 2, 5, _route_shape(old_fragment) + 1):
                    replace_group(receiving[0], old_fragment.contents[index], fragment.contents[index].values)
            else:
                array = _owner_array(project, receiving, counts)
                replace_items(receiving, array, [*path.mutable_array(array), fragment])

    outputs = {doc: writer.dump_verified(project.roots[doc], project.versions[doc]) for doc in sorted(touched)}
    checked = _movement_project({**documents, **outputs}, document_paths, catalog, **project_options)
    after_reference = None
    if new_identity is None:
        require(not any(ident(candidate) == identity and checked.owners[id(candidate)] in (owner, old_receiving)
                        for candidate in checked.routes), 'Deleted Route or its fragment survived archive reload')
    else:
        saved = checked.owned(new_owner, 'OTRoute', new_identity)
        after_reference = {'document': new_owner[0], **ref(saved)}
        require(checked.route_view(saved) == new_keys, 'Saved Route movement differs after archive reload')
        for document, movement, index, _ in dependencies:
            movement_owner = project.owners[id(movement)]
            saved_path = checked.owned(movement_owner, 'OTPath', ident(movement))
            require(checked.path_view(saved_path)[1][index] == (after_reference['document'], ref(saved)),
                    'Saved dependent Path does not resolve to the edited Route')
        if pieces is not None:
            fragments = [saved]
            if receiving is not None:
                fragments.append(checked.owned(receiving, 'OTRoute', new_identity))
            for fragment, (_, releases, zone) in zip(fragments, pieces):
                group = fragment.contents[_route_shape(fragment) + 1].values
                actual = [checked.key(end) for end in path.mutable_array(group[0])]
                actual_zone = [checked.key(end) if end is not None else None for end in group[1:]]
                require(actual == [project.key(end) for end in releases]
                        and actual_zone == [project.key(end) if end is not None else None for end in zone],
                        'Saved Route release groups or slow-speed zone differ after archive reload')
    affected = _affected_movements(before, checked)
    for restore in reversed(undo):
        restore()
    for doc in outputs:
        require(writer.fingerprint(project.roots[doc]) == writer.fingerprint(before.roots[doc]),
                'Unexpected change outside the selected Route records and dependencies')
    return outputs, {'operation': action, 'before': {'document': owner[0], **reference},
                     'after': after_reference, 'old_directional_ends': old_keys, 'new_directional_ends': new_keys,
                     'old_receiving_connector': old_receiving, 'new_receiving_connector': receiving,
                     'dependent_paths': linked, 'affected': affected, 'native_runtime_verified': False}


class RouteLifecycle(NextFunctions, CourseBundles):
    def bound_courses(self, args, run_path, run):
        records = [line.split('#') for line in run.decode('ascii').splitlines() if line.startswith('CourseFile#')]
        if not records and args.courses is None:
            return {}
        if len(records) != 1 or len(records[0]) != 3 or records[0][2] or args.courses is None:
            raise APIError('DOCUMENT_SCOPE', 'Supply the unique run-bound CourseFile and its SHA')
        raw = records[0][1]
        candidate = Path(raw)
        if (not raw or any(x in raw for x in ('%', '$', '\\')) or '..' in candidate.parts
                or candidate.suffix != '.courses'):
            raise APIError('DOCUMENT_SCOPE', 'Expected an explicit portable .courses path')
        if not candidate.is_absolute():
            candidate = run_path.parent / candidate
        if not candidate.is_relative_to(run_path.parent):
            raise APIError('DOCUMENT_SCOPE', 'Run-bound CourseList must be inside the source project')
        course_path, course_data, _, _ = self.checked(args.courses)
        if course_path != self.path(candidate.relative_to(self.root).as_posix()):
            raise APIError('DOCUMENT_SCOPE', 'Supplied CourseList differs from run CourseFile')
        return {course_path: course_data}

    def edit(self, args):
        inputs = {name: self.checked(spec) for name, spec in args.documents.items()}
        if len({entry[0] for entry in inputs.values()}) != len(inputs):
            raise APIError('DOCUMENT_SCOPE', 'Supply distinct project infrastructure documents')
        run_path, run, scope_check, scope = self.checked_document_list(args, inputs)
        catalog_path, catalog, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run_path, run, catalog_path)
        courses = self.bound_courses(args, run_path, run)
        if args.target_directory is not None and self.path(args.target_directory).is_relative_to(run_path.parent):
            raise APIError('DOCUMENT_SCOPE', 'Publish replacement archives outside the source project')
        try:
            outputs, report = edit_route_lifecycle(
                {doc: entry[1] for doc, entry in inputs.items()}, run_infrastructure_paths(run), catalog,
                args.target_document, args.route.model_dump(), args.operation.model_dump(),
                next(iter(courses.values()), None),
            )
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_ROUTE_LIFECYCLE', str(exc)[:500]) from exc
        members = {inputs[doc][0].name: blob for doc, blob in outputs.items()}
        dependencies = {run_path: run, catalog_path: catalog, **courses, **{entry[0]: entry[1] for entry in inputs.values()}}
        manifest = {'format': 'opentrack-route-lifecycle-v1',
                    'files': {name: {'sha256': sha(blob), 'bytes': len(blob)} for name, blob in members.items()},
                    'replacement_for': {inputs[name][0].name: inputs[name][0].relative_to(self.root).as_posix()
                                        for name in outputs},
                    'sources': {file.relative_to(self.root).as_posix(): sha(blob) for file, blob in dependencies.items()},
                    'document_scope': scope, 'complete_relocated_project': False}
        result = {'preview_only': args.preview_only, 'saved': False, 'manifest': manifest,
                  'change_report': report, 'fresh_archive_reload_verified': True, 'native_application_started': False}
        return self.publish_bundle(inputs=dependencies, members=members, manifest=manifest, result=result,
                                   target_directory=args.target_directory, scope_check=scope_check,
                                   windows_publication=True)


def tool_definitions(root):
    service = RouteLifecycle(root)
    return [('opentrack_edit_current_route_lifecycle',
             'Rename, remove an unused Route, or replace a Route extent using one local fragment or a reciprocal '
             'pair. Revalidate run-bound Path, Itinerary, DestInfo and applicable Course Incident references. '
             'Changing the primary owner assigns its next native R/S/P ID. Save a fresh replacement bundle.',
             EditRouteLifecycle, service.edit, False, False)]
