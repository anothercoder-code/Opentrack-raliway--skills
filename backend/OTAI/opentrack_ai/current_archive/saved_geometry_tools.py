"""Native saved infrastructure editing entrypoint."""

from pathlib import Path, PureWindowsPath
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from ..errors import APIError
from . import catalogs, incident_operations, writer
from .bundle_tools import CourseBundles, Source
from .graphic_alignment import GraphicPlacement
from .infrastructure_incidents.core import number_value
from .itinerary_edit_tools import bound_dest_catalog, run_infrastructure_paths
from .multi_document_tools import Ref
from .next_tools import NextFunctions, Ordinal
from .operation_tools import Name, RouteSelector
from .project_candidate_publication import ProjectSave
from .route_fetch_tools import ReviewedName
from .saved_geometry import inspect_vertex, project_from, transform
from .saved_rich_labels import RGB
from .station_reference_edit import EndpointLinkReview, SavedFormationEventReview
from .tools import Input, PathText, sha


Coordinate = Annotated[StrictInt | StrictFloat, Field(allow_inf_nan=False)]
Metres = Annotated[StrictInt, Field(ge=1, lt=2147483647)]


class MoveVertex(Input):
    action: Literal['move_vertex']
    end_id: Ordinal
    x: Coordinate
    y: Coordinate


class InspectVertex(Input):
    source_path: PathText
    end_id: Ordinal


VertexName = Annotated[StrictStr, Field(max_length=200, pattern=r'^[ -~]*$')]
Kilometre = Annotated[StrictInt | StrictFloat, Field(ge=-10000, le=10000, allow_inf_nan=False)]
SwitchSeconds = Annotated[StrictInt | StrictFloat, Field(ge=0, le=3600, allow_inf_nan=False)]


class VertexChanges(Input):
    name: VertexName | None = None
    kilometre_point: Kilometre | None = None
    switch_time_s: SwitchSeconds | None = None
    default_second_leg: StrictBool | None = None

    @model_validator(mode='after')
    def explicit_changes(self):
        if not self.model_fields_set:
            raise ValueError('Provide at least one explicit saved vertex field')
        if any(getattr(self, key) is None for key in self.model_fields_set - {'kilometre_point'}):
            raise ValueError('Only the kilometre point can be explicitly cleared')
        return self


class SetVertexDetails(Input):
    action: Literal['set_vertex_details']
    end_id: Ordinal
    both_halves: StrictBool = False
    changes: VertexChanges


SignalSightMetres = Annotated[StrictInt, Field(ge=1, le=100000)]


class SetSignalSight(Input):
    action: Literal['set_signal_sight']
    end_id: Ordinal
    signal_id: Ordinal
    expected_sight_m: SignalSightMetres
    sight_m: SignalSightMetres


class ReviewedTerminalOverlap(Input):
    shunting: Ref
    edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=1000)]


class ConnectorEnd(Input):
    document: Name
    end_id: Ordinal


class CrossingSlowZone(Input):
    start: ConnectorEnd
    finish: ConnectorEnd
    expected_speed_kmh: Annotated[StrictInt, Field(ge=10, le=300)]


class ReviewedSlowZoneSplit(CrossingSlowZone):
    expected_native_aspect_code: Annotated[StrictInt, Field(ge=1, le=1300)]
    expected_head_only: StrictBool


class ReviewedRouteSplitTiming(Input):
    release_distance_m: Annotated[StrictInt, Field(ge=0, le=2147483647)]
    announce_distance_m: Literal[400]
    release_time_s: Annotated[StrictInt, Field(ge=0, le=86400)]
    reserve_time_s: Annotated[StrictInt, Field(ge=0, le=86400)]
    approach_length_m: Annotated[Coordinate, Field(ge=0, le=10000000)]
    approach_speed_kmh: Annotated[Coordinate, Field(ge=0, le=1000)]
    reservation_distance_m: Annotated[StrictInt, Field(ge=0, le=2147483647)]
    use_reservation_distance: StrictBool
    use_release_distance: StrictBool
    release_group_starts: Annotated[list[ConnectorEnd], Field(min_length=1, max_length=1000)]
    allow_delayed_prefix_retry: StrictBool = False
    parallel_overlap_preparation: StrictBool = False
    preserve_occupied_terminal_approach: StrictBool = False


class ReviewedOccupiedEntry(Input):
    terminal_end: ConnectorEnd
    stop_edge_id: Ordinal
    expected_speed_kmh: Annotated[StrictFloat | StrictInt, Field(gt=0, le=1000, allow_inf_nan=False)]


class ReviewedOccupiedEntrySplit(ReviewedOccupiedEntry):
    expected_speed_kmh: Annotated[StrictFloat | StrictInt, Field(gt=0, le=1000, allow_inf_nan=False)] | None = None
    expected_wait_s: Annotated[StrictInt, Field(gt=0, le=86400)] | None = None
    expected_safety_element_id: Ordinal
    receiver_course: Name
    donor_course: Name
    station_sign: Name
    formation_events: Annotated[list[SavedFormationEventReview], Field(min_length=1, max_length=1000)] | None = None
    turnrounds: Annotated[list[EndpointLinkReview], Field(min_length=1, max_length=1000)] | None = None

    @model_validator(mode='after')
    def complete_formation_reviews(self):
        if (self.expected_speed_kmh is None) == (self.expected_wait_s is None):
            raise ValueError('Review exactly one occupied-entry speed or zero-speed wait')
        if (self.formation_events is None) != (self.turnrounds is None):
            raise ValueError('Provide the complete formation and turnround reviews together')
        return self


OperatingHash = Annotated[StrictStr, Field(pattern=r'^[0-9a-f]{64}$')]


class PlatformOperatingHashes(Input):
    courses: OperatingHash
    timetable: OperatingHash
    trains: OperatingHash
    depot: OperatingHash
    stations: OperatingHash


class ReviewedSplitRouteSpeedIncident(Input):
    name: ReviewedName
    path: Ref
    expected_speed_kmh: Annotated[StrictInt | StrictFloat, Field(gt=0, le=10000, allow_inf_nan=False)]


class ReviewedPrecedingFixedSlowZone(Input):
    route: Ref
    zone: ReviewedSlowZoneSplit


class MainSignalRouteSplit(Input):
    route: Ref
    continued_name: ReviewedName
    expected_upstream_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=500)]
    expected_downstream_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=500)]
    reserve_with_previous: StrictBool = True
    terminal_overlap: ReviewedTerminalOverlap | None = None
    occupied_entry: ReviewedOccupiedEntrySplit | None = None
    slow_zone: ReviewedSlowZoneSplit | None = None
    preceding_fixed_slow_zone: ReviewedPrecedingFixedSlowZone | None = None
    timing: ReviewedRouteSplitTiming | None = None
    route_span_incident_rebindings: 'SpanIncidentRebindings' = Field(default_factory=list)
    route_speed_incident_to_path: ReviewedSplitRouteSpeedIncident | None = None

    @model_validator(mode='after')
    def supported_protection_combinations(self):
        if self.route_speed_incident_to_path is not None and (self.route_span_incident_rebindings
                or not self.reserve_with_previous or any(item is not None for item in
                    (self.terminal_overlap, self.occupied_entry, self.slow_zone, self.timing))):
            raise ValueError('Preserving an entire Route-speed Incident requires ordinary synchronized reservation and no other protection')
        if self.route_span_incident_rebindings and (not self.reserve_with_previous or any(
                item is not None for item in (self.terminal_overlap, self.occupied_entry, self.slow_zone, self.timing))):
            raise ValueError('Preserving a Route-span Incident requires ordinary synchronized reservation and default Route protection')
        if self.occupied_entry is not None and any(
            item is not None for item in (self.terminal_overlap, self.slow_zone)
        ):
            raise ValueError('An occupied-entry split requires separate review from a terminal overlap or a slow zone')
        if self.preceding_fixed_slow_zone is not None and (self.occupied_entry is None or self.reserve_with_previous
                or self.preceding_fixed_slow_zone.route == self.route):
            raise ValueError('A fixed slow predecessor must be a distinct original Route before an independent occupied entry')
        if (self.slow_zone is not None and self.terminal_overlap is not None
                and (self.timing is not None or not self.reserve_with_previous)):
            raise ValueError('Fixed slow zone and terminal overlap require synchronized reservation and default Route timing')
        if self.timing is not None:
            delayed_slow_prefix = self.slow_zone is not None and self.timing.reserve_time_s > 0
            if self.timing.allow_delayed_prefix_retry != delayed_slow_prefix:
                raise ValueError('Review delayed prefix retry exactly for a slow-zone split with a positive reservation delay')
            parallel = self.terminal_overlap is not None and self.timing.reserve_time_s > 0
            if self.timing.parallel_overlap_preparation != parallel or (parallel and not self.reserve_with_previous):
                raise ValueError('Review parallel overlap preparation exactly for a synchronized terminal overlap with positive reservation delay')
            if self.timing.preserve_occupied_terminal_approach and (self.occupied_entry is None or self.reserve_with_previous
                    or self.timing.approach_length_m <= 0 or self.timing.approach_speed_kmh <= 0):
                raise ValueError('Review a positive terminal approach only with independent occupied entry')
        return self


class SetEdgeExclusion(Input):
    action: Literal['set_edge_exclusion']
    edge_id: Ordinal
    expected_target_edge_id: Ordinal | None
    target_edge_id: Ordinal | None
    expected_target_source_edge_id: Ordinal | None = None


class PlatformHaltSignalReview(Input):
    signal_id: Ordinal
    end_id: Ordinal
    signal_type: Ordinal


class PlatformHaltPlacement(Input):
    end_id: Ordinal
    signal_name: Name
    stop_reference: Literal['head', 'center', 'tail', 'length']
    maximum_length_for_marker_m: Annotated[StrictInt, Field(ge=10, le=1000)] | None = None
    expected_position_from_entry_m: Metres
    graphic_offset_x: Coordinate = 0
    graphic_offset_y: Coordinate = 0

    @model_validator(mode='after')
    def length_only(self):
        from .signal_type_workflow.core import STOP_LENGTHS
        if self.stop_reference == 'length':
            if self.maximum_length_for_marker_m not in STOP_LENGTHS.values():
                raise ValueError('Select a native discrete train length for the halt marker')
        elif self.maximum_length_for_marker_m is not None:
            raise ValueError('Only a train-length marker accepts maximum_length_for_marker_m')
        return self


class TerminalHaltPlatform(Input):
    station_id: Ordinal
    arrival_route: Ref
    platform_entry_end_id: Ordinal
    station_reference_end_id: Ordinal | None
    expected_buffer_end_id: Ordinal
    expected_buffer_signal_id: Ordinal | None
    expected_platform_edge_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=100)]


class CreateTerminalStationHaltSignals(TerminalHaltPlatform):
    action: Literal['create_terminal_station_halt_signals']
    expected_halt_signals: Annotated[list[PlatformHaltSignalReview], Field(max_length=100)]
    maximum_train_length_m: Annotated[StrictInt, Field(gt=0, le=10000)] | None = None
    markers: Annotated[list[PlatformHaltPlacement], Field(min_length=1, max_length=32)]
    signal_donor: Source
    donor_signal_id: Ordinal


PlatformDistance = Annotated[StrictInt | StrictFloat, Field(ge=0, allow_inf_nan=False)]


class PlatformResizeVisit(Input):
    course_id: Name
    visit_index: Ordinal
    expected_train_length_m: PlatformDistance
    expected_reference_distance_m: PlatformDistance
    expected_head_distance_m: PlatformDistance
    expected_available_length_m: PlatformDistance
    replacement_reference_distance_m: PlatformDistance
    replacement_head_distance_m: PlatformDistance
    replacement_available_length_m: PlatformDistance


class HaltRelocationVisit(PlatformResizeVisit):
    expected_tail_distance_m: PlatformDistance
    replacement_tail_distance_m: PlatformDistance


class HaltRelocationReview(Input):
    operating_sha256: PlatformOperatingHashes | None = None
    visit_reviews: Annotated[list[HaltRelocationVisit], Field(max_length=2000)] | None = None

    @model_validator(mode='after')
    def require_complete_review(self):
        if (self.operating_sha256 is None) != (self.visit_reviews is None):
            raise ValueError('Supply the native operating fingerprints together with the reviewed platform visits')
        return self


class CreateStationHaltSignals(HaltRelocationReview):
    action: Literal['create_station_halt_signals']
    station_id: Ordinal
    arrival_route: Ref
    expected_platform_edge_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=100)]
    expected_halt_signals: Annotated[list[PlatformHaltSignalReview], Field(max_length=100)]
    maximum_train_length_m: Annotated[StrictInt, Field(gt=0, le=10000)] | None = None
    markers: Annotated[list[PlatformHaltPlacement], Field(min_length=1, max_length=32)]
    signal_donor: Source
    donor_signal_id: Ordinal


class ReviewedStationHaltMove(Input):
    station_id: Ordinal
    signal_id: Ordinal
    from_end_id: Ordinal
    to_end_id: Ordinal
    arrival_route: Ref
    expected_platform_edge_ids: Annotated[list[Ordinal], Field(min_length=3, max_length=100)]
    expected_stop_shift_m: Annotated[StrictInt, Field(gt=-2147483647, lt=2147483647)]
    expected_halt_signals: Annotated[list[PlatformHaltSignalReview], Field(min_length=1, max_length=100)] | None = None


class RelocateStationHaltSignal(HaltRelocationReview, ReviewedStationHaltMove):
    action: Literal['relocate_station_halt_signal']


class RelocateTerminalStationHaltSignal(HaltRelocationReview, TerminalHaltPlatform):
    action: Literal['relocate_terminal_station_halt_signal']
    signal_id: Ordinal
    from_end_id: Ordinal
    to_end_id: Ordinal
    expected_stop_shift_m: Annotated[StrictInt, Field(gt=-2147483647, lt=2147483647)]
    expected_halt_signals: Annotated[list[PlatformHaltSignalReview], Field(min_length=1, max_length=100)]


class JointStationHaltMove(ReviewedStationHaltMove):
    visit_reviews: Annotated[list[HaltRelocationVisit], Field(max_length=2000)]


class VacatedBlockSafety(Input):
    element_id: Ordinal
    expected_member_end_ids: Annotated[list[Ordinal], Field(min_length=4, max_length=200)]
    upstream_member_end_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=100)]
    downstream_member_end_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=100)]


class CreateMainSignal(Input):
    action: Literal['create_main_signal']
    end_id: Ordinal
    signal_name: ReviewedName
    main_role: Literal['home', 'block', 'exit'] = 'exit'
    placement: GraphicPlacement
    sight_m: SignalSightMetres = 500
    delay_s: Annotated[StrictInt | StrictFloat, Field(ge=0, le=86400, allow_inf_nan=False)] = 0
    show_symbol: StrictBool = True
    show_icon: StrictBool = True
    split_route: MainSignalRouteSplit | None = None
    operating_sha256: PlatformOperatingHashes | None = None
    halt_relocation: JointStationHaltMove | None = None
    vacated_block_safety: VacatedBlockSafety | None = None

    @model_validator(mode='after')
    def reviewed_operating_change(self):
        split = self.split_route
        occupied = split.occupied_entry if split is not None else None
        parallel = split is not None and split.timing is not None and split.timing.parallel_overlap_preparation
        if (occupied is not None or self.halt_relocation is not None or parallel) != (self.operating_sha256 is not None):
            raise ValueError('Supply the five operating archive hashes exactly when reviewing occupied entry, a halt move or parallel overlap preparation')
        if occupied is not None:
            if split.terminal_overlap is not None or split.reserve_with_previous:
                raise ValueError('An occupied-entry split requires separate reservation and no terminal overlap')
            if occupied.receiver_course == occupied.donor_course:
                raise ValueError('Select distinct occupied-entry receiver and donor Courses')
        if self.halt_relocation is not None:
            if split is None or self.main_role != 'block':
                raise ValueError('A simultaneous halt move requires a block signal with a reviewed Route split')
            if split.route_span_incident_rebindings or any(item is not None for item in
                    (occupied, split.terminal_overlap, split.slow_zone, split.timing, split.route_speed_incident_to_path)):
                raise ValueError('A simultaneous halt move requires separate review from other Route protection')
        vacates_block_site = self.halt_relocation is not None and self.end_id == self.halt_relocation.from_end_id
        if vacates_block_site != (self.vacated_block_safety is not None):
            raise ValueError('Review the Safety Element partition exactly when the block replaces the moved halt marker')
        return self


class RelocateMainSignal(Input):
    action: Literal['relocate_main_signal']
    signal_id: Ordinal
    from_end_id: Ordinal
    to_end_id: Ordinal
    direction: Literal['forward', 'backward']
    expected_edge_id: Ordinal


class ReverseEdge(Input):
    action: Literal['reverse_edge']
    edge_id: Ordinal


class CrossingEdge(Input):
    document: Name
    edge_id: Ordinal


IncidentLineName = Annotated[StrictStr, Field(max_length=200)]
IncidentKilometres = Annotated[StrictStr, Field(min_length=1, max_length=32)]


class KilometreIncidentSelector(Input):
    line_id: IncidentLineName
    track_id: IncidentLineName
    begin_km: IncidentKilometres
    end_km: IncidentKilometres


class RouteIncidentSelector(Input):
    begin_route: Name
    end_route: Name
    begin_offset_km: IncidentKilometres
    end_offset_km: IncidentKilometres


class SpanIncidentRebinding(Input):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    expected_selector: KilometreIncidentSelector | RouteIncidentSelector
    replacement_selector: KilometreIncidentSelector | RouteIncidentSelector
    expected_edge_refs: Annotated[list[CrossingEdge], Field(min_length=1, max_length=10000)]
    replacement_edge_refs: Annotated[list[CrossingEdge], Field(min_length=1, max_length=10000)]


SpanIncidentRebindings = Annotated[list[SpanIncidentRebinding], Field(max_length=100)]


class SplitEdge(Input):
    action: Literal['split_edge']
    edge_id: Ordinal
    first_length_m: Metres
    shapes: Source
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)


class SplitPlatformEdge(Input):
    action: Literal['split_platform_edge']
    edge_id: Ordinal
    first_length_m: Metres
    shapes: Source
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)
    station_id: Ordinal


class PlatformReplacementWaypoint(Input):
    distance_from_first_end_m: Metres
    x: Coordinate
    y: Coordinate


class PlatformOccupationReview(Input):
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    expected_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=10000)]


class ReplaceUsedPlatformEdge(Input):
    action: Literal['replace_used_platform_edge']
    station_id: Ordinal
    edge_id: Ordinal
    expected_edge_length_m: Metres
    waypoints: Annotated[list[PlatformReplacementWaypoint], Field(min_length=1, max_length=32)]
    occupation_groups: Annotated[list[PlatformOccupationReview], Field(max_length=100)] = Field(default_factory=list)
    shapes: Source
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)


class StationTrackReplacementSelection(Input):
    edge_id: Ordinal
    expected_edge_length_m: Metres
    station_scope: Literal['platform', 'boundary_approach', 'junction_core']
    waypoints: Annotated[list[PlatformReplacementWaypoint], Field(min_length=1, max_length=32)]
    expected_end_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=2)] | None = None
    expected_safety_element_id: Ordinal | None = None

    @model_validator(mode='after')
    def review_core_edge(self):
        junction_core = self.station_scope == 'junction_core'
        has_ends = self.expected_end_ids is not None
        has_safety_element = self.expected_safety_element_id is not None
        if has_ends != junction_core or has_safety_element != junction_core:
            raise ValueError('A junction core Edge requires both its original Ends and Safety Element')
        return self


class JunctionCoreTurnoutReview(Input):
    end_id: Ordinal
    expected_edge_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=2)]
    expected_default_edge_id: Ordinal
    expected_switch_time_s: SwitchSeconds


class ReplaceUsedStationTrackSet(Input):
    action: Literal['replace_used_station_track_set']
    station_id: Ordinal
    edges: Annotated[list[StationTrackReplacementSelection], Field(min_length=2, max_length=32)]
    occupation_groups: Annotated[list[PlatformOccupationReview], Field(max_length=100)] = Field(default_factory=list)
    shapes: Source
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)
    junction_turnout_reviews: Annotated[list[JunctionCoreTurnoutReview], Field(max_length=64)] = Field(default_factory=list)

    @model_validator(mode='after')
    def turnout_review_scope(self):
        if self.junction_turnout_reviews and not any(edge.station_scope == 'junction_core' for edge in self.edges):
            raise ValueError('Junction turnout reviews require at least one junction core Edge')
        return self


class PlatformResizeEdge(Input):
    edge_id: Ordinal
    expected_length_m: Metres
    length_m: Metres


class PlatformResizeScope(Input):
    arrival_route: Ref
    expected_platform_length_m: Metres
    replacement_platform_length_m: Metres
    visit_reviews: Annotated[list[PlatformResizeVisit], Field(min_length=1, max_length=2000)]


class PlatformResizeOptions(Input):
    operating_sha256: PlatformOperatingHashes
    map_itinerary_safety_margins: StrictBool = False
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)


class PlatformResizeReview(PlatformResizeOptions, PlatformResizeScope):
    pass


class LocalPlatformResizeExtent(Input):
    station_id: Ordinal
    expected_platform_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=120)]
    edges: Annotated[list[PlatformResizeEdge], Field(min_length=1, max_length=32)]


class ResizeUsedPlatformSpan(LocalPlatformResizeExtent, PlatformResizeReview):
    action: Literal['resize_used_platform_span']


class TerminalPlatformResizeExtent(TerminalHaltPlatform):
    edges: Annotated[list[PlatformResizeEdge], Field(min_length=1, max_length=32)]


class ResizeUsedTerminalPlatformSpan(TerminalPlatformResizeExtent, PlatformResizeReview):
    action: Literal['resize_used_terminal_platform_span']


class CutDoubleVertex(Input):
    action: Literal['cut_double_vertex']
    end_id: Ordinal
    second_x: Coordinate
    second_y: Coordinate
    shapes: Source


class TrackEdgeRebinding(Input):
    old_edge_id: Ordinal
    new_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=100)]


class TrackIncidentRebinding(Input):
    document: Name
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    expected_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=256)]
    edge_rebindings: Annotated[list[TrackEdgeRebinding], Field(min_length=1, max_length=100)]


TrackIncidentRebindings = Annotated[list[TrackIncidentRebinding], Field(max_length=100)]


class CrossingInstrumentRebinding(Input):
    document: Name
    instrument_id: Ordinal
    expected_end_id: Ordinal
    replacement_end_id: Ordinal | None = None
    expected_edge_ids: Annotated[list[Ordinal], Field(max_length=10000)]
    edge_rebindings: Annotated[list[TrackEdgeRebinding], Field(max_length=100)] = Field(default_factory=list)

    @model_validator(mode='after')
    def selected_change(self):
        if not self.edge_rebindings and self.replacement_end_id in (None, self.expected_end_id):
            raise ValueError('Review changed instrument Edge members, a different owner End, or both')
        return self


InstrumentEdgeRebindings = Annotated[list[CrossingInstrumentRebinding], Field(max_length=100)]


class ReplaceUsedEdge(Input):
    action: Literal['replace_used_edge']
    edge_id: Ordinal
    replacement_edge_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=100)]
    track_incident_rebindings: TrackIncidentRebindings = Field(default_factory=list)
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)


class RerouteUsedTrackSpan(Input):
    action: Literal['reroute_used_track_span']
    start_end_id: Ordinal
    old_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=100)]
    replacement_edge_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=100)]
    expected_replacement_length_m: Metres
    expected_replacement_safety_element_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=100)]
    map_itinerary_safety_margins: StrictBool = False
    retire_original: StrictBool = False
    retire_isolated_end_ids: Annotated[list[Ordinal], Field(max_length=100)] = Field(default_factory=list)
    track_incident_rebindings: TrackIncidentRebindings = Field(default_factory=list)
    instrument_edge_rebindings: InstrumentEdgeRebindings = Field(default_factory=list)
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)

    @model_validator(mode='after')
    def explicit_retirement(self):
        if self.retire_isolated_end_ids and not self.retire_original:
            raise ValueError('Retiring isolated original vertices requires retire_original=true')
        return self


class EditStationArea(Input):
    action: Literal['edit_station_area']
    station_id: Ordinal
    add_end_ids: Annotated[list[Ordinal], Field(max_length=1000)] = Field(default_factory=list)
    remove_end_ids: Annotated[list[Ordinal], Field(max_length=1000)] = Field(default_factory=list)


class ConvertStationReference(Input):
    action: Literal['convert_station_reference']
    end_id: Ordinal
    station_id: Ordinal
    area_end_ids: Annotated[list[Ordinal], Field(max_length=64)] = Field(default_factory=list)


class InsertVertex(Input):
    action: Literal['insert_vertex']
    x: Coordinate
    y: Coordinate
    orientation: Literal['horizontal', 'vertical']
    names: Annotated[list[VertexName], Field(min_length=2, max_length=2)]
    shapes: Source


TwoEnds = Annotated[list[Ordinal], Field(min_length=2, max_length=2)]
SpeedKmh = Annotated[StrictInt, Field(ge=1, le=1000)]
TrainType = Annotated[StrictStr, Field(pattern=r'^(0|[1-9][0-9]{0,5})$')]


class EdgeSpeed(Input):
    train_type: TrainType
    speed12_kmh: SpeedKmh
    speed21_kmh: SpeedKmh


class EditUsedEdgeProfile(Input):
    action: Literal['edit_used_edge_profile']
    edge_id: Ordinal
    length_m: Metres | None = None
    radius_m: Coordinate | None = None
    gradient_per_mille: Coordinate | None = None
    speeds: Annotated[list[EdgeSpeed], Field(min_length=1, max_length=100)] | None = None
    map_itinerary_safety_margins: StrictBool = False
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)

    @model_validator(mode='after')
    def check_profile(self):
        if all(value is None for value in (self.length_m, self.radius_m, self.gradient_per_mille, self.speeds)):
            raise ValueError('Supply at least one track profile field')
        if self.radius_m is not None and self.radius_m < 0:
            raise ValueError('Radius must be nonnegative')
        return self


class InsertEdge(Input):
    action: Literal['insert_edge']
    end_ids: TwoEnds
    length_m: Metres
    radius_m: Coordinate = 0.0
    gradient_per_mille: Coordinate = 0.0
    rack_rail: StrictBool = False
    track_name: VertexName = ''
    line_name: VertexName = ''
    remark: VertexName = ''
    speeds: Annotated[list[EdgeSpeed], Field(min_length=1, max_length=100)]
    allow_safety_regroup: StrictBool = False
    shapes: Source


class DeleteEdge(Input):
    action: Literal['delete_edge']
    edge_id: Ordinal
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)


class RechainEdge(Input):
    action: Literal['rechain_edge']
    edge_id: Ordinal
    end_ids: TwoEnds
    allow_safety_regroup: StrictBool = False
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)


class DeleteVertex(Input):
    action: Literal['delete_vertex']
    end_id: Ordinal


class RotateVertex(Input):
    action: Literal['rotate_vertex']
    end_id: Ordinal
    delta_degrees: Literal[-90, 90]


class DrawingStyle(Input):
    width_points: Annotated[StrictInt | StrictFloat, Field(ge=0, le=50000, allow_inf_nan=False)] | None = None
    height_points: Annotated[StrictInt | StrictFloat, Field(ge=0, le=50000, allow_inf_nan=False)] | None = None
    line_width_points: Annotated[StrictInt | StrictFloat, Field(ge=1, le=5, allow_inf_nan=False)] | None = None
    line_rgb: RGB | None = None
    line_flipped: Annotated[StrictBool, Field(description=(
        'For an unrotated Line, choose decreasing Y as X increases when true, increasing Y when false.'))] | None = None
    fill_rgb: RGB | None = None
    filled: StrictBool | None = None

    @model_validator(mode='after')
    def explicit_changes(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError('Supply at least one explicit non-null drawing style field')
        return self


class EditDecoration(Input):
    action: Literal['edit_decoration']
    graphic_id: Ordinal
    delta_x: Coordinate = 0
    delta_y: Coordinate = 0
    text: VertexName | None = None
    drawing_style: DrawingStyle | None = None


class ImportDecoration(Input):
    action: Literal['import_decoration']
    graphic_id: Ordinal
    drawing_donor: Source
    delta_x: Coordinate = 0
    delta_y: Coordinate = 0
    text: VertexName | None = None
    drawing_style: DrawingStyle | None = None


class MergeSafetyElements(Input):
    action: Literal['merge_safety_elements']
    element_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=1000)]


class ResetSafetyElement(Input):
    action: Literal['reset_safety_element']
    element_id: Ordinal


class CrossingSafetyElement(Input):
    document: Name
    element_id: Ordinal


class ReleaseBoundaryRebinding(Input):
    old: ConnectorEnd
    new: ConnectorEnd


class RouteAnchorSubstitution(Input):
    old_end_id: Ordinal
    new_end_id: Ordinal


class RouteAnchorRebinding(Input):
    fragment_owner: ConnectorEnd
    route: RouteSelector
    anchors: Annotated[list[RouteAnchorSubstitution], Field(min_length=1, max_length=100)]


class CrossingExclusionRebinding(Input):
    document: Name
    old_source_edge_id: Ordinal
    old_target_edge_id: Ordinal
    new_source_edge_id: Ordinal
    new_target_edge_id: Ordinal


class CrossingOccupationRebinding(Input):
    document: Name
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    expected_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=10000)]
    edge_rebindings: Annotated[list[TrackEdgeRebinding], Field(min_length=1, max_length=100)]


class CrossingAlignment(Input):
    start_end: ConnectorEnd
    old_edges: Annotated[list[CrossingEdge], Field(min_length=2, max_length=100)]
    replacement_edges: Annotated[list[CrossingEdge], Field(min_length=2, max_length=100)]
    connector_policy: Literal['replace_pair', 'retain_pair'] = 'replace_pair'
    expected_replacement_length_m: Metres
    expected_replacement_safety_elements: Annotated[list[CrossingSafetyElement], Field(min_length=2, max_length=100)]
    release_boundary_rebindings: Annotated[list[ReleaseBoundaryRebinding], Field(max_length=2)] = Field(default_factory=list)
    route_anchor_rebindings: Annotated[list[RouteAnchorRebinding], Field(max_length=100)] = Field(default_factory=list)

    @model_validator(mode='after')
    def retained_boundary(self):
        if self.connector_policy == 'retain_pair' and self.release_boundary_rebindings:
            raise ValueError('A retained connector pair has no release boundary to rebind to another connector')
        return self


class CrossingReroute(CrossingAlignment):
    exclusion_link_rebindings: Annotated[list[CrossingExclusionRebinding], Field(max_length=100)] = Field(default_factory=list)
    occupation_group_rebindings: Annotated[list[CrossingOccupationRebinding], Field(max_length=100)] = Field(default_factory=list)
    map_itinerary_safety_margins: StrictBool = False
    retire_original: StrictBool = False
    retire_isolated_ends: Annotated[list[ConnectorEnd], Field(max_length=100)] = Field(default_factory=list)

    @model_validator(mode='after')
    def exact_retirement(self):
        if self.retire_isolated_ends and not self.retire_original:
            raise ValueError('Select original crossing retirement before removing isolated interior Ends')
        return self


class RerouteCrossDocumentTrackSpan(CrossingReroute):
    action: Literal['reroute_cross_document_track_span']
    track_incident_rebindings: TrackIncidentRebindings = Field(default_factory=list)
    instrument_edge_rebindings: InstrumentEdgeRebindings = Field(default_factory=list)
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)


class CrossingTurnoutUpdate(Input):
    end: ConnectorEnd
    expected_edge_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=2)]
    expected_default_edge_id: Ordinal
    expected_switch_time_s: SwitchSeconds
    default_edge_id: Ordinal
    switch_time_s: SwitchSeconds


class RerouteMultiDocumentTrackSpan(Input):
    action: Literal['reroute_multi_document_track_span']
    witness_itinerary: Name
    expected_witness_length_m: Metres
    crossings: Annotated[list[CrossingReroute], Field(min_length=2, max_length=12)]
    exclusion_link_rebindings: Annotated[list[CrossingExclusionRebinding], Field(max_length=100)] = Field(default_factory=list)
    occupation_group_rebindings: Annotated[list[CrossingOccupationRebinding], Field(max_length=100)] = Field(default_factory=list)
    turnout_updates: Annotated[list[CrossingTurnoutUpdate], Field(max_length=100)] = Field(default_factory=list)
    track_incident_rebindings: TrackIncidentRebindings = Field(default_factory=list)
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)

    @model_validator(mode='after')
    def distinct_dependency_scope(self):
        if (self.exclusion_link_rebindings or self.occupation_group_rebindings) and any(
                row.exclusion_link_rebindings or row.occupation_group_rebindings for row in self.crossings):
            raise ValueError('Review crossing dependencies at batch scope or individual crossing scope')
        return self


class JunctionCrossing(CrossingAlignment):
    routes: Annotated[list[Ref], Field(min_length=1, max_length=100)]


class RetainedJunctionExclusion(Input):
    document: Name
    source_edge_id: Ordinal
    target_edge_id: Ordinal


class JunctionOccupationExtension(Input):
    document: Name
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    expected_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=10000)]
    added_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=100)]
    insert_before_edge_id: Ordinal | None = None


class LocalJunctionAlignment(Input):
    start_end_id: Ordinal
    old_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=100)]
    replacement_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=100)]
    expected_replacement_length_m: Metres
    expected_replacement_safety_element_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=100)]
    routes: Annotated[list[Ref], Field(min_length=1, max_length=100)]
    route_anchor_rebindings: Annotated[list[RouteAnchorRebinding], Field(max_length=100)] = Field(default_factory=list)


class ScopedLocalJunctionAlignment(LocalJunctionAlignment):
    document: Name


class RerouteJunctionTrackSpans(Input):
    action: Literal['reroute_junction_track_spans']
    crossings: Annotated[list[JunctionCrossing], Field(min_length=1, max_length=12)]
    local_alignments: Annotated[list[ScopedLocalJunctionAlignment], Field(max_length=11)] = Field(default_factory=list)
    witness_itineraries: Annotated[dict[Name, Metres], Field(min_length=1, max_length=100)]
    exclusion_link_rebindings: Annotated[list[CrossingExclusionRebinding], Field(max_length=100)] = Field(default_factory=list)
    occupation_group_rebindings: Annotated[list[CrossingOccupationRebinding], Field(max_length=100)] = Field(default_factory=list)
    retained_exclusion_links: Annotated[list[RetainedJunctionExclusion], Field(max_length=100)] = Field(default_factory=list)
    occupation_group_extensions: Annotated[list[JunctionOccupationExtension], Field(max_length=100)] = Field(default_factory=list)
    instrument_edge_rebindings: InstrumentEdgeRebindings = Field(default_factory=list)
    track_incident_rebindings: TrackIncidentRebindings = Field(default_factory=list)
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)
    turnout_updates: Annotated[list[CrossingTurnoutUpdate], Field(max_length=100)] = Field(default_factory=list)
    map_itinerary_safety_margins: StrictBool = False
    retire_original: StrictBool = False
    retire_edges: Annotated[list[CrossingEdge], Field(max_length=1200)] = Field(default_factory=list)
    retire_isolated_ends: Annotated[list[ConnectorEnd], Field(max_length=100)] = Field(default_factory=list)

    @model_validator(mode='after')
    def bound_single_crossing(self):
        if self.local_alignments:
            if len(self.crossings) + len(self.local_alignments) > 12:
                raise ValueError('Mixed junctions support up to twelve reviewed spans')
            if self.retire_original and self.retire_edges:
                raise ValueError('Choose all former-only track or a list of exact former Edge IDs')
            if self.retire_isolated_ends and not (self.retire_original or self.retire_edges):
                raise ValueError('Select former track retirement before removing its isolated vertices')
        elif self.retire_edges:
            raise ValueError('Explicit selective retirement is supported for a mixed local and crossing edit')
        elif len(self.crossings) == 1:
            crossing = self.crossings[0]
            if crossing.connector_policy != 'retain_pair' or len(crossing.routes) != 1 or self.retire_original or self.retire_isolated_ends:
                raise ValueError('Select one Route and retain the connector and original infrastructure for a single crossing')
        return self


class RerouteLocalJunctionTrackSpans(Input):
    action: Literal['reroute_local_junction_track_spans']
    alignments: Annotated[list[LocalJunctionAlignment], Field(min_length=1, max_length=12)]
    witness_itineraries: Annotated[dict[Name, Metres], Field(min_length=1, max_length=100)]
    exclusion_link_rebindings: Annotated[list[CrossingExclusionRebinding], Field(max_length=100)] = Field(default_factory=list)
    retained_exclusion_links: Annotated[list[RetainedJunctionExclusion], Field(max_length=100)] = Field(default_factory=list)
    occupation_group_rebindings: Annotated[list[CrossingOccupationRebinding], Field(max_length=100)] = Field(default_factory=list)
    occupation_group_extensions: Annotated[list[JunctionOccupationExtension], Field(max_length=100)] = Field(default_factory=list)
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)
    map_itinerary_safety_margins: StrictBool = False


class CalculateKilometrePoints(Input):
    action: Literal['calculate_kilometre_points']
    direction: Literal['increasing', 'decreasing']
    itinerary: Name | None = None
    end_sequence: Annotated[list[ConnectorEnd], Field(min_length=2, max_length=10000)] | None = None
    start_km: Kilometre | None = None
    replace_conflicting: StrictBool = False

    @model_validator(mode='after')
    def exact_source(self):
        if (self.itinerary is None) == (self.end_sequence is None):
            raise ValueError('Provide either one bound Itinerary name or one directed End sequence')
        return self


class EdgeLengthReview(Input):
    edge_id: Ordinal
    expected_length_m: Metres
    expected_calculated_length_m: Metres | None = None


class CalculateEdgeLengths(Input):
    action: Literal['calculate_edge_lengths_from_kilometration']
    edges: Annotated[list[EdgeLengthReview], Field(min_length=1, max_length=1000)]
    span_incident_rebindings: SpanIncidentRebindings = Field(default_factory=list)
    map_itinerary_safety_margins: StrictBool = False


class ConnectorPair(Input):
    a: ConnectorEnd
    b: ConnectorEnd


class CrossPlatformHaltArea(Input):
    document: Name
    station_id: Ordinal


class CrossPlatformHaltPlacement(PlatformHaltPlacement):
    document: Name
    expected_position_from_entry_m: Annotated[StrictInt, Field(ge=0, lt=2147483647)]


class CrossPlatformHaltSignalReview(PlatformHaltSignalReview):
    document: Name


class CreateCrossDocumentStationHaltSignals(Input):
    action: Literal['create_cross_document_station_halt_signals']
    arrival_route: Ref
    expected_station_sign: Name
    station_areas: Annotated[list[CrossPlatformHaltArea], Field(min_length=2, max_length=2)]
    expected_connector_pair: ConnectorPair
    expected_platform_edge_ids: Annotated[list[CrossingEdge], Field(min_length=2, max_length=100)]
    expected_halt_signals: Annotated[list[CrossPlatformHaltSignalReview], Field(max_length=100)]
    maximum_train_length_m: Annotated[StrictInt, Field(gt=0, le=10000)] | None = None
    markers: Annotated[list[CrossPlatformHaltPlacement], Field(min_length=1, max_length=32)]
    signal_donor: Source
    donor_signal_id: Ordinal


class RelocateCrossDocumentStationHaltSignal(HaltRelocationReview):
    action: Literal['relocate_cross_document_station_halt_signal']
    arrival_route: Ref
    expected_station_sign: Name
    station_areas: Annotated[list[CrossPlatformHaltArea], Field(min_length=2, max_length=2)]
    expected_connector_pair: ConnectorPair
    expected_platform_edge_ids: Annotated[list[CrossingEdge], Field(min_length=2, max_length=100)]
    expected_halt_signals: Annotated[list[CrossPlatformHaltSignalReview], Field(min_length=1, max_length=100)]
    signal_id: Ordinal
    from_end: ConnectorEnd
    to_end: ConnectorEnd
    expected_stop_shift_m: Annotated[StrictInt, Field(gt=-2147483647, lt=2147483647)]


class CrossDocumentPlatformResizeEdge(PlatformResizeEdge):
    document: Name


class CrossDocumentPlatformResizeExtent(Input):
    expected_station_sign: Name
    station_areas: Annotated[list[CrossPlatformHaltArea], Field(min_length=2, max_length=2)]
    expected_connector_pair: ConnectorPair
    expected_platform_edge_ids: Annotated[list[CrossingEdge], Field(min_length=2, max_length=120)]
    edges: Annotated[list[CrossDocumentPlatformResizeEdge], Field(min_length=1, max_length=32)]


class ResizeUsedCrossDocumentPlatformSpan(CrossDocumentPlatformResizeExtent, PlatformResizeReview):
    action: Literal['resize_used_cross_document_platform_span']


class LocalPlatformResizeSection(LocalPlatformResizeExtent, PlatformResizeScope):
    kind: Literal['local']
    document: Name


class CrossDocumentPlatformResizeSection(CrossDocumentPlatformResizeExtent, PlatformResizeScope):
    kind: Literal['cross_document']
    document: Name


class TerminalPlatformResizeSection(TerminalPlatformResizeExtent, PlatformResizeScope):
    kind: Literal['terminal']
    document: Name


class ResizeUsedPlatforms(PlatformResizeOptions):
    action: Literal['resize_used_platforms']
    platforms: Annotated[list[Annotated[LocalPlatformResizeSection | CrossDocumentPlatformResizeSection | TerminalPlatformResizeSection,
                                      Field(discriminator='kind')]], Field(min_length=2, max_length=32)]


class SplitCrossDocumentPlatformEdge(SplitEdge):
    action: Literal['split_cross_document_platform_edge']
    reference_document: Name
    arrival_route: Ref
    expected_station_sign: Name
    station_areas: Annotated[list[CrossPlatformHaltArea], Field(min_length=2, max_length=2)]
    expected_connector_pair: ConnectorPair
    expected_platform_edge_ids: Annotated[list[CrossingEdge], Field(min_length=2, max_length=120)]
    expected_edge_length_m: Metres


class ReplaceConnectors(Input):
    action: Literal['replace_connectors']
    unlink: Annotated[list[ConnectorPair], Field(max_length=30)]
    link: Annotated[list[ConnectorPair], Field(max_length=30)]


class NewTerminalOverlap(Input):
    document: Name
    name: ReviewedName
    end_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=1000)]
    edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=999)]
    speed_kmh: Annotated[StrictFloat | StrictInt, Field(ge=0.0001, le=1000, allow_inf_nan=False)]
    release_time_s: Annotated[StrictInt, Field(ge=0, le=86400)]
    reservation_time_s: Annotated[StrictInt, Field(ge=0, le=86400)] = 0


class BindCrossDocumentTerminalOverlap(Input):
    action: Literal['bind_cross_document_terminal_overlap']
    route: Ref
    overlap: ReviewedTerminalOverlap | None = None
    create_overlap: NewTerminalOverlap | None = None

    @model_validator(mode='after')
    def choose_overlap_source(self):
        if (self.overlap is None) == (self.create_overlap is None):
            raise ValueError('Select one existing overlap or create one checked terminal path')
        return self


class RelocateCrossDocumentMeasuringInstrument(Input):
    action: Literal['relocate_cross_document_measuring_instrument']
    instrument_id: Ordinal
    expected_label_id: Ordinal | None = None
    from_end: ConnectorEnd
    to_end: ConnectorEnd
    expected_edge_ids: Annotated[list[Ordinal], Field(max_length=10000)]
    replacement_edge_ids: Annotated[list[Ordinal], Field(max_length=10000)]
    reviewed_end_chain: Annotated[list[ConnectorEnd], Field(min_length=2, max_length=1000)]

    @model_validator(mode='after')
    def distinct_worksheets(self):
        if self.from_end.document == self.to_end.document:
            raise ValueError('Select an original owner and replacement End in distinct worksheets')
        return self


class ReviewedInsertedOccupiedWait(Input):
    terminal_end: ConnectorEnd
    stop_edge_id: Ordinal
    expected_wait_s: Annotated[StrictInt, Field(gt=0, le=86400)]
    expected_safety_element_id: Ordinal
    receiver_course: Name
    donor_course: Name
    station_sign: Name


class ReviewedInsertedOccupiedSpeed(ReviewedOccupiedEntry):
    expected_safety_element_id: Ordinal
    receiver_course: Name
    donor_course: Name
    station_sign: Name


class ReviewedInsertedOccupiedTiming(Input):
    release_time_s: Annotated[StrictInt, Field(gt=0, le=86400)]
    approach_length_m: Annotated[StrictFloat | StrictInt, Field(gt=0, le=10000000, allow_inf_nan=False)]
    approach_speed_kmh: Annotated[StrictFloat | StrictInt, Field(gt=0, le=1000, allow_inf_nan=False)]


class ContinuedRoute(Input):
    route: Ref
    continued_name: ReviewedName
    preserve_local_protection: StrictBool = False
    middle_entry_release_end_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=1000)] | None = None
    middle_exit_release_end_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=1000)] | None = None
    reserve_with_previous: StrictBool = False
    expected_local_slow_zone_end_ids: Annotated[list[Ordinal], Field(min_length=2, max_length=2)] | None = None
    expected_cross_document_slow_zone: CrossingSlowZone | None = None
    expected_terminal_overlap: ReviewedTerminalOverlap | None = None
    expected_occupied_entry: ReviewedOccupiedEntry | ReviewedInsertedOccupiedSpeed | ReviewedInsertedOccupiedWait | None = None
    expected_occupied_entry_timing: ReviewedInsertedOccupiedTiming | None = None

    @model_validator(mode='after')
    def protection_contract(self):
        if self.expected_local_slow_zone_end_ids is not None and self.expected_cross_document_slow_zone is not None:
            raise ValueError('Choose either the local or the crossing slow-zone contract')
        timed = self.expected_occupied_entry_timing
        entry = self.expected_occupied_entry
        if timed is not None and (not isinstance(entry, (ReviewedInsertedOccupiedSpeed, ReviewedInsertedOccupiedWait))
                or not self.preserve_local_protection or self.reserve_with_previous
                or self.expected_terminal_overlap is not None or self.expected_cross_document_slow_zone is not None
                or self.expected_local_slow_zone_end_ids is not None
                or self.middle_entry_release_end_ids is not None or self.middle_exit_release_end_ids is not None):
            raise ValueError('Inserted occupied-entry timing needs one reviewed berth, independent reservation and original implicit terminal release')
        if isinstance(entry, ReviewedInsertedOccupiedSpeed) and timed is None:
            raise ValueError('Include the reviewed timing when binding an inserted speed entry to its formation')
        return self


class InsertionSafetyMarginMapping(Input):
    itinerary: Name
    expected_insertion_position_m: Ordinal
    at_boundary: Literal['upstream', 'downstream']


class PathSpeedEventExtension(Input):
    event: Name
    path: Ref
    expected_speed_kmh: Annotated[StrictInt | StrictFloat, Field(gt=0, le=10000, allow_inf_nan=False)]


class InsertOperationalDocumentSpan(Input):
    action: Literal['insert_operational_document_span']
    old_pair: ConnectorPair
    middle_start: ConnectorEnd
    middle_finish: ConnectorEnd
    middle_first_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=100)]
    middle_second_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=100)]
    expected_middle_safety_elements: Annotated[list[Ordinal], Field(min_length=2, max_length=200)]
    expected_middle_length_m: Metres
    routes: Annotated[list[ContinuedRoute], Field(min_length=1, max_length=100)]
    operating_sha256: PlatformOperatingHashes | None = None
    safety_margin_mappings: Annotated[list[InsertionSafetyMarginMapping], Field(max_length=1000)] = Field(default_factory=list)
    path_speed_event_extensions: Annotated[list[PathSpeedEventExtension], Field(max_length=100)] = Field(default_factory=list)

    @model_validator(mode='after')
    def reviewed_operating_catalogues(self):
        entries = [route.expected_occupied_entry for route in self.routes
                   if isinstance(route.expected_occupied_entry, (ReviewedInsertedOccupiedWait, ReviewedInsertedOccupiedSpeed))]
        if len(entries) > 1 or bool(entries) != (self.operating_sha256 is not None):
            raise ValueError('Bind the five operating archive hashes to exactly one reviewed inserted occupied-entry berth')
        if entries and entries[0].receiver_course == entries[0].donor_course:
            raise ValueError('Select distinct occupied-entry receiver and donor Courses')
        return self


class EditGeometry(ProjectSave):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    dest_catalog: Source
    target_document: Name
    operation: Annotated[
        MoveVertex | SetVertexDetails | SetSignalSight | CreateMainSignal | SetEdgeExclusion | CalculateKilometrePoints | CalculateEdgeLengths
        | ReverseEdge | SplitEdge | SplitPlatformEdge | ReplaceUsedPlatformEdge | ReplaceUsedStationTrackSet
        | ResizeUsedPlatformSpan | ResizeUsedTerminalPlatformSpan | ResizeUsedCrossDocumentPlatformSpan
        | ResizeUsedPlatforms | SplitCrossDocumentPlatformEdge
        | CreateStationHaltSignals | CreateTerminalStationHaltSignals | CreateCrossDocumentStationHaltSignals
        | RelocateStationHaltSignal | RelocateTerminalStationHaltSignal | RelocateCrossDocumentStationHaltSignal | RelocateMainSignal
        | RelocateCrossDocumentMeasuringInstrument
        | CutDoubleVertex | ReplaceUsedEdge | EditUsedEdgeProfile | RerouteUsedTrackSpan | RerouteCrossDocumentTrackSpan
        | RerouteMultiDocumentTrackSpan | RerouteJunctionTrackSpans | RerouteLocalJunctionTrackSpans
        | InsertOperationalDocumentSpan | BindCrossDocumentTerminalOverlap
        | InsertVertex | InsertEdge | DeleteEdge | RechainEdge | DeleteVertex | RotateVertex
        | EditDecoration | ImportDecoration | EditStationArea | ConvertStationReference
        | MergeSafetyElements | ResetSafetyElement | ReplaceConnectors,
        Field(discriminator='action'),
    ]

    @model_validator(mode='after')
    def target_in_documents(self):
        if self.target_document not in self.documents:
            raise ValueError('The edited document must be in the bound project inventory')
        return self


class InspectSpanIncidentBindings(Input):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    dest_catalog: Source


def _track_incident_reviews(document, operation):
    requested = getattr(operation, 'track_incident_rebindings', ())
    if not requested:
        return {}, set()
    if isinstance(operation, (ReplaceUsedEdge, RerouteUsedTrackSpan)):
        old_ids = [operation.edge_id] if isinstance(operation, ReplaceUsedEdge) else operation.old_edge_ids
        old = {(document, edge_id) for edge_id in old_ids}
        new = {(document, edge_id) for edge_id in operation.replacement_edge_ids}
    else:
        sections = (operation,) if isinstance(operation, RerouteCrossDocumentTrackSpan) else operation.crossings
        old = {(edge.document, edge.edge_id) for section in sections for edge in section.old_edges}
        new = {(edge.document, edge.edge_id) for section in sections for edge in section.replacement_edges}
        if isinstance(operation, RerouteJunctionTrackSpans):
            old.update((section.document, edge) for section in operation.local_alignments for edge in section.old_edge_ids)
            new.update((section.document, edge) for section in operation.local_alignments for edge in section.replacement_edge_ids)
    former, replacement = old - new, new - old
    reviews = {}
    for row in requested:
        key = row.document.casefold(), row.name
        if key in reviews:
            raise ValueError('Review each track blockage Incident only once')
        reviewed_ids = {part.old_edge_id for part in row.edge_rebindings}
        if len(reviewed_ids) != len(row.edge_rebindings):
            raise ValueError('Review each former Incident Edge only once')
        if (any((row.document, edge_id) not in former for edge_id in reviewed_ids)
                or any((row.document, edge_id) not in replacement
                       for part in row.edge_rebindings for edge_id in part.new_edge_ids)):
            raise ValueError('Track blockage rebindings must map former track to reviewed same-worksheet replacement track')
        reviews[key] = reviewed_ids
    return reviews, {(name.casefold(), edge_id) for name, edge_id in former}


class SavedGeometryTools(NextFunctions, CourseBundles):
    def _bound_catalog(self, run_path, run_blob, field, suffix):
        rows = [line.split('#') for line in run_blob.decode('ascii').splitlines() if line.startswith(field + '#')]
        if len(rows) != 1 or len(rows[0]) != 3 or rows[0][2]:
            raise ValueError(f'This geometry edit requires the unique run-bound {field}')
        raw = rows[0][1]
        path = Path(raw)
        if not raw or any(char in raw for char in '\\%$') or '..' in path.parts or path.suffix != suffix:
            raise ValueError(f'Expected an unambiguous {field} binding')
        if not path.is_absolute():
            path = run_path.parent / path
        if not path.is_relative_to(run_path.parent):
            raise ValueError(f'{field} must belong to the selected project')
        path = self.path(path.relative_to(self.root).as_posix())
        return path, self.secure_bytes(path)

    def _check_incident_targets(self, run_path, run_blob, document, operation, *, compare_spans=False):
        path, blob = self._bound_catalog(run_path, run_blob, 'CourseFile', '.courses')
        root, _ = writer.load_next_compatible(blob)
        catalogs.course_items(root)
        reviews, former = _track_incident_reviews(document, operation)
        found = set()
        targets = {}
        retiring_crossing = False
        calculating_lengths = isinstance(operation, CalculateEdgeLengths)
        replacing_platform = isinstance(operation, (ReplaceUsedPlatformEdge, ReplaceUsedStationTrackSet,
                                                    ResizeUsedPlatformSpan, ResizeUsedTerminalPlatformSpan,
                                                    ResizeUsedCrossDocumentPlatformSpan,
                                                    ResizeUsedPlatforms))
        if isinstance(operation, (RerouteCrossDocumentTrackSpan, RerouteMultiDocumentTrackSpan, RerouteJunctionTrackSpans)):
            sections = (operation,) if isinstance(operation, RerouteCrossDocumentTrackSpan) else operation.crossings
            retiring_crossing = ((operation.retire_original or bool(operation.retire_edges))
                                 if isinstance(operation, RerouteJunctionTrackSpans)
                                 else any(section.retire_original for section in sections))
            for section in sections:
                for row in (*section.old_edges, *section.replacement_edges):
                    targets.setdefault(row.document.casefold(), set()).add(row.edge_id)
            if isinstance(operation, RerouteJunctionTrackSpans):
                for section in operation.local_alignments:
                    targets.setdefault(section.document.casefold(), set()).update(
                        (*section.old_edge_ids, *section.replacement_edge_ids))
        elif isinstance(operation, RerouteLocalJunctionTrackSpans):
            targets[document.casefold()] = {edge for row in operation.alignments
                                            for edge in (*row.old_edge_ids, *row.replacement_edge_ids)}
        elif isinstance(operation, InsertOperationalDocumentSpan):
            targets = {key.casefold(): set() for key in (operation.old_pair.a.document, operation.old_pair.b.document)}
            targets[operation.middle_start.document.casefold()] = set(
                operation.middle_first_edge_ids + operation.middle_second_edge_ids)
            for row in operation.routes:
                if row.expected_terminal_overlap is not None:
                    overlap = row.expected_terminal_overlap
                    targets.setdefault(overlap.shunting.document.casefold(), set()).update(overlap.edge_ids)
                if row.expected_occupied_entry is not None:
                    occupied = row.expected_occupied_entry
                    targets.setdefault(occupied.terminal_end.document.casefold(), set()).add(occupied.stop_edge_id)
        elif isinstance(operation, BindCrossDocumentTerminalOverlap):
            targets = {operation.route.document.casefold(): set()}
            if operation.overlap is not None:
                targets[operation.overlap.shunting.document.casefold()] = set(operation.overlap.edge_ids)
            else:
                targets[operation.create_overlap.document.casefold()] = set(operation.create_overlap.edge_ids)
        elif isinstance(operation, SetEdgeExclusion):
            targets[document.casefold()] = {value for value in (operation.edge_id, operation.target_edge_id,
                                                               operation.expected_target_edge_id,
                                                               operation.expected_target_source_edge_id)
                                            if value is not None}
        elif isinstance(operation, (CreateStationHaltSignals, CreateTerminalStationHaltSignals,
                                    RelocateStationHaltSignal, RelocateTerminalStationHaltSignal)):
            targets[document.casefold()] = set(operation.expected_platform_edge_ids)
        elif isinstance(operation, (CreateCrossDocumentStationHaltSignals, RelocateCrossDocumentStationHaltSignal)):
            for row in operation.expected_platform_edge_ids:
                targets.setdefault(row.document.casefold(), set()).add(row.edge_id)
        elif isinstance(operation, ResizeUsedCrossDocumentPlatformSpan):
            for row in operation.edges:
                targets.setdefault(row.document.casefold(), set()).add(row.edge_id)
        elif isinstance(operation, ResizeUsedPlatforms):
            for platform in operation.platforms:
                for row in platform.edges:
                    name = getattr(row, 'document', platform.document)
                    targets.setdefault(name.casefold(), set()).add(row.edge_id)
        elif calculating_lengths or isinstance(operation, (ReplaceUsedStationTrackSet, ResizeUsedPlatformSpan,
                                                            ResizeUsedTerminalPlatformSpan)):
            targets[document.casefold()] = {item.edge_id for item in operation.edges}
        else:
            targets[document.casefold()] = {getattr(operation, 'edge_id', None), *getattr(operation, 'old_edge_ids', ()),
                                           *getattr(operation, 'replacement_edge_ids', ())}
        for incident in catalogs.array(root.contents[1].value):
            catalogs.shape(incident, 'OTIncident', 12, incident_operations.SCHEMA)
            _, model_id, kind = incident.contents[5].values
            # The publication path resolves both complete graphs for these global selectors.
            if compare_spans and kind in (6, 7, 8, 13):
                continue
            source = catalogs.text(incident.contents[2].value).casefold()
            if retiring_crossing or calculating_lengths or replacing_platform:
                # Original kilometre and route-relative targets can resolve outside the saved document field.
                if kind in (6, 7, 8, 13):
                    raise ValueError('A saved position or route-span Incident needs separate review for this geometry edit')
                if kind not in range(1, 15):
                    raise ValueError('A saved Incident has an unreviewed target type for this geometry edit')
            if reviews or retiring_crossing or calculating_lengths or replacing_platform:
                source = PureWindowsPath(source).name.removesuffix('.opentrack')
            edge_ids = targets.get(source)
            if edge_ids is None:
                continue
            if kind in (6, 7, 8, 13):
                raise ValueError('An unsupported endpoint-span Incident targets the edited document')
            if kind not in (3, 9):
                continue
            incident_edges = ([model_id] if kind == 3 else
                              [number_value(row) for row in catalogs.array(incident.contents[20].value)])
            if edge_ids.isdisjoint(incident_edges):
                continue
            key = (source, catalogs.text(incident.contents[0].value)) if reviews else None
            if key not in reviews:
                raise ValueError('A saved track blockage Incident observes this Edge')
            present = {edge_id for edge_id in incident_edges if (source, edge_id) in former}
            if key in found or present != reviews[key]:
                raise ValueError('Review every former Edge of the exact affected track blockage Incident')
            found.add(key)
        if found != reviews.keys():
            raise ValueError('Each Incident review must select an existing track blockage on the former alignment')
        return path, blob

    def inspect(self, args):
        path, blob, _, _ = self.read(args.source_path)
        if path.suffix != '.opentrack':
            raise APIError('CURRENT_SAVED_GEOMETRY', 'Select an original-format .opentrack document')
        try:
            result = inspect_vertex(blob, args.end_id)
        except (ValueError, TypeError, IndexError, KeyError, OverflowError) as error:
            raise APIError('CURRENT_SAVED_GEOMETRY', str(error)[:500]) from error
        if self.secure_bytes(path) != blob:
            raise APIError('SOURCE_CHANGED', 'Worksheet changed during saved vertex inspection')
        return {'source_path': path.relative_to(self.root).as_posix(), 'source_sha256': sha(blob), **result}

    def inspect_span_incidents(self, args):
        from .saved_span_incident_rebinding import span_incident_bindings

        inputs = {name: self.checked(source) for name, source in args.documents.items()}
        run_path, run_blob, scope_check, _ = self.checked_document_list(args, inputs)
        catalog_path, catalog_blob, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run_path, run_blob, catalog_path)
        try:
            course_path, course_blob = self._bound_catalog(run_path, run_blob, 'CourseFile', '.courses')
            paths = run_infrastructure_paths(run_blob)
            project = project_from({name: inputs[name][1] for name in paths}, paths, catalog_blob)
            bindings = span_incident_bindings(course_blob, project)
        except (ValueError, TypeError, IndexError, KeyError, OverflowError) as error:
            raise APIError('CURRENT_SAVED_GEOMETRY', str(error)[:500]) from error
        scope_check()
        sources = {run_path: run_blob, catalog_path: catalog_blob, course_path: course_blob,
                   **{entry[0]: entry[1] for entry in inputs.values()}}
        if any(self.secure_bytes(path) != expected for path, expected in sources.items()):
            raise APIError('SOURCE_CHANGED', 'A native dependency changed during Incident inspection')
        return {'sources': {path.relative_to(self.root).as_posix(): sha(blob) for path, blob in sources.items()},
                'span_incidents': bindings}

    def edit(self, args):
        inputs = {name: self.checked(source) for name, source in args.documents.items()}
        run_path, run_blob, scope_check, scope = self.checked_document_list(args, inputs)
        catalog_path, catalog_blob, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run_path, run_blob, catalog_path)
        dependencies = {run_path: run_blob, catalog_path: catalog_blob,
                        **{item[0]: item[1] for item in inputs.values()}}
        shapes = None
        drawing = None
        course_blob = None
        operation = args.operation.model_dump(exclude={'shapes', 'drawing_donor', 'signal_donor', 'operating_sha256'})
        span_reviews = operation.get('span_incident_rebindings')
        if isinstance(args.operation, SetVertexDetails):
            operation['changes'] = args.operation.changes.model_dump(exclude_unset=True)
        if isinstance(args.operation, (SplitEdge, SplitPlatformEdge, ReplaceUsedPlatformEdge, ReplaceUsedStationTrackSet,
                                       CutDoubleVertex, InsertVertex, InsertEdge)):
            shape_path, shapes, _, _ = self.checked(args.operation.shapes)
            dependencies[shape_path] = shapes
        if isinstance(args.operation, ImportDecoration):
            drawing_path, drawing, _, _ = self.checked(args.operation.drawing_donor)
            dependencies[drawing_path] = drawing
        if isinstance(args.operation, (CreateStationHaltSignals, CreateTerminalStationHaltSignals, CreateCrossDocumentStationHaltSignals)):
            signal_path, shapes, _, _ = self.checked(args.operation.signal_donor)
            dependencies[signal_path] = shapes
        try:
            if isinstance(args.operation, (SplitEdge, SplitPlatformEdge, ReplaceUsedPlatformEdge, ReplaceUsedStationTrackSet,
                                           ResizeUsedPlatformSpan, ResizeUsedTerminalPlatformSpan,
                                           ResizeUsedCrossDocumentPlatformSpan, ResizeUsedPlatforms,
                                           CutDoubleVertex, ReplaceUsedEdge,
                                           EditUsedEdgeProfile, RerouteUsedTrackSpan, RerouteCrossDocumentTrackSpan,
                                           RerouteMultiDocumentTrackSpan, RerouteJunctionTrackSpans, RerouteLocalJunctionTrackSpans,
                                           InsertOperationalDocumentSpan,
                                           BindCrossDocumentTerminalOverlap,
                                           SetEdgeExclusion, CalculateEdgeLengths,
                                           CreateStationHaltSignals, CreateTerminalStationHaltSignals, CreateCrossDocumentStationHaltSignals,
                                           RelocateStationHaltSignal, RelocateTerminalStationHaltSignal,
                                           RelocateCrossDocumentStationHaltSignal,
                                           DeleteEdge, RechainEdge)):
                course_path, course_blob = self._check_incident_targets(
                    run_path, run_blob, args.target_document, args.operation, compare_spans=span_reviews is not None)
                dependencies[course_path] = course_blob
            if isinstance(args.operation, (RelocateMainSignal, CreateMainSignal)):
                course_path, course_blob = self._bound_catalog(run_path, run_blob, 'CourseFile', '.courses')
                dependencies[course_path] = course_blob
            platform_options = {}
            operating_hashes = getattr(args.operation, 'operating_sha256', None)
            if operating_hashes is not None:
                banks = {'courses': course_blob}
                for role, field, suffix in (
                    ('timetable', 'TimetableFile', '.timetable'), ('trains', 'TrainFile', '.trains'),
                    ('depot', 'DepotFile', '.depot'), ('stations', 'StationFile', '.stations'),
                ):
                    bank_path, banks[role] = self._bound_catalog(run_path, run_blob, field, suffix)
                    dependencies[bank_path] = banks[role]
                if {role: sha(data) for role, data in banks.items()} != operating_hashes.model_dump():
                    raise APIError('SOURCE_CHANGED', 'An operating catalog differs from its reviewed SHA-256')
                platform_options['platform_inputs'] = banks
            documents = {name: item[1] for name, item in inputs.items()}
            paths = run_infrastructure_paths(run_blob)
            changed, report = transform(
                documents,
                paths, catalog_blob, args.target_document, operation, shapes, drawing,
                courses=course_blob, run_bytes=run_blob, **platform_options)
            candidate_docs = {name: changed.get(name, data) for name, data in documents.items()}
            if operation.get('track_incident_rebindings'):
                from .saved_crossing_incidents import rebind_track_incidents
                revised_courses, reviewed_incidents = rebind_track_incidents(
                    course_blob, documents, candidate_docs, operation['track_incident_rebindings'])
                changed['$course_catalog'] = revised_courses
                report['track_incident_rebindings'] = reviewed_incidents
            if span_reviews is not None:
                from .saved_span_incident_rebinding import has_span_incidents, rebind_span_incidents
                if span_reviews or has_span_incidents(course_blob):
                    current = project_from({name: documents[name] for name in paths}, paths, catalog_blob)
                    candidate = project_from({name: candidate_docs[name] for name in paths}, paths,
                                             changed.get('$dest_catalog', catalog_blob))
                    incoming_courses = changed.get('$course_catalog', course_blob)
                    rebound_courses, receipts = rebind_span_incidents(incoming_courses, current, candidate, span_reviews)
                    if rebound_courses != incoming_courses:
                        changed['$course_catalog'] = rebound_courses
                    report['span_incident_rebindings'] = receipts
            if isinstance(args.operation, CalculateEdgeLengths) and not args.preview_only:
                if not changed:
                    raise ValueError('None of the selected Edges has a different calculated length')
                reviewed = {row.edge_id for row in args.operation.edges if row.expected_calculated_length_m is not None}
                if any(row['status'] == 'changed' and row['edge_id'] not in reviewed for row in report['edges']):
                    raise ValueError('Saving requires expected_calculated_length_m for every changed Edge')
            if isinstance(args.operation, (EditStationArea, SplitPlatformEdge, ReplaceUsedPlatformEdge, ReplaceUsedStationTrackSet,
                                           SplitCrossDocumentPlatformEdge,
                                           ConvertStationReference, CreateStationHaltSignals, CreateTerminalStationHaltSignals,
                                           CreateCrossDocumentStationHaltSignals,
                                           RelocateStationHaltSignal, RelocateTerminalStationHaltSignal,
                                           RelocateCrossDocumentStationHaltSignal)) or (
                    isinstance(args.operation, RelocateMainSignal) and report['station_sign'] is not None):
                station_path, station_blob = self._bound_catalog(run_path, run_blob, 'StationFile', '.stations')
                station_root, _ = writer.load_next_compatible(station_blob)
                if report['station_sign'] not in catalogs.station_items(station_root):
                    raise ValueError('The edited worksheet station is absent from the run-bound StationFile')
                dependencies[station_path] = station_blob
        except (ValueError, TypeError, IndexError, KeyError, OverflowError) as error:
            raise APIError('CURRENT_SAVED_GEOMETRY', str(error)[:500]) from error
        references = {path.relative_to(self.root).as_posix(): sha(blob) for path, blob in dependencies.items()}
        original_paths = {name: item[0] for name, item in inputs.items()}
        original_paths['$dest_catalog'] = catalog_path
        if '$course_catalog' in changed:
            original_paths['$course_catalog'] = course_path
        members = {original_paths[name].name: blob for name, blob in changed.items()}
        manifest = {
            'format': 'opentrack-saved-geometry-v1',
            'sources': references,
            'complete_relocated_project': False,
            'files': {name: {'sha256': sha(blob), 'bytes': len(blob)} for name, blob in members.items()},
            'replacement_for': {original_paths[name].name: original_paths[name].relative_to(self.root).as_posix()
                                for name in changed},
            'document_scope': scope, 'operation': report,
        }
        if isinstance(args.operation, (CreateStationHaltSignals, CreateTerminalStationHaltSignals, CreateCrossDocumentStationHaltSignals)):
            manifest['signal_donor_source'] = args.operation.signal_donor.model_dump()
        elif shapes is not None:
            manifest['shape_source'] = args.operation.shapes.model_dump()
        if isinstance(args.operation, ImportDecoration):
            manifest['drawing_source'] = args.operation.drawing_donor.model_dump()
        if not args.preview_only:
            target = self.path(args.target_directory)
            project = run_path.parent
            if target.is_relative_to(project):
                raise APIError('CURRENT_SAVED_GEOMETRY', 'Publish the replacement bundle outside the bound source project')
        result = {'preview_only': args.preview_only, 'saved': False, 'manifest': manifest,
                  'change_report': report, 'fresh_archive_reload_verified': True,
                  'complete_relocated_project': False}
        if args.preview_only and isinstance(args.operation, CalculateEdgeLengths) and not members:
            for path, original in dependencies.items():
                if self.secure_bytes(path) != original:
                    raise APIError('SOURCE_CHANGED', 'A source changed during the length calculation preview')
            scope_check()
            from ..json_safe import checked_json
            return checked_json(result)
        return self.publish_bundle(inputs=dependencies, members=members, manifest=manifest,
                                   result=result, target_directory=args.target_directory, scope_check=scope_check)


def tool_definitions(root):
    service = SavedGeometryTools(root)
    return [
        ('opentrack_inspect_saved_vertex',
         'Inspect a current native double vertex or connector pair, including both half names, kilometre points, '
         'incident tracks and their exclusion links, signal and station identities, switch settings, and pair mismatches.',
         InspectVertex, service.inspect),
        ('opentrack_inspect_saved_span_incidents',
         'Resolve saved kilometre and Route-relative Incident selectors to reviewed native physical attachments.',
         InspectSpanIncidentBindings, service.inspect_span_incidents),
        ('opentrack_edit_saved_geometry',
         'Translate a native paired vertex and its signals; reverse a track Edge retaining directional speeds and '
         'gradient semantics; split a verified axial track Edge preserving saved movements; replace unused external '
         'connector pairs; set vertex fields, calculate kilometres along a saved movement or group/reset Safety '
         'Elements. Insert or remove track and paired vertices, reconnect an unused Edge, or rotate a vertex. '
         'Change the native sighting distance of an exactly selected main or distant signal. '
         'Create, clear or replace an exact same-worksheet Edge Exclusion Link. '
         'Edit an existing station area or split an axial platform Edge while preserving native stopping markers. '
         'Replace an active native platform Edge with an equivalent chain and migrate its reviewed monitoring members. '
         'Move an existing general or length-dependent stop signal between reviewed interior points of one platform. '
         'Move an existing main signal to the reviewed adjoining End and rebind affected native movements. '
         'Insert a block signal in an ordinary local Route or one reviewed worksheet continuation, updating releases and Paths. '
         'Convert an ordinary local pair to a native station reference and optionally bind paired area Ends. '
         'Cut an ordinary double vertex into two disconnected pairs when no saved movement depends on passage. '
         'Retire a used Edge after rebinding its movements to an equivalent reviewed local track chain. '
         'Update a used Edge physical operating profile, checking dependent movement distances and optional margin mapping. '
         'Calculate several track lengths from native endpoint kilometration and verify distances and safety margins. '
         'Bind all saved movements crossing a complete track span to an alternative connected chain. '
         'Optionally retire old-only track and explicitly selected isolated pairs after checking remaining references. '
         'Move saved two-document crossings to a different reciprocal connector pair and verify continuation ownership. '
         'Transfer reviewed same-worksheet Edge Exclusion Links and occupation members within a crossing reroute. '
         'Rebind audited Edge members of worksheet measuring instruments in a reviewed local or crossing reroute. '
         'Transfer an existing measuring instrument along a reviewed cross-document movement. '
         'Rebind reviewed native track blockage Incidents and publish their CourseFile with the geometry replacements. '
         'Verify kilometre and Route-relative Incident attachments against both graphs and save reviewed span rebindings. '
         'Optionally retire old crossing approaches and their isolated boundary pairs in the same transaction. '
         'Reroute several consecutive crossings on one bound Itinerary and jointly publish the changed documents. '
         'Assign existing Routes to reviewed local and cross-document junction alternatives in one transaction. '
         'Reconnect an occupied external crossing through an intermediate worksheet and extend all affected Paths. '
         'Bind a reviewed Overlap at the expanded terminal of a continued Route and transfer it when splitting. '
         'Transfer a reviewed speed-only occupied-entry authorization to the new terminal leg and its relay signal. '
         'Move a standalone drawing or clone native decoration by exact donor ID. '
         'Validate the exact SHA-bound project and DestInfo, '
         'then save a fresh native replacement bundle.',
         EditGeometry, service.edit, False, False),
    ]
