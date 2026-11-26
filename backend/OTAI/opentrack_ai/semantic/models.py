"""Typed contracts for AI requirement interpretation and reviewed execution.

The semantic layer composes audited tools.  These models deliberately describe
railway intent and evidence boundaries; they are not replacements for native
archive schemas or a second railway simulation engine.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CapabilityId = Annotated[
    str,
    Field(
        pattern=r"^[a-z][a-z0-9_.-]{1,119}$",
        description="Stable semantic capability ID, not a tool name.",
    ),
]
Identifier = Annotated[str, Field(min_length=1, max_length=200)]


class SemanticInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SourceFact(SemanticInput):
    fact_id: Identifier
    statement: str = Field(min_length=1, max_length=4000)
    source_type: Literal[
        "user_statement",
        "saved_project_observation",
        "native_software_observation",
        "provided_document",
        "tool_output",
        "design_inference",
        "assumption",
    ]
    source: str | None = Field(default=None, max_length=2000)
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    confidence: Literal["explicit", "observed", "inferred", "assumed"] = "explicit"


class MissingFact(SemanticInput):
    fact_id: Identifier
    question: str = Field(min_length=1, max_length=2000)
    affects_design: bool = True
    accepted_default: str | None = Field(default=None, max_length=2000)


class RequirementNormalForm(SemanticInput):
    schema_version: Literal[1] = 1
    request_id: Identifier
    objective: str = Field(min_length=1, max_length=10000)
    project_scope: str | None = Field(default=None, max_length=2000)
    acceptance_wanted: Literal[
        "plan_only",
        "offline_candidate",
        "native_gui_save_reload",
        "actual_train_run",
    ] = "plan_only"
    preserve: list[Identifier] = Field(default_factory=list, max_length=1000)
    stations: list[Identifier] = Field(default_factory=list, max_length=1000)
    tracks: list[Identifier] = Field(default_factory=list, max_length=10000)
    movements: list[Identifier] = Field(default_factory=list, max_length=10000)
    facilities: list[Identifier] = Field(default_factory=list, max_length=10000)
    services: list[Identifier] = Field(default_factory=list, max_length=10000)
    requested_capabilities: list[CapabilityId] = Field(default_factory=list, max_length=200)
    assertions: list[Identifier] = Field(default_factory=list, max_length=2000)
    facts: list[SourceFact] = Field(default_factory=list, max_length=10000)
    missing_facts: list[MissingFact] = Field(default_factory=list, max_length=1000)
    assumptions: list[SourceFact] = Field(default_factory=list, max_length=10000)
    unsupported_requirements: list[str] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def unique_identities(self):
        fact_ids = [row.fact_id for row in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("Fact IDs must be unique")
        question_ids = [row.fact_id for row in self.missing_facts]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Missing-fact IDs must be unique")
        return self


class CapabilityQuery(SemanticInput):
    query: str = Field(default="", max_length=500)
    objects: list[str] = Field(default_factory=list, max_length=100)
    effects: list[
        Literal["inspect", "validate", "prepare", "publish", "export"]
    ] = Field(default_factory=list, max_length=10)
    include_unavailable: bool = False
    limit: int = Field(default=100, ge=1, le=500)


class GetCapabilitiesRequest(CapabilityQuery):
    pass


class PlanAction(SemanticInput):
    action_id: Identifier
    capability_id: CapabilityId
    purpose: str = Field(min_length=1, max_length=2000)
    depends_on: list[Identifier] = Field(default_factory=list, max_length=200)
    inputs: dict = Field(default_factory=dict)
    expected_outputs: list[str] = Field(default_factory=list, max_length=500)
    evidence_wanted: Literal[
        "static",
        "fresh_archive_reload",
        "native_gui_observation",
        "native_simulation",
    ] = "static"
    publication: Literal["information_only", "preview", "explicit_publish"] = "preview"


class Assertion(SemanticInput):
    assertion_id: Identifier
    subject: str = Field(min_length=1, max_length=1000)
    claim: str = Field(min_length=1, max_length=4000)
    required_evidence: Literal[
        "static",
        "fresh_archive_reload",
        "native_gui_observation",
        "native_simulation",
    ]
    initially: Literal["verified", "not_run", "unsupported", "failed"] = "not_run"
    capability_id: CapabilityId | None = None


class CompilePlanRequest(SemanticInput):
    requirement: RequirementNormalForm
    selected_capabilities: list[CapabilityId] = Field(default_factory=list, max_length=200)
    supplied_results: list[Identifier] = Field(default_factory=list, max_length=1000)
    planning_only: Literal[True] = True


class CompilePlanToolInput(CompilePlanRequest):
    pass


class PlanEdge(SemanticInput):
    source: Identifier
    target: Identifier


class CompiledPlan(SemanticInput):
    schema_version: Literal[1] = 1
    plan_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    requirement_id: Identifier
    actions: list[PlanAction]
    edges: list[PlanEdge]
    assertions: list[Assertion]
    grouped_questions: list[str] = Field(default_factory=list, max_length=100)
    unsupported: list[str] = Field(default_factory=list, max_length=1000)
    warnings: list[str] = Field(default_factory=list, max_length=1000)
    evidence_level: Literal["plan_only"] = "plan_only"
    native_archive_written: Literal[False] = False
    native_application_started: Literal[False] = False


class InspectRailwayRequest(SemanticInput):
    requirement: RequirementNormalForm
    tool_results: list[dict] = Field(default_factory=list, max_length=10000)


class AppliedStepResult(SemanticInput):
    action_id: Identifier
    status: Literal["verified", "not_run", "unsupported", "failed"]
    evidence_level: Literal[
        "static",
        "fresh_archive_reload",
        "native_gui_observation",
        "native_simulation",
    ]
    evidence: list[dict] = Field(default_factory=list, max_length=1000)


class ApplyPlanRequest(SemanticInput):
    plan: CompiledPlan
    expected_plan_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    mode: Literal["audit", "preview"] = "audit"
    step_results: list[AppliedStepResult] = Field(default_factory=list, max_length=200)
    allow_explicit_publish: bool = False

    @model_validator(mode="after")
    def safe_execution_boundary(self):
        if self.mode == "preview" and any(
            action.publication == "explicit_publish" for action in self.plan.actions
        ) and not self.allow_explicit_publish:
            raise ValueError(
                "Explicit publication actions require allow_explicit_publish=true and "
                "execution by their reviewed underlying tools."
            )
        return self


class InvokeRailwayWriterRequest(SemanticInput):
    plan: CompiledPlan
    expected_plan_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    action_id: Identifier
    tool_name: str = Field(
        pattern=r"^opentrack_[a-z0-9_]+$",
        description=(
            "One current-archive writer named by the selected plan action and "
            "accepted by the semantic writer allowlist."
        ),
    )
    arguments: dict = Field(default_factory=dict)
    allow_explicit_publish: bool = False


class VerifyOutcomesRequest(SemanticInput):
    plan: CompiledPlan
    step_results: list[AppliedStepResult] = Field(default_factory=list, max_length=200)
    native_result: dict | None = None


class GetCapabilitiesToolInput(GetCapabilitiesRequest):
    pass

