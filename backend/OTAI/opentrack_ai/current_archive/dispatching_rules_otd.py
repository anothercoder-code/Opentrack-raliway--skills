"""Generate the original external OTD dispatching-rules XML for reviewed Routes."""

import json
from typing import Annotated, Literal
from xml.etree import ElementTree as xml

from pydantic import Field, StrictInt, StrictStr, model_validator

from ..errors import APIError
from . import writer
from .bundle_tools import CourseBundles, Source
from .multi_document.core import Project, ident, need
from .next_tools import NextFunctions, Ordinal
from .project_candidate_publication import ProjectSave, project_target, require_external_target
from .tools import Input, sha
from .windows_publish import publish_project


Label = Annotated[StrictStr, Field(pattern=r'^[!-~](?:[ -~]{0,198}[!-~])?$')]
Metres = Annotated[StrictInt, Field(ge=0, le=100000)]
XML_FILE = 'dispatching-rules.xml'
LAUNCH_FILE = 'launch-manifest.json'
LAUNCH_FORMAT = 'opentrack-dispatching-rules-otd-v1'
XML_LIMIT = 8 * 1024 * 1024
PROLOGUE = b'<?xml version="1.0" encoding="ISO-8859-1"?>\n<!DOCTYPE otd SYSTEM "otd.dtd">\n'


class RuleRoute(Input):
    document: Label
    start_end_id: Ordinal
    route_name: Label

    def key(self):
        return self.document, self.start_end_id, self.route_name


class RuleCondition(Input):
    route: RuleRoute
    reservation: Literal['reserved', 'free'] | None = None
    minimum_length_m: Metres | None = None
    stop_code: Literal['unplannedStop', 'extendedDwell'] | None = None
    extended_dwell_s: Annotated[float, Field(gt=0, le=604800, allow_inf_nan=False)] | None = None

    @model_validator(mode='after')
    def valid_condition(self):
        if sum(value is not None for value in (self.reservation, self.minimum_length_m, self.stop_code)) > 1:
            raise ValueError('Choose one original condition mode: reservation, train length or stop')
        if (self.stop_code == 'extendedDwell') != (self.extended_dwell_s is not None):
            raise ValueError('Extended dwell requires one explicit dwell threshold in seconds')
        return self


class ConditionalRule(Input):
    kind: Literal['conditions']
    conditions: Annotated[list[RuleCondition], Field(min_length=1, max_length=256)]


class CapacityRule(Input):
    kind: Literal['capacity']
    maximum_other_trains: Annotated[StrictInt, Field(ge=0, le=10000)]
    reserved_routes: Annotated[list[RuleRoute], Field(min_length=1, max_length=256)]


Rule = Annotated[ConditionalRule | CapacityRule, Field(discriminator='kind')]


class RuleSet(Input):
    name: Label
    applies_to: Annotated[list[RuleRoute], Field(min_length=1, max_length=512)]
    rules: Annotated[list[Rule], Field(min_length=1, max_length=128)]


class WriteDispatchingRules(ProjectSave):
    project_run: Source
    documents: Annotated[dict[Label, Source], Field(min_length=1, max_length=100)]
    route_id_mode: Literal['compound', 'route_name'] = 'compound'
    rule_sets: Annotated[list[RuleSet], Field(min_length=1, max_length=128)]


class RuleProject(Input):
    project_run: Source
    documents: Annotated[dict[Label, Source], Field(min_length=1, max_length=100)]


class InspectDispatchingRules(RuleProject):
    source_manifest: Source


class ExactRuleRoute(RuleRoute):
    array_id: Ordinal


class RuleRouteRebinding(Input):
    old: ExactRuleRoute
    new: ExactRuleRoute


class RebindDispatchingRules(ProjectSave):
    source_manifest: Source
    original: RuleProject
    candidate: RuleProject
    route_rebindings: Annotated[list[RuleRouteRebinding], Field(max_length=2000)] = Field(default_factory=list)


def route_ids(project, mode):
    ids, by_id = {}, {}
    for route in project.routes:
        owner = project.owners[id(route)]
        if writer.kind(project.model(owner)) != 'OTEndModel':
            continue
        name = ident(route)[0]
        first = project.route_view(route)[0]
        need(first == owner, 'The main Route stored owner does not equal its start')
        key = *owner, name
        route_id = name if mode == 'route_name' else f'{owner[0]}-{owner[1]}-{name}'
        need(key not in ids and route_id not in by_id, f'Ambiguous native OTD Route ID: {route_id}')
        ids[key] = route_id
        by_id[route_id] = key
    return ids


def _condition_attributes(rule, resolve):
    if isinstance(rule, CapacityRule):
        selected = [resolve(row) for row in rule.reserved_routes]
        need(len(set(selected)) == len(selected), 'A capacity rule lists one Route more than once')
        return [{'routeID': route_id} for route_id in selected]
    entries = []
    for condition in rule.conditions:
        fields = {'routeID': resolve(condition.route)}
        if condition.reservation is not None:
            fields['routeReservationState'] = condition.reservation
        if condition.minimum_length_m is not None:
            fields['minimalLength'] = str(condition.minimum_length_m)
        if condition.stop_code is not None:
            fields['stopCode'] = condition.stop_code
        if condition.extended_dwell_s is not None:
            fields['extendedDwellTime'] = str(condition.extended_dwell_s)
        need(fields not in entries, 'Duplicate condition in one exclusion rule')
        entries.append(fields)
    return entries


def dispatching_rules(project, rule_sets, mode):
    total = sum(len(rule.conditions) if isinstance(rule, ConditionalRule) else len(rule.reserved_routes)
                for rule_set in rule_sets for rule in rule_set.rules)
    need(total <= 16000, 'An OTD XML bundle permits at most 16000 condition references')
    discovered = route_ids(project, mode)

    def resolve(reference):
        key = reference.key()
        need(key in discovered, f'OTD reference does not identify a saved main Route: {key}')
        identifier = discovered[key]
        need(identifier.isascii() and identifier.isprintable(), 'Selected OTD Route ID requires printable ASCII')
        return identifier

    root = xml.Element('otd')
    definitions = xml.SubElement(root, 'routeRuleSets')
    assignments = xml.SubElement(root, 'routes')
    names, applied, plan = set(), set(), []
    for rule_set in rule_sets:
        need(rule_set.name not in names, f'Duplicate OTD ruleset: {rule_set.name}')
        names.add(rule_set.name)
        definition = xml.SubElement(definitions, 'routeRuleSet', id=rule_set.name)
        for rule in rule_set.rules:
            properties = {'maximalNumberOfTrains': str(rule.maximum_other_trains)} if isinstance(rule, CapacityRule) else {}
            node = xml.SubElement(definition, 'routeExclusionRule', properties)
            for attributes in _condition_attributes(rule, resolve):
                xml.SubElement(node, 'routeExclusionCondition', attributes)
        assigned = []
        for reference in rule_set.applies_to:
            route_id = resolve(reference)
            need(route_id not in applied, f'The Route can belong to only one OTD ruleset: {route_id}')
            applied.add(route_id)
            assigned.append(route_id)
            xml.SubElement(assignments, 'route', id=route_id, routeRuleSetID=rule_set.name)
        plan.append({'name': rule_set.name, 'applies_to': assigned, 'rule_count': len(rule_set.rules)})
    xml.indent(root, space='\t')
    blob = PROLOGUE + xml.tostring(root, encoding='iso-8859-1', xml_declaration=False) + b'\n'
    need(len(blob) <= XML_LIMIT, 'Generated OTD XML exceeds the tool limit')
    need(xml.tostring(xml.fromstring(blob)) == xml.tostring(root), 'OTD XML readback differs from the reviewed graph')
    return blob, plan


def _launch_manifest(project_args, scope, mode, blob, target, rules):
    rules_path = XML_FILE if target is None else (target / XML_FILE).as_posix()
    need('=' not in rules_path, 'The original dispatching-rules file option cannot contain an equals sign in its path')
    options = ['-dispatchingrules', f'-dispatchingrulesfile={rules_path}']
    if mode == 'route_name':
        options.append('-routeidtype=routename')
    return {'format': LAUNCH_FORMAT, 'route_id_mode': mode,
            'original_startup_options': options, 'use_with_project_run': project_args.project_run.model_dump(),
            'document_sources': {key: source.model_dump() for key, source in project_args.documents.items()},
            'document_scope': scope, 'rule_sets': rules, 'xml_sha256': sha(blob), 'xml_bytes': len(blob),
            'launch_path_is_relative_to_bundle': target is None, 'native_app_verified': False}


def rebound_rule_plan(blob):
    definitions, assignments = xml.fromstring(blob)
    assigned = {item.attrib['id']: [] for item in definitions}
    for entry in assignments:
        assigned[entry.attrib['routeRuleSetID']].append(entry.attrib['id'])
    return [{'name': item.attrib['id'], 'applies_to': assigned[item.attrib['id']], 'rule_count': len(item)}
            for item in definitions]


class DispatchingRuleTools(NextFunctions, CourseBundles):
    def _publish_rules(self, args, target, blob, receipt, recheck):
        if args.preview_only:
            recheck()
            return {**receipt, 'preview_only': True, 'saved': False}
        members = {XML_FILE: blob, LAUNCH_FILE: (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode()}

        def validate(saved):
            if saved != members or xml.fromstring(saved[XML_FILE]).tag != 'otd':
                raise APIError('CURRENT_DISPATCHING_RULES_OTD', 'Published OTD XML or launch manifest failed readback')

        published = publish_project(self.root, target, members, recheck=recheck, validate_bundle=validate, empty_directories=())
        return {**receipt, 'preview_only': False, 'saved': True, 'publication': published}

    def write_rules(self, args):
        inputs = {name: self.checked(source) for name, source in args.documents.items()}
        run_path, run, scope_check, scope = self.checked_document_list(args, inputs)
        target = project_target(self, args)
        require_external_target(target, run_path.parent)
        files = {path: data for path, data, _, _ in inputs.values()}
        files[run_path] = run

        def recheck():
            scope_check()
            if any(self.secure_bytes(path) != data for path, data in files.items()):
                raise APIError('SOURCE_CHANGED', 'An OTD Route source changed before publication')

        try:
            project = Project({key: item[1] for key, item in inputs.items()},
                              document_paths={key: item[0].as_posix() for key, item in inputs.items()},
                              expected_hashes={key: source.sha256 for key, source in args.documents.items()},
                              complete_document_set=True)
            blob, plan = dispatching_rules(project, args.rule_sets, args.route_id_mode)
            receipt = _launch_manifest(args, scope, args.route_id_mode, blob, target, plan)
        except (TypeError, ValueError, IndexError, KeyError, OverflowError) as exc:
            raise APIError('CURRENT_DISPATCHING_RULES_OTD', str(exc)[:500]) from exc
        return self._publish_rules(args, target, blob, receipt, recheck)

    @staticmethod
    def _rule_project(inputs):
        from .itinerary_edit_tools import EditableItineraryProject

        return EditableItineraryProject(
            {name: item[1] for name, item in inputs.items()},
            document_paths={name: item[0].as_posix() for name, item in inputs.items()},
            expected_hashes={name: sha(item[1]) for name, item in inputs.items()}, complete_document_set=True)

    def _rule_source(self, manifest, run_path, run_bytes, inputs):
        from ..native_execution import OTD_MANIFEST_LIMIT, bind_dispatching_rules

        source_path = self.path(manifest.path)
        need(source_path.name == LAUNCH_FILE, f'Select an exported {LAUNCH_FILE}')
        xml_path = self.path((source_path.parent / XML_FILE).relative_to(self.root).as_posix())
        manifest_raw, rules = self.secure_bytes(source_path), self.secure_bytes(xml_path)
        need(0 < len(manifest_raw) <= OTD_MANIFEST_LIMIT and 0 < len(rules) <= XML_LIMIT,
             'Source OTD manifest or XML is empty or exceeds its bound size')
        members = {path.relative_to(run_path.parent).as_posix(): data for path, data, _, _ in inputs.values()}
        members[run_path.name] = run_bytes
        bound = bind_dispatching_rules(self.root, run_path.parent, run_path.name, members,
                                       manifest.model_dump(), {LAUNCH_FILE: manifest_raw, XML_FILE: rules})
        return rules, bound, [(source_path, manifest_raw), (xml_path, rules)]

    def inspect_rules(self, args):
        from .saved_dispatching_rule_rebinding import dispatching_rule_route_bindings

        inputs = {name: self.checked(source) for name, source in args.documents.items()}
        run_path, run_bytes, scope_check, _ = self.checked_document_list(args, inputs)
        try:
            rules, bound, sources = self._rule_source(args.source_manifest, run_path, run_bytes, inputs)
            routes = dispatching_rule_route_bindings(rules, self._rule_project(inputs), bound['route_id_mode'])
        except (TypeError, ValueError, IndexError, KeyError, OverflowError) as exc:
            raise APIError('CURRENT_DISPATCHING_RULES_OTD', str(exc)[:500]) from exc
        scope_check()
        sources.append((run_path, run_bytes))
        sources.extend((item[0], item[1]) for item in inputs.values())
        if any(self.secure_bytes(path) != data for path, data in sources):
            raise APIError('SOURCE_CHANGED', 'An OTD dependency changed during inspection')
        return {**bound, 'route_bindings': routes}

    def rebind_rules(self, args):
        from .saved_dispatching_rule_rebinding import rebind_dispatching_rule_routes

        original_inputs = {name: self.checked(source) for name, source in args.original.documents.items()}
        candidate_inputs = {name: self.checked(source) for name, source in args.candidate.documents.items()}
        original_run, original_raw, original_check, _ = self.checked_document_list(args.original, original_inputs)
        candidate_run, candidate_raw, candidate_check, scope = self.checked_document_list(args.candidate, candidate_inputs)
        target = project_target(self, args)
        require_external_target(target, original_run.parent)
        require_external_target(target, candidate_run.parent)

        try:
            rules, bound, sources = self._rule_source(args.source_manifest, original_run, original_raw, original_inputs)
            mode = bound['route_id_mode']
            blob, reviewed = rebind_dispatching_rule_routes(
                rules, self._rule_project(original_inputs), self._rule_project(candidate_inputs), mode,
                [row.model_dump() for row in args.route_rebindings])
            receipt = _launch_manifest(args.candidate, scope, mode, blob, target, rebound_rule_plan(blob))
            receipt.update(rebound_from=bound['manifest_source'], source_xml_sha256=bound['xml_sha256'],
                           route_rebindings=reviewed)
        except (TypeError, ValueError, IndexError, KeyError, OverflowError, xml.ParseError) as exc:
            raise APIError('CURRENT_DISPATCHING_RULES_OTD', str(exc)[:500]) from exc

        sources.extend([(original_run, original_raw), (candidate_run, candidate_raw)])
        sources.extend((item[0], item[1]) for data in (original_inputs, candidate_inputs) for item in data.values())

        def recheck():
            original_check()
            candidate_check()
            if any(self.secure_bytes(path) != original for path, original in sources):
                raise APIError('SOURCE_CHANGED', 'An OTD dependency changed before candidate publication')

        return self._publish_rules(args, target, blob, receipt, recheck)


def tool_definitions(root):
    service = DispatchingRuleTools(root)
    return [('opentrack_write_dispatching_rules_otd',
             'Write original external OTD interlocking-rule XML and startup options for exact saved main Routes. '
             'Supports reservation, minimum length, stop, dwell and counted-train exclusion rules. No native execution.',
             WriteDispatchingRules, service.write_rules, False, False),
            ('opentrack_inspect_dispatching_rule_bindings',
             'Resolve an exact project-bound native OTD XML file to main Route identities and occupied resources.',
             InspectDispatchingRules, service.inspect_rules),
            ('opentrack_rebind_dispatching_rules_otd',
             'Rebind all reviewed native OTD assignments and exclusion predicates from their original complete project '
             'to a different complete route graph, then publish XML and a candidate-bound launch manifest.',
             RebindDispatchingRules, service.rebind_rules, False, False)]
