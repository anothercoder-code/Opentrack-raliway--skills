"""Run the installation's pinned original RailML infrastructure bridge."""

import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Annotated, Literal
from xml.parsers.expat import ExpatError

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from ..errors import APIError
from ..models import DocumentName
from . import writer
from .bundle_tools import Source
from .empty_project_tools import EmptyProjectWindow
from .infrastructure_railml import MAX_MEMBER_BYTES, gmodel_inventory, railml_inventory
from .multi_document_tools import Inventory
from .next_tools import Save
from .network_generation_tools import Speed
from .operation_tools import I32, Name
from .project_candidate_publication import ProjectSave, project_target, publish_candidate
from .tools import ArchiveTools, Input, PathText, sha
from .zero_generation.topology import validate_network


BRIDGE = Path('OpenTrack.app/Resources/railML4OT.jar')
BRIDGE_VERSION = '2.0.16.20150225'
BRIDGE_SHA256 = '7ddcb5759fa51e0819373227dbb430d479046b62c614529143d64e011101cfbe'
JVM_OPTION_ENV = {'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'CLASSPATH'}
RAILML_SUFFIXES = {'.xml', '.railml'}
GMODEL_SUFFIXES = {'.plist', '.opentrackgmodel'}


class ConvertInfrastructure(Save):
    source: Source
    direction: Literal['railml_to_gmodel', 'gmodel_to_railml']
    geometry_only: StrictBool = False

    @model_validator(mode='after')
    def geometry_direction(self):
        if self.geometry_only and self.direction != 'railml_to_gmodel':
            raise ValueError('geometry_only applies to RailML-to-GModel conversion')
        return self


class InfrastructureSpeedProfile(Input):
    native_train_type: Name
    etcs_train_category: Annotated[StrictInt, Field(ge=0, le=15)]


InfrastructureSpeedProfiles = Annotated[list[InfrastructureSpeedProfile], Field(min_length=1, max_length=16)]


def speed_profile_map(values):
    profiles = {item.native_train_type: item.etcs_train_category for item in values or ()}
    if values and (len(profiles) != len(values) or len(set(profiles.values())) != len(profiles)):
        raise ValueError('Speed profiles require distinct native keys and distinct RailML 2.2 ETCS categories')
    return profiles


class MaterializeGModel(Save):
    gmodel: Source
    header_document: Source
    shapes: Source
    fallback_speeds: Annotated[list[Speed], Field(max_length=100)] = Field(default_factory=list)
    speed_profiles: InfrastructureSpeedProfiles | None = None
    railml_speed_source: Source | None = None

    @model_validator(mode='after')
    def speed_profile_contract(self):
        speed_profile_map(self.speed_profiles)
        if (self.speed_profiles is None) != (self.railml_speed_source is None):
            raise ValueError('speed_profiles requires its original SHA-bound railml_speed_source')
        if self.speed_profiles and self.fallback_speeds:
            raise ValueError('Explicit RailML speed profile recovery requires complete GModel speeds on every Edge')
        return self


class TrackEdgeBinding(Input):
    edge_id: I32
    start_end_id: I32


class FacilityTrackBinding(Input):
    track_id: Name
    edges: Annotated[list[TrackEdgeBinding], Field(min_length=1, max_length=1000)]


class FacilitySignalBinding(Input):
    signal_id: Name
    fallback_sight_m: Annotated[StrictInt, Field(ge=1, le=100000)] | None = None
    existing_model_id: Annotated[StrictInt, Field(ge=0, le=2147483646)] | None = None


class FacilityStationBinding(Input):
    cross_section_id: Name
    direction: Literal['up', 'down']
    station_anchor: StrictBool = False
    platform_edge_id: Name | None = None
    exit_signal_id: Name | None = None
    stop_post_id: Name | None = None

    @model_validator(mode='after')
    def platform_contract(self):
        if self.platform_edge_id is None and (self.exit_signal_id is not None or self.stop_post_id is not None):
            raise ValueError('A selected platform is required when setting exit signal or stop post')
        if self.platform_edge_id is not None and self.exit_signal_id is None:
            raise ValueError('A selected platform requires a directional exit signal')
        return self


class ApplyFacilities(ProjectSave):
    railml: Source
    worksheet: Source
    source_project: Inventory | None = None
    tracks: Annotated[list[FacilityTrackBinding], Field(min_length=1, max_length=100)]
    signals: Annotated[list[FacilitySignalBinding], Field(max_length=100)] = Field(default_factory=list)
    stations: Annotated[list[FacilityStationBinding], Field(max_length=100)] = Field(default_factory=list)

    @model_validator(mode='after')
    def selected_facilities(self):
        if not self.signals and not self.stations:
            raise ValueError('Choose at least one signal or station')
        return self


class CrossDocumentTrackEdgeBinding(TrackEdgeBinding):
    document: Name


class CrossDocumentFacilityTrack(Input):
    track_id: Name
    edges: Annotated[list[CrossDocumentTrackEdgeBinding], Field(min_length=2, max_length=1000)]


class ApplyCrossDocumentPlatform(ProjectSave):
    railml: Source
    documents: Annotated[list[Source], Field(min_length=2, max_length=100)]
    stations_catalog: Source
    track: CrossDocumentFacilityTrack
    station: FacilityStationBinding

    @model_validator(mode='after')
    def require_platform(self):
        if self.station.platform_edge_id is None:
            raise ValueError('A cross-worksheet transfer requires one directed RailML stopping platform')
        return self


class RebuildCorridorWorksheet(Input):
    document: DocumentName
    start_position_m: I32
    end_position_m: I32


class RebuildRailMLProject(ProjectSave):
    railml: Source
    header_document: Source
    shapes: Source
    execution_root: PathText
    run_filename: Annotated[StrictStr, Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,59}\.run$')] = 'corridor.run'
    train_types: Annotated[list[StrictStr], Field(min_length=1, max_length=16)]
    speed_profiles: InfrastructureSpeedProfiles | None = None
    simulation: EmptyProjectWindow | None = None
    additional_outputs: Annotated[list[Literal['station_and_signal_positions']], Field(max_length=1)] = Field(default_factory=list)


class RebuildRailMLCorridor(RebuildRailMLProject):
    track_id: Name
    worksheets: Annotated[list[RebuildCorridorWorksheet], Field(min_length=2, max_length=100)]
    station: FacilityStationBinding

    @model_validator(mode='after')
    def represented_platform(self):
        if self.station.platform_edge_id is None or self.station.station_anchor:
            raise ValueError('Choose a directed physical RailML platform ending at its native exit, without a separate station anchor')
        speed_profile_map(self.speed_profiles)
        return self


class RebuildStationTrack(Input):
    track_id: Name
    start_position_m: I32
    end_position_m: I32


class RebuildStationWorksheet(Input):
    document: DocumentName
    tracks: Annotated[list[RebuildStationTrack], Field(min_length=1, max_length=100)]


class RebuildStationFacility(FacilityStationBinding):
    track_id: Name


class RebuildRailMLStation(RebuildRailMLProject):
    run_filename: Annotated[StrictStr, Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,59}\.run$')] = 'station.run'
    worksheets: Annotated[list[RebuildStationWorksheet], Field(min_length=2, max_length=100)]
    stations: Annotated[list[RebuildStationFacility], Field(min_length=2, max_length=1000)]

    @model_validator(mode='after')
    def represented_platforms(self):
        if sum(station.platform_edge_id is not None for station in self.stations) < 2:
            raise ValueError('A rebuilt branched station requires at least two explicitly directed platforms')
        speed_profile_map(self.speed_profiles)
        return self


RailMLId = Annotated[str, Field(strict=True, pattern=r'^[A-Za-z_][A-Za-z0-9_.-]{0,199}$')]


class ExportFacilitySignal(Input):
    signal_id: RailMLId
    track_id: Name
    direction: Literal['up', 'down']
    end_id: I32


class ExportFacilityStation(FacilityStationBinding):
    track_id: Name
    station_sign: Name
    ocp_id: RailMLId
    cross_section_id: RailMLId
    platform_edge_id: RailMLId | None = None
    exit_signal_id: RailMLId | None = None
    stop_post_id: RailMLId | None = None


class CrossDocumentExportTrack(CrossDocumentFacilityTrack):
    track_id: RailMLId


class ExportCrossDocumentStation(FacilityStationBinding):
    station_sign: Name
    ocp_id: RailMLId
    cross_section_id: RailMLId
    platform_edge_id: RailMLId
    exit_signal_id: RailMLId
    stop_post_id: RailMLId | None = None


class ExportCrossDocumentPlatform(Save):
    documents: Annotated[list[Source], Field(min_length=2, max_length=100)]
    stations_catalog: Source
    track: CrossDocumentExportTrack
    station: ExportCrossDocumentStation
    speed_train_type: Name = '0'
    speed_profiles: InfrastructureSpeedProfiles | None = None

    @model_validator(mode='after')
    def speed_contract(self):
        if self.speed_profiles and 'speed_train_type' in self.model_fields_set:
            raise ValueError('Choose speed_profiles or speed_train_type')
        speed_profile_map(self.speed_profiles)
        return self


class ExportFacilities(Save):
    template_railml: Source | None = None
    worksheet: Source
    stations_catalog: Source | None = None
    speed_train_type: Name = '0'
    speed_profiles: InfrastructureSpeedProfiles | None = None
    tracks: Annotated[list[FacilityTrackBinding], Field(min_length=1, max_length=100)]
    signals: Annotated[list[ExportFacilitySignal], Field(max_length=100)] = Field(default_factory=list)
    stations: Annotated[list[ExportFacilityStation], Field(max_length=100)] = Field(default_factory=list)

    @model_validator(mode='after')
    def export_contract(self):
        if not self.signals and not self.stations:
            raise ValueError('Choose at least one native signal or station to export')
        if self.stations and self.stations_catalog is None:
            raise ValueError('A selected station export requires its original station catalog')
        if self.speed_profiles and (self.template_railml is not None or 'speed_train_type' in self.model_fields_set):
            raise ValueError('speed_profiles applies to fresh geometry and replaces speed_train_type')
        speed_profile_map(self.speed_profiles)
        return self


class GeometryTrackBinding(FacilityTrackBinding):
    track_id: RailMLId


class GeometryDocumentBinding(Source):
    tracks: Annotated[list[GeometryTrackBinding], Field(min_length=1, max_length=100)]


class ExportGeometry(Save):
    documents: Annotated[list[GeometryDocumentBinding], Field(min_length=1, max_length=20)]
    speed_train_type: Name = '0'
    speed_profiles: InfrastructureSpeedProfiles | None = None

    @model_validator(mode='after')
    def bounded_inventory(self):
        if sum(len(track.edges) for doc in self.documents for track in doc.tracks) > 2000:
            raise ValueError('At most 2000 physical Edges across the supplied worksheets')
        if self.speed_profiles and 'speed_train_type' in self.model_fields_set:
            raise ValueError('Choose speed_profiles or speed_train_type')
        speed_profile_map(self.speed_profiles)
        return self


def java_executable():
    java_home = os.environ.get('OPENTRACK_JAVA_HOME') or os.environ.get('JAVA_HOME')
    name = 'java.exe' if os.name == 'nt' else 'java'
    path = Path(java_home) / 'bin' / name if java_home else shutil.which(name)
    if not path or not Path(path).is_absolute() or not Path(path).is_file():
        raise APIError('RAILML_BRIDGE_JAVA', 'Set OPENTRACK_JAVA_HOME to an existing local Java installation')
    return Path(path).resolve(strict=True)


def bridge_resource(root):
    try:
        with (root / BRIDGE).open('rb') as stream:
            data = stream.read(1024 * 1024 + 1)
    except OSError as exc:
        raise APIError('RAILML_BRIDGE_RESOURCE', 'Original OpenTrack.app/Resources/railML4OT.jar was not available') from exc
    if sha(data) != BRIDGE_SHA256:
        raise APIError('RAILML_BRIDGE_SHA', 'The local railML4OT.jar differs from the verified original bridge')
    return data


def bridge_convert(java, jar, command, source_name, raw, output_name):
    if sha(jar) != BRIDGE_SHA256:
        raise APIError('RAILML_BRIDGE_SHA', 'The local railML4OT.jar differs from the verified original bridge')
    for name in (source_name, output_name):
        if re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_. -]{0,199}', name) is None:
            raise APIError('RAILML_BRIDGE_FILENAME', 'Use a printable original worksheet or RailML filename')
    environment = {key: value for key, value in os.environ.items() if key.upper() not in JVM_OPTION_ENV}
    with TemporaryDirectory(prefix='opentrack-railml-') as directory:
        stage = Path(directory)
        jar_name = BRIDGE.name
        (stage / jar_name).write_bytes(jar)
        (stage / source_name).write_bytes(raw)
        options = ['-Xmx512m', '-Djava.io.tmpdir=.', '-Djava.awt.headless=true', '-Dfile.encoding=UTF-8',
                   '-Duser.language=en', '-Duser.country=US', '-Djavax.xml.accessExternalDTD=',
                   '-Djavax.xml.accessExternalSchema=']
        try:
            with (stage / 'bridge-stdout.log').open('w+b') as stdout, (stage / 'bridge-stderr.log').open('w+b') as stderr:
                process = subprocess.run([str(java), *options, '-jar', jar_name, command, source_name, output_name],
                                         cwd=stage, env=environment, stdin=subprocess.DEVNULL, stdout=stdout,
                                         stderr=stderr, timeout=90,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                stderr.seek(max(0, stderr.tell() - 32768))
                diagnostics = stderr.read().decode('utf-8', errors='replace').splitlines()
        except subprocess.TimeoutExpired as exc:
            raise APIError('RAILML_BRIDGE_TIMEOUT', 'Original RailML bridge exceeded 90 seconds') from exc
        target = stage / output_name
        messages = [line for line in diagnostics if line.strip()]
        if process.returncode != 0 or not messages or messages[-1].strip() != 'ok' or not target.is_file():
            raise APIError('RAILML_BRIDGE_FAILED', 'Original bridge did not complete conversion',
                           {'process_exit_code': process.returncode, 'terminal_messages': messages[-5:]})
        if not 0 < target.stat().st_size <= MAX_MEMBER_BYTES:
            raise APIError('RAILML_BRIDGE_OUTPUT', 'Original bridge produced an empty or oversized file')
        warning_lines = [line[:500] for line in messages if line.startswith('WARNING:')]
        return target.read_bytes(), {'process_exit_code': process.returncode, 'original_ok_marker': True,
                                    'warning_count_in_log_tail': len(warning_lines), 'warnings': warning_lines[-20:]}


class InfrastructureRailMLTools(ArchiveTools):
    def convert(self, args):
        from .infrastructure_railml_facilities import project_geometry

        importing = args.direction == 'railml_to_gmodel'
        source = self.path(args.source.path)
        source_suffixes, target_suffixes = (RAILML_SUFFIXES, GMODEL_SUFFIXES) if importing else (GMODEL_SUFFIXES, RAILML_SUFFIXES)
        target = self.path(args.target_path) if args.target_path is not None else None
        if source.suffix.casefold() not in source_suffixes or (target is not None and target.suffix.casefold() not in target_suffixes):
            raise APIError('RAILML_BRIDGE_FORMAT', 'Pair RailML 2.2 XML with an OpenTrack GModel .plist or .opentrackgmodel worksheet')
        input_data = self.secure_bytes(source)
        if sha(input_data) != args.source.sha256:
            raise APIError('SOURCE_CHANGED', 'Selected infrastructure exchange input differs from its inspected SHA-256')
        jar = bridge_resource(self.root)
        reader, verify = (railml_inventory, gmodel_inventory) if importing else (gmodel_inventory, railml_inventory)
        output_name = target.name if target is not None else source.stem + ('.plist' if importing else '.xml')
        bridge_source = source.with_suffix('.plist').name if not importing else source.name
        bridge_output = Path(output_name).with_suffix('.plist').name if importing else output_name
        try:
            source_info = reader(input_data)
            bridge_input, projection = project_geometry(input_data) if args.geometry_only else (input_data, None)
            output, process = bridge_convert(java_executable(), jar, 'r2p' if importing else 'p2r', bridge_source, bridge_input, bridge_output)
            target_info = verify(output)
        except (ValueError, KeyError, IndexError, TypeError, OverflowError, ExpatError) as exc:
            raise APIError('RAILML_BRIDGE_FORMAT', str(exc)[:500]) from exc
        gmodel, railml = (target_info, source_info) if importing else (source_info, target_info)
        length_delta = gmodel['total_edge_length_m'] - railml['total_track_length_m']
        proof = {'saved': False, 'preview_only': args.preview_only, 'direction': args.direction,
                 'source_sha256': sha(input_data), 'output_sha256': sha(output), 'output_bytes': len(output),
                 'original_bridge': {'version': BRIDGE_VERSION, 'sha256': sha(jar), **process},
                 'source_inventory': source_info, 'output_inventory': target_info, 'geometry_readback_verified': True,
                 'converted_length_delta_m': length_delta, 'native_application_started': False}
        if projection is not None:
            proof['geometry_only_projection'] = {'bridge_input_sha256': sha(bridge_input), **projection}

        def verify_bridge(_published=None):
            bridge_resource(self.root)

        if args.preview_only:
            verify_bridge()
            if self.secure_bytes(source) != input_data:
                raise APIError('SOURCE_CHANGED', 'Infrastructure exchange input changed during conversion')
            return proof
        return self.save_copy(source, input_data, output, proof, args.target_path,
                              scope_check=verify_bridge, validate_output=verify)

    def materialize(self, args):
        from .gmodel_materialization import materialize
        from .infrastructure_railml_facilities import project_geometry
        from .infrastructure_railml_speed_profiles import source_speed_edges, verify_native_speed_edges

        inputs, payload = {}, {}
        roles = ('gmodel', 'header_document', 'shapes')
        if args.railml_speed_source is not None:
            roles += ('railml_speed_source',)
        for role in roles:
            binding = getattr(args, role)
            path = self.path(binding.path)
            raw = self.secure_bytes(path)
            if sha(raw) != binding.sha256:
                raise APIError('SOURCE_CHANGED', 'GModel materialization input differs from its checksum', role)
            inputs[path] = raw
            payload[role] = raw
        source = self.path(args.gmodel.path)
        target = self.path(args.target_path) if args.target_path is not None else None
        if source.suffix.casefold() not in GMODEL_SUFFIXES or (target is not None and target.suffix.casefold() != '.opentrack'):
            raise APIError('GMODEL_MATERIALIZATION_FORMAT', 'Choose an original .plist or .opentrackgmodel and a new .opentrack')
        profiles = speed_profile_map(args.speed_profiles)
        speed_source_proof = {}
        try:
            if profiles:
                speed_source = self.path(args.railml_speed_source.path)
                raw = payload['railml_speed_source']
                if speed_source.suffix.casefold() not in RAILML_SUFFIXES:
                    raise APIError('GMODEL_MATERIALIZATION_FORMAT', 'The exact speed-profile source must be RailML XML')
                expected = source_speed_edges(raw, profiles)
                projected, _ = project_geometry(raw)
                replay, original_bridge = bridge_convert(java_executable(), bridge_resource(self.root), 'r2p',
                                                          speed_source.name, projected, source.with_suffix('.plist').name)
                if replay != payload['gmodel']:
                    raise APIError('RAILML_SPEED_BRIDGE_MISMATCH', 'GModel differs from the official bridge replay of the source')
            output, report = materialize(payload['gmodel'], payload['header_document'], payload['shapes'],
                                         [speed.model_dump() for speed in args.fallback_speeds],
                                         speed_profiles=profiles)
            if profiles:
                speed_source_proof = {'railml_speed_source_sha256': sha(raw), 'gmodel_speed_source_replayed': True,
                                      'verified_speed_vectors': verify_native_speed_edges(output, profiles, expected),
                                      'original_speed_bridge': original_bridge}
        except (ValueError, KeyError, IndexError, TypeError, OverflowError, ExpatError) as exc:
            raise APIError('GMODEL_MATERIALIZATION', str(exc)[:500]) from exc
        if len(output) > MAX_MEMBER_BYTES:
            raise APIError('ARCHIVE_SIZE', 'Generated worksheet exceeds 20 MiB')
        result = {'saved': False, 'preview_only': args.preview_only, 'source_sha256': sha(payload['gmodel']),
                  'output_sha256': sha(output), 'output_bytes': len(output), 'geometry_readback_verified': True,
                  'native_application_started': False, 'operations_generated': False, **report, **speed_source_proof}
        if args.preview_only:
            if any(self.secure_bytes(path) != data for path, data in inputs.items()):
                raise APIError('SOURCE_CHANGED', 'GModel or worksheet donor changed during materialization')
            return result
        return self.save_copy(source, payload['gmodel'], output, result, args.target_path,
                              additional_inputs={path: data for path, data in inputs.items() if path != source},
                              validate_output=lambda raw: validate_network(writer.load_next_compatible(raw)[0]))

    def facilities(self, args):
        from .infrastructure_railml_facilities import apply_facilities

        railml, sheet = self.path(args.railml.path), self.path(args.worksheet.path)
        if railml.suffix.casefold() not in RAILML_SUFFIXES or sheet.suffix != '.opentrack':
            raise APIError('RAILML_FACILITY_FORMAT', 'Choose RailML 2.2 XML and an ordinary native .opentrack worksheet')
        sources = {path: self.secure_bytes(path) for path in (railml, sheet)}
        if (sha(sources[railml]), sha(sources[sheet])) != (args.railml.sha256, args.worksheet.sha256):
            raise APIError('SOURCE_CHANGED', 'The RailML or native facility worksheet differs from its checksum')
        target = project_target(self, args)

        def recheck():
            if any(self.secure_bytes(path) != data for path, data in sources.items()):
                raise APIError('SOURCE_CHANGED', 'The RailML or native facility worksheet changed during application')

        try:
            output, stations, report = apply_facilities(sources[railml], sources[sheet], args.tracks,
                                                        args.signals, args.stations)
        except (ValueError, KeyError, IndexError, TypeError, OverflowError, ExpatError) as exc:
            raise APIError('RAILML_FACILITY_MAPPING', str(exc)[:500]) from exc
        members = {sheet.name: output}
        if stations is not None:
            members['FacilityCatalog.stations'] = stations
        if any(len(raw) > MAX_MEMBER_BYTES for raw in members.values()):
            raise APIError('ARCHIVE_SIZE', 'Generated native facility member exceeds 20 MiB')
        result = {'saved': False, 'preview_only': args.preview_only,
                  'railml_sha256': sha(sources[railml]), 'worksheet_sha256': sha(sources[sheet]),
                  'native_application_started': False,
                  'members': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in members.items()}, **report}
        if args.source_project is not None:
            from .infrastructure_railml_project import publish_facility_project

            return publish_facility_project(self, args, target, sheet, sources[sheet], output, stations, result, recheck)
        if args.preview_only:
            recheck()
            return result
        return publish_candidate(self, target, members, result, recheck, require_run=False)

    def cross_platform_sources(self, args):
        inputs, documents, paths = {}, {}, {}

        def read_source(binding, suffixes):
            path = self.path(binding.path)
            if path.suffix.casefold() not in suffixes:
                raise APIError('RAILML_CROSS_PLATFORM_FORMAT', 'Expected a native worksheet/catalog or RailML XML')
            raw = self.secure_bytes(path)
            if sha(raw) != binding.sha256:
                raise APIError('SOURCE_CHANGED', 'A cross-worksheet platform input differs from its exact checksum', path.name)
            inputs[path] = raw
            return path, raw

        station_path, station_data = read_source(args.stations_catalog, {'.stations'})
        for binding in args.documents:
            path, raw = read_source(binding, {'.opentrack'})
            require_key = path.stem.casefold()
            if any(key.casefold() == require_key for key in paths):
                raise APIError('RAILML_CROSS_PLATFORM_FORMAT', 'Worksheet basenames must be distinct')
            paths[path.stem] = path.name
            documents[path.stem] = raw
        return read_source, inputs, station_path, station_data, documents, paths

    def cross_document_platform(self, args):
        from .infrastructure_railml_cross_platform import apply_cross_platform

        read_source, inputs, station_path, station_data, documents, paths = self.cross_platform_sources(args)
        xml, data = read_source(args.railml, RAILML_SUFFIXES)
        target = project_target(self, args)
        try:
            sheets, stations, report = apply_cross_platform(data, documents, paths, station_data, args.track, args.station)
        except (ValueError, KeyError, IndexError, TypeError, OverflowError, ExpatError) as exc:
            raise APIError('RAILML_CROSS_PLATFORM_MAPPING', str(exc)[:500]) from exc

        def recheck():
            if any(self.secure_bytes(path) != raw for path, raw in inputs.items()):
                raise APIError('SOURCE_CHANGED', 'Cross-worksheet platform inputs changed during publication')

        members = {paths[key]: raw for key, raw in sheets.items()}
        members[station_path.name] = stations
        if any(len(raw) > MAX_MEMBER_BYTES for raw in members.values()):
            raise APIError('ARCHIVE_SIZE', 'Cross-worksheet platform writes exceed 20 MiB per native member')
        result = {'saved': False, 'preview_only': args.preview_only, 'native_application_started': False,
                  'railml_sha256': sha(inputs[xml]), 'worksheet_sha256': {key: sha(raw) for key, raw in documents.items()},
                  'stations_source_sha256': sha(station_data),
                  'members': {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in members.items()}, **report}
        if args.preview_only:
            recheck()
            return result
        return publish_candidate(self, target, members, result, recheck, require_run=False)

    def export_cross_document_platform(self, args):
        from .infrastructure_railml_cross_platform_export import export_cross_platform

        _, inputs, station_path, catalog, documents, paths = self.cross_platform_sources(args)
        target = self.path(args.target_path) if args.target_path is not None else None
        if target is not None and target.suffix.casefold() not in RAILML_SUFFIXES:
            raise APIError('RAILML_CROSS_PLATFORM_FORMAT', 'Use a new XML or .railml target')
        try:
            output, report = export_cross_platform(documents, paths, catalog, args.track, args.station,
                                                   args.speed_train_type, speed_profiles=speed_profile_map(args.speed_profiles))
        except (ValueError, KeyError, IndexError, TypeError, OverflowError, ExpatError) as exc:
            raise APIError('RAILML_CROSS_PLATFORM_EXPORT', str(exc)[:500]) from exc
        result = {'saved': False, 'preview_only': args.preview_only, 'native_application_started': False,
                  'worksheet_sha256': {key: sha(data) for key, data in documents.items()},
                  'station_catalog_sha256': sha(catalog), 'output_sha256': sha(output), 'output_bytes': len(output), **report}
        if args.preview_only:
            if any(self.secure_bytes(path) != raw for path, raw in inputs.items()):
                raise APIError('SOURCE_CHANGED', 'A cross-worksheet platform export source changed during preview')
            return result
        return self.save_copy(station_path, catalog, output, result, args.target_path,
                              additional_inputs={path: raw for path, raw in inputs.items() if path != station_path},
                              validate_output=railml_inventory)

    def rebuild_railml_corridor(self, args):
        from .infrastructure_railml_rebuild import rebuild_corridor

        return self._rebuild_railml_project(args, rebuild_corridor, 'corridor')

    def rebuild_railml_station(self, args):
        from .infrastructure_railml_station_rebuild import rebuild_station

        return self._rebuild_railml_project(args, rebuild_station, 'station')

    def _rebuild_railml_project(self, args, builder, kind):
        target = project_target(self, args, args.execution_root)
        payload, sources = {}, {}
        for role in ('railml', 'header_document', 'shapes'):
            binding = getattr(args, role)
            path = self.path(binding.path)
            allowed = RAILML_SUFFIXES if role == 'railml' else {'.opentrack'}
            if role != 'shapes' and path.suffix.casefold() not in allowed:
                raise APIError('RAILML_REBUILD_FORMAT', 'Select an original RailML input and original-format worksheet header')
            data = self.secure_bytes(path)
            if sha(data) != binding.sha256 or (path in sources and sources[path] != data):
                raise APIError('SOURCE_CHANGED', f'RailML {kind} rebuild input differs from its pinned checksum', role)
            if target is not None and path.is_relative_to(target):
                raise APIError('PROJECT_TARGET_BINDING', f'The new {kind} target cannot enclose a source file')
            sources[path], payload[role] = data, data
        try:
            files, report = builder(payload['railml'], payload['header_document'], payload['shapes'], args,
                                    speed_profile_map(args.speed_profiles))
        except (ValueError, TypeError, IndexError, KeyError, OverflowError, ExpatError) as exc:
            raise APIError(f'RAILML_{kind.upper()}_REBUILD', str(exc)[:600]) from exc

        def recheck():
            if any(self.secure_bytes(path) != data for path, data in sources.items()):
                raise APIError('SOURCE_CHANGED', f'A reviewed RailML {kind} source changed during publication')

        result = {'preview_only': args.preview_only, 'saved': False, 'publication_review_pending': True,
                  'native_application_started': False, 'native_runtime_ready': False,
                  'source_bindings': {role: getattr(args, role).model_dump() for role in payload},
                  'members': {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in files.items()}, **report}
        recheck()
        if args.preview_only:
            return result
        return publish_candidate(self, target, files, result, recheck)

    def export_facilities(self, args):
        from .infrastructure_railml_export import export_facilities
        from .infrastructure_railml_geometry import export_geometry

        bindings = {'worksheet': args.worksheet}
        if args.template_railml is not None:
            bindings['template_railml'] = args.template_railml
        suffixes = {'template_railml': RAILML_SUFFIXES, 'worksheet': {'.opentrack'}, 'stations_catalog': {'.stations'}}
        if args.stations_catalog is not None:
            bindings['stations_catalog'] = args.stations_catalog
        sources, data = {}, {}
        for role, binding in bindings.items():
            source = self.path(binding.path)
            if source.suffix.casefold() not in suffixes[role]:
                raise APIError('RAILML_FACILITY_FORMAT', 'Select the original native or RailML member type', role)
            sources[role] = source
            data[role] = self.secure_bytes(source)
            if sha(data[role]) != binding.sha256:
                raise APIError('SOURCE_CHANGED', 'RailML facility export input differs from its checksum', role)
        target = self.path(args.target_path) if args.target_path is not None else None
        if target is not None and target.suffix.casefold() not in RAILML_SUFFIXES:
            raise APIError('RAILML_FACILITY_FORMAT', 'Use an XML or .railml target for the native facility export')
        try:
            template = data.get('template_railml')
            geometry_report = None
            if template is None:
                sheet = sources['worksheet']
                for track in args.tracks:
                    GeometryTrackBinding.model_validate(track.model_dump())
                template, geometry_report = export_geometry({sheet.stem: data['worksheet']}, {sheet.stem: sheet.name},
                                                           [(sheet.stem, track) for track in args.tracks],
                                                           args.speed_train_type, speed_profiles=speed_profile_map(args.speed_profiles))
            output, report = export_facilities(template, data['worksheet'], data.get('stations_catalog'),
                                                 args.tracks, args.signals, args.stations)
        except (ValueError, KeyError, IndexError, TypeError, OverflowError, ExpatError) as exc:
            raise APIError('RAILML_FACILITY_EXPORT', str(exc)[:500]) from exc
        if geometry_report is not None:
            report.update(geometry_template_preserved=False, fresh_geometry=geometry_report)
        result = {'saved': False, 'preview_only': args.preview_only,
                  'input_sha256': {role: sha(blob) for role, blob in data.items()},
                  'output_sha256': sha(output), 'output_bytes': len(output), 'native_application_started': False, **report}
        if args.preview_only:
            if any(self.secure_bytes(path) != data[role] for role, path in sources.items()):
                raise APIError('SOURCE_CHANGED', 'An export source changed during the preview')
            return result
        primary = 'template_railml' if args.template_railml is not None else 'worksheet'
        return self.save_copy(sources[primary], data[primary], output, result, args.target_path,
                              additional_inputs={sources[role]: data[role] for role in data if role != primary},
                              validate_output=railml_inventory)

    def export_geometry(self, args):
        from .infrastructure_railml_geometry import export_geometry

        sources, data, bindings = {}, {}, []
        for selection in args.documents:
            path = self.path(selection.path)
            key = path.stem
            if path.suffix != '.opentrack' or any(key.casefold() == name.casefold() for name in sources):
                raise APIError('RAILML_GEOMETRY_FORMAT', 'Supply ordinary .opentrack files with unique worksheet basenames')
            data[key] = self.secure_bytes(path)
            sources[key] = path
            if sha(data[key]) != selection.sha256:
                raise APIError('SOURCE_CHANGED', 'RailML geometry export source differs from its checksum', key)
            bindings.extend((key, track) for track in selection.tracks)
        target = self.path(args.target_path) if args.target_path is not None else None
        if target is not None and target.suffix.casefold() not in RAILML_SUFFIXES:
            raise APIError('RAILML_GEOMETRY_FORMAT', 'Use an XML or .railml target for the native geometry export')
        try:
            output, report = export_geometry(data, {name: path.name for name, path in sources.items()},
                                             bindings, args.speed_train_type, speed_profiles=speed_profile_map(args.speed_profiles))
        except (ValueError, KeyError, IndexError, TypeError, OverflowError, ExpatError) as exc:
            raise APIError('RAILML_GEOMETRY_EXPORT', str(exc)[:500]) from exc
        result = {'saved': False, 'preview_only': args.preview_only, 'native_application_started': False,
                  'input_sha256': {key: sha(blob) for key, blob in data.items()},
                  'output_sha256': sha(output), 'output_bytes': len(output), **report}
        if args.preview_only:
            if any(self.secure_bytes(path) != data[name] for name, path in sources.items()):
                raise APIError('SOURCE_CHANGED', 'A native worksheet changed during geometry export preview')
            return result
        primary = next(iter(sources))
        return self.save_copy(sources[primary], data[primary], output, result, args.target_path,
                              additional_inputs={sources[name]: blob for name, blob in data.items() if name != primary},
                              validate_output=railml_inventory)


def tool_definitions(root):
    service = InfrastructureRailMLTools(root)
    return [('opentrack_convert_native_railml_infrastructure',
             'Use the original installed OpenTrack RailML bridge to convert between RailML 2.2 '
             'and native GModel .plist or .opentrackgmodel worksheets. Review geometry readback and save a fresh copy. '
             'Optional geometry_only projection prepares the geometry stage for mapped native facility writing. '
             'Requires local Java; no simulation or desktop application launch.',
             ConvertInfrastructure, service.convert, False, False),
            ('opentrack_materialize_native_gmodel_worksheet',
             'Build an ordinary editable .opentrack worksheet from original GModel track topology. '
             'Includes reciprocal pairs, turnout branch ordering, safety groups and directional speed profiles. '
             'Requires current worksheet and shape donors. Active signals, stations, routes and cross-document links require other tools.',
             MaterializeGModel, service.materialize, False, False),
            ('opentrack_apply_native_railml_facilities',
             'Write selected RailML 2.2 OCP, cross section, platform, optional stop post and mapped directional signal '
             'identities into an ordinary native worksheet and station catalog using surveyed Edge and End bindings. '
             'Supports contiguous directional stopping areas, separate platform tracks sharing a native StationModel, '
             'and native point stations. Optional source_project saves the mapped worksheet and its StationFile '
             'together in a fresh complete pre-service project while preserving its stock and service catalogues.',
             ApplyFacilities, service.facilities, False, False),
            ('opentrack_apply_native_railml_cross_document_platform',
             'Write one continuous RailML station platform along ordered reciprocal connectors in native worksheets. '
             'Uses one catalog identity, worksheet-local StationModels and a matched directional exit. '
             'Matches represented through blocks against exact existing advance-reservation Routes.',
             ApplyCrossDocumentPlatform, service.cross_document_platform, False, False),
            ('opentrack_export_native_railml_cross_document_platform',
             'Export an ordered native worksheet corridor and one platform to a continuous RailML 2.2 track. '
             'Verify directed facility bindings, reciprocal boundary positions and native worksheet readback.',
             ExportCrossDocumentPlatform, service.export_cross_document_platform, False, False),
            ('opentrack_rebuild_native_railml_corridor',
             'Generate fresh native worksheets and reciprocal connectors from one measured RailML 2.2 track and explicit '
             'worksheet chainage partitions. Rebuild a directed platform, its signals and the native through Routes it '
             'requires. Publish a complete pre-service project using a structural header and native classes. '
             'No original topology or archived movement input is required.',
             RebuildRailMLCorridor, service.rebuild_railml_corridor, False, False),
            ('opentrack_rebuild_native_railml_station',
             'Generate native multi-worksheet geometry, facing turnout legs, reciprocal worksheet connectors, signals '
             'and mapped station platforms from reviewed RailML 2.2 partitions. Publish a pre-service project for native '
             'Route and service authoring.',
             RebuildRailMLStation, service.rebuild_railml_station, False, False),
            ('opentrack_export_native_railml_facilities',
             'Export native point stations, contiguous whole-Edge stopping areas, and mapped directional signals into a RailML 2.2 '
             'geometry template or freshly generated single-worksheet geometry using explicit native End and RailML identities. '
             'Verify mapped native facility reimport before publication.',
             ExportFacilities, service.export_facilities, False, False),
            ('opentrack_export_native_railml_geometry',
             'Export fresh RailML 2.2 geometry from explicitly oriented ordinary native worksheet tracks. '
             'Includes explicit ETCS speed category mappings, simple turnouts and reciprocal local or cross-worksheet links.',
             ExportGeometry, service.export_geometry, False, False)]
