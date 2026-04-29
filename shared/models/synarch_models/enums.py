from enum import StrEnum


class Priority(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AgentStatus(StrEnum):
    active = "active"
    inactive = "inactive"
    degraded = "degraded"
    pending_approval = "pending_approval"


class TaskStatus(StrEnum):
    draft = "draft"
    queued = "queued"
    running = "running"
    completed = "completed"
    blocked = "blocked"
    failed = "failed"
    needs_review = "needs_review"


class EventType(StrEnum):
    goal_received = "goal.received"
    routing_decided = "routing.decided"
    project_created = "project.created"
    project_workspace_created = "project_workspace.created"
    project_complexity_reported = "project_complexity.reported"
    project_split_requested = "project_split.requested"
    task_created = "task.created"
    task_started = "task.started"
    task_completed = "task.completed"
    task_blocked = "task.blocked"
    agent_reported = "agent.reported"
    agent_created = "agent.created"
    agent_updated = "agent.updated"
    agent_deactivated = "agent.deactivated"
    agent_soul_created = "agent_soul.created"
    agent_project_assigned = "agent_project.assigned"
    memory_candidate_created = "memory.candidate_created"
    model_call_started = "model_call.started"
    model_call_completed = "model_call.completed"
    model_call_failed = "model_call.failed"
    cost_recorded = "cost.recorded"
    tool_called = "tool.called"
    tool_failed = "tool.failed"
    approval_requested = "approval.requested"
    approval_decided = "approval.decided"


class AiProviderType(StrEnum):
    openrouter = "openrouter"
    openai = "openai"
    anthropic = "anthropic"
    ollama = "ollama"
    vllm = "vllm"
    local = "local"
    custom = "custom"


class ActorType(StrEnum):
    user = "user"
    agent = "agent"
    system = "system"
    service = "service"


class LifecycleAction(StrEnum):
    create_agent = "create_agent"
    update_agent = "update_agent"
    deactivate_agent = "deactivate_agent"


class ApprovalStatus(StrEnum):
    requested = "requested"
    approved = "approved"
    rejected = "rejected"
    applied = "applied"


class ServiceKind(StrEnum):
    internal = "internal"
    external = "external"
    ai_provider = "ai_provider"
    tool_provider = "tool_provider"
