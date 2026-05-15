from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

import synarch_gateway.main as gateway_main
from synarch_gateway.main import (
    app,
    get_control_plane_client,
    get_memory_client,
    get_state_client,
    get_task_runner,
)
from synarch_gateway.state_client import StateServiceRequestError, StateServiceUnavailable
from synarch_gateway.task_runner import TaskRunner, TaskRunnerUnavailable, next_ready_task
from synarch_models import (
    AgentDefinition,
    AgentLifecycleRequest,
    AgentProjectAssignment,
    AgentResult,
    AgentSoul,
    AgentTaskRequest,
    AiProviderType,
    AuditLogRecord,
    ConnectorJobMutationResult,
    ConnectorJobRecord,
    ConnectorJobResumeRequest,
    ConnectorJobRunRecord,
    ConnectorJobRunRequest,
    ConnectorJobRunResult,
    ConnectorJobStatus,
    ConnectorJobStopRequest,
    CostRecord,
    CredentialAccessDecision,
    CredentialAccessRequest,
    CredentialGrant,
    CredentialGrantApplication,
    CredentialGrantApplicationRequest,
    EventRecord,
    EventType,
    LocalWorldView,
    MemoryCompactionPlanItem,
    MemoryCompactionPlanRequest,
    MemoryCompactionPlanResult,
    MemoryCompactionPolicyRequest,
    MemoryCompactionPolicyResult,
    MemoryCompactionRequest,
    MemoryCompactionResult,
    MemoryContext,
    MemoryItem,
    MemoryStatus,
    MemoryStatusUpdate,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ModelUsage,
    PermissionBundle,
    ProjectComplexityAssessment,
    ProjectComplexityReport,
    ProjectRecord,
    ProjectSplitApplication,
    ProjectSplitRequest,
    ProjectWorkspace,
    ServiceDefinition,
    TaskDraft,
    TaskLeaseRecoveryResult,
    TaskRecord,
    TaskReviewDecision,
    TaskReviewResult,
    TaskStatus,
    ToolCallRequest,
)


class FakeStateClient:
    def __init__(self) -> None:
        self.projects: list[ProjectRecord] = []
        self.workspaces: list[ProjectWorkspace] = []
        self.assignments: list[AgentProjectAssignment] = []
        self.tasks: list[TaskRecord] = []
        self.services: list[ServiceDefinition] = []
        self.model_providers: list[ModelProviderConfig] = []
        self.model_definitions: list[ModelDefinition] = []
        self.model_policies: list[ModelPolicy] = []
        self.connector_jobs: list[ConnectorJobRecord] = []
        self.connector_job_runs: list[ConnectorJobRunRecord] = []
        self.events: list[EventRecord] = []
        self.costs: list[CostRecord] = []
        self.audit_logs: list[AuditLogRecord] = []
        self.agent_lifecycle_requests: list[AgentLifecycleRequest] = []
        self.credential_access_requests: list[CredentialAccessRequest] = []
        self.credential_grants: list[CredentialGrant] = []
        self.complexity_assessments: list[ProjectComplexityAssessment] = []
        self.split_applications: list[ProjectSplitApplication] = []
        self.headers: list[dict[str, str]] = []

    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord:
        self.headers.append(headers)
        self.projects.append(project)
        return project

    def create_project_workspace(
        self,
        workspace: ProjectWorkspace,
        *,
        headers: dict[str, str],
    ) -> ProjectWorkspace:
        self.headers.append(headers)
        self.workspaces.append(workspace)
        return workspace

    def list_project_workspaces(
        self,
        *,
        project_id: str | None = None,
        active: bool | None = None,
    ) -> list[ProjectWorkspace]:
        workspaces = self.workspaces
        if project_id is not None:
            workspaces = [
                workspace for workspace in workspaces if workspace.project_id == project_id
            ]
        if active is not None:
            workspaces = [workspace for workspace in workspaces if workspace.active is active]
        return workspaces

    def create_agent_project_assignment(
        self,
        assignment: AgentProjectAssignment,
        *,
        headers: dict[str, str],
    ) -> AgentProjectAssignment:
        self.headers.append(headers)
        self.assignments.append(assignment)
        return assignment

    def create_task(
        self,
        task: TaskRecord,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        self.headers.append(headers)
        self.tasks.append(task)
        return task

    def create_event(
        self,
        event: EventRecord,
        *,
        headers: dict[str, str],
    ) -> EventRecord:
        self.headers.append(headers)
        self.events.append(event)
        return event

    def list_events(
        self,
        *,
        event_type: str | None = None,
        trace_id: str | None = None,
    ) -> list[EventRecord]:
        events = self.events
        if event_type is not None:
            events = [event for event in events if event.type == event_type]
        if trace_id is not None:
            events = [event for event in events if event.trace_id == trace_id]
        return events

    def list_services(
        self,
        *,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[ServiceDefinition]:
        services = self.services
        if kind is not None:
            services = [service for service in services if service.kind == kind]
        if enabled is not None:
            services = [service for service in services if service.enabled is enabled]
        return services

    def get_model_provider(self, provider_id: str) -> ModelProviderConfig:
        for provider in self.model_providers:
            if provider.id == provider_id:
                return provider
        raise StateServiceRequestError(404, f"Unknown model provider: {provider_id}")

    def get_model_definition(self, model_id: str) -> ModelDefinition:
        for model in self.model_definitions:
            if model.id == model_id:
                return model
        raise StateServiceRequestError(404, f"Unknown model definition: {model_id}")

    def get_model_policy(self, policy_id: str) -> ModelPolicy:
        for policy in self.model_policies:
            if policy.id == policy_id:
                return policy
        raise StateServiceRequestError(404, f"Unknown model policy: {policy_id}")

    def assess_project_complexity(
        self,
        project_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectComplexityAssessment:
        self.headers.append(headers)
        assessment = ProjectComplexityAssessment(
            report=ProjectComplexityReport(
                project_id=project_id,
                task_count=len([task for task in self.tasks if task.project_id == project_id]),
                open_task_count=len(
                    [
                        task
                        for task in self.tasks
                        if task.project_id == project_id
                        and task.status not in {TaskStatus.completed, TaskStatus.failed}
                    ]
                ),
                score=4,
                threshold=10,
                split_recommended=False,
            )
        )
        self.complexity_assessments.append(assessment)
        return assessment

    def apply_project_split(
        self,
        split_request_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectSplitApplication:
        self.headers.append(headers)
        source_project = ProjectRecord(
            id="project-large",
            title="Large project",
            goal="Split this approved project.",
            owner_agent_id="agent-direction",
        )
        shard_project = ProjectRecord(
            id="project-large-shard-planning",
            title="Large project - planning",
            goal="Shard of Large project.",
            owner_agent_id="agent-direction",
        )
        shard_workspace = ProjectWorkspace(
            id="workspace-large-shard-planning",
            project_id=shard_project.id,
            name=shard_project.title,
            memory_scope=f"project:{shard_project.id}",
            allowed_agent_ids=["agent-direction"],
            bridge_project_ids=[source_project.id],
        )
        shard_task = TaskRecord(
            id="task-large-shard-plan",
            project_id=shard_project.id,
            title="Define execution plan for Large project - planning",
            assigned_agent_id="agent-direction",
            acceptance_criteria=["Shard plan is explicit."],
        )
        application = ProjectSplitApplication(
            request_id=split_request_id,
            split_request=ProjectSplitRequest(
                id=split_request_id,
                project_id=source_project.id,
                complexity_report_id="complexity-large",
                requested_by="agent-direction",
                reason="Project reached the split threshold.",
                proposed_shard_titles=[shard_project.title],
                status="applied",
            ),
            source_project_id=source_project.id,
            shard_projects=[shard_project],
            shard_workspaces=[shard_workspace],
            shard_tasks=[shard_task],
        )
        self.split_applications.append(application)
        return application

    def get_project(self, project_id: str) -> ProjectRecord:
        for project in self.projects:
            if project.id == project_id:
                return project
        return ProjectRecord(
            id=project_id,
            title="Demo project",
            goal="Demo project goal.",
            owner_agent_id="agent-direction",
        )

    def get_task(self, task_id: str) -> TaskRecord:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise ValueError(f"Unknown task: {task_id}")

    def list_tasks(self, *, project_id: str | None = None) -> list[TaskRecord]:
        if project_id is None:
            return self.tasks
        return [task for task in self.tasks if task.project_id == project_id]

    def list_task_review_queue(self, *, project_id: str | None = None) -> list[TaskRecord]:
        return [
            task
            for task in self.tasks
            if task.status == TaskStatus.needs_review
            and (project_id is None or task.project_id == project_id)
        ]

    def apply_task_review_decision(
        self,
        task_id: str,
        decision: TaskReviewDecision,
        *,
        headers: dict[str, str],
    ) -> TaskReviewResult:
        self.headers.append(headers)
        task = next(task for task in self.tasks if task.id == task_id)
        if task.status != TaskStatus.needs_review:
            raise StateServiceRequestError(409, f"Task is not in review: {task.status}")
        next_status = {
            "retry": TaskStatus.queued,
            "cancel": TaskStatus.failed,
            "update": TaskStatus.needs_review,
        }[decision.action]
        updated_task = task.model_copy(
            update={
                "status": next_status,
                "title": decision.title or task.title,
                "result": {
                    **(task.result or {}),
                    "review": {
                        "action": decision.action,
                        "reason": decision.reason,
                        "next_status": next_status,
                    },
                },
                "dead_letter_reason": None
                if decision.action == "retry"
                else task.dead_letter_reason,
                "dead_lettered_at": None
                if decision.action == "retry"
                else task.dead_lettered_at,
            }
        )
        self.tasks[self.tasks.index(task)] = updated_task
        event = EventRecord(
            type=EventType.task_reviewed,
            target=updated_task.project_id,
            payload={
                "task_id": updated_task.id,
                "action": decision.action,
                "next_status": updated_task.status,
            },
            trace_id=headers.get("x-synarch-trace-id"),
        )
        audit_log = AuditLogRecord(
            actor_type=headers.get("x-synarch-actor-type", "user"),
            actor_id=headers.get("x-synarch-actor-id", "local-user"),
            action="task.reviewed",
            target_type="task",
            target_id=updated_task.id,
            payload={"action": decision.action, "next_status": updated_task.status},
            trace_id=headers.get("x-synarch-trace-id"),
        )
        self.events.append(event)
        self.audit_logs.append(audit_log)
        return TaskReviewResult(task=updated_task, event=event, audit_log=audit_log)

    def recover_expired_task_leases(
        self,
        *,
        headers: dict[str, str],
    ) -> TaskLeaseRecoveryResult:
        self.headers.append(headers)
        return TaskLeaseRecoveryResult()

    def start_task(
        self,
        task_id: str,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        self.headers.append(headers)
        task = next(task for task in self.tasks if task.id == task_id)
        started_task = task.model_copy(update={"status": TaskStatus.running})
        self.tasks[self.tasks.index(task)] = started_task
        return started_task

    def record_task_result(
        self,
        task_id: str,
        result: AgentResult,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        self.headers.append(headers)
        task = next(task for task in self.tasks if task.id == task_id)
        recorded_task = task.model_copy(
            update={
                "status": result.status,
                "result": {
                    "summary": result.summary,
                    "tool_results": [
                        tool_result.model_dump(mode="json")
                        for tool_result in result.tool_results
                    ],
                    "tool_calls_requested": [
                        tool_call.model_dump(mode="json")
                        for tool_call in result.tool_calls_requested
                    ],
                },
            }
        )
        self.tasks[self.tasks.index(task)] = recorded_task
        return recorded_task

    def create_cost_record(
        self,
        cost: CostRecord,
        *,
        headers: dict[str, str],
    ) -> CostRecord:
        self.headers.append(headers)
        self.costs.append(cost)
        return cost

    def list_cost_records(
        self,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[CostRecord]:
        costs = self.costs
        if project_id is not None:
            costs = [cost for cost in costs if cost.project_id == project_id]
        if agent_id is not None:
            costs = [cost for cost in costs if cost.agent_id == agent_id]
        if provider_id is not None:
            costs = [cost for cost in costs if cost.provider_id == provider_id]
        if model_id is not None:
            costs = [cost for cost in costs if cost.model_id == model_id]
        if trace_id is not None:
            costs = [cost for cost in costs if cost.trace_id == trace_id]
        return costs

    def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[AuditLogRecord]:
        audits = self.audit_logs
        if actor_id is not None:
            audits = [audit for audit in audits if audit.actor_id == actor_id]
        if target_type is not None:
            audits = [audit for audit in audits if audit.target_type == target_type]
        if target_id is not None:
            audits = [audit for audit in audits if audit.target_id == target_id]
        if trace_id is not None:
            audits = [audit for audit in audits if audit.trace_id == trace_id]
        return audits

    def create_audit_log(
        self,
        audit: AuditLogRecord,
        *,
        headers: dict[str, str],
    ) -> AuditLogRecord:
        self.headers.append(headers)
        self.audit_logs.append(audit)
        return audit

    def create_agent_lifecycle_request(
        self,
        lifecycle_request: AgentLifecycleRequest,
        *,
        headers: dict[str, str],
    ) -> AgentLifecycleRequest:
        self.headers.append(headers)
        self.agent_lifecycle_requests.append(lifecycle_request)
        return lifecycle_request

    def create_credential_access_request(
        self,
        access_request: CredentialAccessRequest,
        *,
        headers: dict[str, str],
    ) -> CredentialAccessRequest:
        self.headers.append(headers)
        if any(
            existing_request.id == access_request.id
            for existing_request in self.credential_access_requests
        ):
            raise StateServiceRequestError(
                409,
                f"Record already exists: {access_request.id}",
            )
        self.credential_access_requests.append(access_request)
        return access_request

    def list_credential_access_requests(
        self,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> list[CredentialAccessRequest]:
        access_requests = self.credential_access_requests
        if project_id is not None:
            access_requests = [
                access_request
                for access_request in access_requests
                if access_request.project_id == project_id
            ]
        if task_id is not None:
            access_requests = [
                access_request
                for access_request in access_requests
                if access_request.task_id == task_id
            ]
        if agent_id is not None:
            access_requests = [
                access_request
                for access_request in access_requests
                if access_request.agent_id == agent_id
            ]
        if status is not None:
            access_requests = [
                access_request
                for access_request in access_requests
                if access_request.status == status
            ]
        return access_requests

    def decide_credential_access_request(
        self,
        request_id: str,
        decision: CredentialAccessDecision,
        *,
        headers: dict[str, str],
    ) -> CredentialAccessDecision:
        self.headers.append(headers)
        access_request = next(
            request
            for request in self.credential_access_requests
            if request.id == request_id
        )
        if access_request.status != "requested":
            raise StateServiceRequestError(
                409,
                f"Credential access request is already {access_request.status}",
            )
        updated_request = access_request.model_copy(update={"status": decision.status})
        self.credential_access_requests[
            self.credential_access_requests.index(access_request)
        ] = updated_request
        event = EventRecord(
            type=EventType.approval_decided,
            target=access_request.project_id,
            payload={
                "request_type": "credential_access",
                "credential_access_request_id": access_request.id,
                "status": decision.status,
                "rationale": decision.rationale,
            },
            trace_id=headers.get("x-synarch-trace-id"),
        )
        self.events.append(event)
        return decision.model_copy(update={"events_emitted": [event]})

    def apply_credential_access_grant(
        self,
        request_id: str,
        application: CredentialGrantApplicationRequest,
        *,
        headers: dict[str, str],
    ) -> CredentialGrantApplication:
        self.headers.append(headers)
        access_request = next(
            request
            for request in self.credential_access_requests
            if request.id == request_id
        )
        if access_request.status != "approved":
            raise StateServiceRequestError(
                409,
                "Credential access request must be approved before grants can be applied",
            )
        updated_request = access_request.model_copy(update={"status": "applied"})
        self.credential_access_requests[
            self.credential_access_requests.index(access_request)
        ] = updated_request
        grant = CredentialGrant(
            id=f"credential_grant_{request_id}_{application.service_id}",
            request_id=request_id,
            service_id=application.service_id,
            agent_id=access_request.agent_id,
            project_id=access_request.project_id,
            task_id=access_request.task_id,
            tool_name=access_request.tool_name,
            scopes=list(access_request.requested_scopes),
            granted_by_type=application.applied_by_type,
            granted_by_id=application.applied_by_id,
            rationale=application.rationale,
        )
        self.credential_grants.append(grant)
        event = EventRecord(
            type=EventType.credential_grant_applied,
            target=access_request.project_id,
            payload={
                "request_type": "credential_access",
                "credential_access_request_id": access_request.id,
                "credential_grant_id": grant.id,
                "service_id": application.service_id,
                "status": "applied",
            },
            trace_id=headers.get("x-synarch-trace-id"),
        )
        self.events.append(event)
        service = ServiceDefinition(
            id=application.service_id,
            name=application.service_id,
            kind="tool_provider",
            capabilities=[access_request.tool_name],
            credential_scopes=list(access_request.requested_scopes),
        )
        return CredentialGrantApplication(
            request_id=request_id,
            service_id=application.service_id,
            access_request=updated_request,
            grant=grant,
            service=service,
            events_emitted=[event],
        )

    def list_credential_grants(
        self,
        *,
        request_id: str | None = None,
        service_id: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        active: bool | None = None,
    ) -> list[CredentialGrant]:
        grants = self.credential_grants
        if request_id is not None:
            grants = [grant for grant in grants if grant.request_id == request_id]
        if service_id is not None:
            grants = [grant for grant in grants if grant.service_id == service_id]
        if agent_id is not None:
            grants = [grant for grant in grants if grant.agent_id == agent_id]
        if project_id is not None:
            grants = [grant for grant in grants if grant.project_id == project_id]
        if active is not None:
            grants = [grant for grant in grants if grant.active == active]
        return grants

    def get_connector_job(self, job_id: str) -> ConnectorJobRecord:
        for job in self.connector_jobs:
            if job.id == job_id:
                return job
        raise StateServiceRequestError(404, f"Unknown connector job: {job_id}")

    def list_connector_jobs(
        self,
        *,
        service_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        owner_agent_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        due_before: datetime | None = None,
    ) -> list[ConnectorJobRecord]:
        jobs = self.connector_jobs
        if service_id is not None:
            jobs = [job for job in jobs if job.service_id == service_id]
        if project_id is not None:
            jobs = [job for job in jobs if job.project_id == project_id]
        if task_id is not None:
            jobs = [job for job in jobs if job.task_id == task_id]
        if owner_agent_id is not None:
            jobs = [job for job in jobs if job.owner_agent_id == owner_agent_id]
        if kind is not None:
            jobs = [job for job in jobs if job.kind == kind]
        if status is not None:
            jobs = [job for job in jobs if job.status == status]
        if due_before is not None:
            jobs = [
                job
                for job in jobs
                if job.next_run_at is None or job.next_run_at <= due_before
            ]
        return sorted(jobs, key=lambda job: job.created_at)

    def create_connector_job(
        self,
        job: ConnectorJobRecord,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobMutationResult:
        self.headers.append(headers)
        self.connector_jobs.append(job)
        event = EventRecord(
            type=EventType.connector_job_created,
            source_agent_id=job.owner_agent_id,
            target=job.project_id or job.service_id,
            payload={
                "connector_job_id": job.id,
                "service_id": job.service_id,
                "kind": job.kind,
                "status": job.status,
            },
            trace_id=headers.get("x-synarch-trace-id"),
        )
        audit = AuditLogRecord(
            actor_type=headers.get("x-synarch-actor-type", "agent"),
            actor_id=headers.get("x-synarch-actor-id", job.owner_agent_id),
            action="connector_job.created",
            target_type="connector_job",
            target_id=job.id,
            payload={
                "connector_job_id": job.id,
                "service_id": job.service_id,
                "kind": job.kind,
                "status": job.status,
            },
            trace_id=headers.get("x-synarch-trace-id"),
        )
        self.events.append(event)
        self.audit_logs.append(audit)
        return ConnectorJobMutationResult(job=job, event=event, audit_log=audit)

    def record_connector_job_run(
        self,
        job_id: str,
        run_request: ConnectorJobRunRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobRunResult:
        self.headers.append(headers)
        job = self.get_connector_job(job_id)
        run = ConnectorJobRunRecord(
            job_id=job.id,
            service_id=job.service_id,
            project_id=job.project_id,
            task_id=job.task_id,
            owner_agent_id=job.owner_agent_id,
            status=run_request.status,
            triggered_by_type=run_request.triggered_by_type,
            triggered_by_id=run_request.triggered_by_id,
            trace_id=headers.get("x-synarch-trace-id"),
            output=run_request.output,
            error=run_request.error,
            started_at=run_request.started_at,
            completed_at=run_request.completed_at,
        )
        self.connector_job_runs.append(run)
        event = EventRecord(
            type=EventType.connector_job_run_recorded,
            source_agent_id=job.owner_agent_id,
            target=job.project_id or job.service_id,
            payload={
                "connector_job_id": job.id,
                "connector_job_run_id": run.id,
                "run_status": run.status,
            },
            trace_id=headers.get("x-synarch-trace-id"),
        )
        audit = AuditLogRecord(
            actor_type=headers.get("x-synarch-actor-type", "service"),
            actor_id=headers.get(
                "x-synarch-actor-id",
                "gateway-connector-job-executor",
            ),
            action="connector_job.run_recorded",
            target_type="connector_job",
            target_id=job.id,
            payload={
                "connector_job_id": job.id,
                "connector_job_run_id": run.id,
                "run_status": run.status,
            },
            trace_id=headers.get("x-synarch-trace-id"),
        )
        self.events.append(event)
        self.audit_logs.append(audit)
        return ConnectorJobRunResult(run=run, event=event, audit_log=audit)

    def stop_connector_job(
        self,
        job_id: str,
        stop_request: ConnectorJobStopRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobMutationResult:
        self.headers.append(headers)
        job = self.get_connector_job(job_id)
        if job.status == ConnectorJobStatus.stopped:
            raise StateServiceRequestError(409, "Connector job is already stopped")
        stopped_job = job.model_copy(
            update={
                "status": ConnectorJobStatus.stopped,
                "updated_at": stop_request.stopped_at,
                "next_run_at": None,
                "stopped_at": stop_request.stopped_at,
            }
        )
        self.connector_jobs[self.connector_jobs.index(job)] = stopped_job
        event = EventRecord(
            type=EventType.connector_job_stopped,
            source_agent_id=job.owner_agent_id,
            target=job.project_id or job.service_id,
            payload={"connector_job_id": job.id, "reason": stop_request.reason},
            trace_id=headers.get("x-synarch-trace-id"),
        )
        audit = AuditLogRecord(
            actor_type=stop_request.stopped_by_type,
            actor_id=stop_request.stopped_by_id,
            action="connector_job.stopped",
            target_type="connector_job",
            target_id=job.id,
            payload={"connector_job_id": job.id, "reason": stop_request.reason},
            trace_id=headers.get("x-synarch-trace-id"),
        )
        self.events.append(event)
        self.audit_logs.append(audit)
        return ConnectorJobMutationResult(job=stopped_job, event=event, audit_log=audit)

    def resume_connector_job(
        self,
        job_id: str,
        resume_request: ConnectorJobResumeRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobMutationResult:
        self.headers.append(headers)
        job = self.get_connector_job(job_id)
        if job.status == ConnectorJobStatus.active:
            raise StateServiceRequestError(409, "Connector job is already active")
        resumed_job = job.model_copy(
            update={
                "status": ConnectorJobStatus.active,
                "updated_at": resume_request.resumed_at,
                "next_run_at": resume_request.next_run_at or resume_request.resumed_at,
                "stopped_at": None,
            }
        )
        self.connector_jobs[self.connector_jobs.index(job)] = resumed_job
        event = EventRecord(
            type=EventType.connector_job_resumed,
            source_agent_id=job.owner_agent_id,
            target=job.project_id or job.service_id,
            payload={"connector_job_id": job.id, "reason": resume_request.reason},
            trace_id=headers.get("x-synarch-trace-id"),
        )
        audit = AuditLogRecord(
            actor_type=resume_request.resumed_by_type,
            actor_id=resume_request.resumed_by_id,
            action="connector_job.resumed",
            target_type="connector_job",
            target_id=job.id,
            payload={"connector_job_id": job.id, "reason": resume_request.reason},
            trace_id=headers.get("x-synarch-trace-id"),
        )
        self.events.append(event)
        self.audit_logs.append(audit)
        return ConnectorJobMutationResult(job=resumed_job, event=event, audit_log=audit)


class FailingStateClient(FakeStateClient):
    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord:
        raise StateServiceUnavailable("state-service offline")


class ClaimConflictStateClient(FakeStateClient):
    def __init__(self, conflict_task_id: str) -> None:
        super().__init__()
        self.conflict_task_id = conflict_task_id
        self.conflict_raised = False

    def start_task(
        self,
        task_id: str,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        if task_id == self.conflict_task_id and not self.conflict_raised:
            self.conflict_raised = True
            self.headers.append(headers)
            task = next(task for task in self.tasks if task.id == task_id)
            self.tasks[self.tasks.index(task)] = task.model_copy(
                update={"status": TaskStatus.running}
            )
            raise StateServiceRequestError(409, "Task is already running")
        return super().start_task(task_id, headers=headers)


class InactiveAgentStateClient(FakeStateClient):
    def __init__(self, inactive_task_id: str) -> None:
        super().__init__()
        self.inactive_task_id = inactive_task_id

    def start_task(
        self,
        task_id: str,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        if task_id == self.inactive_task_id:
            self.headers.append(headers)
            task = next(task for task in self.tasks if task.id == task_id)
            raise StateServiceRequestError(
                409,
                f"Agent is not active: {task.assigned_agent_id}",
            )
        return super().start_task(task_id, headers=headers)


class RecoveringStateClient(FakeStateClient):
    def recover_expired_task_leases(
        self,
        *,
        headers: dict[str, str],
    ) -> TaskLeaseRecoveryResult:
        self.headers.append(headers)
        inspected_at = datetime.now(UTC)
        recovered_tasks: list[TaskRecord] = []
        events: list[EventRecord] = []
        for task in list(self.tasks):
            if (
                task.status != TaskStatus.running
                or task.lease_expires_at is None
                or task.lease_expires_at > inspected_at
                or task.attempt_count >= task.max_attempts
            ):
                continue
            recovered_task = task.model_copy(
                update={
                    "status": TaskStatus.queued,
                    "lease_owner_id": None,
                    "lease_expires_at": None,
                    "last_heartbeat_at": None,
                    "retry_after_at": inspected_at + timedelta(seconds=60),
                }
            )
            self.tasks[self.tasks.index(task)] = recovered_task
            recovered_tasks.append(recovered_task)
            events.append(
                EventRecord(
                    type=EventType.task_lease_expired,
                    source_agent_id=recovered_task.assigned_agent_id,
                    target=recovered_task.project_id,
                    payload={"task_id": recovered_task.id, "will_retry": True},
                )
            )
        return TaskLeaseRecoveryResult(
            inspected_at=inspected_at,
            recovered_task_ids=[task.id for task in recovered_tasks],
            recovered_tasks=recovered_tasks,
            events=events,
        )


class FakeControlPlaneClient:
    def __init__(self, world_views: dict[str, LocalWorldView] | None = None) -> None:
        self.world_views = world_views or {}

    def get_world_view(self, agent_id: str) -> LocalWorldView:
        if agent_id in self.world_views:
            return self.world_views[agent_id]
        return LocalWorldView(agent_id=agent_id, role="Code and infra", division="dev")


class FakeMemoryClient:
    def __init__(self, context_items: list[MemoryItem] | None = None) -> None:
        self.contexts: list[MemoryContext] = []
        self.context_items = context_items or []
        self.items: list[MemoryItem] = []
        self.items_by_id: dict[str, MemoryItem] = {}
        self.compaction_plan_requests: list[MemoryCompactionPlanRequest] = []

    def assemble_context(self, context: MemoryContext) -> MemoryContext:
        self.contexts.append(context)
        return context.model_copy(
            update={
                "items": self.context_items,
                "summary": "Fake context assembled.",
                "tokens_used": sum(
                    max(1, (len(item.content) + 3) // 4) for item in self.context_items
                ),
            }
        )

    def create_memory_item(self, item: MemoryItem) -> MemoryItem:
        self.items.append(item)
        self.items_by_id[item.id] = item
        return item

    def list_memory_items(
        self,
        *,
        scope: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        status: MemoryStatus | None = None,
    ) -> list[MemoryItem]:
        items = list(self.items_by_id.values())
        if scope is not None:
            items = [item for item in items if item.scope == scope]
        if agent_id is not None:
            items = [item for item in items if item.agent_id == agent_id]
        if project_id is not None:
            items = [item for item in items if item.project_id == project_id]
        if status is not None:
            items = [item for item in items if item.status == status]
        return items

    def update_memory_status(self, item_id: str, update: MemoryStatusUpdate) -> MemoryItem:
        item = self.items_by_id[item_id]
        updated = item.model_copy(update={"status": update.status})
        self.items_by_id[item_id] = updated
        return updated

    def compact_memory_items(
        self, request: MemoryCompactionRequest
    ) -> MemoryCompactionResult:
        source_items = [
            item
            for item in self.list_memory_items(
                scope=request.scope,
                agent_id=request.agent_id,
                project_id=request.project_id,
                status=MemoryStatus.approved,
            )
            if item.metadata.get("kind") != "compaction"
        ][: request.max_source_items]
        compacted_item = self.create_memory_item(
            MemoryItem(
                id="memory-compacted",
                scope=request.scope,
                content="Compacted: " + ", ".join(item.id for item in source_items),
                status=request.status,
                agent_id=request.agent_id,
                project_id=request.project_id,
                metadata={
                    "kind": "compaction",
                    "source_memory_ids": [item.id for item in source_items],
                    "source_count": len(source_items),
                    "source_tokens": sum(
                        max(1, (len(item.content) + 3) // 4) for item in source_items
                    ),
                },
            )
        )
        return MemoryCompactionResult(
            compacted_item=compacted_item,
            source_memory_ids=[item.id for item in source_items],
            source_count=len(source_items),
            source_tokens=sum(max(1, (len(item.content) + 3) // 4) for item in source_items),
        )

    def compact_memory_items_if_needed(
        self, request: MemoryCompactionPolicyRequest
    ) -> MemoryCompactionPolicyResult:
        compaction_request = MemoryCompactionRequest(
            scope=request.scope,
            project_id=request.project_id,
            agent_id=request.agent_id,
            status=request.status,
            max_source_items=request.max_source_items,
            max_summary_chars=request.max_summary_chars,
        )
        source_items = [
            item
            for item in self.list_memory_items(
                scope=request.scope,
                agent_id=request.agent_id,
                project_id=request.project_id,
                status=MemoryStatus.approved,
            )
            if item.metadata.get("kind") != "compaction"
        ][: request.max_source_items]
        source_tokens = sum(max(1, (len(item.content) + 3) // 4) for item in source_items)
        if source_tokens <= request.min_source_tokens:
            return MemoryCompactionPolicyResult(
                compaction_needed=False,
                reason="source_tokens_within_threshold",
                threshold_tokens=request.min_source_tokens,
                source_memory_ids=[item.id for item in source_items],
                source_count=len(source_items),
                source_tokens=source_tokens,
            )
        existing_compacted_item = next(
            (
                item
                for item in self.items_by_id.values()
                if item.scope == request.scope
                and item.project_id == request.project_id
                and item.agent_id == request.agent_id
                and item.status in {MemoryStatus.approved, MemoryStatus.proposed}
                and item.metadata.get("kind") == "compaction"
                and item.metadata.get("source_memory_ids")
                == [source_item.id for source_item in source_items]
            ),
            None,
        )
        if existing_compacted_item is not None:
            return MemoryCompactionPolicyResult(
                compaction_needed=False,
                reason="matching_compaction_exists",
                threshold_tokens=request.min_source_tokens,
                source_memory_ids=[item.id for item in source_items],
                source_count=len(source_items),
                source_tokens=source_tokens,
                existing_compacted_item=existing_compacted_item,
            )
        compaction = self.compact_memory_items(compaction_request)
        return MemoryCompactionPolicyResult(
            compaction_needed=True,
            reason="source_tokens_exceed_threshold",
            threshold_tokens=request.min_source_tokens,
            source_memory_ids=compaction.source_memory_ids,
            source_count=compaction.source_count,
            source_tokens=compaction.source_tokens,
            compaction=compaction,
        )

    def plan_memory_compaction(
        self, request: MemoryCompactionPlanRequest
    ) -> MemoryCompactionPlanResult:
        self.compaction_plan_requests.append(request)
        groups: dict[tuple[str, str | None, str | None], list[MemoryItem]] = {}
        allowed_scopes = set(request.scopes) if request.scopes is not None else None
        for item in self.items_by_id.values():
            if item.status != MemoryStatus.approved:
                continue
            if item.metadata.get("kind") == "compaction":
                continue
            if allowed_scopes is not None and item.scope not in allowed_scopes:
                continue
            if request.project_id is not None and item.project_id != request.project_id:
                continue
            if request.agent_id is not None and item.agent_id != request.agent_id:
                continue
            groups.setdefault((item.scope, item.project_id, item.agent_id), []).append(item)
        plan_items: list[MemoryCompactionPlanItem] = []
        for _, group in sorted(groups.items()):
            source_items = sorted(group, key=lambda item: (item.created_at, item.id))[
                : request.max_source_items
            ]
            source_tokens = sum(
                max(1, (len(item.content) + 3) // 4) for item in source_items
            )
            if source_tokens <= request.min_source_tokens:
                continue
            source_memory_ids = [item.id for item in source_items]
            if any(
                item.metadata.get("kind") == "compaction"
                and item.metadata.get("source_memory_ids") == source_memory_ids
                and item.scope == source_items[0].scope
                and item.project_id == source_items[0].project_id
                and item.agent_id == source_items[0].agent_id
                for item in self.items_by_id.values()
            ):
                continue
            plan_items.append(
                MemoryCompactionPlanItem(
                    scope=source_items[0].scope,
                    project_id=source_items[0].project_id,
                    agent_id=source_items[0].agent_id,
                    source_memory_ids=source_memory_ids,
                    source_count=len(source_items),
                    source_tokens=source_tokens,
                )
            )
        return MemoryCompactionPlanResult(
            threshold_tokens=request.min_source_tokens,
            inspected_scope_count=len(groups),
            planned_scope_count=len(plan_items),
            items=plan_items[: request.max_scopes],
        )


class FakeQueryEmbeddingProvider:
    provider_id = "provider-test-embedding"
    model_id = "model-test-embedding"

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.texts.append(text)
        embedding = [0.0] * 1536
        embedding[min(len(self.texts) - 1, 1535)] = 1.0
        return embedding


class FakeAgentRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[AgentTaskRequest] = []

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        self.requests.append(request)
        return AgentResult(
            agent_id=request.world_view.agent_id,
            task_id=request.task.id,
            status=TaskStatus.needs_review,
            actions_taken=["Loaded LocalWorldView", "Prepared execution plan"],
            memory_candidates=[
                MemoryItem(
                    scope="global",
                    content="Remember that this project needs explicit acceptance criteria.",
                )
            ],
            model_usage=ModelUsage(
                provider_id=request.provider_id or "provider-local-runtime-stub",
                model_id=request.model_id or "model-local-runtime-stub",
                input_tokens=123,
                output_tokens=45,
                total_cost=0.000021,
            ),
            summary="Runtime stub prepared the task for review.",
        )


class CompletingAgentRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[AgentTaskRequest] = []

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        self.requests.append(request)
        return AgentResult(
            agent_id=request.world_view.agent_id,
            task_id=request.task.id,
            status=TaskStatus.completed,
            actions_taken=["Completed deterministic task"],
            model_usage=ModelUsage(
                provider_id=request.provider_id or "provider-local-runtime-stub",
                model_id=request.model_id or "model-local-runtime-stub",
                input_tokens=10,
                output_tokens=5,
                total_cost=0.000001,
            ),
            summary=f"Completed {request.task.title}.",
        )


class SubTaskAgentRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[AgentTaskRequest] = []

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        self.requests.append(request)
        return AgentResult(
            agent_id=request.world_view.agent_id,
            task_id=request.task.id,
            status=TaskStatus.completed,
            actions_taken=["Split the next supplier workflow into debuggable tasks"],
            sub_tasks_created=[
                TaskDraft(
                    title="Find supplier directories",
                    description="Identify the first vetted supplier directory to inspect.",
                    assigned_agent_id="agent-ops-sourcing",
                    acceptance_criteria=["Directory URL and selection rationale are recorded."],
                    sequence=1,
                ),
                TaskDraft(
                    title="Contact first supplier",
                    description="Prepare the first supplier contact step after source selection.",
                    assigned_agent_id="agent-ops-sourcing",
                    depends_on=["Find supplier directories", "invented-child-task-id"],
                    acceptance_criteria=[
                        "Contact channel, message, and stop condition are recorded."
                    ],
                    sequence=2,
                ),
            ],
            summary="Created the next supplier workflow slices.",
        )


class LifecycleProposingAgentRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[AgentTaskRequest] = []

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        self.requests.append(request)
        proposed_agent = AgentDefinition(
            id="agent-ops-sourcing-researcher",
            name="IA Ops Researcher",
            role="Supplier research specialist",
            division="ops",
            manager_id=request.world_view.agent_id,
            created_by=request.world_view.agent_id,
        )
        return AgentResult(
            agent_id=request.world_view.agent_id,
            task_id=request.task.id,
            status=TaskStatus.completed,
            actions_taken=["Proposed a bounded specialist for supplier research"],
            lifecycle_requests_created=[
                AgentLifecycleRequest(
                    action="create_agent",
                    requested_by_type="user",
                    requested_by_id="malicious-client-value",
                    reason="Supplier sourcing needs a dedicated research worker.",
                    proposed_agent=proposed_agent,
                    proposed_soul=AgentSoul(
                        agent_id=proposed_agent.id,
                        identity="Ops sourcing researcher",
                        mission="Research suppliers with traceable source evidence.",
                        responsibilities=["Find supplier directories", "Record source evidence"],
                        boundaries=["Do not contact suppliers without approved credentials"],
                        escalation_rules=["Escalate missing credentials to the manager"],
                        created_by=request.world_view.agent_id,
                    ),
                    requires_human_approval=False,
                )
            ],
            summary="Requested creation of a supplier research worker.",
        )


class ToolLoopAgentRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[AgentTaskRequest] = []

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        self.requests.append(request)
        if not request.tool_results:
            return AgentResult(
                agent_id=request.world_view.agent_id,
                task_id=request.task.id,
                status=TaskStatus.needs_review,
                actions_taken=["Requested source evidence before finalizing"],
                tool_calls_requested=[
                    ToolCallRequest(
                        agent_id=request.world_view.agent_id,
                        tool_name="web.fetch",
                        service_id="connector-supplier-web",
                        project_id=request.task.project_id,
                        task_id=request.task.id,
                        reason="Fetch source evidence for the supplier research task.",
                        arguments={"url": "https://example.com", "max_bytes": 2048},
                    )
                ],
                model_usage=ModelUsage(
                    provider_id=request.provider_id or "provider-local-runtime-stub",
                    model_id=request.model_id or "model-local-runtime-stub",
                    input_tokens=20,
                    output_tokens=10,
                    total_cost=0.000002,
                ),
                summary="Need source evidence before final answer.",
            )

        assert request.tool_results[0].tool_name == "web.fetch"
        assert request.tool_results[0].output["title"] == "Example Domain"
        return AgentResult(
            agent_id=request.world_view.agent_id,
            task_id=request.task.id,
            status=TaskStatus.completed,
            actions_taken=["Reviewed fetched source evidence"],
            model_usage=ModelUsage(
                provider_id=request.provider_id or "provider-local-runtime-stub",
                model_id=request.model_id or "model-local-runtime-stub",
                input_tokens=30,
                output_tokens=12,
                total_cost=0.000003,
            ),
            summary="Completed supplier source verification from Example Domain.",
        )


class ConnectorJobToolLoopAgentRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[AgentTaskRequest] = []

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        self.requests.append(request)
        if not request.tool_results:
            return AgentResult(
                agent_id=request.world_view.agent_id,
                task_id=request.task.id,
                status=TaskStatus.needs_review,
                actions_taken=["Requested durable supplier follow-up job"],
                tool_calls_requested=[
                    ToolCallRequest(
                        agent_id=request.world_view.agent_id,
                        tool_name="connector.job.create",
                        service_id="connector-supplier-web",
                        project_id=request.task.project_id,
                        task_id=request.task.id,
                        reason="Schedule a bounded supplier follow-up check.",
                        arguments={
                            "id": "connector-job-task-runner-followup",
                            "kind": "cron",
                            "schedule": "*/30 * * * *",
                            "purpose": "Fetch supplier evidence before the next follow-up.",
                            "run_tool_name": "web.fetch",
                            "run_arguments": {
                                "url": "https://example.com",
                                "max_bytes": 1024,
                            },
                            "metadata": {"max_runs": 2},
                        },
                    )
                ],
                model_usage=ModelUsage(
                    provider_id=request.provider_id or "provider-local-runtime-stub",
                    model_id=request.model_id or "model-local-runtime-stub",
                    input_tokens=24,
                    output_tokens=16,
                    total_cost=0.000003,
                ),
                summary="Need a durable follow-up job before finalizing.",
            )

        tool_result = request.tool_results[0]
        assert tool_result.tool_name == "connector.job.create"
        assert tool_result.output["connector_job_id"] == "connector-job-task-runner-followup"
        return AgentResult(
            agent_id=request.world_view.agent_id,
            task_id=request.task.id,
            status=TaskStatus.completed,
            actions_taken=["Confirmed durable supplier follow-up job"],
            model_usage=ModelUsage(
                provider_id=request.provider_id or "provider-local-runtime-stub",
                model_id=request.model_id or "model-local-runtime-stub",
                input_tokens=18,
                output_tokens=8,
                total_cost=0.000002,
            ),
            summary="Created a bounded supplier follow-up connector job.",
        )


class ConnectorJobStopToolLoopAgentRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[AgentTaskRequest] = []

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        self.requests.append(request)
        if not request.tool_results:
            return AgentResult(
                agent_id=request.world_view.agent_id,
                task_id=request.task.id,
                status=TaskStatus.needs_review,
                actions_taken=["Requested stop for completed supplier follow-up job"],
                tool_calls_requested=[
                    ToolCallRequest(
                        agent_id=request.world_view.agent_id,
                        tool_name="connector.job.stop",
                        service_id="connector-supplier-web",
                        project_id=request.task.project_id,
                        task_id=request.task.id,
                        reason="Supplier replied and the follow-up loop is complete.",
                        arguments={
                            "job_id": "connector-job-task-runner-stop",
                            "reason": "Supplier replied; loop complete.",
                        },
                    )
                ],
                model_usage=ModelUsage(
                    provider_id=request.provider_id or "provider-local-runtime-stub",
                    model_id=request.model_id or "model-local-runtime-stub",
                    input_tokens=16,
                    output_tokens=8,
                    total_cost=0.000002,
                ),
                summary="Need to stop the follow-up job before finalizing.",
            )

        tool_result = request.tool_results[0]
        assert tool_result.tool_name == "connector.job.stop"
        assert tool_result.output["connector_job_id"] == "connector-job-task-runner-stop"
        return AgentResult(
            agent_id=request.world_view.agent_id,
            task_id=request.task.id,
            status=TaskStatus.completed,
            actions_taken=["Confirmed supplier follow-up job stopped"],
            model_usage=ModelUsage(
                provider_id=request.provider_id or "provider-local-runtime-stub",
                model_id=request.model_id or "model-local-runtime-stub",
                input_tokens=14,
                output_tokens=6,
                total_cost=0.000001,
            ),
            summary="Stopped the completed supplier follow-up connector job.",
        )


class ConnectorJobListThenStopToolLoopAgentRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[AgentTaskRequest] = []

    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        self.requests.append(request)
        if not request.tool_results:
            return AgentResult(
                agent_id=request.world_view.agent_id,
                task_id=request.task.id,
                status=TaskStatus.needs_review,
                actions_taken=["Requested active connector job inventory"],
                tool_calls_requested=[
                    ToolCallRequest(
                        agent_id=request.world_view.agent_id,
                        tool_name="connector.job.list",
                        service_id="connector-supplier-web",
                        project_id=request.task.project_id,
                        task_id=request.task.id,
                        reason="Find the active follow-up job before stopping it.",
                        arguments={"status": "active", "limit": 10},
                    ),
                    ToolCallRequest(
                        agent_id=request.world_view.agent_id,
                        tool_name="connector.job.stop",
                        service_id="connector-supplier-web",
                        project_id=request.task.project_id,
                        task_id=request.task.id,
                        reason="Premature stop request before observing list output.",
                        arguments={
                            "job_id": "connector-job-unobserved",
                            "reason": "Premature stop should wait for list result.",
                        },
                    )
                ],
                model_usage=ModelUsage(
                    provider_id=request.provider_id or "provider-local-runtime-stub",
                    model_id=request.model_id or "model-local-runtime-stub",
                    input_tokens=18,
                    output_tokens=8,
                    total_cost=0.000002,
                ),
                summary="Need connector job inventory before acting.",
            )

        if len(request.tool_results) == 1:
            list_result = request.tool_results[0]
            assert list_result.tool_name == "connector.job.list"
            listed_jobs = list_result.output["connector_jobs"]
            assert isinstance(listed_jobs, list)
            assert [job["id"] for job in listed_jobs] == [
                "connector-job-list-then-stop"
            ]
            return AgentResult(
                agent_id=request.world_view.agent_id,
                task_id=request.task.id,
                status=TaskStatus.needs_review,
                actions_taken=["Selected active connector job to stop"],
                tool_calls_requested=[
                    ToolCallRequest(
                        agent_id=request.world_view.agent_id,
                        tool_name="connector.job.list",
                        service_id="connector-supplier-web",
                        project_id=request.task.project_id,
                        task_id=request.task.id,
                        reason="Duplicate list request that should not be replayed.",
                        arguments={"status": "active", "limit": 10},
                    ),
                    ToolCallRequest(
                        agent_id=request.world_view.agent_id,
                        tool_name="connector.job.stop",
                        service_id="connector-supplier-web",
                        project_id=request.task.project_id,
                        task_id=request.task.id,
                        reason="Stop the completed follow-up job discovered by list.",
                        arguments={
                            "job_id": "connector-job-list-then-stop",
                            "reason": "Supplier replied; follow-up loop complete.",
                        },
                    )
                ],
                model_usage=ModelUsage(
                    provider_id=request.provider_id or "provider-local-runtime-stub",
                    model_id=request.model_id or "model-local-runtime-stub",
                    input_tokens=20,
                    output_tokens=8,
                    total_cost=0.000002,
                ),
                summary="Need to stop the selected connector job.",
            )

        stop_result = request.tool_results[1]
        assert stop_result.tool_name == "connector.job.stop"
        assert stop_result.output["connector_job_id"] == "connector-job-list-then-stop"
        return AgentResult(
            agent_id=request.world_view.agent_id,
            task_id=request.task.id,
            status=TaskStatus.completed,
            actions_taken=["Stopped discovered supplier follow-up job"],
            model_usage=ModelUsage(
                provider_id=request.provider_id or "provider-local-runtime-stub",
                model_id=request.model_id or "model-local-runtime-stub",
                input_tokens=14,
                output_tokens=6,
                total_cost=0.000001,
            ),
            summary="Listed and stopped the completed supplier follow-up connector job.",
        )


class FailingAgentRuntimeClient:
    def run_task(self, request: AgentTaskRequest) -> AgentResult:
        raise TaskRunnerUnavailable("runtime offline")


def test_goal_routes_to_dev_agent() -> None:
    response = TestClient(app).post(
        "/goals",
        json={"goal": "Corriger un bug API sur le gateway", "priority": "high"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "agent-dev" in payload["target_agents"]
    assert payload["project_intent"]["priority"] == "high"


def test_goal_submit_persists_project_tasks_and_events() -> None:
    state_client = FakeStateClient()
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/goals/submit",
            json={
                "goal": "Traiter une facture fournisseur avec TVA",
                "priority": "high",
                "requester": "hugo",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["project"]["goal"] == "Traiter une facture fournisseur avec TVA"
    assert payload["project"]["owner_agent_id"] == "agent-direction"
    assert payload["workspace"]["memory_scope"] == f"project:{payload['project']['id']}"
    assert payload["workspace"]["allowed_agent_ids"] == ["agent-direction", "agent-finance"]
    assert [assignment["agent_id"] for assignment in payload["assignments"]] == [
        "agent-direction",
        "agent-finance",
    ]
    assert [task["assigned_agent_id"] for task in payload["tasks"]] == [
        "agent-direction",
        "agent-finance",
        "agent-finance",
        "agent-direction",
    ]
    assert payload["tasks"][1]["depends_on"] == [payload["tasks"][0]["id"]]
    assert payload["tasks"][2]["depends_on"] == [payload["tasks"][1]["id"]]
    assert payload["tasks"][3]["depends_on"] == [payload["tasks"][2]["id"]]
    assert all(task["acceptance_criteria"] for task in payload["tasks"])
    assert [task["sequence"] for task in payload["tasks"]] == [1, 2, 3, 4]
    assert [event["type"] for event in payload["events"]] == [
        "goal.received",
        "routing.decided",
        "project.created",
        "task.created",
        "task.created",
        "task.created",
        "task.created",
    ]
    task_events = payload["events"][3:]
    assert [event["payload"]["sequence"] for event in task_events] == [1, 2, 3, 4]
    assert {event["trace_id"] for event in payload["events"]} == {payload["trace_id"]}
    assert payload["complexity_assessment"]["report"]["project_id"] == payload["project"]["id"]
    assert payload["complexity_assessment"]["report"]["split_recommended"] is False
    assert state_client.complexity_assessments[0].report.project_id == payload["project"]["id"]
    assert state_client.projects[0].id == payload["project"]["id"]
    assert state_client.workspaces[0].project_id == payload["project"]["id"]
    assert state_client.assignments[0].workspace_id == payload["workspace"]["id"]
    assert state_client.headers[0]["x-synarch-actor-id"] == "hugo"
    assert state_client.headers[0]["x-synarch-trace-id"] == payload["trace_id"]
    assert state_client.headers[-1]["x-synarch-actor-id"] == "gateway-goal-submitter"
    assert state_client.headers[-1]["x-synarch-trace-id"] == payload["trace_id"]


def test_goal_submit_returns_bad_gateway_when_state_service_is_unavailable() -> None:
    app.dependency_overrides[get_state_client] = FailingStateClient

    try:
        response = TestClient(app).post(
            "/goals/submit",
            json={"goal": "Corriger un bug API", "priority": "high"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["detail"] == "State service unavailable"


def test_gateway_applies_project_split_through_state_service() -> None:
    state_client = FakeStateClient()
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/project-split-requests/project-split-large/apply",
            headers={"X-Synarch-Trace-Id": "trace_gateway_split_apply"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["request_id"] == "project-split-large"
    assert payload["split_request"]["status"] == "applied"
    assert payload["shard_projects"][0]["title"] == "Large project - planning"
    assert state_client.split_applications[0].request_id == "project-split-large"
    assert state_client.headers[-1]["x-synarch-actor-id"] == "gateway-project-split-applier"
    assert state_client.headers[-1]["x-synarch-trace-id"] == "trace_gateway_split_apply"


def test_tool_adapter_registry_exposes_executable_tools() -> None:
    assert gateway_main.registered_tool_names() == [
        "connector.job.create",
        "connector.job.list",
        "connector.job.stop",
        "event.emit",
        "web.fetch",
    ]
    assert gateway_main.tool_adapter_registry_errors() == []


def test_tool_registry_endpoint_returns_adapter_manifests() -> None:
    response = TestClient(app).get("/tools/registry")

    assert response.status_code == 200
    manifests = {
        manifest["tool_name"]: manifest for manifest in response.json()["tools"]
    }
    assert manifests["connector.job.create"]["required_arguments"] == [
        "kind",
        "purpose",
        "run_tool_name",
    ]
    assert manifests["connector.job.create"]["optional_arguments"] == [
        "id",
        "schedule",
        "webhook_path",
        "run_arguments",
        "run_reason",
        "metadata",
    ]
    assert manifests["connector.job.create"]["risk_level"] == "medium"
    assert manifests["connector.job.list"]["optional_arguments"] == [
        "project_id",
        "task_id",
        "kind",
        "status",
        "limit",
    ]
    assert manifests["connector.job.list"]["risk_level"] == "low"
    assert manifests["connector.job.stop"]["required_arguments"] == ["job_id", "reason"]
    assert manifests["connector.job.stop"]["risk_level"] == "medium"
    assert manifests["event.emit"]["required_arguments"] == ["type"]
    assert manifests["event.emit"]["credential_scopes"] == []
    assert manifests["event.emit"]["audit_required"] is True
    assert manifests["web.fetch"]["required_arguments"] == ["url"]
    assert manifests["web.fetch"]["optional_arguments"] == ["max_bytes"]
    assert manifests["web.fetch"]["risk_level"] == "medium"
    assert manifests["web.fetch"]["network_access"] is True


def test_tool_credential_status_endpoint_reports_missing_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        gateway_main.TOOL_ADAPTER_MANIFESTS,
        "web.fetch",
        gateway_main.ToolAdapterManifest(
            tool_name="web.fetch",
            adapter="web.fetch",
            required_arguments=("url",),
            credential_scopes=("browser:authenticated_fetch",),
            requires_credentials=True,
            network_access=True,
            risk_level="medium",
        ),
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web", "service-event-log"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.fetch"],
                    "service-event-log": ["event.emit"],
                },
                available_service_credential_scopes={
                    "connector-supplier-web": [],
                    "service-event-log": [],
                },
            )
        }
    )
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).get(
            "/tools/credential-status",
            params={"agent_id": "agent-ops-sourcing"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    statuses = {
        (status["service_id"], status["tool_name"]): status
        for status in response.json()["credential_statuses"]
    }
    assert statuses[("service-event-log", "event.emit")]["status"] == "not_required"
    assert statuses[("connector-supplier-web", "web.fetch")] == {
        "agent_id": "agent-ops-sourcing",
        "service_id": "connector-supplier-web",
        "tool_name": "web.fetch",
        "status": "missing_scopes",
        "required_scopes": ["browser:authenticated_fetch"],
        "available_scopes": [],
        "missing_scopes": ["browser:authenticated_fetch"],
    }


def test_tool_credential_status_endpoint_reports_ready_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        gateway_main.TOOL_ADAPTER_MANIFESTS,
        "web.fetch",
        gateway_main.ToolAdapterManifest(
            tool_name="web.fetch",
            adapter="web.fetch",
            required_arguments=("url",),
            credential_scopes=("browser:authenticated_fetch",),
            requires_credentials=True,
            network_access=True,
            risk_level="medium",
        ),
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.fetch"]
                },
                available_service_credential_scopes={
                    "connector-supplier-web": ["browser:authenticated_fetch"]
                },
            )
        }
    )
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).get(
            "/tools/credential-status",
            params={"agent_id": "agent-ops-sourcing"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["credential_statuses"][0]["status"] == "ready"
    assert response.json()["credential_statuses"][0]["missing_scopes"] == []


def test_service_health_check_filters_agent_services_and_records_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_client = FakeStateClient()
    state_client.services.extend(
        [
            ServiceDefinition(
                id="connector-supplier-web",
                name="Supplier Web",
                kind="tool_provider",
                base_url="https://supplier.example",
                health_endpoint="/healthz",
                capabilities=["web.fetch"],
                credential_scopes=["browser:authenticated_fetch"],
                allowed_divisions=["ops-sourcing"],
            ),
            ServiceDefinition(
                id="connector-hidden-dev",
                name="Hidden Dev",
                kind="tool_provider",
                base_url="https://dev.example",
                health_endpoint="/healthz",
                capabilities=["git.read"],
                allowed_divisions=["dev"],
            ),
        ]
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                available_services=["connector-supplier-web"],
            )
        }
    )
    called_urls: list[str] = []

    def fake_get(url: str, *, timeout: float) -> httpx.Response:
        called_urls.append(url)
        assert timeout == gateway_main.settings.service_health_timeout_seconds
        return httpx.Response(204)

    monkeypatch.setattr("synarch_gateway.main.httpx.get", fake_get)
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/services/health-checks",
            params={"agent_id": "agent-ops-sourcing"},
            headers={"X-Synarch-Trace-Id": "trace_service_health"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert called_urls == ["https://supplier.example/healthz"]
    assert payload["agent_id"] == "agent-ops-sourcing"
    assert [check["service_id"] for check in payload["checks"]] == [
        "connector-supplier-web"
    ]
    assert payload["checks"][0]["status"] == "healthy"
    assert payload["event"]["type"] == "service_health.checked"
    assert payload["event"]["trace_id"] == "trace_service_health"
    assert payload["event"]["payload"]["status_counts"]["healthy"] == 1
    assert payload["audit_log"]["action"] == "services.health_checked"
    assert payload["audit_log"]["trace_id"] == "trace_service_health"
    assert state_client.events[0].type == EventType.service_health_checked
    assert state_client.audit_logs[0].actor_id == "gateway-service-health"
    assert state_client.headers[-1]["x-synarch-trace-id"] == "trace_service_health"


def test_tool_gate_authorizes_allowed_tool_and_records_logs() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-dev": LocalWorldView(
                agent_id="agent-dev",
                role="Code and infra",
                division="dev",
                permissions=PermissionBundle(
                    allowed_tools=["git.read", "event.emit"],
                    denied_tools=["payment.execute"],
                ),
                available_services=["connector-github", "service-event-log"],
                available_service_capabilities={
                    "connector-github": ["git.read", "git.write"],
                    "service-event-log": ["event.emit"],
                },
                available_connector_ids=["connector-github"],
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_tool_allowed"},
            json={
                "agent_id": "agent-dev",
                "tool_name": "git.read",
                "service_id": "connector-github",
                "project_id": "project_demo",
                "task_id": "task_demo",
                "reason": "Read code before editing.",
                "arguments": {"path": "README.md"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_name"] == "git.read"
    assert payload["output"]["authorized"] is True
    assert payload["output"]["executed"] is False
    assert payload["output"]["trace_id"] == "trace_tool_allowed"
    assert state_client.events[0].type == EventType.tool_called
    assert state_client.events[0].target == "task_demo"
    assert state_client.events[0].payload["argument_keys"] == ["path"]
    assert state_client.audit_logs[0].action == "tool.allowed"
    assert state_client.audit_logs[0].actor_id == "agent-dev"
    assert state_client.headers[-1]["x-synarch-actor-id"] == "gateway-tool-gate"


def test_tool_gate_denies_tool_not_exposed_by_selected_service() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["service-event-log"],
                available_service_capabilities={"service-event-log": ["event.emit"]},
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_tool_service_capability_denied"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "web.fetch",
                "service_id": "service-event-log",
                "project_id": "project_sourcing",
                "task_id": "task_sourcing",
                "reason": "Try to fetch via the event log service.",
                "arguments": {"url": "https://example.com"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Tool not exposed by service: web.fetch via service-event-log"
    )
    assert state_client.events[0].type == EventType.tool_failed
    assert state_client.events[0].payload["service_id"] == "service-event-log"
    assert state_client.audit_logs[0].action == "tool.denied"


def test_tool_gate_denies_missing_required_credential_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        gateway_main.TOOL_ADAPTER_MANIFESTS,
        "web.fetch",
        gateway_main.ToolAdapterManifest(
            tool_name="web.fetch",
            adapter="web.fetch",
            required_arguments=("url",),
            credential_scopes=("browser:authenticated_fetch",),
            requires_credentials=True,
            network_access=True,
            risk_level="medium",
        ),
    )
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.fetch"]
                },
                available_service_credential_scopes={"connector-supplier-web": []},
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_tool_missing_credential_scope"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "web.fetch",
                "service_id": "connector-supplier-web",
                "project_id": "project_sourcing",
                "task_id": "task_sourcing",
                "reason": "Try to fetch through a connector without required credentials.",
                "arguments": {"url": "https://example.com"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Missing credential scopes for service connector-supplier-web: "
        "browser:authenticated_fetch"
    )
    assert state_client.events[0].type == EventType.tool_failed
    assert state_client.audit_logs[0].action == "tool.denied"


def test_tool_gate_denies_missing_task_credential_scope() -> None:
    state_client = FakeStateClient()
    state_client.tasks.append(
        TaskRecord(
            id="task_task_scoped_credentials",
            project_id="project_sourcing",
            title="Fetch authenticated supplier page",
            assigned_agent_id="agent-ops-sourcing",
            required_tools=["web.fetch"],
            required_tool_scopes={"web.fetch": ["browser:authenticated_fetch"]},
            acceptance_criteria=["Authenticated fetch has evidence."],
        )
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.fetch"]
                },
                available_service_credential_scopes={"connector-supplier-web": []},
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_tool_missing_task_credential_scope"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "web.fetch",
                "service_id": "connector-supplier-web",
                "project_id": "project_sourcing",
                "task_id": "task_task_scoped_credentials",
                "reason": "Try to fetch through a connector without task credentials.",
                "arguments": {"url": "https://example.com"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Missing task credential scopes for service connector-supplier-web: "
        "browser:authenticated_fetch"
    )
    assert state_client.events[0].type == EventType.tool_failed
    assert state_client.audit_logs[0].action == "tool.denied"


def test_tool_gate_denies_forbidden_tool_and_records_logs() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-finance": LocalWorldView(
                agent_id="agent-finance",
                role="Finance",
                division="finance",
                permissions=PermissionBundle(
                    allowed_tools=["document.read", "ledger.write", "event.emit"],
                    denied_tools=["payment.execute"],
                ),
                available_services=["service-ledger"],
                available_service_capabilities={"service-ledger": ["ledger.write"]},
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_tool_denied"},
            json={
                "agent_id": "agent-finance",
                "tool_name": "payment.execute",
                "service_id": "service-ledger",
                "reason": "Try to pay an invoice.",
                "arguments": {"invoice_id": "invoice_demo"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "Tool denied for agent: payment.execute"
    assert state_client.events[0].type == EventType.tool_failed
    assert state_client.events[0].payload["error"] == "Tool denied for agent: payment.execute"
    assert state_client.audit_logs[0].action == "tool.denied"
    assert state_client.audit_logs[0].target_id == "payment.execute"


def test_tool_gate_executes_event_emit_adapter() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-direction": LocalWorldView(
                agent_id="agent-direction",
                role="Direction",
                division="direction",
                permissions=PermissionBundle(
                    allowed_tools=["event.emit"],
                    denied_tools=[],
                ),
                available_services=["service-event-log"],
                available_service_capabilities={"service-event-log": ["event.emit"]},
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_event_emit_adapter"},
            json={
                "agent_id": "agent-direction",
                "tool_name": "event.emit",
                "service_id": "service-event-log",
                "project_id": "project_demo",
                "reason": "Report a project blocker.",
                "arguments": {
                    "type": "agent.reported",
                    "target": "project_demo",
                    "payload": {"summary": "Supplier response is blocked."},
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["output"]["executed"] is True
    assert payload["output"]["adapter"] == "event.emit"
    assert payload["output"]["emitted_event_type"] == "agent.reported"
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.agent_reported,
    ]
    assert state_client.events[1].source_agent_id == "agent-direction"
    assert state_client.events[1].target == "project_demo"
    assert state_client.events[1].payload == {"summary": "Supplier response is blocked."}


def test_tool_gate_executes_web_fetch_adapter() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web", "service-event-log"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.search", "web.fetch"],
                    "service-event-log": ["event.emit"],
                },
                available_connector_ids=["connector-supplier-web"],
            )
        }
    )

    def fake_fetch_http_url(url: str, *, max_bytes: int) -> dict[str, object]:
        assert url == "https://example.com"
        assert max_bytes == 2048
        return {
            "url": url,
            "final_url": url,
            "status_code": 200,
            "content_type": "text/html",
            "bytes_read": 512,
            "truncated": False,
            "title": "Example Domain",
            "text_excerpt": "Example Domain This domain is for use in illustrative examples.",
        }

    original_fetch_http_url = gateway_main.fetch_http_url
    gateway_main.fetch_http_url = fake_fetch_http_url
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_web_fetch_adapter"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "web.fetch",
                "service_id": "connector-supplier-web",
                "project_id": "project_sourcing",
                "reason": "Fetch supplier evidence before outreach.",
                "arguments": {
                    "url": "https://example.com",
                    "max_bytes": 2048,
                },
            },
        )
    finally:
        gateway_main.fetch_http_url = original_fetch_http_url
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["output"]["executed"] is True
    assert payload["output"]["adapter"] == "web.fetch"
    assert payload["output"]["status_code"] == 200
    assert payload["output"]["title"] == "Example Domain"
    assert payload["output"]["truncated"] is False
    assert [event.type for event in state_client.events] == [EventType.tool_called]
    assert state_client.events[0].payload["argument_keys"] == ["max_bytes", "url"]
    assert state_client.audit_logs[0].action == "tool.allowed"


def test_tool_gate_creates_connector_job_after_permission_check() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["connector.job.create", "web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": [
                        "connector.job.create",
                        "web.fetch",
                    ]
                },
                available_connector_ids=["connector-supplier-web"],
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_create_tool"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "connector.job.create",
                "service_id": "connector-supplier-web",
                "project_id": "project_sourcing",
                "task_id": "task_supplier_followup",
                "reason": "Schedule one bounded supplier follow-up check.",
                "arguments": {
                    "id": "connector-job-supplier-followup-tool",
                    "kind": "cron",
                    "schedule": "*/30 * * * *",
                    "purpose": "Fetch supplier evidence before the next follow-up.",
                    "run_tool_name": "web.fetch",
                    "run_arguments": {
                        "url": "https://example.com",
                        "max_bytes": 1024,
                    },
                    "metadata": {"max_runs": 3},
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["output"]["adapter"] == "connector.job.create"
    assert payload["output"]["connector_job_id"] == "connector-job-supplier-followup-tool"
    assert payload["output"]["event_id"] == state_client.events[0].id
    assert payload["output"]["audit_id"] == state_client.audit_logs[0].id
    assert payload["output"]["connector_job_event_id"] == state_client.events[1].id
    assert payload["output"]["connector_job_audit_id"] == state_client.audit_logs[1].id
    assert payload["output"]["run_tool_name"] == "web.fetch"
    assert len(state_client.connector_jobs) == 1
    job = state_client.connector_jobs[0]
    assert job.service_id == "connector-supplier-web"
    assert job.owner_agent_id == "agent-ops-sourcing"
    assert job.project_id == "project_sourcing"
    assert job.task_id == "task_supplier_followup"
    assert job.schedule == "*/30 * * * *"
    assert job.metadata["tool_name"] == "web.fetch"
    assert job.metadata["arguments"] == {
        "url": "https://example.com",
        "max_bytes": 1024,
    }
    assert job.metadata["max_runs"] == 3
    assert job.metadata["source_trace_id"] == "trace_connector_job_create_tool"
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.connector_job_created,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "connector_job.created",
    ]
    assert state_client.audit_logs[1].actor_id == "agent-ops-sourcing"


def test_tool_gate_denies_connector_job_for_unavailable_run_tool() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["connector.job.create", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["connector.job.create"]
                },
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_denied_run_tool"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "connector.job.create",
                "service_id": "connector-supplier-web",
                "project_id": "project_sourcing",
                "reason": "Try to schedule a job for a tool this agent cannot use.",
                "arguments": {
                    "kind": "cron",
                    "schedule": "*/30 * * * *",
                    "purpose": "Fetch supplier evidence later.",
                    "run_tool_name": "web.fetch",
                    "run_arguments": {"url": "https://example.com"},
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "Connector job run tool not allowed for agent: web.fetch"
    assert state_client.connector_jobs == []
    assert state_client.events[0].type == EventType.tool_failed
    assert state_client.audit_logs[0].action == "tool.denied"


def test_tool_gate_lists_only_owned_connector_jobs() -> None:
    state_client = FakeStateClient()
    state_client.connector_jobs.extend(
        [
            ConnectorJobRecord(
                id="connector-job-owned-active",
                service_id="connector-supplier-web",
                project_id="project_sourcing",
                task_id="task_supplier_followup",
                owner_agent_id="agent-ops-sourcing",
                kind="cron",
                schedule="*/30 * * * *",
                purpose="Owned active follow-up job.",
                created_by_type="agent",
                created_by_id="agent-ops-sourcing",
                metadata={"tool_name": "web.fetch"},
            ),
            ConnectorJobRecord(
                id="connector-job-other-owner",
                service_id="connector-supplier-web",
                project_id="project_sourcing",
                task_id="task_supplier_followup",
                owner_agent_id="agent-other",
                kind="cron",
                schedule="*/30 * * * *",
                purpose="Other owner follow-up job.",
                created_by_type="agent",
                created_by_id="agent-other",
                metadata={"tool_name": "web.fetch"},
            ),
            ConnectorJobRecord(
                id="connector-job-owned-stopped",
                service_id="connector-supplier-web",
                project_id="project_sourcing",
                task_id="task_supplier_followup",
                owner_agent_id="agent-ops-sourcing",
                kind="cron",
                status=ConnectorJobStatus.stopped,
                schedule="*/30 * * * *",
                purpose="Owned stopped follow-up job.",
                created_by_type="agent",
                created_by_id="agent-ops-sourcing",
                metadata={"tool_name": "web.fetch"},
            ),
        ]
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["connector.job.list"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["connector.job.list"]
                },
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_list_tool"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "connector.job.list",
                "service_id": "connector-supplier-web",
                "project_id": "project_sourcing",
                "task_id": "task_supplier_followup",
                "reason": "Inspect my active follow-up jobs.",
                "arguments": {"status": "active"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["output"]["adapter"] == "connector.job.list"
    assert payload["output"]["count"] == 1
    assert payload["output"]["total_count"] == 1
    assert payload["output"]["connector_jobs"][0]["id"] == "connector-job-owned-active"
    assert [event.type for event in state_client.events] == [EventType.tool_called]
    assert [audit.action for audit in state_client.audit_logs] == ["tool.allowed"]


def test_tool_gate_denies_connector_job_list_without_service() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["connector.job.list"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["connector.job.list"]
                },
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_list_no_service"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "connector.job.list",
                "project_id": "project_sourcing",
                "reason": "Inspect connector jobs without selecting a service.",
                "arguments": {"status": "active"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "connector.job.list requires selected service_id"
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.tool_failed,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "tool.failed",
    ]


def test_tool_gate_stops_owned_connector_job() -> None:
    state_client = FakeStateClient()
    state_client.connector_jobs.append(
        ConnectorJobRecord(
            id="connector-job-owned-stop",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id="task_supplier_followup",
            owner_agent_id="agent-ops-sourcing",
            kind="cron",
            schedule="*/30 * * * *",
            purpose="Stop once supplier replied.",
            created_by_type="agent",
            created_by_id="agent-ops-sourcing",
            metadata={"tool_name": "web.fetch"},
        )
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["connector.job.stop"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["connector.job.stop"]
                },
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_stop_tool"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "connector.job.stop",
                "service_id": "connector-supplier-web",
                "project_id": "project_sourcing",
                "task_id": "task_supplier_followup",
                "reason": "Supplier replied; stop the follow-up loop.",
                "arguments": {
                    "job_id": "connector-job-owned-stop",
                    "reason": "Supplier replied; follow-up loop complete.",
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["output"]["adapter"] == "connector.job.stop"
    assert payload["output"]["connector_job_id"] == "connector-job-owned-stop"
    assert payload["output"]["status"] == "stopped"
    assert state_client.connector_jobs[0].status == ConnectorJobStatus.stopped
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.connector_job_stopped,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "connector_job.stopped",
    ]
    assert state_client.audit_logs[1].actor_id == "agent-ops-sourcing"


def test_tool_gate_denies_stopping_connector_job_owned_by_another_agent() -> None:
    state_client = FakeStateClient()
    state_client.connector_jobs.append(
        ConnectorJobRecord(
            id="connector-job-other-owner",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id="task_supplier_followup",
            owner_agent_id="agent-other",
            kind="cron",
            schedule="*/30 * * * *",
            purpose="Another agent owns this job.",
            created_by_type="agent",
            created_by_id="agent-other",
            metadata={"tool_name": "web.fetch"},
        )
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["connector.job.stop"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["connector.job.stop"]
                },
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_stop_denied"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "connector.job.stop",
                "service_id": "connector-supplier-web",
                "project_id": "project_sourcing",
                "reason": "Try to stop another agent job.",
                "arguments": {
                    "job_id": "connector-job-other-owner",
                    "reason": "Not mine.",
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["detail"] == "Connector job is not owned by requesting agent"
    assert state_client.connector_jobs[0].status == ConnectorJobStatus.active
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.tool_failed,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "tool.failed",
    ]


def test_gateway_tool_runner_returns_failed_result_for_missing_connector_job() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["connector.job.stop"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["connector.job.stop"]
                },
            )
        }
    )

    result = gateway_main.GatewayToolRunner().call_tool(
        ToolCallRequest(
            agent_id="agent-ops-sourcing",
            tool_name="connector.job.stop",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id="task_supplier_followup",
            reason="Stop a connector job that does not exist.",
            arguments={
                "job_id": "connector-job-missing",
                "reason": "Supplier replied.",
            },
        ),
        state_client=state_client,
        control_plane=control_plane,
        headers=gateway_main.service_headers("trace_missing_connector_job_tool_result"),
        trace_id="trace_missing_connector_job_tool_result",
    )

    assert result.status == TaskStatus.failed
    assert result.error == "Unknown connector job: connector-job-missing"
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.tool_failed,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "tool.failed",
    ]


def test_connector_job_execute_runs_tool_gate_and_records_completed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_client = FakeStateClient()
    state_client.connector_jobs.append(
        ConnectorJobRecord(
            id="connector-job-gateway-exec",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id="task_supplier_followup",
            owner_agent_id="agent-ops-sourcing",
            kind="cron",
            schedule="*/15 * * * *",
            purpose="Fetch supplier evidence before follow-up.",
            created_by_type="agent",
            created_by_id="agent-ops-sourcing",
            metadata={
                "tool_name": "web.fetch",
                "arguments": {"url": "https://example.com", "max_bytes": 1024},
            },
        )
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.fetch"]
                },
            )
        }
    )

    def fake_fetch_http_url(url: str, *, max_bytes: int) -> dict[str, object]:
        assert url == "https://example.com"
        assert max_bytes == 1024
        return {
            "url": url,
            "final_url": url,
            "status_code": 200,
            "content_type": "text/html",
            "bytes_read": 256,
            "truncated": False,
            "title": "Example Domain",
            "text_excerpt": "Example Domain supplier source.",
        }

    monkeypatch.setattr(gateway_main, "fetch_http_url", fake_fetch_http_url)
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/connector-jobs/connector-job-gateway-exec/execute",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_gateway_exec"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["status"] == "completed"
    assert payload["run"]["triggered_by_id"] == "gateway-connector-job-executor"
    assert payload["run"]["output"]["execution_mode"] == "tool_gate"
    assert payload["run"]["output"]["tool_result"]["status"] == "completed"
    assert payload["run"]["output"]["tool_result"]["output"]["adapter"] == "web.fetch"
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.connector_job_run_recorded,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "connector_job.run_recorded",
    ]
    assert state_client.headers[-1]["x-synarch-actor-id"] == (
        "gateway-connector-job-executor"
    )


def test_connector_job_execute_records_failed_run_when_tool_gate_denies() -> None:
    state_client = FakeStateClient()
    state_client.connector_jobs.append(
        ConnectorJobRecord(
            id="connector-job-denied",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id="task_supplier_followup",
            owner_agent_id="agent-ops-sourcing",
            kind="cron",
            schedule="*/15 * * * *",
            purpose="Fetch supplier evidence before follow-up.",
            created_by_type="agent",
            created_by_id="agent-ops-sourcing",
            metadata={
                "tool_name": "web.fetch",
                "arguments": {"url": "https://example.com"},
            },
        )
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(allowed_tools=[], denied_tools=[]),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.fetch"]
                },
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/connector-jobs/connector-job-denied/execute",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_denied"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["status"] == "failed"
    assert payload["run"]["error"] == "Tool not allowed for agent: web.fetch"
    assert payload["run"]["output"]["tool_result"]["status"] == "failed"
    assert payload["run"]["output"]["tool_result"]["output"]["authorized"] is False
    assert [event.type for event in state_client.events] == [
        EventType.tool_failed,
        EventType.connector_job_run_recorded,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.denied",
        "connector_job.run_recorded",
    ]


def test_connector_job_execute_records_skipped_run_without_tool_mapping() -> None:
    state_client = FakeStateClient()
    state_client.connector_jobs.append(
        ConnectorJobRecord(
            id="connector-job-unmapped",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            owner_agent_id="agent-ops-sourcing",
            kind="cron",
            schedule="*/15 * * * *",
            purpose="No executable adapter has been selected yet.",
            created_by_type="agent",
            created_by_id="agent-ops-sourcing",
            metadata={"stop_condition": "supplier replied"},
        )
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/connector-jobs/connector-job-unmapped/execute",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_skipped"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["status"] == "skipped"
    assert payload["run"]["output"] == {
        "executed": False,
        "reason": "connector job metadata missing tool_name",
        "metadata_keys": ["stop_condition"],
    }
    assert [event.type for event in state_client.events] == [
        EventType.connector_job_run_recorded
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "connector_job.run_recorded"
    ]


def test_connector_job_stop_and_resume_proxy_state_with_user_headers() -> None:
    state_client = FakeStateClient()
    state_client.connector_jobs.append(
        ConnectorJobRecord(
            id="connector-job-control",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id="task_supplier_followup",
            owner_agent_id="agent-ops-sourcing",
            kind="cron",
            schedule="*/15 * * * *",
            purpose="Controlled connector job action smoke.",
            created_by_type="agent",
            created_by_id="agent-ops-sourcing",
            metadata={"tool_name": "web.fetch"},
        )
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        stop_response = TestClient(app).post(
            "/connector-jobs/connector-job-control/stop",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_control"},
            json={
                "stopped_by_type": "user",
                "stopped_by_id": "local-user",
                "reason": "Pause from dashboard.",
            },
        )
        resume_response = TestClient(app).post(
            "/connector-jobs/connector-job-control/resume",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_control"},
            json={
                "resumed_by_type": "user",
                "resumed_by_id": "local-user",
                "reason": "Resume from dashboard.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert stop_response.status_code == 200
    assert stop_response.json()["job"]["status"] == "stopped"
    assert resume_response.status_code == 200
    assert resume_response.json()["job"]["status"] == "active"
    assert resume_response.json()["job"]["next_run_at"] is not None
    assert [event.type for event in state_client.events] == [
        EventType.connector_job_stopped,
        EventType.connector_job_resumed,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "connector_job.stopped",
        "connector_job.resumed",
    ]
    assert state_client.headers[0]["x-synarch-actor-id"] == "local-user"
    assert state_client.headers[1]["x-synarch-actor-id"] == "local-user"


def test_connector_job_run_ready_executes_bounded_jobs_and_records_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_client = FakeStateClient()
    for job in [
        ConnectorJobRecord(
            id="connector-job-batch-cron-a",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id="task_supplier_followup_a",
            owner_agent_id="agent-ops-sourcing",
            kind="cron",
            schedule="*/15 * * * *",
            purpose="Fetch supplier A evidence.",
            created_by_type="agent",
            created_by_id="agent-ops-sourcing",
            metadata={
                "tool_name": "web.fetch",
                "arguments": {"url": "https://example.com/a", "max_bytes": 512},
            },
        ),
        ConnectorJobRecord(
            id="connector-job-batch-cron-b",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id="task_supplier_followup_b",
            owner_agent_id="agent-ops-sourcing",
            kind="cron",
            schedule="*/30 * * * *",
            purpose="Fetch supplier B evidence.",
            created_by_type="agent",
            created_by_id="agent-ops-sourcing",
            metadata={
                "tool_name": "web.fetch",
                "arguments": {"url": "https://example.com/b", "max_bytes": 512},
            },
        ),
        ConnectorJobRecord(
            id="connector-job-batch-webhook",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id="task_supplier_webhook",
            owner_agent_id="agent-ops-sourcing",
            kind="webhook",
            webhook_path="/webhooks/supplier",
            purpose="Receive supplier replies.",
            created_by_type="agent",
            created_by_id="agent-ops-sourcing",
            metadata={
                "tool_name": "event.emit",
                "arguments": {"type": "agent.reported"},
            },
        ),
    ]:
        state_client.connector_jobs.append(job)

    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.fetch", "event.emit"]
                },
            )
        }
    )

    def fake_fetch_http_url(url: str, *, max_bytes: int) -> dict[str, object]:
        assert url == "https://example.com/a"
        assert max_bytes == 512
        return {
            "url": url,
            "final_url": url,
            "status_code": 200,
            "content_type": "text/html",
            "bytes_read": 128,
            "truncated": False,
            "title": "Supplier A",
            "text_excerpt": "Supplier A evidence.",
        }

    monkeypatch.setattr(gateway_main, "fetch_http_url", fake_fetch_http_url)
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/connector-jobs/run-ready",
            params={"max_jobs": 1, "kind": "cron"},
            headers={"X-Synarch-Trace-Id": "trace_connector_job_batch"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_id"] == "trace_connector_job_batch"
    assert payload["stop_reason"] == "max_jobs_reached"
    assert len(payload["runs"]) == 1
    run = payload["runs"][0]["run"]
    assert run["job_id"] == "connector-job-batch-cron-a"
    assert run["status"] == "completed"
    assert run["output"]["tool_result"]["output"]["adapter"] == "web.fetch"
    assert payload["tick_event"]["type"] == "connector_job.tick"
    assert payload["tick_event"]["payload"]["connector_job_ids"] == [
        "connector-job-batch-cron-a"
    ]
    assert payload["tick_event"]["payload"]["run_statuses"] == ["completed"]
    assert payload["tick_audit_log"]["action"] == "connector_job.tick"
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.connector_job_run_recorded,
        EventType.connector_job_tick,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "connector_job.run_recorded",
        "connector_job.tick",
    ]


def test_connector_job_run_ready_records_empty_tick() -> None:
    state_client = FakeStateClient()
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/connector-jobs/run-ready",
            params={"project_id": "project_empty", "max_jobs": 3},
            headers={"X-Synarch-Trace-Id": "trace_connector_job_empty_batch"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "project_empty"
    assert payload["stop_reason"] == "no_ready_connector_job"
    assert payload["runs"] == []
    assert payload["tick_event"]["payload"] == {
        "max_jobs": 3,
        "kind": "cron",
        "service_id": None,
        "project_id": "project_empty",
        "owner_agent_id": None,
        "stop_reason": "no_ready_connector_job",
        "run_count": 0,
        "connector_job_ids": [],
        "connector_job_run_ids": [],
        "run_statuses": [],
        "executor": "gateway-connector-job-executor",
    }
    assert payload["tick_audit_log"]["target_id"] == "project_empty"
    assert [event.type for event in state_client.events] == [EventType.connector_job_tick]
    assert [audit.action for audit in state_client.audit_logs] == ["connector_job.tick"]


def test_webhook_triggers_matching_connector_job_through_tool_gate() -> None:
    state_client = FakeStateClient()
    state_client.connector_jobs.append(
        ConnectorJobRecord(
            id="connector-job-supplier-webhook",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id="task_supplier_webhook",
            owner_agent_id="agent-ops-sourcing",
            kind="webhook",
            webhook_path="/webhooks/supplier",
            purpose="Record supplier webhook replies.",
            created_by_type="agent",
            created_by_id="agent-ops-sourcing",
            metadata={
                "tool_name": "event.emit",
                "arguments": {
                    "type": "agent.reported",
                    "target": "project_sourcing",
                    "payload": {"source": "supplier-webhook"},
                },
            },
        )
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["event.emit"]
                },
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/webhooks/supplier",
            headers={"X-Synarch-Trace-Id": "trace_supplier_webhook"},
            json={"supplier_id": "factory-a", "message": "ready to quote"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "webhook"
    assert payload["stop_reason"] == "all_matching_webhook_jobs_ran"
    assert len(payload["runs"]) == 1
    run = payload["runs"][0]["run"]
    assert run["job_id"] == "connector-job-supplier-webhook"
    assert run["status"] == "completed"
    tool_result = run["output"]["tool_result"]
    assert tool_result["tool_name"] == "event.emit"
    assert tool_result["output"]["adapter"] == "event.emit"
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.agent_reported,
        EventType.connector_job_run_recorded,
        EventType.connector_job_tick,
    ]
    emitted_payload = state_client.events[1].payload
    assert emitted_payload["source"] == "supplier-webhook"
    assert emitted_payload["webhook"] == {
        "webhook_path": "/webhooks/supplier",
        "body": {"supplier_id": "factory-a", "message": "ready to quote"},
        "content_type": "application/json",
    }
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "connector_job.run_recorded",
        "connector_job.tick",
    ]
    assert payload["tick_event"]["payload"]["connector_job_ids"] == [
        "connector-job-supplier-webhook"
    ]


def test_connector_job_run_ready_ignores_jobs_in_cooldown() -> None:
    state_client = FakeStateClient()
    now = datetime.now(UTC)
    state_client.connector_jobs.extend(
        [
            ConnectorJobRecord(
                id="connector-job-future",
                service_id="connector-supplier-web",
                project_id="project_sourcing",
                task_id="task_supplier_future",
                owner_agent_id="agent-ops-sourcing",
                kind="cron",
                schedule="*/5 * * * *",
                purpose="Do not run while cooldown is active.",
                created_by_type="agent",
                created_by_id="agent-ops-sourcing",
                created_at=now - timedelta(minutes=10),
                next_run_at=now + timedelta(minutes=10),
            ),
            ConnectorJobRecord(
                id="connector-job-due",
                service_id="connector-supplier-web",
                project_id="project_sourcing",
                task_id="task_supplier_due",
                owner_agent_id="agent-ops-sourcing",
                kind="cron",
                schedule="*/5 * * * *",
                purpose="Run once the cooldown has elapsed.",
                created_by_type="agent",
                created_by_id="agent-ops-sourcing",
                created_at=now - timedelta(minutes=5),
                next_run_at=now - timedelta(minutes=1),
            ),
        ]
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/connector-jobs/run-ready",
            params={"project_id": "project_sourcing", "max_jobs": 3},
            headers={"X-Synarch-Trace-Id": "trace_connector_job_cooldown"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["stop_reason"] == "no_ready_connector_job"
    assert [run["run"]["job_id"] for run in payload["runs"]] == ["connector-job-due"]
    assert payload["tick_event"]["payload"]["connector_job_ids"] == ["connector-job-due"]
    assert [run.job_id for run in state_client.connector_job_runs] == ["connector-job-due"]


def test_tool_gate_rejects_private_web_fetch_url() -> None:
    state_client = FakeStateClient()
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.search", "web.fetch"]
                },
                available_connector_ids=["connector-supplier-web"],
            )
        }
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_control_plane_client] = lambda: control_plane

    try:
        response = TestClient(app).post(
            "/tools/call",
            headers={"X-Synarch-Trace-Id": "trace_private_web_fetch"},
            json={
                "agent_id": "agent-ops-sourcing",
                "tool_name": "web.fetch",
                "service_id": "connector-supplier-web",
                "reason": "Try to fetch a local URL.",
                "arguments": {"url": "http://127.0.0.1:8020/healthz"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "web.fetch cannot target private hosts"
    assert [event.type for event in state_client.events] == [
        EventType.tool_called,
        EventType.tool_failed,
    ]
    assert state_client.audit_logs[0].action == "tool.allowed"
    assert state_client.audit_logs[1].action == "tool.failed"


def test_run_next_task_executes_first_ready_task() -> None:
    state_client = FakeStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_demo",
            title="Demo project",
            goal="Deliver a verified backend slice.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(
        TaskRecord(
            project_id="project_demo",
            title="Ready task",
            assigned_agent_id="agent-dev",
            acceptance_criteria=["Ready task can produce a recorded result."],
        )
    )
    approved_memory = MemoryItem(
        id="memory-approved",
        scope="project:project_demo",
        content="Use the approved deployment checklist before marking backend slices done.",
        status=MemoryStatus.approved,
        agent_id="agent-dev",
        project_id="project_demo",
    )
    memory_client = FakeMemoryClient(context_items=[approved_memory])
    runtime_client = FakeAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=memory_client,
        runtime=runtime_client,
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_gateway_runner_test"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_id"] == "trace_gateway_runner_test"
    assert payload["project"]["goal"] == "Deliver a verified backend slice."
    assert runtime_client.requests[0].project is not None
    assert runtime_client.requests[0].project.goal == "Deliver a verified backend slice."
    assert payload["task"]["status"] == "needs_review"
    assert payload["task"]["result"]["summary"] == "Runtime stub prepared the task for review."
    assert payload["world_view"]["agent_id"] == "agent-dev"
    assert payload["memory_context"]["summary"] == "Fake context assembled."
    assert payload["memory_context"]["items"][0]["id"] == "memory-approved"
    assert memory_client.contexts[0].allowed_scopes == [
        "global",
        "division:dev",
        "agent:agent-dev",
        "project:project_demo",
    ]
    assert memory_client.items[0].scope == "project:project_demo"
    assert memory_client.items[0].agent_id == "agent-dev"
    assert memory_client.items[0].project_id == "project_demo"
    assert memory_client.items[0].status == "proposed"
    assert payload["agent_result"]["memory_candidates"][0]["status"] == "proposed"
    assert payload["cost_records"][0]["provider_id"] == "provider-local-runtime-stub"
    assert payload["cost_records"][0]["task_id"] == payload["task"]["id"]
    assert payload["cost_records"][0]["input_tokens"] == 123
    assert payload["cost_records"][0]["output_tokens"] == 45
    assert payload["cost_records"][0]["total_cost"] == 0.000021
    assert [event.type for event in state_client.events] == [
        "model_call.started",
        "model_call.completed",
        "memory.candidate_created",
    ]
    assert [event["type"] for event in payload["model_call_events"]] == [
        "model_call.started",
        "model_call.completed",
    ]
    started_payload = payload["model_call_events"][0]["payload"]
    assert started_payload["memory_item_count"] == 1
    assert started_payload["memory_item_ids"] == ["memory-approved"]
    assert started_payload["memory_tokens_used"] == payload["memory_context"]["tokens_used"]
    assert started_payload["memory_token_budget"] == 1200
    assert started_payload["memory_allowed_scopes"] == [
        "global",
        "division:dev",
        "agent:agent-dev",
        "project:project_demo",
    ]
    assert [event["type"] for event in payload["memory_events"]] == [
        "memory.candidate_created",
    ]
    assert payload["memory_events"][0]["payload"]["status"] == "proposed"
    assert state_client.headers[-1]["x-synarch-actor-id"] == "gateway-task-runner"


def test_task_runner_resolves_model_route_from_world_view_policy() -> None:
    state_client = FakeStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_model_policy",
            title="Model policy project",
            goal="Route model calls through the employee model policy.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(
        TaskRecord(
            id="task_model_policy",
            project_id="project_model_policy",
            title="Run with the policy model",
            assigned_agent_id="agent-dev",
            acceptance_criteria=["Runtime uses the policy-selected provider and model."],
        )
    )
    state_client.model_providers.append(
        ModelProviderConfig(
            id="provider-openrouter",
            name="OpenRouter",
            provider_type=AiProviderType.openrouter,
            default_model_id="deepseek/deepseek-v4-flash",
        )
    )
    state_client.model_definitions.append(
        ModelDefinition(
            id="deepseek/deepseek-v4-flash",
            provider_id="provider-openrouter",
            display_name="DeepSeek V4 Flash",
            input_cost_per_million_tokens=0.0,
            output_cost_per_million_tokens=0.0,
        )
    )
    state_client.model_policies.append(
        ModelPolicy(
            id="policy-openrouter-test",
            name="OpenRouter test policy",
            default_model_id="deepseek/deepseek-v4-flash",
            allowed_model_ids=["deepseek/deepseek-v4-flash"],
        )
    )
    runtime_client = FakeAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(
            {
                "agent-dev": LocalWorldView(
                    agent_id="agent-dev",
                    role="Code and infra",
                    division="dev",
                    policies=["model_policy:policy-openrouter-test"],
                )
            }
        ),
        memory=FakeMemoryClient(),
        runtime=runtime_client,
    )

    result = runner.run_task(
        "task_model_policy",
        trace_id="trace_model_policy_route",
        headers={"x-synarch-trace-id": "trace_model_policy_route"},
    )

    assert runtime_client.requests[0].provider_id == "provider-openrouter"
    assert runtime_client.requests[0].model_id == "deepseek/deepseek-v4-flash"
    assert result.model_call_events[0].payload["provider_id"] == "provider-openrouter"
    assert result.model_call_events[0].payload["model_id"] == "deepseek/deepseek-v4-flash"
    assert (
        result.model_call_events[0].payload["model_policy_id"]
        == "policy-openrouter-test"
    )
    assert (
        result.model_call_events[1].payload["model_policy_id"]
        == "policy-openrouter-test"
    )
    assert result.cost_records[0].provider_id == "provider-openrouter"
    assert result.cost_records[0].model_id == "deepseek/deepseek-v4-flash"


def test_run_next_task_includes_workspace_bridge_memory_scope() -> None:
    state_client = FakeStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_target",
            title="Target project",
            goal="Use explicitly bridged memory only.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.workspaces.append(
        ProjectWorkspace(
            id="workspace-target",
            project_id="project_target",
            name="Target workspace",
            memory_scope="project:project_target",
            bridge_project_ids=["project_source"],
            active=True,
        )
    )
    state_client.workspaces.append(
        ProjectWorkspace(
            id="workspace-inactive",
            project_id="project_target",
            name="Inactive target workspace",
            memory_scope="project:project_target_old",
            bridge_project_ids=["project_archived"],
            active=False,
        )
    )
    state_client.tasks.append(
        TaskRecord(
            project_id="project_target",
            title="Ready task",
            assigned_agent_id="agent-dev",
            acceptance_criteria=["Bridge scope is explicit."],
        )
    )
    memory_client = FakeMemoryClient(
        context_items=[
            MemoryItem(
                id="memory-bridged",
                scope="project:project_source",
                content="Source project context.",
                status=MemoryStatus.approved,
                project_id="project_source",
            )
        ]
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=memory_client,
        runtime=FakeAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_bridge_memory_test"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert memory_client.contexts[0].allowed_scopes == [
        "global",
        "division:dev",
        "agent:agent-dev",
        "project:project_target",
        "project:project_source",
    ]
    assert memory_client.contexts[0].allowed_project_ids == [
        "project_target",
        "project_source",
    ]
    started_payload = response.json()["model_call_events"][0]["payload"]
    assert started_payload["memory_allowed_project_ids"] == [
        "project_target",
        "project_source",
    ]


def test_run_next_task_uses_query_embedding_without_sending_vector_to_runtime() -> None:
    state_client = FakeStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_demo",
            title="Demo project",
            goal="Deliver a verified backend slice.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(
        TaskRecord(
            project_id="project_demo",
            title="Ready task",
            description="Use semantic memory retrieval before execution.",
            assigned_agent_id="agent-dev",
            acceptance_criteria=["Ready task can produce a recorded result."],
        )
    )
    memory_client = FakeMemoryClient(
        context_items=[
            MemoryItem(
                id="memory-embedded",
                scope="project:project_demo",
                project_id="project_demo",
                content="Embedded memory should be visible without its vector.",
                embedding=[1.0] + [0.0] * 1535,
            )
        ]
    )
    runtime_client = FakeAgentRuntimeClient()
    embedding_provider = FakeQueryEmbeddingProvider()
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=memory_client,
        runtime=runtime_client,
        query_embedding_provider=embedding_provider,
    )

    result = runner.run_next(
        trace_id="trace_gateway_embedding_test",
        headers={
            "x-synarch-actor-type": "service",
            "x-synarch-actor-id": "gateway-task-runner",
            "x-synarch-trace-id": "trace_gateway_embedding_test",
        },
    )

    assert "Ready task" in embedding_provider.texts[0]
    assert "Deliver a verified backend slice." in embedding_provider.texts[0]
    assert memory_client.contexts[0].query_embedding == [1.0] + [0.0] * 1535
    assert result.memory_context.query_embedding is None
    assert result.memory_context.items[0].embedding is None
    assert runtime_client.requests[0].memory_context is not None
    assert runtime_client.requests[0].memory_context.query_embedding is None
    assert runtime_client.requests[0].memory_context.items[0].embedding is None
    assert embedding_provider.texts[1] == (
        "Remember that this project needs explicit acceptance criteria."
    )
    assert memory_client.items[0].embedding == [0.0, 1.0] + [0.0] * 1534
    started_payload = result.model_call_events[0].payload
    assert started_payload["memory_query_embedding_used"] is True
    assert started_payload["memory_query_embedding_dimensions"] == 1536
    assert result.memory_events[0].payload["embedding_dimensions"] == 1536


def test_run_next_task_persists_agent_created_sub_tasks() -> None:
    state_client = FakeStateClient()
    parent_task = TaskRecord(
        id="task_parent",
        project_id="project_sourcing",
        title="Plan supplier outreach",
        assigned_agent_id="agent-ops-sourcing",
        acceptance_criteria=["Next supplier workflow is split into debuggable tasks."],
        sequence=3,
    )
    state_client.projects.append(
        ProjectRecord(
            id="project_sourcing",
            title="Supplier sourcing",
            goal="Find reliable suppliers for a motor in China.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(parent_task)
    runtime_client = SubTaskAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(
            {
                "agent-ops-sourcing": LocalWorldView(
                    agent_id="agent-ops-sourcing",
                    role="Ops sourcing",
                    division="ops",
                )
            }
        ),
        memory=FakeMemoryClient(),
        runtime=runtime_client,
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_sub_task_creation"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    created_sub_tasks = payload["created_sub_tasks"]
    assert [task["title"] for task in created_sub_tasks] == [
        "Find supplier directories",
        "Contact first supplier",
    ]
    assert created_sub_tasks[0]["parent_task_id"] == parent_task.id
    assert created_sub_tasks[0]["depends_on"] == [parent_task.id]
    assert created_sub_tasks[1]["depends_on"] == [
        parent_task.id,
        created_sub_tasks[0]["id"],
    ]
    assert created_sub_tasks[1]["acceptance_criteria"] == [
        "Contact channel, message, and stop condition are recorded."
    ]
    assert [event["type"] for event in payload["sub_task_events"]] == [
        "task.created",
        "task.created",
    ]
    assert [event.payload.get("parent_task_id") for event in state_client.events[-2:]] == [
        parent_task.id,
        parent_task.id,
    ]


def test_run_next_task_persists_agent_proposed_lifecycle_request() -> None:
    state_client = FakeStateClient()
    parent_task = TaskRecord(
        id="task_lifecycle_parent",
        project_id="project_sourcing",
        title="Assess staffing for supplier sourcing",
        assigned_agent_id="agent-ops-sourcing",
        acceptance_criteria=["Org changes are proposed, not applied directly."],
    )
    state_client.projects.append(
        ProjectRecord(
            id="project_sourcing",
            title="Supplier sourcing",
            goal="Find reliable suppliers for a motor in China.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(parent_task)
    runtime_client = LifecycleProposingAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(
            {
                "agent-ops-sourcing": LocalWorldView(
                    agent_id="agent-ops-sourcing",
                    role="Ops sourcing manager",
                    division="ops",
                )
            }
        ),
        memory=FakeMemoryClient(),
        runtime=runtime_client,
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_lifecycle_proposal"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    lifecycle_requests = payload["lifecycle_requests_created"]
    assert [request["action"] for request in lifecycle_requests] == ["create_agent"]
    assert lifecycle_requests[0]["requested_by_type"] == "agent"
    assert lifecycle_requests[0]["requested_by_id"] == "agent-ops-sourcing"
    assert lifecycle_requests[0]["status"] == "requested"
    assert lifecycle_requests[0]["requires_human_approval"] is True
    assert (
        lifecycle_requests[0]["proposed_agent"]["id"]
        == "agent-ops-sourcing-researcher"
    )
    assert state_client.agent_lifecycle_requests == [
        AgentLifecycleRequest.model_validate(lifecycle_requests[0])
    ]
    assert state_client.headers[-1]["x-synarch-actor-id"] == "gateway-task-runner"


def test_run_next_task_executes_agent_requested_tool_call() -> None:
    state_client = FakeStateClient()
    task = TaskRecord(
        id="task_tool_loop",
        project_id="project_sourcing",
        title="Verify supplier source",
        assigned_agent_id="agent-ops-sourcing",
        acceptance_criteria=["Fetched source evidence is reviewed before completion."],
    )
    state_client.projects.append(
        ProjectRecord(
            id="project_sourcing",
            title="Supplier sourcing",
            goal="Find reliable suppliers with source evidence.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(task)
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web", "service-event-log"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.search", "web.fetch"],
                    "service-event-log": ["event.emit"],
                },
                available_connector_ids=["connector-supplier-web"],
            )
        }
    )
    runtime_client = ToolLoopAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=control_plane,
        memory=FakeMemoryClient(),
        runtime=runtime_client,
        tool_runner=gateway_main.GatewayToolRunner(),
    )

    def fake_fetch_http_url(url: str, *, max_bytes: int) -> dict[str, object]:
        assert url == "https://example.com"
        assert max_bytes == 2048
        return {
            "url": url,
            "final_url": url,
            "status_code": 200,
            "content_type": "text/html",
            "bytes_read": 512,
            "truncated": False,
            "title": "Example Domain",
            "text_excerpt": "Example Domain This domain is for examples.",
        }

    original_fetch_http_url = gateway_main.fetch_http_url
    gateway_main.fetch_http_url = fake_fetch_http_url
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_tool_loop"},
        )
    finally:
        gateway_main.fetch_http_url = original_fetch_http_url
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(runtime_client.requests) == 2
    assert runtime_client.requests[0].tool_results == []
    assert runtime_client.requests[1].tool_results[0].tool_name == "web.fetch"
    assert payload["agent_result"]["status"] == "completed"
    assert payload["tool_results"][0]["tool_name"] == "web.fetch"
    assert payload["tool_results"][0]["output"]["title"] == "Example Domain"
    assert payload["cost_records"][0]["input_tokens"] == 50
    assert payload["cost_records"][0]["output_tokens"] == 22
    assert payload["cost_records"][0]["total_cost"] == 0.000005
    assert [event.type for event in state_client.events] == [
        EventType.model_call_started,
        EventType.tool_called,
        EventType.model_call_completed,
    ]
    assert state_client.audit_logs[0].action == "tool.allowed"
    assert state_client.tasks[0].result is not None
    assert state_client.tasks[0].result["tool_results"][0]["tool_name"] == "web.fetch"


def test_run_next_task_can_create_connector_job_through_tool_loop() -> None:
    state_client = FakeStateClient()
    task = TaskRecord(
        id="task_connector_job_tool_loop",
        project_id="project_sourcing",
        title="Schedule supplier follow-up",
        assigned_agent_id="agent-ops-sourcing",
        acceptance_criteria=["A bounded connector job is created for supplier follow-up."],
    )
    state_client.projects.append(
        ProjectRecord(
            id="project_sourcing",
            title="Supplier sourcing",
            goal="Find reliable suppliers with bounded autonomous follow-up.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(task)
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["connector.job.create", "web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": [
                        "connector.job.create",
                        "web.fetch",
                    ]
                },
                available_connector_ids=["connector-supplier-web"],
            )
        }
    )
    runtime_client = ConnectorJobToolLoopAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=control_plane,
        memory=FakeMemoryClient(),
        runtime=runtime_client,
        tool_runner=gateway_main.GatewayToolRunner(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_tool_loop"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(runtime_client.requests) == 2
    assert runtime_client.requests[0].tool_results == []
    assert runtime_client.requests[1].tool_results[0].tool_name == "connector.job.create"
    assert payload["agent_result"]["status"] == "completed"
    assert payload["tool_results"][0]["tool_name"] == "connector.job.create"
    assert (
        payload["tool_results"][0]["output"]["connector_job_id"]
        == "connector-job-task-runner-followup"
    )
    assert payload["tool_results"][0]["output"]["event_id"] == state_client.events[1].id
    assert payload["tool_results"][0]["output"]["audit_id"] == state_client.audit_logs[0].id
    assert (
        payload["tool_results"][0]["output"]["connector_job_event_id"]
        == state_client.events[2].id
    )
    assert len(state_client.connector_jobs) == 1
    job = state_client.connector_jobs[0]
    assert job.owner_agent_id == "agent-ops-sourcing"
    assert job.project_id == "project_sourcing"
    assert job.task_id == "task_connector_job_tool_loop"
    assert job.metadata["tool_name"] == "web.fetch"
    assert job.metadata["arguments"] == {
        "url": "https://example.com",
        "max_bytes": 1024,
    }
    assert job.metadata["max_runs"] == 2
    assert [event.type for event in state_client.events] == [
        EventType.model_call_started,
        EventType.tool_called,
        EventType.connector_job_created,
        EventType.model_call_completed,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "connector_job.created",
    ]
    assert state_client.tasks[0].result is not None
    assert (
        state_client.tasks[0].result["tool_results"][0]["output"]["connector_job_id"]
        == "connector-job-task-runner-followup"
    )


def test_run_next_task_can_stop_owned_connector_job_through_tool_loop() -> None:
    state_client = FakeStateClient()
    task = TaskRecord(
        id="task_connector_job_stop_tool_loop",
        project_id="project_sourcing",
        title="Stop supplier follow-up",
        assigned_agent_id="agent-ops-sourcing",
        acceptance_criteria=["The completed connector job is stopped."],
    )
    state_client.projects.append(
        ProjectRecord(
            id="project_sourcing",
            title="Supplier sourcing",
            goal="Stop bounded autonomous follow-up when a supplier replies.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(task)
    state_client.connector_jobs.append(
        ConnectorJobRecord(
            id="connector-job-task-runner-stop",
            service_id="connector-supplier-web",
            project_id="project_sourcing",
            task_id=task.id,
            owner_agent_id="agent-ops-sourcing",
            kind="cron",
            schedule="*/30 * * * *",
            purpose="Poll supplier until a reply is received.",
            created_by_type="agent",
            created_by_id="agent-ops-sourcing",
            metadata={"tool_name": "web.fetch"},
        )
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["connector.job.stop", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["connector.job.stop"]
                },
                available_connector_ids=["connector-supplier-web"],
            )
        }
    )
    runtime_client = ConnectorJobStopToolLoopAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=control_plane,
        memory=FakeMemoryClient(),
        runtime=runtime_client,
        tool_runner=gateway_main.GatewayToolRunner(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_stop_tool_loop"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(runtime_client.requests) == 2
    assert runtime_client.requests[1].tool_results[0].tool_name == "connector.job.stop"
    assert payload["agent_result"]["status"] == "completed"
    assert payload["tool_results"][0]["tool_name"] == "connector.job.stop"
    assert payload["tool_results"][0]["output"]["status"] == "stopped"
    assert state_client.connector_jobs[0].status == ConnectorJobStatus.stopped
    assert [event.type for event in state_client.events] == [
        EventType.model_call_started,
        EventType.tool_called,
        EventType.connector_job_stopped,
        EventType.model_call_completed,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "connector_job.stopped",
    ]
    assert state_client.tasks[0].result is not None
    assert (
        state_client.tasks[0].result["tool_results"][0]["output"]["connector_job_id"]
        == "connector-job-task-runner-stop"
    )


def test_run_next_task_can_list_then_stop_owned_connector_job() -> None:
    state_client = FakeStateClient()
    task = TaskRecord(
        id="task_connector_job_list_then_stop",
        project_id="project_sourcing",
        title="Find and stop completed supplier follow-up",
        assigned_agent_id="agent-ops-sourcing",
        acceptance_criteria=[
            "The active owned connector job is discovered before it is stopped."
        ],
    )
    state_client.projects.append(
        ProjectRecord(
            id="project_sourcing",
            title="Supplier sourcing",
            goal="Discover active follow-up jobs from state before acting.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(task)
    state_client.connector_jobs.extend(
        [
            ConnectorJobRecord(
                id="connector-job-list-then-stop",
                service_id="connector-supplier-web",
                project_id="project_sourcing",
                task_id="task_previous_followup",
                owner_agent_id="agent-ops-sourcing",
                kind="cron",
                schedule="*/30 * * * *",
                purpose="Poll supplier until a reply is received.",
                created_by_type="agent",
                created_by_id="agent-ops-sourcing",
                metadata={"tool_name": "web.fetch"},
            ),
            ConnectorJobRecord(
                id="connector-job-list-other-owner",
                service_id="connector-supplier-web",
                project_id="project_sourcing",
                task_id="task_previous_followup",
                owner_agent_id="agent-other",
                kind="cron",
                schedule="*/30 * * * *",
                purpose="Another agent follow-up job.",
                created_by_type="agent",
                created_by_id="agent-other",
                metadata={"tool_name": "web.fetch"},
            ),
        ]
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["connector.job.list", "connector.job.stop"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": [
                        "connector.job.list",
                        "connector.job.stop",
                    ]
                },
                available_connector_ids=["connector-supplier-web"],
            )
        }
    )
    runtime_client = ConnectorJobListThenStopToolLoopAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=control_plane,
        memory=FakeMemoryClient(),
        runtime=runtime_client,
        tool_runner=gateway_main.GatewayToolRunner(),
        max_tool_rounds=2,
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_connector_job_list_then_stop"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(runtime_client.requests) == 3
    assert [tool_result["tool_name"] for tool_result in payload["tool_results"]] == [
        "connector.job.list",
        "connector.job.stop",
    ]
    assert payload["tool_results"][0]["output"]["connector_jobs"][0]["id"] == (
        "connector-job-list-then-stop"
    )
    assert payload["tool_results"][1]["output"]["status"] == "stopped"
    assert state_client.connector_jobs[0].status == ConnectorJobStatus.stopped
    assert state_client.connector_jobs[1].status == ConnectorJobStatus.active
    assert [event.type for event in state_client.events] == [
        EventType.model_call_started,
        EventType.tool_called,
        EventType.tool_called,
        EventType.connector_job_stopped,
        EventType.model_call_completed,
    ]
    assert [audit.action for audit in state_client.audit_logs] == [
        "tool.allowed",
        "tool.allowed",
        "connector_job.stopped",
    ]
    assert payload["agent_result"]["status"] == "completed"
    assert state_client.tasks[0].result is not None
    assert [result["tool_name"] for result in state_client.tasks[0].result["tool_results"]] == [
        "connector.job.list",
        "connector.job.stop",
    ]


def test_run_task_by_id_executes_requested_task() -> None:
    state_client = FakeStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_targeted",
            title="Targeted run",
            goal="Run one requested task even if another task is queued.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.extend(
        [
            TaskRecord(
                id="task_old_ready",
                project_id="project_targeted",
                title="Old ready task",
                assigned_agent_id="agent-dev",
                acceptance_criteria=["Old task remains queued."],
            ),
            TaskRecord(
                id="task_requested",
                project_id="project_targeted",
                title="Requested task",
                assigned_agent_id="agent-dev",
                acceptance_criteria=["Requested task runs."],
            ),
        ]
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=FakeAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/task_requested/run",
            headers={"X-Synarch-Trace-Id": "trace_targeted_task_run"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["id"] == "task_requested"
    assert state_client.tasks[0].id == "task_old_ready"
    assert state_client.tasks[0].status == TaskStatus.queued
    assert state_client.tasks[1].id == "task_requested"
    assert state_client.tasks[1].status == TaskStatus.needs_review


def test_run_task_by_id_records_skip_event_when_agent_is_inactive() -> None:
    state_client = InactiveAgentStateClient("task_inactive_targeted")
    state_client.projects.append(
        ProjectRecord(
            id="project_inactive_targeted",
            title="Inactive targeted run",
            goal="Record a targeted run rejection in the project timeline.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(
        TaskRecord(
            id="task_inactive_targeted",
            project_id="project_inactive_targeted",
            title="Assigned to inactive agent",
            assigned_agent_id="agent-retired",
            acceptance_criteria=["The task remains queued."],
        )
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=FakeAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/task_inactive_targeted/run",
            headers={"X-Synarch-Trace-Id": "trace_targeted_inactive_skip"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "Agent is not active: agent-retired"
    assert state_client.tasks[0].status == TaskStatus.queued
    assert [event.type for event in state_client.events] == [EventType.task_skipped]
    assert state_client.events[0].target == "project_inactive_targeted"
    assert state_client.events[0].trace_id == "trace_targeted_inactive_skip"
    assert state_client.events[0].payload["skipped_tasks"] == [
        {
            "task_id": "task_inactive_targeted",
            "category": "inactive_agent",
            "reason": "Task assigned agent is inactive.",
        }
    ]
    assert state_client.events[0].payload["skipped_task_ids"] == [
        "task_inactive_targeted"
    ]
    assert state_client.events[0].payload["status_code"] == 409
    assert [audit.action for audit in state_client.audit_logs] == ["task.run_skipped"]
    assert state_client.audit_logs[0].target_id == "task_inactive_targeted"
    assert state_client.audit_logs[0].trace_id == "trace_targeted_inactive_skip"


def test_run_ready_tasks_executes_project_chain_until_no_ready_task() -> None:
    state_client = FakeStateClient()
    state_client.projects.extend(
        [
            ProjectRecord(
                id="project_batch",
                title="Batch run",
                goal="Run a small ready chain.",
                owner_agent_id="agent-direction",
            ),
            ProjectRecord(
                id="project_other",
                title="Other project",
                goal="Must not be run by a project-filtered batch.",
                owner_agent_id="agent-direction",
            ),
        ]
    )
    state_client.tasks.extend(
        [
            TaskRecord(
                id="task_batch_first",
                project_id="project_batch",
                title="First batch task",
                assigned_agent_id="agent-dev",
                acceptance_criteria=["First task completes."],
                sequence=1,
            ),
            TaskRecord(
                id="task_batch_second",
                project_id="project_batch",
                title="Second batch task",
                assigned_agent_id="agent-dev",
                depends_on=["task_batch_first"],
                acceptance_criteria=["Second task completes after first."],
                sequence=2,
            ),
            TaskRecord(
                id="task_other_ready",
                project_id="project_other",
                title="Other ready task",
                assigned_agent_id="agent-dev",
                acceptance_criteria=["Other task remains queued."],
            ),
        ]
    )
    runtime_client = CompletingAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=runtime_client,
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-ready",
            params={"project_id": "project_batch", "max_tasks": 5},
            headers={"X-Synarch-Trace-Id": "trace_batch_run"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_id"] == "trace_batch_run"
    assert payload["project_id"] == "project_batch"
    assert payload["max_tasks"] == 5
    assert payload["stop_reason"] == "no_ready_task"
    assert payload["scheduler_event"]["type"] == "scheduler.tick"
    assert payload["scheduler_event"]["payload"]["run_count"] == 2
    assert payload["scheduler_audit_log"]["action"] == "scheduler.tick"
    assert [run["task"]["id"] for run in payload["runs"]] == [
        "task_batch_first",
        "task_batch_second",
    ]
    assert [request.task.id for request in runtime_client.requests] == [
        "task_batch_first",
        "task_batch_second",
    ]
    assert [task.status for task in state_client.tasks] == [
        TaskStatus.completed,
        TaskStatus.completed,
        TaskStatus.queued,
    ]
    assert state_client.events[-1].type == EventType.scheduler_tick
    assert state_client.events[-1].payload["task_ids"] == [
        "task_batch_first",
        "task_batch_second",
    ]
    assert state_client.audit_logs[-1].action == "scheduler.tick"
    assert state_client.audit_logs[-1].payload["stop_reason"] == "no_ready_task"


def test_run_ready_tasks_skips_task_with_missing_required_tool_credentials() -> None:
    state_client = FakeStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_readiness",
            title="Credential readiness",
            goal="Skip blocked tool tasks and run the next ready task.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.extend(
        [
            TaskRecord(
                id="task_missing_credentials",
                project_id="project_readiness",
                title="Fetch authenticated page",
                assigned_agent_id="agent-ops-sourcing",
                required_tools=["web.fetch"],
                required_tool_scopes={
                    "web.fetch": ["browser:authenticated_fetch"]
                },
                acceptance_criteria=["Authenticated fetch has evidence."],
                sequence=1,
            ),
            TaskRecord(
                id="task_no_required_tools",
                project_id="project_readiness",
                title="Run fallback planning",
                assigned_agent_id="agent-dev",
                acceptance_criteria=["Fallback planning completes."],
                sequence=2,
            ),
        ]
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.fetch"]
                },
                available_service_credential_scopes={"connector-supplier-web": []},
            ),
            "agent-dev": LocalWorldView(
                agent_id="agent-dev",
                role="Code and infra",
                division="dev",
            ),
        }
    )
    runtime_client = CompletingAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=control_plane,
        memory=FakeMemoryClient(),
        runtime=runtime_client,
        tool_readiness=gateway_main.GatewayToolReadinessChecker(),
    )

    result = runner.run_ready(
        max_tasks=1,
        trace_id="trace_readiness_skip",
        headers=gateway_main.service_headers("trace_readiness_skip"),
        project_id="project_readiness",
    )

    assert result.skipped_task_ids == ["task_missing_credentials"]
    assert [skip.model_dump(mode="json") for skip in result.skipped_tasks] == [
        {
            "task_id": "task_missing_credentials",
            "category": "credential_readiness",
            "reason": "Credential scopes missing for required tool: web.fetch",
        }
    ]
    access_request_payload = result.credential_access_requests[0].model_dump(mode="json")
    assert access_request_payload | {"created_at": None} == {
        "id": "credential_access_task_missing_credentials_web_fetch",
        "task_id": "task_missing_credentials",
        "project_id": "project_readiness",
        "agent_id": "agent-ops-sourcing",
        "tool_name": "web.fetch",
        "requested_scopes": ["browser:authenticated_fetch"],
        "candidate_service_ids": ["connector-supplier-web"],
        "reason": "Credential scopes missing for required tool: web.fetch",
        "requested_by_type": "service",
        "requested_by_id": "gateway-scheduler",
        "status": "requested",
        "created_at": None,
    }
    assert [run.task.id for run in result.runs] == ["task_no_required_tools"]
    assert [request.task.id for request in runtime_client.requests] == [
        "task_no_required_tools"
    ]
    assert state_client.tasks[0].status == TaskStatus.queued
    assert state_client.tasks[1].status == TaskStatus.completed
    assert state_client.events[-1].payload["skipped_task_ids"] == [
        "task_missing_credentials"
    ]
    assert state_client.events[-1].payload["skipped_tasks"] == [
        {
            "task_id": "task_missing_credentials",
            "category": "credential_readiness",
            "reason": "Credential scopes missing for required tool: web.fetch",
        }
    ]
    assert state_client.events[-1].payload["credential_access_request_ids"] == [
        "credential_access_task_missing_credentials_web_fetch"
    ]
    assert state_client.credential_access_requests[0].requested_scopes == [
        "browser:authenticated_fetch"
    ]


def test_run_ready_tasks_resumes_after_credential_grant() -> None:
    state_client = FakeStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_readiness_resume",
            title="Credential readiness resume",
            goal="Resume credential-blocked work after a grant is applied.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(
        TaskRecord(
            id="task_credentials_applied",
            project_id="project_readiness_resume",
            title="Fetch authenticated page",
            assigned_agent_id="agent-ops-sourcing",
            required_tools=["web.fetch"],
            required_tool_scopes={"web.fetch": ["browser:authenticated_fetch"]},
            acceptance_criteria=["Authenticated fetch has evidence."],
            sequence=1,
        )
    )
    state_client.credential_access_requests.append(
        CredentialAccessRequest(
            id="credential_access_task_credentials_applied_web_fetch",
            task_id="task_credentials_applied",
            project_id="project_readiness_resume",
            agent_id="agent-ops-sourcing",
            tool_name="web.fetch",
            requested_scopes=["browser:authenticated_fetch"],
            candidate_service_ids=["connector-supplier-web"],
            reason="Credential scopes missing for required tool: web.fetch",
            status="applied",
        )
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.fetch"]
                },
                available_service_credential_scopes={
                    "connector-supplier-web": ["browser:authenticated_fetch"]
                },
            )
        }
    )
    runtime_client = CompletingAgentRuntimeClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=control_plane,
        memory=FakeMemoryClient(),
        runtime=runtime_client,
        tool_readiness=gateway_main.GatewayToolReadinessChecker(),
    )

    result = runner.run_ready(
        max_tasks=1,
        trace_id="trace_readiness_resume",
        headers=gateway_main.service_headers("trace_readiness_resume"),
        project_id="project_readiness_resume",
    )

    assert result.skipped_task_ids == []
    assert result.credential_access_requests == []
    assert result.credential_resumed_task_ids == ["task_credentials_applied"]
    assert [run.task.id for run in result.runs] == ["task_credentials_applied"]
    assert [request.task.id for request in runtime_client.requests] == [
        "task_credentials_applied"
    ]
    assert state_client.tasks[0].status == TaskStatus.completed
    assert state_client.events[-1].payload["credential_resumed_task_ids"] == [
        "task_credentials_applied"
    ]
    assert state_client.events[-1].payload["credential_resumed_task_count"] == 1


def test_list_credential_access_requests_forwards_state_filters() -> None:
    state_client = FakeStateClient()
    state_client.credential_access_requests.append(
        CredentialAccessRequest(
            id="credential-access-visible",
            task_id="task_fetch_supplier",
            project_id="project_supplier",
            agent_id="agent-ops-sourcing",
            tool_name="web.fetch",
            requested_scopes=["browser:authenticated_fetch"],
            candidate_service_ids=["connector-supplier-web"],
            reason="Credential scopes missing for required tool: web.fetch",
        )
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).get(
            "/credential-access-requests",
            params={"project_id": "project_supplier", "status": "requested"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["id"] == "credential-access-visible"
    assert response.json()[0]["requested_scopes"] == ["browser:authenticated_fetch"]


def test_decide_credential_access_request_forwards_decision() -> None:
    state_client = FakeStateClient()
    state_client.credential_access_requests.append(
        CredentialAccessRequest(
            id="credential-access-decision-visible",
            task_id="task_fetch_supplier",
            project_id="project_supplier",
            agent_id="agent-ops-sourcing",
            tool_name="web.fetch",
            requested_scopes=["browser:authenticated_fetch"],
            candidate_service_ids=["connector-supplier-web"],
            reason="Credential scopes missing for required tool: web.fetch",
        )
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/credential-access-requests/credential-access-decision-visible/decisions",
            headers={"X-Synarch-Trace-Id": "trace_credential_gateway_decision"},
            json={
                "request_id": "credential-access-decision-visible",
                "status": "approved",
                "decided_by_type": "user",
                "decided_by_id": "local-user",
                "rationale": "Approved for a scoped supplier lookup.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["events_emitted"][0]["type"] == "approval.decided"
    assert state_client.credential_access_requests[0].status == "approved"
    assert state_client.headers[-1]["x-synarch-trace-id"] == (
        "trace_credential_gateway_decision"
    )


def test_apply_credential_access_grant_forwards_application() -> None:
    state_client = FakeStateClient()
    state_client.credential_access_requests.append(
        CredentialAccessRequest(
            id="credential-access-grant-visible",
            task_id="task_fetch_supplier",
            project_id="project_supplier",
            agent_id="agent-ops-sourcing",
            tool_name="web.fetch",
            requested_scopes=["browser:authenticated_fetch"],
            candidate_service_ids=["connector-supplier-web"],
            reason="Credential scopes missing for required tool: web.fetch",
            status="approved",
        )
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/credential-access-requests/credential-access-grant-visible/grant-applications",
            headers={"X-Synarch-Trace-Id": "trace_credential_gateway_grant"},
            json={
                "request_id": "credential-access-grant-visible",
                "service_id": "connector-supplier-web",
                "applied_by_type": "user",
                "applied_by_id": "local-user",
                "rationale": "Apply approved credential scopes.",
            },
        )
        grants_response = TestClient(app).get(
            "/credential-grants",
            params={"request_id": "credential-access-grant-visible"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["access_request"]["status"] == "applied"
    assert response.json()["grant"]["scopes"] == ["browser:authenticated_fetch"]
    assert response.json()["events_emitted"][0]["type"] == "credential_grant.applied"
    assert grants_response.status_code == 200
    assert grants_response.json()[0]["service_id"] == "connector-supplier-web"
    assert state_client.headers[-1]["x-synarch-trace-id"] == (
        "trace_credential_gateway_grant"
    )


def test_run_ready_tasks_records_tool_loop_metrics() -> None:
    state_client = FakeStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_scheduler_tool_loop",
            title="Scheduler tool loop",
            goal="Run a ready task that needs source evidence.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(
        TaskRecord(
            id="task_scheduler_tool_loop",
            project_id="project_scheduler_tool_loop",
            title="Verify supplier source from scheduler",
            assigned_agent_id="agent-ops-sourcing",
            acceptance_criteria=["web.fetch evidence is returned to the runtime."],
        )
    )
    control_plane = FakeControlPlaneClient(
        {
            "agent-ops-sourcing": LocalWorldView(
                agent_id="agent-ops-sourcing",
                role="Ops sourcing",
                division="ops-sourcing",
                permissions=PermissionBundle(
                    allowed_tools=["web.fetch", "event.emit"],
                    denied_tools=[],
                ),
                available_services=["connector-supplier-web", "service-event-log"],
                available_service_capabilities={
                    "connector-supplier-web": ["web.search", "web.fetch"],
                    "service-event-log": ["event.emit"],
                },
                available_connector_ids=["connector-supplier-web"],
            )
        }
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=control_plane,
        memory=FakeMemoryClient(),
        runtime=ToolLoopAgentRuntimeClient(),
        tool_runner=gateway_main.GatewayToolRunner(),
    )

    def fake_fetch_http_url(url: str, *, max_bytes: int) -> dict[str, object]:
        return {
            "url": url,
            "final_url": url,
            "status_code": 200,
            "content_type": "text/html",
            "bytes_read": max_bytes,
            "truncated": False,
            "title": "Example Domain",
            "text_excerpt": "Example Domain This domain is for examples.",
        }

    original_fetch_http_url = gateway_main.fetch_http_url
    gateway_main.fetch_http_url = fake_fetch_http_url
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-ready",
            params={"project_id": "project_scheduler_tool_loop", "max_tasks": 1},
            headers={"X-Synarch-Trace-Id": "trace_scheduler_tool_loop"},
        )
    finally:
        gateway_main.fetch_http_url = original_fetch_http_url
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    scheduler_payload = payload["scheduler_event"]["payload"]
    assert payload["runs"][0]["tool_results"][0]["tool_name"] == "web.fetch"
    assert scheduler_payload["run_count"] == 1
    assert scheduler_payload["tool_result_count"] == 1
    assert scheduler_payload["failed_tool_result_count"] == 0
    assert scheduler_payload["tool_names"] == ["web.fetch"]
    assert scheduler_payload["total_cost"] == 0.000005
    assert state_client.events[-1].type == EventType.scheduler_tick
    assert state_client.events[-1].payload["tool_result_count"] == 1


def test_run_ready_tasks_stops_at_max_tasks() -> None:
    state_client = FakeStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_limited",
            title="Limited batch run",
            goal="Stop after one task even when more work is ready.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.extend(
        [
            TaskRecord(
                id="task_limited_first",
                project_id="project_limited",
                title="First limited task",
                assigned_agent_id="agent-dev",
                acceptance_criteria=["First task completes."],
            ),
            TaskRecord(
                id="task_limited_second",
                project_id="project_limited",
                title="Second limited task",
                assigned_agent_id="agent-dev",
                acceptance_criteria=["Second task waits for another batch."],
            ),
        ]
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=CompletingAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-ready",
            params={"project_id": "project_limited", "max_tasks": 1},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["stop_reason"] == "max_tasks_reached"
    assert payload["scheduler_event"]["payload"]["run_count"] == 1
    assert [run["task"]["id"] for run in payload["runs"]] == ["task_limited_first"]
    assert [task.status for task in state_client.tasks] == [
        TaskStatus.completed,
        TaskStatus.queued,
    ]


def test_run_ready_tasks_skips_claim_conflict_and_continues() -> None:
    state_client = ClaimConflictStateClient("task_claimed_elsewhere")
    state_client.projects.append(
        ProjectRecord(
            id="project_claim_conflict",
            title="Claim conflict",
            goal="Another scheduler may claim the first task.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.extend(
        [
            TaskRecord(
                id="task_claimed_elsewhere",
                project_id="project_claim_conflict",
                title="Claimed elsewhere",
                assigned_agent_id="agent-dev",
                acceptance_criteria=["Conflict is skipped."],
            ),
            TaskRecord(
                id="task_after_conflict",
                project_id="project_claim_conflict",
                title="Run after conflict",
                assigned_agent_id="agent-dev",
                acceptance_criteria=["Next ready task still runs."],
            ),
        ]
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=CompletingAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-ready",
            params={"project_id": "project_claim_conflict", "max_tasks": 2},
            headers={"X-Synarch-Trace-Id": "trace_claim_conflict"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["stop_reason"] == "no_ready_task"
    assert payload["skipped_task_ids"] == ["task_claimed_elsewhere"]
    assert payload["skipped_tasks"] == [
        {
            "task_id": "task_claimed_elsewhere",
            "category": "claim_conflict",
            "reason": "Task was already claimed by another scheduler.",
        }
    ]
    assert [run["task"]["id"] for run in payload["runs"]] == ["task_after_conflict"]
    assert payload["scheduler_event"]["payload"]["skipped_task_count"] == 1
    assert payload["scheduler_event"]["payload"]["skipped_task_ids"] == [
        "task_claimed_elsewhere"
    ]
    assert payload["scheduler_event"]["payload"]["skipped_tasks"] == [
        {
            "task_id": "task_claimed_elsewhere",
            "category": "claim_conflict",
            "reason": "Task was already claimed by another scheduler.",
        }
    ]
    assert [task.status for task in state_client.tasks] == [
        TaskStatus.running,
        TaskStatus.completed,
    ]


def test_run_ready_tasks_skips_inactive_agent_and_continues() -> None:
    state_client = InactiveAgentStateClient("task_inactive_agent")
    state_client.projects.append(
        ProjectRecord(
            id="project_inactive_agent",
            title="Inactive agent",
            goal="Skip queued work assigned to inactive agents.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.extend(
        [
            TaskRecord(
                id="task_inactive_agent",
                project_id="project_inactive_agent",
                title="Assigned to inactive agent",
                assigned_agent_id="agent-retired",
                acceptance_criteria=["Inactive agent task remains queued."],
            ),
            TaskRecord(
                id="task_after_inactive_agent",
                project_id="project_inactive_agent",
                title="Run active agent task",
                assigned_agent_id="agent-dev",
                acceptance_criteria=["Next ready task still runs."],
            ),
        ]
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=CompletingAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-ready",
            params={"project_id": "project_inactive_agent", "max_tasks": 2},
            headers={"X-Synarch-Trace-Id": "trace_inactive_agent_skip"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["stop_reason"] == "no_ready_task"
    assert payload["skipped_task_ids"] == ["task_inactive_agent"]
    assert payload["skipped_tasks"] == [
        {
            "task_id": "task_inactive_agent",
            "category": "inactive_agent",
            "reason": "Task assigned agent is inactive.",
        }
    ]
    assert [run["task"]["id"] for run in payload["runs"]] == ["task_after_inactive_agent"]
    assert payload["scheduler_event"]["payload"]["skipped_tasks"] == [
        {
            "task_id": "task_inactive_agent",
            "category": "inactive_agent",
            "reason": "Task assigned agent is inactive.",
        }
    ]
    assert [task.status for task in state_client.tasks] == [
        TaskStatus.queued,
        TaskStatus.completed,
    ]


def test_next_ready_task_skips_tasks_inside_retry_backoff() -> None:
    task_waiting = TaskRecord(
        id="task_retry_waiting",
        project_id="project_retry_backoff",
        title="Waiting retry",
        status=TaskStatus.queued,
        assigned_agent_id="agent-dev",
        acceptance_criteria=["The retry window is respected."],
        retry_after_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    task_due = TaskRecord(
        id="task_retry_due",
        project_id="project_retry_backoff",
        title="Due retry",
        status=TaskStatus.queued,
        assigned_agent_id="agent-dev",
        acceptance_criteria=["The task can run after backoff."],
        retry_after_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    assert next_ready_task([task_waiting]) is None
    assert next_ready_task([task_waiting, task_due]) == task_due


def test_run_ready_tasks_recovers_expired_leases_before_selecting_ready_task() -> None:
    state_client = RecoveringStateClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_recover_lease",
            title="Recover lease",
            goal="Recover expired work before selecting ready tasks.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.append(
        TaskRecord(
            id="task_expired_running",
            project_id="project_recover_lease",
            title="Expired running task",
            status=TaskStatus.running,
            assigned_agent_id="agent-dev",
            acceptance_criteria=["Expired task is retried."],
            attempt_count=1,
            max_attempts=3,
            lease_owner_id="gateway-task-runner",
            lease_expires_at=datetime.now(UTC) - timedelta(seconds=30),
            last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=60),
        )
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=CompletingAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-ready",
            params={"project_id": "project_recover_lease", "max_tasks": 1},
            headers={"X-Synarch-Trace-Id": "trace_recover_lease"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["lease_recovery"]["recovered_task_ids"] == ["task_expired_running"]
    assert payload["runs"] == []
    assert payload["stop_reason"] == "no_ready_task"
    assert payload["scheduler_event"]["payload"]["lease_recovered_task_ids"] == [
        "task_expired_running"
    ]
    assert state_client.tasks[0].status == TaskStatus.queued
    assert state_client.tasks[0].retry_after_at is not None


def test_run_ready_tasks_records_empty_scheduler_tick() -> None:
    state_client = FakeStateClient()
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=CompletingAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-ready",
            params={"project_id": "project_empty", "max_tasks": 3},
            headers={"X-Synarch-Trace-Id": "trace_empty_scheduler_tick"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["runs"] == []
    assert payload["stop_reason"] == "no_ready_task"
    assert payload["lease_recovery"]["recovered_task_ids"] == []
    assert payload["lease_recovery"]["failed_task_ids"] == []
    assert payload["scheduler_event"]["type"] == "scheduler.tick"
    assert payload["scheduler_event"]["target"] == "project_empty"
    assert payload["scheduler_event"]["payload"] == {
        "project_id": "project_empty",
        "max_tasks": 3,
        "stop_reason": "no_ready_task",
        "run_count": 0,
        "task_ids": [],
        "skipped_task_ids": [],
        "skipped_tasks": [],
        "skipped_task_count": 0,
        "credential_access_request_ids": [],
        "credential_access_request_count": 0,
        "credential_resumed_task_ids": [],
        "credential_resumed_task_count": 0,
        "lease_recovered_task_ids": [],
        "lease_failed_task_ids": [],
        "created_sub_task_count": 0,
        "tool_result_count": 0,
        "failed_tool_result_count": 0,
        "tool_names": [],
        "cost_ids": [],
        "total_cost": 0,
    }
    assert payload["scheduler_audit_log"]["actor_id"] == "gateway-scheduler"
    assert payload["scheduler_audit_log"]["target_id"] == "project_empty"
    assert state_client.events[0].type == EventType.scheduler_tick
    assert state_client.audit_logs[0].action == "scheduler.tick"


def test_list_task_review_queue_reads_state_service() -> None:
    state_client = FakeStateClient()
    state_client.tasks.append(
        TaskRecord(
            id="task_gateway_review",
            project_id="project_gateway_review",
            title="Review gateway task",
            status=TaskStatus.needs_review,
            assigned_agent_id="agent-dev",
            acceptance_criteria=["Reviewer can see this task."],
            dead_letter_reason="lease_expired",
            dead_lettered_at=datetime.now(UTC),
        )
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).get(
            "/tasks/review-queue",
            params={"project_id": "project_gateway_review"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [task["id"] for task in response.json()] == ["task_gateway_review"]


def test_apply_task_review_decision_forwards_reviewer_headers() -> None:
    state_client = FakeStateClient()
    state_client.tasks.append(
        TaskRecord(
            id="task_gateway_retry",
            project_id="project_gateway_retry",
            title="Retry through gateway",
            status=TaskStatus.needs_review,
            assigned_agent_id="agent-dev",
            acceptance_criteria=["Reviewer can retry this task."],
            dead_letter_reason="lease_expired",
            dead_lettered_at=datetime.now(UTC),
        )
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).post(
            "/tasks/task_gateway_retry/review-decisions",
            headers={
                "X-Synarch-Actor-Type": "user",
                "X-Synarch-Actor-Id": "hugo",
                "X-Synarch-Trace-Id": "trace_gateway_review",
            },
            json={
                "action": "retry",
                "reason": "Retry after human clarification.",
                "title": "Retry clarified task",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["status"] == "queued"
    assert payload["task"]["title"] == "Retry clarified task"
    assert payload["event"]["type"] == "task.reviewed"
    assert payload["audit_log"]["actor_id"] == "hugo"
    assert state_client.headers[-1] == {
        "x-synarch-actor-type": "user",
        "x-synarch-actor-id": "hugo",
        "x-synarch-trace-id": "trace_gateway_review",
    }


def test_list_memory_items_filters_review_queue() -> None:
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-candidate"] = MemoryItem(
        id="memory-candidate",
        scope="project:project_demo",
        content="Candidate memory.",
        status="proposed",
        agent_id="agent-dev",
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-approved"] = MemoryItem(
        id="memory-approved",
        scope="project:project_demo",
        content="Approved memory.",
        status="approved",
        agent_id="agent-dev",
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-other-project"] = MemoryItem(
        id="memory-other-project",
        scope="project:project_other",
        content="Other project candidate.",
        status="proposed",
        agent_id="agent-dev",
        project_id="project_other",
    )
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).get(
            "/memory-items",
            params={"project_id": "project_demo", "status": "proposed"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == ["memory-candidate"]


def test_backfill_memory_embeddings_updates_items_and_records_events() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    embedding_provider = FakeQueryEmbeddingProvider()
    memory_client.items_by_id["memory-missing-embedding"] = MemoryItem(
        id="memory-missing-embedding",
        scope="project:project_demo",
        content="Backfill me.",
        status=MemoryStatus.approved,
        agent_id="agent-dev",
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-existing-embedding"] = MemoryItem(
        id="memory-existing-embedding",
        scope="project:project_demo",
        content="Already indexed.",
        status=MemoryStatus.approved,
        agent_id="agent-dev",
        project_id="project_demo",
        embedding=[0.2] * 1536,
    )
    memory_client.items_by_id["memory-empty-content"] = MemoryItem(
        id="memory-empty-content",
        scope="project:project_demo",
        content=" ",
        status=MemoryStatus.approved,
        agent_id="agent-dev",
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-proposed"] = MemoryItem(
        id="memory-proposed",
        scope="project:project_demo",
        content="Not approved yet.",
        status=MemoryStatus.proposed,
        agent_id="agent-dev",
        project_id="project_demo",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client
    app.dependency_overrides[gateway_main.get_query_embedding_provider] = (
        lambda: embedding_provider
    )

    try:
        response = TestClient(app).post(
            "/memory-items/embedding-backfill",
            json={"project_id": "project_demo", "max_items": 2},
            headers={
                "X-Synarch-Actor-Type": "service",
                "X-Synarch-Actor-Id": "memory-embedding-worker-test",
                "X-Synarch-Trace-Id": "trace_memory_embedding_test",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "inspected_count": 3,
        "backfilled_count": 1,
        "skipped_count": 2,
        "memory_ids": ["memory-missing-embedding"],
    }
    assert embedding_provider.texts == ["Backfill me."]
    backfilled_item = memory_client.items_by_id["memory-missing-embedding"]
    assert backfilled_item.embedding is not None
    assert len(backfilled_item.embedding) == 1536
    assert [event.type for event in state_client.events] == [
        "memory.embedding_backfilled"
    ]
    assert state_client.events[0].target == "project_demo"
    assert state_client.events[0].payload == {
        "memory_id": "memory-missing-embedding",
        "scope": "project:project_demo",
        "status": "approved",
        "project_id": "project_demo",
        "agent_id": "agent-dev",
        "embedding_dimensions": 1536,
        "embedding_provider_id": "provider-test-embedding",
        "embedding_model_id": "model-test-embedding",
    }
    assert state_client.events[0].trace_id == "trace_memory_embedding_test"
    assert state_client.headers[-1]["x-synarch-actor-id"] == (
        "memory-embedding-worker-test"
    )


def test_backfill_memory_embeddings_requires_configured_provider() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client
    app.dependency_overrides[gateway_main.get_query_embedding_provider] = lambda: None

    try:
        response = TestClient(app).post(
            "/memory-items/embedding-backfill",
            json={"project_id": "project_demo"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Memory embedding provider unavailable"
    assert state_client.events == []


def test_propose_memory_relation_creates_reviewable_memory_and_event() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    state_client.workspaces.append(
        ProjectWorkspace(
            id="workspace-target",
            project_id="project_target",
            name="Target workspace",
            memory_scope="project:project_target",
            bridge_project_ids=["project_source"],
            active=True,
        )
    )
    memory_client.items_by_id["memory-source"] = MemoryItem(
        id="memory-source",
        scope="project:project_target",
        content="Source memory.",
        status=MemoryStatus.approved,
        project_id="project_target",
    )
    memory_client.items_by_id["memory-related"] = MemoryItem(
        id="memory-related",
        scope="project:project_source",
        content="Related source memory.",
        status=MemoryStatus.approved,
        project_id="project_source",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).post(
            "/memory-items/relation-proposals",
            json={
                "source_memory_id": "memory-source",
                "related_memory_ids": ["memory-related"],
                "reason": "The related memory explains the source memory.",
            },
            headers={
                "X-Synarch-Actor-Type": "user",
                "X-Synarch-Actor-Id": "hugo",
                "X-Synarch-Trace-Id": "trace_memory_relation_proposal",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    proposal = payload["proposal_memory"]
    assert proposal["status"] == "proposed"
    assert proposal["project_id"] == "project_target"
    assert proposal["metadata"] == {
        "kind": "memory_relation_proposal",
        "source_memory_id": "memory-source",
        "related_memory_ids": ["memory-related"],
        "reason": "The related memory explains the source memory.",
    }
    assert payload["event"]["type"] == "memory.relation_proposed"
    assert payload["event"]["payload"]["source_memory_id"] == "memory-source"
    assert [event.type for event in state_client.events] == [
        EventType.memory_relation_proposed
    ]
    assert state_client.headers[-1]["x-synarch-actor-id"] == "hugo"


def test_propose_memory_relation_rejects_unbridged_project() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-source"] = MemoryItem(
        id="memory-source",
        scope="project:project_target",
        content="Source memory.",
        status=MemoryStatus.approved,
        project_id="project_target",
    )
    memory_client.items_by_id["memory-related"] = MemoryItem(
        id="memory-related",
        scope="project:project_other",
        content="Unbridged memory.",
        status=MemoryStatus.approved,
        project_id="project_other",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).post(
            "/memory-items/relation-proposals",
            json={
                "source_memory_id": "memory-source",
                "related_memory_ids": ["memory-related"],
                "reason": "This project is not bridged.",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Related memory project is not authorized by an active bridge"
    )
    assert state_client.events == []


def test_apply_memory_relation_proposal_updates_source_metadata_and_records_event() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-source"] = MemoryItem(
        id="memory-source",
        scope="project:project_target",
        content="Source memory.",
        status=MemoryStatus.approved,
        project_id="project_target",
        metadata={"related_memory_ids": ["memory-existing"]},
    )
    memory_client.items_by_id["memory-existing"] = MemoryItem(
        id="memory-existing",
        scope="project:project_target",
        content="Existing related memory.",
        status=MemoryStatus.approved,
        project_id="project_target",
    )
    memory_client.items_by_id["memory-related"] = MemoryItem(
        id="memory-related",
        scope="project:project_target",
        content="New related memory.",
        status=MemoryStatus.approved,
        project_id="project_target",
    )
    memory_client.items_by_id["memory-proposal"] = MemoryItem(
        id="memory-proposal",
        scope="project:project_target",
        content="Proposal.",
        status=MemoryStatus.approved,
        project_id="project_target",
        metadata={
            "kind": "memory_relation_proposal",
            "source_memory_id": "memory-source",
            "related_memory_ids": ["memory-related", "memory-existing"],
            "reason": "Link source to related memories.",
        },
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).post(
            "/memory-items/relation-proposals/memory-proposal/apply",
            headers={"X-Synarch-Trace-Id": "trace_memory_relation_apply"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_memory"]["metadata"]["related_memory_ids"] == [
        "memory-existing",
        "memory-related",
    ]
    assert payload["proposal_memory"]["metadata"]["applied"] is True
    assert payload["applied_related_memory_ids"] == [
        "memory-related",
        "memory-existing",
    ]
    assert payload["event"]["type"] == "memory.relation_applied"
    assert memory_client.items_by_id["memory-source"].metadata["related_memory_ids"] == [
        "memory-existing",
        "memory-related",
    ]
    assert [event.type for event in state_client.events] == [
        EventType.memory_relation_applied
    ]


def test_apply_memory_relation_proposal_requires_approval() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-proposal"] = MemoryItem(
        id="memory-proposal",
        scope="project:project_target",
        content="Proposal.",
        status=MemoryStatus.proposed,
        project_id="project_target",
        metadata={
            "kind": "memory_relation_proposal",
            "source_memory_id": "memory-source",
            "related_memory_ids": ["memory-related"],
        },
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).post(
            "/memory-items/relation-proposals/memory-proposal/apply"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"] == "Relation proposal must be approved first"
    assert state_client.events == []


def test_operational_records_are_listed_through_gateway() -> None:
    state_client = FakeStateClient()
    state_client.events.extend(
        [
            EventRecord(
                id="event-model-call",
                type=EventType.model_call_completed,
                target="project_demo",
                trace_id="trace_ops",
            ),
            EventRecord(
                id="event-other",
                type=EventType.task_created,
                target="project_other",
                trace_id="trace_other",
            ),
        ]
    )
    state_client.costs.extend(
        [
            CostRecord(
                id="cost-model-call",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_demo",
                trace_id="trace_ops",
                total_cost=0.0005,
            ),
            CostRecord(
                id="cost-other",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                project_id="project_other",
                trace_id="trace_other",
            ),
        ]
    )
    state_client.audit_logs.extend(
        [
            AuditLogRecord(
                id="audit-model-call",
                actor_type="user",
                actor_id="hugo",
                action="cost.recorded",
                target_type="cost_record",
                target_id="cost-model-call",
                trace_id="trace_ops",
            ),
            AuditLogRecord(
                id="audit-other",
                actor_type="service",
                actor_id="gateway",
                action="event.recorded",
                target_type="event",
                target_id="event-other",
                trace_id="trace_other",
            ),
        ]
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        client = TestClient(app)
        events_response = client.get(
            "/events",
            params={"event_type": "model_call.completed", "trace_id": "trace_ops"},
        )
        costs_response = client.get(
            "/cost-records",
            params={"project_id": "project_demo", "trace_id": "trace_ops"},
        )
        audits_response = client.get(
            "/audit-logs",
            params={"actor_id": "hugo", "trace_id": "trace_ops"},
        )
    finally:
        app.dependency_overrides.clear()

    assert events_response.status_code == 200
    assert [event["id"] for event in events_response.json()] == ["event-model-call"]
    assert costs_response.status_code == 200
    assert [cost["id"] for cost in costs_response.json()] == ["cost-model-call"]
    assert audits_response.status_code == 200
    assert [audit["id"] for audit in audits_response.json()] == ["audit-model-call"]


def test_cost_summary_groups_filtered_records() -> None:
    state_client = FakeStateClient()
    state_client.costs.extend(
        [
            CostRecord(
                id="cost-direction-1",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_demo",
                input_tokens=100,
                output_tokens=50,
                total_cost=0.25,
            ),
            CostRecord(
                id="cost-direction-2",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_demo",
                input_tokens=40,
                output_tokens=20,
                total_cost=0.25,
            ),
            CostRecord(
                id="cost-dev",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-dev",
                project_id="project_demo",
                input_tokens=10,
                output_tokens=5,
                total_cost=0.5,
            ),
            CostRecord(
                id="cost-other-project",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_other",
                input_tokens=999,
                output_tokens=999,
                total_cost=9.0,
            ),
        ]
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).get(
            "/cost-records/summary",
            params={"project_id": "project_demo", "group_by": "agent"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["group_by"] == "agent"
    assert payload["record_count"] == 3
    assert payload["input_tokens"] == 150
    assert payload["output_tokens"] == 75
    assert payload["total_cost"] == 1.0
    assert payload["groups"] == [
        {
            "group_key": "agent-dev",
            "record_count": 1,
            "input_tokens": 10,
            "output_tokens": 5,
            "total_cost": 0.5,
            "currency": "USD",
        },
        {
            "group_key": "agent-direction",
            "record_count": 2,
            "input_tokens": 140,
            "output_tokens": 70,
            "total_cost": 0.5,
            "currency": "USD",
        },
    ]


def test_cost_budget_evaluation_uses_filtered_records() -> None:
    state_client = FakeStateClient()
    state_client.costs.extend(
        [
            CostRecord(
                id="cost-1",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_demo",
                input_tokens=100,
                output_tokens=50,
                total_cost=0.4,
            ),
            CostRecord(
                id="cost-2",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-dev",
                project_id="project_demo",
                input_tokens=200,
                output_tokens=100,
                total_cost=0.7,
            ),
            CostRecord(
                id="cost-other",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                agent_id="agent-direction",
                project_id="project_other",
                input_tokens=999,
                output_tokens=999,
                total_cost=9.0,
            ),
        ]
    )
    app.dependency_overrides[get_state_client] = lambda: state_client

    try:
        response = TestClient(app).get(
            "/cost-records/budget",
            params={"project_id": "project_demo", "budget": "1.0"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["budget"] == 1.0
    assert payload["spent"] == 1.1
    assert payload["remaining"] == -0.1
    assert payload["usage_ratio"] == 1.1
    assert payload["budget_exceeded"] is True
    assert payload["record_count"] == 2
    assert payload["input_tokens"] == 300
    assert payload["output_tokens"] == 150


def test_project_timeline_aggregates_project_records() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    state_client.projects.append(
        ProjectRecord(
            id="project_demo",
            title="Demo project",
            goal="Track project execution.",
            owner_agent_id="agent-direction",
        )
    )
    state_client.tasks.extend(
        [
            TaskRecord(
                id="task-demo",
                project_id="project_demo",
                title="Demo task",
                assigned_agent_id="agent-direction",
                acceptance_criteria=["Timeline contains project records."],
            ),
            TaskRecord(
                id="task-other",
                project_id="project_other",
                title="Other task",
                assigned_agent_id="agent-direction",
                acceptance_criteria=["Other project task is excluded."],
            ),
        ]
    )
    state_client.events.extend(
        [
            EventRecord(
                id="event-project",
                type=EventType.task_created,
                target="project_demo",
                trace_id="trace_demo",
            ),
            EventRecord(
                id="event-task",
                type=EventType.model_call_completed,
                target="task-demo",
                trace_id="trace_demo",
            ),
            EventRecord(
                id="event-other",
                type=EventType.task_created,
                target="project_other",
                trace_id="trace_other",
            ),
        ]
    )
    state_client.costs.extend(
        [
            CostRecord(
                id="cost-demo",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                project_id="project_demo",
                trace_id="trace_demo",
                total_cost=0.25,
            ),
            CostRecord(
                id="cost-other",
                provider_id="provider-openrouter",
                model_id="deepseek/deepseek-v4-flash",
                project_id="project_other",
                trace_id="trace_other",
                total_cost=1.0,
            ),
        ]
    )
    state_client.audit_logs.extend(
        [
            AuditLogRecord(
                id="audit-project",
                actor_type="user",
                actor_id="hugo",
                action="task.created",
                target_type="task",
                target_id="task-demo",
                payload={"project_id": "project_demo"},
                trace_id="trace_demo",
            ),
            AuditLogRecord(
                id="audit-other",
                actor_type="user",
                actor_id="hugo",
                action="task.created",
                target_type="task",
                target_id="task-other",
                payload={"project_id": "project_other"},
                trace_id="trace_other",
            ),
        ]
    )
    memory_client.items_by_id["memory-demo"] = MemoryItem(
        id="memory-demo",
        scope="project:project_demo",
        content="Demo memory.",
        project_id="project_demo",
        status="proposed",
    )
    memory_client.items_by_id["memory-other"] = MemoryItem(
        id="memory-other",
        scope="project:project_other",
        content="Other memory.",
        project_id="project_other",
        status="proposed",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).get("/projects/project_demo/timeline")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "project_demo"
    assert payload["project"]["id"] == "project_demo"
    assert [task["id"] for task in payload["tasks"]] == ["task-demo"]
    assert [event["id"] for event in payload["events"]] == ["event-project", "event-task"]
    assert [cost["id"] for cost in payload["cost_records"]] == ["cost-demo"]
    assert [audit["id"] for audit in payload["audit_logs"]] == ["audit-project"]
    assert [item["id"] for item in payload["memory_items"]] == ["memory-demo"]
    assert payload["total_cost"] == 0.25


def test_update_memory_item_status_records_gateway_event() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-candidate"] = MemoryItem(
        id="memory-candidate",
        scope="project:project_demo",
        content="Candidate memory.",
        status="proposed",
        agent_id="agent-dev",
        project_id="project_demo",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).patch(
            "/memory-items/memory-candidate/status",
            json={"status": "approved"},
            headers={
                "X-Synarch-Actor-Type": "user",
                "X-Synarch-Actor-Id": "hugo",
                "X-Synarch-Trace-Id": "trace_memory_review_test",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert [event.type for event in state_client.events] == ["memory.status_updated"]
    assert state_client.events[0].target == "project_demo"
    assert state_client.events[0].payload == {
        "memory_id": "memory-candidate",
        "scope": "project:project_demo",
        "status": "approved",
        "project_id": "project_demo",
        "agent_id": "agent-dev",
    }
    assert state_client.events[0].trace_id == "trace_memory_review_test"
    assert state_client.headers[-1]["x-synarch-actor-id"] == "hugo"


def test_compact_memory_items_records_gateway_event() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-source-a"] = MemoryItem(
        id="memory-source-a",
        scope="project:project_demo",
        content="First source fact.",
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-source-b"] = MemoryItem(
        id="memory-source-b",
        scope="project:project_demo",
        content="Second source fact.",
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).post(
            "/memory-items/compact",
            json={"scope": "project:project_demo", "project_id": "project_demo"},
            headers={
                "X-Synarch-Actor-Type": "user",
                "X-Synarch-Actor-Id": "hugo",
                "X-Synarch-Trace-Id": "trace_memory_compaction_test",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["compacted_item"]["id"] == "memory-compacted"
    assert payload["source_memory_ids"] == ["memory-source-a", "memory-source-b"]
    assert [event.type for event in state_client.events] == ["memory.compacted"]
    assert state_client.events[0].target == "project_demo"
    assert state_client.events[0].payload == {
        "memory_id": "memory-compacted",
        "scope": "project:project_demo",
        "status": "proposed",
        "project_id": "project_demo",
        "agent_id": None,
        "source_memory_ids": ["memory-source-a", "memory-source-b"],
        "source_count": 2,
        "source_tokens": payload["source_tokens"],
    }
    assert state_client.events[0].trace_id == "trace_memory_compaction_test"
    assert state_client.headers[-1]["x-synarch-actor-id"] == "hugo"


def test_compact_memory_items_if_needed_records_event_when_threshold_exceeded() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-source-a"] = MemoryItem(
        id="memory-source-a",
        scope="project:project_demo",
        content="A" * 80,
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-source-b"] = MemoryItem(
        id="memory-source-b",
        scope="project:project_demo",
        content="B" * 80,
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client
    client = TestClient(app)

    try:
        response = client.post(
            "/memory-items/compact-if-needed",
            json={
                "scope": "project:project_demo",
                "project_id": "project_demo",
                "min_source_tokens": 10,
            },
            headers={
                "X-Synarch-Actor-Type": "user",
                "X-Synarch-Actor-Id": "hugo",
                "X-Synarch-Trace-Id": "trace_memory_policy_test",
            },
        )
        duplicate_response = client.post(
            "/memory-items/compact-if-needed",
            json={
                "scope": "project:project_demo",
                "project_id": "project_demo",
                "min_source_tokens": 10,
            },
            headers={"X-Synarch-Trace-Id": "trace_memory_policy_duplicate_test"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["compaction_needed"] is True
    assert payload["reason"] == "source_tokens_exceed_threshold"
    assert payload["compaction"]["compacted_item"]["id"] == "memory-compacted"
    assert payload["compaction"]["compacted_item"]["metadata"]["source_memory_ids"] == [
        "memory-source-a",
        "memory-source-b",
    ]
    assert payload["source_memory_ids"] == ["memory-source-a", "memory-source-b"]
    assert [event.type for event in state_client.events] == ["memory.compacted"]
    assert state_client.events[0].payload["memory_id"] == "memory-compacted"
    assert state_client.events[0].payload["source_memory_ids"] == [
        "memory-source-a",
        "memory-source-b",
    ]
    assert state_client.events[0].trace_id == "trace_memory_policy_test"

    assert duplicate_response.status_code == 200
    duplicate_payload = duplicate_response.json()
    assert duplicate_payload["compaction_needed"] is False
    assert duplicate_payload["reason"] == "matching_compaction_exists"
    assert duplicate_payload["existing_compacted_item"]["id"] == "memory-compacted"
    assert duplicate_payload["compaction"] is None
    assert [event.type for event in state_client.events] == ["memory.compacted"]


def test_compact_memory_items_if_needed_skips_event_when_under_threshold() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-source-a"] = MemoryItem(
        id="memory-source-a",
        scope="project:project_demo",
        content="Short source fact.",
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).post(
            "/memory-items/compact-if-needed",
            json={
                "scope": "project:project_demo",
                "project_id": "project_demo",
                "min_source_tokens": 100,
            },
            headers={"X-Synarch-Trace-Id": "trace_memory_policy_skip_test"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["compaction_needed"] is False
    assert payload["reason"] == "source_tokens_within_threshold"
    assert payload["compaction"] is None
    assert state_client.events == []


def test_plan_memory_compaction_uses_active_workspace_scopes() -> None:
    state_client = FakeStateClient()
    state_client.workspaces = [
        ProjectWorkspace(
            id="workspace-demo",
            project_id="project_demo",
            name="Demo workspace",
            memory_scope="project:project_demo",
            active=True,
        ),
        ProjectWorkspace(
            id="workspace-archived",
            project_id="project_archived",
            name="Archived workspace",
            memory_scope="project:project_archived",
            active=False,
        ),
    ]
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-source-a"] = MemoryItem(
        id="memory-source-a",
        scope="project:project_demo",
        content="A" * 80,
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-source-b"] = MemoryItem(
        id="memory-source-b",
        scope="project:project_demo",
        content="B" * 80,
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-archived-a"] = MemoryItem(
        id="memory-archived-a",
        scope="project:project_archived",
        content="C" * 80,
        status=MemoryStatus.approved,
        project_id="project_archived",
    )
    memory_client.items_by_id["memory-archived-b"] = MemoryItem(
        id="memory-archived-b",
        scope="project:project_archived",
        content="D" * 80,
        status=MemoryStatus.approved,
        project_id="project_archived",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).post(
            "/memory-items/compaction-plan",
            json={"min_source_tokens": 10},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert memory_client.compaction_plan_requests[0].scopes == ["project:project_demo"]
    payload = response.json()
    assert payload["threshold_tokens"] == 10
    assert payload["inspected_scope_count"] == 1
    assert payload["planned_scope_count"] == 1
    assert payload["items"][0]["scope"] == "project:project_demo"
    assert payload["items"][0]["source_memory_ids"] == [
        "memory-source-a",
        "memory-source-b",
    ]
    assert payload["items"][0]["source_tokens"] == 40


def test_plan_memory_compaction_explicit_empty_scopes_plans_nothing() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-source-a"] = MemoryItem(
        id="memory-source-a",
        scope="project:project_demo",
        content="A" * 80,
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-source-b"] = MemoryItem(
        id="memory-source-b",
        scope="project:project_demo",
        content="B" * 80,
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).post(
            "/memory-items/compaction-plan",
            json={"scopes": [], "min_source_tokens": 10},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert memory_client.compaction_plan_requests[0].scopes == []
    payload = response.json()
    assert payload["inspected_scope_count"] == 0
    assert payload["planned_scope_count"] == 0
    assert payload["items"] == []


def test_plan_memory_compaction_without_active_workspaces_plans_nothing() -> None:
    state_client = FakeStateClient()
    memory_client = FakeMemoryClient()
    memory_client.items_by_id["memory-source-a"] = MemoryItem(
        id="memory-source-a",
        scope="project:project_demo",
        content="A" * 80,
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    memory_client.items_by_id["memory-source-b"] = MemoryItem(
        id="memory-source-b",
        scope="project:project_demo",
        content="B" * 80,
        status=MemoryStatus.approved,
        project_id="project_demo",
    )
    app.dependency_overrides[get_state_client] = lambda: state_client
    app.dependency_overrides[get_memory_client] = lambda: memory_client

    try:
        response = TestClient(app).post(
            "/memory-items/compaction-plan",
            json={"min_source_tokens": 10},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert memory_client.compaction_plan_requests[0].scopes == []
    payload = response.json()
    assert payload["inspected_scope_count"] == 0
    assert payload["planned_scope_count"] == 0
    assert payload["items"] == []


def test_run_next_task_records_failed_model_call_when_runtime_is_unavailable() -> None:
    state_client = FakeStateClient()
    state_client.tasks.append(
        TaskRecord(
            project_id="project_demo",
            title="Ready task",
            assigned_agent_id="agent-dev",
            acceptance_criteria=["Ready task can produce a recorded result."],
        )
    )
    runner = TaskRunner(
        state=state_client,
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=FailingAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post(
            "/tasks/run-next",
            headers={"X-Synarch-Trace-Id": "trace_gateway_runner_failure_test"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["status"] == "failed"
    assert payload["agent_result"]["status"] == "failed"
    assert payload["cost_records"] == []
    assert "runtime offline" in payload["agent_result"]["summary"]
    assert [event.type for event in state_client.events] == [
        "model_call.started",
        "model_call.failed",
    ]
    assert [event["type"] for event in payload["model_call_events"]] == [
        "model_call.started",
        "model_call.failed",
    ]
    assert state_client.events[1].trace_id == "trace_gateway_runner_failure_test"


def test_run_next_task_returns_404_when_no_task_is_ready() -> None:
    runner = TaskRunner(
        state=FakeStateClient(),
        control_plane=FakeControlPlaneClient(),
        memory=FakeMemoryClient(),
        runtime=FakeAgentRuntimeClient(),
    )
    app.dependency_overrides[get_task_runner] = lambda: runner

    try:
        response = TestClient(app).post("/tasks/run-next")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "No queued task is ready to run"
