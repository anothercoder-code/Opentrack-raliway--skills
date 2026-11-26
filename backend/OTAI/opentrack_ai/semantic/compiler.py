"""Compile normalized railway intent into a typed dependency plan."""

from hashlib import sha256
import json

from .capabilities import DEPENDENCY_ORDER, closure, query
from .models import (
    Assertion,
    CompilePlanRequest,
    CompiledPlan,
    PlanAction,
    PlanEdge,
)


def _canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _infer(requirement):
    selected = list(requirement.requested_capabilities)
    corpus = " ".join(
        [
            requirement.objective,
            *requirement.stations,
            *requirement.tracks,
            *requirement.movements,
            *requirement.facilities,
            *requirement.services,
            *requirement.assertions,
        ]
    ).casefold()
    if not selected:
        selected.append("railway.inspect_project")
        if any(word in corpus for word in ("platform", "platform face", "站台", "股道")):
            selected.append("railway.reality_station_plan")
        if any(word in corpus for word in ("turnout", "switch", "throat", "道岔", "咽喉")):
            selected.append("railway.network_archive_build")
            selected.append("railway.route_interlocking_edit")
        if any(word in corpus for word in ("course", "timetable", "train", "service", "车次", "时刻")):
            selected.append("railway.operating_plan_write")
        if any(word in corpus for word in ("actual run", "simulate", "开行", "实跑")):
            selected.extend(("railway.station_run_candidate", "railway.native_evidence"))
    return selected


def _assertions(requirement, capabilities=()):
    rows = []
    seen = set()
    explicit = requirement.assertions
    if not explicit:
        explicit = ["Complete the requested rail behavior without altering unspecified source state."]
    native_gui_words = (
        "native gui",
        "gui save",
        "gui reload",
        "inspector",
        "原版界面",
        "界面保存",
        "界面重载",
        "真实重载",
        "检查器",
    )
    native_simulation_words = (
        "actual run",
        "actual running",
        "simulate",
        "simulation",
        "实跑",
        "开行",
        "停车",
        "复开",
        "运行到达",
        "stops at",
        "departs",
        "arrives",
    )
    for index, claim in enumerate(explicit, 1):
        lowered = claim.casefold()
        matched = next(
            (
                capability
                for capability in capabilities
                if any(
                    term in lowered
                    for term in capability.objects + capability.effects
                )
            ),
            None,
        )
        capability_id = matched.capability_id if matched else None
        if any(word in lowered for word in native_simulation_words):
            required_evidence = "native_simulation"
        elif any(word in lowered for word in native_gui_words):
            required_evidence = "native_gui_observation"
        else:
            required_evidence = "static"
        row = Assertion(
            assertion_id=f"A{index:04}",
            subject=requirement.request_id,
            claim=claim,
            required_evidence=required_evidence,
            initially="not_run",
            capability_id=capability_id,
        )
        seen.add(row.assertion_id)
        rows.append(row)
    for index, assumption in enumerate(requirement.assumptions, 1):
        row = Assertion(
            assertion_id=f"AS{index:04}",
            subject=requirement.request_id,
            claim=f"Assumption remains explicit: {assumption.statement}",
            required_evidence="static",
            initially="verified",
        )
        if row.assertion_id not in seen:
            seen.add(row.assertion_id)
            rows.append(row)
    return rows


def compile_plan(args: CompilePlanRequest):
    requirement = args.requirement
    selected = _infer(requirement)
    if args.selected_capabilities:
        selected.extend(args.selected_capabilities)
    capabilities = closure(selected)
    supplied = set(args.supplied_results)
    actions = []
    for capability in capabilities:
        action_id = capability.capability_id.replace(".", "_")
        dependencies = []
        for dependency in capability.requires:
            dependency_action = dependency.replace(".", "_")
            if dependency_action not in supplied:
                dependencies.append(dependency_action)
        publication = (
            "explicit_publish"
            if "publish" in capability.effects
            and requirement.acceptance_wanted in ("offline_candidate", "native_gui_save_reload", "actual_train_run")
            else "preview"
        )
        actions.append(
            PlanAction(
                action_id=action_id,
                capability_id=capability.capability_id,
                purpose=capability.title,
                depends_on=dependencies,
                inputs={
                    "implementation_tools": list(capability.implementation_tools),
                    "requirement_id": requirement.request_id,
                },
                expected_outputs=[
                    "typed tool result",
                    "source and output hashes",
                    "scope limitations",
                ],
                evidence_wanted=(
                    "native_simulation"
                    if requirement.acceptance_wanted == "actual_train_run"
                    and "railway.native_evidence" in capability.capability_id
                    else "static"
                ),
                publication=publication,
            )
        )
    edges = [
        PlanEdge(
            source=dependency,
            target=action.action_id,
        )
        for action in actions
        for dependency in action.depends_on
    ]
    action_ids = {row.action_id for row in actions}
    edges = [row for row in edges if row.source in action_ids and row.target in action_ids]
    for action in actions:
        action.depends_on = [name for name in action.depends_on if name in action_ids]
    unsupported = list(requirement.unsupported_requirements)
    warnings = []
    if requirement.missing_facts:
        warnings.append(
            "Unresolved facts remain assumptions or questions; no design inference was promoted to observation."
        )
    if requirement.acceptance_wanted == "actual_train_run":
        warnings.append(
            "Actual running is planned as a final native evidence layer; this compile step does not execute it."
        )
    questions = [
        row.question
        for row in requirement.missing_facts
        if row.affects_design and row.accepted_default is None
    ]
    assertions = _assertions(requirement, capabilities)
    payload = {
        "requirement_id": requirement.request_id,
        "actions": [row.model_dump(mode="json") for row in actions],
        "edges": [row.model_dump(mode="json") for row in edges],
        "assertions": [row.model_dump(mode="json") for row in assertions],
        "grouped_questions": questions[:100],
        "unsupported": unsupported,
        "warnings": warnings,
    }
    plan = CompiledPlan(
        plan_id=sha256(_canonical(payload)).hexdigest(),
        requirement_id=requirement.request_id,
        actions=actions,
        edges=edges,
        assertions=assertions,
        grouped_questions=questions[:100],
        unsupported=unsupported,
        warnings=warnings,
    )
    return plan.model_dump(mode="json")


def inspect(args):
    requirement = args.requirement
    observations = []
    for result in args.tool_results:
        observations.append(
            {
                "source": "tool_output",
                "result": result,
                "status": "observed",
                "evidence_limitation": (
                    "A tool result is evidence only within its declared scope."
                ),
            }
        )
    return {
        "schema_version": 1,
        "requirement_id": requirement.request_id,
        "facts": [row.model_dump(mode="json") for row in requirement.facts],
        "tool_observations": observations,
        "missing_facts": [
            row.model_dump(mode="json") for row in requirement.missing_facts
        ],
        "suggested_capabilities": query(
            query=" ".join(requirement.requested_capabilities),
            objects=requirement.stations + requirement.tracks + requirement.facilities,
            include_unavailable=True,
        ),
        "unsupported": list(requirement.unsupported_requirements),
        "evidence_level": "requirement_and_supplied_tool_results",
        "native_application_started": False,
    }

