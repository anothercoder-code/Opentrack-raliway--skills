"""Inspect and author verified original Preferences import text."""

from typing import Annotated

from pydantic import Field, StrictStr, model_validator

from ..errors import APIError
from ..json_safe import checked_json
from . import native_preferences as preferences, writer as w
from .bundle_tools import Source
from .next_tools import Save
from .runfile_tools import RunKey
from .tools import ArchiveTools, Input, sha


Settings = Annotated[dict[RunKey, Annotated[StrictStr, Field(min_length=1, max_length=100)]], Field(max_length=100)]
SetName = Annotated[StrictStr, Field(pattern=f'^{preferences.SET_NAME}$')]


class InspectPreferences(Input):
    source: Source


class CopySettings(Input):
    source: Source
    fields: Annotated[list[RunKey], Field(min_length=1, max_length=100)]


class DocumentSet(Input):
    name: SetName
    documents: Annotated[list[Source], Field(min_length=1, max_length=100)]


class EditPreferences(Save):
    source: Source
    copy_settings: CopySettings | None = None
    changes: Settings = Field(default_factory=dict)
    document_sets: Annotated[list[DocumentSet], Field(max_length=100)] | None = None

    @model_validator(mode='after')
    def has_edits(self):
        if self.copy_settings is None and not self.changes and self.document_sets is None:
            raise ValueError('Select settings to copy or change, or provide named Document Sets')
        if self.copy_settings is not None and self.changes.keys() & set(self.copy_settings.fields):
            raise ValueError('A setting may be copied or assigned in one operation')
        return self


DOCUMENT_SHAPES = {'Infrastructure Document': {'.opentrack': 'OTDocument'},
                   'Train Diagram Document': {'.otsimcor': 'OTCorridorDocument', '.otsimnet': 'OTSimDocument'}}
EXPORT_SUFFIXES = {'.txt', '.run'}


class PreferencesTools(ArchiveTools):
    def read_source(self, spec):
        path = self.path(spec.path)
        if path.suffix.lower() not in EXPORT_SUFFIXES | {'.pref'}:
            raise APIError('PREFERENCES_PATH', 'Use a native Preferences export or run file')
        raw = self.secure_bytes(path)
        if sha(raw) != spec.sha256:
            raise APIError('SOURCE_CHANGED', 'Preferences source differs from the inspected SHA-256')
        return path, raw

    def inspect_preferences(self, args):
        path, source = self.read_source(args.source)
        try:
            result = preferences.inspect(source)
        except (ValueError, TypeError) as exc:
            raise APIError('PREFERENCES_FORMAT', str(exc)[:500]) from exc
        if self.secure_bytes(path) != source:
            raise APIError('SOURCE_CHANGED', 'Preferences source changed during inspection')
        return {'source': args.source.model_dump(), **result, 'read_only': True}

    def changed_sets(self, commands, base, additional_inputs):
        rows, _ = preferences.parse(base)
        declared = preferences.declared_document_paths(rows)
        edits = []
        for group in commands:
            documents = []
            for spec in group.documents:
                path = self.path(spec.path)
                key = path.as_posix().casefold()
                if key not in declared:
                    raise APIError('PREFERENCES_DOCUMENT_BINDING', 'Document Set member is outside the selected profile declarations', spec.path)
                kind, _ = declared[key]
                expected = DOCUMENT_SHAPES[kind].get(path.suffix.lower())
                raw = additional_inputs.get(path)
                if raw is None:
                    raw = self.secure_bytes(path)
                    extra, _ = w.load_next_compatible(raw)
                    if expected is None or w.kind(extra) != expected:
                        raise APIError('PREFERENCES_DOCUMENT_BINDING', 'Declared native document root differs from the member type', spec.path)
                    additional_inputs[path] = raw
                if sha(raw) != spec.sha256:
                    raise APIError('SOURCE_CHANGED', 'Native Document Set member differs from its inspected SHA-256', spec.path)
                documents.append(path.as_posix())
            edits.append({'name': group.name, 'documents': documents})
        return edits

    def edit_preferences(self, args):
        path, source = self.read_source(args.source)
        if args.target_path is not None and self.path(args.target_path).suffix.lower() not in EXPORT_SUFFIXES:
            raise APIError('PREFERENCES_PATH', 'Use .txt or .run for the new original Preferences import file')
        additional = {}
        try:
            copied = {}
            if args.copy_settings is not None:
                donor_path, donor = self.read_source(args.copy_settings.source)
                copied = preferences.transferable(donor, args.copy_settings.fields)
                additional[donor_path] = donor
            sets = None if args.document_sets is None else self.changed_sets(args.document_sets, source, additional)
            output, changes = preferences.edit(source, args.changes | copied, sets)
            result = checked_json({'preview_only': args.preview_only, 'saved': False, 'source_path': args.source.path,
                'source_sha256': args.source.sha256, 'output_sha256': sha(output), 'output_bytes': len(output),
                'input_sources': [{'path': value.relative_to(self.root).as_posix(), 'sha256': sha(raw)}
                                  for value, raw in {path: source, **additional}.items()],
                'native_application_started': False, 'native_preferences_import_executed': False,
                'fresh_preferences_readback': True, 'copied_settings': sorted(copied), **changes})
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('PREFERENCES_FORMAT', str(exc)[:500]) from exc
        if not args.preview_only:
            return self.save_copy(path, source, output, result, args.target_path, additional_inputs=additional,
                                  validate_output=preferences.inspect)
        for value, raw in {path: source, **additional}.items():
            if self.secure_bytes(value) != raw:
                raise APIError('SOURCE_CHANGED', 'Preferences input or document changed during preview')
        return result


def tool_definitions(root):
    service = PreferencesTools(root)
    return [
        ('opentrack_inspect_native_preferences',
         'Inspect a SHA-bound original Preferences export, scalar options, document bindings and ordered Document Sets.',
         InspectPreferences, service.inspect_preferences),
        ('opentrack_edit_native_preferences',
         'Publish a fresh original Info > Preferences import file with selected scalar settings and ordered Document Sets of existing SHA-bound declared documents.',
         EditPreferences, service.edit_preferences, False, False),
    ]
