"""Merge selected formations and their exact native vehicle dependencies."""

from copy import copy
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..errors import APIError
from . import catalogs as c, course_factories as cf, writer as w
from .bundle_tools import Source
from .consist_workflow.core import finite, summary
from .graph_references import incoming_counts
from .itinerary_edit_tools import EditableItineraryProject
from .legacy_rolling_stock import upgrade_category, upgrade_train
from .multi_document_tools import Inventory
from .operating_plan_edit import need, text
from .operating_plan_edit_tools import Id, OperatingPlanEditTools, operating_candidate
from .operation_tools import Name
from .pre_service_project import validate_pre_service_project
from .project_candidate_publication import ProjectSave, project_target, publish_candidate
from .project_workflow.relocation import relocate_project
from .stock_operations import CATEGORY_LAYOUT
from .train_factory import validate_template
from .tools import sha
from .zero_operations.vehicle_catalogs import lookup, validate_graph


Selection = Annotated[dict[Name, Id], Field(max_length=1000)]


class ImportNativeStock(ProjectSave):
    source_project: Inventory
    donor_depot: Source | None = None
    donor_trains: Source | None = None
    formations: Selection = Field(default_factory=dict)
    engines: Selection = Field(default_factory=dict)
    categories: Selection = Field(default_factory=dict)
    existing: Literal['require_identical', 'reject'] = 'require_identical'
    target_scope: Literal['archive_increment', 'pre_service_project'] = 'archive_increment'

    @model_validator(mode='after')
    def selected_archives(self):
        if not (self.formations or self.engines or self.categories):
            raise ValueError('Select at least one native Formation, Engine or Category')
        if bool(self.engines or self.formations) != bool(self.donor_depot):
            raise ValueError('A SHA-bound donor Depot is required for Engines and Formations')
        if bool(self.categories or self.formations) != bool(self.donor_trains):
            raise ValueError('A SHA-bound donor TrainList is required for Categories and Formations')
        if self.target_scope == 'pre_service_project' and self.target_directory is None:
            raise ValueError('Previewing or saving the complete native project requires its fresh target_directory')
        return self


def categories(root):
    need(root.contents[0].value == 17, 'TrainList must use current format 17')
    records = c.array(root.contents[1].value)
    for record in records:
        c.shape(record, 'OTTrainCategory', 19, CATEGORY_LAYOUT)
    return lookup(records, 1, 'Category name')


def donor_train_list(root):
    c.shape(root, 'OTTrainList', 3, ['i', '@', '@', '@'])
    marker = root.contents[0].value
    if marker == 17:
        return lookup(c.train_items(root), 0, 'Formation name'), categories(root), False
    need(marker == 16, 'Use current TrainList marker17 or the observed legacy marker16')
    category_rows, _, formation_rows = [c.array(slot.value) for slot in root.contents[1:]]
    return lookup(formation_rows, 0, 'Formation name'), lookup(category_rows, 1, 'Category name'), True


def rename(record, slot, name):
    if text(record, slot) != name:
        cf.settext(record, slot, name)


def import_selection(current, donor, selected, slot, label, policy, copy_record):
    need(selected.keys() <= donor.keys(), f'Unknown selected native {label} name')
    used = {name.casefold() for name in current}
    target_names = {name.casefold() for name in selected.values()}
    need(len(target_names) == len(selected), f'Donor {label} selections resolve to the same destination name')
    added, reused = [], []
    for source, target in selected.items():
        record = copy_record(donor[source])
        rename(record, slot, target)
        if target in current:
            need(policy == 'require_identical' and w.fingerprint(current[target]) == w.fingerprint(record),
                 f'Destination {label} already exists with this name. Select a fresh alias or an exact match: {target}')
            reused.append(target)
            continue
        need(target.casefold() not in used, f'Destination {label} name differs only by case: {target}')
        used.add(target.casefold())
        current[target] = record
        added.append(target)
    return {'added': added, 'reused_identical': reused}


def copy_validated(record):
    validate_graph(record)
    return cf.clone(record)


def validate_formation_numbers(formation):
    average = formation.contents[1].values[2]
    if (isinstance(average, w.WireFloat) and average.encoding == b'f'
            and int.from_bytes(average.bits, average.byte_order) == 0xffc00000):
        # Original Demo/Training leave the cached average unset. The active formula at
        # 0x6c1838 uses the saved deceleration table and never reads this cache.
        diagram = c.array(formation.contents[2].values[0].contents[0].value)
        need(formation.contents[12].values[0] == 0 and diagram,
             'The original unset average deceleration needs an active saved braking table')
        probe = copy(formation)
        probe.contents = list(formation.contents)
        group = formation.contents[1]
        probe.contents[1] = w.TypedGroup(group.encodings, [*group.values[:2], 0.0])
        finite(probe)
    else:
        finite(formation)


def import_stock(plan, donor_depot, donor_trains, args):
    depot = plan.roots[plan.roles['depot']]
    trains = plan.roots[plan.roles['trains']]
    parents = trains.contents[1].value, trains.contents[3].value
    counts = incoming_counts(trains)
    need(not incoming_counts(depot).get(id(depot)) and all(counts[id(parent)] == 1 for parent in parents),
         'Target Depot and TrainList arrays must have exclusive ownership')
    known_engines = lookup(c.engine_items(depot), 1, 'Engine name')
    known_trains = lookup(c.train_items(trains), 0, 'Formation name')
    known_categories = categories(trains)
    source_engines = lookup(c.engine_items(donor_depot), 1, 'Engine name') if donor_depot is not None else {}
    source_trains, source_categories, legacy = donor_train_list(donor_trains) if donor_trains is not None else ({}, {}, False)
    engine_names, category_names = dict(args.engines), dict(args.categories)
    need(args.formations.keys() <= source_trains.keys(), 'Unknown selected native Formation name')
    for name in args.formations:
        formation = source_trains[name]
        if legacy:
            formation = source_trains[name] = upgrade_train(formation)
        refs, _ = validate_template(formation)
        summary(formation, source_engines)
        for ref in refs:
            engine = text(ref, 0)
            engine_names.setdefault(engine, engine)
        category = text(formation, 3)
        category_names.setdefault(category, category)

    if legacy:
        need(category_names.keys() <= source_categories.keys(), 'Unknown selected native Category name')
        for name in category_names:
            source_categories[name] = upgrade_category(source_categories[name])
    engine_result = import_selection(known_engines, source_engines, engine_names, 1, 'Engine',
                                     args.existing, copy_validated)
    category_result = import_selection(known_categories, source_categories, category_names, 1, 'Category',
                                       args.existing, copy_validated)

    def copy_formation(original):
        refs, _ = validate_template(original)
        validate_formation_numbers(original)
        result = cf.clone(original)
        rename(result, 3, category_names[text(original, 3)])
        imported_refs = []
        for engine in refs:
            reference = cf.clone(engine)
            rename(reference, 0, engine_names[text(engine, 0)])
            imported_refs.append(reference)
        array = cf.clone(original.contents[2].values[1])
        w.set_elements(array, imported_refs)
        result.contents[2].values[1] = array
        return result

    formation_result = import_selection(known_trains, source_trains, args.formations, 0, 'Formation',
                                        args.existing, copy_formation)
    for target in args.formations.values():
        formation = known_trains[target]
        need(text(formation, 3) in known_categories, 'Imported Formation lacks its Category')
        summary(formation, known_engines)
    w.set_elements(depot, list(known_engines.values()))
    w.set_elements(parents[0], list(known_categories.values()))
    w.set_elements(parents[1], list(known_trains.values()))
    return {
        'formation_mapping': args.formations, 'engine_mapping': engine_names, 'category_mapping': category_names,
        'formations': formation_result, 'engines': engine_result, 'categories': category_result,
        'legacy_class_upgrades': ({'source_train_list_marker': 16,
            'formations_train12_to_train16': list(args.formations),
            'categories_11_to_19': list(category_names),
            'trailer2_to_trailer3_delta_power_default_kw_per_t': 0.0,
            'formation_positions': 'consecutive engine array order then trailer array order'} if legacy else None),
        'formation_summaries': [summary(known_trains[target], known_engines) for target in list(args.formations.values())[:20]],
    }


def validate_saved_stock(depot_blob, trains_blob):
    depot, _ = w.load_next_compatible(depot_blob)
    trains, _ = w.load_next_compatible(trains_blob)
    engines = lookup(c.engine_items(depot), 1, 'Engine name')
    formations = lookup(c.train_items(trains), 0, 'Formation name')
    category_rows = categories(trains)
    conflicts = c.array(trains.contents[2].value)
    for row in conflicts:
        c.shape(row, 'OTConflictCategory', 0, ['iii', '@', '@'])
    for row in (*engines.values(), *category_rows.values(), *conflicts):
        validate_graph(row)
    checked = []
    for name, row in formations.items():
        category = text(row, 3)
        need(category in category_rows, 'Saved Formation references an unknown category: ' + name)
        body = summary(row, engines)
        validate_formation_numbers(row)
        checked.append({'name': name, 'category': category, 'engine_array_order': body['engine_array_order'],
                        'length_m': body['length_m']})
    return {'engines': sorted(engines), 'categories': sorted(category_rows), 'formations': checked,
            'conflict_category_count': len(conflicts)}


class NativeRollingStockImport(OperatingPlanEditTools):
    def pre_service_candidate(self, args, state, selected, target, original, changed, report):
        run = args.source_project.run_file
        roles = original['catalog_paths']
        expected_changes = {roles['depot'], roles['trains']}
        need(changed.keys() <= expected_changes, 'A pre-service stock import may change only Depot and TrainList')
        sources = {name: sha(data) for name, data in selected.items()}
        draft = {**selected, **changed}
        moved, relocation = relocate_project(
            draft, source_root=state['root'], target_root=target.as_posix(), run_file=run,
            expected_hashes={name: sha(data) for name, data in draft.items()},
            output_directory=original['output_directory'], project_type=EditableItineraryProject,
        )
        preserved = {name: digest for name, digest in sources.items()
                     if name not in expected_changes | {run, roles['dest']} and name not in relocation['diagrams']}
        need(all(sha(moved[name]) == digest for name, digest in preserved.items()),
             'The stock import changed a worksheet, StationFile or another preserved member')
        cold = validate_pre_service_project(moved, run_file=run, execution_root=target.as_posix())
        stock = validate_saved_stock(moved[roles['depot']], moved[roles['trains']])
        need(cold['station_model_bindings'] == original['station_model_bindings']
             and cold['destination_count'] == original['destination_count'],
             'Native StationFile or DestInfo binding changed while constructing the fresh stock project')
        result = {
            **report, 'preview_only': args.preview_only, 'saved': False, 'publication_review_pending': True,
            'target_scope': args.target_scope, 'run_member': run, 'native_application_executed': False,
            'native_runtime_ready': False, 'source_project': self.source_receipt(args, state),
            'selected_source_sha256': sources, 'member_sha256': {name: sha(data) for name, data in moved.items()},
            'preserved_member_sha256': preserved, 'changed_stock_members': sorted(changed),
            'pre_service_validation': cold, 'saved_stock_validation': stock, 'relocation': relocation,
        }
        recheck = lambda: self.recheck(state)
        recheck()
        if args.preview_only:
            return result
        return publish_candidate(self, target, moved, result, recheck)

    def import_rolling_stock(self, args):
        state = self.load_operating_project(args)
        selected, target, pre_service = None, None, None
        if args.target_scope == 'pre_service_project':
            target = project_target(self, args)
            if (state['root'] != state['base'].as_posix() or target.is_relative_to(state['base'])
                    or state['base'].is_relative_to(target)):
                raise APIError('PRE_SERVICE_STOCK_TARGET', 'Use the exact source execution root and a separate fresh project target')
            selected = {name: state['files'][name] for name in state['selected']}
            try:
                pre_service = validate_pre_service_project(selected, run_file=args.source_project.run_file,
                                                           execution_root=state['root'])
            except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
                raise APIError('PRE_SERVICE_STOCK_INVALID', 'The source is outside the verified construction project scope',
                               str(exc)[:600]) from exc
        originals, paths = {}, {}
        for role, source in [('depot', args.donor_depot), ('trains', args.donor_trains)]:
            if source is None:
                continue
            path = self.path(source.path)
            raw = self.secure_bytes(path)
            if path.suffix.lower() != f'.{role}' or sha(raw) != source.sha256:
                raise APIError('NATIVE_STOCK_SOURCE', f'Use a native .{role} archive matching its supplied SHA-256')
            if path in state['inputs'] and raw != state['inputs'][path]:
                raise APIError('SOURCE_CHANGED', 'Stock donor changed after its target project snapshot')
            paths[path] = raw
            originals[role] = raw
        try:
            roots = {role: w.load_next_compatible(raw)[0] for role, raw in originals.items()}
            changed, report = operating_candidate(state, args.source_project.run_file,
                lambda plan: import_stock(plan, roots.get('depot'), roots.get('trains'), args))
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_STOCK_IMPORT_INVALID', str(exc)[:700]) from exc
        state['inputs'].update(paths)
        report['donor_archives'] = {role: {'path': source.path, 'sha256': source.sha256}
            for role, source in [('depot', args.donor_depot), ('trains', args.donor_trains)] if source is not None}
        if pre_service is not None:
            try:
                return self.pre_service_candidate(args, state, selected, target, pre_service, changed, report)
            except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
                raise APIError('PRE_SERVICE_STOCK_INVALID', 'Could not validate the fresh stock construction project',
                               str(exc)[:600]) from exc
        return self.publish_operating_increment(args, state, changed, report)


def tool_definitions(root):
    service = NativeRollingStockImport(root)
    return [('opentrack_import_native_rolling_stock_archives',
             'Merge selected native formations, Engines and Categories from SHA-bound .trains and .depot files. '
             'Carries dependencies and the exact Engine2 efficiency table, supports aliases, and upgrades '
             'the observed Demo and Training legacy Train12, Trailer2 and Category11 using original decoder defaults. '
             'Default archive increment or explicitly publish a complete pre-service project with no Courses or timetable rows.',
             ImportNativeStock, service.import_rolling_stock, False, False)]
