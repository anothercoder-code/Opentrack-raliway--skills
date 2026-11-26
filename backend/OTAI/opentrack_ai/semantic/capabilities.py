"""Semantic capability catalog over the existing audited tool families."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Capability:
    capability_id: str
    title: str
    effects: tuple[str, ...]
    objects: tuple[str, ...]
    implementation_tools: tuple[str, ...]
    requires: tuple[str, ...]
    evidence: tuple[str, ...]
    limits: tuple[str, ...]
    status: str = "available"

    def as_dict(self):
        return asdict(self)


# This is an intent-to-implementation map, intentionally coarser than the MCP
# tool inventory. Models select outcomes and compose implementations instead
# of treating every original function as a separate end-user command.
CAPABILITIES = (
    Capability(
        "railway.inspect_project",
        "Inspect selected native project, identities and basic topology",
        ("inspect", "validate"),
        ("project", "station", "track", "signal", "catalog"),
        (
            "opentrack_inspect_project",
            "opentrack_validate_project",
            "opentrack_get_worksheet",
            "opentrack_inspect_topology",
        ),
        (),
        ("static",),
        ("Does not launch the original application or prove native acceptance.",),
    ),
    Capability(
        "railway.plan_information_only",
        "Normalize definitions, references and timetable chronology without writing",
        ("prepare", "validate"),
        ("route", "path", "itinerary", "service", "timetable"),
        ("opentrack_prepare_operations", "opentrack_compile_route_bundle"),
        ("railway.inspect_project",),
        ("static",),
        (
            "Caller-supplied topology and catalog identities are assertions.",
            "Route compiler returns definitions and no native apply batch.",
        ),
    ),
    Capability(
        "railway.reality_station_plan",
        "Validate a sourced real-station semantic plan before native composition",
        ("inspect", "validate", "prepare"),
        ("station", "platform", "track", "throat", "movement", "timetable"),
        (
            "opentrack_validate_reality_station_plan",
            "opentrack_inspect_railway",
        ),
        ("railway.inspect_project",),
        ("static",),
        (
            "Proximity never establishes connectivity.",
            "Unsupported complex crossings remain explicit.",
        ),
    ),
    Capability(
        "railway.platform_reference_build",
        "Build a bounded single through-platform corridor and planned stop",
        ("prepare", "publish"),
        ("station", "platform", "track", "service", "timetable", "run"),
        ("opentrack_build_reference_platform_corridor",),
        ("railway.reality_station_plan",),
        ("static", "fresh_archive_reload"),
        (
            "Single platform face, one linear chain and one direction.",
            "Does not establish a complex throat, GUI save or actual train run.",
        ),
    ),
    Capability(
        "railway.network_archive_build",
        "Write explicit Vertex, Edge, signal, Route, Path and Itinerary objects",
        ("prepare", "publish"),
        ("track", "switch", "signal", "route", "path", "itinerary"),
        ("opentrack_generate_current_network_archives",),
        ("railway.plan_information_only",),
        ("static", "fresh_archive_reload"),
        (
            "Inputs must state exact paired Ends and directed connectivity.",
            "No unproved compound turnout or crossing inference.",
        ),
    ),
    Capability(
        "railway.railml_station_build",
        "Rebuild supported multi-track RailML station geometry and platforms",
        ("prepare", "publish"),
        ("track", "switch", "platform", "signal", "railml"),
        ("opentrack_rebuild_native_railml_station",),
        ("railway.reality_station_plan",),
        ("static", "fresh_archive_reload"),
        (
            "Bounded reviewed RailML partitions and supported turnout profiles only.",
            "No general compound crossing, ladder or arbitrary station compiler.",
        ),
    ),
    Capability(
        "railway.facilities_write",
        "Apply mapped stations, platform spans, stop posts and exit signals",
        ("prepare", "publish"),
        ("station", "platform", "signal", "track"),
        ("opentrack_apply_native_railml_facilities",),
        ("railway.inspect_project",),
        ("static", "fresh_archive_reload"),
        (
            "Requires exact existing End, Edge and signal identities.",
            "Contiguous directed spans and exit-signal bindings are mandatory.",
        ),
    ),
    Capability(
        "railway.route_interlocking_edit",
        "Create and edit bounded Routes, Paths, Itineraries and protection",
        ("prepare", "publish"),
        ("route", "path", "itinerary", "signal", "interlocking"),
        (
            "opentrack_create_current_route",
            "opentrack_edit_current_route",
            "opentrack_edit_current_path",
            "opentrack_create_current_itinerary",
            "opentrack_edit_current_route_protection",
        ),
        (
            "railway.inspect_project",
            "railway.plan_information_only",
            "railway.facilities_write",
        ),
        ("static", "fresh_archive_reload"),
        (
            "Supported saved-data domains only.",
            "Static resources do not prove deadlock freedom or continuous clearance.",
        ),
    ),
    Capability(
        "railway.operating_plan_write",
        "Create or edit vehicle, Course, timetable and connection records",
        ("prepare", "publish"),
        ("formation", "service", "timetable", "connection"),
        (
            "opentrack_generate_current_operating_archives",
            "opentrack_generate_current_course",
            "opentrack_edit_current_timetable",
            "opentrack_apply_current_connections",
            "opentrack_generate_existing_network_operating_plan",
        ),
        ("railway.route_interlocking_edit",),
        ("static", "fresh_archive_reload"),
        (
            "Planned service binding does not prove physical fleet circulation.",
            "Default vehicle physics may be inherited proxy data.",
        ),
    ),
    Capability(
        "railway.station_run_candidate",
        "Prepare a fresh complete station project and launch input",
        ("prepare", "publish"),
        ("project", "run", "service", "timetable"),
        ("opentrack_prepare_station_run_candidate",),
        ("railway.operating_plan_write", "railway.route_interlocking_edit"),
        ("static", "fresh_archive_reload"),
        ("This prepares a candidate and does not start OpenTrack.",),
    ),
    Capability(
        "railway.native_evidence",
        "Evaluate isolated original-run outputs and frozen launch evidence",
        ("inspect", "validate"),
        ("native_output", "timetable", "protocol", "occupation", "signal"),
        (
            "opentrack_evaluate_native_run",
            "opentrack_verify_native_timetable_visits",
            "opentrack_verify_native_throat_passage",
            "opentrack_verify_native_route_protection",
            "opentrack_verify_native_turnround_chain",
        ),
        ("railway.station_run_candidate",),
        ("native_simulation",),
        (
            "Only bound original outputs are evidence of native simulation.",
            "Graphical observation remains a separate verification layer.",
        ),
    ),
)

BY_ID = {row.capability_id: row for row in CAPABILITIES}
DEPENDENCY_ORDER = {
    "railway.inspect_project": 0,
    "railway.plan_information_only": 1,
    "railway.reality_station_plan": 2,
    "railway.platform_reference_build": 3,
    "railway.network_archive_build": 3,
    "railway.railml_station_build": 3,
    "railway.facilities_write": 4,
    "railway.route_interlocking_edit": 5,
    "railway.operating_plan_write": 6,
    "railway.station_run_candidate": 7,
    "railway.native_evidence": 8,
}
EVIDENCE_RANK = {
    "static": 1,
    "fresh_archive_reload": 2,
    "native_gui_observation": 3,
    "native_simulation": 4,
    "plan_only": 0,
}


def query(query="", objects=(), effects=(), include_unavailable=False, limit=100):
    terms = tuple(x.casefold() for x in query.split() if x)
    wanted_objects = {x.casefold() for x in objects}
    wanted_effects = set(effects)
    rows = []
    for capability in CAPABILITIES:
        if not include_unavailable and capability.status != "available":
            continue
        text = " ".join(
            (capability.capability_id, capability.title, *capability.objects)
        ).casefold()
        if terms and not all(term in text for term in terms):
            continue
        if wanted_objects and not wanted_objects.intersection(capability.objects):
            continue
        if wanted_effects and not wanted_effects.intersection(capability.effects):
            continue
        rows.append(capability.as_dict())
    rows.sort(key=lambda row: (DEPENDENCY_ORDER[row["capability_id"]], row["capability_id"]))
    return rows[:limit]


def require(ids):
    unknown = [value for value in ids if value not in BY_ID]
    if unknown:
        raise ValueError("Unknown semantic capabilities: " + ", ".join(unknown))
    return [BY_ID[value] for value in sorted(set(ids), key=DEPENDENCY_ORDER.get)]


def closure(ids):
    selected = set(ids)
    queue = list(ids)
    while queue:
        capability = BY_ID[queue.pop()]
        for dependency in capability.requires:
            if dependency not in selected:
                selected.add(dependency)
                queue.append(dependency)
    return require(selected)

