import { useEffect, useMemo, useState } from "react";
import {
  getAvailableModels,
  getDirectories,
  getSessions,
  getStats,
  type DirectorySummary,
  type SessionSummary,
  type StatsResponse,
} from "./api";

interface DashboardData {
  stats: StatsResponse;
  directories: DirectorySummary[];
  sessions: SessionSummary[];
  availableModelCount: number;
  modelLoadError?: string;
}

type LoadState =
  | { status: "loading" }
  | { status: "ready"; data: DashboardData }
  | { status: "error"; message: string };

export default function App() {
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [query, setQuery] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");

  useEffect(() => {
    let mounted = true;

    async function load() {
      try {
        const [stats, directories, sessions, models] = await Promise.all([
          getStats(),
          getDirectories(),
          getSessions({ limit: 200 }),
          getAvailableModels()
            .then((response) => ({ models: response.models }))
            .catch((error: unknown) => ({ models: [] as string[], error: errorText(error) })),
        ]);

        if (!mounted) return;
        setLoadState({
          status: "ready",
          data: {
            stats,
            directories: directories.directories,
            sessions: sessions.sessions,
            availableModelCount: models.models.length,
            modelLoadError: "error" in models ? models.error : undefined,
          },
        });
      } catch (error) {
        if (!mounted) return;
        setLoadState({ status: "error", message: errorText(error) });
      }
    }

    load();

    return () => {
      mounted = false;
    };
  }, []);

  const data = loadState.status === "ready" ? loadState.data : null;
  const filteredSessions = useMemo(
    () => filterSessions(data?.sessions ?? [], query),
    [data?.sessions, query],
  );
  const groupedSessions = useMemo(
    () => groupSessions(filteredSessions, data?.directories ?? []),
    [filteredSessions, data?.directories],
  );
  const selectedSession =
    data?.sessions.find((session) => session.id === selectedSessionId) ??
    filteredSessions[0] ??
    null;

  return (
    <main className="app-shell">
      <aside className="sidebar-shell">
        <div className="brand-row">
          <span className="brand-mark" aria-hidden="true">
            ◆
          </span>
          <h1>OpenCode Sessions</h1>
        </div>
        <input
          className="search-input"
          placeholder="Search sessions"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="sidebar-meta">
          {data ? `${filteredSessions.length} / ${data.sessions.length} sessions` : "Loading"}
        </div>
        <nav className="session-list" aria-label="Sessions">
          {loadState.status === "loading" && <StatusBlock label="Loading sessions" />}
          {loadState.status === "error" && <StatusBlock label={loadState.message} tone="error" />}
          {loadState.status === "ready" && groupedSessions.length === 0 && (
            <StatusBlock label="No sessions" />
          )}
          {groupedSessions.map((group) => (
            <section className="session-group" key={group.path}>
              <div className="group-header">
                <span>{group.name}</span>
                <span>{group.sessions.length}</span>
              </div>
              {group.sessions.map((session) => (
                <button
                  className={`session-row ${session.id === selectedSession?.id ? "active" : ""}`}
                  key={session.id}
                  type="button"
                  onClick={() => setSelectedSessionId(session.id)}
                >
                  <span className="session-title">{session.title || "Untitled session"}</span>
                  <span className="session-meta">
                    {session.model || "N/A"} · {session.time_updated}
                  </span>
                </button>
              ))}
            </section>
          ))}
        </nav>
      </aside>

      <section className="content-shell">
        <header className="content-header">
          <div>
            <p className="eyebrow">Session Browser</p>
            <h2>{selectedSession?.title || "OpenCode Sessions"}</h2>
          </div>
          {data && (
            <div className="summary-strip" aria-label="Summary">
              <SummaryItem label="Sessions" value={formatNumber(data.stats.total_sessions)} />
              <SummaryItem label="Projects" value={formatNumber(data.stats.total_projects)} />
              <SummaryItem label="Input" value={formatTokens(data.stats.total_tokens_input)} />
              <SummaryItem label="Output" value={formatTokens(data.stats.total_tokens_output)} />
              <SummaryItem label="Models" value={formatNumber(data.availableModelCount)} />
            </div>
          )}
        </header>

        {loadState.status === "loading" && <PanelStatus label="Loading data" />}
        {loadState.status === "error" && <PanelStatus label={loadState.message} tone="error" />}
        {data && (
          <div className="workspace-grid">
            <section className="detail-panel">
              <div className="panel-heading">
                <h3>Session</h3>
                <span>{selectedSession?.message_count ?? 0} messages</span>
              </div>
              {selectedSession ? (
                <dl className="detail-list">
                  <div>
                    <dt>Project</dt>
                    <dd>{selectedSession.project}</dd>
                  </div>
                  <div>
                    <dt>Directory</dt>
                    <dd>{selectedSession.directory}</dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd>{selectedSession.model || "N/A"}</dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd>{selectedSession.time_updated}</dd>
                  </div>
                  <div>
                    <dt>Cost</dt>
                    <dd>${selectedSession.cost.toFixed(6)}</dd>
                  </div>
                </dl>
              ) : (
                <PanelStatus label="No session selected" />
              )}
            </section>

            <section className="detail-panel">
              <div className="panel-heading">
                <h3>Recent Projects</h3>
                <span>{data.directories.length}</span>
              </div>
              <div className="directory-list">
                {data.directories.slice(0, 8).map((directory) => (
                  <div className="directory-row" key={directory.path}>
                    <span>{directory.name}</span>
                    <span>{directory.session_count}</span>
                  </div>
                ))}
              </div>
              {data.modelLoadError && (
                <p className="inline-warning">Models unavailable: {data.modelLoadError}</p>
              )}
            </section>
          </div>
        )}
      </section>
    </main>
  );
}

function StatusBlock({ label, tone = "muted" }: { label: string; tone?: "muted" | "error" }) {
  return <div className={`status-block ${tone}`}>{label}</div>;
}

function PanelStatus({ label, tone = "muted" }: { label: string; tone?: "muted" | "error" }) {
  return <div className={`panel-status ${tone}`}>{label}</div>;
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function filterSessions(sessions: SessionSummary[], query: string) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return sessions;
  return sessions.filter((session) =>
    [session.title, session.directory, session.project, session.model]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(normalized)),
  );
}

function groupSessions(sessions: SessionSummary[], directories: DirectorySummary[]) {
  const directoryNames = new Map(directories.map((directory) => [directory.path, directory.name]));
  const groups = new Map<string, { path: string; name: string; sessions: SessionSummary[] }>();

  for (const session of sessions) {
    const group = groups.get(session.directory) ?? {
      path: session.directory,
      name: directoryNames.get(session.directory) || session.project || session.directory,
      sessions: [],
    };
    group.sessions.push(session);
    groups.set(session.directory, group);
  }

  return Array.from(groups.values()).sort((a, b) => {
    const aTime = Math.max(...a.sessions.map((session) => session.time_updated_raw || 0));
    const bTime = Math.max(...b.sessions.map((session) => session.time_updated_raw || 0));
    return bTime - aTime;
  });
}

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

function formatTokens(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function errorText(error: unknown) {
  if (error instanceof Error) return error.message;
  return String(error || "Unknown error");
}
