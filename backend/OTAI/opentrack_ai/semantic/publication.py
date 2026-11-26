"""Controlled publication gateway for reviewed native archive writers.

The gateway composes already registered tools. It never implements archive
semantics, accepts arbitrary tool names, delegates to quarantined entries or
launches the original application.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..errors import APIError
from .models import InvokeRailwayWriterRequest
from .outcomes import _verify_plan_hash


# These are deliberately coarse, reusable writer boundaries. Their Pydantic
# models still enforce every native field, source hash and scope restriction.
REVIEWED_WRITERS = frozenset(
    {
        "opentrack_build_reference_platform_corridor",
        "opentrack_generate_existing_network_operating_plan",
        "opentrack_generate_current_network_archives",
        "opentrack_generate_current_operating_archives",
        "opentrack_rebuild_native_railml_station",
        "opentrack_apply_native_railml_facilities",
        "opentrack_create_current_route",
        "opentrack_edit_current_route",
        "opentrack_edit_current_path",
        "opentrack_edit_current_route_protection",
        "opentrack_create_current_itinerary",
        "opentrack_edit_current_timetable",
        "opentrack_apply_current_connections",
        "opentrack_generate_current_course",
        "opentrack_prepare_station_run_candidate",
    }
)


def _secure_arguments(
    arguments: Mapping[str, Any],
    *,
    target_fields: tuple[str, ...],
) -> dict[str, Any]:
    """Reject attempts to smuggle another execution policy."""

    values = dict(arguments)
    for key in values:
        folded = key.casefold()
        if (
            "preview" in folded
            or "dry_run" in folded
            or folded in {"apply", "commit", "force", "overwrite", "replace"}
        ) and key not in {"preview_only"}:
            raise APIError(
                "PUBLICATION_ARGUMENT_REFUSED",
                "Publication arguments contain an unsupported preview, execute or overwrite flag.",
                {"argument": key},
            )
        if (
            "allow_" in folded
            and folded != "preview_only"
            and values[key] is not False
        ):
            raise APIError(
                "PUBLICATION_ARGUMENT_REFUSED",
                "Publication arguments cannot elevate a writer's permissions.",
                {"argument": key},
            )

    targets = [
        key for key in target_fields if key in values and values[key] is not None
    ]
    if not targets:
        raise APIError(
            "PUBLICATION_TARGET_REQUIRED",
            "A publication needs one explicit fresh target described by the selected writer.",
            {"accepted_fields": list(target_fields)},
        )
    return values


def _publication_arguments(
    arguments: Mapping[str, Any],
    *,
    target_fields: tuple[str, ...],
    has_preview_flag: bool,
) -> dict[str, Any]:
    values = _secure_arguments(arguments, target_fields=target_fields)
    if has_preview_flag:
        values["preview_only"] = False
    return values


def _publication_receipt(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise APIError(
            "PUBLICATION_RESULT_INVALID",
            "The reviewed writer did not return a JSON object.",
        )
    publication = result.get("publication")
    saved = result.get("saved") is True
    atomic_copy_completed = (
        result.get("saved") is True
        and result.get("atomic_no_replace") is True
        and result.get("source_unchanged") is True
    )
    completed = (
        result.get("commit_completed") is True
        or atomic_copy_completed
        or (
            isinstance(publication, dict)
            and publication.get("saved") is True
            and publication.get("commit_completed") is True
        )
    )
    if not saved or not completed:
        raise APIError(
            "PUBLICATION_UNCONFIRMED",
            "The writer returned without a saved publication receipt.",
            {
                "saved": result.get("saved"),
                "commit_completed": result.get("commit_completed"),
                "atomic_no_replace": result.get("atomic_no_replace"),
                "source_unchanged": result.get("source_unchanged"),
            },
        )
    return {
        "valid": True,
        "saved": True,
        "commit_completed": True,
        "target_path": result.get("target_path"),
        "target_directory": result.get("target_directory"),
        "member_sha256": result.get("member_sha256"),
        "publication": result.get("publication"),
        "fresh_archive_reload_verified": result.get(
            "fresh_archive_reload_verified"
        ),
        "source_unchanged": result.get("source_unchanged"),
        "atomic_no_replace": result.get("atomic_no_replace"),
    }


def publish(
    request: InvokeRailwayWriterRequest,
    *,
    registered_tools: Mapping[str, Any],
    dispatch: Callable[[str, dict[str, Any]], Any],
) -> dict[str, Any]:
    if request.expected_plan_id != request.plan.plan_id:
        raise APIError(
            "RAILWAY_PLAN_MISMATCH",
            "Expected plan hash differs from the compiled plan.",
        )
    try:
        _verify_plan_hash(request.plan)
    except ValueError as exc:
        raise APIError("RAILWAY_PLAN_MISMATCH", str(exc)) from exc
    actions = [
        action
        for action in request.plan.actions
        if action.action_id == request.action_id
    ]
    if len(actions) != 1:
        raise APIError(
            "RAILWAY_PLAN_ACTION",
            "Select exactly one action from the compiled plan.",
            {"action_id": request.action_id},
        )
    action = actions[0]
    if request.tool_name not in REVIEWED_WRITERS:
        raise APIError(
            "PUBLICATION_TOOL_REFUSED",
            "The selected tool is not an approved native publication boundary.",
            {"tool": request.tool_name, "allowed_tools": sorted(REVIEWED_WRITERS)},
        )
    implementation_tools = action.inputs.get("implementation_tools", [])
    if not isinstance(implementation_tools, list) or request.tool_name not in implementation_tools:
        raise APIError(
            "PUBLICATION_TOOL_NOT_IN_ACTION",
            "The selected writer is not named by the compiled plan action.",
            {
                "action_id": request.action_id,
                "tool": request.tool_name,
            },
        )
    if action.publication != "explicit_publish":
        raise APIError(
            "PUBLICATION_ACTION_NOT_BOUND",
            "The selected plan action is not an explicit publication action.",
            {
                "action_id": request.action_id,
                "publication": action.publication,
            },
        )
    if request.allow_explicit_publish is not True:
        raise APIError(
            "PUBLICATION_AUTHORIZATION_REQUIRED",
            "Set allow_explicit_publish=true for a plan action that requests publication.",
            {"action_id": request.action_id},
        )
    tool = registered_tools.get(request.tool_name)
    if tool is None:
        raise APIError(
            "PUBLICATION_TOOL_NOT_REGISTERED",
            "The approved writer is not present in this installation.",
            {"tool": request.tool_name},
        )
    if getattr(tool, "read_only", True):
        raise APIError(
            "PUBLICATION_TOOL_REFUSED",
            "A read-only tool cannot be used as a publication boundary.",
            {"tool": request.tool_name},
        )

    target_fields = tuple(
        name
        for name in ("target_path", "target_directory")
        if name in tool.model.model_fields
    )
    values = _secure_arguments(request.arguments, target_fields=target_fields)
    try:
        # Validate the caller's effective arguments first. The next validation
        # forces the writer's publication switch while preserving its schema.
        validated = tool.model.model_validate(values)
        validated = tool.model.model_validate(
            _publication_arguments(
                values,
                target_fields=target_fields,
                has_preview_flag="preview_only" in tool.model.model_fields,
            )
        )
    except Exception as exc:
        raise APIError(
            "PUBLICATION_ARGUMENTS_INVALID",
            "Publication arguments failed the writer's original schema.",
            str(exc)[:1000],
        ) from exc

    result = dispatch(request.tool_name, validated.model_dump(mode="json"))
    return {
        "schema_version": 1,
        "action_id": request.action_id,
        "tool": request.tool_name,
        "expected_plan_id": request.expected_plan_id,
        "result": result,
        "publication": _publication_receipt(result),
        "execution_engine": "registered_reviewed_writer",
        "arbitrary_tool_names": False,
        "arbitrary_shell": False,
        "arbitrary_internal_imports": False,
        "nested_tool_dispatch": False,
        "native_application_started": False,
    }

