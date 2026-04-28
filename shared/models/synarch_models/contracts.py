from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import AgentStatus, EventType, Priority, TaskStatus


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
    assigned_agent_id: str
    depends_on: list[str] = Field(default_factory=list)
    priority: Priority = Priority.medium
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LocalWorldView(SynarchModel):
    agent_id: str
    role: str
    division: str
    peers: list[str] = Field(default_factory=list)
    manager: str | None = None
    active_projects: list[str] = Field(default_factory=list)
    permissions: PermissionBundle = Field(default_factory=PermissionBundle)
    capabilities: CapabilityMap = Field(default_factory=CapabilityMap)
    policies: list[str] = Field(default_factory=list)


class ProjectRecord(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("project"))
    title: str
    goal: str
    status: TaskStatus = TaskStatus.queued
    priority: Priority = Priority.medium
    owner_agent_id: str = "agent-direction"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskRecord(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("task"))
    project_id: str
    title: str
    status: TaskStatus = TaskStatus.queued
    assigned_agent_id: str
    depends_on: list[str] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventRecord(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("event"))
    type: EventType
    source_agent_id: str | None = None
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryItem(SynarchModel):
    id: str = Field(default_factory=lambda: new_id("memory"))
    scope: str
    content: str
    agent_id: str | None = None
    project_id: str | None = None
    embedding: list[float] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class MemoryContext(SynarchModel):
    agent_id: str
    project_id: str | None = None
    token_budget: int = 4000
    items: list[MemoryItem] = Field(default_factory=list)
    summary: str = ""


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
    world_view: LocalWorldView
    memory_context: MemoryContext | None = None


class AgentResult(SynarchModel):
    agent_id: str
    task_id: str
    status: TaskStatus
    actions_taken: list[str] = Field(default_factory=list)
    sub_tasks_created: list[TaskDraft] = Field(default_factory=list)
    events_emitted: list[EventRecord] = Field(default_factory=list)
    memory_candidates: list[MemoryItem] = Field(default_factory=list)
    summary: str
