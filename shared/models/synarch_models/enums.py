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
    task_created = "task.created"
    task_started = "task.started"
    task_completed = "task.completed"
    task_blocked = "task.blocked"
    agent_reported = "agent.reported"
    memory_candidate_created = "memory.candidate_created"
    tool_called = "tool.called"
    tool_failed = "tool.failed"
