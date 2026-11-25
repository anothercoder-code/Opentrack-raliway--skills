"""Discover and control owned native jobs, or inspect existing protocol text."""
from collections import Counter
import hashlib
import math
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .current_archive.bundle_tools import Source

CATALOG_KEYS = ('DestInfoFile', 'DepotFile', 'TrainFile', 'CourseFile', 'StationFile', 'TimetableFile')
LIMIT = 10 * 1024 * 1024


class EvidenceError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class HeadwaySweep(Empty):
    leading_course_id: str = Field(min_length=1, max_length=200)
    following_course_id: str = Field(min_length=1, max_length=200)
    comparison_mode: Literal['same_itinerary', 'shared_fixed_block'] = 'same_itinerary'
    minimum_s: int = Field(default=1, ge=1, le=3600)
    maximum_s: int = Field(ge=1, le=3600)

    @model_validator(mode='after')
    def bounded_interval(self):
        if not self.minimum_s <= self.maximum_s < self.minimum_s + 600:
            raise ValueError('Choose a positive integer interval with at most 600 candidates')
        if self.leading_course_id == self.following_course_id:
            raise ValueError('Select two different Courses')
        return self


class Control(Empty):
    action: Literal['start', 'status', 'stop']
    mode: Literal['batch', 'interactive'] = 'batch'
    job_directory: str | None = None
    project_directory: str | None = None
    run_file: str | None = None
    executable: str = 'OpenTrack.app/OpenTrack.exe'
    source_sha256: dict[str, str] | None = None
    dispatching_rules: Source | None = None
    scenarios: list[int] | None = Field(default=None, min_length=1, max_length=1000)
    headway_sweep: HeadwaySweep | None = None
    timeout_s: int = Field(default=180, ge=1, le=86400)
    expectations: dict | None = None

    @model_validator(mode='after')
    def action_arguments(self):
        if self.job_directory is None:
            if self.model_fields_set - {'action'}:
                raise ValueError('A native job directory is required')
        elif self.action == 'start':
            if not self.project_directory or not self.run_file:
                raise ValueError('Starting a native job requires the source project and run file')
            if self.mode == 'interactive' and self.scenarios is not None and len(self.scenarios) != 1:
                raise ValueError('Interactive mode requires exactly one scenario')
            if self.headway_sweep is not None and (self.mode != 'batch' or self.scenarios not in (None, [0])):
                raise ValueError('Headway sweeps require batch mode and Delay Scenario 0')
        elif self.model_fields_set - {'action', 'job_directory'}:
            raise ValueError('Status and stop accept only the job directory')
        return self


class InspectEvidence(Empty):
    run_file: str = Field(min_length=1)
    protocol_file: str = Field(min_length=1)
    expected_course_ids: list[str] = Field(min_length=1, max_length=10000)

    @field_validator('expected_course_ids')
    @classmethod
    def unique_ids(cls, values):
        if any(not x or x != x.strip() or '\n' in x or '\r' in x for x in values):
            raise ValueError('Course IDs must be nonempty single-line exact identifiers')
        if len(values) != len(set(values)):
            raise ValueError('Expected course IDs must be unique')
        return values


class SimulationEvidence:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def _path(self, path):
        path = Path(path)
        path = (path if path.is_absolute() else self.root / path).resolve()
        if not path.is_relative_to(self.root):
            raise EvidenceError('PATH_OUTSIDE_SCOPE', 'Evidence must remain inside the configured root')
        return path

    def _read(self, path):
        path = self._path(path)
        if not path.is_file():
            raise EvidenceError('EVIDENCE_NOT_REGULAR_FILE', 'Evidence must be an existing regular file')
        with path.open('rb') as stream:
            data = stream.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise EvidenceError('EVIDENCE_TOO_LARGE', 'Evidence exceeds 10 MiB')
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise EvidenceError('EVIDENCE_ENCODING', 'Only verified UTF-8/ASCII text is supported') from exc
        return text, {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}

    def capabilities(self, args):
        import sys

        return {
            'state': 'available' if sys.platform == 'win32' else 'unsupported_host',
            'native_simulation_verified': False,
            'native_start': 'owned_original_script_job',
            'native_status': 'owned_job_state_and_current_worker_identity',
            'native_stop': 'request_cancellation_via_owned_child_handle',
            'available': ['inspect_existing_protocol_evidence', 'run_isolated_project',
                          'run_explicit_delay_scenarios', 'run_integer_headway_sweep', 'launch_owned_interactive_window',
                          'attach_reviewed_dispatching_rules'],
            'engine': 'Stock English OpenTrack 1.7 on Windows',
            'source_contract': 'Explicit .run and its selected, relocatable native archive closure',
            'interactive_controls': 'stock_simulation_window_after_owned_interactive_launch',
            'per_train_verification': 'requires explicit expected terminal events and bound new outputs',
        }

    def control(self, args):
        from . import native_execution

        if args.job_directory is None:
            return {'state': 'blocked', 'requested_action': args.action, 'executed': False,
                    'job_id': None, 'native_simulation_verified': False,
                    'reason_code': 'NATIVE_JOB_REQUIRED',
                    'reason': 'Select a job directory to start, inspect or stop an owned native job.'}
        try:
            if args.action == 'start':
                return native_execution.start(self.root, args)
            return native_execution.job_control(self.root, args)
        except (OSError, ValueError) as exc:
            raise EvidenceError('NATIVE_JOB_REJECTED', str(exc)) from exc

    def inspect(self, args):
        run_path = self._path(args.run_file)
        run_text, run_meta = self._read(run_path)
        parameters = {}
        for line in run_text.splitlines():
            if not line.strip() or line.startswith('//'):
                continue
            fields = line.split('#')
            if len(fields) != 3 or fields[2] != '' or (fields[0] in parameters and fields[0] in (*CATALOG_KEYS, 'OutputPath', 'Start Time', 'Stop Time', 'Step', 'Start Day Offset', 'Stop Day Offset')):
                raise EvidenceError('RUN_FORMAT', 'Expected key#value# records with unique simulation/catalog parameters')
            parameters[fields[0]] = fields[1]
        if not parameters.get('OutputPath'):
            raise EvidenceError('OUTPUT_NOT_CONFIGURED', 'Selected run has no OutputPath')
        output = Path(parameters['OutputPath'])
        output = self._path(output if output.is_absolute() else run_path.parent / output)
        protocol_path = self._path(args.protocol_file)
        if protocol_path.parent != output or not re.fullmatch(r'OT_Protocol\..+\.txt', protocol_path.name):
            raise EvidenceError('PROTOCOL_NOT_SELECTED_OUTPUT', 'Select an OT_Protocol.*.txt directly in the run OutputPath')
        text, protocol_meta = self._read(protocol_path)
        messages_path = self._path(output / 'OT_Messages.txt')
        message_text, message_meta = self._read(messages_path) if messages_path.is_file() else ('', None)
        # Duplicated headers are ambiguous rather than silently selecting the first.
        def one(pattern):
            matches = re.findall(pattern, text, re.M)
            return matches[0] if len(matches) == 1 else None
        catalog_matches = {}
        for key in CATALOG_KEYS:
            value = one(r'^' + key + r':([^\r\n]+)\r?$')
            expected = parameters.get(key)
            # No cross-platform path remapping is invented. Comparison is lexical,
            # not proof of matching catalog bytes at simulation time.
            catalog_matches[key] = bool(value and expected and value.strip().replace('\\', '/') == expected.replace('\\', '/'))
        window = one(r'^Simulation Time\s*:\s*(\d\d:\d\d:\d\d) - (\d\d:\d\d:\d\d)\s*$')
        step = one(r'^Simulation Step\s*:\s*([\d.]+)\s*$')
        try:
            actual_step = float(step) if step else None
            configured_step = float(parameters.get('Step', 'nan'))
            step_matches = bool(actual_step and math.isfinite(actual_step) and math.isfinite(configured_step) and math.isclose(actual_step, configured_step, rel_tol=1e-6, abs_tol=1e-6))
            days = [int(parameters.get(key, '0')) for key in ('Start Day Offset', 'Stop Day Offset')]
        except ValueError as exc:
            raise EvidenceError('RUN_OR_PROTOCOL_NUMERIC_FORMAT', 'Invalid Step or day offset') from exc
        used = None
        if text.count('Used Courses:') == 1 and text.count('Occupations:') == 1:
            before, after = text.split('Used Courses:', 1)
            if 'Occupations:' in after:
                used = [line.strip() for line in after.split('Occupations:', 1)[0].splitlines() if line.strip()]
        counts = Counter(used or [])
        expected = set(args.expected_course_ids)
        ids_match = used is not None and set(used) == expected and len(used) == len(expected)
        message_lines = [x.strip() for x in message_text.splitlines()]
        ended = 'End of Simulation' in message_lines
        canceled = 'Cancel Simulation' in message_lines
        window_matches = bool(window and tuple(window) == (parameters.get('Start Time'), parameters.get('Stop Time')))
        protocol_consistent = all(catalog_matches.values()) and window_matches and step_matches and not any(days) and ids_match and ended and not canceled
        rows = [{'course_id': course, 'listed_in_used_courses': None if used is None else course in counts,
                 'departure_observed': None, 'terminal_arrival_time': None, 'terminal_reached': None,
                 'canceled': None, 'interrupted': None} for course in args.expected_course_ids]
        return {'state': 'incomplete_evidence', 'goal_complete': False, 'native_simulation_verified': False,
                'evidence_level': 'existing_native_protocol_text_only',
                'files': {'run': run_meta, 'protocol': protocol_meta, 'messages': message_meta},
                'catalog_path_matches': catalog_matches, 'catalog_content_binding': 'unknown',
                'same_execution_binding': 'unknown', 'protocol_consistent_with_selected_run': protocol_consistent,
                'actual_clock_window': list(window) if window else None, 'window_matches': window_matches,
                'actual_step_s': actual_step, 'step_matches': step_matches, 'configured_day_offsets': days,
                'protocol_day_offset_evidence': 'unknown', 'full_24h_simulated': None,
                'expected_courses': len(expected), 'used_course_lines': used,
                'used_ids_match': ids_match,
                'missing_used_ids': sorted(expected - set(used)) if used is not None else None,
                'unexpected_used_ids': sorted(set(used) - expected) if used is not None else None,
                'duplicate_used_ids': sorted(k for k, count in counts.items() if count > 1),
                'end_marker_observed': ended, 'cancel_marker_observed': canceled,
                'per_train': rows, 'all_courses_completed': None,
                'conflicts': None, 'deadlocks': None, 'not_departed': None,
                'cancellations': True if canceled else None, 'interruptions': None,
                'blockers': ['NO_VERIFIED_PER_TRAIN_RESULT_FORMAT', 'NO_24H_ELAPSED_TIME_EVIDENCE',
                             'NO_CONFLICT_DEADLOCK_COVERAGE', 'NO_RUN_CONTENT_OR_EXECUTION_BINDING'],
                'limitation': 'Used Courses is a list, not arrival/departure evidence. Marker absence does not prove zero incidents. No verified arrival/occupation result fixture is supplied. Caller expected IDs are requirements, not observed native trains.'}


def tool_definitions(root):
    """Rows directly compatible with Registry.Tool(*row); append before filtering."""
    service = SimulationEvidence(root)
    return [
        ('opentrack_simulation_capabilities', 'Report supported original script-job controls and evidence contracts.', Empty, service.capabilities),
        ('opentrack_simulation_control', 'Start a fresh isolated OpenTrack 1.7 job, query state, or request cancellation. Batch mode runs explicit delay scenarios. Interactive mode preserves an in-window breakpoint. An optional source-bound OTD manifest attaches dispatching rules to each run copy.', Control, service.control, False, False),
        ('opentrack_inspect_simulation_evidence', 'Read selected existing native protocol/messages, compare exact required Course IDs, and report unknown train arrival/24h/incident evidence. Cannot certify successful simulation.', InspectEvidence, service.inspect),
    ]


class EvidenceRegistry:
    """Small standalone profile, preserving the main registry envelope contract."""
    def __init__(self, root, profile='simulation-evidence'):
        if profile not in ('simulation-evidence', 'all'):
            raise EvidenceError('PROFILE_UNKNOWN', 'Supported profiles: simulation-evidence, all')
        self.profile = profile
        self.tools = {row[0]: row for row in tool_definitions(root)}

    def list(self):
        return [{'name': n, 'description': d, 'inputSchema': m.model_json_schema(),
                 'annotations': {'readOnlyHint': not flags or flags[0], 'destructiveHint': False,
                                 'idempotentHint': not flags or flags[0], 'openWorldHint': False}}
                for n, d, m, _, *flags in self.tools.values()]

    def envelope(self, name, arguments):
        try:
            if name not in self.tools:
                raise EvidenceError('UNKNOWN_TOOL', 'Discover supported tools with tools/list')
            _, _, model, handler, *_ = self.tools[name]
            return {'ok': True, 'result': handler(model.model_validate(arguments))}
        except (EvidenceError, ValidationError, OSError) as exc:
            return {'ok': False, 'error': {'code': getattr(exc, 'code', 'INVALID_ARGUMENTS' if isinstance(exc, ValidationError) else 'EVIDENCE_IO_ERROR'), 'message': str(exc)}}
