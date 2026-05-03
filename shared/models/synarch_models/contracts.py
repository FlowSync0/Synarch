from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    ActorType,
    AgentStatus,
    AiProviderType,
    ApprovalStatus,
    EventType,
    LifecycleAction,
    MemoryStatus,
    Priority,
    ServiceKind,
    TaskStatus,
)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class SynarchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True, validate_default=True)


class HealthResponse(SynarchModel):
    service: str
    status: str = "ok"
    version: str = "0.1.0"


class GoalEnvelope(SynarchModel):
    goal: str = Field(min_length=1)
    priority: Priority = Priority.medium
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    requester: str = "local-user"


class ProjectIntent(SynarchModel):
    title: str
    goal: str
    priority: Priority = Priority.medium
    owner_agent_id: str = "agent-direction"


class TaskDraft(SynarchModel):
    title: str
    description: str = ""
    assigned_agent_id: str
    depends_on: list[str] = Field(default_factory=list)
    priority: Priority = Priority.medium
    acceptance_criteria: list[str] = Field(default_factory=list)
    sequence: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoutingDecision(SynarchModel):
    project_intent: ProjectIntent
    task_drafts: list[TaskDraft]
    target_agents: list[str]
    rationale: str


class CapabilityMap(SynarchModel):
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)


class PermissionBundle(SynarchModel):
    can_read_scopes: list[str] = Field(default_factory=list)
    can_write_scopes: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)


class DivisionRecord(SynarchModel):
    id: str
    name: str
    purpose: str
    manager_agent_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentDefinition(SynarchModel):
    id: str
    name: str
    role: str
    division: str
    manager_id: str | None = None
    status: AgentStatus = AgentStatus.active
    capabilities: CapabilityMap = Field(default_factory=CapabilityMap)
    permissions: PermissionBundle = Field(default_factory=PermissionBundle)
    model: str = "gpt-4.1-mini"
    model_policy_id: str | None = None
    allowed_model_ids: list[str] = Field(default_factory=list)
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentSoul(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("agent_soul"))
    agent_id: str
    version: int = 1
    identity: str = Field(min_length=1, max_length=1200)
    mission: str = Field(min_length=1, max_length=1200)
    responsibilities: list[str] = Field(default_factory=list)
    operating_principles: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    escalation_rules: list[str] = Field(default_factory=list)
    communication_style: str = Field(
        default="Clear, concise, and auditable.",
        max_length=800,
    )
    created_by: str
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LocalWorldView(SynarchModel):
    agent_id: str
    name: str | None = None
    role: str
    division: str
    peers: list[str] = Field(default_factory=list)
    manager: str | None = None
    manager_agent_id: str | None = None
    peer_agent_ids: list[str] = Field(default_factory=list)
    direct_report_agent_ids: list[str] = Field(default_factory=list)
    soul: AgentSoul | None = None
    active_projects: list[str] = Field(default_factory=list)
    permissions: PermissionBundle = Field(default_factory=PermissionBundle)
    capabilities: CapabilityMap = Field(default_factory=CapabilityMap)
    policies: list[str] = Field(default_factory=list)
    available_services: list[str] = Field(default_factory=list)
    available_connector_ids: list[str] = Field(default_factory=list)
    available_skill_ids: list[str] = Field(default_factory=list)


class ProjectRecord(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("project"))
    title: str
    goal: str
    status: TaskStatus = TaskStatus.queued
    priority: Priority = Priority.medium
    owner_agent_id: str = "agent-direction"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectWorkspace(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("workspace"))
    project_id: str
    name: str
    summary: str = ""
    memory_scope: str
    allowed_agent_ids: list[str] = Field(default_factory=list)
    bridge_project_ids: list[str] = Field(default_factory=list)
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentProjectAssignment(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("assignment"))
    project_id: str
    workspace_id: str
    agent_id: str
    assignment_role: str = "contributor"
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectComplexityReport(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("complexity"))
    project_id: str
    task_count: int = 0
    open_task_count: int = 0
    blocked_task_count: int = 0
    assigned_agent_count: int = 0
    workspace_bridge_count: int = 0
    score: int = 0
    threshold: int = 10
    split_recommended: bool = False
    reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectSplitRequest(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("project_split"))
    project_id: str
    complexity_report_id: str
    requested_by: str = "system"
    reason: str
    proposed_shard_titles: list[str] = Field(default_factory=list)
    status: ApprovalStatus = ApprovalStatus.requested
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectComplexityAssessment(SynarchModel):
    report: ProjectComplexityReport
    split_request: ProjectSplitRequest | None = None


class TaskRecord(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("task"))
    project_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.queued
    assigned_agent_id: str
    depends_on: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    parent_task_id: str | None = None
    sequence: int = 0
    result: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventRecord(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("event"))
    type: EventType
    source_agent_id: str | None = None
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trace_id: str | None = None


class GoalSubmissionResult(SynarchModel):
    trace_id: str
    routing_decision: RoutingDecision
    project: ProjectRecord
    workspace: ProjectWorkspace
    assignments: list[AgentProjectAssignment] = Field(default_factory=list)
    tasks: list[TaskRecord]
    events: list[EventRecord]
    complexity_assessment: ProjectComplexityAssessment | None = None


class ProjectSplitDecision(SynarchModel):
    request_id: str
    status: ApprovalStatus
    decided_by_type: ActorType
    decided_by_id: str
    rationale: str
    events_emitted: list[EventRecord] = Field(default_factory=list)
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectSplitApplication(SynarchModel):
    request_id: str
    split_request: ProjectSplitRequest
    source_project_id: str
    shard_projects: list[ProjectRecord] = Field(default_factory=list)
    shard_workspaces: list[ProjectWorkspace] = Field(default_factory=list)
    shard_assignments: list[AgentProjectAssignment] = Field(default_factory=list)
    shard_tasks: list[TaskRecord] = Field(default_factory=list)
    events_emitted: list[EventRecord] = Field(default_factory=list)
    applied_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryItem(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("memory"))
    scope: str
    content: str
    status: MemoryStatus = MemoryStatus.approved
    agent_id: str | None = None
    project_id: str | None = None
    embedding: list[float] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class MemoryStatusUpdate(SynarchModel):
    status: MemoryStatus


class MemoryContext(SynarchModel):
    agent_id: str
    project_id: str | None = None
    token_budget: int = 4000
    allowed_scopes: list[str] = Field(default_factory=list)
    items: list[MemoryItem] = Field(default_factory=list)
    summary: str = ""
    tokens_used: int = 0


class ServiceDefinition(SynarchModel):
    id: str
    name: str
    kind: ServiceKind = ServiceKind.internal
    base_url: str | None = None
    health_endpoint: str | None = "/healthz"
    capabilities: list[str] = Field(default_factory=list)
    owner_agent_id: str | None = None
    allowed_agent_ids: list[str] = Field(default_factory=list)
    allowed_divisions: list[str] = Field(default_factory=list)
    audit_required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SkillDefinition(SynarchModel):
    id: str
    name: str
    description: str = ""
    version: str = "0.1.0"
    required_tools: list[str] = Field(default_factory=list)
    owner_agent_id: str | None = None
    allowed_agent_ids: list[str] = Field(default_factory=list)
    allowed_divisions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModelProviderConfig(SynarchModel):
    id: str
    name: str
    provider_type: AiProviderType
    base_url: str | None = None
    api_key_env_var: str | None = None
    default_model_id: str | None = None
    enabled: bool = True


class ModelDefinition(SynarchModel):
    id: str
    provider_id: str
    display_name: str
    context_window: int | None = None
    input_cost_per_million_tokens: float = 0.0
    output_cost_per_million_tokens: float = 0.0
    currency: str = "USD"
    supports_tool_calling: bool = False
    supports_structured_output: bool = False
    enabled: bool = True


class ModelPolicy(SynarchModel):
    id: str
    name: str
    default_model_id: str
    allowed_model_ids: list[str] = Field(default_factory=list)
    max_cost_per_task: float | None = None
    max_cost_per_day: float | None = None
    currency: str = "USD"
    require_human_approval_above: float | None = None


class ModelCallRequest(SynarchModel):
    agent_id: str
    model_id: str
    task_id: str | None = None
    project_id: str | None = None
    trace_id: str = Field(default_factory=lambda: new_id("trace"))
    purpose: str
    input_tokens_estimate: int | None = None
    max_output_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelUsage(SynarchModel):
    provider_id: str
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    currency: str = "USD"


class CostRecord(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("cost"))
    provider_id: str
    model_id: str
    agent_id: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    trace_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    currency: str = "USD"
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CostSummaryGroup(SynarchModel):
    group_key: str
    record_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    currency: str = "USD"


class CostSummary(SynarchModel):
    group_by: str
    groups: list[CostSummaryGroup] = Field(default_factory=list)
    record_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    currency: str = "USD"


class CostBudgetEvaluation(SynarchModel):
    budget: float
    spent: float = 0.0
    remaining: float = 0.0
    usage_ratio: float = 0.0
    budget_exceeded: bool = False
    record_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    currency: str = "USD"


class AuditLogRecord(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("audit"))
    actor_type: ActorType
    actor_id: str
    action: str
    target_type: str
    target_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentLifecycleRequest(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("agent_lifecycle"))
    action: LifecycleAction
    requested_by_type: ActorType
    requested_by_id: str
    reason: str
    proposed_agent: AgentDefinition | None = None
    target_agent_id: str | None = None
    status: ApprovalStatus = ApprovalStatus.requested
    requires_human_approval: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentLifecycleDecision(SynarchModel):
    request_id: str
    status: ApprovalStatus
    decided_by_type: ActorType
    decided_by_id: str
    rationale: str
    events_emitted: list[EventRecord] = Field(default_factory=list)
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ToolCallRequest(SynarchModel):
    agent_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str


class ToolResult(SynarchModel):
    tool_name: str
    status: TaskStatus = TaskStatus.completed
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AgentTaskRequest(SynarchModel):
    task: TaskRecord
    project: ProjectRecord | None = None
    world_view: LocalWorldView
    memory_context: MemoryContext | None = None
    provider_id: str | None = None
    model_id: str | None = None
    max_output_tokens: int | None = None


class AgentResult(SynarchModel):
    agent_id: str
    task_id: str
    status: TaskStatus
    actions_taken: list[str] = Field(default_factory=list)
    sub_tasks_created: list[TaskDraft] = Field(default_factory=list)
    events_emitted: list[EventRecord] = Field(default_factory=list)
    memory_candidates: list[MemoryItem] = Field(default_factory=list)
    model_usage: ModelUsage | None = None
    summary: str


class TaskRunResult(SynarchModel):
    trace_id: str
    task: TaskRecord
    project: ProjectRecord | None = None
    world_view: LocalWorldView
    memory_context: MemoryContext
    agent_result: AgentResult
    model_call_events: list[EventRecord] = Field(default_factory=list)
    memory_events: list[EventRecord] = Field(default_factory=list)
    cost_records: list[CostRecord] = Field(default_factory=list)


class ProjectTimeline(SynarchModel):
    project_id: str
    project: ProjectRecord
    tasks: list[TaskRecord] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)
    cost_records: list[CostRecord] = Field(default_factory=list)
    audit_logs: list[AuditLogRecord] = Field(default_factory=list)
    memory_items: list[MemoryItem] = Field(default_factory=list)
    total_cost: float = 0.0
    currency: str = "USD"
