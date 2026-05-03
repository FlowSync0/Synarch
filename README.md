# Synarch — Brief Technique Détaillé

## Qu'est-ce que Synarch ?

Synarch est une plateforme open source de type "AI Company" : un système multi-IA organisé comme une entreprise, où plusieurs IA persistantes (pas de simples agents jetables) collaborent sous une hiérarchie, avec mémoire, skills, traçabilité et vue projet native. L'utilisateur n'a qu'un seul interlocuteur (l'IA Direction) et donne des objectifs — le système se débrouille, découpe, délègue, exécute et rend compte.

Le problème résolu : les systèmes multi-agents actuels saturent sur les projets longs (context rot, explosion de tokens, perte de fiabilité). Synarch isole chaque division IA avec sa propre mémoire, ses outils, son historique, et une coordination légère au-dessus.

---

## Architecture — 9 Couches

```
SYNARCH PLATFORM
├─ A. Interface Layer          (Frontend / Dashboard)
├─ B. Orchestration Layer      (Routing / Planning)
├─ C. Control Plane            (Org, permissions, policies)
├─ D. Domain Agents Layer      (IA persistantes par division)
├─ E. Project / Workflow Layer (Projets, tâches, dépendances)
├─ F. Memory & Context Layer   (Mémoire hiérarchique paginée)
├─ G. Execution & Tooling Layer(Outils, API, sandbox)
├─ H. Data / Knowledge Layer   (Sources de vérité métier)
└─ I. Observability & Governance Layer (Traces, métriques, coûts)
```

---

## Détail de chaque couche

### A. Interface Layer
- **Rôle** : Point d'entrée humain. Affiche projets, timeline, organigramme IA, blocages. Permet de donner des objectifs et valider les exceptions.
- **Stack** : Next.js, React, Tailwind, TanStack Query, shadcn/ui
- **Connexions** : Parle au Gateway API. Lit projets/tâches/agents/métriques. Écrit objectifs/validations.
- **Données** : Entrée = objectif utilisateur, priorités, validations. Sortie = état projet, résumé, coûts, blocages.
- **Limites** : Ne décide rien. Ne contient pas de logique métier/agentique. N'est jamais source de vérité.
- **Test** : "Je crée un objectif → un projet apparaît", "Je vois quel agent travaille sur quoi"

### B. Orchestration Layer
- **Rôle** : Prend l'objectif brut, le transforme en plan exécutable. Choisit s'il faut ouvrir un projet, découper en tâches, appeler Finance IA / Dev IA / etc.
- **Stack** : FastAPI, Pydantic v2, optionnel LangGraph pour graphes d'orchestration
- **Connexions** : Reçoit du Gateway → interroge Control Plane → ouvre/met à jour Project Layer → déclenche Domain Agents
- **Données** : Entrée = `GoalEnvelope`. Sortie = `ProjectIntent`, `TaskDrafts`, `RoutingDecision`
- **Limites** : Doit rester routeur + planificateur, pas un silo de logique cachée.
- **Test** : "Même objectif → même type de routage", "Un objectif compta n'atterrit pas chez Dev IA"

### C. Control Plane
- **Rôle** : Cœur structurel. Sait quels agents existent, leurs rôles, qui reporte à qui, quelles skills/outils sont autorisés, quelles policies sont actives. Remplace le `soul.md` géant.
- **Stack** : FastAPI, PostgreSQL, SQLAlchemy/SQLModel, Alembic, Redis (cache), NATS (events)
- **Connexions** : Parle à tout (Orchestration, State, Event bus, Domain Agents). Produit les `LocalWorldView`.
- **Données** : Entrée = org updates, project status, agent health, policy updates. Sortie = `LocalWorldView`, `PermissionBundle`, `CapabilityMap`, `RoutingPolicy`
- **Limites** : Doit rester déterministe au maximum. Pas de LLM ici.
- **Test** : "J'ajoute un agent → il apparaît dans l'org", "Un agent ne voit que ce qu'il doit voir"

### D. Domain Agents Layer
- **Rôle** : Les IA persistantes de division (Finance IA, Ops/Sourcing IA, Dev IA, Admin/Knowledge IA). Chacune a identité, rôle, mémoire locale, outils autorisés, historique de travail.
- **Stack** : Hermes (existant) ou wrappers compatibles LangGraph / CrewAI / OpenAI Agents SDK / PydanticAI
- **Connexions** : Reçoit `LocalWorldView` → récupère contexte dans Memory Layer → exécute outils via Execution Layer → émet événements → renvoie `AgentResult`
- **Données** : Entrée = tâche, projection locale, contexte mémoire, outils autorisés. Sortie = actions, sous-tâches, événements, mémoire candidate, résumé partiel.
- **Limites** : Un agent n'est pas source de vérité. Ne parle pas directement aux autres sans passer par les contrats.
- **Test** : "Finance IA traite une tâche finance sans recharger tout l'historique global", "Dev IA n'a pas accès aux actions paiement"

### E. Project / Workflow Layer
- **Rôle** : Transforme les objectifs en projets vivants : tâches, sous-tâches, dépendances, blocages, priorités, participants.
- **Stack** : Table SQL dédiée dans PostgreSQL. Optionnel : scheduler jobs, NATS + workers.
- **Connexions** : Alimente l'UI et les agents. Se nourrit des événements.
- **Données** : Entrée = objectifs, changements de statut, résultats d'agents. Sortie = roadmap de tâches, blocages, état global.
- **Limites** : Ne pas confondre "chat history" et "project state". Le projet = données structurées, pas un transcript.
- **Test** : "Une tâche bloquée reste bloquée et visible", "Le projet survit au redémarrage"

### F. Memory & Context Layer (la plus critique)
- **Rôle** : Stocke et sert mémoire session/agent/projet/division/entreprise. Décide ce qui rentre dans le prompt et à quel niveau de détail.

**Sous-couches :**

- **F1. Working Memory** : Redis. État court terme, files, locks, session state.
- **F2. Persistent Memory** :
  - Option principale : **OpenViking** — context database hiérarchique type filesystem, chargement tiered L0/L1/L2, réduction massive de tokens. Très bon pour vision contextuelle progressive.
  - Option avancée : **Cognee** — memory engine graph+vector+metadata (LanceDB pour vecteurs, Kuzu/Memgraph pour graphe). Très bon pour relations entités, multi-hop reasoning, provenance.
  - Option baseline : **pgvector** ou **LanceDB** seul. Simple, robuste, rapide à mettre en place.
- **F3. Retrieval Engine** : OpenViking retrieval hiérarchique, Cognee query engine, pgvector similarity search.
- **F4. Compaction / Summarization** : Code maison + LLM. Transforme events → summaries, session transcripts → memories, task results → learned procedures. Seuil de compaction à ~70% de la fenêtre effective.
- **F5. Context Assembly** : Construit le `memory_context` final envoyé à l'agent (L0/L1 OpenViking + extraits Cognee + policies + résumés projet + préférences).

- **Limites** : Si trop de choses dans le contexte → retour au problème initial. Cette couche doit être budgétée.
- **Test** : "Même projet après 3 semaines : récupération correcte sans repasser tout le transcript", "Le coût token reste stable malgré la croissance"

### G. Execution & Tooling Layer
- **Rôle** : Exécuter les actions réelles : API externes, scripts Python, code sandbox, MCP tools, emails, fichiers, shell.
- **Stack** : MCP pour standardiser les tools, Python subprocess / Celery / RQ / Arq pour workers async, sandboxing dédié.
- **Connexions** : Domain Agents demandent → Control Plane autorise → Event Layer journalise → Observability trace.
- **Données** : Entrée = `ToolCallRequest`. Sortie = `ToolResult`, logs, artifacts, erreurs.
- **Limites** : Couche la plus risquée côté sécurité. Ne jamais donner accès large par défaut.
- **Test** : "Un tool échoue → l'échec est journalisé et visible", "Les outils ne sortent pas de leur périmètre"

### H. Data / Knowledge Layer
- **Rôle** : Sources de vérité métier : fichiers, emails, docs, CRM, ERP, GitHub, drive, bases externes.
- **Stack** : Connecteurs maison, loaders, APIs, ETL léger, ingestion pipelines.
- **Connexions** : Ingestion vers Cognee/OpenViking. Outils pour agents. Events quand nouvelles données.
- **Données** : Documents, métadonnées, objets métier, états externes.
- **Limites** : Garbage in, garbage out. Versionner les sources et la provenance.
- **Test** : "Une nouvelle source ajoutée est indexée proprement", "La provenance d'une réponse est traçable"

### I. Observability & Governance Layer
- **Rôle** : Voir ce qui se passe réellement : traces, métriques, logs, coûts, raisons d'échec, trajectoires contextuelles.
- **Stack** : OpenTelemetry (standard), Langfuse (traces/evals agentiques), Grafana + Tempo + Loki + Prometheus (dashboards)
- **Connexions** : Tous les services émettent des spans/logs/metrics. Le front lit les vues synthétiques.
- **Données** : trace_id, span_id, coût, latence, tool calls, retrieved context IDs, erreurs, décisions.
- **Limites** : Si ajouté trop tard → debug à l'aveugle. Si mal tracé → bruit sans vérité.
- **Test** : "Je peux suivre une requête de bout en bout", "Je sais quel agent a coûté combien"

---

## Stack Technique Complète

```
Frontend
└─ Next.js + Tailwind + TanStack Query + shadcn/ui

Backend (Python)
├─ FastAPI Gateway
├─ FastAPI Control Plane
├─ FastAPI State Service
├─ FastAPI Memory Service
├─ Agent Runtime (Hermes wrappers ou LangGraph/CrewAI/PydanticAI)
└─ Event Service

Infra
├─ PostgreSQL (state canonique)
├─ pgvector (embeddings)
├─ Redis (cache chaud, working memory)
├─ NATS (event bus)
├─ OpenViking (context database hiérarchique)
├─ Cognee + LanceDB + Kuzu/Memgraph (memory graph, optionnel phase 2)
├─ OTEL Collector
├─ Grafana + Tempo + Loki + Prometheus
└─ Langfuse (traces agentiques)
```

---

## Contrats JSON Principaux

### GoalEnvelope (entrée utilisateur)
```json
{
  "goal": "string",
  "priority": "low|medium|high|critical",
  "context": {},
  "constraints": [],
  "requester": "user_id"
}
```

### LocalWorldView (ce que chaque agent reçoit)
```json
{
  "agent_id": "string",
  "name": "string",
  "role": "string",
  "division": "string",
  "peers": ["agent_id"],
  "manager": "agent_id",
  "manager_agent_id": "agent_id",
  "peer_agent_ids": ["agent_id"],
  "direct_report_agent_ids": ["agent_id"],
  "soul": {
    "identity": "string",
    "mission": "string",
    "responsibilities": [],
    "operating_principles": [],
    "boundaries": [],
    "escalation_rules": []
  },
  "active_projects": [],
  "permissions": {},
  "capabilities": [],
  "policies": [],
  "available_services": ["service_id"],
  "available_connector_ids": ["connector_id"],
  "available_skill_ids": ["skill_id"]
}
```

### AgentResult (ce que chaque agent renvoie)
```json
{
  "agent_id": "string",
  "task_id": "string",
  "status": "completed|blocked|failed|needs_review",
  "actions_taken": [],
  "sub_tasks_created": [],
  "events_emitted": [],
  "memory_candidates": [],
  "summary": "string"
}
```

---

## Tables de Base de Données Minimales

- **agents** : id, name, role, division, manager_id, status, capabilities, model, created_at
- **agent_souls** : id, agent_id, version, identity, mission, responsibilities, boundaries, active
- **projects** : id, title, goal, status, priority, owner_agent_id, created_at
- **project_workspaces** : id, project_id, memory_scope, allowed_agent_ids, bridge_project_ids, active
- **agent_project_assignments** : id, project_id, workspace_id, agent_id, assignment_role, active
- **project_complexity_reports** : id, project_id, task_count, open_task_count, blocked_task_count, assigned_agent_count, score, split_recommended
- **project_split_requests** : id, project_id, complexity_report_id, requested_by, reason, proposed_shard_titles, status
- **tasks** : id, project_id, title, status, assigned_agent_id, depends_on, acceptance_criteria, sequence, result, created_at
- **events** : id, type, source_agent_id, target, payload, timestamp
- **memory_items** : id, scope (global/division/agent/project), agent_id, content, embedding, created_at, expires_at
- **checkpoints** : id, agent_id, project_id, state_snapshot, timestamp

---

## Les IA de Division à Créer

| IA | Rôle | Exemples de tâches |
|---|---|---|
| **IA Direction** | Interlocuteur unique, arbitrage, priorisation, reporting | Comprendre objectifs, découper, arbitrer conflits |
| **IA Finance** | Compta, TVA, factures, fournisseurs, paiements | OCR factures, écritures comptables, rapprochement bancaire |
| **IA Ops / Sourcing** | Usines, RFQ, comparatifs, MOQ, négociation | Recherche fournisseurs, chiffrage, suivi commandes |
| **IA Dev** | Code, infra, bugs, roadmap technique | Développement, CI/CD, debug, architecture |
| **IA Admin / Knowledge** | Docs, mails, procédures, historique entreprise | Gestion documentaire, recherche interne, procédures |

Chaque IA a : sa mémoire longue, ses documents propres, ses skills, son journal d'activité, son modèle éventuellement différent (local cheap pour workers, premium pour supervisor).

---

## Principes Clés

1. **Isolation des contextes** : Chaque projet a son `ProjectWorkspace`. Finance ne pollue pas Dev, et un projet ne pollue pas un autre.
2. **Mémoire paginée** : Pas de rechargement d'historique complet. Compaction, résumés, retrieval ciblé.
3. **Découpage vérifiable** : Aucun objectif ne devient une seule grosse tâche. Chaque tâche a des critères de réussite et une dépendance explicite.
4. **World model partagé** : Chaque agent sait où il est dans l'org via `LocalWorldView` injecté par le Control Plane. Son `AgentSoul` reste borné et séparé de la mémoire, de l'historique et des skills.
5. **Event-driven** : Tout passe par des événements (NATS). Les agents réagissent, le système journalise.
6. **Observabilité dès le jour 1** : OTEL + Langfuse. Pas de vol à l'aveugle.
7. **Modèles différenciés** : Workers cheap (Ollama/Mistral local), supervisor premium si besoin.
8. **Sécurité par défaut** : Permissions par agent, pas d'accès large.

---

## Ordre de Construction Recommandé

### Phase 1 — Fondations
- State store + tables PostgreSQL (agents, projects, tasks, events)
- Control Plane basique (CRUD agents, divisions, permissions)
- API Gateway FastAPI

### Phase 2 — Agent Runtime
- Intégration Hermes ou wrapper LangGraph
- Un seul agent de test avec tâche simple
- Contrats GoalEnvelope / LocalWorldView / AgentResult

### Phase 3 — Memory Layer
- pgvector ou OpenViking en baseline
- Working memory Redis
- Context Assembly basique

### Phase 4 — Event Layer + Observability
- NATS event bus
- OpenTelemetry instrumentation
- Langfuse pour traces agentiques
- Timeline d'événements

### Phase 5 — Scaling
- Ajout des IA de division (Finance, Dev, Ops, Admin)
- Cognee / graph memory (si besoin de raisonnement relationnel)
- Vue projet native dans le frontend
- Vue organigramme IA

---

## Organisation GitHub

```
Synarch/
├─ README.md                    # Vision, principes, quickstart
├─ docs/                        # Architecture détaillée, ADR
├─ docker-compose.yml           # Déploiement local complet
├─ packages/
│  ├─ gateway/                  # FastAPI Gateway
│  ├─ control-plane/            # Control Plane service
│  ├─ state-service/            # State store + migrations
│  ├─ memory-service/           # Memory Layer (OpenViking, pgvector)
│  ├─ event-service/            # NATS event bus
│  ├─ agent-runtime/            # Agent execution (Hermes wrappers)
│  └─ frontend/                 # Next.js dashboard
├─ shared/
│  └─ models/                   # Pydantic models partagés (contrats)
├─ scripts/                     # Setup, migrations, seeds
├─ .github/
│  └─ workflows/                # CI/CD
└─ .env.example
```

### Conventions
- Branching : `main` (stable) + `dev` + feature branches `feat/xxx`
- PRs obligatoires, review avant merge
- Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`)
- CI : lint + type check + tests sur chaque PR

---

## Quickstart du squelette

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
make install-backend
make test
make dev-backend
```

Services locaux :
- Gateway : `http://localhost:8000`
- Control Plane : `http://localhost:8010`
- State Service : `http://localhost:8020`
- Memory Service : `http://localhost:8030`
- Event Service : `http://localhost:8040`
- Agent Runtime : `http://localhost:8050`
- Frontend : `packages/frontend` puis `npm install && npm run dev`

## Suivi de développement

Le développement se fait par quality gates vérifiables : une capacité, un test, puis seulement la
couche suivante. Voir `docs/development-quality-gates.md`.

Commandes de base :
- `make verify` : lint + tests backend.
- `make test-integration` : scénario transverse actuel `goal -> agent result -> event`.

Priorité backend actuelle :
- état durable de l'entreprise IA ;
- choix des providers/modèles IA via un Model Gateway ;
- cycle de vie des employés IA avec approbation ;
- registre des services accessibles ;
- suivi coûts/tokens/traces/audit logs.

Voir `docs/backend-core-priorities.md`.

Roadmap complete :
- `docs/roadmap.md` : etat actuel, prochaine priorite, statut des 9 couches, risques, tests et
  decisions ouvertes.

---

## Résumé en une phrase

Synarch est un OS d'entreprise IA open source : 1 interlocuteur → 1 supervisor → N divisions IA persistantes → mémoire hiérarchique paginée → event-driven → observabilité complète → vue projet et organigramme natifs.
