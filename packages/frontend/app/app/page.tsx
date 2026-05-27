"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Check,
  CheckCircle2,
  CircleDot,
  ExternalLink,
  KeyRound,
  ListChecks,
  PlugZap,
  Play,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Workflow,
  X
} from "lucide-react";
import { type FormEvent, type ReactNode, useMemo, useState } from "react";

import {
  applyCredentialAccessGrant,
  connectConnectorService,
  decideCredentialAccessRequest,
  disableConnectorConnection,
  getSystemReadiness,
  listCredentialAccessRequests,
  listConnectorConnections,
  listHumanAssistanceRequests,
  listOperatorActions,
  listProjectBriefs,
  reencryptSecretVault,
  resolveHumanAssistanceRequest,
  runReadyTasks,
  submitGoal,
  type ConnectorConnectionMode,
  type ConnectorConnectionRecord,
  type CredentialAccessRequest,
  type GoalPriority,
  type HumanAssistanceRequest,
  type OperatorAction,
  type ProjectBrief,
  type SystemReadinessItem,
  type SystemReadinessStatus
} from "../../lib/gateway-api";
import {
  createWorkQueueItem,
  listProjects,
  listServices,
  listWorkerHeartbeats,
  listWorkQueueItems,
  listWorkQueueSummary,
  reviewWorkQueueItem,
  type ProjectRecord,
  type ServiceDefinition,
  type WorkerHeartbeatRecord,
  type WorkQueueItem,
  type WorkQueueSummary
} from "../../lib/state-service-api";

const priorityOptions: GoalPriority[] = ["medium", "high", "critical", "low"];
const connectorModes: ConnectorConnectionMode[] = ["api_key", "no_key", "oauth"];
type WorkQueueAction = "project_reminder" | "log";

const readinessClass: Record<SystemReadinessStatus, string> = {
  ready: "bg-ok-soft text-ok ring-ok/15",
  warning: "bg-warn-soft text-warn ring-warn/15",
  blocked: "bg-risk-soft text-risk ring-risk/15"
};

const projectStatusClass: Record<string, string> = {
  completed: "bg-ok-soft text-ok ring-ok/15",
  running: "bg-info-soft text-info ring-info/15",
  queued: "bg-accent-soft text-accent ring-accent/15",
  needs_review: "bg-warn-soft text-warn ring-warn/15",
  blocked: "bg-risk-soft text-risk ring-risk/15",
  failed: "bg-risk-soft text-risk ring-risk/15",
  dead_lettered: "bg-risk-soft text-risk ring-risk/15",
  draft: "bg-slate-100 text-muted ring-border"
};

function statusClass(status: string): string {
  return projectStatusClass[status] ?? "bg-slate-100 text-muted ring-border";
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "n/a";
  }
  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date(value));
}

function connectionByService(
  connections: ConnectorConnectionRecord[]
): Map<string, ConnectorConnectionRecord> {
  return new Map(
    [...connections]
      .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
      .map((connection) => [connection.service_id, connection])
  );
}

function isConnectableService(service: ServiceDefinition): boolean {
  return service.enabled && ["external", "ai_provider", "tool_provider"].includes(service.kind);
}

function metadataBoolean(service: ServiceDefinition | null, key: string): boolean {
  return service?.metadata[key] === true;
}

function metadataString(service: ServiceDefinition | null, key: string): string | null {
  const value = service?.metadata[key];
  return typeof value === "string" ? value : null;
}

function hasConnectorAuthorizationLink(service: ServiceDefinition): boolean {
  return (
    metadataString(service, "oauth_authorization_url") !== null ||
    metadataString(service, "connect_url") !== null ||
    metadataString(service, "manual_connection_url") !== null
  );
}

function connectorModesForService(service: ServiceDefinition): ConnectorConnectionMode[] {
  const modes: ConnectorConnectionMode[] = [];
  if (metadataBoolean(service, "requires_api_key") || service.credential_scopes.length > 0) {
    modes.push("api_key");
  }
  if (!metadataBoolean(service, "requires_api_key")) {
    modes.push("no_key");
  }
  if (hasConnectorAuthorizationLink(service)) {
    modes.push("oauth");
  }
  return modes.length > 0 ? modes : ["no_key"];
}

function selectedScopeSet(scopes: string[]): Set<string> {
  return new Set(scopes.filter(Boolean));
}

function evidenceBoolean(item: SystemReadinessItem, key: string): boolean {
  return item.evidence[key] === true;
}

function evidenceNumber(item: SystemReadinessItem, key: string): number {
  const value = item.evidence[key];
  return typeof value === "number" ? value : 0;
}

function canReencryptSecretVault(item: SystemReadinessItem): boolean {
  return (
    item.id === "secret_vault" &&
    evidenceBoolean(item, "encryption_enabled") &&
    evidenceNumber(item, "plaintext_secret_count") > 0
  );
}

export default function SynarchAppPage() {
  const queryClient = useQueryClient();
  const [goal, setGoal] = useState("");
  const [priority, setPriority] = useState<GoalPriority>("medium");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
  const [connectorMode, setConnectorMode] = useState<ConnectorConnectionMode>("api_key");
  const [lastConnectorConnection, setLastConnectorConnection] =
    useState<ConnectorConnectionRecord | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [workQueueName, setWorkQueueName] = useState("reminders");
  const [workQueueAction, setWorkQueueAction] = useState<WorkQueueAction>("project_reminder");
  const [workQueueMessage, setWorkQueueMessage] = useState("");
  const [workQueueRunAfter, setWorkQueueRunAfter] = useState("");
  const [humanResponsesById, setHumanResponsesById] = useState<Record<string, string>>({});
  const [scopeSelectionsByService, setScopeSelectionsByService] = useState<
    Record<string, string[]>
  >({});

  const projectsQuery = useQuery({ queryKey: ["app-projects"], queryFn: listProjects });
  const servicesQuery = useQuery({ queryKey: ["app-services"], queryFn: listServices });
  const connectionsQuery = useQuery({
    queryKey: ["app-connector-connections"],
    queryFn: listConnectorConnections
  });
  const readinessQuery = useQuery({
    queryKey: ["app-readiness"],
    queryFn: getSystemReadiness
  });
  const workQueueQuery = useQuery({
    queryKey: ["app-work-queue", workQueueName],
    queryFn: () => listWorkQueueItems(workQueueName.trim() || undefined),
    refetchInterval: 15_000
  });
  const workQueueSummaryQuery = useQuery({
    queryKey: ["app-work-queue-summary"],
    queryFn: listWorkQueueSummary,
    refetchInterval: 15_000
  });
  const workerHeartbeatsQuery = useQuery({
    queryKey: ["app-worker-heartbeats"],
    queryFn: listWorkerHeartbeats,
    refetchInterval: 15_000
  });
  const credentialRequestsQuery = useQuery({
    queryKey: ["app-credential-access-requests"],
    queryFn: listCredentialAccessRequests,
    refetchInterval: 15_000
  });
  const humanAssistanceQuery = useQuery({
    queryKey: ["app-human-assistance-requests"],
    queryFn: listHumanAssistanceRequests,
    refetchInterval: 15_000
  });

  const selectedProject =
    projectsQuery.data?.find((project) => project.id === selectedProjectId) ??
    projectsQuery.data?.[0] ??
    null;
  const effectiveProjectId = selectedProject?.id ?? null;

  const briefsQuery = useQuery({
    queryKey: ["app-project-briefs", effectiveProjectId],
    queryFn: () => listProjectBriefs(effectiveProjectId ?? undefined),
    enabled: effectiveProjectId !== null,
    refetchInterval: 15_000
  });
  const actionsQuery = useQuery({
    queryKey: ["app-operator-actions", effectiveProjectId],
    queryFn: () => listOperatorActions(effectiveProjectId ?? undefined),
    refetchInterval: 15_000
  });

  const connectorServices = useMemo(
    () => (servicesQuery.data ?? []).filter(isConnectableService),
    [servicesQuery.data]
  );
  const selectedService =
    connectorServices.find((service) => service.id === selectedServiceId) ??
    connectorServices[0] ??
    null;
  const serviceScopes = selectedService?.credential_scopes ?? [];
  const selectedScopes = selectedService
    ? (scopeSelectionsByService[selectedService.id] ?? serviceScopes)
    : [];
  const selectedScopesSet = selectedScopeSet(selectedScopes);
  const connectionsByService = connectionByService(connectionsQuery.data ?? []);
  const selectedConnection = selectedService
    ? connectionsByService.get(selectedService.id) ?? null
    : null;
  const activeConnection =
    selectedService && lastConnectorConnection?.service_id === selectedService.id
      ? lastConnectorConnection
      : selectedConnection;
  const availableConnectorModes = selectedService
    ? connectorModesForService(selectedService)
    : connectorModes;
  const effectiveConnectorMode = availableConnectorModes.includes(connectorMode)
    ? connectorMode
    : (availableConnectorModes[0] ?? "no_key");
  const selectedBrief = briefsQuery.data?.[0] ?? null;
  const servicesById = useMemo(
    () => new Map((servicesQuery.data ?? []).map((service) => [service.id, service])),
    [servicesQuery.data]
  );
  const visibleCredentialRequests = useMemo(
    () => visibleCredentialAccessRequests(credentialRequestsQuery.data ?? [], effectiveProjectId),
    [credentialRequestsQuery.data, effectiveProjectId]
  );
  const visibleHumanRequests = useMemo(
    () => visibleHumanAssistanceRequests(humanAssistanceQuery.data ?? [], effectiveProjectId),
    [humanAssistanceQuery.data, effectiveProjectId]
  );
  const canSubmitWorkQueue =
    workQueueName.trim().length > 0 &&
    (workQueueAction === "log" ||
      (effectiveProjectId !== null && workQueueMessage.trim().length > 0));

  const invalidateOperatorState = () => {
    void queryClient.invalidateQueries({ queryKey: ["app-credential-access-requests"] });
    void queryClient.invalidateQueries({ queryKey: ["app-human-assistance-requests"] });
    void queryClient.invalidateQueries({ queryKey: ["app-operator-actions"] });
    void queryClient.invalidateQueries({ queryKey: ["app-readiness"] });
    void queryClient.invalidateQueries({ queryKey: ["app-project-briefs"] });
    void queryClient.invalidateQueries({ queryKey: ["app-projects"] });
  };

  const submitGoalMutation = useMutation({
    mutationFn: () =>
      submitGoal({
        goal,
        priority,
        requester: "local-user",
        constraints: [
          "Découper l'objectif en étapes vérifiables.",
          "Demander une action humaine pour captcha, accès, choix critique ou document ambigu."
        ],
        context: { source: "synarch_app" }
      }),
    onSuccess: (result) => {
      setGoal("");
      setSelectedProjectId(result.project.id);
      void queryClient.invalidateQueries({ queryKey: ["app-projects"] });
      void queryClient.invalidateQueries({ queryKey: ["app-project-briefs"] });
      void queryClient.invalidateQueries({ queryKey: ["app-operator-actions"] });
    }
  });

  const runProjectMutation = useMutation({
    mutationFn: () =>
      runReadyTasks({
        projectId: effectiveProjectId ?? "",
        maxTasks: 3
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["app-projects"] });
      void queryClient.invalidateQueries({ queryKey: ["app-project-briefs", effectiveProjectId] });
      void queryClient.invalidateQueries({ queryKey: ["app-operator-actions", effectiveProjectId] });
    }
  });

  const connectMutation = useMutation({
    mutationFn: () => {
      if (!selectedService) {
        throw new Error("Aucun service sélectionné.");
      }
      return connectConnectorService({
        serviceId: selectedService.id,
        request: {
          mode: effectiveConnectorMode,
          api_key: effectiveConnectorMode === "api_key" ? apiKey : undefined,
          credential_scopes: selectedScopes,
          project_id: effectiveProjectId,
          rationale: "Connector configured from Synarch app."
        }
      });
    },
    onSuccess: (result) => {
      setLastConnectorConnection(result.connection);
      setApiKey("");
      void queryClient.invalidateQueries({ queryKey: ["app-services"] });
      void queryClient.invalidateQueries({ queryKey: ["app-connector-connections"] });
      void queryClient.invalidateQueries({ queryKey: ["app-readiness"] });
    }
  });

  const disableConnectorMutation = useMutation({
    mutationFn: () => {
      if (!activeConnection) {
        throw new Error("Aucune connexion sélectionnée.");
      }
      return disableConnectorConnection({
        connectionId: activeConnection.id,
        request: {
          rationale: "Connector disabled from Synarch app."
        }
      });
    },
    onSuccess: (result) => {
      setLastConnectorConnection(result.connection);
      void queryClient.invalidateQueries({ queryKey: ["app-services"] });
      void queryClient.invalidateQueries({ queryKey: ["app-connector-connections"] });
      void queryClient.invalidateQueries({ queryKey: ["app-readiness"] });
    }
  });

  const createWorkQueueMutation = useMutation({
    mutationFn: () => {
      if (workQueueAction === "project_reminder") {
        if (!effectiveProjectId) {
          throw new Error("Aucun projet sélectionné.");
        }
        if (workQueueMessage.trim().length === 0) {
          throw new Error("Message de rappel requis.");
        }
        return createWorkQueueItem({
          queue_name: workQueueName.trim() || "reminders",
          payload: {
            action: "project.reminder.emit",
            project_id: effectiveProjectId,
            message: workQueueMessage.trim()
          },
          priority: 50,
          max_attempts: 3,
          run_after_at: workQueueRunAfter ? new Date(workQueueRunAfter).toISOString() : undefined
        });
      }
      return createWorkQueueItem({
        queue_name: workQueueName.trim() || "default",
        payload: {
          action: "log",
          message: workQueueMessage.trim() || "operator-created"
        },
        priority: 100,
        max_attempts: 1
      });
    },
    onSuccess: () => {
      setWorkQueueMessage("");
      setWorkQueueRunAfter("");
      void queryClient.invalidateQueries({ queryKey: ["app-work-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["app-work-queue-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["app-project-briefs"] });
    }
  });

  const reviewWorkQueueMutation = useMutation({
    mutationFn: ({ itemId, action }: { itemId: string; action: "retry" | "dead_letter" }) =>
      reviewWorkQueueItem(itemId, {
        action,
        reviewed_by_type: "user",
        reviewed_by_id: "local-user",
        reason:
          action === "retry"
            ? "Retry requested from Synarch app."
            : "Dead-letter requested from Synarch app."
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["app-work-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["app-work-queue-summary"] });
    }
  });

  const credentialDecisionMutation = useMutation({
    mutationFn: decideCredentialAccessRequest,
    onSuccess: invalidateOperatorState
  });

  const credentialGrantMutation = useMutation({
    mutationFn: applyCredentialAccessGrant,
    onSuccess: invalidateOperatorState
  });

  const humanAssistanceMutation = useMutation({
    mutationFn: resolveHumanAssistanceRequest,
    onSuccess: (_result, variables) => {
      setHumanResponsesById((current) => {
        const next = { ...current };
        delete next[variables.requestId];
        return next;
      });
      invalidateOperatorState();
    }
  });

  const reencryptSecretVaultMutation = useMutation({
    mutationFn: reencryptSecretVault,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["app-readiness"] });
    }
  });

  const handleGoalSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (goal.trim().length === 0) {
      return;
    }
    submitGoalMutation.mutate();
  };

  const handleConnectSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (effectiveConnectorMode === "api_key" && apiKey.trim().length === 0) {
      return;
    }
    connectMutation.mutate();
  };

  const handleWorkQueueSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    createWorkQueueMutation.mutate();
  };

  const handleWorkQueueReview = (itemId: string, action: "retry" | "dead_letter") => {
    reviewWorkQueueMutation.mutate({ itemId, action });
  };

  const handleCredentialDecision = (
    requestId: string,
    status: "approved" | "rejected"
  ) => {
    credentialDecisionMutation.mutate({ requestId, status });
  };

  const handleCredentialGrant = (requestId: string, serviceId: string) => {
    credentialGrantMutation.mutate({ requestId, serviceId });
  };

  const handleHumanResponseChange = (requestId: string, response: string) => {
    setHumanResponsesById((current) => ({
      ...current,
      [requestId]: response
    }));
  };

  const handleHumanResolution = (
    requestId: string,
    status: "answered" | "dismissed"
  ) => {
    const response = humanResponsesById[requestId]?.trim();
    humanAssistanceMutation.mutate({
      requestId,
      status,
      response: response || `${status} from Synarch app.`
    });
  };

  const readinessStatus = readinessQuery.data?.status ?? "warning";
  const activeActions = actionsQuery.data ?? [];

  return (
    <main className="min-h-screen bg-app text-ink">
      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-4 px-4 py-4 lg:px-6">
        <header className="flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-accent">
              Synarch
            </p>
            <h1 className="truncate text-2xl font-semibold">Workspace</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-md px-2 py-1 text-xs font-semibold ring-1 ${readinessClass[readinessStatus]}`}
            >
              {readinessStatus}
            </span>
            <button
              type="button"
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-panel px-3 text-sm font-medium shadow-soft hover:bg-slate-50 disabled:opacity-60"
              disabled={readinessQuery.isFetching}
              onClick={() => {
                void readinessQuery.refetch();
                void workerHeartbeatsQuery.refetch();
                void workQueueSummaryQuery.refetch();
                void workQueueQuery.refetch();
              }}
              title="Rafraîchir l'état système"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Rafraîchir</span>
            </button>
          </div>
        </header>

        <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)_420px]">
          <aside className="flex min-w-0 flex-col gap-4">
            <section className="rounded-md border border-border bg-panel shadow-soft">
              <div className="border-b border-border px-4 py-3">
                <h2 className="text-sm font-semibold">Nouvel objectif</h2>
              </div>
              <form className="flex flex-col gap-3 p-4" onSubmit={handleGoalSubmit}>
                <textarea
                  className="min-h-32 resize-y rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus:border-accent"
                  value={goal}
                  onChange={(event) => setGoal(event.target.value)}
                  placeholder="Ex: organiser le sourcing de fournisseurs pour le projet moteur..."
                />
                <div className="grid grid-cols-2 gap-2">
                  {priorityOptions.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={`rounded-md border px-3 py-2 text-sm font-medium ${
                        priority === option
                          ? "border-accent bg-accent-soft text-accent"
                          : "border-border bg-white text-muted"
                      }`}
                      onClick={() => setPriority(option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
                <button
                  type="submit"
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
                  disabled={submitGoalMutation.isPending || goal.trim().length === 0}
                >
                  <Send className="h-4 w-4" />
                  <span>{submitGoalMutation.isPending ? "Envoi" : "Créer"}</span>
                </button>
                {submitGoalMutation.isError ? (
                  <p className="text-xs text-risk">
                    {submitGoalMutation.error instanceof Error
                      ? submitGoalMutation.error.message
                      : "Création impossible."}
                  </p>
                ) : null}
              </form>
            </section>

            <section className="rounded-md border border-border bg-panel shadow-soft">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h2 className="text-sm font-semibold">Projets</h2>
                <span className="text-xs text-muted">{projectsQuery.data?.length ?? 0}</span>
              </div>
              <div className="max-h-[520px] overflow-auto">
                {projectsQuery.isLoading ? (
                  <p className="px-4 py-3 text-sm text-muted">Chargement...</p>
                ) : (projectsQuery.data ?? []).length === 0 ? (
                  <p className="px-4 py-3 text-sm text-muted">Aucun projet.</p>
                ) : (
                  (projectsQuery.data ?? []).map((project) => (
                    <ProjectRow
                      key={project.id}
                      project={project}
                      selected={project.id === effectiveProjectId}
                      onSelect={() => setSelectedProjectId(project.id)}
                    />
                  ))
                )}
              </div>
            </section>
          </aside>

          <section className="min-w-0 rounded-md border border-border bg-panel shadow-soft">
            <div className="flex flex-col gap-3 border-b border-border px-4 py-3 md:flex-row md:items-center md:justify-between">
              <div className="min-w-0">
                <h2 className="truncate text-lg font-semibold">
                  {selectedProject?.title ?? "Aucun projet sélectionné"}
                </h2>
                <p className="truncate text-sm text-muted">
                  {selectedProject?.goal ?? "Crée un objectif pour démarrer un fil de travail."}
                </p>
              </div>
              <button
                type="button"
                className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-ink px-3 text-sm font-semibold text-white disabled:opacity-50"
                disabled={!effectiveProjectId || runProjectMutation.isPending}
                onClick={() => runProjectMutation.mutate()}
                title="Lancer les tâches prêtes"
              >
                <Play className="h-4 w-4" />
                <span>{runProjectMutation.isPending ? "Exécution" : "Exécuter"}</span>
              </button>
            </div>
            <div className="grid gap-0 md:grid-cols-3">
              <MetricBlock label="Tâches prêtes" value={selectedBrief?.next_tasks.length ?? 0} />
              <MetricBlock label="Actions humaines" value={activeActions.length} />
              <MetricBlock
                label="Connecteurs actifs"
                value={(connectionsQuery.data ?? []).filter((item) => item.status === "active").length}
              />
            </div>
            <div className="grid gap-4 border-t border-border p-4 lg:grid-cols-2">
              <BriefPanel brief={selectedBrief} loading={briefsQuery.isLoading} />
              <ActionPanel actions={activeActions} loading={actionsQuery.isLoading} />
            </div>
            <OperatorQueuePanel
              credentialRequests={visibleCredentialRequests}
              humanRequests={visibleHumanRequests}
              servicesById={servicesById}
              humanResponsesById={humanResponsesById}
              loading={credentialRequestsQuery.isLoading || humanAssistanceQuery.isLoading}
              credentialDecisionPending={credentialDecisionMutation.isPending}
              credentialGrantPending={credentialGrantMutation.isPending}
              humanAssistancePending={humanAssistanceMutation.isPending}
              credentialDecisionVariables={credentialDecisionMutation.variables}
              credentialGrantVariables={credentialGrantMutation.variables}
              humanAssistanceVariables={humanAssistanceMutation.variables}
              credentialError={credentialDecisionMutation.error ?? credentialGrantMutation.error}
              humanError={humanAssistanceMutation.error}
              onCredentialDecision={handleCredentialDecision}
              onCredentialGrant={handleCredentialGrant}
              onHumanResponseChange={handleHumanResponseChange}
              onHumanResolution={handleHumanResolution}
            />
            {runProjectMutation.isError ? (
              <p className="border-t border-border px-4 py-3 text-sm text-risk">
                {runProjectMutation.error instanceof Error
                  ? runProjectMutation.error.message
                  : "Exécution impossible."}
              </p>
            ) : null}
          </section>

          <aside className="flex min-w-0 flex-col gap-4">
            <section className="rounded-md border border-border bg-panel shadow-soft">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h2 className="text-sm font-semibold">Connecteurs</h2>
                <PlugZap className="h-4 w-4 text-accent" />
              </div>
              <form className="flex flex-col gap-3 p-4" onSubmit={handleConnectSubmit}>
                <select
                  className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
                  value={selectedService?.id ?? ""}
                  onChange={(event) => {
                    const nextServiceId = event.target.value;
                    const nextService =
                      connectorServices.find((service) => service.id === nextServiceId) ?? null;
                    setSelectedServiceId(nextServiceId);
                    setConnectorMode(
                      nextService ? connectorModesForService(nextService)[0] ?? "no_key" : "no_key"
                    );
                    setLastConnectorConnection(null);
                    setApiKey("");
                  }}
                >
                  {connectorServices.map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.name}
                    </option>
                  ))}
                </select>

                {selectedService ? (
                  <div className="rounded-md border border-border bg-slate-50 p-3 text-xs text-muted">
                    <div className="flex items-center justify-between gap-2">
                      <span>{selectedService.id}</span>
                      <span className="font-medium text-ink">{selectedService.kind}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(selectedService.capabilities.length > 0
                        ? selectedService.capabilities
                        : ["aucune capacité déclarée"]
                      ).map((capability) => (
                        <span
                          key={capability}
                          className="rounded-md bg-white px-2 py-1 ring-1 ring-border"
                        >
                          {capability}
                        </span>
                      ))}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {availableConnectorModes.map((mode) => (
                        <span
                          key={mode}
                          className="rounded-md bg-accent-soft px-2 py-1 text-[11px] text-accent ring-1 ring-accent/15"
                        >
                          {mode}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div
                  className={`grid gap-2 ${
                    availableConnectorModes.length === 1
                      ? "grid-cols-1"
                      : availableConnectorModes.length === 2
                        ? "grid-cols-2"
                        : "grid-cols-3"
                  }`}
                >
                  {availableConnectorModes.map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      className={`rounded-md border px-2 py-2 text-xs font-semibold ${
                        effectiveConnectorMode === mode
                          ? "border-accent bg-accent-soft text-accent"
                          : "border-border bg-white text-muted"
                      }`}
                      onClick={() => setConnectorMode(mode)}
                    >
                      {mode}
                    </button>
                  ))}
                </div>

                {effectiveConnectorMode === "api_key" ? (
                  <input
                    className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
                    type="password"
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    placeholder="Clé API"
                    autoComplete="off"
                  />
                ) : null}

                {serviceScopes.length > 0 ? (
                  <div className="flex flex-col gap-2">
                    <p className="text-xs font-semibold text-muted">Scopes</p>
                    {serviceScopes.map((scope) => (
                      <label
                        key={scope}
                        className="flex items-center gap-2 rounded-md border border-border bg-white px-3 py-2 text-sm"
                      >
                        <input
                          type="checkbox"
                          checked={selectedScopesSet.has(scope)}
                          onChange={(event) => {
                            const next = new Set(
                              selectedScopes.length === 0 ? serviceScopes : selectedScopes
                            );
                          if (event.target.checked) {
                            next.add(scope);
                          } else {
                            next.delete(scope);
                          }
                          if (selectedService) {
                            setScopeSelectionsByService((current) => ({
                              ...current,
                              [selectedService.id]: [...next]
                            }));
                          }
                        }}
                      />
                        <span>{scope}</span>
                      </label>
                    ))}
                  </div>
                ) : null}

                <button
                  type="submit"
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-60"
                  disabled={
                    !selectedService ||
                    connectMutation.isPending ||
                    (effectiveConnectorMode === "api_key" && apiKey.trim().length === 0)
                  }
                >
                  <KeyRound className="h-4 w-4" />
                  <span>{connectMutation.isPending ? "Connexion" : "Connecter"}</span>
                </button>

                {activeConnection ? (
                  <ConnectionStatus connection={activeConnection} service={selectedService} />
                ) : null}
                {activeConnection && activeConnection.status !== "disabled" ? (
                  <button
                    type="button"
                    className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-risk/30 bg-white px-3 text-sm font-semibold text-risk hover:bg-risk-soft disabled:opacity-60"
                    disabled={disableConnectorMutation.isPending}
                    onClick={() => disableConnectorMutation.mutate()}
                    title="Désactiver la connexion et supprimer le secret local associé"
                  >
                    <X className="h-4 w-4" />
                    <span>
                      {disableConnectorMutation.isPending ? "Désactivation" : "Désactiver"}
                    </span>
                  </button>
                ) : null}
                {connectMutation.isError ? (
                  <p className="text-xs text-risk">
                    {connectMutation.error instanceof Error
                      ? connectMutation.error.message
                      : "Connexion impossible."}
                  </p>
                ) : null}
                {disableConnectorMutation.isError ? (
                  <p className="text-xs text-risk">
                    {disableConnectorMutation.error instanceof Error
                      ? disableConnectorMutation.error.message
                      : "Désactivation impossible."}
                  </p>
                ) : null}
              </form>
            </section>

            <section className="rounded-md border border-border bg-panel shadow-soft">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h2 className="text-sm font-semibold">État système</h2>
                <ShieldCheck className="h-4 w-4 text-ok" />
              </div>
              <div className="divide-y divide-border">
                {(readinessQuery.data?.items ?? []).slice(0, 8).map((item) => (
                  <div key={item.id} className="flex items-start gap-3 px-4 py-3">
                    {item.status === "ready" ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" />
                    ) : item.status === "blocked" ? (
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-risk" />
                    ) : (
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{item.title}</p>
                      <p className="line-clamp-2 text-xs text-muted">{item.detail}</p>
                      {item.manual_action ? (
                        <p className="mt-1 line-clamp-2 text-xs text-muted">
                          {item.manual_action}
                        </p>
                      ) : null}
                      {item.id === "secret_vault" && reencryptSecretVaultMutation.isError ? (
                        <p className="mt-1 text-xs text-risk">
                          {reencryptSecretVaultMutation.error instanceof Error
                            ? reencryptSecretVaultMutation.error.message
                            : "Action impossible."}
                        </p>
                      ) : null}
                    </div>
                    {canReencryptSecretVault(item) ? (
                      <button
                        type="button"
                        className="inline-flex h-8 shrink-0 items-center gap-2 rounded-md border border-border bg-white px-2 text-xs font-semibold hover:bg-slate-50 disabled:opacity-60"
                        disabled={reencryptSecretVaultMutation.isPending}
                        onClick={() => reencryptSecretVaultMutation.mutate()}
                        title="Chiffrer les anciens secrets locaux"
                      >
                        <KeyRound className="h-3.5 w-3.5" />
                        <span>
                          {reencryptSecretVaultMutation.isPending ? "Chiffrement" : "Chiffrer"}
                        </span>
                      </button>
                    ) : null}
                  </div>
                ))}
                {readinessQuery.isLoading ? (
                  <p className="px-4 py-3 text-sm text-muted">Chargement...</p>
                ) : null}
              </div>
            </section>

            <WorkerPanel
              heartbeats={workerHeartbeatsQuery.data ?? []}
              loading={workerHeartbeatsQuery.isLoading}
            />

            <WorkQueuePanel
              items={workQueueQuery.data ?? []}
              summaries={workQueueSummaryQuery.data ?? []}
              loading={workQueueQuery.isLoading}
              summaryLoading={workQueueSummaryQuery.isLoading}
              queueName={workQueueName}
              action={workQueueAction}
              message={workQueueMessage}
              runAfter={workQueueRunAfter}
              selectedProjectTitle={selectedProject?.title ?? null}
              submitting={createWorkQueueMutation.isPending}
              reviewing={reviewWorkQueueMutation.isPending}
              canSubmit={canSubmitWorkQueue}
              error={createWorkQueueMutation.error}
              reviewError={reviewWorkQueueMutation.error}
              onQueueNameChange={setWorkQueueName}
              onActionChange={setWorkQueueAction}
              onMessageChange={setWorkQueueMessage}
              onRunAfterChange={setWorkQueueRunAfter}
              onSubmit={handleWorkQueueSubmit}
              onReview={handleWorkQueueReview}
            />
          </aside>
        </div>
      </div>
    </main>
  );
}

function ProjectRow({
  project,
  selected,
  onSelect
}: {
  project: ProjectRecord;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`flex w-full min-w-0 flex-col gap-2 border-b border-border px-4 py-3 text-left hover:bg-slate-50 ${
        selected ? "bg-accent-soft/60" : "bg-panel"
      }`}
      onClick={onSelect}
    >
      <div className="flex min-w-0 items-center justify-between gap-2">
        <span className="truncate text-sm font-semibold">{project.title}</span>
        <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${statusClass(project.status)}`}>
          {project.status}
        </span>
      </div>
      <p className="line-clamp-2 text-xs text-muted">{project.goal}</p>
      <div className="flex items-center justify-between gap-2 text-[11px] text-muted">
        <span>{project.priority}</span>
        <span>{formatDate(project.created_at)}</span>
      </div>
    </button>
  );
}

function MetricBlock({ label, value }: { label: string; value: number }) {
  return (
    <div className="border-b border-border px-4 py-3 md:border-b-0 md:border-r">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function BriefPanel({ brief, loading }: { brief: ProjectBrief | null; loading: boolean }) {
  if (loading) {
    return <PanelEmpty icon={<Workflow className="h-4 w-4" />} text="Chargement du brief..." />;
  }
  if (!brief) {
    return <PanelEmpty icon={<Workflow className="h-4 w-4" />} text="Aucun brief." />;
  }
  return (
    <div className="min-w-0 rounded-md border border-border">
      <div className="border-b border-border px-3 py-2">
        <h3 className="text-sm font-semibold">Fil directeur</h3>
      </div>
      <div className="p-3">
        <p className="text-sm font-medium">{brief.next_action.title}</p>
        <p className="mt-1 text-xs text-muted">{brief.next_action.reason}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(brief.task_counts).map(([status, count]) => (
            <span
              key={status}
              className={`rounded-md px-2 py-1 text-xs ring-1 ${statusClass(status)}`}
            >
              {status}: {count}
            </span>
          ))}
        </div>
        <div className="mt-4 space-y-2">
          {brief.next_tasks.slice(0, 4).map((task) => (
            <div key={task.id} className="flex items-start gap-2 text-sm">
              <CircleDot className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
              <div className="min-w-0">
                <p className="truncate font-medium">{task.title}</p>
                <p className="truncate text-xs text-muted">{task.assigned_agent_id}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ActionPanel({ actions, loading }: { actions: OperatorAction[]; loading: boolean }) {
  if (loading) {
    return <PanelEmpty icon={<AlertTriangle className="h-4 w-4" />} text="Chargement actions..." />;
  }
  if (actions.length === 0) {
    return <PanelEmpty icon={<CheckCircle2 className="h-4 w-4" />} text="Aucune action bloquante." />;
  }
  return (
    <div className="min-w-0 rounded-md border border-border">
      <div className="border-b border-border px-3 py-2">
        <h3 className="text-sm font-semibold">Actions opérateur</h3>
      </div>
      <div className="divide-y divide-border">
        {actions.slice(0, 5).map((action) => (
          <div key={action.id} className="px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <p className="truncate text-sm font-medium">{action.title}</p>
              <span className="shrink-0 rounded-md bg-warn-soft px-2 py-0.5 text-[11px] text-warn ring-1 ring-warn/15">
                {action.priority}
              </span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs text-muted">{action.recommended_action}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function visibleCredentialAccessRequests(
  requests: CredentialAccessRequest[],
  projectId: string | null
): CredentialAccessRequest[] {
  return [...requests]
    .filter((request) => request.status === "requested" || request.status === "approved")
    .sort((left, right) => {
      const leftMatchesProject = projectId !== null && left.project_id === projectId;
      const rightMatchesProject = projectId !== null && right.project_id === projectId;
      if (leftMatchesProject !== rightMatchesProject) {
        return leftMatchesProject ? -1 : 1;
      }
      if (left.status !== right.status) {
        return left.status === "requested" ? -1 : 1;
      }
      return right.created_at.localeCompare(left.created_at);
    })
    .slice(0, 6);
}

function visibleHumanAssistanceRequests(
  requests: HumanAssistanceRequest[],
  projectId: string | null
): HumanAssistanceRequest[] {
  return [...requests]
    .filter((request) => request.status === "requested")
    .sort((left, right) => {
      const leftMatchesProject = projectId !== null && left.project_id === projectId;
      const rightMatchesProject = projectId !== null && right.project_id === projectId;
      if (leftMatchesProject !== rightMatchesProject) {
        return leftMatchesProject ? -1 : 1;
      }
      if (left.urgency !== right.urgency) {
        return priorityRank(right.urgency) - priorityRank(left.urgency);
      }
      return right.created_at.localeCompare(left.created_at);
    })
    .slice(0, 6);
}

function priorityRank(priority: GoalPriority): number {
  return {
    low: 1,
    medium: 2,
    high: 3,
    critical: 4
  }[priority];
}

function OperatorQueuePanel({
  credentialRequests,
  humanRequests,
  servicesById,
  humanResponsesById,
  loading,
  credentialDecisionPending,
  credentialGrantPending,
  humanAssistancePending,
  credentialDecisionVariables,
  credentialGrantVariables,
  humanAssistanceVariables,
  credentialError,
  humanError,
  onCredentialDecision,
  onCredentialGrant,
  onHumanResponseChange,
  onHumanResolution
}: {
  credentialRequests: CredentialAccessRequest[];
  humanRequests: HumanAssistanceRequest[];
  servicesById: Map<string, ServiceDefinition>;
  humanResponsesById: Record<string, string>;
  loading: boolean;
  credentialDecisionPending: boolean;
  credentialGrantPending: boolean;
  humanAssistancePending: boolean;
  credentialDecisionVariables?: { requestId: string; status: "approved" | "rejected" };
  credentialGrantVariables?: { requestId: string; serviceId: string };
  humanAssistanceVariables?: {
    requestId: string;
    status: "answered" | "dismissed";
    response: string;
  };
  credentialError: unknown;
  humanError: unknown;
  onCredentialDecision: (requestId: string, status: "approved" | "rejected") => void;
  onCredentialGrant: (requestId: string, serviceId: string) => void;
  onHumanResponseChange: (requestId: string, response: string) => void;
  onHumanResolution: (requestId: string, status: "answered" | "dismissed") => void;
}) {
  const hasRows = credentialRequests.length > 0 || humanRequests.length > 0;
  return (
    <section className="border-t border-border px-4 py-4">
      <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">Autorisations et assistance</h3>
          <p className="text-xs text-muted">
            Credentials, accès outils, captcha, PDF et décisions bloquantes.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-md bg-warn-soft px-2 py-1 text-warn ring-1 ring-warn/15">
            credentials: {credentialRequests.length}
          </span>
          <span className="rounded-md bg-info-soft px-2 py-1 text-info ring-1 ring-info/15">
            humain: {humanRequests.length}
          </span>
        </div>
      </div>

      {loading ? (
        <p className="rounded-md bg-slate-50 px-3 py-3 text-sm text-muted">Chargement...</p>
      ) : !hasRows ? (
        <p className="rounded-md bg-ok-soft px-3 py-3 text-sm text-ok">
          Aucune autorisation ou assistance ouverte.
        </p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-accent" />
              <h4 className="text-xs font-semibold uppercase text-muted">Credentials</h4>
            </div>
            <div className="space-y-2">
              {credentialRequests.length === 0 ? (
                <p className="rounded-md bg-slate-50 px-3 py-3 text-sm text-muted">
                  Aucune demande d&apos;accès ouverte.
                </p>
              ) : (
                credentialRequests.map((request) => {
                  const candidateServiceId = request.candidate_service_ids[0] ?? "";
                  const candidateService = servicesById.get(candidateServiceId);
                  const canApplyGrant = request.status === "approved" && candidateServiceId;
                  const isDecisionPending =
                    credentialDecisionPending &&
                    credentialDecisionVariables?.requestId === request.id;
                  const isGrantPending =
                    credentialGrantPending && credentialGrantVariables?.requestId === request.id;
                  return (
                    <article key={request.id} className="rounded-md border border-border bg-white p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">{request.tool_name}</p>
                          <p className="truncate text-xs text-muted">
                            {request.agent_id} / {request.task_id}
                          </p>
                        </div>
                        <span
                          className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${statusClass(request.status)}`}
                        >
                          {request.status}
                        </span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-xs text-muted">{request.reason}</p>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {(request.requested_scopes.length > 0
                          ? request.requested_scopes
                          : ["scope outil"]
                        ).map((scope) => (
                          <span
                            key={scope}
                            className="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-muted ring-1 ring-border"
                          >
                            {scope}
                          </span>
                        ))}
                      </div>
                      <p className="mt-2 truncate text-[11px] text-muted">
                        Service candidat: {candidateService?.name ?? (candidateServiceId || "aucun")}
                      </p>
                      <div className="mt-3 flex flex-wrap justify-end gap-2">
                        {request.status === "requested" ? (
                          <>
                            <button
                              type="button"
                              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-ok/30 px-2 text-xs font-medium text-ok disabled:opacity-50"
                              disabled={credentialDecisionPending || credentialGrantPending}
                              onClick={() => onCredentialDecision(request.id, "approved")}
                            >
                              <Check className="h-3.5 w-3.5" />
                              <span>{isDecisionPending ? "..." : "Approuver"}</span>
                            </button>
                            <button
                              type="button"
                              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-risk/30 px-2 text-xs font-medium text-risk disabled:opacity-50"
                              disabled={credentialDecisionPending || credentialGrantPending}
                              onClick={() => onCredentialDecision(request.id, "rejected")}
                            >
                              <X className="h-3.5 w-3.5" />
                              <span>Rejeter</span>
                            </button>
                          </>
                        ) : null}
                        {request.status === "approved" ? (
                          <button
                            type="button"
                            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-2 text-xs font-semibold text-white disabled:opacity-50"
                            disabled={!canApplyGrant || credentialGrantPending}
                            onClick={() => {
                              if (candidateServiceId) {
                                onCredentialGrant(request.id, candidateServiceId);
                              }
                            }}
                          >
                            <KeyRound className="h-3.5 w-3.5" />
                            <span>{isGrantPending ? "Application" : "Appliquer le grant"}</span>
                          </button>
                        ) : null}
                      </div>
                    </article>
                  );
                })
              )}
            </div>
          </div>

          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-warn" />
              <h4 className="text-xs font-semibold uppercase text-muted">Assistance humaine</h4>
            </div>
            <div className="space-y-2">
              {humanRequests.length === 0 ? (
                <p className="rounded-md bg-slate-50 px-3 py-3 text-sm text-muted">
                  Aucune demande humaine ouverte.
                </p>
              ) : (
                humanRequests.map((request) => {
                  const response = humanResponsesById[request.id] ?? "";
                  const isPending =
                    humanAssistancePending &&
                    humanAssistanceVariables?.requestId === request.id;
                  return (
                    <article key={request.id} className="rounded-md border border-border bg-white p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">{request.title}</p>
                          <p className="truncate text-xs text-muted">
                            {request.kind} / {request.agent_id}
                          </p>
                        </div>
                        <span
                          className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${statusClass(request.urgency)}`}
                        >
                          {request.urgency}
                        </span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-xs text-muted">
                        {request.description}
                      </p>
                      <textarea
                        className="mt-3 min-h-20 w-full resize-y rounded-md border border-border bg-white px-3 py-2 text-xs outline-none focus:border-accent"
                        value={response}
                        onChange={(event) => onHumanResponseChange(request.id, event.target.value)}
                        placeholder="Réponse opérateur, résumé PDF, captcha terminé, décision prise..."
                      />
                      <div className="mt-3 flex flex-wrap justify-end gap-2">
                        <button
                          type="button"
                          className="inline-flex h-8 items-center gap-1.5 rounded-md border border-risk/30 px-2 text-xs font-medium text-risk disabled:opacity-50"
                          disabled={humanAssistancePending}
                          onClick={() => onHumanResolution(request.id, "dismissed")}
                        >
                          <X className="h-3.5 w-3.5" />
                          <span>Dismiss</span>
                        </button>
                        <button
                          type="button"
                          className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-2 text-xs font-semibold text-white disabled:opacity-50"
                          disabled={humanAssistancePending || response.trim().length === 0}
                          onClick={() => onHumanResolution(request.id, "answered")}
                        >
                          <Check className="h-3.5 w-3.5" />
                          <span>{isPending ? "Envoi" : "Répondre"}</span>
                        </button>
                      </div>
                    </article>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {credentialError ? (
        <p className="mt-3 text-xs text-risk">
          {credentialError instanceof Error ? credentialError.message : "Décision credential impossible."}
        </p>
      ) : null}
      {humanError ? (
        <p className="mt-3 text-xs text-risk">
          {humanError instanceof Error ? humanError.message : "Réponse humaine impossible."}
        </p>
      ) : null}
    </section>
  );
}

function WorkerPanel({
  heartbeats,
  loading
}: {
  heartbeats: WorkerHeartbeatRecord[];
  loading: boolean;
}) {
  const recentHeartbeats = [...heartbeats]
    .sort((left, right) => right.last_seen_at.localeCompare(left.last_seen_at))
    .slice(0, 4);
  const statusCounts = heartbeats.reduce<Record<string, number>>((counts, heartbeat) => {
    counts[heartbeat.status] = (counts[heartbeat.status] ?? 0) + 1;
    return counts;
  }, {});

  return (
    <section className="rounded-md border border-border bg-panel shadow-soft">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold">Workers</h2>
        <Activity className="h-4 w-4 text-accent" />
      </div>
      <div className="border-b border-border px-4 py-3">
        <div className="flex flex-wrap gap-2">
          {["completed", "failed", "running", "idle", "stopped"].map((status) => (
            <span
              key={status}
              className={`rounded-md px-2 py-1 text-xs ring-1 ${statusClass(status)}`}
            >
              {status}: {statusCounts[status] ?? 0}
            </span>
          ))}
        </div>
      </div>
      <div className="divide-y divide-border">
        {loading ? (
          <p className="px-4 py-3 text-sm text-muted">Chargement...</p>
        ) : recentHeartbeats.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">Aucun worker signalé.</p>
        ) : (
          recentHeartbeats.map((heartbeat) => (
            <div key={heartbeat.id} className="px-4 py-3">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-medium">{heartbeat.id}</p>
                <span
                  className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${statusClass(heartbeat.status)}`}
                >
                  {heartbeat.status}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted">
                <span className="truncate">
                  {heartbeat.worker_kind}
                  {heartbeat.target ? ` / ${heartbeat.target}` : ""}
                </span>
                <span className="shrink-0">#{heartbeat.heartbeat_count}</span>
              </div>
              {heartbeat.last_error ? (
                <p className="mt-1 line-clamp-2 text-xs text-risk">{heartbeat.last_error}</p>
              ) : null}
              <p className="mt-1 text-[11px] text-muted">{formatDate(heartbeat.last_seen_at)}</p>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function QueueSummaryStrip({
  summaries,
  selectedQueueName,
  loading,
  onSelect
}: {
  summaries: WorkQueueSummary[];
  selectedQueueName: string;
  loading: boolean;
  onSelect: (queueName: string) => void;
}) {
  const orderedSummaries = [...summaries].sort((left, right) => {
    const leftProblemCount = left.failed_count + left.dead_lettered_count;
    const rightProblemCount = right.failed_count + right.dead_lettered_count;
    if (leftProblemCount !== rightProblemCount) {
      return rightProblemCount - leftProblemCount;
    }
    if (left.ready_count !== right.ready_count) {
      return right.ready_count - left.ready_count;
    }
    return left.queue_name.localeCompare(right.queue_name);
  });

  return (
    <div className="border-b border-border px-4 py-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase text-muted">Queues</p>
        <span className="text-xs text-muted">{summaries.length}</span>
      </div>
      {loading ? (
        <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-muted">Chargement...</p>
      ) : orderedSummaries.length === 0 ? (
        <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-muted">Aucune queue.</p>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {orderedSummaries.map((summary) => {
            const problemCount = summary.failed_count + summary.dead_lettered_count;
            const selected = summary.queue_name === selectedQueueName;
            return (
              <button
                key={summary.queue_name}
                type="button"
                className={`flex min-w-[180px] flex-col gap-2 rounded-md border px-3 py-2 text-left ${
                  selected ? "border-accent bg-accent-soft" : "border-border bg-white"
                }`}
                onClick={() => onSelect(summary.queue_name)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-semibold">{summary.queue_name}</span>
                  <span className="shrink-0 text-[11px] text-muted">{summary.item_count}</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  <span className="rounded-md bg-ok-soft px-2 py-0.5 text-[11px] text-ok ring-1 ring-ok/15">
                    prêt {summary.ready_count}
                  </span>
                  <span className="rounded-md bg-info-soft px-2 py-0.5 text-[11px] text-info ring-1 ring-info/15">
                    actif {summary.running_count}
                  </span>
                  <span
                    className={`rounded-md px-2 py-0.5 text-[11px] ring-1 ${
                      problemCount > 0
                        ? "bg-risk-soft text-risk ring-risk/15"
                        : "bg-slate-100 text-muted ring-border"
                    }`}
                  >
                    err {problemCount}
                  </span>
                </div>
                {summary.next_run_after_at ? (
                  <p className="truncate text-[11px] text-muted">
                    prochain {formatDate(summary.next_run_after_at)}
                  </p>
                ) : null}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WorkQueuePanel({
  items,
  summaries,
  loading,
  summaryLoading,
  queueName,
  action,
  message,
  runAfter,
  selectedProjectTitle,
  submitting,
  reviewing,
  canSubmit,
  error,
  reviewError,
  onQueueNameChange,
  onActionChange,
  onMessageChange,
  onRunAfterChange,
  onSubmit,
  onReview
}: {
  items: WorkQueueItem[];
  summaries: WorkQueueSummary[];
  loading: boolean;
  summaryLoading: boolean;
  queueName: string;
  action: WorkQueueAction;
  message: string;
  runAfter: string;
  selectedProjectTitle: string | null;
  submitting: boolean;
  reviewing: boolean;
  canSubmit: boolean;
  error: unknown;
  reviewError: unknown;
  onQueueNameChange: (value: string) => void;
  onActionChange: (value: WorkQueueAction) => void;
  onMessageChange: (value: string) => void;
  onRunAfterChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onReview: (itemId: string, action: "retry" | "dead_letter") => void;
}) {
  const statusCounts = items.reduce<Record<string, number>>((counts, item) => {
    counts[item.status] = (counts[item.status] ?? 0) + 1;
    return counts;
  }, {});
  const recentItems = [...items]
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .slice(0, 4);
  const normalizedQueueName = queueName.trim();
  const selectedSummary =
    summaries.find((summary) => summary.queue_name === normalizedQueueName) ?? null;
  const visibleStatusCounts = selectedSummary?.status_counts ?? statusCounts;

  return (
    <section className="rounded-md border border-border bg-panel shadow-soft">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold">Queue durable</h2>
        <ListChecks className="h-4 w-4 text-accent" />
      </div>
      <QueueSummaryStrip
        summaries={summaries}
        selectedQueueName={normalizedQueueName}
        loading={summaryLoading}
        onSelect={onQueueNameChange}
      />
      <form className="flex flex-col gap-3 p-4" onSubmit={onSubmit}>
        <div className="grid grid-cols-2 rounded-md border border-border bg-slate-50 p-1">
          <button
            type="button"
            className={`h-8 rounded text-xs font-semibold ${
              action === "project_reminder" ? "bg-white text-ink shadow-soft" : "text-muted"
            }`}
            onClick={() => onActionChange("project_reminder")}
          >
            Rappel projet
          </button>
          <button
            type="button"
            className={`h-8 rounded text-xs font-semibold ${
              action === "log" ? "bg-white text-ink shadow-soft" : "text-muted"
            }`}
            onClick={() => onActionChange("log")}
          >
            Log
          </button>
        </div>
        <input
          aria-label="Nom de queue"
          className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
          value={queueName}
          onChange={(event) => onQueueNameChange(event.target.value)}
          placeholder={action === "project_reminder" ? "reminders" : "default"}
        />
        {action === "project_reminder" ? (
          <div className="rounded-md border border-border bg-slate-50 px-3 py-2 text-xs text-muted">
            <span className="font-medium text-ink">Projet:</span>{" "}
            {selectedProjectTitle ?? "aucun projet sélectionné"}
          </div>
        ) : null}
        <input
          aria-label="Message de queue"
          className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
          value={message}
          onChange={(event) => onMessageChange(event.target.value)}
          placeholder={action === "project_reminder" ? "rappel à créer" : "message"}
        />
        {action === "project_reminder" ? (
          <input
            aria-label="Date du rappel"
            type="datetime-local"
            className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
            value={runAfter}
            onChange={(event) => onRunAfterChange(event.target.value)}
          />
        ) : null}
        <button
          type="submit"
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-white disabled:opacity-60"
          disabled={submitting || !canSubmit}
        >
          <Plus className="h-4 w-4" />
          <span>
            {submitting ? "Création" : action === "project_reminder" ? "Planifier" : "Ajouter"}
          </span>
        </button>
        {error ? (
          <p className="text-xs text-risk">
            {error instanceof Error ? error.message : "Création impossible."}
          </p>
        ) : null}
        {reviewError ? (
          <p className="text-xs text-risk">
            {reviewError instanceof Error ? reviewError.message : "Décision impossible."}
          </p>
        ) : null}
      </form>
      <div className="border-t border-border px-4 py-3">
        <div className="flex flex-wrap gap-2">
          {["queued", "running", "completed", "failed", "dead_lettered"].map((status) => (
            <span
              key={status}
              className={`rounded-md px-2 py-1 text-xs ring-1 ${statusClass(status)}`}
            >
              {status}: {visibleStatusCounts[status] ?? 0}
            </span>
          ))}
          {selectedSummary ? (
            <>
              <span className="rounded-md bg-ok-soft px-2 py-1 text-xs text-ok ring-1 ring-ok/15">
                prêts: {selectedSummary.ready_count}
              </span>
              <span className="rounded-md bg-slate-100 px-2 py-1 text-xs text-muted ring-1 ring-border">
                différés: {selectedSummary.delayed_count}
              </span>
            </>
          ) : null}
        </div>
        {selectedSummary?.latest_error ? (
          <p className="mt-2 line-clamp-2 text-xs text-risk">{selectedSummary.latest_error}</p>
        ) : null}
      </div>
      <div className="divide-y divide-border">
        {loading ? (
          <p className="px-4 py-3 text-sm text-muted">Chargement...</p>
        ) : recentItems.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">Aucun item.</p>
        ) : (
          recentItems.map((item) => {
            const canRetry = item.status === "failed" || item.status === "dead_lettered";
            const canDeadLetter = item.status !== "completed" && item.status !== "dead_lettered";
            return (
              <div key={item.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium">{item.id}</p>
                  <span
                    className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${statusClass(item.status)}`}
                  >
                    {item.status}
                  </span>
                </div>
                <p className="mt-1 truncate text-xs text-muted">
                  {workQueuePayloadLabel(item.payload)}
                </p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <p className="mr-auto text-[11px] text-muted">{formatDate(item.updated_at)}</p>
                  {canRetry ? (
                    <button
                      type="button"
                      className="inline-flex h-7 items-center gap-1.5 rounded-md border border-border px-2 text-[11px] font-medium text-ink disabled:opacity-60"
                      disabled={reviewing}
                      onClick={() => onReview(item.id, "retry")}
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      <span>Réessayer</span>
                    </button>
                  ) : null}
                  {canDeadLetter ? (
                    <button
                      type="button"
                      className="inline-flex h-7 items-center gap-1.5 rounded-md border border-risk/30 px-2 text-[11px] font-medium text-risk disabled:opacity-60"
                      disabled={reviewing}
                      onClick={() => onReview(item.id, "dead_letter")}
                    >
                      <AlertTriangle className="h-3.5 w-3.5" />
                      <span>Dead-letter</span>
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

function workQueuePayloadLabel(payload: Record<string, unknown>): string {
  const action = typeof payload.action === "string" ? payload.action : "payload";
  const message = typeof payload.message === "string" ? payload.message : "";
  if (action === "project.reminder.emit") {
    const projectId = typeof payload.project_id === "string" ? payload.project_id : null;
    const prefix = projectId ? `rappel projet / ${projectId}` : "rappel projet";
    return message ? `${prefix}: ${message}` : prefix;
  }
  return message ? `${action}: ${message}` : action;
}

function PanelEmpty({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div className="flex min-h-32 items-center justify-center gap-2 rounded-md border border-border text-sm text-muted">
      {icon}
      <span>{text}</span>
    </div>
  );
}

function ConnectionStatus({
  connection,
  service
}: {
  connection: ConnectorConnectionRecord;
  service: ServiceDefinition | null;
}) {
  if (connection.status === "disabled") {
    return (
      <div className="rounded-md border border-risk/20 bg-risk-soft p-3 text-xs text-risk">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold">Désactivé</span>
          <span>{connection.mode}</span>
        </div>
        <p className="mt-1 text-risk">
          La connexion est inactive et son secret local n&apos;est plus référencé.
        </p>
        <p className="mt-1 text-risk">Mis à jour: {formatDate(connection.updated_at)}</p>
      </div>
    );
  }
  if (connection.status === "needs_oauth") {
    return (
      <div className="rounded-md border border-warn/20 bg-warn-soft p-3 text-xs text-warn">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold">Autorisation requise</span>
          <span>{connection.mode}</span>
        </div>
        <p className="mt-1 text-warn">
          Le connecteur attend la validation du compte externe.
        </p>
        {connection.setup_url ? (
          <a
            href={connection.setup_url}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-flex h-8 items-center gap-2 rounded-md border border-warn/30 px-2 text-xs font-medium text-warn"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Ouvrir
          </a>
        ) : null}
        <p className="mt-2 text-warn">Mis à jour: {formatDate(connection.updated_at)}</p>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-ok/20 bg-ok-soft p-3 text-xs text-ok">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold">
          {connection.status === "active" ? "Connecté" : connection.status}
        </span>
        <span>{connection.mode}</span>
      </div>
      <p className="mt-1 text-ok">
        {connection.secret_ref
          ? "Secret stocké dans le vault local."
          : connection.mode === "oauth"
            ? "Autorisation externe enregistrée."
            : "Connexion sans clé active."}
      </p>
      <p className="mt-1 text-ok">
        Ref:{" "}
        {connection.secret_ref
          ? connection.secret_fingerprint
          : (metadataString(service, "web_provider") ?? connection.status)}
      </p>
      <p className="mt-1 text-ok">Mis à jour: {formatDate(connection.updated_at)}</p>
    </div>
  );
}
