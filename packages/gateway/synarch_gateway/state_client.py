from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import httpx

from synarch_models import (
    AgentLifecycleRequest,
    AgentProjectAssignment,
    AgentResult,
    AuditLogRecord,
    ConnectorConnectionCallbackRequest,
    ConnectorConnectionRecord,
    ConnectorConnectionRequest,
    ConnectorConnectionResult,
    ConnectorJobMutationResult,
    ConnectorJobRecord,
    ConnectorJobResumeRequest,
    ConnectorJobRunRequest,
    ConnectorJobRunResult,
    ConnectorJobStopRequest,
    CostRecord,
    CredentialAccessDecision,
    CredentialAccessRequest,
    CredentialGrant,
    CredentialGrantApplication,
    CredentialGrantApplicationRequest,
    EventRecord,
    HumanAssistanceRequest,
    HumanAssistanceResolution,
    ModelDefinition,
    ModelPolicy,
    ModelProviderConfig,
    ProjectComplexityAssessment,
    ProjectRecord,
    ProjectSplitApplication,
    ProjectWorkspace,
    ServiceDefinition,
    TaskLeaseRecoveryResult,
    TaskRecord,
    TaskReviewDecision,
    TaskReviewResult,
    WorkerHeartbeatRecord,
)


class StateServiceUnavailable(Exception):
    pass


class StateServiceRequestError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class StateClient(Protocol):
    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord: ...

    def create_task(
        self,
        task: TaskRecord,
        *,
        headers: dict[str, str],
    ) -> TaskRecord: ...

    def create_project_workspace(
        self,
        workspace: ProjectWorkspace,
        *,
        headers: dict[str, str],
    ) -> ProjectWorkspace: ...

    def list_project_workspaces(
        self,
        *,
        project_id: str | None = None,
        active: bool | None = None,
    ) -> list[ProjectWorkspace]: ...

    def create_agent_project_assignment(
        self,
        assignment: AgentProjectAssignment,
        *,
        headers: dict[str, str],
    ) -> AgentProjectAssignment: ...

    def create_event(
        self,
        event: EventRecord,
        *,
        headers: dict[str, str],
    ) -> EventRecord: ...

    def list_events(
        self,
        *,
        event_type: str | None = None,
        trace_id: str | None = None,
    ) -> list[EventRecord]: ...

    def list_services(
        self,
        *,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[ServiceDefinition]: ...

    def get_model_provider(self, provider_id: str) -> ModelProviderConfig: ...

    def get_model_definition(self, model_id: str) -> ModelDefinition: ...

    def get_model_policy(self, policy_id: str) -> ModelPolicy: ...

    def assess_project_complexity(
        self,
        project_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectComplexityAssessment: ...

    def apply_project_split(
        self,
        split_request_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectSplitApplication: ...

    def get_project(self, project_id: str) -> ProjectRecord: ...

    def list_projects(self) -> list[ProjectRecord]: ...

    def get_task(self, task_id: str) -> TaskRecord: ...

    def list_tasks(self, *, project_id: str | None = None) -> list[TaskRecord]: ...

    def list_task_review_queue(self, *, project_id: str | None = None) -> list[TaskRecord]: ...

    def apply_task_review_decision(
        self,
        task_id: str,
        decision: TaskReviewDecision,
        *,
        headers: dict[str, str],
    ) -> TaskReviewResult: ...

    def recover_expired_task_leases(
        self,
        *,
        headers: dict[str, str],
    ) -> TaskLeaseRecoveryResult: ...

    def start_task(
        self,
        task_id: str,
        *,
        headers: dict[str, str],
    ) -> TaskRecord: ...

    def record_task_result(
        self,
        task_id: str,
        result: AgentResult,
        *,
        headers: dict[str, str],
    ) -> TaskRecord: ...

    def create_cost_record(
        self,
        cost: CostRecord,
        *,
        headers: dict[str, str],
    ) -> CostRecord: ...

    def list_cost_records(
        self,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[CostRecord]: ...

    def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[AuditLogRecord]: ...

    def create_audit_log(
        self,
        audit: AuditLogRecord,
        *,
        headers: dict[str, str],
    ) -> AuditLogRecord: ...

    def create_agent_lifecycle_request(
        self,
        lifecycle_request: AgentLifecycleRequest,
        *,
        headers: dict[str, str],
    ) -> AgentLifecycleRequest: ...

    def create_credential_access_request(
        self,
        access_request: CredentialAccessRequest,
        *,
        headers: dict[str, str],
    ) -> CredentialAccessRequest: ...

    def create_human_assistance_request(
        self,
        assistance_request: HumanAssistanceRequest,
        *,
        headers: dict[str, str],
    ) -> HumanAssistanceRequest: ...

    def list_human_assistance_requests(
        self,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
    ) -> list[HumanAssistanceRequest]: ...

    def get_human_assistance_request(self, request_id: str) -> HumanAssistanceRequest: ...

    def resolve_human_assistance_request(
        self,
        request_id: str,
        resolution: HumanAssistanceResolution,
        *,
        headers: dict[str, str],
    ) -> HumanAssistanceResolution: ...

    def list_credential_access_requests(
        self,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> list[CredentialAccessRequest]: ...

    def decide_credential_access_request(
        self,
        request_id: str,
        decision: CredentialAccessDecision,
        *,
        headers: dict[str, str],
    ) -> CredentialAccessDecision: ...

    def apply_credential_access_grant(
        self,
        request_id: str,
        application: CredentialGrantApplicationRequest,
        *,
        headers: dict[str, str],
    ) -> CredentialGrantApplication: ...

    def list_credential_grants(
        self,
        *,
        request_id: str | None = None,
        service_id: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        active: bool | None = None,
    ) -> list[CredentialGrant]: ...

    def create_connector_connection(
        self,
        connection: ConnectorConnectionRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorConnectionResult: ...

    def complete_connector_connection_oauth(
        self,
        connection_id: str,
        callback: ConnectorConnectionCallbackRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorConnectionResult: ...

    def list_connector_connections(
        self,
        *,
        service_id: str | None = None,
        status: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[ConnectorConnectionRecord]: ...

    def get_connector_job(self, job_id: str) -> ConnectorJobRecord: ...

    def list_connector_jobs(
        self,
        *,
        service_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        owner_agent_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        last_run_status: str | None = None,
        due_before: datetime | None = None,
    ) -> list[ConnectorJobRecord]: ...

    def create_connector_job(
        self,
        job: ConnectorJobRecord,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobMutationResult: ...

    def record_connector_job_run(
        self,
        job_id: str,
        run_request: ConnectorJobRunRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobRunResult: ...

    def stop_connector_job(
        self,
        job_id: str,
        stop_request: ConnectorJobStopRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobMutationResult: ...

    def resume_connector_job(
        self,
        job_id: str,
        resume_request: ConnectorJobResumeRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobMutationResult: ...

    def list_worker_heartbeats(
        self,
        *,
        worker_kind: str | None = None,
        target: str | None = None,
    ) -> list[WorkerHeartbeatRecord]: ...


@dataclass(frozen=True)
class HttpStateClient:
    base_url: str
    timeout_seconds: float = 5.0

    def create_project(
        self,
        project: ProjectRecord,
        *,
        headers: dict[str, str],
    ) -> ProjectRecord:
        response = self._post("/projects", project.model_dump(mode="json"), headers)
        return ProjectRecord.model_validate(response.json())

    def create_task(
        self,
        task: TaskRecord,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        response = self._post("/tasks", task.model_dump(mode="json"), headers)
        return TaskRecord.model_validate(response.json())

    def create_project_workspace(
        self,
        workspace: ProjectWorkspace,
        *,
        headers: dict[str, str],
    ) -> ProjectWorkspace:
        response = self._post("/project-workspaces", workspace.model_dump(mode="json"), headers)
        return ProjectWorkspace.model_validate(response.json())

    def list_project_workspaces(
        self,
        *,
        project_id: str | None = None,
        active: bool | None = None,
    ) -> list[ProjectWorkspace]:
        response = self._get(
            "/project-workspaces",
            params=compact_params(
                project_id=project_id,
                active=str(active).lower() if active is not None else None,
            ),
        )
        return [
            ProjectWorkspace.model_validate(workspace)
            for workspace in response.json()
        ]

    def create_agent_project_assignment(
        self,
        assignment: AgentProjectAssignment,
        *,
        headers: dict[str, str],
    ) -> AgentProjectAssignment:
        response = self._post(
            "/agent-project-assignments",
            assignment.model_dump(mode="json"),
            headers,
        )
        return AgentProjectAssignment.model_validate(response.json())

    def create_event(
        self,
        event: EventRecord,
        *,
        headers: dict[str, str],
    ) -> EventRecord:
        response = self._post("/events", event.model_dump(mode="json"), headers)
        return EventRecord.model_validate(response.json())

    def list_events(
        self,
        *,
        event_type: str | None = None,
        trace_id: str | None = None,
    ) -> list[EventRecord]:
        response = self._get(
            "/events",
            params=compact_params(event_type=event_type, trace_id=trace_id),
        )
        return [EventRecord.model_validate(event) for event in response.json()]

    def list_services(
        self,
        *,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[ServiceDefinition]:
        params: dict[str, str] = {}
        if kind is not None:
            params["kind"] = kind
        if enabled is not None:
            params["enabled"] = str(enabled).lower()
        response = self._get("/services", params=params)
        return [ServiceDefinition.model_validate(service) for service in response.json()]

    def get_model_provider(self, provider_id: str) -> ModelProviderConfig:
        response = self._get(f"/model-providers/{provider_id}")
        return ModelProviderConfig.model_validate(response.json())

    def get_model_definition(self, model_id: str) -> ModelDefinition:
        response = self._get(f"/model-definitions/{model_id}")
        return ModelDefinition.model_validate(response.json())

    def get_model_policy(self, policy_id: str) -> ModelPolicy:
        response = self._get(f"/model-policies/{policy_id}")
        return ModelPolicy.model_validate(response.json())

    def assess_project_complexity(
        self,
        project_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectComplexityAssessment:
        response = self._post(f"/projects/{project_id}/complexity-assessments", None, headers)
        return ProjectComplexityAssessment.model_validate(response.json())

    def apply_project_split(
        self,
        split_request_id: str,
        *,
        headers: dict[str, str],
    ) -> ProjectSplitApplication:
        response = self._post(f"/project-split-requests/{split_request_id}/apply", None, headers)
        return ProjectSplitApplication.model_validate(response.json())

    def get_project(self, project_id: str) -> ProjectRecord:
        response = self._get(f"/projects/{project_id}")
        return ProjectRecord.model_validate(response.json())

    def list_projects(self) -> list[ProjectRecord]:
        response = self._get("/projects")
        return [ProjectRecord.model_validate(project) for project in response.json()]

    def get_task(self, task_id: str) -> TaskRecord:
        response = self._get(f"/tasks/{task_id}")
        return TaskRecord.model_validate(response.json())

    def list_tasks(self, *, project_id: str | None = None) -> list[TaskRecord]:
        response = self._get("/tasks", params=compact_params(project_id=project_id))
        return [TaskRecord.model_validate(task) for task in response.json()]

    def list_task_review_queue(self, *, project_id: str | None = None) -> list[TaskRecord]:
        response = self._get(
            "/tasks/review-queue",
            params=compact_params(project_id=project_id),
        )
        return [TaskRecord.model_validate(task) for task in response.json()]

    def apply_task_review_decision(
        self,
        task_id: str,
        decision: TaskReviewDecision,
        *,
        headers: dict[str, str],
    ) -> TaskReviewResult:
        response = self._post(
            f"/tasks/{task_id}/review-decisions",
            decision.model_dump(mode="json"),
            headers,
        )
        return TaskReviewResult.model_validate(response.json())

    def recover_expired_task_leases(
        self,
        *,
        headers: dict[str, str],
    ) -> TaskLeaseRecoveryResult:
        response = self._post("/tasks/recover-expired-leases", None, headers)
        return TaskLeaseRecoveryResult.model_validate(response.json())

    def start_task(
        self,
        task_id: str,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        response = self._post(f"/tasks/{task_id}/start", None, headers)
        return TaskRecord.model_validate(response.json())

    def record_task_result(
        self,
        task_id: str,
        result: AgentResult,
        *,
        headers: dict[str, str],
    ) -> TaskRecord:
        response = self._post(
            f"/tasks/{task_id}/results",
            result.model_dump(mode="json"),
            headers,
        )
        return TaskRecord.model_validate(response.json())

    def create_cost_record(
        self,
        cost: CostRecord,
        *,
        headers: dict[str, str],
    ) -> CostRecord:
        response = self._post("/cost-records", cost.model_dump(mode="json"), headers)
        return CostRecord.model_validate(response.json())

    def list_cost_records(
        self,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[CostRecord]:
        response = self._get(
            "/cost-records",
            params=compact_params(
                project_id=project_id,
                agent_id=agent_id,
                provider_id=provider_id,
                model_id=model_id,
                trace_id=trace_id,
            ),
        )
        return [CostRecord.model_validate(cost) for cost in response.json()]

    def list_audit_logs(
        self,
        *,
        actor_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[AuditLogRecord]:
        response = self._get(
            "/audit-logs",
            params=compact_params(
                actor_id=actor_id,
                target_type=target_type,
                target_id=target_id,
                trace_id=trace_id,
            ),
        )
        return [AuditLogRecord.model_validate(audit) for audit in response.json()]

    def create_audit_log(
        self,
        audit: AuditLogRecord,
        *,
        headers: dict[str, str],
    ) -> AuditLogRecord:
        response = self._post("/audit-logs", audit.model_dump(mode="json"), headers)
        return AuditLogRecord.model_validate(response.json())

    def create_agent_lifecycle_request(
        self,
        lifecycle_request: AgentLifecycleRequest,
        *,
        headers: dict[str, str],
    ) -> AgentLifecycleRequest:
        response = self._post(
            "/agent-lifecycle-requests",
            lifecycle_request.model_dump(mode="json"),
            headers,
        )
        return AgentLifecycleRequest.model_validate(response.json())

    def create_credential_access_request(
        self,
        access_request: CredentialAccessRequest,
        *,
        headers: dict[str, str],
    ) -> CredentialAccessRequest:
        response = self._post(
            "/credential-access-requests",
            access_request.model_dump(mode="json"),
            headers,
        )
        return CredentialAccessRequest.model_validate(response.json())

    def create_human_assistance_request(
        self,
        assistance_request: HumanAssistanceRequest,
        *,
        headers: dict[str, str],
    ) -> HumanAssistanceRequest:
        response = self._post(
            "/human-assistance-requests",
            assistance_request.model_dump(mode="json"),
            headers,
        )
        return HumanAssistanceRequest.model_validate(response.json())

    def list_human_assistance_requests(
        self,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
    ) -> list[HumanAssistanceRequest]:
        response = self._get(
            "/human-assistance-requests",
            params=compact_params(
                project_id=project_id,
                task_id=task_id,
                agent_id=agent_id,
                kind=kind,
                status=status,
            ),
        )
        return [
            HumanAssistanceRequest.model_validate(assistance_request)
            for assistance_request in response.json()
        ]

    def get_human_assistance_request(self, request_id: str) -> HumanAssistanceRequest:
        response = self._get(f"/human-assistance-requests/{request_id}")
        return HumanAssistanceRequest.model_validate(response.json())

    def resolve_human_assistance_request(
        self,
        request_id: str,
        resolution: HumanAssistanceResolution,
        *,
        headers: dict[str, str],
    ) -> HumanAssistanceResolution:
        response = self._post(
            f"/human-assistance-requests/{request_id}/resolutions",
            resolution.model_dump(mode="json"),
            headers,
        )
        return HumanAssistanceResolution.model_validate(response.json())

    def list_credential_access_requests(
        self,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> list[CredentialAccessRequest]:
        response = self._get(
            "/credential-access-requests",
            params=compact_params(
                project_id=project_id,
                task_id=task_id,
                agent_id=agent_id,
                status=status,
            ),
        )
        return [
            CredentialAccessRequest.model_validate(access_request)
            for access_request in response.json()
        ]

    def decide_credential_access_request(
        self,
        request_id: str,
        decision: CredentialAccessDecision,
        *,
        headers: dict[str, str],
    ) -> CredentialAccessDecision:
        response = self._post(
            f"/credential-access-requests/{request_id}/decisions",
            decision.model_dump(mode="json"),
            headers,
        )
        return CredentialAccessDecision.model_validate(response.json())

    def apply_credential_access_grant(
        self,
        request_id: str,
        application: CredentialGrantApplicationRequest,
        *,
        headers: dict[str, str],
    ) -> CredentialGrantApplication:
        response = self._post(
            f"/credential-access-requests/{request_id}/grant-applications",
            application.model_dump(mode="json"),
            headers,
        )
        return CredentialGrantApplication.model_validate(response.json())

    def list_credential_grants(
        self,
        *,
        request_id: str | None = None,
        service_id: str | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        active: bool | None = None,
    ) -> list[CredentialGrant]:
        params: dict[str, str] = {}
        if request_id is not None:
            params["request_id"] = request_id
        if service_id is not None:
            params["service_id"] = service_id
        if agent_id is not None:
            params["agent_id"] = agent_id
        if project_id is not None:
            params["project_id"] = project_id
        if active is not None:
            params["active"] = str(active).lower()
        response = self._get("/credential-grants", params=params)
        return [CredentialGrant.model_validate(grant) for grant in response.json()]

    def create_connector_connection(
        self,
        connection: ConnectorConnectionRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorConnectionResult:
        response = self._post(
            "/connector-connections",
            connection.model_dump(mode="json"),
            headers,
        )
        return ConnectorConnectionResult.model_validate(response.json())

    def complete_connector_connection_oauth(
        self,
        connection_id: str,
        callback: ConnectorConnectionCallbackRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorConnectionResult:
        response = self._post(
            f"/connector-connections/{connection_id}/oauth-callback",
            callback.model_dump(mode="json"),
            headers,
        )
        return ConnectorConnectionResult.model_validate(response.json())

    def list_connector_connections(
        self,
        *,
        service_id: str | None = None,
        status: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[ConnectorConnectionRecord]:
        params = compact_params(
            service_id=service_id,
            status=status,
            project_id=project_id,
            agent_id=agent_id,
        )
        response = self._get("/connector-connections", params=params)
        return [
            ConnectorConnectionRecord.model_validate(connection)
            for connection in response.json()
        ]

    def get_connector_job(self, job_id: str) -> ConnectorJobRecord:
        response = self._get(f"/connector-jobs/{job_id}")
        return ConnectorJobRecord.model_validate(response.json())

    def list_connector_jobs(
        self,
        *,
        service_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        owner_agent_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        last_run_status: str | None = None,
        due_before: datetime | None = None,
    ) -> list[ConnectorJobRecord]:
        response = self._get(
            "/connector-jobs",
            params=compact_params(
                service_id=service_id,
                project_id=project_id,
                task_id=task_id,
                owner_agent_id=owner_agent_id,
                kind=kind,
                status=status,
                last_run_status=last_run_status,
                due_before=due_before.isoformat() if due_before is not None else None,
            ),
        )
        return [ConnectorJobRecord.model_validate(job) for job in response.json()]

    def create_connector_job(
        self,
        job: ConnectorJobRecord,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobMutationResult:
        response = self._post(
            "/connector-jobs",
            job.model_dump(mode="json"),
            headers,
        )
        return ConnectorJobMutationResult.model_validate(response.json())

    def record_connector_job_run(
        self,
        job_id: str,
        run_request: ConnectorJobRunRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobRunResult:
        response = self._post(
            f"/connector-jobs/{job_id}/runs",
            run_request.model_dump(mode="json"),
            headers,
        )
        return ConnectorJobRunResult.model_validate(response.json())

    def stop_connector_job(
        self,
        job_id: str,
        stop_request: ConnectorJobStopRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobMutationResult:
        response = self._post(
            f"/connector-jobs/{job_id}/stop",
            stop_request.model_dump(mode="json"),
            headers,
        )
        return ConnectorJobMutationResult.model_validate(response.json())

    def resume_connector_job(
        self,
        job_id: str,
        resume_request: ConnectorJobResumeRequest,
        *,
        headers: dict[str, str],
    ) -> ConnectorJobMutationResult:
        response = self._post(
            f"/connector-jobs/{job_id}/resume",
            resume_request.model_dump(mode="json"),
            headers,
        )
        return ConnectorJobMutationResult.model_validate(response.json())

    def list_worker_heartbeats(
        self,
        *,
        worker_kind: str | None = None,
        target: str | None = None,
    ) -> list[WorkerHeartbeatRecord]:
        response = self._get(
            "/worker-heartbeats",
            params=compact_params(worker_kind=worker_kind, target=target),
        )
        return [
            WorkerHeartbeatRecord.model_validate(heartbeat)
            for heartbeat in response.json()
        ]

    def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = httpx.get(
                f"{self.base_url.rstrip('/')}{path}",
                params=params,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise StateServiceUnavailable(str(error)) from error

        if 400 <= response.status_code < 500:
            raise StateServiceRequestError(response.status_code, response_detail(response))

        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise StateServiceUnavailable(str(error)) from error

        return response

    def _post(
        self,
        path: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}{path}",
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise StateServiceUnavailable(str(error)) from error

        if 400 <= response.status_code < 500:
            raise StateServiceRequestError(response.status_code, response_detail(response))

        try:
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise StateServiceUnavailable(str(error)) from error

        return response


def response_detail(response: httpx.Response) -> Any:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if isinstance(body, dict):
        return body.get("detail", body)
    return body


def compact_params(**values: str | None) -> dict[str, str]:
    return {key: value for key, value in values.items() if value is not None}
