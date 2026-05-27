"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Check,
  CheckCircle2,
  CircleDot,
  ExternalLink,
  Globe2,
  KeyRound,
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
  decideTaskReview,
  decideCredentialAccessRequest,
  disableConnectorConnection,
  getSystemReadiness,
  getProjectTimeline,
  listCredentialAccessRequests,
  listConnectorConnections,
  listHumanAssistanceRequests,
  listOperatorActions,
  listProjectBriefs,
  listWebProviders,
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
  type ProjectTimeline,
  type SystemReadinessItem,
  type SystemReadinessStatus,
  type WebProviderStatus
} from "../../lib/gateway-api";
import {
  createWorkQueueItem,
  listProjects,
  listServices,
  listWorkerHeartbeats,
  listWorkQueueItems,
  listWorkQueueSummary,
  recoverExpiredWorkQueueLeases,
  reviewWorkQueueItem,
  type ProjectRecord,
  type ServiceDefinition,
  type WorkerHeartbeatRecord,
  type WorkQueueItem,
  type WorkQueueRecoveryResult,
  type WorkQueueSummary
} from "../../lib/state-service-api";

const priorityOptions: GoalPriority[] = ["medium", "high", "critical", "low"];
const connectorModes: ConnectorConnectionMode[] = ["api_key", "no_key", "oauth"];
const connectorModeDetails: Record<
  ConnectorConnectionMode,
  { label: string; description: string; submitLabel: string }
> = {
  api_key: {
    label: "Clé API",
    description: "Stockage chiffré dans SecretVault.",
    submitLabel: "Stocker la clé"
  },
  no_key: {
    label: "Sans clé",
    description: "Activer un connecteur local ou public.",
    submitLabel: "Activer"
  },
  oauth: {
    label: "OAuth",
    description: "Créer une demande d'autorisation externe.",
    submitLabel: "Préparer OAuth"
  }
};
type WorkQueueAction = "project_reminder" | "log";
type TaskReviewMutationVariables = {
  taskId: string;
  decision: { action: "retry" | "cancel" | "update" };
};
type CredentialDecisionMutationVariables = {
  requestId: string;
  status: "approved" | "rejected";
};
type CredentialGrantMutationVariables = {
  requestId: string;
  serviceId: string;
};
type HumanAssistanceMutationVariables = {
  requestId: string;
  status: "answered" | "dismissed";
  response: string;
};

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
  active: "bg-ok-soft text-ok ring-ok/15",
  needs_oauth: "bg-warn-soft text-warn ring-warn/15",
  disabled: "bg-risk-soft text-risk ring-risk/15",
  stale: "bg-warn-soft text-warn ring-warn/15",
  healthy: "bg-ok-soft text-ok ring-ok/15",
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

function secondsSince(value?: string | null): number | null {
  if (!value) {
    return null;
  }
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return null;
  }
  return Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) {
    return "n/a";
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 48) {
    return `${hours}h`;
  }
  return `${Math.floor(hours / 24)}j`;
}

function formatCurrency(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat("fr-FR", {
      style: "currency",
      currency,
      maximumFractionDigits: 4
    }).format(value);
  } catch {
    return `${value.toFixed(4)} ${currency}`;
  }
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

function connectorConnectionCounts(
  connections: ConnectorConnectionRecord[]
): Record<ConnectorConnectionRecord["status"], number> {
  return connections.reduce<Record<ConnectorConnectionRecord["status"], number>>(
    (counts, connection) => {
      counts[connection.status] = (counts[connection.status] ?? 0) + 1;
      return counts;
    },
    { active: 0, disabled: 0, needs_oauth: 0 }
  );
}

function isConnectableService(service: ServiceDefinition): boolean {
  return service.enabled && ["external", "ai_provider", "tool_provider"].includes(service.kind);
}

function connectorServicePriority(
  service: ServiceDefinition,
  connection: ConnectorConnectionRecord | null
): number {
  if (connection?.status === "active") {
    return 0;
  }
  if (connection?.status === "needs_oauth") {
    return 1;
  }
  if (
    metadataString(service, "web_provider") !== null ||
    manualConnectionUrl(service) !== null ||
    hasOAuthAuthorizationLink(service)
  ) {
    return 2;
  }
  if (service.credential_scopes.length > 0) {
    return 3;
  }
  return 4;
}

function compareConnectorServices(
  left: ServiceDefinition,
  right: ServiceDefinition,
  connectionsByService: Map<string, ConnectorConnectionRecord>
): number {
  const leftPriority = connectorServicePriority(left, connectionsByService.get(left.id) ?? null);
  const rightPriority = connectorServicePriority(right, connectionsByService.get(right.id) ?? null);
  if (leftPriority !== rightPriority) {
    return leftPriority - rightPriority;
  }
  return left.name.localeCompare(right.name);
}

function metadataBoolean(service: ServiceDefinition | null, key: string): boolean {
  return service?.metadata[key] === true;
}

function metadataString(service: ServiceDefinition | null, key: string): string | null {
  const value = service?.metadata[key];
  return typeof value === "string" ? value : null;
}

function hasOAuthAuthorizationLink(service: ServiceDefinition): boolean {
  return (
    metadataString(service, "oauth_authorization_url") !== null ||
    metadataString(service, "connect_url") !== null
  );
}

function requiresOAuth(service: ServiceDefinition): boolean {
  return metadataBoolean(service, "requires_oauth") || hasOAuthAuthorizationLink(service);
}

function manualConnectionUrl(service: ServiceDefinition | null): string | null {
  return metadataString(service, "manual_connection_url");
}

function connectionSetupLabel(service: ServiceDefinition | null): string {
  return metadataString(service, "connection_setup_label") ?? "Préparer la connexion";
}

function connectionSetupInstructions(service: ServiceDefinition | null): string | null {
  return metadataString(service, "connection_setup_instructions");
}

function connectorModesForService(service: ServiceDefinition): ConnectorConnectionMode[] {
  const modes: ConnectorConnectionMode[] = [];
  const oauthRequired = requiresOAuth(service);
  if (
    metadataBoolean(service, "requires_api_key") ||
    (service.credential_scopes.length > 0 && !oauthRequired)
  ) {
    modes.push("api_key");
  }
  if (
    !metadataBoolean(service, "requires_api_key") &&
    !oauthRequired &&
    service.credential_scopes.length === 0
  ) {
    modes.push("no_key");
  }
  if (oauthRequired) {
    modes.push("oauth");
  }
  return modes.length > 0 ? modes : ["no_key"];
}

function selectedScopeSet(scopes: string[]): Set<string> {
  return new Set(scopes.filter(Boolean));
}

function openCredentialAccessRequests(
  requests: CredentialAccessRequest[]
): CredentialAccessRequest[] {
  return [...requests]
    .filter((request) => request.status === "requested" || request.status === "approved")
    .sort((left, right) => {
      if (left.status !== right.status) {
        return left.status === "requested" ? -1 : 1;
      }
      return right.created_at.localeCompare(left.created_at);
    });
}

function openHumanAssistanceRequests(
  requests: HumanAssistanceRequest[]
): HumanAssistanceRequest[] {
  return [...requests]
    .filter((request) => request.status === "requested")
    .sort((left, right) => {
      if (left.urgency !== right.urgency) {
        return priorityRank(right.urgency) - priorityRank(left.urgency);
      }
      return right.created_at.localeCompare(left.created_at);
    });
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

function secretVaultCanStoreConnectorSecrets(item: SystemReadinessItem | null): boolean {
  return (
    item?.id === "secret_vault" &&
    item.status === "ready" &&
    evidenceBoolean(item, "writable") &&
    evidenceBoolean(item, "encryption_enabled") &&
    evidenceNumber(item, "plaintext_secret_count") === 0
  );
}

function secretVaultBadges(item: SystemReadinessItem): string[] {
  if (item.id !== "secret_vault") {
    return [];
  }
  const encrypted = evidenceBoolean(item, "encryption_enabled");
  const strict = evidenceBoolean(item, "encryption_required");
  const plaintextCount = evidenceNumber(item, "plaintext_secret_count");
  return [
    strict ? "mode strict" : "mode dev",
    encrypted ? "chiffré" : "non chiffré",
    plaintextCount > 0 ? `${plaintextCount} plaintext` : "0 plaintext"
  ];
}

export default function SynarchAppPage() {
  const queryClient = useQueryClient();
  const [projectTitle, setProjectTitle] = useState("");
  const [goal, setGoal] = useState("");
  const [successDefinition, setSuccessDefinition] = useState("");
  const [firstNextAction, setFirstNextAction] = useState("");
  const [projectReminderAt, setProjectReminderAt] = useState("");
  const [projectSubmitNotice, setProjectSubmitNotice] = useState<string | null>(null);
  const [projectSearch, setProjectSearch] = useState("");
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
  const [workQueueRecoveryResult, setWorkQueueRecoveryResult] =
    useState<WorkQueueRecoveryResult | null>(null);
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
  const webProvidersQuery = useQuery({
    queryKey: ["app-web-providers"],
    queryFn: listWebProviders
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
  const globalActionsQuery = useQuery({
    queryKey: ["app-operator-actions", "all"],
    queryFn: () => listOperatorActions(),
    refetchInterval: 15_000
  });

  const orderedProjects = useMemo(
    () =>
      [...(projectsQuery.data ?? [])].sort((left, right) => {
        const createdDelta = right.created_at.localeCompare(left.created_at);
        if (createdDelta !== 0) {
          return createdDelta;
        }
        return left.title.localeCompare(right.title);
      }),
    [projectsQuery.data]
  );
  const visibleProjects = useMemo(() => {
    const query = projectSearch.trim().toLocaleLowerCase("fr-FR");
    if (query.length === 0) {
      return orderedProjects;
    }
    return orderedProjects.filter((project) =>
      [project.title, project.goal, project.id, project.owner_agent_id]
        .join(" ")
        .toLocaleLowerCase("fr-FR")
        .includes(query)
    );
  }, [orderedProjects, projectSearch]);
  const selectedProject =
    orderedProjects.find((project) => project.id === selectedProjectId) ??
    visibleProjects[0] ??
    orderedProjects[0] ??
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
  const timelineQuery = useQuery({
    queryKey: ["app-project-timeline", effectiveProjectId],
    queryFn: () => getProjectTimeline(effectiveProjectId ?? ""),
    enabled: effectiveProjectId !== null,
    refetchInterval: 15_000
  });
  const connectorServices = useMemo(
    () => (servicesQuery.data ?? []).filter(isConnectableService),
    [servicesQuery.data]
  );
  const connectionsByService = connectionByService(connectionsQuery.data ?? []);
  const orderedConnectorServices = useMemo(
    () =>
      [...connectorServices].sort((left, right) =>
        compareConnectorServices(left, right, connectionsByService)
      ),
    [connectorServices, connectionsByService]
  );
  const selectedService =
    orderedConnectorServices.find((service) => service.id === selectedServiceId) ??
    orderedConnectorServices[0] ??
    null;
  const serviceScopes = selectedService?.credential_scopes ?? [];
  const selectedScopes = selectedService
    ? (scopeSelectionsByService[selectedService.id] ?? serviceScopes)
    : [];
  const selectedScopesSet = selectedScopeSet(selectedScopes);
  const selectedConnection = selectedService
    ? connectionsByService.get(selectedService.id) ?? null
    : null;
  const activeConnection =
    selectedService && lastConnectorConnection?.service_id === selectedService.id
      ? lastConnectorConnection
      : selectedConnection;
  const connectorCounts = connectorConnectionCounts(connectionsQuery.data ?? []);
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
  const secretVaultReadiness =
    readinessQuery.data?.items.find((item) => item.id === "secret_vault") ?? null;
  const connectorSecretVaultReady = secretVaultCanStoreConnectorSecrets(secretVaultReadiness);
  const apiKeyConnectorBlocked =
    effectiveConnectorMode === "api_key" && !connectorSecretVaultReady;
  const workQueueWorkerReadiness = readinessQuery.data?.items.find(
    (item) => item.id === "work_queue_worker"
  );
  const workerStaleAfterSeconds = workQueueWorkerReadiness
    ? evidenceNumber(workQueueWorkerReadiness, "stale_after_seconds") || 120
    : 120;
  const visibleCredentialRequests = useMemo(
    () => visibleCredentialAccessRequests(credentialRequestsQuery.data ?? [], effectiveProjectId),
    [credentialRequestsQuery.data, effectiveProjectId]
  );
  const visibleHumanRequests = useMemo(
    () => visibleHumanAssistanceRequests(humanAssistanceQuery.data ?? [], effectiveProjectId),
    [humanAssistanceQuery.data, effectiveProjectId]
  );
  const globalCredentialRequests = useMemo(
    () => openCredentialAccessRequests(credentialRequestsQuery.data ?? []),
    [credentialRequestsQuery.data]
  );
  const globalHumanRequests = useMemo(
    () => openHumanAssistanceRequests(humanAssistanceQuery.data ?? []),
    [humanAssistanceQuery.data]
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
    void queryClient.invalidateQueries({ queryKey: ["app-project-timeline"] });
  };

  const submitGoalMutation = useMutation({
    mutationFn: async () => {
      const title = projectTitle.trim();
      const objective = goal.trim();
      const success = successDefinition.trim();
      const firstAction = firstNextAction.trim();
      const submission = await submitGoal({
        title: title || undefined,
        goal: objective,
        priority,
        requester: "local-user",
        constraints: [
          "Découper l'objectif en étapes vérifiables.",
          "Demander une action humaine pour captcha, accès, choix critique ou document ambigu."
        ],
        context: {
          source: "synarch_app",
          first_next_action: firstAction || undefined,
          success_definition: success || undefined
        }
      });
      let reminderQueued = false;
      let reminderError: string | null = null;
      if (projectReminderAt.trim().length > 0) {
        try {
          await createWorkQueueItem({
            queue_name: "reminders",
            payload: {
              action: "project.reminder.emit",
              project_id: submission.project.id,
              message: firstAction || `Faire le point sur ${submission.project.title}`,
              source: "synarch_app_onboarding"
            },
            priority: 80,
            max_attempts: 3,
            run_after_at: new Date(projectReminderAt).toISOString()
          });
          reminderQueued = true;
        } catch (error) {
          reminderError =
            error instanceof Error ? error.message : "Rappel non planifié.";
        }
      }
      return { submission, reminderQueued, reminderError };
    },
    onSuccess: (result) => {
      setProjectTitle("");
      setGoal("");
      setSuccessDefinition("");
      setFirstNextAction("");
      setProjectReminderAt("");
      setSelectedProjectId(result.submission.project.id);
      setProjectSubmitNotice(
        result.reminderError
          ? `Projet créé. Rappel non planifié: ${result.reminderError}`
          : result.reminderQueued
            ? "Projet créé avec rappel durable."
            : "Projet créé."
      );
      void queryClient.invalidateQueries({ queryKey: ["app-projects"] });
      void queryClient.invalidateQueries({ queryKey: ["app-project-briefs"] });
      void queryClient.invalidateQueries({ queryKey: ["app-operator-actions"] });
      void queryClient.invalidateQueries({ queryKey: ["app-project-timeline"] });
      void queryClient.invalidateQueries({ queryKey: ["app-work-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["app-work-queue-summary"] });
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
      void queryClient.invalidateQueries({ queryKey: ["app-project-timeline", effectiveProjectId] });
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
      void queryClient.invalidateQueries({ queryKey: ["app-web-providers"] });
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
      void queryClient.invalidateQueries({ queryKey: ["app-web-providers"] });
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

  const recoverWorkQueueLeasesMutation = useMutation({
    mutationFn: recoverExpiredWorkQueueLeases,
    onSuccess: (result) => {
      setWorkQueueRecoveryResult(result);
      void queryClient.invalidateQueries({ queryKey: ["app-work-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["app-work-queue-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["app-worker-heartbeats"] });
      void queryClient.invalidateQueries({ queryKey: ["app-readiness"] });
    }
  });

  const credentialDecisionMutation = useMutation({
    mutationFn: decideCredentialAccessRequest,
    onSuccess: invalidateOperatorState
  });

  const taskReviewMutation = useMutation({
    mutationFn: decideTaskReview,
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
    setProjectSubmitNotice(null);
    submitGoalMutation.mutate();
  };

  const handleConnectSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (effectiveConnectorMode === "api_key" && apiKey.trim().length === 0) {
      return;
    }
    if (apiKeyConnectorBlocked) {
      return;
    }
    connectMutation.mutate();
  };

  const handleConnectorServiceSelect = (nextServiceId: string) => {
    const nextService =
      connectorServices.find((service) => service.id === nextServiceId) ?? null;
    setSelectedServiceId(nextService?.id ?? null);
    setConnectorMode(nextService ? connectorModesForService(nextService)[0] ?? "no_key" : "no_key");
    setLastConnectorConnection(null);
    setApiKey("");
  };

  const handleWebProviderSelect = (provider: WebProviderStatus) => {
    const service = connectorServices.find(
      (candidate) => metadataString(candidate, "web_provider") === provider.provider_id
    );
    if (!service) {
      return;
    }
    handleConnectorServiceSelect(service.id);
  };

  const handleWorkQueueSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    createWorkQueueMutation.mutate();
  };

  const handleWorkQueueReview = (itemId: string, action: "retry" | "dead_letter") => {
    reviewWorkQueueMutation.mutate({ itemId, action });
  };

  const handleWorkQueueRecovery = () => {
    recoverWorkQueueLeasesMutation.mutate();
  };

  const handleCredentialDecision = (
    requestId: string,
    status: "approved" | "rejected"
  ) => {
    credentialDecisionMutation.mutate({ requestId, status });
  };

  const handleTaskReviewDecision = (
    action: OperatorAction,
    reviewAction: "retry" | "cancel"
  ) => {
    const taskId = action.task_id ?? action.target_id;
    taskReviewMutation.mutate({
      taskId,
      decision: {
        action: reviewAction,
        reason:
          reviewAction === "retry"
            ? "Retry requested from Synarch app action center."
            : "Cancel requested from Synarch app action center."
      }
    });
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
                void actionsQuery.refetch();
                void globalActionsQuery.refetch();
                void timelineQuery.refetch();
              }}
              title="Rafraîchir l'état système"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Rafraîchir</span>
            </button>
          </div>
        </header>

        <GlobalActionCenterPanel
          actions={globalActionsQuery.data ?? []}
          credentialRequests={globalCredentialRequests}
          humanRequests={globalHumanRequests}
          projects={projectsQuery.data ?? []}
          servicesById={servicesById}
          humanResponsesById={humanResponsesById}
          loading={
            globalActionsQuery.isLoading ||
            credentialRequestsQuery.isLoading ||
            humanAssistanceQuery.isLoading
          }
          selectedProjectId={effectiveProjectId}
          taskReviewPending={taskReviewMutation.isPending}
          taskReviewVariables={taskReviewMutation.variables}
          taskReviewError={taskReviewMutation.error}
          credentialDecisionPending={credentialDecisionMutation.isPending}
          credentialGrantPending={credentialGrantMutation.isPending}
          credentialDecisionVariables={credentialDecisionMutation.variables}
          credentialGrantVariables={credentialGrantMutation.variables}
          credentialError={credentialDecisionMutation.error ?? credentialGrantMutation.error}
          humanAssistancePending={humanAssistanceMutation.isPending}
          humanAssistanceVariables={humanAssistanceMutation.variables}
          humanError={humanAssistanceMutation.error}
          onSelectProject={setSelectedProjectId}
          onTaskReviewDecision={handleTaskReviewDecision}
          onCredentialDecision={handleCredentialDecision}
          onCredentialGrant={handleCredentialGrant}
          onHumanResponseChange={handleHumanResponseChange}
          onHumanResolution={handleHumanResolution}
        />

        <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)_420px]">
          <aside className="flex min-w-0 flex-col gap-4">
            <section className="rounded-md border border-border bg-panel shadow-soft">
              <div className="border-b border-border px-4 py-3">
                <h2 className="text-sm font-semibold">Nouveau projet</h2>
              </div>
              <form className="flex flex-col gap-3 p-4" onSubmit={handleGoalSubmit}>
                <input
                  className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
                  value={projectTitle}
                  onChange={(event) => setProjectTitle(event.target.value)}
                  placeholder="Titre projet"
                />
                <textarea
                  className="min-h-28 resize-y rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus:border-accent"
                  value={goal}
                  onChange={(event) => setGoal(event.target.value)}
                  placeholder="Objectif"
                />
                <input
                  className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
                  value={successDefinition}
                  onChange={(event) => setSuccessDefinition(event.target.value)}
                  placeholder="Résultat attendu"
                />
                <textarea
                  className="min-h-20 resize-y rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus:border-accent"
                  value={firstNextAction}
                  onChange={(event) => setFirstNextAction(event.target.value)}
                  placeholder="Première action"
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
                <input
                  className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
                  type="datetime-local"
                  value={projectReminderAt}
                  onChange={(event) => setProjectReminderAt(event.target.value)}
                  aria-label="Rappel"
                />
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
                {projectSubmitNotice ? (
                  <p className="text-xs text-ok">{projectSubmitNotice}</p>
                ) : null}
              </form>
            </section>

            <section className="rounded-md border border-border bg-panel shadow-soft">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h2 className="text-sm font-semibold">Projets</h2>
                <span className="text-xs text-muted">{visibleProjects.length}</span>
              </div>
              <div className="border-b border-border px-4 py-3">
                <input
                  aria-label="Rechercher un projet"
                  className="h-9 w-full rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
                  value={projectSearch}
                  onChange={(event) => setProjectSearch(event.target.value)}
                  placeholder="Rechercher projet, objectif, agent"
                />
              </div>
              <div className="max-h-[520px] overflow-auto">
                {projectsQuery.isLoading ? (
                  <p className="px-4 py-3 text-sm text-muted">Chargement...</p>
                ) : orderedProjects.length === 0 ? (
                  <p className="px-4 py-3 text-sm text-muted">Aucun projet.</p>
                ) : visibleProjects.length === 0 ? (
                  <p className="px-4 py-3 text-sm text-muted">Aucun résultat.</p>
                ) : (
                  visibleProjects.map((project) => (
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
              <ActionPanel
                actions={activeActions}
                loading={actionsQuery.isLoading}
                taskReviewPending={taskReviewMutation.isPending}
                taskReviewVariables={taskReviewMutation.variables}
                taskReviewError={taskReviewMutation.error}
                onTaskReviewDecision={handleTaskReviewDecision}
              />
            </div>
            <ProjectTimelinePanel
              timeline={timelineQuery.data ?? null}
              loading={timelineQuery.isLoading}
              error={timelineQuery.error}
            />
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
                <div>
                  <h2 className="text-sm font-semibold">Connecteurs</h2>
                  <p className="text-xs text-muted">
                    {connectorCounts.active} actifs / {connectorCounts.needs_oauth} OAuth en attente
                  </p>
                </div>
                <PlugZap className="h-4 w-4 shrink-0 text-accent" />
              </div>
              <ConnectorConnectionOverview
                connections={connectionsQuery.data ?? []}
                services={orderedConnectorServices}
                loading={connectionsQuery.isLoading || servicesQuery.isLoading}
                selectedServiceId={selectedService?.id ?? null}
                onSelectService={handleConnectorServiceSelect}
              />
              <form className="flex flex-col gap-3 p-4" onSubmit={handleConnectSubmit}>
                <select
                  className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
                  value={selectedService?.id ?? ""}
                  onChange={(event) => handleConnectorServiceSelect(event.target.value)}
                >
                  {orderedConnectorServices.map((service) => (
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
                    {manualConnectionUrl(selectedService) ? (
                      <div className="mt-3 rounded-md border border-border bg-white p-2">
                        {connectionSetupInstructions(selectedService) ? (
                          <p className="mb-2 text-[11px] text-muted">
                            {connectionSetupInstructions(selectedService)}
                          </p>
                        ) : null}
                        <a
                          href={manualConnectionUrl(selectedService) ?? "#"}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex h-8 items-center gap-2 rounded-md border border-border px-2 text-xs font-semibold text-ink hover:bg-slate-50"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          <span>{connectionSetupLabel(selectedService)}</span>
                        </a>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                <ConnectorSetupSteps
                  service={selectedService}
                  connection={activeConnection}
                  mode={effectiveConnectorMode}
                  hasApiKey={apiKey.trim().length > 0}
                />

                {effectiveConnectorMode === "api_key" ? (
                  <SecretVaultConnectorGate
                    item={secretVaultReadiness}
                    loading={readinessQuery.isLoading}
                  />
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
                      className={`min-h-16 rounded-md border px-2 py-2 text-left text-xs ${
                        effectiveConnectorMode === mode
                          ? "border-accent bg-accent-soft text-accent"
                          : "border-border bg-white text-muted"
                      }`}
                      onClick={() => setConnectorMode(mode)}
                    >
                      <span className="block font-semibold">{connectorModeDetails[mode].label}</span>
                      <span className="mt-1 block leading-snug">
                        {connectorModeDetails[mode].description}
                      </span>
                    </button>
                  ))}
                </div>

                {effectiveConnectorMode === "api_key" ? (
                  <input
                    className="h-10 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-accent"
                    type="password"
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    placeholder="Clé API à stocker dans SecretVault"
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
                    apiKeyConnectorBlocked ||
                    (effectiveConnectorMode === "api_key" && apiKey.trim().length === 0)
                  }
                >
                  <KeyRound className="h-4 w-4" />
                  <span>
                    {connectMutation.isPending
                      ? "Connexion"
                      : connectorModeDetails[effectiveConnectorMode].submitLabel}
                  </span>
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

            <WebProviderPanel
              providers={webProvidersQuery.data ?? []}
              services={orderedConnectorServices}
              connections={connectionsQuery.data ?? []}
              loading={webProvidersQuery.isLoading || servicesQuery.isLoading}
              selectedServiceId={selectedService?.id ?? null}
              onSelectProvider={handleWebProviderSelect}
            />

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
                      {secretVaultBadges(item).length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {secretVaultBadges(item).map((badge) => (
                            <span
                              key={badge}
                              className="rounded-md bg-slate-50 px-2 py-1 text-[11px] font-semibold text-muted ring-1 ring-border"
                            >
                              {badge}
                            </span>
                          ))}
                        </div>
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
              staleAfterSeconds={workerStaleAfterSeconds}
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
              recovering={recoverWorkQueueLeasesMutation.isPending}
              canSubmit={canSubmitWorkQueue}
              error={createWorkQueueMutation.error}
              reviewError={reviewWorkQueueMutation.error}
              recoveryError={recoverWorkQueueLeasesMutation.error}
              recoveryResult={workQueueRecoveryResult}
              onQueueNameChange={setWorkQueueName}
              onActionChange={setWorkQueueAction}
              onMessageChange={setWorkQueueMessage}
              onRunAfterChange={setWorkQueueRunAfter}
              onSubmit={handleWorkQueueSubmit}
              onReview={handleWorkQueueReview}
              onRecoverLeases={handleWorkQueueRecovery}
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

function GlobalActionCenterPanel({
  actions,
  credentialRequests,
  humanRequests,
  projects,
  servicesById,
  humanResponsesById,
  loading,
  selectedProjectId,
  taskReviewPending,
  taskReviewVariables,
  taskReviewError,
  credentialDecisionPending,
  credentialGrantPending,
  credentialDecisionVariables,
  credentialGrantVariables,
  credentialError,
  humanAssistancePending,
  humanAssistanceVariables,
  humanError,
  onSelectProject,
  onTaskReviewDecision,
  onCredentialDecision,
  onCredentialGrant,
  onHumanResponseChange,
  onHumanResolution
}: {
  actions: OperatorAction[];
  credentialRequests: CredentialAccessRequest[];
  humanRequests: HumanAssistanceRequest[];
  projects: ProjectRecord[];
  servicesById: Map<string, ServiceDefinition>;
  humanResponsesById: Record<string, string>;
  loading: boolean;
  selectedProjectId: string | null;
  taskReviewPending: boolean;
  taskReviewVariables?: TaskReviewMutationVariables;
  taskReviewError: unknown;
  credentialDecisionPending: boolean;
  credentialGrantPending: boolean;
  credentialDecisionVariables?: CredentialDecisionMutationVariables;
  credentialGrantVariables?: CredentialGrantMutationVariables;
  credentialError: unknown;
  humanAssistancePending: boolean;
  humanAssistanceVariables?: HumanAssistanceMutationVariables;
  humanError: unknown;
  onSelectProject: (projectId: string) => void;
  onTaskReviewDecision: (action: OperatorAction, reviewAction: "retry" | "cancel") => void;
  onCredentialDecision: (requestId: string, status: "approved" | "rejected") => void;
  onCredentialGrant: (requestId: string, serviceId: string) => void;
  onHumanResponseChange: (requestId: string, response: string) => void;
  onHumanResolution: (requestId: string, status: "answered" | "dismissed") => void;
}) {
  const projectsById = new Map(projects.map((project) => [project.id, project]));
  const actionCounts = actions.reduce<Record<OperatorAction["kind"], number>>(
    (counts, action) => {
      counts[action.kind] = (counts[action.kind] ?? 0) + 1;
      return counts;
    },
    {
      connector_job_review: 0,
      credential_access: 0,
      human_assistance: 0,
      task_review: 0
    }
  );
  const orderedActions = [...actions]
    .filter((action) => !["credential_access", "human_assistance"].includes(action.kind))
    .sort((left, right) => {
      const priorityDelta = priorityRank(right.priority) - priorityRank(left.priority);
      if (priorityDelta !== 0) {
        return priorityDelta;
      }
      return right.created_at.localeCompare(left.created_at);
    })
    .slice(0, 8);
  const globalCredentialRows = credentialRequests.slice(0, 4);
  const globalHumanRows = humanRequests.slice(0, 4);
  const hasRows =
    orderedActions.length > 0 || globalCredentialRows.length > 0 || globalHumanRows.length > 0;
  const totalOpenCount =
    actions.length +
    Math.max(0, credentialRequests.length - actionCounts.credential_access) +
    Math.max(0, humanRequests.length - actionCounts.human_assistance);

  return (
    <section className="rounded-md border border-border bg-panel shadow-soft">
      <div className="flex flex-col gap-3 border-b border-border px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">Centre d&apos;actions global</h2>
          <p className="text-xs text-muted">
            Toutes les décisions bloquantes, indépendamment du projet sélectionné.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-md bg-warn-soft px-2 py-1 text-warn ring-1 ring-warn/15">
            total: {totalOpenCount}
          </span>
          <span className="rounded-md bg-risk-soft px-2 py-1 text-risk ring-1 ring-risk/15">
            reviews: {actionCounts.task_review}
          </span>
          <span className="rounded-md bg-info-soft px-2 py-1 text-info ring-1 ring-info/15">
            credentials: {credentialRequests.length || actionCounts.credential_access}
          </span>
          <span className="rounded-md bg-slate-100 px-2 py-1 text-muted ring-1 ring-border">
            connecteurs: {actionCounts.connector_job_review}
          </span>
          <span className="rounded-md bg-slate-100 px-2 py-1 text-muted ring-1 ring-border">
            humain: {humanRequests.length || actionCounts.human_assistance}
          </span>
        </div>
      </div>

      {loading ? (
        <p className="px-4 py-3 text-sm text-muted">Chargement...</p>
      ) : !hasRows ? (
        <p className="px-4 py-3 text-sm text-ok">Aucune action ouverte.</p>
      ) : (
        <>
          {globalCredentialRows.length > 0 ? (
            <div className="border-b border-border bg-slate-50/60 px-4 py-3">
              <div className="mb-2 flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-accent" />
                <h3 className="text-xs font-semibold uppercase text-muted">
                  Credentials à traiter
                </h3>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                {globalCredentialRows.map((request) => (
                  <CredentialRequestCard
                    key={request.id}
                    request={request}
                    servicesById={servicesById}
                    credentialDecisionPending={credentialDecisionPending}
                    credentialGrantPending={credentialGrantPending}
                    credentialDecisionVariables={credentialDecisionVariables}
                    credentialGrantVariables={credentialGrantVariables}
                    onCredentialDecision={onCredentialDecision}
                    onCredentialGrant={onCredentialGrant}
                  />
                ))}
              </div>
            </div>
          ) : null}
          {globalHumanRows.length > 0 ? (
            <div className="border-b border-border bg-slate-50/60 px-4 py-3">
              <div className="mb-2 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-warn" />
                <h3 className="text-xs font-semibold uppercase text-muted">
                  Assistance humaine à traiter
                </h3>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                {globalHumanRows.map((request) => (
                  <HumanAssistanceRequestCard
                    key={request.id}
                    request={request}
                    response={humanResponsesById[request.id] ?? ""}
                    humanAssistancePending={humanAssistancePending}
                    humanAssistanceVariables={humanAssistanceVariables}
                    onHumanResponseChange={onHumanResponseChange}
                    onHumanResolution={onHumanResolution}
                  />
                ))}
              </div>
            </div>
          ) : null}
          {orderedActions.length > 0 ? (
            <div className="grid gap-0 divide-y divide-border lg:grid-cols-2 lg:divide-x lg:divide-y-0">
              {orderedActions.map((action) => {
                const project = action.project_id ? projectsById.get(action.project_id) : null;
                const taskId = action.task_id ?? action.target_id;
                const taskReviewActive =
                  taskReviewPending && taskReviewVariables?.taskId === taskId;
                return (
                  <article key={action.id} className="min-w-0 px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold">{action.title}</p>
                        <p className="truncate text-xs text-muted">
                          {project?.title ?? action.project_id ?? "sans projet"} / {action.agent_id ?? "agent"}
                        </p>
                      </div>
                      <span
                        className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${statusClass(action.status)}`}
                      >
                        {action.kind}
                      </span>
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs text-muted">
                      {action.recommended_action}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
                      {action.project_id ? (
                        <button
                          type="button"
                          className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-2 text-xs font-medium disabled:opacity-50 ${
                            selectedProjectId === action.project_id
                              ? "border-accent bg-accent-soft text-accent"
                              : "border-border text-ink hover:bg-slate-50"
                          }`}
                          onClick={() => onSelectProject(action.project_id ?? "")}
                        >
                          <Workflow className="h-3.5 w-3.5" />
                          <span>{selectedProjectId === action.project_id ? "Projet ouvert" : "Ouvrir projet"}</span>
                        </button>
                      ) : null}
                      {action.kind === "task_review" ? (
                        <>
                          <button
                            type="button"
                            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2 text-xs font-medium text-ink disabled:opacity-50"
                            disabled={taskReviewPending}
                            onClick={() => onTaskReviewDecision(action, "retry")}
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                            <span>
                              {taskReviewActive && taskReviewVariables?.decision.action === "retry"
                                ? "Retry"
                                : "Réessayer"}
                            </span>
                          </button>
                          <button
                            type="button"
                            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-risk/30 px-2 text-xs font-medium text-risk disabled:opacity-50"
                            disabled={taskReviewPending}
                            onClick={() => onTaskReviewDecision(action, "cancel")}
                          >
                            <X className="h-3.5 w-3.5" />
                            <span>
                              {taskReviewActive && taskReviewVariables?.decision.action === "cancel"
                                ? "Annulation"
                                : "Annuler"}
                            </span>
                          </button>
                        </>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : null}
        </>
      )}

      {credentialError ? (
        <p className="border-t border-border px-4 py-2 text-xs text-risk">
          {credentialError instanceof Error
            ? credentialError.message
            : "Décision credential impossible."}
        </p>
      ) : null}
      {taskReviewError ? (
        <p className="border-t border-border px-4 py-2 text-xs text-risk">
          {taskReviewError instanceof Error
            ? taskReviewError.message
            : "Décision de review impossible."}
        </p>
      ) : null}
      {humanError ? (
        <p className="border-t border-border px-4 py-2 text-xs text-risk">
          {humanError instanceof Error ? humanError.message : "Réponse humaine impossible."}
        </p>
      ) : null}
    </section>
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

function ActionPanel({
  actions,
  loading,
  taskReviewPending,
  taskReviewVariables,
  taskReviewError,
  onTaskReviewDecision
}: {
  actions: OperatorAction[];
  loading: boolean;
  taskReviewPending: boolean;
  taskReviewVariables?: TaskReviewMutationVariables;
  taskReviewError: unknown;
  onTaskReviewDecision: (action: OperatorAction, reviewAction: "retry" | "cancel") => void;
}) {
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
            {action.kind === "task_review" ? (
              <div className="mt-3 flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2 text-xs font-medium text-ink disabled:opacity-50"
                  disabled={taskReviewPending}
                  onClick={() => onTaskReviewDecision(action, "retry")}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  <span>
                    {taskReviewPending &&
                    taskReviewVariables?.taskId === (action.task_id ?? action.target_id) &&
                    taskReviewVariables.decision.action === "retry"
                      ? "Retry"
                      : "Réessayer"}
                  </span>
                </button>
                <button
                  type="button"
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border border-risk/30 px-2 text-xs font-medium text-risk disabled:opacity-50"
                  disabled={taskReviewPending}
                  onClick={() => onTaskReviewDecision(action, "cancel")}
                >
                  <X className="h-3.5 w-3.5" />
                  <span>
                    {taskReviewPending &&
                    taskReviewVariables?.taskId === (action.task_id ?? action.target_id) &&
                    taskReviewVariables.decision.action === "cancel"
                      ? "Annulation"
                      : "Annuler"}
                  </span>
                </button>
              </div>
            ) : null}
          </div>
        ))}
      </div>
      {taskReviewError ? (
        <p className="border-t border-border px-3 py-2 text-xs text-risk">
          {taskReviewError instanceof Error
            ? taskReviewError.message
            : "Décision de review impossible."}
        </p>
      ) : null}
    </div>
  );
}

function ProjectTimelinePanel({
  timeline,
  loading,
  error
}: {
  timeline: ProjectTimeline | null;
  loading: boolean;
  error: unknown;
}) {
  if (loading) {
    return (
      <section className="border-t border-border px-4 py-4">
        <PanelEmpty icon={<Workflow className="h-4 w-4" />} text="Chargement timeline..." />
      </section>
    );
  }
  if (error) {
    return (
      <section className="border-t border-border px-4 py-4">
        <p className="rounded-md bg-risk-soft px-3 py-3 text-sm text-risk">
          {error instanceof Error ? error.message : "Timeline projet indisponible."}
        </p>
      </section>
    );
  }
  if (!timeline) {
    return (
      <section className="border-t border-border px-4 py-4">
        <PanelEmpty icon={<Workflow className="h-4 w-4" />} text="Aucun projet suivi." />
      </section>
    );
  }

  const orderedTasks = [...timeline.tasks].sort((left, right) => left.sequence - right.sequence);
  const latestEvents = [...timeline.events]
    .sort((left, right) => right.timestamp.localeCompare(left.timestamp))
    .slice(0, 6);
  const latestMemoryItems = [...timeline.memory_items]
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(0, 4);
  const latestCosts = [...timeline.cost_records]
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(0, 3);
  const currency = timeline.currency || "USD";

  return (
    <section className="border-t border-border px-4 py-4">
      <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">Exécution projet</h3>
          <p className="truncate text-xs text-muted">{timeline.project_id}</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="rounded-md bg-accent-soft px-2 py-1 text-accent ring-1 ring-accent/15">
            tâches: {timeline.tasks.length}
          </span>
          <span className="rounded-md bg-info-soft px-2 py-1 text-info ring-1 ring-info/15">
            événements: {timeline.events.length}
          </span>
          <span className="rounded-md bg-slate-100 px-2 py-1 text-muted ring-1 ring-border">
            mémoire: {timeline.memory_items.length}
          </span>
          <span className="rounded-md bg-ok-soft px-2 py-1 text-ok ring-1 ring-ok/15">
            coût: {formatCurrency(timeline.total_cost, currency)}
          </span>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <div className="min-w-0 rounded-md border border-border">
          <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
            <h4 className="text-xs font-semibold uppercase text-muted">Tâches</h4>
            <span className="text-xs text-muted">{orderedTasks.length}</span>
          </div>
          <div className="max-h-[420px] divide-y divide-border overflow-auto">
            {orderedTasks.length === 0 ? (
              <p className="px-3 py-3 text-sm text-muted">Aucune tâche.</p>
            ) : (
              orderedTasks.map((task) => (
                <article key={task.id} className="px-3 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">
                        {task.sequence}. {task.title}
                      </p>
                      <p className="truncate text-xs text-muted">
                        {task.assigned_agent_id}
                        {task.depends_on.length > 0 ? ` / dépend de ${task.depends_on.length}` : ""}
                      </p>
                    </div>
                    <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${statusClass(task.status)}`}>
                      {task.status}
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-xs text-muted">{task.description}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <span className="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-muted ring-1 ring-border">
                      essais {task.attempt_count}/{task.max_attempts}
                    </span>
                    {task.required_tools.slice(0, 3).map((tool) => (
                      <span
                        key={tool}
                        className="rounded-md bg-warn-soft px-2 py-1 text-[11px] text-warn ring-1 ring-warn/15"
                      >
                        {tool}
                      </span>
                    ))}
                    {task.acceptance_criteria[0] ? (
                      <span className="truncate rounded-md bg-white px-2 py-1 text-[11px] text-muted ring-1 ring-border">
                        {task.acceptance_criteria[0]}
                      </span>
                    ) : null}
                  </div>
                </article>
              ))
            )}
          </div>
        </div>

        <div className="grid min-w-0 gap-4">
          <div className="min-w-0 rounded-md border border-border">
            <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
              <h4 className="text-xs font-semibold uppercase text-muted">Journal</h4>
              <span className="text-xs text-muted">audit {timeline.audit_logs.length}</span>
            </div>
            <div className="max-h-56 divide-y divide-border overflow-auto">
              {latestEvents.length === 0 ? (
                <p className="px-3 py-3 text-sm text-muted">Aucun événement.</p>
              ) : (
                latestEvents.map((event) => (
                  <article key={event.id} className="px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium">{event.type}</p>
                      <span className="shrink-0 text-[11px] text-muted">
                        {formatDate(event.timestamp)}
                      </span>
                    </div>
                    <p className="truncate text-xs text-muted">
                      {event.target ?? "sans cible"}
                      {event.trace_id ? ` / ${event.trace_id}` : ""}
                    </p>
                    <p className="mt-1 line-clamp-1 text-[11px] text-muted">
                      {payloadPreview(event.payload)}
                    </p>
                  </article>
                ))
              )}
            </div>
          </div>

          <div className="min-w-0 rounded-md border border-border">
            <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
              <h4 className="text-xs font-semibold uppercase text-muted">Mémoire</h4>
              <span className="text-xs text-muted">{timeline.memory_items.length}</span>
            </div>
            <div className="divide-y divide-border">
              {latestMemoryItems.length === 0 ? (
                <p className="px-3 py-3 text-sm text-muted">Aucune mémoire projet.</p>
              ) : (
                latestMemoryItems.map((item) => (
                  <article key={item.id} className="px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium">{item.scope}</p>
                      <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${statusClass(item.status)}`}>
                        {item.status}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-muted">{item.content}</p>
                  </article>
                ))
              )}
            </div>
          </div>

          <div className="min-w-0 rounded-md border border-border">
            <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
              <h4 className="text-xs font-semibold uppercase text-muted">Coûts IA</h4>
              <span className="text-xs text-muted">
                {formatCurrency(timeline.total_cost, currency)}
              </span>
            </div>
            <div className="divide-y divide-border">
              {latestCosts.length === 0 ? (
                <p className="px-3 py-3 text-sm text-muted">Aucun coût enregistré.</p>
              ) : (
                latestCosts.map((cost) => (
                  <article key={cost.id} className="px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium">{cost.model_id}</p>
                      <span className="shrink-0 text-xs font-semibold">
                        {formatCurrency(cost.total_cost, cost.currency)}
                      </span>
                    </div>
                    <p className="truncate text-xs text-muted">
                      {cost.provider_id} / in {cost.input_tokens} / out {cost.output_tokens}
                    </p>
                  </article>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function payloadPreview(payload: Record<string, unknown>): string {
  const entries = Object.entries(payload).slice(0, 3);
  if (entries.length === 0) {
    return "payload vide";
  }
  return entries
    .map(([key, value]) => {
      if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        return `${key}: ${String(value)}`;
      }
      if (Array.isArray(value)) {
        return `${key}: ${value.length} items`;
      }
      return `${key}: object`;
    })
    .join(" / ");
}

function CredentialRequestCard({
  request,
  servicesById,
  credentialDecisionPending,
  credentialGrantPending,
  credentialDecisionVariables,
  credentialGrantVariables,
  onCredentialDecision,
  onCredentialGrant
}: {
  request: CredentialAccessRequest;
  servicesById: Map<string, ServiceDefinition>;
  credentialDecisionPending: boolean;
  credentialGrantPending: boolean;
  credentialDecisionVariables?: CredentialDecisionMutationVariables;
  credentialGrantVariables?: CredentialGrantMutationVariables;
  onCredentialDecision: (requestId: string, status: "approved" | "rejected") => void;
  onCredentialGrant: (requestId: string, serviceId: string) => void;
}) {
  const candidateServiceId = request.candidate_service_ids[0] ?? "";
  const candidateService = servicesById.get(candidateServiceId);
  const canApplyGrant = request.status === "approved" && candidateServiceId;
  const isDecisionPending =
    credentialDecisionPending && credentialDecisionVariables?.requestId === request.id;
  const isGrantPending =
    credentialGrantPending && credentialGrantVariables?.requestId === request.id;

  return (
    <article className="rounded-md border border-border bg-white p-3">
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
}

function HumanAssistanceRequestCard({
  request,
  response,
  humanAssistancePending,
  humanAssistanceVariables,
  onHumanResponseChange,
  onHumanResolution
}: {
  request: HumanAssistanceRequest;
  response: string;
  humanAssistancePending: boolean;
  humanAssistanceVariables?: HumanAssistanceMutationVariables;
  onHumanResponseChange: (requestId: string, response: string) => void;
  onHumanResolution: (requestId: string, status: "answered" | "dismissed") => void;
}) {
  const isPending =
    humanAssistancePending && humanAssistanceVariables?.requestId === request.id;

  return (
    <article className="rounded-md border border-border bg-white p-3">
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
      <p className="mt-2 line-clamp-2 text-xs text-muted">{request.description}</p>
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
          <span>
            {isPending && humanAssistanceVariables?.status === "answered" ? "Envoi" : "Répondre"}
          </span>
        </button>
      </div>
    </article>
  );
}

function SecretVaultConnectorGate({
  item,
  loading
}: {
  item: SystemReadinessItem | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="rounded-md border border-border bg-slate-50 p-3 text-xs text-muted">
        Vérification SecretVault...
      </div>
    );
  }
  const ready = secretVaultCanStoreConnectorSecrets(item);
  const badges = item ? secretVaultBadges(item) : [];
  return (
    <div
      className={`rounded-md border p-3 text-xs ${
        ready
          ? "border-ok/20 bg-ok-soft text-ok"
          : "border-risk/20 bg-risk-soft text-risk"
      }`}
    >
      <div className="flex items-start gap-2">
        {ready ? (
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        ) : (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        )}
        <div className="min-w-0">
          <p className="font-semibold">
            {ready ? "SecretVault prêt pour les clés API" : "SecretVault requis"}
          </p>
          <p className="mt-1">
            {ready
              ? "Les nouvelles clés connecteur seront stockées chiffrées, sans valeur exposée dans state-service."
              : item?.manual_action ??
                "Attendre ou corriger SecretVault avant d'enregistrer une clé connecteur."}
          </p>
          {badges.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {badges.map((badge) => (
                <span
                  key={badge}
                  className="rounded-md bg-white/70 px-2 py-1 text-[11px] ring-1 ring-current/15"
                >
                  {badge}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ConnectorConnectionOverview({
  connections,
  services,
  loading,
  selectedServiceId,
  onSelectService
}: {
  connections: ConnectorConnectionRecord[];
  services: ServiceDefinition[];
  loading: boolean;
  selectedServiceId: string | null;
  onSelectService: (serviceId: string) => void;
}) {
  const servicesById = new Map(services.map((service) => [service.id, service]));
  const recentConnections = [...connections]
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .slice(0, 4);

  if (loading) {
    return <p className="border-b border-border px-4 py-3 text-sm text-muted">Chargement...</p>;
  }

  if (recentConnections.length === 0) {
    return (
      <p className="border-b border-border px-4 py-3 text-sm text-muted">
        Aucune connexion enregistrée.
      </p>
    );
  }

  return (
    <div className="divide-y divide-border border-b border-border">
      {recentConnections.map((connection) => {
        const service = servicesById.get(connection.service_id) ?? null;
        const selected = selectedServiceId === connection.service_id;
        return (
          <article key={connection.id} className="px-4 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">
                  {service?.name ?? connection.service_id}
                </p>
                <p className="truncate text-xs text-muted">
                  {connection.mode}
                  {connection.secret_fingerprint ? ` / ${connection.secret_fingerprint}` : ""}
                </p>
              </div>
              <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${statusClass(connection.status)}`}>
                {connection.status}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap justify-end gap-2">
              {connection.status === "needs_oauth" && connection.setup_url ? (
                <a
                  href={connection.setup_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex h-8 items-center gap-1.5 rounded-md border border-warn/30 px-2 text-xs font-semibold text-warn"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  <span>Autoriser</span>
                </a>
              ) : null}
              {service ? (
                <button
                  type="button"
                  className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-2 text-xs font-semibold ${
                    selected
                      ? "border-accent bg-accent-soft text-accent"
                      : "border-border bg-white text-ink hover:bg-slate-50"
                  }`}
                  onClick={() => onSelectService(connection.service_id)}
                >
                  <PlugZap className="h-3.5 w-3.5" />
                  <span>{selected ? "Ouvert" : "Gérer"}</span>
                </button>
              ) : null}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function ConnectorSetupSteps({
  service,
  connection,
  mode,
  hasApiKey
}: {
  service: ServiceDefinition | null;
  connection: ConnectorConnectionRecord | null;
  mode: ConnectorConnectionMode;
  hasApiKey: boolean;
}) {
  const secretReady =
    mode === "no_key" || mode === "oauth" || hasApiKey || Boolean(connection?.secret_fingerprint);
  const authorizationReady = connection?.status === "active";
  const authorizationPending = connection?.status === "needs_oauth";
  const steps = [
    {
      label: "Service",
      detail: service?.name ?? "Sélectionner un connecteur",
      ready: Boolean(service),
      warning: false
    },
    {
      label: "Identifiants",
      detail:
        mode === "api_key"
          ? "Clé reçue puis stockée dans SecretVault"
          : mode === "oauth"
            ? "Autorisation externe préparée par Synarch"
            : "Aucun secret nécessaire",
      ready: secretReady,
      warning: false
    },
    {
      label: "État",
      detail: authorizationPending
        ? "Autorisation externe à finaliser"
        : authorizationReady
          ? "Connexion utilisable par les agents autorisés"
          : "Connexion à créer ou mettre à jour",
      ready: authorizationReady,
      warning: authorizationPending
    }
  ];

  return (
    <div className="rounded-md border border-border bg-white">
      {steps.map((step) => (
        <div key={step.label} className="flex items-start gap-2 border-b border-border px-3 py-2 last:border-b-0">
          {step.ready ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" />
          ) : step.warning ? (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          ) : (
            <CircleDot className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
          )}
          <div className="min-w-0">
            <p className="text-xs font-semibold text-ink">{step.label}</p>
            <p className="line-clamp-1 text-xs text-muted">{step.detail}</p>
          </div>
        </div>
      ))}
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
  humanAssistanceVariables?: HumanAssistanceMutationVariables;
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
                credentialRequests.map((request) => (
                  <CredentialRequestCard
                    key={request.id}
                    request={request}
                    servicesById={servicesById}
                    credentialDecisionPending={credentialDecisionPending}
                    credentialGrantPending={credentialGrantPending}
                    credentialDecisionVariables={credentialDecisionVariables}
                    credentialGrantVariables={credentialGrantVariables}
                    onCredentialDecision={onCredentialDecision}
                    onCredentialGrant={onCredentialGrant}
                  />
                ))
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
                humanRequests.map((request) => (
                  <HumanAssistanceRequestCard
                    key={request.id}
                    request={request}
                    response={humanResponsesById[request.id] ?? ""}
                    humanAssistancePending={humanAssistancePending}
                    humanAssistanceVariables={humanAssistanceVariables}
                    onHumanResponseChange={onHumanResponseChange}
                    onHumanResolution={onHumanResolution}
                  />
                ))
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

function WebProviderPanel({
  providers,
  services,
  connections,
  loading,
  selectedServiceId,
  onSelectProvider
}: {
  providers: WebProviderStatus[];
  services: ServiceDefinition[];
  connections: ConnectorConnectionRecord[];
  loading: boolean;
  selectedServiceId: string | null;
  onSelectProvider: (provider: WebProviderStatus) => void;
}) {
  const connectionsByService = connectionByService(connections);
  const orderedProviders = [...providers].sort((left, right) => {
    if (left.implemented !== right.implemented) {
      return left.implemented ? -1 : 1;
    }
    if (left.configured !== right.configured) {
      return left.configured ? -1 : 1;
    }
    return left.name.localeCompare(right.name);
  });

  return (
    <section className="rounded-md border border-border bg-panel shadow-soft">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold">Web providers</h2>
        <Globe2 className="h-4 w-4 text-accent" />
      </div>
      <div className="divide-y divide-border">
        {loading ? (
          <p className="px-4 py-3 text-sm text-muted">Chargement...</p>
        ) : orderedProviders.length === 0 ? (
          <p className="px-4 py-3 text-sm text-muted">Aucun provider.</p>
        ) : (
          orderedProviders.map((provider) => {
            const service =
              services.find(
                (candidate) => metadataString(candidate, "web_provider") === provider.provider_id
              ) ?? null;
            const connection = service ? connectionsByService.get(service.id) : null;
            const selected = service?.id === selectedServiceId;
            const selectable = Boolean(service && provider.implemented);
            return (
              <article key={provider.provider_id} className="px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">{provider.name}</p>
                    <p className="truncate text-xs text-muted">
                      {provider.category}
                      {service ? ` / ${service.id}` : ""}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${
                      provider.configured
                        ? statusClass("completed")
                        : provider.implemented
                          ? statusClass("queued")
                          : statusClass("draft")
                    }`}
                  >
                    {provider.configured
                      ? "configuré"
                      : provider.implemented
                        ? "disponible"
                        : "prévu"}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {provider.requires_api_key ? (
                    <span className="rounded-md bg-warn-soft px-2 py-1 text-[11px] text-warn ring-1 ring-warn/15">
                      clé API
                    </span>
                  ) : (
                    <span className="rounded-md bg-ok-soft px-2 py-1 text-[11px] text-ok ring-1 ring-ok/15">
                      sans clé
                    </span>
                  )}
                  {provider.configured_by.map((source) => (
                    <span
                      key={source}
                      className="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-muted ring-1 ring-border"
                    >
                      {source}
                    </span>
                  ))}
                  {connection ? (
                    <span className={`rounded-md px-2 py-1 text-[11px] ring-1 ${statusClass(connection.status)}`}>
                      {connection.status}
                    </span>
                  ) : null}
                </div>
                <p className="mt-2 line-clamp-2 text-xs text-muted">{provider.notes}</p>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <div className="min-w-0 truncate text-[11px] text-muted">
                    {provider.capabilities.slice(0, 4).join(" / ")}
                  </div>
                  <button
                    type="button"
                    className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2 text-xs font-semibold disabled:opacity-50 ${
                      selected
                        ? "border-accent bg-accent-soft text-accent"
                        : "border-border bg-white text-ink hover:bg-slate-50"
                    }`}
                    disabled={!selectable}
                    onClick={() => onSelectProvider(provider)}
                  >
                    <PlugZap className="h-3.5 w-3.5" />
                    <span>{selected ? "Sélectionné" : "Configurer"}</span>
                  </button>
                </div>
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}

function WorkerPanel({
  heartbeats,
  loading,
  staleAfterSeconds
}: {
  heartbeats: WorkerHeartbeatRecord[];
  loading: boolean;
  staleAfterSeconds: number;
}) {
  const recentHeartbeats = [...heartbeats]
    .sort((left, right) => right.last_seen_at.localeCompare(left.last_seen_at))
    .slice(0, 5);
  const statusCounts = heartbeats.reduce<Record<string, number>>((counts, heartbeat) => {
    counts[heartbeat.status] = (counts[heartbeat.status] ?? 0) + 1;
    return counts;
  }, {});
  const staleCount = heartbeats.filter((heartbeat) => {
    const age = secondsSince(heartbeat.last_seen_at);
    return (
      !["failed", "stopped"].includes(heartbeat.status) &&
      age !== null &&
      age > staleAfterSeconds
    );
  }).length;
  const failedCount = heartbeats.filter((heartbeat) =>
    ["failed", "stopped"].includes(heartbeat.status)
  ).length;
  const healthyCount = heartbeats.filter((heartbeat) => {
    const age = secondsSince(heartbeat.last_seen_at);
    return (
      !["failed", "stopped"].includes(heartbeat.status) &&
      (age === null || age <= staleAfterSeconds)
    );
  }).length;

  return (
    <section className="rounded-md border border-border bg-panel shadow-soft">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">Workers</h2>
          <p className="text-xs text-muted">
            stale après {formatDuration(staleAfterSeconds)}
          </p>
        </div>
        <Activity className="h-4 w-4 shrink-0 text-accent" />
      </div>
      <div className="border-b border-border px-4 py-3">
        <div className="flex flex-wrap gap-2">
          <span className={`rounded-md px-2 py-1 text-xs ring-1 ${statusClass(failedCount > 0 ? "failed" : "healthy")}`}>
            actifs: {healthyCount}
          </span>
          <span className={`rounded-md px-2 py-1 text-xs ring-1 ${statusClass(staleCount > 0 ? "stale" : "healthy")}`}>
            stale: {staleCount}
          </span>
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
          recentHeartbeats.map((heartbeat) => {
            const ageSeconds = secondsSince(heartbeat.last_seen_at);
            const isStale = ageSeconds !== null && ageSeconds > staleAfterSeconds;
            const statusLabel =
              heartbeat.status === "failed" || heartbeat.status === "stopped"
                ? heartbeat.status
                : isStale
                  ? "stale"
                  : heartbeat.status;
            const tickSummary = workerTickSummary(heartbeat.last_tick_result);
            return (
              <div key={heartbeat.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-medium">{heartbeat.id}</p>
                  <span
                    className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] ring-1 ${statusClass(statusLabel)}`}
                  >
                    {statusLabel}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted">
                  <span className="truncate">
                    {heartbeat.worker_kind}
                    {heartbeat.target ? ` / ${heartbeat.target}` : ""}
                  </span>
                  <span className="shrink-0">vu {formatDuration(ageSeconds)}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  <span className="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-muted ring-1 ring-border">
                    #{heartbeat.heartbeat_count}
                  </span>
                  {tickSummary.map((item) => (
                    <span
                      key={item}
                      className="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-muted ring-1 ring-border"
                    >
                      {item}
                    </span>
                  ))}
                </div>
                {heartbeat.last_error ? (
                  <p className="mt-1 line-clamp-2 text-xs text-risk">{heartbeat.last_error}</p>
                ) : null}
                <p className="mt-1 text-[11px] text-muted">
                  {formatDate(heartbeat.last_seen_at)}
                </p>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

function workerTickSummary(result: Record<string, unknown>): string[] {
  const labels: string[] = [];
  for (const [key, label] of [
    ["tick", "tick"],
    ["claimed_count", "claim"],
    ["completed_count", "done"],
    ["failed_count", "fail"],
    ["recovered_item_count", "recover"],
    ["dead_lettered_recovery_count", "dead"]
  ] as const) {
    const value = result[key];
    if (typeof value === "number") {
      labels.push(`${label} ${value}`);
    }
  }
  const status = result.status;
  if (typeof status === "string" && labels.length < 6) {
    labels.unshift(status);
  }
  return labels.slice(0, 6);
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
  recovering,
  canSubmit,
  error,
  reviewError,
  recoveryError,
  recoveryResult,
  onQueueNameChange,
  onActionChange,
  onMessageChange,
  onRunAfterChange,
  onSubmit,
  onReview,
  onRecoverLeases
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
  recovering: boolean;
  canSubmit: boolean;
  error: unknown;
  reviewError: unknown;
  recoveryError: unknown;
  recoveryResult: WorkQueueRecoveryResult | null;
  onQueueNameChange: (value: string) => void;
  onActionChange: (value: WorkQueueAction) => void;
  onMessageChange: (value: string) => void;
  onRunAfterChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onReview: (itemId: string, action: "retry" | "dead_letter") => void;
  onRecoverLeases: () => void;
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
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">Queue durable</h2>
          <p className="text-xs text-muted">
            leases, retries et dead-letter PostgreSQL
          </p>
        </div>
        <button
          type="button"
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-border bg-white px-2 text-xs font-semibold text-ink hover:bg-slate-50 disabled:opacity-60"
          disabled={recovering}
          onClick={onRecoverLeases}
          title="Réexaminer les items running dont le lease a expiré"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          <span>{recovering ? "Récupération" : "Récupérer"}</span>
        </button>
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
        {recoveryError ? (
          <p className="text-xs text-risk">
            {recoveryError instanceof Error ? recoveryError.message : "Récupération impossible."}
          </p>
        ) : null}
        {recoveryResult ? (
          <p className="text-xs text-muted">
            Récupération: {recoveryResult.recovered_item_ids.length} récupérés /{" "}
            {recoveryResult.dead_lettered_item_ids.length} dead-letter à{" "}
            {formatDate(recoveryResult.inspected_at)}.
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
