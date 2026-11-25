"""Save reviewed Route discoveries into native local or continued archives."""

from collections import defaultdict
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, StrictBool, StrictInt, StrictStr, model_validator

from ..errors import APIError
from . import path_functions, route_factory, writer
from .bundle_tools import Source
from .graph_references import incoming_counts
from .itinerary_edit_tools import bound_dest_catalog, run_infrastructure_paths
from .movement_edits import _movement_project
from .multi_document.core import ident, need, ref
from .multi_document.generate import route as make_native_route
from .next_tools import Ordinal
from .operation_tools import Name
from .project_candidate_publication import ProjectSave
from .route_discovery_tools import main_signal
from .route_lifecycle_tools import RouteLifecycle, _guard_incidents, _owner_array
from .tools import Input, sha
from .zero_generation.native_signal_routes import string


RouteEnd = Annotated[tuple[Name, Ordinal],
                     BeforeValidator(lambda value: tuple(value) if type(value) is list else value)]
ReviewedName = Annotated[StrictStr, Field(pattern=r'^[!-~](?:[ -~]{0,158}[!-~])?$')]
Description = Annotated[StrictStr, Field(max_length=4096, pattern=r'^[ -~]*$')]
EndSequence = Annotated[list[RouteEnd], Field(min_length=2, max_length=4097)]


class ReviewedDiscovery(Input):
    end_sequence: EndSequence
    edge_sequence: Annotated[list[RouteEnd], Field(min_length=1, max_length=4096)]
    distance_m: Annotated[StrictInt, Field(ge=1, le=2147483647 * 4096)]
    document_boundaries: Annotated[StrictInt, Field(ge=0)] | None = None
    existing_route_names: list[Name] | None = None
    one_route_storage_compatible: StrictBool | None = None
    terminal_kind: Literal['main_signal', 'buffer_stop'] = 'main_signal'


class SelectedRoute(Input):
    name: ReviewedName
    candidate: ReviewedDiscovery
    description: Description = ''
    release_groups: Literal['native_default', 'global', 'each_end', 'explicit'] = 'native_default'
    release_end_sequence: EndSequence | None = None
    reserve_previous: StrictBool = False
    allow_duplicate_movement: StrictBool = False

    @model_validator(mode='after')
    def release_contract(self):
        if (self.release_groups == 'explicit') != (self.release_end_sequence is not None):
            raise ValueError('Explicit release grouping requires a release_end_sequence')
        return self


class FetchRoutes(ProjectSave):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    dest_catalog: Source
    courses: Source | None = None
    routes: Annotated[list[SelectedRoute], Field(min_length=1, max_length=100)]


def _reviewed_chain(project, candidate):
    keys = [tuple(key) for key in candidate['end_sequence']]
    need(len(keys) >= 2 and len(keys) == len(set(keys)), 'Route requires nonrepeated directional Ends')
    models = [project.model(key) for key in keys]
    need(all(writer.kind(end) == 'OTEndModel' for end in models), 'Only ordinary saved directional Ends define a Route')
    need(not any(main_signal(end) for end in models[1:-1]), 'An intermediate main signal splits the Route')
    buffer = candidate.get('terminal_kind', 'main_signal') == 'buffer_stop'
    if buffer:
        need(models[-1].contents[11].value is None
             and route_factory.physical_buffer(models[-1], project.model(project.related(keys[-1]))),
             'The reviewed signal-free physical buffer differs from the saved Route endpoint')
    for terminal in ((models[0],) if buffer else (models[0], models[-1])):
        need(main_signal(terminal), 'Route endpoints must carry native main signals')
        signal = terminal.contents[11].value
        flags = signal.contents[9].values[2]
        need(signal.contents[9].values[0] == 2 and type(flags) is int and 0 <= flags <= 1023 and not flags & 2,
             'The reviewed show-type and terminal signal flag profile is required')
        indications = route_factory.wrapper(signal.contents[10].value, 'OTSigIndList')
        track_speed = [ind for ind in indications if ind.contents[0].value == 0]
        need(len(track_speed) == 1 and track_speed[0].contents[1].value is terminal,
             'Each terminal requires a unique native track-speed aspect tied to its End')
    edges = [project.edge_between(a, b) for a, b in zip(keys, keys[1:])]
    need(edges == [tuple(key) for key in candidate['edge_sequence']], 'Reviewed Edge sequence differs from saved track')
    distance = sum(project.model(edge).contents[9].values[1] for edge in edges)
    need(distance == candidate['distance_m'], 'Reviewed metre count differs from saved track')
    breaks = [i for i, (first, last) in enumerate(zip(keys, keys[1:]), 1) if first[0] != last[0]]
    need(len(breaks) <= 1, 'One saved Route can continue across at most one document boundary')
    if candidate['document_boundaries'] is not None:
        need(candidate['document_boundaries'] == len(breaks), 'Reviewed document boundary count differs')
    need(candidate['one_route_storage_compatible'] is not False, 'Reviewed candidate is marked incompatible')
    if not breaks:
        return keys, (keys,), (keys[0],)
    split, = breaks
    right = keys[split:]
    left = keys[:split]
    connector = project.block_end(project.related(left[-1]))
    need(connector[0] == right[0][0], 'The saved receiving connector does not match the reviewed continuation')
    return keys, (left, right), (keys[0], connector)


def _stable_inventory(project):
    names = set()
    identities = defaultdict(set)
    path_reference_documents = defaultdict(set)
    for path in project.paths_objects:
        stored = path_functions.mutable_array(path.contents[4].value)
        _, reviewed = project.path_view(path)
        for obj, (owner, item) in zip(stored, reviewed, strict=True):
            need(tuple(obj.contents[1].values) == (item['array_id'], item['start_id']),
                 'Saved Path reference differs from its resolved native owner')
            path_reference_documents[id(obj)].add(owner)
    for document, root in project.roots.items():
        for obj in writer.objects(root):
            kind = writer.kind(obj)
            if kind in ('OTRouteExclusionCondition', 'OTRouteRuleSet'):
                raise ValueError('Saved Route exclusion rules need a rule-aware identity allocator')
            if kind == 'OTRoute':
                names.add(ident(obj)[0].casefold())
            elif kind in ('OTArrayInfo', 'OTArrayExtInfo'):
                names.add(path_functions.string(obj.contents[0].value).casefold())
                if kind == 'OTArrayExtInfo':
                    owners = (path_functions.string(obj.contents[2].value),)
                else:
                    owners = path_reference_documents.get(id(obj), (document,))
                for owner in owners:
                    identities[owner.casefold()].add(tuple(obj.contents[1].values))
    return names, identities


def _release_ends(route, chain, fragments):
    mode = route['release_groups']
    if mode == 'native_default':
        # The audited native continuation factory stores the primary start
        # boundary only; the remote companion has no explicit group starts.
        return ([chain[0], chain[-1]],) if len(fragments) == 1 else ([chain[0]], [])
    if mode == 'global':
        selected = {chain[0], chain[-1]}
    elif mode == 'each_end':
        selected = set(chain)
    else:
        explicit = [tuple(key) for key in route['release_end_sequence']]
        offsets = {key: index for index, key in enumerate(chain)}
        need(all(key in offsets for key in explicit) and explicit[0] == chain[0] and explicit[-1] == chain[-1],
             'Release boundaries must include the reviewed first and last Ends')
        order = [offsets[key] for key in explicit]
        need(order == sorted(set(order)), 'Release boundaries must be distinct and in Route order')
        selected = set(explicit)
    return tuple([key for key in fragment if key in selected] for fragment in fragments)


def fetch_routes(documents, paths, dest_catalog, requested, courses=None):
    project = _movement_project(documents, paths, dest_catalog, allow_external_destinations=True)
    known_names, known_reference_ids = _stable_inventory(project)
    counts = {name: incoming_counts(root) for name, root in project.roots.items()}
    known_chains = defaultdict(list)
    for route in project.routes:
        key = project.owners[id(route)]
        if writer.kind(project.model(key)) == 'OTEndModel':
            known_chains[tuple(project.route_view(route))].append(ident(route)[0])
    owner_snapshots = {}
    staged = []
    new_incident_keys = set()
    for packet in requested:
        name = packet['name']
        need(name.casefold() not in known_names, 'Route name already exists or would capture a saved reference')
        chain, fragments, owners = _reviewed_chain(project, packet['candidate'])
        duplicates = known_chains[tuple(chain)]
        need(not duplicates or packet['allow_duplicate_movement'],
             'The candidate already has a saved Route; explicitly request a separately named duplicate')
        origin = owners[0]
        owner = project.model(origin)
        path_functions.guard_counter_references(project.roots[origin[0]], owner, allow_local_shunting=True)
        last_id = owner.contents[19].value
        need(type(last_id) is int and -1 <= last_id < 2147483647, 'Original Route/Path owner ID allocator is exhausted')
        aid = last_id + 1
        need((aid, origin[1]) not in known_reference_ids[origin[0].casefold()],
             'New Route ID would capture a saved reference')
        new_incident_keys.add((origin[0].casefold(), origin[1], aid))
        release_fragments = _release_ends(packet, chain, fragments)
        assembled = []
        for index, (owner_key, fragment, release_keys) in enumerate(zip(owners, fragments, release_fragments)):
            array = _owner_array(project, owner_key, counts)
            items = path_functions.mutable_array(array)
            need(not any(ident(old)[1:] == (aid, origin[1]) for old in items),
                 'A native Route ID is ambiguous at the selected receiving connector')
            owner_snapshots.setdefault(owner_key, project.model(owner_key).contents[19].value)
            nodes = [project.model(key) for key in fragment]
            continuation = len(nodes) if index == 0 and len(fragments) == 2 else -1
            route = make_native_route(name, aid, origin[1], nodes, continuation, fragment=index > 0)
            route.contents[3].value = string(packet['description'])
            route.contents[11].value = int(packet['reserve_previous']) if index == 0 else 0
            group = route.contents[12].values[0]
            route.contents[12].values[0] = path_functions.array_like(group, [project.model(key) for key in release_keys])
            writer.set_elements(array, [*items, route])
            assembled.append({'owner': owner_key, 'continuation_index': continuation, 'end_sequence': fragment,
                              'release_end_sequence': release_keys})
        owner.contents[19].value = aid
        known_names.add(name.casefold())
        duplicates.append(name)
        staged.append({'owner': origin, 'route': {'name': name, 'array_id': aid, 'start_id': origin[1]},
                       'terminal_kind': packet['candidate'].get('terminal_kind', 'main_signal'),
                       'end_sequence': chain, 'edge_sequence': packet['candidate']['edge_sequence'],
                       'distance_m': packet['candidate']['distance_m'], 'fragments': assembled,
                       'reserve_previous': packet['reserve_previous'], 'release_groups': packet['release_groups']})

    _guard_incidents(courses, new_incident_keys)
    touched = sorted({owner[0] for owner in owner_snapshots})
    changed = {doc: writer.dump_verified(project.roots[doc], project.versions[doc]) for doc in touched}
    saved = _movement_project({**documents, **changed}, paths, dest_catalog, allow_external_destinations=True)
    for item in staged:
        identity = tuple(item['route'][role] for role in ('name', 'array_id', 'start_id'))
        primary = saved.owned(item['owner'], 'OTRoute', identity)
        need(saved.route_view(primary) == item['end_sequence'] and ref(primary) == item['route'],
             'Freshly saved Route differs from the reviewed movement')
        need(bool(primary.contents[11].value) == item['reserve_previous'], 'Fresh reservation flag differs')
        for fragment in item['fragments']:
            native = saved.owned(fragment['owner'], 'OTRoute', identity)
            need(native.contents[5].values[4] == fragment['continuation_index']
                 and [saved.key(end) for end in path_functions.mutable_array(native.contents[0].value)]
                 == fragment['end_sequence']
                 and [saved.key(end) for end in path_functions.mutable_array(native.contents[12].values[0])]
                 == fragment['release_end_sequence'], 'Fresh companion or route release boundaries differ')

    added_names = {item['route']['name'].casefold() for item in staged}
    for owner, old_high in owner_snapshots.items():
        current_end = saved.model(owner)
        array = current_end.contents[15].value.contents[0].value
        writer.set_elements(array, [route for route in path_functions.mutable_array(array)
                                    if ident(route)[0].casefold() not in added_names])
        current_end.contents[19].value = old_high
    for document in touched:
        original, version = writer.load_next_compatible(documents[document])
        need(writer.dump_verified(saved.roots[document], saved.versions[document]) == writer.dump_verified(original, version),
             'The verified Route additions also changed an existing archive object or reference')
    return changed, {'created_routes': staged, 'companion_count': sum(len(item['fragments']) - 1 for item in staged),
                     'unchanged_archive_graph_verified': True, 'dest_info_catalog_unchanged': True,
                     'native_runtime_verified': False}


class RouteFetch(RouteLifecycle):
    def fetch(self, args):
        inputs = {name: self.checked(source) for name, source in args.documents.items()}
        run_path, run, scope_check, scope = self.checked_document_list(args, inputs)
        catalog_path, catalog, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run_path, run, catalog_path)
        courses = self.bound_courses(args, run_path, run)
        if args.target_directory is not None and self.path(args.target_directory).is_relative_to(run_path.parent):
            raise APIError('CURRENT_ROUTE_FETCH', 'Publish the new native documents outside the source project')
        try:
            output, report = fetch_routes(
                {name: entry[1] for name, entry in inputs.items()}, run_infrastructure_paths(run), catalog,
                [route.model_dump() for route in args.routes], next(iter(courses.values()), None),
            )
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            raise APIError('CURRENT_ROUTE_FETCH', str(error)[:500]) from error
        members = {inputs[name][0].name: data for name, data in output.items()}
        dependencies = {run_path: run, catalog_path: catalog, **courses,
                        **{entry[0]: entry[1] for entry in inputs.values()}}
        manifest = {
            'format': 'opentrack-route-fetch-v1',
            'files': {name: {'sha256': sha(data), 'bytes': len(data)} for name, data in members.items()},
            'replacement_for': {inputs[name][0].name: inputs[name][0].relative_to(self.root).as_posix()
                                for name in output},
            'sources': {path.relative_to(self.root).as_posix(): sha(data) for path, data in dependencies.items()},
            'document_scope': scope, 'complete_relocated_project': False,
        }
        result = {'preview_only': args.preview_only, 'saved': False, 'manifest': manifest,
                  'change_report': report, 'fresh_archive_reload_verified': True, 'native_application_started': False}
        return self.publish_bundle(inputs=dependencies, members=members, manifest=manifest, result=result,
                                   target_directory=args.target_directory, scope_check=scope_check)


def tool_definitions(root):
    service = RouteFetch(root)
    return [
        ('opentrack_fetch_discovered_routes',
         'Save selected local or one-boundary Routes ending at a reviewed main signal or unsignalized buffer. '
         'Revalidate reviewed Ends, Edges and metres, release grouping and paired continuation, and preserve all '
         'existing movements and catalog references. Preview or publish fresh replacement worksheets.',
         FetchRoutes, service.fetch, False, False),
    ]
