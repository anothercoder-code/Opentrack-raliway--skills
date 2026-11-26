"""Evidence aggregation and bounded execution audit for semantic plans."""

from hashlib import sha256
import json

from .capabilities import EVIDENCE_RANK
from .models import ApplyPlanRequest, VerifyOutcomesRequest


def _step_map(args):
    rows = {}
    for row in args.step_results:
        if row.action_id in rows:
            raise ValueError("A plan action has more than one bound result.")
        rows[row.action_id] = row
    return rows


def _verify_plan_hash(plan):
    payload = {
        "requirement_id": plan.requirement_id,
        "actions": [row.model_dump(mode="json") for row in plan.actions],
        "edges": [row.model_dump(mode="json") for row in plan.edges],
        "assertions": [row.model_dump(mode="json") for row in plan.assertions],
        "grouped_questions": plan.grouped_questions,
        "unsupported": plan.unsupported,
        "warnings": plan.warnings,
    }
    actual = sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if actual != plan.plan_id:
        raise ValueError("Compiled plan content differs from its plan hash.")


def _topological_verified(args, steps):
    actions = {row.action_id: row for row in args.plan.actions}
    if set(steps) - actions.keys():
        raise ValueError("A supplied result references an action outside the plan.")
    state = {}

    def visit(action_id, active=()):
        if action_id in state:
            return state[action_id]
        if action_id in active:
            raise ValueError("The compiled plan contains a dependency cycle.")
        action = actions[action_id]
        active = (*active, action_id)
        row = steps.get(action_id)
        if row is None:
            ok = False
        elif row.status == "verified":
            ok = True
        elif row.status in ("failed", "unsupported"):
            ok = False
        else:
            ok = False
        if ok:
            parent_ok = all(visit(dependency, active) for dependency in action.depends_on)
            ok = parent_ok
        state[action_id] = ok
        return ok

    for action_id in actions:
        visit(action_id)
    return state


def verify(args: VerifyOutcomesRequest):
    _verify_plan_hash(args.plan)
    steps = _step_map(args)
    action_ok = _topological_verified(args, steps)
    rows = []
    for assertion in args.plan.assertions:
        step = None
        if assertion.capability_id:
            step = steps.get(assertion.capability_id.replace(".", "_"))
        required = EVIDENCE_RANK[assertion.required_evidence]
        if step is None:
            status = "not_run"
            evidence = []
            reason = "No bound step result supplies evidence for this assertion."
        elif not action_ok.get(step.action_id, False):
            status = (
                step.status
                if step.status in ("failed", "unsupported")
                else "not_run"
            )
            evidence = [row for row in step.evidence]
            if step.status == "verified" and EVIDENCE_RANK[step.evidence_level] < required:
                reason = (
                    f"Evidence level {step.evidence_level!r} cannot establish "
                    f"required {assertion.required_evidence!r}."
                )
            else:
                reason = (
                    "The bound step or one of its plan dependencies did not verify."
                )
        else:
            status = step.status
            evidence = [row for row in step.evidence]
            actual = EVIDENCE_RANK[step.evidence_level]
            if status == "verified" and actual < required:
                status = "not_run"
                reason = (
                    f"Evidence level {step.evidence_level!r} cannot establish "
                    f"required {assertion.required_evidence!r}."
                )
            elif status == "verified":
                reason = "Bound evidence satisfies the requested evidence level."
            else:
                reason = "Bound step did not establish the requested outcome."
        rows.append(
            {
                "assertion_id": assertion.assertion_id,
                "claim": assertion.claim,
                "required_evidence": assertion.required_evidence,
                "status": status,
                "evidence": evidence,
                "reason": reason,
            }
        )
    if args.native_result is not None:
        rows.append(
            {
                "assertion_id": "NATIVE_RESULT",
                "claim": "Original result payload was supplied separately.",
                "required_evidence": "native_simulation",
                "status": "verified"
                if args.native_result.get("ok")
                else "failed",
                "evidence": [args.native_result],
                "reason": "A standalone tool result does not automatically prove any plan assertion.",
            }
        )
    statuses = [row["status"] for row in rows]
    overall = (
        "verified"
        if statuses and all(value == "verified" for value in statuses)
        else "failed"
        if "failed" in statuses
        else "unsupported"
        if "unsupported" in statuses
        else "not_run"
    )
    return {
        "schema_version": 1,
        "plan_id": args.plan.plan_id,
        "overall": overall,
        "assertions": rows,
        "evidence_hierarchy": [
            "static",
            "fresh_archive_reload",
            "native_gui_observation",
            "native_simulation",
        ],
        "no_evidence_upgrade": True,
        "native_application_started": False,
    }


def audit(args: ApplyPlanRequest):
    if args.plan.plan_id != args.expected_plan_id:
        raise ValueError("Expected plan hash differs from the compiled plan.")
    _verify_plan_hash(args.plan)
    steps = _step_map(args)
    action_ok = _topological_verified(args, steps)
    rows = []
    for action in args.plan.actions:
        step = steps.get(action.action_id)
        if step is None:
            rows.append(
                {
                    "action_id": action.action_id,
                    "capability_id": action.capability_id,
                    "status": "not_run",
                    "publication": action.publication,
                    "implementation_tools": action.inputs.get(
                        "implementation_tools", []
                    ),
                    "reason": "No bound tool result was supplied.",
                }
            )
            continue
        rows.append(
            {
                "action_id": action.action_id,
                "capability_id": action.capability_id,
                "status": step.status,
                "dependency_chain_verified": action_ok[action.action_id],
                "publication": action.publication,
                "evidence_level": step.evidence_level,
                "implementation_tools": action.inputs.get("implementation_tools", []),
                "reason": "Result was supplied by a reviewed existing tool.",
            }
        )
    return {
        "schema_version": 1,
        "plan_id": args.plan.plan_id,
        "mode": args.mode,
        "actions": rows,
        "execution_engine": "external_reviewed_tools",
        "arbitrary_shell": False,
        "arbitrary_internal_imports": False,
        "nested_tool_dispatch": False,
        "native_application_started": False,
        "note": "The semantic core audits and constrains execution; concrete files are written only by audited implementation tools.",
    }

