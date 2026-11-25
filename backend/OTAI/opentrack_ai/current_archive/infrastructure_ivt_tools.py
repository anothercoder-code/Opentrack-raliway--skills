"""Publish normal native worksheets from original tabular track data."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, StrictStr

from ..errors import APIError
from .bundle_tools import Source
from .next_tools import Save
from .project_candidate_publication import ProjectSave, project_target, publish_candidate
from .tools import ArchiveTools, Input, sha


class IVTPlatform(Input):
    station_sign: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    direction: Literal['ascending', 'descending']
    entry_position_m: Annotated[StrictStr, Field(min_length=1, max_length=25)]


WorksheetName = Annotated[StrictStr, Field(pattern=r'^[A-Za-z][A-Za-z0-9_ -]{0,79}\.opentrack$')]
Speed = Annotated[StrictInt, Field(ge=0, le=1000)]
DirectionalSpeeds = Annotated[list[Speed], Field(min_length=2, max_length=2)]


class TrackTableSources(ProjectSave):
    source: Source
    header_document: Source
    shapes: Source
    stations_catalog: Source | None = None


class ImportIVT(TrackTableSources):
    worksheet_name: WorksheetName = 'IVTWorksheet.opentrack'
    signal_sight_m: Annotated[StrictInt, Field(ge=1, le=100000)] = 500
    platform_areas: Annotated[list[IVTPlatform], Field(max_length=100)] = Field(default_factory=list)


class ImportSiemens(TrackTableSources):
    worksheet_name: WorksheetName = 'SiemensWorksheet.opentrack'
    default_directional_limits_kmh: Annotated[list[DirectionalSpeeds], Field(min_length=4, max_length=4)]


class SBBSignalTemplate(Input):
    worksheet: Source
    signal_id: Annotated[StrictInt, Field(ge=0, le=2147483647)]


class ImportSBBZLR(TrackTableSources):
    worksheet_name: WorksheetName = 'SBBZLRWorksheet.opentrack'
    default_directional_limits_kmh: Annotated[list[DirectionalSpeeds], Field(min_length=4, max_length=4)]
    signal_template: SBBSignalTemplate | None = None


class ConvertBentley(Save):
    source: Source
    orientation: Literal['horizontal', 'vertical']


class InfrastructureIVTTools(ArchiveTools):
    def convert_bentley(self, args):
        from .infrastructure_bentley import convert_bentley
        from .infrastructure_ivt import parse_ivt

        source = self.path(args.source.path)
        target = self.path(args.target_path) if args.target_path is not None else None
        if source.suffix.casefold() not in ('.txt', '.tsv', '.rpt'):
            raise APIError('BENTLEY_FILE_FORMAT', 'Select an original Bentley text alignment report')
        if target is not None and target.suffix.casefold() not in ('.txt', '.ivt'):
            raise APIError('BENTLEY_FILE_FORMAT', 'Use a new original-style IVT text target')
        raw = self.secure_bytes(source)
        if sha(raw) != args.source.sha256:
            raise APIError('SOURCE_CHANGED', 'Bentley report differs from its requested checksum')
        try:
            output, report = convert_bentley(raw, args.orientation)
        except (ValueError, TypeError, IndexError, OverflowError) as exc:
            raise APIError('BENTLEY_CONVERSION', str(exc)[:500]) from exc
        receipt = {**report, 'source_sha256': sha(raw), 'output_sha256': sha(output), 'output_bytes': len(output),
                   'saved': False, 'preview_only': args.preview_only, 'native_application_started': False}
        if args.preview_only:
            if self.secure_bytes(source) != raw:
                raise APIError('SOURCE_CHANGED', 'Bentley report changed during preparation')
            return receipt
        return self.save_copy(source, raw, output, receipt, args.target_path, validate_output=parse_ivt)

    def import_line(self, args):
        from .infrastructure_ivt import import_ivt

        return self._publish_line(args, 'IVT', ('.txt', '.tsv', '.ivt'),
                                  'IVTStationCatalog.stations', import_ivt,
                                  (args.platform_areas, args.signal_sight_m))

    def import_siemens(self, args):
        from .infrastructure_siemens import import_siemens

        return self._publish_line(args, 'SIEMENS', ('.txt', '.tsv', '.siemens'),
                                  'SiemensStationCatalog.stations', import_siemens,
                                  (args.default_directional_limits_kmh,))

    def import_sbb_zlr(self, args):
        from .infrastructure_sbb_zlr import import_sbb_zlr

        template = args.signal_template
        return self._publish_line(args, 'SBB_ZLR', ('.txt', '.tsv', '.zlr', '.sbb'),
                                  'SBBZLRStationCatalog.stations', import_sbb_zlr,
                                  (args.default_directional_limits_kmh, template.signal_id if template else None),
                                  extra_sources={'signal_template': template.worksheet} if template else None)

    def _publish_line(self, args, format_name, input_extensions, catalog_name, converter, converter_options,
                      *, extra_sources=None):
        bindings = {role: getattr(args, role) for role in ('source', 'header_document', 'shapes')}
        if args.stations_catalog is not None:
            bindings['stations_catalog'] = args.stations_catalog
        if extra_sources:
            bindings.update(extra_sources)
        files, data = {}, {}
        for role, binding in bindings.items():
            source = self.path(binding.path)
            files[role], data[role] = source, self.secure_bytes(source)
            if sha(data[role]) != binding.sha256:
                raise APIError('SOURCE_CHANGED', f'{format_name} input or native donor differs from its checksum', role)
        if files['source'].suffix.casefold() not in input_extensions:
            raise APIError(f'{format_name}_FILE_FORMAT', f'Select an original {format_name} tab-delimited track table')
        if 'stations_catalog' in files and files['stations_catalog'].suffix.casefold() != '.stations':
            raise APIError(f'{format_name}_FILE_FORMAT', 'Select an original native .stations catalog')
        if 'signal_template' in files and files['signal_template'].suffix.casefold() != '.opentrack':
            raise APIError(f'{format_name}_FILE_FORMAT', 'Select a native .opentrack signal template worksheet')
        target = project_target(self, args)

        def recheck():
            if any(self.secure_bytes(files[role]) != data[role] for role in bindings):
                raise APIError('SOURCE_CHANGED', f'{format_name} input or donor changed during preparation or publication')

        try:
            worksheet, report = converter(data['source'], data['header_document'], data['shapes'],
                                          data.get('stations_catalog'), *converter_options,
                                          *(data[role] for role in (extra_sources or {})))
        except (ValueError, KeyError, IndexError, TypeError, OverflowError) as exc:
            raise APIError(f'{format_name}_IMPORT', str(exc)[:500]) from exc
        members = {args.worksheet_name: worksheet}
        if 'stations_catalog' in files:
            members[catalog_name] = data['stations_catalog']
        receipt = {**report, 'saved': False, 'preview_only': args.preview_only,
                   'input_sha256': {role: sha(raw) for role, raw in data.items()},
                   'members': {name: {'bytes': len(blob), 'sha256': sha(blob)} for name, blob in members.items()},
                   'source_catalog_preserved': 'stations_catalog' in files, 'native_application_started': False}
        if args.preview_only:
            recheck()
            return receipt
        return publish_candidate(self, target, members, receipt, recheck, require_run=False)


def tool_definitions(root):
    service = InfrastructureIVTTools(root)
    return [('opentrack_import_native_ivt_infrastructure',
             'Import the original tab-delimited IVT infrastructure format into a fresh ordinary .opentrack worksheet. '
             'Preserves four positional speed categories in both directions, gradients, radii, kilometre marks, reviewed tunnel '
             'and signal tags, and exact station catalogue markers. Optional explicit whole-Edge stopping areas.',
             ImportIVT, service.import_line, False, False),
            ('opentrack_import_native_siemens_infrastructure',
             'Import a Siemens tab-delimited line into an ordinary editable worksheet. Uses reviewed default speed '
             'categories, the original symmetric first speed, gradients, radii, tunnel codes and exact station names.',
             ImportSiemens, service.import_siemens, False, False),
            ('opentrack_import_native_sbb_zlr_infrastructure',
             'Import SBB ZLR format-1 continuous track, kilometre marks, speed profiles and point stations into a fresh '
             'native worksheet. H/V and co-located complementary signals require a pinned native signal template.',
             ImportSBBZLR, service.import_sbb_zlr, False, False),
            ('opentrack_convert_bentley_railtrack_to_ivt',
             'Write the original Bentley Rail Track horizontal or vertical report conversion as an OpenTrack IVT file. '
             'The result can be read directly with the native IVT worksheet import tool.',
             ConvertBentley, service.convert_bentley, False, False)]
