"""Publish one native station candidate from a reviewed movement replacement bundle."""

import json
from typing import Annotated

from pydantic import Field, StrictBool, StrictInt

from ..errors import APIError
from ..json_safe import checked_json
from ..native_execution import bind_dispatching_rules, child_path, reset_copied_actuals
from ..simulation_evidence import Control
from .bundle_tools import Source
from .dispatching_rules_otd import (
    LAUNCH_FILE, XML_FILE, DispatchingRuleTools, RuleProject, RuleRouteRebinding,
    _launch_manifest, rebound_rule_plan,
)
from .itinerary_edit_tools import EditableItineraryProject, run_infrastructure_paths
from .movement_application_tools import MovementApplicationTools, PrepareMovementApplication
from .multi_document_tools import Inventory, MultiDocumentTools
from .native_result_tools import EvaluateNativeRun
from .native_run_evaluation import plan as evaluation_plan
from .prepare_contract import preflight
from .project_candidate_publication import ProjectSave, project_target
from .project_workflow.relocation import relocate_project
from .runfile_parameters import edit_runfile
from .saved_dispatching_rule_rebinding import rebind_dispatching_rule_routes
from .tools import Input, PathText, sha
from .windows_publish import publish_project


class CandidateRuleReview(Input):
    source_manifest: Source
    route_rebindings: Annotated[list[RuleRouteRebinding], Field(max_length=2000)] = Field(default_factory=list)


class CandidateSimulation(Input):
    job_directory: PathText
    scenarios: Annotated[list[StrictInt], Field(min_length=1, max_length=1000)] | None = None
    timeout_s: Annotated[StrictInt, Field(ge=1, le=86400)] = 180
    expectations: dict | None = None
    record_instruments: StrictBool = False


class PrepareStationCandidate(ProjectSave):
    source_project: Inventory
    bundle_manifest: Source
    target_directory: PathText
    dispatching_rules: CandidateRuleReview | None = None
    simulation: CandidateSimulation | None = None


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _metadata(data):
    return {name: {'sha256': sha(blob), 'bytes': len(blob)} for name, blob in sorted(data.items())}


def _json(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


class StationCandidateTools(MultiDocumentTools):
    def _source(self, path, content):
        return Source(path=path.relative_to(self.root).as_posix(), sha256=sha(content))

    def _preflight(self, target, run_name, files):
        prefix = target.as_posix() + '/'

        def read(path):
            _require(path.startswith(prefix), f'Candidate input is outside its publication root: {path}')
            return files[path[len(prefix):]]

        report = preflight.check(files[run_name], read)
        _require(report['passed_static_subset'], f'Candidate saved-data preflight failed: {report["errors"]}')
        return report

    def _rules(self, review, state, target, run_name, files, source_graph):
        old_run = state['base'] / run_name
        documents = {name: (state['base'] / member, state['files'][member], None, None)
                     for name, member in state['document_members'].items()}
        service = DispatchingRuleTools(self.root)
        old_xml, binding, dependencies = service._rule_source(review.source_manifest, old_run, state['run'], documents)
        paths = run_infrastructure_paths(files[run_name])
        native_docs = {name: files[member] for name, member in state['document_members'].items()}
        revised = EditableItineraryProject(native_docs, document_paths=paths,
                                           expected_hashes={name: sha(data) for name, data in native_docs.items()},
                                           complete_document_set=True)
        revised.check_dest_catalog(files[state['roles']['dest']])
        mode = binding['route_id_mode']
        xml, changes = rebind_dispatching_rule_routes(
            old_xml, source_graph, revised, mode, [item.model_dump() for item in review.route_rebindings])
        args = RuleProject(project_run=self._source(target / run_name, files[run_name]),
                           documents={name: self._source(target / member, files[member])
                                      for name, member in state['document_members'].items()})
        rules_directory = target / 'otd-rules'
        scope = {'project_root': target.relative_to(self.root).as_posix(),
                 'inventory_paths': [entry.path for entry in args.documents.values()]}
        manifest = _launch_manifest(args, scope, mode, xml, rules_directory, rebound_rule_plan(xml))
        manifest.update(rebound_from=binding['manifest_source'], source_xml_sha256=binding['xml_sha256'],
                        route_rebindings=changes)
        raw = _json(manifest)
        reference = self._source(rules_directory / LAUNCH_FILE, raw).model_dump()
        outputs = {f'otd-rules/{XML_FILE}': xml, f'otd-rules/{LAUNCH_FILE}': raw}
        return outputs, reference, dependencies

    def _simulation(self, request, target, run_name, hashes, rules, protected):
        job = child_path(self.root, self.path(request.job_directory).relative_to(self.root).as_posix())
        _require(not any(job.is_relative_to(path) or path.is_relative_to(job) for path in (target, *protected))
                 and not job.exists() and job.as_posix().isascii(),
                 'Use a fresh ASCII native job directory separate from source and candidate files')
        _require(not rules or '=' not in job.as_posix(), 'The original OTD job path cannot contain an equals sign')
        _require(request.scenarios is None or (len(set(request.scenarios)) == len(request.scenarios)
                 and all(-1 <= value <= 2147483647 for value in request.scenarios)),
                 'Use distinct original delay scenarios of -1 or higher')
        if request.expectations is not None:
            _require(not {'output_directory', 'evidence_directory'} & request.expectations.keys(),
                     'Native outcome directories are assigned by the execution job')
            expectations = EvaluateNativeRun.model_validate({
                **request.expectations, 'output_directory': (target / 'output').relative_to(self.root).as_posix(),
            })
            evaluation_plan(expectations.model_dump(exclude_none=True))
        start = Control(action='start', project_directory=target.relative_to(self.root).as_posix(),
                        run_file=run_name, job_directory=job.relative_to(self.root).as_posix(),
                        source_sha256=hashes, dispatching_rules=rules, scenarios=request.scenarios,
                        timeout_s=request.timeout_s, expectations=request.expectations)
        return start.model_dump(exclude_none=True)

    def prepare(self, args):
        target = project_target(self, args)
        state = self.load_project(args.source_project, minimum_documents=1)
        run_name = args.source_project.run_file
        _require(state['root'] == state['base'].as_posix(), 'Use the original run at its actual execution root')
        bundle = self.path(args.bundle_manifest.path).parent
        if any(target.is_relative_to(path) or path.is_relative_to(target) for path in (state['base'], bundle)):
            raise APIError('STATION_CANDIDATE_SCOPE', 'Use a fresh target outside the original project and replacement bundle')

        run_source = self._source(state['base'] / run_name, state['run'])
        manifest = json.loads(self.secure_bytes(self.path(args.bundle_manifest.path)))
        if isinstance(manifest, dict) and manifest.get('format') == 'opentrack-operating-plan-increment-v1':
            # Imported here because native_editor_tools imports this module.
            from .native_editor_tools import NativeEditorTools
            updated, recheck_bundle = NativeEditorTools(self.root)._bundle(args.bundle_manifest, state, run_name)
            replacements = {state['base'] / relative: data for relative, data in updated.items()}
            application = {'run': run_source.model_dump(), 'replacements': [
                {'project_file': (state['base'] / relative).relative_to(self.root).as_posix(),
                 'before_sha256': sha(state['files'][relative]), 'after_sha256': sha(data)}
                for relative, data in updated.items()]}
        else:
            app = MovementApplicationTools(self.root)
            application, _, replacements, recheck_bundle, _ = app.review(PrepareMovementApplication(
                project_run=run_source, bundle_manifest=args.bundle_manifest))
        selected = {member: state['files'][member] for member in state['selected']}
        for path, data in replacements.items():
            relative = path.relative_to(state['base']).as_posix()
            if relative not in selected:
                raise APIError('STATION_CANDIDATE_SCOPE', 'A replacement is outside the selected native run', relative)
            selected[relative] = data

        dependencies, sidecars, rule_source = [], {}, None
        try:
            moved, _ = relocate_project(selected, source_root=state['root'], target_root=target.as_posix(),
                                        run_file=run_name, expected_hashes={name: sha(data) for name, data in selected.items()},
                                        project_type=EditableItineraryProject)
            timetable = state['roles']['timetable']
            moved[timetable], actual_rows_reset = reset_copied_actuals(moved[timetable])
            if args.simulation and args.simulation.record_instruments:
                moved[run_name] = edit_runfile(moved[run_name], {b'Show Instruments': b'1', b'Output Instruments': b'1'})
            static_check = self._preflight(target, run_name, moved)
            if args.dispatching_rules:
                original = self.project(state, EditableItineraryProject)
                sidecars, rule_source, dependencies = self._rules(
                    args.dispatching_rules, state, target, run_name, moved, original)
            hashes = {name: sha(data) for name, data in moved.items()}
            start = None
            if args.simulation:
                start = self._simulation(args.simulation, target, run_name, hashes, rule_source, (state['base'], bundle))
        except (IndexError, KeyError, OverflowError, TypeError, ValueError) as exc:
            raise APIError('STATION_CANDIDATE_INVALID', str(exc)[:700]) from exc

        report = {'format': 'opentrack-station-candidate-v1', 'source_bundle': args.bundle_manifest.model_dump(),
                  'source_project_run': application['run'], 'replacement_members': application['replacements'],
                  'candidate_project_directory': target.relative_to(self.root).as_posix(), 'run_file': run_name,
                  'project_sha256': hashes, 'copied_timetable_actual_rows_reset': actual_rows_reset,
                  'static_simulation_preflight': static_check,
                  'dispatching_rules': rule_source, 'native_start': start,
                  'native_application_started': False}
        files = {**moved, **sidecars, 'station-candidate.json': _json(report)}
        if start is not None:
            files['native-start.json'] = _json(start)

        def recheck():
            self.recheck(state)
            recheck_bundle()
            if any(self.secure_bytes(path) != data for path, data in dependencies):
                raise APIError('SOURCE_CHANGED', 'An original OTD input changed before candidate publication')

        def validate(actual):
            _require(actual == files, 'Published files differ from the reviewed candidate')
            native = {name: actual[name] for name in moved}
            self._preflight(target, run_name, native)
            if rule_source:
                bind_dispatching_rules(self.root, target, run_name, native, rule_source,
                                       {name: actual[f'otd-rules/{name}'] for name in (XML_FILE, LAUNCH_FILE)})

        validate(files)
        result = checked_json({**report, 'preview_only': args.preview_only, 'saved': False, 'files': _metadata(files)})
        recheck()
        if args.preview_only:
            return result
        publication = publish_project(self.root, target, files, recheck=recheck, validate_bundle=validate,
                                      empty_directories=('output',))
        return {**result, 'saved': True, 'publication': publication}


def tool_definitions(root):
    service = StationCandidateTools(root)
    return [('opentrack_prepare_station_run_candidate',
             'Apply a reviewed native movement bundle to a fresh complete station project, rebind optional OTD rules, '
             'and generate verified offline launch inputs without starting OpenTrack.',
             PrepareStationCandidate, service.prepare, False, False)]
