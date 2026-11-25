"""Import selected DestInfo records by materializing their worksheet-owned definitions."""

import math
from typing import Annotated

from pydantic import Field

from ..errors import APIError
from . import path_functions as paths, writer as w
from .finite_itinerary_workflow import MAX_PATH_REFERENCES
from .itinerary_edit_tools import EditableItineraryProject, SafetyMarginRow, _margin_members, _margin_values, _ordered_paths
from .itinerary_lifecycle_tools import _catalog_array, _catalog_row, _copy_margins, _definitions, _owner_array
from .multi_document.generate import inf
from .multi_document_tools import Inventory, Ref
from .operating_plan_edit import need, text
from .operating_plan_edit_tools import Id, OperatingPlanEditTools
from .operation_tools import Name
from .prepare_contract import preflight
from .project_candidate_publication import ProjectSave
from .tools import Input, sha


class Selection(Input):
    source_name: Name
    target_name: Id
    target_paths: Annotated[list[Ref], Field(min_length=1, max_length=MAX_PATH_REFERENCES)] | None = None
    safety_margins: Annotated[list[SafetyMarginRow], Field(max_length=10000)] | None = None


class ImportNativeItineraries(ProjectSave):
    source_project: Inventory
    donor_project: Inventory
    itineraries: Annotated[list[Selection], Field(min_length=1, max_length=100)]
    station_mapping: Annotated[dict[Name, Id], Field(max_length=1000)] = Field(default_factory=dict)


def read_project(state):
    docs = state['documents']
    archive = EditableItineraryProject(docs, document_paths=state['document_paths'],
        expected_hashes={name: sha(blob) for name, blob in docs.items()}, complete_document_set=True)
    archive.check_dest_catalog(state['files'][state['roles']['dest']], allow_external=True)
    return archive


def station_sequence(project, nodes):
    signs = []
    for key in nodes:
        end = project.model(key)
        if w.kind(end) == 'OTEndModel' and end.contents[20].value == 2:
            station = end.contents[12].value
            need(w.kind(station) == 'OTStationModel', 'An itinerary Station reference has no StationModel')
            signs.append(text(station, 7))
    return signs


def metres(project, nodes):
    values = [project.model(project.edge_between(left, right)).contents[9].values[1]
              for left, right in zip(nodes, nodes[1:])]
    need(all(type(value) is int and value > 0 for value in values), 'Itinerary has invalid native Edge length')
    return values


def margin_profile(selection, original, old_lengths, new_lengths):
    if selection.safety_margins is None:
        rows = _margin_values(_margin_members(original)[2])
        need(not rows or old_lengths == new_lengths,
             'Different directed Edge distances require explicit target safety_margins or an empty list')
    else:
        rows = [row.model_dump() for row in selection.safety_margins]
    limit = sum(new_lengths)
    previous = 0
    for row in rows:
        position, margin = row['position_m'], row['safety_margin_m']
        need(math.isfinite(position) and previous <= position <= limit and math.isfinite(margin) and margin >= 0,
             'Safety margins require finite nonnegative values and ordered positions within target geometry')
        previous = position
    profile = _copy_margins(original, rows if selection.safety_margins is not None else None)
    stored = _margin_values(w.elements(profile.contents[0].value))
    need(all(0 <= item['position_m'] <= limit for item in stored), 'A stored margin exceeds target length after rounding')
    return profile, stored


def apply_import(target_state, donor_state, args):
    donor, target = read_project(donor_state), read_project(target_state)
    available = _definitions(donor)
    current = _definitions(target)
    cat_file = target_state['roles']['dest']
    catalog, version = w.load_next_compatible(target_state['files'][cat_file])
    catalog_array, catalog_rows, _ = _catalog_array(catalog)
    active_names = {text(row, 1).casefold() for row in catalog_rows}
    names = [item.target_name.casefold() for item in args.itineraries]
    need(len(set(names)) == len(names) and not set(names) & active_names,
         'Select unique new names outside the existing destination catalog')
    need(len({item.source_name for item in args.itineraries}) == len(args.itineraries),
         'Select each donor Itinerary only once per import')
    owners, cases, encountered = {}, [], set()
    for selection in args.itineraries:
        need(selection.source_name in available, 'Select a donor Itinerary from the bound destination catalog')
        original = available[selection.source_name]
        donor_nodes, _ = donor.dest_view(original)
        saved = paths.info(original)
        references = saved['saved_references'] if selection.target_paths is None else [
            item.model_dump() for item in selection.target_paths]
        start = (references[0]['document'], references[0]['start_id'])
        selected, movement = _ordered_paths(target, references, start)
        source_stations = station_sequence(donor, donor_nodes)
        encountered.update(source_stations)
        target_stations = station_sequence(target, movement)
        mapped = [args.station_mapping.get(sign, sign) for sign in source_stations]
        need(mapped == target_stations, 'Mapped Station order differs from the destination movement')
        need(len(set(source_stations)) == len(set(mapped)), 'Distinct donor Stations map to a single target Station')
        old_lengths, new_lengths = metres(donor, donor_nodes), metres(target, movement)
        profile, margins = margin_profile(selection, original, old_lengths, new_lengths)
        owner = start[0]
        dest = paths.clone(original)
        dest.contents[0].value = paths.array_like(original.contents[0].value, [selected[0][1]])
        dest.contents[1].value = paths.fresh_string(original.contents[1].value, selection.target_name)
        dest.contents[2].values = [-1, -1]
        dest.contents[4].value = paths.array_like(original.contents[4].value, [inf(path, name) for name, path in selected])
        dest.contents[5].value = profile
        owners.setdefault(owner, []).append(dest)
        catalog_rows.append(_catalog_row(selection.target_name, target_state['document_paths'][owner], references))
        cases.append({
            'source_name': selection.source_name, 'target_name': selection.target_name, 'owner_document': owner,
            'source_paths': saved['saved_references'], 'target_paths': references,
            'source_station_signs': source_stations, 'target_station_signs': target_stations,
            'source_length_m': sum(old_lengths), 'target_length_m': sum(new_lengths),
            'target_start_end': start, 'target_terminal_end': movement[-1],
            'safety_margins': margins, 'description': saved['description'], 'movement': movement,
        })
    need(args.station_mapping.keys() <= encountered, 'Unused donor Station mapping')
    changes = {}
    for owner, additions in owners.items():
        root = target.roots[owner]
        array, rows = _owner_array(root)
        w.set_elements(array, [*rows, *additions])
        changes[target_state['document_members'][owner]] = w.dump_verified(root, target.versions[owner])
    w.set_elements(catalog_array, catalog_rows)
    changes[cat_file] = w.dump_verified(catalog, version)
    files = {**target_state['files'], **changes}
    docs = {name: files[member] for name, member in target_state['document_members'].items()}
    checked = read_project({**target_state, 'files': files, 'documents': docs})
    definitions = _definitions(checked)
    need(definitions.keys() == current.keys() | {row['target_name'] for row in cases}, 'Unexpected saved Itinerary inventory')
    for name, prior in current.items():
        fresh = definitions[name]
        need(paths.info(prior) == paths.info(fresh)
             and target.dest_view(prior)[0] == checked.dest_view(fresh)[0]
             and w.fingerprint(prior) == w.fingerprint(fresh), 'Existing target Itinerary changed')
    for case in cases:
        dest = definitions[case['target_name']]
        info = paths.info(dest)
        need(checked.dest_view(dest)[0] == case.pop('movement') and info['description'] == case['description']
             and info['saved_references'] == case['target_paths']
             and _margin_values(_margin_members(dest)[2]) == case['safety_margins'],
             'Saved native Itinerary differs from its approved mapped movement')

    def read_bound(path):
        prefix = target_state['root'] + '/'
        need(path.startswith(prefix), 'Run dependency is outside the selected target project')
        return files[path[len(prefix):]]

    check = preflight.check(target_state['run'], read_bound)
    return changes, {
        'imported_itineraries': cases, 'structural_readback_verified': True,
        'static_simulation_preflight': {'passed': check['passed_static_subset'], 'errors': check['errors']},
        'native_execution': False,
    }


class NativeItineraryImport(OperatingPlanEditTools):
    def import_itineraries(self, args):
        state = self.load_operating_project(args)
        donor = self.load_project(args.donor_project, minimum_documents=1)
        if not args.preview_only:
            target = self.path(args.target_directory)
            if target.is_relative_to(donor['base']) or donor['base'].is_relative_to(target):
                raise APIError('NATIVE_ITINERARY_TARGET', 'Use a fresh target separate from the donor project')
        for path, raw in donor['inputs'].items():
            if path in state['inputs'] and raw != state['inputs'][path]:
                raise APIError('SOURCE_CHANGED', 'A shared donor file changed between the two project snapshots')
        try:
            changed, report = apply_import(state, donor, args)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_ITINERARY_IMPORT_INVALID', str(exc)[:700]) from exc
        target_scope = state['scope_check']

        def scope_check():
            target_scope()
            donor['scope_check']()

        state['scope_check'] = scope_check
        state['inputs'].update(donor['inputs'])
        report['donor_catalog_sha256'] = sha(donor['files'][donor['roles']['dest']])
        return self.publish_operating_increment(args, state, changed, report)


def tool_definitions(root):
    service = NativeItineraryImport(root)
    return [('opentrack_import_native_itinerary_archive',
             'Import selected native DestInfo rows and worksheet-owned Itineraries into a target project. '
             'Resolve target Path identities and station order, verify distance-based safety margins, '
             'and publish the coordinated worksheet and .dest increment.',
             ImportNativeItineraries, service.import_itineraries, False, False)]
