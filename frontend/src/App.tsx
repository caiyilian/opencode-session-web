import { useEffect, useMemo, useReducer, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  getAvailableModels,
  getDirectories,
  getSession,
  getSessions,
  getStats,
  type DirectorySummary,
  type MessagePart,
  type SessionDetailResponse,
  type SessionMessage,
  type SessionSummary,
  type StatsResponse,
} from "./api";

const BLOCKED_PROVIDERS_STORAGE_KEY = "blockedProviders";

interface DashboardData {
  stats: StatsResponse;
  directories: DirectorySummary[];
  sessions: SessionSummary[];
  availableModels: string[];
  modelLoadError?: string;
}

interface BrowseState {
  query: string;
  selectedDirectory: string;
  selectedModel: string;
  selectedSessionId: string;
  sidebarOpen: boolean;
  hiddenProviders: string[];
}

type BrowseAction =
  | { type: "setQuery"; value: string }
  | { type: "selectDirectory"; value: string }
  | { type: "selectModel"; value: string }
  | { type: "selectSession"; value: string }
  | { type: "toggleSidebar" }
  | { type: "toggleProvider"; provider: string }
  | { type: "clearFilters" };

type LoadState =
  | { status: "loading" }
  | { status: "ready"; data: DashboardData }
  | { status: "error"; message: string };

type DetailState =
  | { status: "idle" }
  | { status: "loading"; sessionId: string }
  | { status: "ready"; sessionId: string; data: SessionDetailResponse }
  | { status: "error"; sessionId: string; message: string };

interface SessionFilters {
  query: string;
  directory: string;
  model: string;
}

export default function App() {
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [detailState, setDetailState] = useState<DetailState>({ status: "idle" });
  const [browseState, dispatch] = useReducer(browseReducer, undefined, createInitialBrowseState);

  useEffect(() => {
    let mounted = true;

    async function load() {
      try {
        const [stats, directories, sessions, models] = await Promise.all([
          getStats(),
          getDirectories(),
          getSessions({ limit: 200 }),
          getAvailableModels()
            .then((response) => ({ models: response.models, error: undefined }))
            .catch((error: unknown) => ({ models: [] as string[], error: errorText(error) })),
        ]);

        if (!mounted) return;
        setLoadState({
          status: "ready",
          data: {
            stats,
            directories: directories.directories,
            sessions: sessions.sessions,
            availableModels: models.models,
            modelLoadError: models.error,
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

  useEffect(() => {
    writeHiddenProviders(browseState.hiddenProviders);
  }, [browseState.hiddenProviders]);

  const data = loadState.status === "ready" ? loadState.data : null;
  const filters = useMemo<SessionFilters>(
    () => ({
      query: browseState.query,
      directory: browseState.selectedDirectory,
      model: browseState.selectedModel,
    }),
    [browseState.query, browseState.selectedDirectory, browseState.selectedModel],
  );
  const filteredSessions = useMemo(
    () => filterSessions(data?.sessions ?? [], filters),
    [data?.sessions, filters],
  );
  const groupedSessions = useMemo(
    () => groupSessions(filteredSessions, data?.directories ?? []),
    [filteredSessions, data?.directories],
  );
  const modelOptions = useMemo(
    () => deriveModelOptions(data?.sessions ?? []),
    [data?.sessions],
  );
  const visibleModelOptions = useMemo(
    () => modelOptions.filter((model) => !isProviderHidden(model, browseState.hiddenProviders)),
    [browseState.hiddenProviders, modelOptions],
  );
  const providerOptions = useMemo(
    () => deriveProviderOptions([...(data?.availableModels ?? []), ...modelOptions]),
    [data?.availableModels, modelOptions],
  );
  const selectedSession =
    filteredSessions.find((session) => session.id === browseState.selectedSessionId) ??
    filteredSessions[0] ??
    null;

  useEffect(() => {
    if (!selectedSession) {
      setDetailState({ status: "idle" });
      return;
    }

    let mounted = true;
    const sessionId = selectedSession.id;
    setDetailState({ status: "loading", sessionId });

    getSession(sessionId)
      .then((detail) => {
        if (mounted) setDetailState({ status: "ready", sessionId, data: detail });
      })
      .catch((error: unknown) => {
        if (mounted) setDetailState({ status: "error", sessionId, message: errorText(error) });
      });

    return () => {
      mounted = false;
    };
  }, [selectedSession?.id]);

  const activeFilterCount = [filters.query.trim(), filters.directory, filters.model].filter(
    Boolean,
  ).length;

  return (
    <main className={`app-shell ${browseState.sidebarOpen ? "" : "sidebar-collapsed"}`}>
      <aside className="sidebar-shell">
        <div className="brand-row">
          <span className="brand-mark" aria-hidden="true">
            ◆
          </span>
          <h1>OpenCode Sessions</h1>
        </div>
        <div className="filter-stack">
          <input
            className="search-input"
            placeholder="Search sessions"
            value={browseState.query}
            onChange={(event) => dispatch({ type: "setQuery", value: event.target.value })}
          />
          <label className="filter-field">
            <span>Directory</span>
            <select
              className="filter-select"
              value={browseState.selectedDirectory}
              onChange={(event) =>
                dispatch({ type: "selectDirectory", value: event.target.value })
              }
            >
              <option value="">All directories</option>
              {data?.directories.map((directory) => (
                <option key={directory.path} value={directory.path}>
                  {directory.name}
                </option>
              ))}
            </select>
          </label>
          <label className="filter-field">
            <span>Model</span>
            <select
              className="filter-select"
              disabled={visibleModelOptions.length === 0}
              value={browseState.selectedModel}
              onChange={(event) => dispatch({ type: "selectModel", value: event.target.value })}
            >
              <option value="">All models</option>
              {visibleModelOptions.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </label>
          {providerOptions.length > 0 && (
            <div className="provider-filter" aria-label="Provider visibility">
              <div className="provider-heading">
                <span>Providers</span>
                <span>{browseState.hiddenProviders.length} hidden</span>
              </div>
              <div className="provider-options">
                {providerOptions.map((provider) => (
                  <label
                    className={`provider-option ${
                      browseState.hiddenProviders.includes(provider) ? "muted" : ""
                    }`}
                    key={provider}
                  >
                    <input
                      checked={browseState.hiddenProviders.includes(provider)}
                      onChange={() => dispatch({ type: "toggleProvider", provider })}
                      type="checkbox"
                    />
                    <span>{provider}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
          {activeFilterCount > 0 && (
            <button
              className="clear-filter-button"
              type="button"
              onClick={() => dispatch({ type: "clearFilters" })}
            >
              Clear filters
            </button>
          )}
        </div>
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
              <button
                className={`group-header ${
                  browseState.selectedDirectory === group.path ? "active" : ""
                }`}
                type="button"
                onClick={() => dispatch({ type: "selectDirectory", value: group.path })}
              >
                <span>{group.name}</span>
                <span>{group.sessions.length}</span>
              </button>
              {group.sessions.map((session) => (
                <button
                  className={`session-row ${session.id === selectedSession?.id ? "active" : ""}`}
                  key={session.id}
                  type="button"
                  onClick={() => dispatch({ type: "selectSession", value: session.id })}
                >
                  <span className="session-title">{session.title || "Untitled session"}</span>
                  <span className="session-meta">
                    <span>{session.model || "N/A"}</span>
                    {isProviderHidden(session.model, browseState.hiddenProviders) && (
                      <span className="state-pill muted">Hidden provider</span>
                    )}
                    {isModelUnavailable(session.model, data?.availableModels ?? []) && (
                      <span className="state-pill warning">Unavailable</span>
                    )}
                    <span>{session.time_updated}</span>
                  </span>
                </button>
              ))}
            </section>
          ))}
        </nav>
      </aside>

      <section className="content-shell">
        <header className="content-header">
          <div className="header-title-row">
            <button
              aria-expanded={browseState.sidebarOpen}
              aria-label={browseState.sidebarOpen ? "Collapse sidebar" : "Open sidebar"}
              className="sidebar-toggle"
              type="button"
              onClick={() => dispatch({ type: "toggleSidebar" })}
            >
              <span aria-hidden="true">{browseState.sidebarOpen ? "×" : "☰"}</span>
            </button>
            <div>
              <p className="eyebrow">Session Browser</p>
              <h2>{selectedSession?.title || "OpenCode Sessions"}</h2>
            </div>
          </div>
          {data && (
            <div className="summary-strip" aria-label="Summary">
              <SummaryItem label="Sessions" value={formatNumber(data.stats.total_sessions)} />
              <SummaryItem label="Shown" value={formatNumber(filteredSessions.length)} />
              <SummaryItem label="Input" value={formatTokens(data.stats.total_tokens_input)} />
              <SummaryItem label="Output" value={formatTokens(data.stats.total_tokens_output)} />
              <SummaryItem label="Models" value={formatNumber(data.availableModels.length)} />
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
                    <dd className="value-stack">
                      <span>{selectedSession.model || "N/A"}</span>
                      {isProviderHidden(selectedSession.model, browseState.hiddenProviders) && (
                        <span className="inline-status muted">Provider hidden locally</span>
                      )}
                      {isModelUnavailable(selectedSession.model, data.availableModels) && (
                        <span className="inline-status warning">Model not in available list</span>
                      )}
                    </dd>
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
                  <button
                    className={`directory-row ${
                      browseState.selectedDirectory === directory.path ? "active" : ""
                    }`}
                    key={directory.path}
                    type="button"
                    onClick={() => dispatch({ type: "selectDirectory", value: directory.path })}
                  >
                    <span>{directory.name}</span>
                    <span>{directory.session_count}</span>
                  </button>
                ))}
              </div>
              {data.modelLoadError && (
                <p className="inline-warning">Models unavailable: {data.modelLoadError}</p>
              )}
            </section>

            <section className="detail-panel timeline-panel">
              <div className="panel-heading">
                <h3>Messages</h3>
                <span>
                  {detailState.status === "ready"
                    ? `${detailState.data.message_count} messages`
                    : selectedSession
                      ? "Loading"
                      : "No session"}
                </span>
              </div>
              <MessageTimeline state={detailState} />
            </section>
          </div>
        )}
      </section>
    </main>
  );
}

function browseReducer(state: BrowseState, action: BrowseAction): BrowseState {
  switch (action.type) {
    case "setQuery":
      return { ...state, query: action.value, selectedSessionId: "" };
    case "selectDirectory":
      return { ...state, selectedDirectory: action.value, selectedSessionId: "" };
    case "selectModel":
      return { ...state, selectedModel: action.value, selectedSessionId: "" };
    case "selectSession":
      return { ...state, selectedSessionId: action.value, sidebarOpen: false };
    case "toggleSidebar":
      return { ...state, sidebarOpen: !state.sidebarOpen };
    case "toggleProvider": {
      const hiddenProviders = state.hiddenProviders.includes(action.provider)
        ? state.hiddenProviders.filter((provider) => provider !== action.provider)
        : [...state.hiddenProviders, action.provider].sort();
      const selectedModel = isProviderHidden(state.selectedModel, hiddenProviders)
        ? ""
        : state.selectedModel;

      return { ...state, hiddenProviders, selectedModel, selectedSessionId: "" };
    }
    case "clearFilters":
      return { ...state, query: "", selectedDirectory: "", selectedModel: "", selectedSessionId: "" };
    default:
      return state;
  }
}

function createInitialBrowseState(): BrowseState {
  return {
    query: "",
    selectedDirectory: "",
    selectedModel: "",
    selectedSessionId: "",
    sidebarOpen: true,
    hiddenProviders: readHiddenProviders(),
  };
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

function MessageTimeline({ state }: { state: DetailState }) {
  if (state.status === "idle") return <PanelStatus label="No session selected" />;
  if (state.status === "loading") return <PanelStatus label="Loading messages" />;
  if (state.status === "error") return <PanelStatus label={state.message} tone="error" />;
  if (state.data.messages.length === 0) return <PanelStatus label="No messages" />;

  return (
    <div className="message-timeline">
      {state.data.messages.map((message, index) => (
        <MessageCard index={index} key={message.id || index} message={message} />
      ))}
    </div>
  );
}

function MessageCard({ message, index }: { message: SessionMessage; index: number }) {
  const roleClass = roleClassName(message.role);
  const tokens = formatMessageTokens(message.tokens);

  return (
    <article className={`message-card ${roleClass}`}>
      <div className="message-avatar" aria-hidden="true">
        {roleLabel(message.role).slice(0, 2)}
      </div>
      <div className="message-content">
        <div className="message-header">
          <strong>{roleLabel(message.role)}</strong>
          <span>{message.time_created}</span>
          {tokens && <span>{tokens}</span>}
        </div>
        <div className="message-parts">
          {message.parts.length > 0 ? (
            message.parts.map((part, partIndex) => (
              <MessagePartView index={partIndex} key={`${index}-${partIndex}`} part={part} />
            ))
          ) : (
            <div className="message-text muted">(empty)</div>
          )}
        </div>
      </div>
    </article>
  );
}

function MessagePartView({ part, index }: { part: MessagePart; index: number }) {
  if (part.type === "text") {
    return <MarkdownContent source={stringValue(part.text)} />;
  }

  if (part.type === "reasoning") {
    return (
      <details className="part-block reasoning-part">
        <summary>Reasoning</summary>
        <div className="part-text">{stringValue(part.text)}</div>
      </details>
    );
  }

  if (part.type === "tool") {
    const description = stringValue(part.description);
    const input = stringValue(part.input);
    const output = stringValue(part.output);
    const isHidden = Boolean(part.is_hidden);

    return (
      <div className="part-block tool-part">
        <div className="part-heading">
          <strong>{stringValue(part.tool) || "tool"}</strong>
          {isHidden && <span className="state-pill muted">Hidden output</span>}
        </div>
        {description && <div className="part-text compact">{description}</div>}
        {input && (
          <pre className="part-code">
            <code>{input}</code>
          </pre>
        )}
        {!isHidden && output && (
          <pre className="part-code">
            <code>{output}</code>
          </pre>
        )}
      </div>
    );
  }

  if (part.type === "tool_result") {
    const content = stringifyValue(part.content);
    const isHidden = Boolean(part.is_hidden);
    const status = stringValue(part.status);

    return (
      <div className="part-block tool-part">
        <div className="part-heading">
          <strong>{stringValue(part.tool_name) || "tool result"}</strong>
          {status && <span className="state-pill">{status}</span>}
          {isHidden && <span className="state-pill muted">Hidden output</span>}
        </div>
        {!isHidden && content && (
          <pre className="part-code">
            <code>{content}</code>
          </pre>
        )}
      </div>
    );
  }

  if (part.type === "step-finish") {
    const reason = stringValue(part.reason);
    const tokens = numberRecordValue(part.tokens);

    return (
      <div className="part-block step-part">
        <span>Step finished</span>
        {reason && <span>{reason}</span>}
        {tokens && <span>{formatStepTokens(tokens)}</span>}
        {typeof part.cost === "number" && <span>${part.cost.toFixed(6)}</span>}
      </div>
    );
  }

  return (
    <pre className="part-block part-code unknown-part">
      <code>
        {part.type || `part-${index}`}
        {"\n"}
        {stringifyValue(part)}
      </code>
    </pre>
  );
}

function MarkdownContent({ source }: { source: string }) {
  if (!source.trim()) return <div className="message-text muted">(empty)</div>;

  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{source}</ReactMarkdown>
    </div>
  );
}

function filterSessions(sessions: SessionSummary[], filters: SessionFilters) {
  const normalized = filters.query.trim().toLowerCase();

  return sessions.filter((session) => {
    if (filters.directory && session.directory !== filters.directory) return false;
    if (filters.model && session.model !== filters.model) return false;
    if (!normalized) return true;

    return [session.title, session.directory, session.project, session.model]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(normalized));
  });
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

function deriveModelOptions(sessions: SessionSummary[]) {
  return Array.from(
    new Set(sessions.map((session) => session.model).filter((model) => model.trim())),
  ).sort((a, b) => a.localeCompare(b));
}

function deriveProviderOptions(models: string[]) {
  return Array.from(new Set(models.map(providerForModel).filter(Boolean))).sort((a, b) =>
    a.localeCompare(b),
  );
}

function providerForModel(model: string) {
  if (!model.trim() || model.trim().toUpperCase() === "N/A") return "";
  const slashIndex = model.indexOf("/");
  if (slashIndex <= 0) return "";
  return model.slice(0, slashIndex + 1).trim();
}

function isProviderHidden(model: string, hiddenProviders: string[]) {
  const provider = providerForModel(model);
  return Boolean(provider && hiddenProviders.includes(provider));
}

function isModelUnavailable(model: string, availableModels: string[]) {
  return Boolean(model && availableModels.length > 0 && !availableModels.includes(model));
}

function readHiddenProviders() {
  if (typeof window === "undefined") return [];

  try {
    const parsed = JSON.parse(window.localStorage.getItem(BLOCKED_PROVIDERS_STORAGE_KEY) || "[]");
    return Array.isArray(parsed)
      ? parsed.filter((provider): provider is string => typeof provider === "string")
      : [];
  } catch (_) {
    return [];
  }
}

function writeHiddenProviders(hiddenProviders: string[]) {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.setItem(BLOCKED_PROVIDERS_STORAGE_KEY, JSON.stringify(hiddenProviders));
  } catch (_) {
    // Ignore storage failures so private browsing modes still render the shell.
  }
}

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

function formatTokens(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function formatMessageTokens(tokens: SessionMessage["tokens"]) {
  const input = tokens.input ?? 0;
  const output = tokens.output ?? 0;
  if (!input && !output) return "";
  return `${formatTokens(input + output)} tokens`;
}

function formatStepTokens(tokens: Record<string, number>) {
  const total =
    tokens.total ??
    Object.values(tokens).reduce((sum, value) => sum + (typeof value === "number" ? value : 0), 0);
  return `${formatTokens(total)} tokens`;
}

function stringValue(value: unknown) {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  return stringifyValue(value);
}

function numberRecordValue(value: unknown): Record<string, number> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;

  const entries = Object.entries(value).filter((entry): entry is [string, number] => {
    return typeof entry[1] === "number";
  });
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

function roleClassName(role: string) {
  if (role === "user" || role === "assistant" || role === "tool") return role;
  return "other";
}

function roleLabel(role: string) {
  if (role === "user") return "User";
  if (role === "assistant") return "Assistant";
  if (role === "tool") return "Tool";
  return role || "Message";
}

function stringifyValue(value: unknown) {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;

  try {
    return JSON.stringify(value, null, 2);
  } catch (_) {
    return String(value);
  }
}

function errorText(error: unknown) {
  if (error instanceof Error) return error.message;
  return String(error || "Unknown error");
}
