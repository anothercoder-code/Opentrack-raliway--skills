"""Focused AI semantic-planning contracts; no archive or native application."""

import json

import pytest

from opentrack_ai.semantic.capabilities import BY_ID, closure, query
from opentrack_ai.semantic.compiler import compile_plan, inspect
from opentrack_ai.semantic.models import (
    AppliedStepResult,
    ApplyPlanRequest,
    CompilePlanRequest,
    CompiledPlan,
    InspectRailwayRequest,
    RequirementNormalForm,
    SourceFact,
    VerifyOutcomesRequest,
)
from opentrack_ai.semantic.outcomes import audit, verify


def _requirement(**overrides):
    values = {
        "request_id": "station-redesign",
        "objective": (
            "Add peak-hour overtaking at station B, expand its platform faces, "
            "preserve existing services, and stop WX17 at the new platform."
        ),
        "acceptance_wanted": "offline_candidate",
        "stations": ["B"],
        "tracks": ["platform-face"],
        "facilities": ["station", "platform", "turnout"],
        "services": ["WX17"],
        "assertions": [
            "Platform span is contiguous and WX17 stops within its usable length.",
            "Native GUI and actual running remain not_run until the final acceptance round.",
        ],
        "facts": [
            {
                "fact_id": "F1",
                "statement": "The supplied diagram shows two platform faces.",
                "source_type": "provided_document",
                "source": "diagram.pdf",
                "confidence": "observed",
            }
        ],
    }
    values.update(overrides)
    return RequirementNormalForm.model_validate(values)


def test_semantic_capabilities_are_composable_and_have_evidence_limits():
    rows = query(objects=["platform"])
    ids = {row["capability_id"] for row in rows}
    assert "railway.reality_station_plan" in ids
    assert "railway.platform_reference_build" in ids
    selected = closure(["railway.operating_plan_write"])
    selected_ids = {row.capability_id for row in selected}
    assert "railway.inspect_project" in selected_ids
    assert "railway.plan_information_only" in selected_ids
    assert "railway.route_interlocking_edit" in selected_ids
    assert all(row.implementation_tools for row in BY_ID.values())
    assert all(row.limits for row in BY_ID.values())


def test_plan_is_hash_bound_typed_and_queues_design_questions():
    requirement = _requirement(
        missing_facts=[
            {
                "fact_id": "Q1",
                "question": "Which documented usable platform edge bounds stop placement?",
                "affects_design": True,
            }
        ]
    )
    plan = compile_plan(CompilePlanRequest(requirement=requirement))
    assert plan["evidence_level"] == "plan_only"
    assert plan["native_archive_written"] is False
    assert plan["native_application_started"] is False
    assert plan["grouped_questions"] == [
        "Which documented usable platform edge bounds stop placement?"
    ]
    assert {row["capability_id"] for row in plan["actions"]} >= {
        "railway.inspect_project",
        "railway.reality_station_plan",
        "railway.network_archive_build",
        "railway.operating_plan_write",
    }
    assert all(
        row["source"] in {action["action_id"] for action in plan["actions"]}
        and row["target"] in {action["action_id"] for action in plan["actions"]}
        for row in plan["edges"]
    )
    assert next(
        row for row in plan["assertions"] if "WX17" in row["claim"]
    )["required_evidence"] == "static"
    assert next(
        row for row in plan["assertions"] if "actual running" in row["claim"]
    )["required_evidence"] == "native_simulation"


def test_native_gui_and_simulation_assertions_keep_distinct_evidence_levels():
    plan = compile_plan(
        CompilePlanRequest(
            requirement=_requirement(
                assertions=[
                    "The project is saved through the native GUI and reloads with identical Inspector values.",
                    "WX17 stops at the documented platform and departs to the downstream section.",
                ]
            )
        )
    )

    gui_claim = next(
        row for row in plan["assertions"] if "native GUI" in row["claim"]
    )
    simulation_claim = next(
        row for row in plan["assertions"] if "stops at" in row["claim"]
    )
    assert gui_claim["required_evidence"] == "native_gui_observation"
    assert simulation_claim["required_evidence"] == "native_simulation"


def test_plan_hash_detects_material_edits():
    plan = CompiledPlan.model_validate(
        compile_plan(CompilePlanRequest(requirement=_requirement()))
    )
    changed = plan.model_dump(mode="json")
    changed["actions"][0]["purpose"] = "silently widened objective"
    with pytest.raises(ValueError, match="plan hash"):
        audit(
            ApplyPlanRequest(
                plan=CompiledPlan.model_validate(changed),
                expected_plan_id=plan.plan_id,
            )
        )


def test_evidence_cannot_be_upgraded():
    plan = CompiledPlan.model_validate(
        compile_plan(CompilePlanRequest(requirement=_requirement()))
    )
    native_assertion = next(
        row for row in plan.assertions
        if row.required_evidence == "native_simulation"
    )
    static_action = native_assertion.capability_id.replace(".", "_")
    result = AppliedStepResult(
        action_id=static_action,
        status="verified",
        evidence_level="static",
        evidence=[{"type": "static graph"}],
    )
    outcome = verify(
        VerifyOutcomesRequest(plan=plan, step_results=[result])
    )
    row = next(
        item for item in outcome["assertions"]
        if item["assertion_id"] == native_assertion.assertion_id
    )
    assert row["status"] == "not_run"
    assert "cannot establish" in row["reason"]
    assert outcome["no_evidence_upgrade"] is True


def test_inspection_preserves_source_fact_types_and_does_not_infer_connectivity():
    result = inspect(
        InspectRailwayRequest(
            requirement=_requirement(
                facts=[
                    SourceFact(
                        fact_id="F1",
                        statement="Two tracks cross in the PDF drawing.",
                        source_type="provided_document",
                        source="diagram.pdf",
                    ),
                    SourceFact(
                        fact_id="F2",
                        statement="The proposed crossing is through-connected.",
                        source_type="design_inference",
                        confidence="inferred",
                    ),
                ]
            ),
            tool_results=[
                {
                    "ok": True,
                    "result": {
                        "topology_verified": False,
                        "native_simulation_verified": False,
                    },
                }
            ],
        )
    )
    assert [row["source_type"] for row in result["facts"]] == [
        "provided_document",
        "design_inference",
    ]
    assert result["evidence_level"] == "requirement_and_supplied_tool_results"
    assert result["tool_observations"][0]["status"] == "observed"
    assert "does not automatically prove" not in json.dumps(result)


def test_ai_profile_is_minimal_and_registers_semantic_tools(tmp_path):
    from opentrack_ai.registry import Registry
    from opentrack_ai.service import Service

    registry = Registry(Service(tmp_path, False, False), profile="ai")
    assert {
        "opentrack_get_railway_capabilities",
        "opentrack_compile_railway_plan",
        "opentrack_inspect_railway",
        "opentrack_apply_railway_plan",
        "opentrack_verify_railway_outcomes",
        "opentrack_validate_reality_station_plan",
    } <= registry.tools.keys()
    assert len(registry.tools) < 30
