"""Validate a real-station plan before selecting current-archive writers.

This module performs pure, deterministic planning checks. It never opens an
archive, starts OpenTrack, executes a train, or treats drawing proximity as
connectivity. The caller supplies native object references and evidence
declarations. A successful result means only that the reviewed plan is
internally complete enough for native-tool selection and later acceptance.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr

from .tools import Input


Number = Annotated[StrictInt | StrictFloat, Field(allow_inf_nan=False)]
NonEmptyText = Annotated[StrictStr, Field(min_length=1, max_length=240)]
IdText = Annotated[StrictStr, Field(min_length=1, max_length=200)]
DocumentText = Annotated[StrictStr, Field(min_length=1, max_length=100)]
SourceIds = Annotated[list[IdText], Field(min_length=1, max_length=100)]

DIRECTIONS = {"up", "down"}
SOURCE_TYPES = {
    "owner_diagram",
    "platform_length_table",
    "timetable",
    "user_survey",
    "user_statement",
    "native_archive",
    "release_document",
    "assumption",
}
SUPPORTED_LINK_KINDS = {
    "normal_track",
    "cross_document_connector",
    "simple_turnout",
}
UNSUPPORTED_LINK_KINDS = {
    "compound_turnout",
    "crossover",
    "diamond_crossing",
    "single_slip_switch",
    "double_slip_switch",
    "scissors_crossover",
    "ladder_track",
}
UNSUPPORTED_PLATFORM_BOUNDARIES = {
    "compound_turnout",
    "crossover",
    "diamond_crossing",
    "single_slip_switch",
    "double_slip_switch",
    "scissors_crossover",
    "turnout",
    "connector",
    "unknown",
}


class SiteIdentity(Input):
    station_name: NonEmptyText
    station_code: NonEmptyText
    coordinate_datum: NonEmptyText
    source_ids: SourceIds


class Track(Input):
    track_id: IdText
    purpose: NonEmptyText
    directions: Annotated[list[StrictStr], Field(min_length=1, max_length=2)]
    entry_position_m: Number
    exit_position_m: Number
    usable_length_m: Number
    gradient_permille: Number | None = None
    speed_limit_kmh: StrictInt | None = None
    source_ids: SourceIds


class PlatformFace(Input):
    platform_id: IdText
    island_id: IdText | None = None
    track_id: IdText
    face: Literal["left", "right"]
    direction: Literal["up", "down"]
    start_position_m: Number
    end_position_m: Number
    usable_length_m: Number
    width_m: Number | None = None
    height_mm: StrictInt | None = None
    stop_post_id: IdText | None = None
    exit_signal_id: IdText
    source_ids: SourceIds


class NativeEdgeSpan(Input):
    document: DocumentText
    edge_id: StrictInt = Field(ge=0)
    start_end_id: StrictInt = Field(ge=0)
    end_end_id: StrictInt = Field(ge=0)
    length_m: Number
    direction: Literal["up", "down"]
    transition_after: Literal[
        "ordinary",
        "simple_turnout",
        "cross_document_connector",
        "compound_turnout",
        "crossover",
        "diamond_crossing",
        "single_slip_switch",
        "double_slip_switch",
        "scissors_crossover",
        "turnout",
        "connector",
        "unknown",
    ] = "ordinary"
    branch_end_ids: Annotated[list[StrictInt], Field(max_length=20)] = Field(
        default_factory=list
    )
    internal_signal_ids: Annotated[list[IdText], Field(max_length=20)] = Field(
        default_factory=list
    )
    source_ids: SourceIds


class PlatformSpan(Input):
    platform_id: IdText
    platform_edge_id: IdText
    track_id: IdText
    ordered_native_edges: Annotated[
        list[NativeEdgeSpan], Field(min_length=1, max_length=1000)
    ]
    source_ids: SourceIds


class Signal(Input):
    signal_id: IdText
    track_id: IdText
    direction: Literal["up", "down"]
    end_id: StrictInt = Field(ge=0)
    type: Literal["main", "combined"]
    function: Literal["home", "blocking", "exit"]
    virtual: StrictBool = False
    source_ids: SourceIds


class StopPost(Input):
    stop_post_id: IdText
    platform_id: IdText
    track_id: IdText
    direction: Literal["up", "down"]
    end_id: StrictInt = Field(ge=0)
    position_m: Number
    signal_id: IdText
    source_ids: SourceIds


class NativeEnd(Input):
    document: DocumentText
    end_id: StrictInt = Field(ge=0)


class DirectedLink(Input):
    source: NativeEnd
    target: NativeEnd
    kind: StrictStr
    turnout_id: IdText | None = None
    turnout_leg: Literal["main", "diverging"] | None = None
    source_ids: SourceIds


class SharedResource(Input):
    resource_id: IdText
    kind: Literal["track_section", "turnout", "overlap"]
    native_refs: Annotated[list[NonEmptyText], Field(min_length=1, max_length=100)]
    source_ids: SourceIds


class ThroatRoute(Input):
    route_id: IdText
    from_track_id: IdText
    to_track_id: IdText
    signal_id: IdText
    ordered_native_ends: Annotated[list[NativeEnd], Field(min_length=2, max_length=4096)]
    shared_resource_groups: Annotated[list[IdText], Field(max_length=100)] = Field(
        default_factory=list
    )
    source_ids: SourceIds


class Throat(Input):
    throat_id: IdText
    document: DocumentText
    entry_track_ids: Annotated[list[IdText], Field(min_length=1, max_length=100)]
    exit_track_ids: Annotated[list[IdText], Field(min_length=1, max_length=100)]
    turnout_end_ids: Annotated[list[NativeEnd], Field(max_length=100)] = Field(
        default_factory=list
    )
    route_ids: Annotated[list[IdText], Field(min_length=1, max_length=1000)]
    source_ids: SourceIds


class Movement(Input):
    course_id: IdText
    train: IdText
    train_length_m: Number
    from_station_id: IdText
    to_station_id: IdText
    direction: Literal["up", "down"]
    arrival_s: StrictInt = Field(ge=0, le=31622400)
    departure_s: StrictInt = Field(ge=0, le=31622400)
    arrival_day_offset: StrictInt = Field(default=0, ge=-366, le=366)
    departure_day_offset: StrictInt = Field(default=0, ge=-366, le=366)
    stop: StrictBool
    service_platform_id: IdText
    route_ids: Annotated[list[IdText], Field(min_length=1, max_length=1000)]
    source_ids: SourceIds


class SourceRecord(Input):
    id: IdText
    type: StrictStr
    uri_or_path: NonEmptyText
    retrieved_on: StrictStr
    sha256: StrictStr | None = None
    supports: Annotated[list[NonEmptyText], Field(min_length=1, max_length=200)]


class Assumption(Input):
    field: NonEmptyText
    value: NonEmptyText
    reason: NonEmptyText
    affects_acceptance: StrictBool
    source_id: IdText | None = None


class Acceptance(Input):
    preview: Annotated[list[NonEmptyText], Field(max_length=1000)] = Field(
        default_factory=list
    )
    native_editor: Annotated[list[NonEmptyText], Field(max_length=1000)] = Field(
        default_factory=list
    )
    gui_save_and_true_reload: Annotated[list[NonEmptyText], Field(max_length=1000)] = (
        Field(default_factory=list)
    )
    actual_run: Annotated[list[NonEmptyText], Field(max_length=1000)] = Field(
        default_factory=list
    )
    outputs: Annotated[list[NonEmptyText], Field(max_length=1000)] = Field(
        default_factory=list
    )


class RealityStationPlan(Input):
    contract_version: Literal[1]
    contract_kind: Literal["reality_station_semantic_plan"]
    satisfies_single_corridor_builder: StrictBool = False
    template_status: StrictStr | None = None
    purpose: StrictStr | None = None
    site_identity: SiteIdentity
    tracks: Annotated[list[Track], Field(min_length=1, max_length=100)]
    platform_faces: Annotated[list[PlatformFace], Field(min_length=1, max_length=1000)]
    platform_spans: Annotated[list[PlatformSpan], Field(min_length=1, max_length=1000)]
    signals: Annotated[list[Signal], Field(min_length=1, max_length=2000)]
    stop_posts: Annotated[list[StopPost], Field(max_length=1000)] = Field(
        default_factory=list
    )
    directed_links: Annotated[list[DirectedLink], Field(min_length=1, max_length=50000)]
    shared_resources: Annotated[list[SharedResource], Field(max_length=10000)] = Field(
        default_factory=list
    )
    throats: Annotated[list[Throat], Field(min_length=1, max_length=100)]
    routes: Annotated[list[ThroatRoute], Field(min_length=1, max_length=1000)]
    movements: Annotated[list[Movement], Field(min_length=1, max_length=10000)]
    source_register: Annotated[list[SourceRecord], Field(min_length=1, max_length=1000)]
    assumptions: Annotated[list[Assumption], Field(max_length=1000)] = Field(
        default_factory=list
    )
    acceptance: Acceptance = Field(default_factory=Acceptance)


class ValidateRealityStationPlan(Input):
    plan: RealityStationPlan


CAPABILITIES = (
    {
        "capability_id": "network.explicit_current_archive",
        "tool": "opentrack_generate_current_network_archives",
        "supported_objects": ["Vertex", "Edge", "MainSignal", "Route", "Path", "Itinerary"],
        "does_not_infer": ["drawing proximity", "turnout connectivity", "compound turnout"],
    },
    {
        "capability_id": "facilities.explicit_railml_mapping",
        "tool": "opentrack_apply_native_railml_facilities",
        "supported_objects": ["track mapping", "platform edge span", "stop post", "exit signal"],
        "does_not_infer": ["island geometry", "throat connectivity", "stopping candidate"],
    },
    {
        "capability_id": "station.bounded_rebuild",
        "tool": "opentrack_rebuild_native_railml_station",
        "supported_objects": ["facing turnout tree", "shared station faces", "simple passing loop"],
        "does_not_infer": ["crossover", "slip switch", "ladder", "compound turnout"],
    },
    {
        "capability_id": "operations.planned_service",
        "tool": "opentrack_generate_current_operating_archives",
        "supported_objects": ["Course", "Timetable", "vehicle definition", "running plan"],
        "does_not_infer": ["native dwell", "actual departure", "downstream arrival"],
    },
    {
        "capability_id": "candidate.offline_launch_preparation",
        "tool": "opentrack_prepare_station_run_candidate",
        "supported_objects": ["fresh candidate project", "native-start declaration"],
        "does_not_infer": ["OpenTrack launch", "native simulation", "GUI Save"],
    },
)


def _absolute_seconds(day_offset, second):
    return day_offset * 86400 + second


def _source_refs(value):
    """Yield source IDs from every evidence-bearing part of the plan."""
    yield from value.site_identity.source_ids
    for group in (
        value.tracks,
        value.platform_faces,
        value.platform_spans,
        value.signals,
        value.stop_posts,
        value.directed_links,
        value.shared_resources,
        value.throats,
        value.routes,
        value.movements,
    ):
        for row in group:
            yield from row.source_ids
            if isinstance(row, PlatformSpan):
                for edge in row.ordered_native_edges:
                    yield from edge.source_ids


def _is_placeholder(text):
    upper = text.upper()
    return (
        "REPLACE" in upper
        or text == "YYYY-MM-DD"
        or upper in {"TODO", "TBD", "EXAMPLE", "PLACEHOLDER"}
    )


def _path_has_traversal(value):
    normalized = value.replace("\\", "/")
    return any(part == ".." for part in normalized.split("/"))


def _is_absolute_source(value):
    if "://" in value:
        return False
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _issue(code, severity, message, location=None, details=None):
    row = {"code": code, "severity": severity, "message": message}
    if location is not None:
        row["location"] = location
    if details is not None:
        row["details"] = details
    return row


def _status(issues):
    if any(row["severity"] == "unsupported" for row in issues):
        return "unsupported"
    if any(row["severity"] == "error" for row in issues):
        return "invalid"
    return "valid_for_offline_planning"


def _assertion(assertion_id, status, evidence, limitations=()):
    return {
        "assertion_id": assertion_id,
        "status": status,
        "evidence_layer": "static_semantic_plan",
        "evidence": evidence,
        "limitations": list(limitations),
    }


def validate_reality_station_plan(plan):
    """Validate a plan and return a normalized, fail-closed planning report."""
    value = (
        plan
        if isinstance(plan, RealityStationPlan)
        else RealityStationPlan.model_validate(plan)
    )
    issues = []
    checks = {}

    def passed(assertion_id, condition, code, message, severity="error", location=None):
        checks.setdefault(assertion_id, condition)
        if not condition:
            issues.append(_issue(code, severity, message, location))
        return condition

    def unsupported(assertion_id, code, message, location=None):
        checks[assertion_id] = False
        issues.append(_issue(code, "unsupported", message, location))

    # Template placeholders and source provenance.
    passed(
        "contract.final_plan_selected",
        value.template_status is None,
        "TEMPLATE_NOT_FINAL_PLAN",
        "A documentation template cannot be submitted as a final station plan.",
        location={"template_status": value.template_status},
    )
    passed(
        "contract.not_single_corridor",
        value.satisfies_single_corridor_builder is False,
        "CONTRACT_SHAPE_CONFLICT",
        "A multi-face reality plan cannot be represented as a single-corridor request.",
    )
    placeholders = []
    for path, raw in _walk_strings(value.model_dump(mode="json")):
        if _is_placeholder(raw):
            placeholders.append({"field": path, "value": raw})
    passed(
        "sources.placeholders_cleared",
        not placeholders,
        "TEMPLATE_PLACEHOLDER",
        "The plan still contains template placeholder values.",
        location=placeholders[:20],
    )

    sources = {}
    for source in value.source_register:
        if source.id in sources:
            issues.append(
                _issue(
                    "DUPLICATE_SOURCE_ID",
                    "error",
                    "Source IDs must be unique.",
                    {"source_id": source.id},
                )
            )
        sources[source.id] = source
        if source.type not in SOURCE_TYPES:
            unsupported(
                "sources.types_explicit",
                "UNSUPPORTED_SOURCE_TYPE",
                "The source type is not recognized by the semantic contract.",
                {"source_id": source.id, "type": source.type},
            )
        try:
            date.fromisoformat(source.retrieved_on)
        except ValueError:
            issues.append(
                _issue(
                    "SOURCE_DATE_INVALID",
                    "error",
                    "retrieved_on must use an ISO 8601 YYYY-MM-DD date.",
                    {"source_id": source.id, "retrieved_on": source.retrieved_on},
                )
            )
        if _path_has_traversal(source.uri_or_path):
            issues.append(
                _issue(
                    "SOURCE_PATH_TRAVERSAL",
                    "error",
                    "Source paths may not contain parent traversal.",
                    {"source_id": source.id, "uri_or_path": source.uri_or_path},
                )
            )
        if _is_absolute_source(source.uri_or_path):
            issues.append(
                _issue(
                    "SOURCE_ABSOLUTE_PATH",
                    "warning",
                    "The source uses an absolute machine path and is not portable.",
                    {"source_id": source.id, "uri_or_path": source.uri_or_path},
                )
            )
        if source.type == "native_archive" and (
            source.sha256 is None
            or len(source.sha256) != 64
            or any(char not in "0123456789abcdef" for char in source.sha256)
        ):
            issues.append(
                _issue(
                    "NATIVE_SOURCE_SHA_REQUIRED",
                    "error",
                    "A native_archive source requires one lowercase SHA-256.",
                    {"source_id": source.id},
                )
            )

    referenced_sources = set(_source_refs(value))
    missing_sources = sorted(referenced_sources - sources.keys())
    passed(
        "sources.references_resolved",
        not missing_sources,
        "UNRESOLVED_SOURCE",
        "Every evidence reference must resolve to one source-register record.",
        location=missing_sources,
    )

    assumption_source_problems = []
    for index, assumption in enumerate(value.assumptions):
        if assumption.source_id is None:
            assumption_source_problems.append(
                {"assumption_index": index, "reason": "source_id missing"}
            )
        elif assumption.source_id not in sources:
            assumption_source_problems.append(
                {"assumption_index": index, "reason": "unknown source_id"}
            )
        else:
            source = sources[assumption.source_id]
            if source.type != "assumption" and source.type != "user_statement":
                assumption_source_problems.append(
                    {
                        "assumption_index": index,
                        "reason": "source does not declare assumption/user_statement",
                        "source_type": source.type,
                    }
                )
        if assumption.affects_acceptance:
            issues.append(
                _issue(
                    "ASSUMPTION_AFFECTS_ACCEPTANCE",
                    "warning",
                    "The assumption must remain visible in every acceptance record.",
                    {"field": assumption.field, "value": assumption.value},
                )
            )
    passed(
        "sources.assumptions_traceable",
        not assumption_source_problems,
        "ASSUMPTION_SOURCE_UNRESOLVED",
        "Every assumption needs an explicit assumption or user-statement source.",
        location=assumption_source_problems,
    )

    tracks = {}
    for track in value.tracks:
        if track.track_id in tracks:
            issues.append(
                _issue(
                    "DUPLICATE_TRACK_ID",
                    "error",
                    "Track IDs must be unique.",
                    {"track_id": track.track_id},
                )
            )
        tracks[track.track_id] = track
        if not set(track.directions) <= DIRECTIONS or len(set(track.directions)) != len(
            track.directions
        ):
            issues.append(
                _issue(
                    "TRACK_DIRECTION_INVALID",
                    "error",
                    "Track directions must be distinct up/down values.",
                    {"track_id": track.track_id, "directions": track.directions},
                )
            )
        if track.exit_position_m <= track.entry_position_m:
            issues.append(
                _issue(
                    "TRACK_EXTENT_INVALID",
                    "error",
                    "Track exit position must exceed its entry position.",
                    {"track_id": track.track_id},
                )
            )
        if track.usable_length_m <= 0:
            issues.append(
                _issue(
                    "TRACK_LENGTH_INVALID",
                    "error",
                    "Track usable length must be positive.",
                    {"track_id": track.track_id},
                )
            )
    checks["tracks.identity_direction_extent"] = bool(tracks) and not any(
        row["code"]
        in {
            "DUPLICATE_TRACK_ID",
            "TRACK_DIRECTION_INVALID",
            "TRACK_EXTENT_INVALID",
            "TRACK_LENGTH_INVALID",
        }
        for row in issues
    )

    faces = {}
    for face in value.platform_faces:
        if face.platform_id in faces:
            issues.append(
                _issue(
                    "DUPLICATE_PLATFORM_ID",
                    "error",
                    "Platform face IDs must be unique.",
                    {"platform_id": face.platform_id},
                )
            )
        faces[face.platform_id] = face
        track = tracks.get(face.track_id)
        if track is None:
            issues.append(
                _issue(
                    "PLATFORM_TRACK_UNKNOWN",
                    "error",
                    "A platform face references an unknown track.",
                    {"platform_id": face.platform_id, "track_id": face.track_id},
                )
            )
        elif face.direction not in track.directions:
            issues.append(
                _issue(
                    "PLATFORM_DIRECTION_CONFLICT",
                    "error",
                    "The platform direction is not allowed by its track.",
                    {
                        "platform_id": face.platform_id,
                        "direction": face.direction,
                        "track_directions": track.directions,
                    },
                )
            )
        if face.end_position_m <= face.start_position_m:
            issues.append(
                _issue(
                    "PLATFORM_EXTENT_INVALID",
                    "error",
                    "Platform end position must exceed its start position.",
                    {"platform_id": face.platform_id},
                )
            )
        if face.usable_length_m <= 0:
            issues.append(
                _issue(
                    "PLATFORM_USABLE_LENGTH_INVALID",
                    "error",
                    "Platform usable length must be positive.",
                    {"platform_id": face.platform_id},
                )
            )
    checks["platforms.track_direction_binding"] = not any(
        row["code"]
        in {
            "DUPLICATE_PLATFORM_ID",
            "PLATFORM_TRACK_UNKNOWN",
            "PLATFORM_DIRECTION_CONFLICT",
            "PLATFORM_EXTENT_INVALID",
            "PLATFORM_USABLE_LENGTH_INVALID",
        }
        for row in issues
    )

    islands = defaultdict(list)
    for face in value.platform_faces:
        if face.island_id is not None:
            islands[face.island_id].append(face)
    island_problem = False
    for island_id, island_faces in islands.items():
        face_sides = {face.face for face in island_faces}
        track_ids = {face.track_id for face in island_faces}
        if len(island_faces) != 2 or face_sides != {"left", "right"} or len(track_ids) != 2:
            island_problem = True
            unsupported(
                "platforms.island_two_face",
                "UNSUPPORTED_ISLAND_FACE_CONFIGURATION",
                "An island must have exactly two opposite faces on two distinct tracks.",
                {
                    "island_id": island_id,
                    "faces": [face.platform_id for face in island_faces],
                    "face_sides": sorted(face_sides),
                    "track_ids": sorted(track_ids),
                },
            )
    if not island_problem:
        checks["platforms.island_two_face"] = True

    spans = {}
    span_problem = False
    for span in value.platform_spans:
        if span.platform_id in spans:
            issues.append(
                _issue(
                    "DUPLICATE_PLATFORM_SPAN",
                    "error",
                    "Each platform face must have exactly one declared native span.",
                    {"platform_id": span.platform_id},
                )
            )
        spans[span.platform_id] = span
        face = faces.get(span.platform_id)
        if face is None:
            issues.append(
                _issue(
                    "PLATFORM_SPAN_UNKNOWN_FACE",
                    "error",
                    "A platform span references an unknown platform face.",
                    {"platform_id": span.platform_id},
                )
            )
            continue
        if span.track_id != face.track_id:
            issues.append(
                _issue(
                    "PLATFORM_SPAN_TRACK_MISMATCH",
                    "error",
                    "Platform face and native span track IDs differ.",
                    {
                        "platform_id": span.platform_id,
                        "face_track": face.track_id,
                        "span_track": span.track_id,
                    },
                )
            )
        edges = span.ordered_native_edges
        edge_keys = [(edge.document, edge.edge_id) for edge in edges]
        if len(edge_keys) != len(set(edge_keys)):
            issues.append(
                _issue(
                    "PLATFORM_EDGE_REUSED",
                    "error",
                    "A platform span reuses one native Edge.",
                    {"platform_id": span.platform_id},
                )
            )
        for index, edge in enumerate(edges):
            location = {
                "platform_id": span.platform_id,
                "edge_document": edge.document,
                "edge_id": edge.edge_id,
            }
            if edge.direction != face.direction:
                issues.append(
                    _issue(
                        "PLATFORM_EDGE_DIRECTION_CONFLICT",
                        "error",
                        "Every platform Edge must follow the platform face direction.",
                        location,
                    )
                )
            if edge.length_m <= 0:
                issues.append(
                    _issue(
                        "PLATFORM_EDGE_LENGTH_INVALID",
                        "error",
                        "Every platform Edge must have positive length.",
                        location,
                    )
                )
            if edge.branch_end_ids or edge.internal_signal_ids:
                span_problem = True
                unsupported(
                    "platforms.span_unbranched",
                    "UNSUPPORTED_INTERNAL_PLATFORM_OBJECT",
                    "A complete platform span cannot contain an undeclared branch or internal signal.",
                    location,
                )
            if (
                edge.transition_after in UNSUPPORTED_PLATFORM_BOUNDARIES
                and not isinstance(value.template_status, str)
            ):
                span_problem = True
                unsupported(
                    "platforms.span_unbranched",
                    "UNSUPPORTED_COMPOUND_TURNOUT",
                    "The platform span terminates at an unsupported turnout or compound boundary.",
                    {**location, "transition_after": edge.transition_after},
                )
            if index + 1 < len(edges):
                if edge.transition_after in UNSUPPORTED_PLATFORM_BOUNDARIES:
                    span_problem = True
                    unsupported(
                        "platforms.span_unbranched",
                        "UNSUPPORTED_COMPOUND_TURNOUT",
                        "The platform span crosses an unsupported turnout or compound boundary.",
                        {**location, "transition_after": edge.transition_after},
                    )
                following = edges[index + 1]
                if edge.end_end_id != following.start_end_id:
                    span_problem = True
                    unsupported(
                        "platforms.span_contiguous",
                        "UNSUPPORTED_NONCONTIGUOUS_PLATFORM",
                        "Adjacent platform Edges do not declare the exact shared directional End.",
                        {
                            "platform_id": span.platform_id,
                            "previous": [edge.document, edge.edge_id, edge.end_end_id],
                            "next": [
                                following.document,
                                following.edge_id,
                                following.start_end_id,
                            ],
                        },
                    )
        total_length = sum(edge.length_m for edge in edges)
        declared_length = face.end_position_m - face.start_position_m
        if abs(total_length - declared_length) > 1e-6:
            issues.append(
                _issue(
                    "PLATFORM_SPAN_LENGTH_MISMATCH",
                    "error",
                    "The ordered native Edge length differs from the declared platform extent.",
                    {
                        "platform_id": span.platform_id,
                        "native_total_m": total_length,
                        "declared_extent_m": declared_length,
                    },
                )
            )
        if face.usable_length_m > total_length:
            issues.append(
                _issue(
                    "PLATFORM_USABLE_EXCEEDS_SPAN",
                    "error",
                    "Usable stopping length cannot exceed the represented platform span.",
                    {
                        "platform_id": span.platform_id,
                        "usable_length_m": face.usable_length_m,
                        "span_length_m": total_length,
                    },
                )
            )
    for platform_id in sorted(faces.keys() - spans.keys()):
        issues.append(
            _issue(
                "PLATFORM_SPAN_MISSING",
                "error",
                "Every platform face needs one explicit native span.",
                {"platform_id": platform_id},
            )
        )
    if not span_problem and not any(
        row["code"]
        in {
            "DUPLICATE_PLATFORM_SPAN",
            "PLATFORM_SPAN_UNKNOWN_FACE",
            "PLATFORM_SPAN_TRACK_MISMATCH",
            "PLATFORM_EDGE_REUSED",
            "PLATFORM_EDGE_DIRECTION_CONFLICT",
            "PLATFORM_EDGE_LENGTH_INVALID",
            "PLATFORM_SPAN_LENGTH_MISMATCH",
            "PLATFORM_USABLE_EXCEEDS_SPAN",
            "PLATFORM_SPAN_MISSING",
        }
        for row in issues
    ):
        checks.setdefault("platforms.span_contiguous", True)
        checks.setdefault("platforms.span_unbranched", True)
        checks.setdefault("platforms.span_extent", True)

    signals = {}
    signal_duplicates = Counter(signal.signal_id for signal in value.signals)
    for signal in value.signals:
        signals[signal.signal_id] = signal
        if signal_duplicates[signal.signal_id] > 1:
            issues.append(
                _issue(
                    "DUPLICATE_SIGNAL_ID",
                    "error",
                    "Signal IDs must be unique.",
                    {"signal_id": signal.signal_id},
                )
            )
        if signal.track_id not in tracks:
            issues.append(
                _issue(
                    "SIGNAL_TRACK_UNKNOWN",
                    "error",
                    "A signal references an unknown track.",
                    {"signal_id": signal.signal_id, "track_id": signal.track_id},
                )
            )
        if signal.virtual:
            issues.append(
                _issue(
                    "VIRTUAL_EXIT_NOT_PHYSICAL",
                    "error",
                    "A represented platform exit must be a physical signal.",
                    {"signal_id": signal.signal_id},
                )
            )

    stop_posts = {}
    stop_post_duplicates = Counter(row.stop_post_id for row in value.stop_posts)
    for post in value.stop_posts:
        stop_posts[post.stop_post_id] = post
        if stop_post_duplicates[post.stop_post_id] > 1:
            issues.append(
                _issue(
                    "DUPLICATE_STOP_POST_ID",
                    "error",
                    "Stop-post IDs must be unique.",
                    {"stop_post_id": post.stop_post_id},
                )
            )
        face = faces.get(post.platform_id)
        if face is None:
            issues.append(
                _issue(
                    "STOP_POST_PLATFORM_UNKNOWN",
                    "error",
                    "A stop post references an unknown platform face.",
                    {
                        "stop_post_id": post.stop_post_id,
                        "platform_id": post.platform_id,
                    },
                )
            )
        elif (
            post.track_id != face.track_id
            or post.direction != face.direction
            or post.signal_id != face.exit_signal_id
        ):
            issues.append(
                _issue(
                    "STOP_POST_FACILITY_CONFLICT",
                    "error",
                    "Stop post track, direction or signal differs from its platform face.",
                    {
                        "stop_post_id": post.stop_post_id,
                        "platform_id": post.platform_id,
                    },
                )
            )
        if post.signal_id not in signals:
            issues.append(
                _issue(
                    "STOP_POST_SIGNAL_UNKNOWN",
                    "error",
                    "A stop post references an unknown signal.",
                    {
                        "stop_post_id": post.stop_post_id,
                        "signal_id": post.signal_id,
                    },
                )
            )

    exit_problem = False
    for face in value.platform_faces:
        span = spans.get(face.platform_id)
        signal = signals.get(face.exit_signal_id)
        last_end = (
            span.ordered_native_edges[-1].end_end_id if span is not None else None
        )
        if (
            signal is None
            or signal.function != "exit"
            or signal.track_id != face.track_id
            or signal.direction != face.direction
            or signal.end_id != last_end
            or signal.virtual
        ):
            exit_problem = True
            issues.append(
                _issue(
                    "PLATFORM_EXIT_SIGNAL_CONFLICT",
                    "error",
                    "The exit signal must be physical and bind to the last directional End of the face.",
                    {
                        "platform_id": face.platform_id,
                        "exit_signal_id": face.exit_signal_id,
                        "expected_end_id": last_end,
                    },
                )
            )
        if face.stop_post_id is None:
            issues.append(
                _issue(
                    "STOP_POST_NOT_DECLARED",
                    "warning",
                    "No exact stop-post boundary is declared for this platform face.",
                    {"platform_id": face.platform_id},
                )
            )
        elif face.stop_post_id not in stop_posts:
            exit_problem = True
            issues.append(
                _issue(
                    "STOP_POST_UNRESOLVED",
                    "error",
                    "The platform references an unknown stop post.",
                    {
                        "platform_id": face.platform_id,
                        "stop_post_id": face.stop_post_id,
                    },
                )
            )
    checks["facilities.platform_stop_signal_binding"] = not exit_problem and not any(
        row["code"]
        in {
            "DUPLICATE_SIGNAL_ID",
            "SIGNAL_TRACK_UNKNOWN",
            "VIRTUAL_EXIT_NOT_PHYSICAL",
            "DUPLICATE_STOP_POST_ID",
            "STOP_POST_PLATFORM_UNKNOWN",
            "STOP_POST_FACILITY_CONFLICT",
            "STOP_POST_SIGNAL_UNKNOWN",
            "STOP_POST_UNRESOLVED",
            "PLATFORM_EXIT_SIGNAL_CONFLICT",
        }
        for row in issues
    )

    # Directed links are authoritative. Similar or nearby endpoints are never
    # connected implicitly.
    link_map = defaultdict(list)
    unsupported_links = []
    for link in value.directed_links:
        source = (link.source.document, link.source.end_id)
        target = (link.target.document, link.target.end_id)
        link_map[source, target].append(link)
        if link.kind in UNSUPPORTED_LINK_KINDS:
            unsupported_links.append(
                {
                    "source": list(source),
                    "target": list(target),
                    "kind": link.kind,
                }
            )
        elif link.kind not in SUPPORTED_LINK_KINDS:
            unsupported_links.append(
                {
                    "source": list(source),
                    "target": list(target),
                    "kind": link.kind,
                    "reason": "unknown directed-link kind",
                }
            )
        elif link.kind == "simple_turnout" and (
            link.turnout_id is None or link.turnout_leg is None
        ):
            issues.append(
                _issue(
                    "TURNOUT_LINK_INCOMPLETE",
                    "error",
                    "A simple-turnout link needs its turnout ID and selected leg.",
                    {"source": list(source), "target": list(target)},
                )
            )
    if unsupported_links:
        unsupported(
            "throats.supported_link_kinds",
            "UNSUPPORTED_COMPOUND_TURNOUT",
            "At least one directed connection uses a compound or unrecognized turnout kind.",
            unsupported_links[:100],
        )
    else:
        checks["throats.supported_link_kinds"] = True
    for key, rows in link_map.items():
        if len(rows) > 1:
            issues.append(
                _issue(
                    "AMBIGUOUS_DIRECTED_LINK",
                    "error",
                    "One source-target End pair has multiple link declarations.",
                    {"source": list(key[0]), "target": list(key[1])},
                )
            )

    resources = {}
    resource_duplicates = Counter(row.resource_id for row in value.shared_resources)
    for resource in value.shared_resources:
        resources[resource.resource_id] = resource
        if resource_duplicates[resource.resource_id] > 1:
            issues.append(
                _issue(
                    "DUPLICATE_RESOURCE_ID",
                    "error",
                    "Shared-resource IDs must be unique.",
                    {"resource_id": resource.resource_id},
                )
            )

    routes = {}
    route_duplicates = Counter(row.route_id for row in value.routes)
    route_link_problem = False
    resource_problem = False
    for route in value.routes:
        routes[route.route_id] = route
        if route_duplicates[route.route_id] > 1:
            issues.append(
                _issue(
                    "DUPLICATE_ROUTE_ID",
                    "error",
                    "Route IDs must be unique.",
                    {"route_id": route.route_id},
                )
            )
        if route.from_track_id not in tracks or route.to_track_id not in tracks:
            issues.append(
                _issue(
                    "ROUTE_TRACK_UNKNOWN",
                    "error",
                    "A Route references an unknown source or destination track.",
                    {"route_id": route.route_id},
                )
            )
        signal = signals.get(route.signal_id)
        if signal is None:
            issues.append(
                _issue(
                    "ROUTE_SIGNAL_UNKNOWN",
                    "error",
                    "A Route references an unknown signal.",
                    {"route_id": route.route_id, "signal_id": route.signal_id},
                )
            )
        for source, target in zip(
            route.ordered_native_ends, route.ordered_native_ends[1:]
        ):
            key = (
                (source.document, source.end_id),
                (target.document, target.end_id),
            )
            if key not in link_map:
                route_link_problem = True
                issues.append(
                    _issue(
                        "UNDECLARED_DIRECTED_TRANSITION",
                        "error",
                        "A Route step has no explicit directed-link declaration; drawing proximity is not connectivity.",
                        {
                            "route_id": route.route_id,
                            "source": list(key[0]),
                            "target": list(key[1]),
                        },
                    )
                )
        unknown_resources = sorted(
            set(route.shared_resource_groups) - resources.keys()
        )
        if unknown_resources:
            resource_problem = True
            issues.append(
                _issue(
                    "ROUTE_RESOURCE_UNKNOWN",
                    "error",
                    "A Route references a resource missing from the source declaration.",
                    {
                        "route_id": route.route_id,
                        "resource_ids": unknown_resources,
                    },
                )
            )
        uses_turnout = any(
            link_map[
                (
                    (source.document, source.end_id),
                    (target.document, target.end_id),
                )
            ][0].kind
            == "simple_turnout"
            for source, target in zip(
                route.ordered_native_ends, route.ordered_native_ends[1:]
            )
            if (
                (source.document, source.end_id),
                (target.document, target.end_id),
            )
            in link_map
        )
        if uses_turnout and not route.shared_resource_groups:
            resource_problem = True
            issues.append(
                _issue(
                    "ROUTE_TURNOUT_RESOURCE_UNDECLARED",
                    "error",
                    "A Route over a turnout must declare its shared resources.",
                    {"route_id": route.route_id},
                )
            )
    checks["routes.directed_connectivity"] = not route_link_problem
    checks["routes.resource_closure"] = not resource_problem and not any(
        row["code"]
        in {
            "DUPLICATE_RESOURCE_ID",
            "ROUTE_RESOURCE_UNKNOWN",
            "ROUTE_TURNOUT_RESOURCE_UNDECLARED",
        }
        for row in issues
    )

    throat_problem = False
    for throat in value.throats:
        unknown_entries = sorted(set(throat.entry_track_ids) - tracks.keys())
        unknown_exits = sorted(set(throat.exit_track_ids) - tracks.keys())
        unknown_routes = sorted(set(throat.route_ids) - routes.keys())
        if unknown_entries or unknown_exits or unknown_routes:
            throat_problem = True
            issues.append(
                _issue(
                    "THROAT_REFERENCE_UNKNOWN",
                    "error",
                    "Throat track or Route references must be explicit and resolvable.",
                    {
                        "throat_id": throat.throat_id,
                        "entry_tracks": unknown_entries,
                        "exit_tracks": unknown_exits,
                        "routes": unknown_routes,
                    },
                )
            )
        for route_id in throat.route_ids:
            route = routes.get(route_id)
            if route is None:
                continue
            if (
                route.from_track_id not in throat.entry_track_ids
                or route.to_track_id not in throat.exit_track_ids
            ):
                throat_problem = True
                issues.append(
                    _issue(
                        "THROAT_ROUTE_BOUNDARY_CONFLICT",
                        "error",
                        "A throat Route must run from a declared entry track to a declared exit track.",
                        {"throat_id": throat.throat_id, "route_id": route_id},
                    )
                )
    checks["throats.explicit_boundaries"] = not throat_problem and not any(
        row["code"]
        in {
            "THROAT_REFERENCE_UNKNOWN",
            "THROAT_ROUTE_BOUNDARY_CONFLICT",
        }
        for row in issues
    )

    movement_problem = False
    chronology_problem = False
    length_problem = False
    downstream_problem = False
    course_ids = Counter(row.course_id for row in value.movements)
    for movement in value.movements:
        if course_ids[movement.course_id] > 1:
            movement_problem = True
            issues.append(
                _issue(
                    "DUPLICATE_COURSE_ID",
                    "error",
                    "Course IDs must be unique in one station movement plan.",
                    {"course_id": movement.course_id},
                )
            )
        if movement.from_station_id == movement.to_station_id:
            downstream_problem = True
            issues.append(
                _issue(
                    "MOVEMENT_DOWNSTREAM_AMBIGUOUS",
                    "error",
                    "A through movement needs distinct origin and downstream station identities.",
                    {"course_id": movement.course_id},
                )
            )
        face = faces.get(movement.service_platform_id)
        if face is None:
            movement_problem = True
            issues.append(
                _issue(
                    "MOVEMENT_PLATFORM_UNKNOWN",
                    "error",
                    "A movement references an unknown platform face.",
                    {
                        "course_id": movement.course_id,
                        "platform_id": movement.service_platform_id,
                    },
                )
            )
        else:
            if movement.direction != face.direction:
                movement_problem = True
                issues.append(
                    _issue(
                        "MOVEMENT_DIRECTION_CONFLICT",
                        "error",
                        "Movement and service-platform directions differ.",
                        {
                            "course_id": movement.course_id,
                            "movement_direction": movement.direction,
                            "platform_direction": face.direction,
                        },
                    )
                )
            if movement.train_length_m <= 0 or movement.train_length_m > face.usable_length_m:
                length_problem = True
                issues.append(
                    _issue(
                        "TRAIN_EXCEEDS_USABLE_PLATFORM",
                        "error",
                        "The declared train length must be positive and fit the usable platform length.",
                        {
                            "course_id": movement.course_id,
                            "train_length_m": movement.train_length_m,
                            "usable_length_m": face.usable_length_m,
                        },
                    )
                )
            if movement.stop and face.stop_post_id is None:
                movement_problem = True
                issues.append(
                    _issue(
                        "MOVEMENT_STOP_POST_REQUIRED",
                        "error",
                        "A planned passenger stop needs a declared stop-post boundary.",
                        {"course_id": movement.course_id},
                    )
                )
        arrival = _absolute_seconds(
            movement.arrival_day_offset, movement.arrival_s
        )
        departure = _absolute_seconds(
            movement.departure_day_offset, movement.departure_s
        )
        if departure <= arrival and movement.stop:
            chronology_problem = True
            issues.append(
                _issue(
                    "MOVEMENT_STOP_CHRONOLOGY",
                    "error",
                    "A stopping movement requires departure after arrival, including explicit day offsets.",
                    {
                        "course_id": movement.course_id,
                        "arrival_absolute_s": arrival,
                        "departure_absolute_s": departure,
                    },
                )
            )
        unknown_routes = sorted(set(movement.route_ids) - routes.keys())
        if unknown_routes:
            movement_problem = True
            issues.append(
                _issue(
                    "MOVEMENT_ROUTE_UNKNOWN",
                    "error",
                    "A movement references an unknown Route.",
                    {
                        "course_id": movement.course_id,
                        "route_ids": unknown_routes,
                    },
                )
            )
        selected_routes = [
            routes[route_id]
            for route_id in movement.route_ids
            if route_id in routes
        ]
        for first, second in zip(selected_routes, selected_routes[1:]):
            if first.to_track_id != second.from_track_id:
                movement_problem = True
                issues.append(
                    _issue(
                        "MOVEMENT_ROUTE_CHAIN_BROKEN",
                        "error",
                        "Consecutive movement Routes do not share their declared boundary track.",
                        {
                            "course_id": movement.course_id,
                            "first_route": first.route_id,
                            "second_route": second.route_id,
                        },
                    )
                )
        if selected_routes and face is not None:
            if selected_routes[-1].to_track_id != face.track_id:
                movement_problem = True
                issues.append(
                    _issue(
                        "MOVEMENT_ROUTE_PLATFORM_MISMATCH",
                        "error",
                        "The final Route does not terminate on the selected platform track.",
                        {
                            "course_id": movement.course_id,
                            "route_id": selected_routes[-1].route_id,
                            "platform_track_id": face.track_id,
                        },
                    )
                )
    checks["movements.platform_and_route_closure"] = not movement_problem
    checks["movements.stop_chronology_day_crossing"] = not chronology_problem
    checks["movements.train_fits_platform"] = not length_problem
    checks["movements.downstream_continuation"] = not downstream_problem

    # A warning on an unspecified stop post is acceptable for a non-stopping
    # planning face. A declared stopping service is checked separately above.
    static_assertions = [
        _assertion(
            "source.provenance_complete",
            "verified" if checks.get("sources.references_resolved") else "failed",
            {"source_count": len(sources), "referenced_source_count": len(referenced_sources)},
        ),
        _assertion(
            "tracks.direction_and_extent",
            "verified" if checks.get("tracks.identity_direction_extent") else "failed",
            {"track_count": len(tracks)},
        ),
        _assertion(
            "platforms.face_track_binding",
            "verified" if checks.get("platforms.track_direction_binding") else "failed",
            {"platform_face_count": len(faces)},
        ),
        _assertion(
            "platforms.island_faces",
            (
                "verified"
                if checks.get("platforms.island_two_face")
                else "unsupported"
                if island_problem
                else "not_applicable"
            ),
            {"island_count": len(islands)},
        ),
        _assertion(
            "platforms.contiguous_unbranched_span",
            (
                "verified"
                if checks.get("platforms.span_contiguous")
                and checks.get("platforms.span_unbranched")
                else "unsupported"
                if span_problem
                else "failed"
            ),
            {
                "span_count": len(spans),
                "edge_count": sum(
                    len(row.ordered_native_edges) for row in value.platform_spans
                ),
            },
        ),
        _assertion(
            "facilities.stop_and_exit_binding",
            (
                "verified"
                if checks.get("facilities.platform_stop_signal_binding")
                else "failed"
            ),
            {"signal_count": len(signals), "stop_post_count": len(stop_posts)},
        ),
        _assertion(
            "throats.explicit_directed_connectivity",
            (
                "unsupported"
                if unsupported_links
                else "verified"
                if checks.get("throats.supported_link_kinds")
                and checks.get("routes.directed_connectivity")
                and checks.get("throats.explicit_boundaries")
                else "failed"
            ),
            {
                "declared_link_count": len(value.directed_links),
                "route_count": len(routes),
                "throat_count": len(value.throats),
            },
        ),
        _assertion(
            "routes.shared_resource_closure",
            "verified" if checks.get("routes.resource_closure") else "failed",
            {"resource_count": len(resources)},
        ),
        _assertion(
            "movements.platform_route_closure",
            "verified" if checks.get("movements.platform_and_route_closure") else "failed",
            {"movement_count": len(value.movements)},
        ),
        _assertion(
            "movements.train_fits_usable_platform",
            "verified" if checks.get("movements.train_fits_platform") else "failed",
            {"movement_count": len(value.movements)},
        ),
        _assertion(
            "movements.stop_chronology_and_day_crossing",
            "verified"
            if checks.get("movements.stop_chronology_day_crossing")
            else "failed",
            {"movement_count": len(value.movements)},
        ),
        _assertion(
            "movements.downstream_station_declared",
            "verified" if checks.get("movements.downstream_continuation") else "failed",
            {"movement_count": len(value.movements)},
        ),
    ]
    native_assertions = [
        _assertion(
            assertion_id,
            "not_run",
            {},
            ["Requires the original OpenTrack application and the actual candidate project."],
        )
        for assertion_id in (
            "native.gui_open_and_inspect",
            "native.gui_save_then_true_reload",
            "native.arrival_at_platform",
            "native.zero_speed_dwell",
            "native.actual_departure_after_planned_dwell",
            "native.downstream_arrival",
            "native.route_reservation_release",
            "native.output_logs_and_diagram",
        )
    ]
    result_status = _status(issues)
    error_codes = Counter(
        row["code"] for row in issues if row["severity"] == "error"
    )
    unsupported_codes = Counter(
        row["code"] for row in issues if row["severity"] == "unsupported"
    )
    warning_codes = Counter(
        row["code"] for row in issues if row["severity"] == "warning"
    )
    return {
        "format": "opentrack-reality-station-semantic-validation-v1",
        "contract_version": 1,
        "status": result_status,
        "ready_for_offline_composition": result_status == "valid_for_offline_planning",
        "ready_for_native_write": False,
        "native_write_performed": False,
        "native_application_started": False,
        "native_simulation_verified": False,
        "site": {
            "station_name": value.site_identity.station_name,
            "station_code": value.site_identity.station_code,
        },
        "issues": issues,
        "issue_counts": {
            "errors": sum(error_codes.values()),
            "unsupported": sum(unsupported_codes.values()),
            "warnings": sum(warning_codes.values()),
            "error_codes": dict(sorted(error_codes.items())),
            "unsupported_codes": dict(sorted(unsupported_codes.items())),
            "warning_codes": dict(sorted(warning_codes.items())),
        },
        "assertions": [*static_assertions, *native_assertions],
        "capability_candidates": list(CAPABILITIES),
        "composition_boundary": {
            "plan_validation_is_not_native_write": True,
            "drawing_proximity_is_not_connectivity": True,
            "fixed_station_template_is_not_evidence": True,
            "required_application": (
                "After offline composition, inspect the exact discovered native schemas and "
                "apply them to a fresh reviewed candidate before centralized native acceptance."
            ),
        },
        "normalized_plan": value.model_dump(mode="json"),
    }


def _walk_strings(value, prefix=""):
    if isinstance(value, dict):
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else key
            yield from _walk_strings(value[key], path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{prefix}[{index}]")
    elif isinstance(value, str):
        yield prefix, value


def validate_tool(args):
    return validate_reality_station_plan(args.plan)


def tool_definitions(root):
    del root
    return [
        (
            "opentrack_validate_reality_station_plan",
            "Validate an explicit reality-station semantic plan before any native write: source "
            "provenance, tracks/directions, island faces, exact contiguous Edge spans, stop-post and "
            "physical exit-signal bindings, directed throat links and shared resources, train/platform "
            "length, stop chronology including day offsets, and downstream continuation. Returns "
            "UNSUPPORTED_* diagnostics for compound turnouts and noncontiguous spans instead of "
            "inferring connectivity from drawing proximity. Pure offline validation; never writes an "
            "archive, starts OpenTrack, or verifies native running.",
            ValidateRealityStationPlan,
            validate_tool,
        )
    ]
