"""New reconstruction: bounded saved-data preflight, not native prepare emulation.

The caller supplies a reader for an already authorized, exact project inventory.
No filesystem paths are opened by this module and no application is launched.
"""
from __future__ import annotations
import hashlib
import posixpath
from pathlib import Path
from typing import Callable
from .. import runfile_parameters as rp
from ..zero_operations import run_bundle as rb
from .. import writer as w, catalogs as c
from . import auxiliary as aux

PARSER_CONTRACT_PATH = Path(__file__).with_name('parser-contract.json')

RUN_ALLOWLIST = frozenset(k.decode('ascii') for k in rp.KNOWN)
RUN_ALIASES = {}
RUN_PARSERS = tuple((f'native_reader_group_{i+1}', tuple(x.decode('ascii') for x in group))
                    for i, group in enumerate(rp.NATIVE_GROUPS))
RUN_TOKENS = tuple(dict.fromkeys(t for _, group in RUN_PARSERS for t in group)) + ('%', '$')
MAX_MEMBER_BYTES = 20 * 1024 * 1024
MAX_PROJECT_BYTES = 256 * 1024 * 1024


def contract_digest():
    return hashlib.sha256(PARSER_CONTRACT_PATH.read_bytes()).hexdigest()


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _parse(run_blob):
    rows = aux.records(run_blob)
    values = {}
    for key, value, _ in rows:
        if key is None:
            continue
        _require(value and value == value.strip(), 'Empty or whitespace-padded run value')
        _require(not any(t in value for t in ('%', '$')), 'Unresolved path/value macro is outside this profile')
        values.setdefault(key, []).append(value)
    report = rp.inspect_runfile(aux.core_bytes(rows))
    _require(report['editable'], 'Invalid explicit run window/step: ' + '; '.join(report['issues']))
    for role, key in rb.CATALOG_KEYS.items():
        _require(len(values.get(key, [])) == 1, 'Exactly one explicit ' + key + ' required')
    _require(len(values.get('OutputPath', [])) == 1, 'Exactly one explicit OutputPath required')
    _require(1 <= len(values.get('Infrastructure Document', [])) <= 100, 'Need 1..100 explicit infrastructure documents')
    _require(values.get('TrainType'), 'Explicit ordered TrainType entries required; native defaults are not assumed')
    return values, report, rows


def check(run_blob: bytes, bound_reader: Callable[[str], bytes]) -> dict:
    """Check finite current-format catalog/reference/time consistency.

    `passed_static_subset` is deliberately narrower than native loading, route
    dynamics, dispatching, license validation, or completion of a simulation.
    Errors are structured; no source byte is modified. A topology-only empty
    workload is valid as a model artifact but fails this operating-data profile.
    """
    result = {
        'contract': 'opentrack-saved-data-preflight-v2-auxiliary',
        'passed_static_subset': False, 'errors': [],
        'native_application_started': False, 'native_execution': False,
        'native_runtime_ready': False, 'native_prepare_called': False,
        'saved': False, 'sources_changed': False,
        'checks': {}, 'dependency_manifest': {},
        'unestablished': [
            'Native loading and application compatibility are not executed.',
            'Original OpenTrack owns signal dynamics, interlocking, train motion and dispatching; this Skill does not reimplement them.',
            'License, native path namespace and framework/preferences are not inspected.',
            'This profile checks catalog references and planned-time bounds, not complete physical feasibility or a one-day simulation outcome.',
            'Diagram binding checks cover class, self path and Station references, not persisted plot results or display semantics.',
            'Incident run selections are checked by exact CourseList event names; event triggers/targets and stochastic behavior are not executed.',
            'Document Set groups are exported-preferences metadata and are not applied by the script-run document reader.',
        ],
    }
    try:
        _require(type(run_blob) is bytes, 'Run input must be immutable bytes')
        _require(callable(bound_reader), 'A project-bound byte reader is required')
        values, timing, rows = _parse(run_blob)
        result['checks']['canonical_run_records'] = True
        result['checks']['explicit_window'] = timing['numeric']
        catalogs_absolute = {role: values[key][0] for role, key in rb.CATALOG_KEYS.items()}
        documents_absolute = values['Infrastructure Document']
        diagrams_absolute = values.get('Train Diagram Document', [])
        input_paths = list(catalogs_absolute.values()) + documents_absolute + diagrams_absolute
        all_paths = input_paths + [values['OutputPath'][0]]
        
        windows = all(len(p) > 3 and p[1:3] == ':/' for p in all_paths)
        posix = all(p.startswith('/') and not p.startswith('//') for p in all_paths)
        _require(windows or posix, 'All bindings need one canonical absolute path style')
        style = 'windows' if windows else 'posix'
        for path in all_paths:
            _require(rb.root_path(path, style) == path, 'Noncanonical absolute run path')
        _require(len({p.casefold() for p in input_paths}) == len(input_paths), 'Aliased catalog/document paths')
        
        
        common = posixpath.commonpath(all_paths)
        _require(rb.root_path(common, style) == common, 'A non-root common execution tree is required')
        def member(path):
            _require(path.startswith(common + '/'), 'Input is not a descendant of the common execution tree')
            return rb.relative(path[len(common) + 1:])
        catalog_paths = {role: member(path) for role, path in catalogs_absolute.items()}
        document_paths = [member(path) for path in documents_absolute]
        files = {}
        total = 0
        for path in input_paths:
            blob = bound_reader(path)
            _require(type(blob) is bytes and 0 < len(blob) <= MAX_MEMBER_BYTES,
                     'Bound dependency must be nonempty immutable bytes of at most 20 MiB')
            total += len(blob)
            _require(total <= MAX_PROJECT_BYTES, 'Bound dependencies exceed 256 MiB')
            rel = member(path)
            files[rel] = blob
            result['dependency_manifest'][rel] = {
                'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest(),
                'declared_path': path,
            }
        result['checks']['explicit_dependency_bytes'] = True
        stations=c.station_items(w.load_next_compatible(files[catalog_paths['stations']])[0])
        result['checks']['diagrams'] = [aux.diagram_binding(files[member(path)],path,stations) for path in diagrams_absolute]
        result['checks']['document_sets'] = aux.set_bindings(rows,set(documents_absolute+diagrams_absolute))
        result['checks']['incident_selection'] = aux.incident_bindings(files[catalog_paths['courses']], values.get('Incident',[]))
        result['checks']['bindings'] = rb.verify_archive_bindings(
            aux.core_bytes(rows), {key: blob for key,blob in files.items() if key in set(catalog_paths.values())|set(document_paths)},
            catalog_paths=catalog_paths, document_paths=document_paths)
        result['passed_static_subset'] = True
        result['run_sha256'] = hashlib.sha256(run_blob).hexdigest()
        result['execution_root_common_prefix'] = common
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, OSError) as exc:
        result['errors'].append({'rule': 'SAVED_DATA_PREFLIGHT', 'message': str(exc)[:1000]})
    return result
