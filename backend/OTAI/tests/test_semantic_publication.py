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


def _writer(handler, name="opentrack_generate_current_network_archives"):
    return Tool(
        name,
        "test writer",
        FakeWriterArguments,
        handler,
        False,
        False,
    )


class _FakeRegistry:
    def __init__(self, *fake_writers):
        self._writer_tools = {tool.name: tool for tool in fake_writers}

    def dispatch(self, name, arguments):
        tool = self._writer_tools[name]
        return tool.handler(tool.model.model_validate(arguments))


def _registry(fake_writer):
    return _FakeRegistry(fake_writer)


def _sequence_plan():
    requirement = RequirementNormalForm(
        request_id="publication-sequence",
        objective="Build the network and then bind its operating plan.",
        acceptance_wanted="offline_candidate",
        stations=["Station A"],
        tracks=["Platform 1"],
        requested_capabilities=[
            "railway.network_archive_build",
            "railway.operating_plan_write",
        ],
    )
    return CompiledPlan.model_validate(
        compile_plan(CompilePlanRequest(requirement=requirement))
    )


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


def test_ai_toolbox_status_matches_live_registry_and_task_families(tmp_path):
    from opentrack_ai.semantic.capabilities import CAPABILITIES

    root = Path(__file__).resolve().parents[3]
    status = json.loads(
        (root / "references/coverage/ai-toolbox-status.json").read_text(
            encoding="utf-8"
        )
    )
    ai = Registry(Service(tmp_path, False, False), profile="ai")
    all_tools = Registry(Service(tmp_path, False, False), profile="all")
    generation = Registry(Service(tmp_path, False, False), profile="generation")
    implementation_tools = {
        tool_name
        for capability in CAPABILITIES
        for tool_name in capability.implementation_tools
    }

    assert status["schema"] == "opentrack-ai-toolbox-coverage/1"
    assert status["acceptance_model"] == (
        "toolbox_coverage_and_ai_orchestration_reachability"
    )
    assert status["profiles"]["ai"] == len(ai.tools)
    assert status["profiles"]["generation"] == len(generation.tools)
    assert status["profiles"]["all"] == len(all_tools.tools)
    assert status["semantic_capabilities"] == len(CAPABILITIES)
    assert status["reviewed_writers"] == len(REVIEWED_WRITERS)
    direct = implementation_tools & ai.tools.keys()
    bridged = implementation_tools & REVIEWED_WRITERS
    assert status["capability_implementation_tools"] == len(implementation_tools)
    assert status["direct_ai_capability_tools"] == len(direct)
    assert status["bridge_reachable_writers"] == len(bridged)
    assert status["hidden_low_level_writers"] == len(bridged)
    assert status["historical_requirement_inventory"] == 176
    assert status["requirements_meaning"] == "historical_source_inventory"
    assert set(status["native_acceptance"].values()) == {"not_run"}
    assert status["missing_templates"] == []

    templates = root / "assets/reference-platform/templates"
    expected_templates = {
        "source-register.template.json",
        "topology.template.json",
        "native-id-map.template.json",
        "platform-dimensions.template.json",
        "throat-routes.template.json",
        "rolling-stock-service.template.json",
        "publication-receipt.template.json",
        "native-acceptance.template.json",
        "structured-unsupported.template.json",
    }
    assert {path.name for path in templates.glob("*.json")} == expected_templates
    for path in templates.glob("*.json"):
        template = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(template, dict) and template.get("template_id")

    acceptance = json.loads(
        (templates / "native-acceptance.template.json").read_text(encoding="utf-8")
    )
    assert set(acceptance["observations"].values()) == {"not_run"}
    unsupported = json.loads(
        (templates / "structured-unsupported.template.json").read_text(encoding="utf-8")
    )
    assert unsupported["result"]["issues"][0]["code"] == (
        "UNSUPPORTED_COMPOUND_TURNOUT"
    )
    platform = json.loads(
        (templates / "platform-dimensions.template.json").read_text(encoding="utf-8")
    )
    assert any(
        "UNSUPPORTED_NONCONTIGUOUS_PLATFORM" in rule
        for rule in platform["rules"]
    )
    service = json.loads(
        (templates / "rolling-stock-service.template.json").read_text(encoding="utf-8")
    )
    assert {
        service["evidence_boundary"]["arrival_at_platform"],
        service["evidence_boundary"]["zero_speed_stop"],
        service["evidence_boundary"]["planned_departure"],
        service["evidence_boundary"]["downstream_arrival"],
    } == {"not_run"}

    for family in status["task_families"]:
        assert family["status"] in {
            "supported",
            "composed",
            "partial",
            "unreachable",
            "requires_native_app",
        }
        assert set(family["capability_ids"]) <= set(
            capability.capability_id for capability in CAPABILITIES
        )
        assert set(family["required_tools"]) <= implementation_tools
        assert set(family["prerequisites"]) <= set(
            capability.capability_id for capability in CAPABILITIES
        )

    reachable = implementation_tools & (ai.tools.keys() | REVIEWED_WRITERS)
    assert implementation_tools == reachable
    by_family = {
        family["task_family"]: family for family in status["task_families"]
    }
    assert by_family["station_run_candidate_preparation"]["status"] == "composed"
    assert by_family["end_to_end_station_replication_and_run"][
        "status"
    ] == "requires_native_app"
    assert by_family["end_to_end_station_replication_and_run"][
        "native_acceptance"
    ] == "not_run"

def test_capability_catalog_resolves_to_registered_implementation_families(tmp_path):
    from opentrack_ai.semantic.capabilities import CAPABILITIES

    registry = Registry(Service(tmp_path, False, False), profile="all")
    implementation_tools = {
        tool_name
        for capability in CAPABILITIES
        for tool_name in capability.implementation_tools
    }

    assert len(CAPABILITIES) == 11
    assert implementation_tools <= registry._writer_tools.keys()
    assert REVIEWED_WRITERS <= registry._writer_tools.keys()
    assert all(not registry._writer_tools[name].read_only for name in REVIEWED_WRITERS)


def test_sequential_plan_calls_are_each_bound_to_the_same_hash():
    plan = _sequence_plan()
    action_tools = [
        (action.action_id, action.inputs["implementation_tools"][0])
        for action in plan.actions
        if action.publication == "explicit_publish"
    ]
    assert [row[0] for row in action_tools] == [
        "railway_network_archive_build",
        "railway_facilities_write",
        "railway_route_interlocking_edit",
        "railway_operating_plan_write",
    ]
    registry = _FakeRegistry(
        *(_writer(lambda args: _receipt(args.target_directory), name)
          for _, name in action_tools)
    )
    calls = []

    results = []
    dispatched = []
    for action_id, tool_name in action_tools:
        writer = _writer(
            lambda args, action_id=action_id: (
                dispatched.append(action_id)
                or _receipt(args.target_directory)
            ),
            tool_name,
        )
        registry._writer_tools[tool_name] = writer
        results.append(
            publish(
                _request(
                    plan,
                    action_id=action_id,
                    tool_name=tool_name,
                    arguments={
                        "target_directory": f"OTProjects/Output/{action_id}"
                    },
                ),
                registered_tools=registry._writer_tools,
                dispatch=registry.dispatch,
            )
        )
        calls.append(writer.handler)

    assert [row["expected_plan_id"] for row in results] == [
        plan.plan_id,
        plan.plan_id,
        plan.plan_id,
        plan.plan_id,
    ]
    assert [row["action_id"] for row in results] == [
        row[0] for row in action_tools
    ]
    assert dispatched == [row[0] for row in action_tools]
    assert len({id(row) for row in calls}) == len(action_tools)


def _receipt(target):
    return {
        "saved": True,
        "commit_completed": True,
        "target_directory": target,
    }


def test_ai_profile_keeps_reviewed_writers_hidden_and_reachable(tmp_path):
    from opentrack_ai.semantic.capabilities import CAPABILITIES

    registry = Registry(Service(tmp_path, False, False), profile="ai")
    implementation_tools = {
        tool_name
        for capability in CAPABILITIES
        for tool_name in capability.implementation_tools
    }
    low_level_writers = implementation_tools & REVIEWED_WRITERS

    assert low_level_writers
    assert low_level_writers <= registry._writer_tools.keys()
    assert low_level_writers.isdisjoint(registry.tools)
    assert "opentrack_publish_railway_plan" in registry.tools


def test_every_capability_tool_is_directly_or_bridge_reachable_in_ai_profile(
    tmp_path,
):
    from opentrack_ai.semantic.capabilities import CAPABILITIES

    registry = Registry(Service(tmp_path, False, False), profile="ai")
    implementation_tools = {
        tool_name
        for capability in CAPABILITIES
        for tool_name in capability.implementation_tools
    }
    direct = implementation_tools & registry.tools.keys()
    bridged = implementation_tools & REVIEWED_WRITERS

    assert len(registry.tools) == 21
    assert len(implementation_tools) == 28
    assert implementation_tools == direct | bridged
    assert direct.isdisjoint(bridged)
    assert REVIEWED_WRITERS.isdisjoint(registry.tools)
    assert {
        "opentrack_prepare_operations",
        "opentrack_compile_route_bundle",
        "opentrack_evaluate_native_run",
        "opentrack_verify_native_timetable_visits",
        "opentrack_verify_native_throat_passage",
        "opentrack_verify_native_route_protection",
        "opentrack_verify_native_turnround_chain",
    } <= registry.tools.keys()


def test_same_plan_cannot_publish_an_unbound_writer(tmp_path):
    plan = _sequence_plan()
    action_id, tool_name = next(
        (action.action_id, action.inputs["implementation_tools"][0])
        for action in plan.actions
        if action.action_id == "railway_network_archive_build"
    )
    registry = _FakeRegistry(
        _writer(lambda args: _receipt(args.target_directory), tool_name)
    )

    with pytest.raises(APIError) as refused:
        publish(
            _request(
                plan,
                action_id=action_id,
                tool_name="opentrack_edit_current_timetable",
                arguments={"target_directory": "OTProjects/Output/Other"},
            ),
            registered_tools=registry._writer_tools,
            dispatch=registry.dispatch,
        )
    assert refused.value.code == "PUBLICATION_TOOL_NOT_IN_ACTION"


def test_historical_requirement_inventory_remains_explicit_source_evidence():
    from opentrack_ai.coverage import read_packaged_coverage
    from opentrack_ai.models import FunctionCoverage

    result = read_packaged_coverage(
        FunctionCoverage(scope="packaged", section="summary", require_fresh=False)
    )

    assert result["summary"]["original_requirements"] == 176
    assert "saved_function_record_provenance" in result["summary"]
    assert result["summary"]["goal_complete"] is False
    assert "Historical function status" in result["evidence_level"]
