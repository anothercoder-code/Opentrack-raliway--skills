"""Public AI-facing semantic tools."""

from ..errors import APIError
from . import capabilities, compiler, outcomes, registry_bridge
from .models import (
    ApplyPlanRequest,
    CompilePlanToolInput,
    GetCapabilitiesToolInput,
    InspectRailwayRequest,
    InvokeRailwayWriterRequest,
    VerifyOutcomesRequest,
)


def get_capabilities(args):
    return {
        "schema_version": 1,
        "capability_model": "railway intent -> semantic capability -> audited tool composition",
        "capabilities": capabilities.query(
            args.query,
            args.objects,
            args.effects,
            args.include_unavailable,
            args.limit,
        ),
        "dependency_order": capabilities.DEPENDENCY_ORDER,
        "important_limit": (
            "A capability groups audited tools; it does not assert arbitrary native parity."
        ),
    }


def compile_plan(args):
    try:
        return compiler.compile_plan(args)
    except ValueError as exc:
        raise APIError("RAILWAY_PLAN_INVALID", str(exc)) from exc


def inspect_railway(args):
    return compiler.inspect(args)


def apply_plan(args):
    try:
        return outcomes.audit(args)
    except ValueError as exc:
        raise APIError("RAILWAY_PLAN_MISMATCH", str(exc)) from exc


def verify_outcomes(args):
    return outcomes.verify(args)


def publish_plan(args):
    return registry_bridge.publish(args)


def tool_definitions(registry=None):
    shared = []
    if registry is not None:
        shared.append(
            (
                "opentrack_publish_railway_plan",
                "Execute one writer named by one hash-bound plan action. The tool must be in the fixed reviewed-writer allowlist and the writer's original schema. Explicit requires authorization. Refuse quarantined tools, overwrite elevators and missing saved-commit receipts. This is a controlled composition gateway, not a second archive implementation.",
                InvokeRailwayWriterRequest,
                publish_plan,
                False,
                False,
            )
        )
    return shared + [
        (
            "opentrack_get_railway_capabilities",
            "Query railway semantic capabilities by object, effect or text. Each result declares dependencies, audited implementation tools and evidence limits. Use this to compose existing tools rather than add a one-function solver.",
            GetCapabilitiesToolInput,
            get_capabilities,
        ),
        (
            "opentrack_compile_railway_plan",
            "Compile a normalized railway requirement into a hash-bound capability dependency plan and an assertion matrix. Planning only; it never writes an archive, imports arbitrary code or launches OpenTrack.",
            CompilePlanToolInput,
            compile_plan,
        ),
        (
            "opentrack_inspect_railway",
            "Organize supplied source facts and tool outputs into observations, group unresolved design questions and suggest existing capabilities. No topology is inferred from drawing proximity.",
            InspectRailwayRequest,
            inspect_railway,
        ),
        (
            "opentrack_apply_railway_plan",
            "Audit a hash-bound plan against results from explicitly selected reviewed tools. This tool does not dispatch nested tools or write files; publishing remains with audited implementation tools.",
            ApplyPlanRequest,
            apply_plan,
        ),
        (
            "opentrack_verify_railway_outcomes",
            "Evaluate each plan assertion as verified, not_run, unsupported or failed, preserving evidence-level separation. Static and fresh-reload evidence cannot establish native GUI or simulation claims.",
            VerifyOutcomesRequest,
            verify_outcomes,
        ),
    ]

