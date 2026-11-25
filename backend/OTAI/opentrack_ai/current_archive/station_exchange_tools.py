"""SHA-bound native station catalog import and original exchange publication."""

import os
from typing import Annotated, Literal
from xml.parsers.expat import ExpatError

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from ..errors import APIError
from ..json_safe import checked_json
from . import station_exchange as exchange
from .bundle_tools import Source
from .next_tools import Save
from .operation_tools import Name
from .prepare_contract.auxiliary import records
from .project_candidate_publication import ProjectSave
from .tools import ArchiveTools, Input, sha


Format = Literal['opentrack_text', 'opentrack_xml', 'railml_2_2']
StationInteger = Annotated[StrictInt, Field(ge=-(2 ** 31), le=2 ** 31 - 1)]
StationCaption = Annotated[StrictStr, Field(max_length=200, pattern=r'^[ -~]*$')]
StationCoordinate = Annotated[StrictStr, Field(max_length=48, pattern=r'^[ -~]*$')]


class ImportStations(Save):
    stations: Source
    exchange_file: Source
    format: Format
    station_signs: Annotated[list[Name], Field(max_length=10000)] = Field(default_factory=list)
    existing: Literal['reject', 'preserve', 'update', 'replace'] = 'reject'
    project_run: Source | None = None


class ImportStationArchive(Save):
    stations: Source
    donor_stations: Source
    station_signs: Annotated[list[Name], Field(min_length=1, max_length=10000)]
    existing: Literal['reject', 'preserve', 'replace'] = 'reject'
    project_run: Source | None = None


class ExportStations(ProjectSave):
    stations: Source
    format: Literal['opentrack_text', 'opentrack_xml', 'railml_2_2', 'google_earth', 'google_earth_ch']
    basename: Annotated[StrictStr, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')] = 'Stations'
    station_signs: Annotated[list[Name], Field(max_length=10000)] = Field(default_factory=list)


class StationFields(Input):
    name: StationCaption | None = None
    station_type: StationCaption | None = None
    altitude_m: StationInteger | None = None
    station_number: StationInteger | None = None
    company_id: StationInteger | None = None
    department_id: StationInteger | None = None
    coord_x_m: StationInteger | None = None
    coord_y_m: StationInteger | None = None
    timing_point: StrictBool | None = None
    longitude: StationCoordinate | None = None
    latitude: StationCoordinate | None = None

    @model_validator(mode='after')
    def changed_fields(self):
        changes = self.model_dump(exclude_unset=True)
        if not changes or any(value is None for value in changes.values()):
            raise ValueError('Supply one or more explicit station field values')
        for field, limit in (('longitude', 180), ('latitude', 90)):
            if field in changes:
                exchange.geographic(changes[field], limit)
        return self


class StationEdit(Input):
    sign: Name
    changes: StationFields


class EditStations(Save):
    stations: Source
    project_run: Source | None = None
    edits: Annotated[list[StationEdit], Field(min_length=1, max_length=10000)]

    @model_validator(mode='after')
    def unique_stations(self):
        if len({edit.sign for edit in self.edits}) != len(self.edits):
            raise ValueError('Select each station once')
        return self


class StationExchangeTools(ArchiveTools):
    def checked_file(self, spec, *suffixes):
        path = self.path(spec.path)
        if path.suffix.casefold() not in suffixes:
            raise APIError('STATION_EXCHANGE_EXTENSION', f'Expected a source with extension {" or ".join(suffixes)}', spec.path)
        raw = self.secure_bytes(path)
        if sha(raw) != spec.sha256:
            raise APIError('SOURCE_CHANGED', 'Station exchange input differs from its inspected checksum', spec.path)
        return path, raw

    def recheck(self, inputs):
        if any(self.secure_bytes(path) != raw for path, raw in inputs.items()):
            raise APIError('SOURCE_CHANGED', 'Station exchange input changed during operation')

    def run_dependency(self, spec, source):
        if spec is None:
            return {}
        run_path, run = self.checked_file(spec, '.run')
        try:
            bindings = [value.replace('\\', '/') for key, value, _ in records(run) if key == 'StationFile']
        except (ValueError, TypeError) as exc:
            raise APIError('STATION_EXCHANGE_RUN', 'Invalid native run file', str(exc)[:300]) from exc
        expected = source.as_posix()
        equal = len(bindings) == 1 and (bindings[0].casefold() == expected.casefold() if os.name == 'nt'
                                        else bindings[0] == expected)
        if not equal:
            raise APIError('STATION_EXCHANGE_RUN', 'Run StationFile must identify the selected native catalog')
        return {run_path: run}

    def finish_catalog(self, args, source, original, output, inputs, report):
        if len(output) > 20 * 1024 * 1024:
            raise APIError('ARCHIVE_SIZE', 'Generated station archive exceeds 20 MiB')
        result = {'saved': False, 'preview_only': args.preview_only, 'station_source_sha256': sha(original),
                  'project_run_sha256': args.project_run.sha256 if args.project_run else None,
                  'output_sha256': sha(output), 'output_bytes': len(output),
                  'fresh_archive_reload_verified': True, **report}
        if args.preview_only:
            self.recheck({source: original, **inputs})
            return result
        if self.path(args.target_path).suffix.casefold() != '.stations':
            raise APIError('STATION_EXCHANGE_EXTENSION', 'Use an explicit fresh .stations target')
        return self.save_copy(source, original, output, result, args.target_path, additional_inputs=inputs,
                              validate_output=lambda blob: exchange.read_catalog(blob, mutable=True))

    def import_stations(self, args):
        source, original = self.checked_file(args.stations, '.stations')
        suffixes = {'opentrack_text': ('.txt', '.tsv'), 'opentrack_xml': ('.xml',), 'railml_2_2': ('.xml', '.railml')}
        input_path, raw = self.checked_file(args.exchange_file, *suffixes[args.format])
        inputs = {input_path: raw, **self.run_dependency(args.project_run, source)}
        try:
            entries, ignored = exchange.read_exchange(raw, args.format)
            if args.station_signs:
                by_sign = {entry['sign']: entry for entry in entries}
                wanted = set(args.station_signs)
                if len(wanted) != len(args.station_signs) or wanted - by_sign.keys():
                    raise ValueError('Use unique exact station signs present in the exchange file')
                entries = [by_sign[sign] for sign in args.station_signs]
            output, report = exchange.apply_records(original, entries, args.format, args.existing)
        except (ValueError, KeyError, IndexError, TypeError, OverflowError, ExpatError) as exc:
            raise APIError('STATION_EXCHANGE_IMPORT', str(exc)[:500]) from exc
        return self.finish_catalog(args, source, original, output, inputs, {
            'format': args.format, 'exchange_sha256': sha(raw), 'native_import_ignores': ignored, **report,
        })

    def edit_stations(self, args):
        source, original = self.checked_file(args.stations, '.stations')
        inputs = self.run_dependency(args.project_run, source)
        entries = []
        for edit in args.edits:
            changes = edit.changes.model_dump(exclude_unset=True)
            if 'timing_point' in changes:
                changes['timing_point'] = int(changes['timing_point'])
            entries.append({'sign': edit.sign, **changes})
        try:
            output, report = exchange.apply_records(original, entries, None, 'update', require_existing=True)
        except (ValueError, KeyError, IndexError, TypeError, OverflowError) as exc:
            raise APIError('STATION_CATALOG_EDIT', str(exc)[:500]) from exc
        return self.finish_catalog(args, source, original, output, inputs, {
            'applied_fields': entries, **report,
        })

    def import_station_archive(self, args):
        source, original = self.checked_file(args.stations, '.stations')
        donor_path, donor = self.checked_file(args.donor_stations, '.stations')
        if donor_path == source and donor != original:
            raise APIError('SOURCE_CHANGED', 'Station archive changed since the destination snapshot')
        inputs = {donor_path: donor, **self.run_dependency(args.project_run, source)}
        try:
            output, report = exchange.import_station_objects(original, donor, args.station_signs, args.existing)
        except (ValueError, KeyError, IndexError, TypeError, OverflowError) as exc:
            raise APIError('STATION_CATALOG_IMPORT', str(exc)[:500]) from exc
        return self.finish_catalog(args, source, original, output, inputs, {
            'donor_station_source_sha256': sha(donor), **report,
        })

    def export_stations(self, args):
        source, original = self.checked_file(args.stations, '.stations')
        try:
            outputs, report = exchange.export_catalog(original, args.format, args.basename, args.station_signs)
        except (ValueError, KeyError, IndexError, TypeError, OverflowError, ExpatError) as exc:
            raise APIError('STATION_EXCHANGE_EXPORT', str(exc)[:500]) from exc
        result = {'saved': False, 'preview_only': args.preview_only, 'format': args.format,
                  'station_source_sha256': sha(original), 'export_readback_verified': True,
                  'files': {name: {'sha256': sha(blob), 'bytes': len(blob)} for name, blob in outputs.items()}, **report}
        inputs = {source: original}
        if args.preview_only:
            self.recheck(inputs)
            return result
        if os.name != 'nt':
            raise APIError('UNSUPPORTED_SECURE_FILESYSTEM', 'Station exchange bundle saving requires Windows x64 local NTFS')
        from .windows_publish import publish_project

        def validate_bundle(found):
            if found != outputs:
                raise APIError('STATION_EXCHANGE_EXPORT', 'Station exchange directory readback differs from preview')

        result = checked_json(result)
        publication = publish_project(self.root, self.path(args.target_directory), outputs,
                                      recheck=lambda: self.recheck(inputs), validate_bundle=validate_bundle,
                                      empty_directories=())
        return {**result, **publication}


def tool_definitions(root):
    service = StationExchangeTools(root)
    return [
        ('opentrack_edit_native_station_catalog',
         'Write selected existing native station metadata, including timing-point status and individual coordinates, '
         'to a fresh .stations copy. Upgrade Station0/1/2 using original defaults, keep saved station signs, '
         'and optionally verify the run StationFile binding.',
         EditStations, service.edit_stations, False, False),
        ('opentrack_import_native_station_catalog_archive',
         'Select exact stations from a SHA-bound native .stations donor and merge into a fresh native catalog copy. '
         'Supports Station0/1/2/3, preserves native names and coordinates, and retains the destination identity on replacement.',
         ImportStationArchive, service.import_station_archive, False, False),
        ('opentrack_import_native_station_catalog',
         'Import original station TSV, proprietary stations XML or RailML 2.2 OCPs into a fresh current .stations copy. '
         'SHA-bound catalog, optional run StationFile check, and explicit existing-station collision policy.',
         ImportStations, service.import_stations, False, False),
        ('opentrack_export_native_station_catalog',
         'Export an existing native station catalog as original TSV, stations XML plus DTD, RailML 2.2 OCPs, or Google Earth KML '
         'using saved coordinates or the original Swiss-grid projection. '
         'Supports audited older Station shapes for export. Reports fields omitted by the exchange format.',
         ExportStations, service.export_stations, False, False),
    ]
