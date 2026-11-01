"""Conservative evidence adapter for the existing native protocol text format.

This generic protocol adapter is independent of the archive backends. It
neither starts native code nor treats protocol output as train arrival evidence.
Format source: Service.logs and tests/test_api.py, not a new CSV convention.
"""
from collections import Counter
import hashlib
import math
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CATALOG_KEYS = ('DestInfoFile', 'DepotFile', 'TrainFile', 'CourseFile', 'StationFile', 'TimetableFile')
LIMIT = 10 * 1024 * 1024


class EvidenceError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Control(Empty):
    action: Literal['start', 'status', 'stop']


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
        return {'state': 'blocked', 'native_simulation_verified': False,
                'native_start': 'blocked_no_audited_entrypoint',
                'native_status': 'blocked_no_owned_native_job',
                'native_stop': 'blocked_no_audited_entrypoint',
                'available': ['inspect_existing_protocol_evidence'],
                'archive_dependency_status': 'not_checked_by_this_adapter; requirements_depend_on_the_selected_archive_tool',
                'native_engine_status': 'not_observed_by_this_adapter; other_authorized_native_workflows_are_separate',
                'control_adapter_status': 'not_implemented_in_supplied_API',
                'format_basis': ['opentrack_ai/service.py:Service.logs', 'tests/test_api.py:test_matching_end_protocol_is_not_all_train_acceptance'],
                'per_train_arrival_parser': 'not_implemented_in_this_generic_protocol_adapter; profile_specific_auditors_are_separate',
                'reason': 'This generic protocol evidence adapter has no owned-job launch/stop implementation. It does not describe every original-app or separately authorized native workflow.'}

    def control(self, args):
        return {'state': 'blocked', 'requested_action': args.action, 'executed': False,
                'job_id': None, 'native_simulation_verified': False,
                'reason_code': 'NATIVE_CONTROL_UNAVAILABLE',
                'reason': 'No native control is implemented by this generic protocol adapter. No process was launched, inspected, or stopped.'}

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
        
        def one(pattern):
            matches = re.findall(pattern, text, re.M)
            return matches[0] if len(matches) == 1 else None
        catalog_matches = {}
        for key in CATALOG_KEYS:
            value = one(r'^' + key + r':([^\r\n]+)\r?$')
            expected = parameters.get(key)
            
            
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
        ('opentrack_simulation_capabilities', 'Report supported simulation controls and result-format blockers; never execute native code.', Empty, service.capabilities),
        ('opentrack_simulation_control', 'Request start/status/stop; currently explicitly blocked because no audited native adapter exists. Never starts or stops a process.', Control, service.control),
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
                 'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}}
                for n, d, m, h in self.tools.values()]

    def envelope(self, name, arguments):
        try:
            if name not in self.tools:
                raise EvidenceError('UNKNOWN_TOOL', 'Discover supported tools with tools/list')
            _, _, model, handler = self.tools[name]
            return {'ok': True, 'result': handler(model.model_validate(arguments))}
        except (EvidenceError, ValidationError, OSError) as exc:
            return {'ok': False, 'error': {'code': getattr(exc, 'code', 'INVALID_ARGUMENTS' if isinstance(exc, ValidationError) else 'EVIDENCE_IO_ERROR'), 'message': str(exc)}}
