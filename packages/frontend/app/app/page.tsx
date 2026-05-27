"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
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
  Workflow
} from "lucide-react";
import { type FormEvent, type ReactNode, useMemo, useState } from "react";

import {
  connectConnectorService,
  getSystemReadiness,
  listConnectorConnections,
  listOperatorActions,
  listProjectBriefs,
  runReadyTasks,
  submitGoal,
  type ConnectorConnectionMode,
  type ConnectorConnectionRecord,
  type GoalPriority,
  type OperatorAction,
  type ProjectBrief,
  type SystemReadinessStatus
} from "../../lib/gateway-api";
import {
  createWorkQueueItem,
  listProjects,
  listServices,
  listWorkQueueItems,
  type ProjectRecord,
  type ServiceDefinition,
  type WorkQueueItem
} from "../../lib/state-service-api";

const priorityOptions: GoalPriority[] = ["medium", "high", "critical", "low"];
const connectorModes: ConnectorConnectionMode[] = ["api_key", "no_key", "oauth"];

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

function selectedScopeSet(scopes: string[]): Set<string> {
  return new Set(scopes.filter(Boolean));
}

export default function SynarchAppPage() {
  const queryClient = useQueryClient();
  const [goal, setGoal] = useState("");
  const [priority, setPriority] = useState<GoalPriority>("medium");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
  const [connectorMode, setConnectorMode] = useState<ConnectorConnectionMode>("api_key");
  const [apiKey, setApiKey] = useState("");
  const [workQueueName, setWorkQueueName] = useState("default");
  const [workQueueMessage, setWorkQueueMessage] = useState("");
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
    queryFn: () => listWorkQueueItems(workQueueName.trim() || undefined)
  });

  const selectedProject =
    projectsQuery.data?.find((project) => project.id === selectedProjectId) ??
    projectsQuery.data?.[0] ??
    null;
  const effectiveProjectId = selectedProject?.id ?? null;

  const briefsQuery = useQuery({
    queryKey: ["app-project-briefs", effectiveProjectId],
    queryFn: () => listProjectBriefs(effectiveProjectId ?? undefined),
    enabled: effectiveProjectId !== null
  });
  const actionsQuery = useQuery({
    queryKey: ["app-operator-actions", effectiveProjectId],
    queryFn: () => listOperatorActions(effectiveProjectId ?? undefined)
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
  const selectedBrief = briefsQuery.data?.[0] ?? null;

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
          mode: connectorMode,
          api_key: connectorMode === "api_key" ? apiKey : undefined,
          credential_scopes: selectedScopes,
          project_id: effectiveProjectId,
          rationale: "Connector configured from Synarch app."
        }
      });
    },
    onSuccess: () => {
      setApiKey("");
      void queryClient.invalidateQueries({ queryKey: ["app-services"] });
      void queryClient.invalidateQueries({ queryKey: ["app-connector-connections"] });
      void queryClient.invalidateQueries({ queryKey: ["app-readiness"] });
    }
  });

  const createWorkQueueMutation = useMutation({
    mutationFn: () =>
      createWorkQueueItem({
        queue_name: workQueueName.trim() || "default",
        payload: {
          action: "log",
          message: workQueueMessage.trim() || "operator-created"
        },
        priority: 100,
        max_attempts: 1
      }),
    onSuccess: () => {
      setWorkQueueMessage("");
      void queryClient.invalidateQueries({ queryKey: ["app-work-queue"] });
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
    if (connectorMode === "api_key" && apiKey.trim().length === 0) {
      return;
    }
    connectMutation.mutate();
  };

  const handleWorkQueueSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    createWorkQueueMutation.mutate();
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
                    setSelectedServiceId(event.target.value);
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
                  </div>
                ) : null}

                <div className="grid grid-cols-3 gap-2">
                  {connectorModes.map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      className={`rounded-md border px-2 py-2 text-xs font-semibold ${
                        connectorMode === mode
                          ? "border-accent bg-accent-soft text-accent"
                          : "border-border bg-white text-muted"
                      }`}
                      onClick={() => setConnectorMode(mode)}
                    >
                      {mode}
                    </button>
                  ))}
                </div>

                {connectorMode === "api_key" ? (
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
                    (connectorMode === "api_key" && apiKey.trim().length === 0)
                  }
                >
                  <KeyRound className="h-4 w-4" />
                  <span>{connectMutation.isPending ? "Connexion" : "Connecter"}</span>
                </button>

                {selectedConnection ? (
                  <ConnectionStatus connection={selectedConnection} service={selectedService} />
                ) : null}
                {connectMutation.isError ? (
                  <p className="text-xs text-risk">
                    {connectMutation.error instanceof Error
                      ? connectMutation.error.message
                      : "Connexion impossible."}
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
                {(readinessQuery.data?.items ?? []).slice(0, 6).map((item) => (
                  <div key={item.id} className="flex items-start gap-3 px-4 py-3">
                    {item.status === "ready" ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" />
                    ) : (
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
                    )}
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{item.title}</p>
                      <p className="line-clamp-2 text-xs text-muted">{item.detail}</p>
                    </div>
                  </div>
                ))}
                {readinessQuery.isLoading ? (
                  <p className="px-4 py-3 text-sm text-muted">Chargement...</p>
                ) : null}
              </div>
            </section>

            <WorkQueuePanel
              items={workQueueQuery.data ?? []}
              loading={workQueueQuery.isLoading}
              queueName={workQueueName}
              message={workQueueMessage}
              submitting={createWorkQueueMutation.isPending}
              error={createWorkQueueMutation.error}
              onQueueNameChange={setWorkQueueName}
              onMessageChange={setWorkQueueMessage}
              onSubmit={handleWorkQueueSubmit}
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

function WorkQueuePanel({
  items,
  loading,
  queueName,
  message,
  submitting,
  error,
  onQueueNameChange,
  onMessageChange,
  onSubmit
}: {
  items: WorkQueueItem[];
  loading: boolean;
  queueName: string;
  message: string;
  submitting: boolean;
  error: unknown;
  onQueueNameChange: (value: string) => void;
  onMessageChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const statusCounts = items.reduce<Record<string, number>>((counts, item) => {
    counts[item.status] = (counts[item.status] ?? 0) + 1;
    return counts;
  }, {});
  const recentItems = [...items]
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .slice(0, 4);

  return (
    <section className="rounded-md border border-border bg-panel shadow-soft">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold">Queue durable</h2>
        <ListChecks className="h-4 w-4 text-accent" />
      </div>
      <form className="flex flex-col gap-3 p-4" onSubmit={onSubmit}>
        <input
          className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
          value={queueName}
          onChange={(event) => onQueueNameChange(event.target.value)}
          placeholder="default"
        />
        <input
          className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
          value={message}
          onChange={(event) => onMessageChange(event.target.value)}
          placeholder="message"
        />
        <button
          type="submit"
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-white disabled:opacity-60"
          disabled={submitting || queueName.trim().length === 0}
        >
          <Plus className="h-4 w-4" />
          <span>{submitting ? "Création" : "Ajouter"}</span>
        </button>
        {error ? (
          <p className="text-xs text-risk">
            {error instanceof Error ? error.message : "Création impossible."}
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
              {status}: {statusCounts[status] ?? 0}
            </span>
          ))}
        </div>
      </div>
      <div className="divide-y divide-border">
        {loading ? (
          <p className="px-4 py-3 text-sm text-muted">Chargement...</p>
        ) : recentItems.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">Aucun item.</p>
        ) : (
          recentItems.map((item) => (
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
              <p className="mt-1 text-[11px] text-muted">{formatDate(item.updated_at)}</p>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function workQueuePayloadLabel(payload: Record<string, unknown>): string {
  const action = typeof payload.action === "string" ? payload.action : "payload";
  const message = typeof payload.message === "string" ? payload.message : "";
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
        {metadataBoolean(service, "requires_api_key")
          ? "Secret stocké dans le vault local."
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
