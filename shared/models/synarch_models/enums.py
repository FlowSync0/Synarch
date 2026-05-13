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


class TaskReviewAction(StrEnum):
    retry = "retry"
    cancel = "cancel"
    update = "update"


class EventType(StrEnum):
    goal_received = "goal.received"
    routing_decided = "routing.decided"
    project_created = "project.created"
    project_workspace_created = "project_workspace.created"
    project_complexity_reported = "project_complexity.reported"
    project_split_requested = "project_split.requested"
    project_split_applied = "project_split.applied"
    task_created = "task.created"
    task_started = "task.started"
    task_heartbeat = "task.heartbeat"
    task_lease_expired = "task.lease_expired"
    task_skipped = "task.skipped"
    task_reviewed = "task.reviewed"
    task_completed = "task.completed"
    task_blocked = "task.blocked"
    agent_reported = "agent.reported"
    agent_created = "agent.created"
    agent_updated = "agent.updated"
    agent_deactivated = "agent.deactivated"
    agent_soul_created = "agent_soul.created"
    agent_project_assigned = "agent_project.assigned"
    memory_candidate_created = "memory.candidate_created"
    memory_status_updated = "memory.status_updated"
    memory_compacted = "memory.compacted"
    memory_embedding_backfilled = "memory.embedding_backfilled"
    model_call_started = "model_call.started"
    model_call_completed = "model_call.completed"
    model_call_failed = "model_call.failed"
    cost_recorded = "cost.recorded"
    scheduler_tick = "scheduler.tick"
    service_health_checked = "service_health.checked"
    connector_job_created = "connector_job.created"
    connector_job_run_recorded = "connector_job.run_recorded"
    connector_job_stopped = "connector_job.stopped"
    connector_job_resumed = "connector_job.resumed"
    connector_job_tick = "connector_job.tick"
    tool_called = "tool.called"
    tool_failed = "tool.failed"
    approval_requested = "approval.requested"
    approval_decided = "approval.decided"
    credential_grant_applied = "credential_grant.applied"


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


class MemoryStatus(StrEnum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"


class ServiceKind(StrEnum):
    internal = "internal"
    external = "external"
    ai_provider = "ai_provider"
    tool_provider = "tool_provider"


class ServiceHealthStatus(StrEnum):
    healthy = "healthy"
    unhealthy = "unhealthy"
    unknown = "unknown"


class ConnectorJobKind(StrEnum):
    cron = "cron"
    webhook = "webhook"


class ConnectorJobStatus(StrEnum):
    active = "active"
    stopped = "stopped"


class ConnectorJobRunStatus(StrEnum):
    completed = "completed"
    failed = "failed"
    skipped = "skipped"
