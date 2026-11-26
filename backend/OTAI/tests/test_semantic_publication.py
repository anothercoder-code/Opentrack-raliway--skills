"""Controlled plan-bound publication bridge; no native application is started."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, StrictBool

from opentrack_ai.errors import APIError
from opentrack_ai.registry import Registry, Tool
from opentrack_ai.semantic.compiler import compile_plan
from opentrack_ai.semantic.models import (
    CompilePlanRequest,
    CompiledPlan,
    InvokeRailwayWriterRequest,
    RequirementNormalForm,
)
from opentrack_ai.semantic.publication import REVIEWED_WRITERS, publish
from opentrack_ai.service import Service


class FakeWriterArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_only: StrictBool = True
    target_directory: str | None = None
    source: str = "source"


def _plan(tool_name="opentrack_generate_current_network_archives"):
    requirement = RequirementNormalForm(
        request_id="publication-boundary",
        objective="Build the required station network without native acceptance claims.",
        acceptance_wanted="offline_candidate",
        stations=["Station A"],
        tracks=["Platform 1"],
        facts=[
            {
                "fact_id": "F1",
                "statement": "The supplied design names one platform track.",
                "source_type": "provided_document",
                "source": "station.pdf",
            }
        ],
        requested_capabilities=["railway.network_archive_build"],
    )
    plan = CompiledPlan.model_validate(
        compile_plan(CompilePlanRequest(requirement=requirement))
    )
    action = next(
        row
        for row in plan.actions
        if row.capability_id == "railway.network_archive_build"
    )
    changed = plan.model_dump(mode="json")
    target_action = next(
        row
        for row in changed["actions"]
        if row["action_id"] == action.action_id
    )
    target_action["inputs"]["implementation_tools"] = [tool_name]
    # Normal callers use the compiler output. This clone exercises the bridge
    # independently of that catalog after recomputing its binding hash.
    return _rebind_plan(CompiledPlan.model_validate(changed))


def _rebind_plan(plan):
    from opentrack_ai.semantic.outcomes import _verify_plan_hash

    payload = {
        "requirement_id": plan.requirement_id,
        "actions": [row.model_dump(mode="json") for row in plan.actions],
        "edges": [row.model_dump(mode="json") for row in plan.edges],
        "assertions": [row.model_dump(mode="json") for row in plan.assertions],
        "grouped_questions": plan.grouped_questions,
        "unsupported": plan.unsupported,
        "warnings": plan.warnings,
    }
    from hashlib import sha256
    import json

    plan.plan_id = sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    _verify_plan_hash(plan)
    return plan


def _request(plan, **overrides):
    action_id = "railway_network_archive_build"
    values = {
        "plan": plan,
        "expected_plan_id": plan.plan_id,
        "action_id": action_id,
        "tool_name": "opentrack_generate_current_network_archives",
        "arguments": {
            "target_directory": "OTProjects/Output",
            "source": "source",
        },
        "allow_explicit_publish": True,
    }
    values.update(overrides)
    return InvokeRailwayWriterRequest.model_validate(values)


def _writer(handler):
    return Tool(
        "opentrack_generate_current_network_archives",
        "test writer",
        FakeWriterArguments,
        handler,
        False,
        False,
    )


class _FakeRegistry:
    def __init__(self, fake_writer):
        self._writer_tools = {
            "opentrack_generate_current_network_archives": fake_writer,
        }

    def dispatch(self, name, arguments):
        tool = self._writer_tools[name]
        return tool.handler(tool.model.model_validate(arguments))


def _registry(fake_writer):
    return _FakeRegistry(fake_writer)


def test_success_forces_publication_and_calls_exactly_one_reviewed_writer():
    plan = _plan()
    calls = []

    def writer(args):
        calls.append(args)
        return {
            "saved": True,
            "commit_completed": True,
            "target_directory": "OTProjects/Output",
            "member_sha256": {"Station.opentrack": "a" * 64},
            "fresh_archive_reload_verified": True,
        }

    registry = _registry(_writer(writer))
    result = publish(
        _request(plan, arguments={"preview_only": True, "target_directory": "OTProjects/Output"}),
        registered_tools=registry._writer_tools,
        dispatch=registry.dispatch,
    )
    assert len(calls) == 1
    assert calls[0].preview_only is False
    assert result["publication"]["saved"] is True
    assert result["publication"]["commit_completed"] is True
    assert result["nested_tool_dispatch"] is False


def test_rejected_binding_never_calls_the_writer():
    plan = _plan()
    calls = []

    def writer(args):
        calls.append(args)
        return {"saved": True, "commit_completed": True}

    registry = _registry(_writer(writer))
    cases = [
        (
            "RAILWAY_PLAN_MISMATCH",
            _request(plan, expected_plan_id="1" * 64),
        ),
        (
            "RAILWAY_PLAN_ACTION",
            _request(plan, action_id="missing_action"),
        ),
        (
            "PUBLICATION_TOOL_NOT_IN_ACTION",
            _request(
                plan,
                tool_name="opentrack_build_reference_platform_corridor",
            ),
        ),
        (
            "PUBLICATION_TOOL_REFUSED",
            _request(plan, tool_name="opentrack_create_project"),
        ),
        (
            "PUBLICATION_AUTHORIZATION_REQUIRED",
            _request(plan, allow_explicit_publish=False),
        ),
        (
            "PUBLICATION_TARGET_REQUIRED",
            _request(plan, arguments={"source": "source"}),
        ),
        (
            "PUBLICATION_ARGUMENT_REFUSED",
            _request(
                plan,
                arguments={"target_directory": "OTProjects/Output", "overwrite": True},
            ),
        ),
        (
            "PUBLICATION_ARGUMENTS_INVALID",
            _request(
                plan,
                arguments={"target_directory": "OTProjects/Output", "unexpected": 1},
            ),
        ),
    ]
    for code, request in cases:
        try:
            publish(
                request,
                registered_tools=registry._writer_tools,
                dispatch=registry.dispatch,
            )
        except APIError as error:
            assert error.code == code
        else:
            pytest.fail(f"Expected {code}, but the bridge returned successfully")
    assert calls == []


def test_material_plan_edit_is_rejected_before_dispatch():
    plan = _plan()
    calls = []
    changed = plan.model_dump(mode="json")
    changed["actions"][0]["purpose"] = "silently changed"
    changed_plan = CompiledPlan.model_validate(changed)
    registry = _registry(_writer(lambda args: calls.append(args)))

    with pytest.raises(APIError) as mismatch:
        publish(
            _request(changed_plan),
            registered_tools=registry._writer_tools,
            dispatch=registry.dispatch,
        )
    assert mismatch.value.code == "RAILWAY_PLAN_MISMATCH"
    assert calls == []


def test_writer_without_saved_commit_receipt_is_an_error():
    plan = _plan()
    registry = _registry(
        _writer(lambda args: {"saved": False, "preview_only": True})
    )

    with pytest.raises(APIError) as unconfirmed:
        publish(
            _request(plan),
            registered_tools=registry._writer_tools,
            dispatch=registry.dispatch,
        )
    assert unconfirmed.value.code == "PUBLICATION_UNCONFIRMED"


def test_atomic_no_replace_save_copy_is_a_publication_receipt():
    plan = _plan()
    registry = _registry(
        _writer(
            lambda args: {
                "saved": True,
                "target_directory": "OTProjects/Output",
                "source_unchanged": True,
                "atomic_no_replace": True,
            }
        )
    )

    result = publish(
        _request(plan),
        registered_tools=registry._writer_tools,
        dispatch=registry.dispatch,
    )

    assert result["publication"]["saved"] is True
    assert result["publication"]["commit_completed"] is True
    assert result["publication"]["atomic_no_replace"] is True
    assert result["publication"]["source_unchanged"] is True


def test_saved_alone_is_not_a_publication_receipt():
    plan = _plan()
    registry = _registry(_writer(lambda args: {"saved": True}))

    with pytest.raises(APIError) as unconfirmed:
        publish(
            _request(plan),
            registered_tools=registry._writer_tools,
            dispatch=registry.dispatch,
        )

    assert unconfirmed.value.code == "PUBLICATION_UNCONFIRMED"


def test_ai_profile_hides_writer_implementations_but_exposes_contracted_bridge(tmp_path):
    registry = Registry(Service(tmp_path, False, False), profile="ai")
    assert "opentrack_publish_railway_plan" in registry.tools
    assert "opentrack_generate_current_network_archives" not in registry.tools
    assert (
        "opentrack_generate_current_network_archives"
        in registry._writer_tools
    )
    bridge = registry.tools["opentrack_publish_railway_plan"]
    schema = bridge.model.model_json_schema()
    assert schema["properties"]["tool_name"]["pattern"] == "^opentrack_[a-z0-9_]+$"
    assert bridge.read_only is False


@pytest.mark.parametrize("profile", ["generation", "simulation-evidence"])
def test_non_ai_profiles_do_not_expose_the_semantic_bridge(tmp_path, profile):
    registry = Registry(Service(tmp_path, False, False), profile=profile)

    assert "opentrack_publish_railway_plan" not in registry.tools
    assert not hasattr(registry, "_semantic_writer_bridge")


def test_reviewed_writer_allowlist_excludes_quarantined_and_unknown_tools():
    from opentrack_ai.legacy_geometry_guard import BLOCKED_TOOLS

    assert len(REVIEWED_WRITERS) == 15
    assert REVIEWED_WRITERS.isdisjoint(BLOCKED_TOOLS)
    assert "opentrack_edit_current_route_approach_batch" not in REVIEWED_WRITERS


def test_publication_composition_example_uses_only_reviewed_writers():
    root = Path(__file__).resolve().parents[3]
    path = (
        root
        / "assets/reference-platform/"
        "reality-station.publication-plan.example.json"
    )
    example = json.loads(path.read_text(encoding="utf-8"))
    bridge_steps = [
        row for row in example["ordered_calls"] if row["kind"] == "reviewed_writer_bridge"
    ]

    assert example["status"] == "documentation_only_symbolic"
    assert len(bridge_steps) == 1
    assert bridge_steps[0]["tool_name"].startswith("<")
    assert "one reviewed writer" in example["limitations"][0]
    assert example["execution_rules"]["native_acceptance_claimed"] is False
    assert {
        row["status"]
        for row in example["required_observations_separate_from_composition"]
    } == {"not_run"}
