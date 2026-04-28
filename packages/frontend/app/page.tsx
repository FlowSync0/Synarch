import { Plus, Search, Settings2 } from "lucide-react";

import { agents, events, metrics, projects } from "../lib/sample-data";

const statusClass: Record<string, string> = {
  blocked: "text-risk",
  running: "text-accent",
  queued: "text-muted"
};

const metricClass: Record<string, string> = {
  accent: "text-accent",
  ok: "text-ok",
  warn: "text-warn",
  risk: "text-risk"
};

export default function DashboardPage() {
  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-panel">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-normal text-accent">Synarch</p>
            <h1 className="text-2xl font-semibold tracking-normal">Control Surface</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="grid h-10 w-10 place-items-center rounded-md border border-border bg-white text-muted"
              aria-label="Search"
              title="Search"
            >
              <Search size={18} />
            </button>
            <button
              className="grid h-10 w-10 place-items-center rounded-md border border-border bg-white text-muted"
              aria-label="Settings"
              title="Settings"
            >
              <Settings2 size={18} />
            </button>
            <button className="flex h-10 items-center gap-2 rounded-md bg-accent px-3 text-sm font-medium text-white">
              <Plus size={18} />
              Objectif
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-5 px-5 py-5 lg:grid-cols-[1fr_360px]">
        <section className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {metrics.map((metric) => (
              <article key={metric.label} className="rounded-md border border-border bg-panel p-4">
                <p className="text-sm text-muted">{metric.label}</p>
                <p className={`mt-2 text-2xl font-semibold ${metricClass[metric.tone]}`}>
                  {metric.value}
                </p>
              </article>
            ))}
          </div>

          <section className="rounded-md border border-border bg-panel">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold">Projets</h2>
            </div>
            <div className="divide-y divide-border">
              {projects.map((project) => (
                <article key={project.title} className="grid gap-3 px-4 py-4 md:grid-cols-[1fr_120px_140px]">
                  <div>
                    <h3 className="text-sm font-semibold">{project.title}</h3>
                    <p className="mt-1 text-sm text-muted">{project.owner}</p>
                  </div>
                  <div>
                    <p className={`text-sm font-medium ${statusClass[project.status]}`}>
                      {project.status}
                    </p>
                    <p className="mt-1 text-xs text-muted">{project.priority}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="h-2 flex-1 rounded-full bg-slate-200">
                      <div
                        className="h-2 rounded-full bg-accent"
                        style={{ width: `${project.progress}%` }}
                      />
                    </div>
                    <span className="w-10 text-right text-xs text-muted">{project.progress}%</span>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </section>

        <aside className="space-y-5">
          <section className="rounded-md border border-border bg-panel">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold">Agents</h2>
            </div>
            <div className="divide-y divide-border">
              {agents.map((agent) => {
                const Icon = agent.icon;
                return (
                  <article key={agent.id} className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="grid h-9 w-9 place-items-center rounded-md bg-slate-100 text-accent">
                        <Icon size={18} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate text-sm font-semibold">{agent.name}</h3>
                        <p className="text-xs text-muted">{agent.division}</p>
                      </div>
                      <span className="text-xs font-medium text-ok">{agent.status}</span>
                    </div>
                    <div className="mt-3 flex items-center gap-3">
                      <div className="h-2 flex-1 rounded-full bg-slate-200">
                        <div className="h-2 rounded-full bg-warn" style={{ width: `${agent.load}%` }} />
                      </div>
                      <span className="w-8 text-right text-xs text-muted">{agent.load}%</span>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="rounded-md border border-border bg-panel">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold">Timeline</h2>
            </div>
            <div className="divide-y divide-border">
              {events.map((event) => {
                const Icon = event.icon;
                return (
                  <article key={`${event.time}-${event.label}`} className="flex gap-3 px-4 py-3">
                    <div className="grid h-8 w-8 place-items-center rounded-md bg-slate-100 text-muted">
                      <Icon size={16} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate text-sm font-medium">{event.label}</p>
                        <span className="text-xs text-muted">{event.time}</span>
                      </div>
                      <p className="mt-1 text-xs text-muted">{event.target}</p>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}
