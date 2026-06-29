import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import Prism from "prismjs";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-css";
import "prismjs/components/prism-diff";
import "prismjs/components/prism-json";
import "prismjs/components/prism-jsx";
import "prismjs/components/prism-markup";
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-typescript";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  compareSessions,
  createNewSessionStream,
  getAvailableModels,
  getDirectories,
  getSession,
  getSessionStreamUrl,
  getSessions,
  getStats,
  type DirectorySummary,
  type CompareResponse,
  type CompareSession,
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

type CompareState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: CompareResponse }
  | { status: "error"; message: string };

type StreamStatus = "connecting" | "streaming" | "done" | "error" | "stopped";

interface SessionFilters {
  query: string;
  directory: string;
  model: string;
}

interface StreamDraft {
  sessionId: string;
  userMessage: SessionMessage;
  assistantText: string;
  thinkingText: string;
  tools: string[];
  status: StreamStatus;
  statusLabel: string;
  error?: string;
}

export default function App() {
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [detailState, setDetailState] = useState<DetailState>({ status: "idle" });
  const [browseState, dispatch] = useReducer(browseReducer, undefined, createInitialBrowseState);
  const [composerText, setComposerText] = useState("");
  const [composerModel, setComposerModel] = useState("");
  const [composerError, setComposerError] = useState("");
  const [streamDraft, setStreamDraft] = useState<StreamDraft | null>(null);
  const [newSessionOpen, setNewSessionOpen] = useState(false);
  const [newSessionDirectory, setNewSessionDirectory] = useState("");
  const [newSessionCustomDirectory, setNewSessionCustomDirectory] = useState("");
  const [newSessionMessage, setNewSessionMessage] = useState("");
  const [newSessionModel, setNewSessionModel] = useState("");
  const [newSessionError, setNewSessionError] = useState("");
  const [newSessionDraft, setNewSessionDraft] = useState<StreamDraft | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const newSessionAbortRef = useRef<AbortController | null>(null);

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

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      newSessionAbortRef.current?.abort();
    };
  }, []);

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
  const composerModelOptions = useMemo(
    () => deriveComposerModelOptions(visibleModelOptions, selectedSession?.model ?? ""),
    [selectedSession?.model, visibleModelOptions],
  );

  useEffect(() => {
    if (!selectedSession) {
      setDetailState({ status: "idle" });
      setStreamDraft(null);
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
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

  useEffect(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setStreamDraft(null);
    setComposerError("");
    setComposerModel((currentModel) => {
      if (currentModel && composerModelOptions.includes(currentModel)) return currentModel;
      return composerModelOptions[0] ?? "";
    });
  }, [composerModelOptions, selectedSession?.id]);

  const activeFilterCount = [filters.query.trim(), filters.directory, filters.model].filter(
    Boolean,
  ).length;

  function reloadSessionDetail(sessionId: string, clearDraft = false) {
    return getSession(sessionId)
      .then((detail) => {
        setDetailState({ status: "ready", sessionId, data: detail });
        if (clearDraft) setStreamDraft(null);
      })
      .catch((error: unknown) => {
        setDetailState({ status: "error", sessionId, message: errorText(error) });
      });
  }

  function refreshDashboard(selectSessionId?: string) {
    return Promise.all([getStats(), getDirectories(), getSessions({ limit: 200 })])
      .then(([stats, directories, sessions]) => {
        setLoadState((current) => {
          const previous = current.status === "ready" ? current.data : null;
          return {
            status: "ready",
            data: {
              stats,
              directories: directories.directories,
              sessions: sessions.sessions,
              availableModels: previous?.availableModels ?? [],
              modelLoadError: previous?.modelLoadError,
            },
          };
        });
        if (selectSessionId) dispatch({ type: "selectSession", value: selectSessionId });
      })
      .catch((error: unknown) => {
        setLoadState({ status: "error", message: errorText(error) });
      });
  }

  function stopStream() {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setStreamDraft((draft) =>
      draft ? { ...draft, status: "stopped", statusLabel: "Stopped by user" } : draft,
    );
  }

  function submitComposer() {
    if (!selectedSession) return;

    const message = composerText.trim();
    if (!message) {
      setComposerError("Enter a message before sending.");
      return;
    }

    eventSourceRef.current?.close();
    setComposerError("");
    setComposerText("");

    const sessionId = selectedSession.id;
    const now = Date.now();
    const draft: StreamDraft = {
      sessionId,
      userMessage: {
        id: `local-user-${now}`,
        role: "user",
        parts: [{ type: "text", text: message }],
        time_created: "Just now",
        time_created_raw: now,
        tokens: {},
      },
      assistantText: "",
      thinkingText: "",
      tools: [],
      status: "connecting",
      statusLabel: "Connecting",
    };
    setStreamDraft(draft);

    const source = new EventSource(
      getSessionStreamUrl(sessionId, {
        message,
        model: normalizeModelValue(composerModel),
      }),
    );
    eventSourceRef.current = source;

    const appendDraft = (update: (draft: StreamDraft) => StreamDraft) => {
      setStreamDraft((current) => {
        if (!current || current.sessionId !== sessionId) return current;
        return update(current);
      });
    };
    const closeSource = () => {
      source.close();
      if (eventSourceRef.current === source) eventSourceRef.current = null;
    };

    source.addEventListener("thinking", (event) => {
      appendDraft((current) => ({
        ...current,
        status: "streaming",
        statusLabel: "Thinking",
        thinkingText: appendStreamText(current.thinkingText, event.data),
      }));
    });

    source.addEventListener("text", (event) => {
      appendDraft((current) => ({
        ...current,
        status: "streaming",
        statusLabel: "Streaming",
        assistantText: appendStreamText(current.assistantText, event.data),
      }));
    });

    source.addEventListener("tool_use", (event) => {
      appendDraft((current) => ({
        ...current,
        status: "streaming",
        statusLabel: "Using tool",
        tools: [...current.tools, toolLabel(event.data)],
      }));
    });

    source.addEventListener("tool_result", () => {
      appendDraft((current) => ({
        ...current,
        status: "streaming",
        statusLabel: "Processing tool result",
      }));
    });

    source.addEventListener("status", (event) => {
      const label = event.data === "waiting" ? "Waiting for model" : "Thinking";
      appendDraft((current) => ({ ...current, statusLabel: label }));
    });

    source.addEventListener("done", () => {
      closeSource();
      appendDraft((current) => ({ ...current, status: "done", statusLabel: "Done" }));
      void reloadSessionDetail(sessionId, true);
    });

    source.addEventListener("stream_error", (event) => {
      closeSource();
      appendDraft((current) => ({
        ...current,
        status: "error",
        statusLabel: "Error",
        error: streamErrorText(event.data),
      }));
    });

    source.onerror = () => {
      if (eventSourceRef.current !== source) return;
      closeSource();
      appendDraft((current) => ({
        ...current,
        status: "error",
        statusLabel: "Connection interrupted",
        error: "Connection interrupted. Stop and try another model if the model is unavailable.",
      }));
    };
  }

  function openNewSession() {
    const preferredDirectory = selectedSession?.directory || data?.directories[0]?.path || "";
    setNewSessionDirectory(preferredDirectory);
    setNewSessionCustomDirectory("");
    setNewSessionMessage("");
    setNewSessionModel(composerModel);
    setNewSessionError("");
    setNewSessionDraft(null);
    setNewSessionOpen(true);
  }

  function closeNewSession() {
    if (isStreamActive(newSessionDraft)) return;
    setNewSessionOpen(false);
    setNewSessionError("");
  }

  function stopNewSession() {
    newSessionAbortRef.current?.abort();
    newSessionAbortRef.current = null;
    setNewSessionDraft((draft) =>
      draft ? { ...draft, status: "stopped", statusLabel: "Stopped by user" } : draft,
    );
  }

  async function submitNewSession() {
    const directory =
      newSessionDirectory === "__custom__" ? newSessionCustomDirectory.trim() : newSessionDirectory;
    const message = newSessionMessage.trim();

    if (!directory) {
      setNewSessionError("Choose or enter a working directory.");
      return;
    }
    if (!message) {
      setNewSessionError("Enter the first message.");
      return;
    }

    const controller = new AbortController();
    newSessionAbortRef.current = controller;
    setNewSessionError("");
    setNewSessionMessage("");

    const now = Date.now();
    const streamSessionId = `new-${now}`;
    setNewSessionDraft({
      sessionId: streamSessionId,
      userMessage: {
        id: `local-new-user-${now}`,
        role: "user",
        parts: [{ type: "text", text: message }],
        time_created: "Just now",
        time_created_raw: now,
        tokens: {},
      },
      assistantText: "",
      thinkingText: "",
      tools: [],
      status: "connecting",
      statusLabel: "Connecting",
    });

    try {
      const response = await createNewSessionStream(
        {
          directory,
          message,
          model: normalizeModelValue(newSessionModel),
        },
        controller.signal,
      );

      if (!response.ok) {
        throw new Error(await responseErrorText(response));
      }
      if (!response.body) {
        throw new Error("Streaming response is unavailable.");
      }

      let newSessionId = "";
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";

        for (const block of blocks) {
          const event = parseSseBlock(block);
          if (!event.type) continue;

          if (event.type === "done") {
            const donePayload = parseDonePayload(event.data);
            newSessionId = donePayload.session_id || newSessionId;
            setNewSessionDraft((draft) =>
              draft ? { ...draft, status: "done", statusLabel: "Done" } : draft,
            );
          } else if (event.type === "stream_error") {
            setNewSessionDraft((draft) =>
              draft
                ? {
                    ...draft,
                    status: "error",
                    statusLabel: "Error",
                    error: streamErrorText(event.data),
                  }
                : draft,
            );
            return;
          } else {
            applyStreamEvent(setNewSessionDraft, streamSessionId, event.type, event.data);
          }
        }
      }

      if (newSessionId) {
        await refreshDashboard(newSessionId);
        await reloadSessionDetail(newSessionId, true);
        setNewSessionOpen(false);
      }
    } catch (error) {
      if ((error as { name?: string }).name === "AbortError") return;
      setNewSessionDraft((draft) =>
        draft
          ? {
              ...draft,
              status: "error",
              statusLabel: "Error",
              error: errorText(error),
            }
          : draft,
      );
      setNewSessionError(errorText(error));
    } finally {
      if (newSessionAbortRef.current === controller) newSessionAbortRef.current = null;
    }
  }

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
            <button className="new-session-button" type="button" onClick={openNewSession}>
              New Session
            </button>
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
        {newSessionOpen && (
          <NewSessionPanel
            customDirectory={newSessionCustomDirectory}
            directories={data?.directories ?? []}
            directory={newSessionDirectory}
            draft={newSessionDraft}
            error={newSessionError}
            message={newSessionMessage}
            model={newSessionModel}
            modelOptions={composerModelOptions}
            onClose={closeNewSession}
            onCustomDirectoryChange={setNewSessionCustomDirectory}
            onDirectoryChange={(value) => {
              setNewSessionDirectory(value);
              if (newSessionError) setNewSessionError("");
            }}
            onMessageChange={(value) => {
              setNewSessionMessage(value);
              if (newSessionError) setNewSessionError("");
            }}
            onModelChange={setNewSessionModel}
            onStop={stopNewSession}
            onSubmit={submitNewSession}
          />
        )}
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

            <StatsPanel
              stats={data.stats}
              onSelectSession={(sessionId) => dispatch({ type: "selectSession", value: sessionId })}
            />

            <ComparePanel sessions={data.sessions} />

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
              <MessageTimeline state={detailState} streamDraft={streamDraft} />
              <SessionComposer
                disabled={!selectedSession}
                error={composerError}
                model={composerModel}
                modelOptions={composerModelOptions}
                selectedSession={selectedSession}
                streamDraft={streamDraft}
                text={composerText}
                onModelChange={setComposerModel}
                onStop={stopStream}
                onSubmit={submitComposer}
                onTextChange={(value) => {
                  setComposerText(value);
                  if (composerError) setComposerError("");
                }}
              />
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

function StatsPanel({
  stats,
  onSelectSession,
}: {
  stats: StatsResponse;
  onSelectSession: (sessionId: string) => void;
}) {
  const maxModelCount = maxCount(stats.top_models.map((model) => model.count));
  const maxDirectoryCount = maxCount(stats.top_directories.map((directory) => directory.count));

  return (
    <section className="detail-panel stats-panel">
      <div className="panel-heading">
        <h3>Usage Stats</h3>
        <span>{formatNumber(stats.total_sessions)} sessions</span>
      </div>
      <div className="stats-metrics">
        <SummaryItem label="Projects" value={formatNumber(stats.total_projects)} />
        <SummaryItem label="Cost" value={`$${stats.total_cost.toFixed(4)}`} />
        <SummaryItem label="Input" value={formatTokens(stats.total_tokens_input)} />
        <SummaryItem label="Output" value={formatTokens(stats.total_tokens_output)} />
      </div>
      <div className="stats-columns">
        <StatsRankList
          emptyLabel="No model stats"
          items={stats.top_models.map((model) => ({
            count: model.count,
            label: model.model || "N/A",
            maxCount: maxModelCount,
          }))}
          title="Top Models"
        />
        <StatsRankList
          emptyLabel="No directory stats"
          items={stats.top_directories.map((directory) => ({
            count: directory.count,
            label: directory.path,
            maxCount: maxDirectoryCount,
          }))}
          title="Top Directories"
        />
        <section className="stats-column">
          <h4>Recent Sessions</h4>
          {stats.recent_sessions.length > 0 ? (
            <div className="recent-session-list">
              {stats.recent_sessions.map((session) => (
                <button
                  className="recent-session-row"
                  key={session.id}
                  type="button"
                  onClick={() => onSelectSession(session.id)}
                >
                  <span>{session.title || "Untitled session"}</span>
                  <span>{session.time_updated}</span>
                </button>
              ))}
            </div>
          ) : (
            <PanelStatus label="No recent sessions" />
          )}
        </section>
      </div>
    </section>
  );
}

function StatsRankList({
  emptyLabel,
  items,
  title,
}: {
  emptyLabel: string;
  items: Array<{ count: number; label: string; maxCount: number }>;
  title: string;
}) {
  return (
    <section className="stats-column">
      <h4>{title}</h4>
      {items.length > 0 ? (
        <div className="stats-rank-list">
          {items.map((item) => (
            <div className="stats-rank-row" key={`${title}-${item.label}`}>
              <div className="stats-rank-header">
                <span>{item.label || "N/A"}</span>
                <strong>{formatNumber(item.count)}</strong>
              </div>
              <div className="stats-bar" aria-hidden="true">
                <span style={{ width: `${percentage(item.count, item.maxCount)}%` }} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <PanelStatus label={emptyLabel} />
      )}
    </section>
  );
}

function ComparePanel({ sessions }: { sessions: SessionSummary[] }) {
  const defaultLeftId = sessions[0]?.id || "";
  const defaultRightId = sessions.find((session) => session.id !== defaultLeftId)?.id || "";
  const [leftId, setLeftId] = useState(defaultLeftId);
  const [rightId, setRightId] = useState(defaultRightId);
  const [compareState, setCompareState] = useState<CompareState>({ status: "idle" });

  useEffect(() => {
    const available = new Set(sessions.map((session) => session.id));
    setLeftId((current) => (current && available.has(current) ? current : defaultLeftId));
    setRightId((current) => (current && available.has(current) ? current : defaultRightId));
  }, [defaultLeftId, defaultRightId, sessions]);

  async function loadComparison() {
    if (!leftId || !rightId) {
      setCompareState({ status: "error", message: "Choose two sessions to compare" });
      return;
    }
    if (leftId === rightId) {
      setCompareState({ status: "error", message: "Choose two different sessions" });
      return;
    }

    setCompareState({ status: "loading" });
    try {
      const data = await compareSessions(leftId, rightId);
      setCompareState({ status: "ready", data });
    } catch (error) {
      setCompareState({ status: "error", message: errorText(error) });
    }
  }

  function updateLeft(value: string) {
    setLeftId(value);
    setCompareState({ status: "idle" });
  }

  function updateRight(value: string) {
    setRightId(value);
    setCompareState({ status: "idle" });
  }

  return (
    <section className="detail-panel compare-panel">
      <div className="panel-heading">
        <h3>Compare Sessions</h3>
        <span>{sessions.length} loaded</span>
      </div>
      <div className="compare-controls">
        <label>
          <span>First session</span>
          <select value={leftId} onChange={(event) => updateLeft(event.target.value)}>
            <option value="">Select session</option>
            {sessions.map((session) => (
              <option key={`left-${session.id}`} value={session.id}>
                {session.title || "Untitled session"}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Second session</span>
          <select value={rightId} onChange={(event) => updateRight(event.target.value)}>
            <option value="">Select session</option>
            {sessions.map((session) => (
              <option key={`right-${session.id}`} value={session.id}>
                {session.title || "Untitled session"}
              </option>
            ))}
          </select>
        </label>
        <button
          disabled={compareState.status === "loading" || sessions.length < 2}
          type="button"
          onClick={loadComparison}
        >
          Compare
        </button>
      </div>
      {compareState.status === "idle" && (
        <PanelStatus label={sessions.length < 2 ? "Need two loaded sessions" : "Choose two sessions and compare"} />
      )}
      {compareState.status === "loading" && <PanelStatus label="Loading comparison" />}
      {compareState.status === "error" && <PanelStatus label={compareState.message} tone="error" />}
      {compareState.status === "ready" && <CompareResult data={compareState.data} />}
    </section>
  );
}

function CompareResult({ data }: { data: CompareResponse }) {
  return (
    <div className="compare-grid">
      <CompareSessionColumn label="First" session={data.session1} />
      <CompareSessionColumn label="Second" session={data.session2} />
    </div>
  );
}

function CompareSessionColumn({ label, session }: { label: string; session: CompareSession }) {
  const totalTokens = session.tokens_input + session.tokens_output;

  return (
    <section className="compare-column">
      <div className="compare-session-header">
        <span>{label}</span>
        <h4>{session.title || "Untitled session"}</h4>
        <p>
          {session.model || "N/A"} · {session.message_count} messages · {formatTokens(totalTokens)} tokens · $
          {session.cost.toFixed(4)}
        </p>
      </div>
      <div className="compare-message-list">
        {session.messages.length > 0 ? (
          session.messages.slice(0, 12).map((message) => (
            <article className={`compare-message ${roleClassName(message.role)}`} key={message.id}>
              <div>
                <strong>{roleLabel(message.role)}</strong>
                <span>{formatCompareTime(message.time)}</span>
              </div>
              <p>{message.content || "(empty)"}</p>
            </article>
          ))
        ) : (
          <PanelStatus label="No messages" />
        )}
      </div>
    </section>
  );
}

function MessageTimeline({ state, streamDraft }: { state: DetailState; streamDraft?: StreamDraft | null }) {
  if (state.status === "idle") return <PanelStatus label="No session selected" />;
  if (state.status === "loading") return <PanelStatus label="Loading messages" />;
  if (state.status === "error") return <PanelStatus label={state.message} tone="error" />;
  if (state.data.messages.length === 0 && !streamDraft) return <PanelStatus label="No messages" />;

  return (
    <div className="message-timeline">
      {state.data.messages.map((message, index) => (
        <MessageCard index={index} key={message.id || index} message={message} />
      ))}
      {streamDraft?.sessionId === state.sessionId && (
        <>
          <MessageCard index={state.data.messages.length} message={streamDraft.userMessage} />
          <StreamingMessageCard draft={streamDraft} />
        </>
      )}
    </div>
  );
}

function SessionComposer({
  disabled,
  error,
  model,
  modelOptions,
  selectedSession,
  streamDraft,
  text,
  onModelChange,
  onStop,
  onSubmit,
  onTextChange,
}: {
  disabled: boolean;
  error: string;
  model: string;
  modelOptions: string[];
  selectedSession: SessionSummary | null;
  streamDraft: StreamDraft | null;
  text: string;
  onModelChange: (value: string) => void;
  onStop: () => void;
  onSubmit: () => void;
  onTextChange: (value: string) => void;
}) {
  const isStreaming =
    streamDraft?.status === "connecting" || streamDraft?.status === "streaming";

  return (
    <form
      className="composer-panel"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="composer-toolbar">
        <label className="composer-model">
          <span>Model</span>
          <select
            disabled={disabled || isStreaming}
            value={model}
            onChange={(event) => onModelChange(event.target.value)}
          >
            <option value="">Default model</option>
            {modelOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <span className={`composer-state ${streamDraft?.status ?? "idle"}`}>
          {streamDraft?.statusLabel ?? (selectedSession ? "Ready" : "No session")}
        </span>
      </div>
      <textarea
        disabled={disabled || isStreaming}
        placeholder="Continue this session"
        rows={4}
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
      />
      <div className="composer-actions">
        {error && <span className="composer-error">{error}</span>}
        {streamDraft?.error && <span className="composer-error">{streamDraft.error}</span>}
        <div className="composer-buttons">
          {isStreaming && (
            <button className="secondary-button" type="button" onClick={onStop}>
              Stop
            </button>
          )}
          <button disabled={disabled || isStreaming} type="submit">
            Send
          </button>
        </div>
      </div>
    </form>
  );
}

function NewSessionPanel({
  customDirectory,
  directories,
  directory,
  draft,
  error,
  message,
  model,
  modelOptions,
  onClose,
  onCustomDirectoryChange,
  onDirectoryChange,
  onMessageChange,
  onModelChange,
  onStop,
  onSubmit,
}: {
  customDirectory: string;
  directories: DirectorySummary[];
  directory: string;
  draft: StreamDraft | null;
  error: string;
  message: string;
  model: string;
  modelOptions: string[];
  onClose: () => void;
  onCustomDirectoryChange: (value: string) => void;
  onDirectoryChange: (value: string) => void;
  onMessageChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onStop: () => void;
  onSubmit: () => void;
}) {
  const active = isStreamActive(draft);

  return (
    <section className="new-session-panel" aria-label="New session">
      <div className="panel-heading">
        <h3>New Session</h3>
        <button disabled={active} type="button" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="new-session-form">
        <label className="filter-field">
          <span>Directory</span>
          <select
            disabled={active}
            value={directory}
            onChange={(event) => onDirectoryChange(event.target.value)}
          >
            {directories.map((item) => (
              <option key={item.path} value={item.path}>
                {item.name}
              </option>
            ))}
            <option value="__custom__">Custom path</option>
          </select>
        </label>
        {directory === "__custom__" && (
          <input
            disabled={active}
            placeholder="Working directory path"
            value={customDirectory}
            onChange={(event) => onCustomDirectoryChange(event.target.value)}
          />
        )}
        <label className="filter-field">
          <span>Model</span>
          <select disabled={active} value={model} onChange={(event) => onModelChange(event.target.value)}>
            <option value="">Default model</option>
            {modelOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <textarea
          disabled={active}
          placeholder="Start a new session"
          rows={4}
          value={message}
          onChange={(event) => onMessageChange(event.target.value)}
        />
        <div className="composer-actions">
          {error && <span className="composer-error">{error}</span>}
          {draft?.error && <span className="composer-error">{draft.error}</span>}
          <div className="composer-buttons">
            {active && (
              <button className="secondary-button" type="button" onClick={onStop}>
                Stop
              </button>
            )}
            <button disabled={active} type="button" onClick={onSubmit}>
              Start
            </button>
          </div>
        </div>
      </div>
      {draft && (
        <div className="new-session-preview">
          <MessageCard index={0} message={draft.userMessage} />
          <StreamingMessageCard draft={draft} />
        </div>
      )}
    </section>
  );
}

function StreamingMessageCard({ draft }: { draft: StreamDraft }) {
  return (
    <article className={`message-card assistant streaming ${draft.status}`}>
      <div className="message-avatar" aria-hidden="true">
        As
      </div>
      <div className="message-content">
        <div className="message-header">
          <strong>Assistant</strong>
          <span>{draft.statusLabel}</span>
        </div>
        <div className="message-parts">
          {draft.tools.length > 0 && (
            <div className="stream-tools">
              {draft.tools.map((tool, index) => (
                <span className="tool-chip" key={`${tool}-${index}`}>
                  {tool}
                </span>
              ))}
            </div>
          )}
          {draft.thinkingText && (
            <details className="part-block reasoning-part" open>
              <summary>Reasoning</summary>
              <div className="part-text">{draft.thinkingText}</div>
            </details>
          )}
          {draft.assistantText ? (
            <MarkdownContent source={draft.assistantText} />
          ) : (
            <div className="message-text muted">
              {draft.status === "error"
                ? draft.error || "Stream failed"
                : draft.status === "stopped"
                  ? "Generation stopped."
                  : "Waiting for output..."}
            </div>
          )}
        </div>
      </div>
    </article>
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
    return (
      <ToolCard
        description={stringValue(part.description)}
        hidden={Boolean(part.is_hidden)}
        input={stringValue(part.input)}
        output={stringValue(part.output)}
        durationMs={partDurationMs(part)}
        status={stringValue(part.status)}
        tool={stringValue(part.tool)}
        variant="call"
      />
    );
  }

  if (part.type === "tool_result") {
    return (
      <ToolCard
        hidden={Boolean(part.is_hidden)}
        durationMs={partDurationMs(part)}
        output={stringifyValue(part.content)}
        status={stringValue(part.status)}
        tool={stringValue(part.tool_name)}
        variant="result"
      />
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

function ToolCard({
  description = "",
  durationMs,
  hidden,
  input = "",
  output = "",
  status,
  tool,
  variant,
}: {
  description?: string;
  durationMs?: number;
  hidden: boolean;
  input?: string;
  output?: string;
  status: string;
  tool: string;
  variant: "call" | "result";
}) {
  const name = tool || (variant === "call" ? "tool" : "tool result");
  const kind = toolKind(name);
  const hasBody = Boolean(description || input || output || hidden);
  const statusMeta = toolStatusMeta(status, hidden, variant);
  const durationLabel = durationMs === undefined ? "" : formatDurationMs(durationMs);

  return (
    <details className={`tool-card ${kind.className}`} open={variant === "call"}>
      <summary>
        <span className="tool-card-title">
          <strong>{name}</strong>
          <span>{kind.label}</span>
        </span>
        <span className={`state-pill tool-status ${statusMeta.tone}`}>
          <span className="tool-status-icon" aria-hidden="true" />
          <span>{statusMeta.label}</span>
          {durationLabel && <span className="tool-duration">{durationLabel}</span>}
        </span>
      </summary>
      {hasBody ? (
        <div className="tool-card-body">
          {description && <div className="tool-description">{description}</div>}
          {input && <ToolSection label="Input" tool={name} value={input} />}
          {hidden ? (
            <div className="tool-hidden-output">Output is hidden or truncated.</div>
          ) : (
            output && (
              <ToolSection
                label={variant === "call" ? "Output" : "Result"}
                tool={name}
                value={output}
              />
            )
          )}
        </div>
      ) : (
        <div className="tool-card-body muted">No tool details.</div>
      )}
    </details>
  );
}

function ToolSection({ label, tool, value }: { label: string; tool: string; value: string }) {
  const language = inferToolLanguage(tool, label, value);

  return (
    <section className="tool-section">
      <div>{label}</div>
      <HighlightedCodeBlock language={language} value={value} />
    </section>
  );
}

function MarkdownContent({ source }: { source: string }) {
  if (!source.trim()) return <div className="message-text muted">(empty)</div>;

  return (
    <div className="markdown-content">
      <ReactMarkdown
        components={{
          code({ children, className, ...props }) {
            const value = String(children ?? "");
            const language = languageFromClassName(className);
            const inline = !className;

            if (inline) {
              return (
                <code {...props} className="inline-code">
                  {children}
                </code>
              );
            }

            return <HighlightedCodeBlock language={language} value={value.replace(/\n$/, "")} />;
          },
        }}
        remarkPlugins={[remarkGfm]}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}

function HighlightedCodeBlock({ language, value }: { language: string; value: string }) {
  const highlighted = highlightCode(value, language);

  return (
    <pre className={`part-code syntax-code language-${highlighted.language}`}>
      {highlighted.html ? (
        <code
          className={`language-${highlighted.language}`}
          dangerouslySetInnerHTML={{ __html: highlighted.html }}
        />
      ) : (
        <code>{value}</code>
      )}
    </pre>
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

function deriveComposerModelOptions(modelOptions: string[], currentModel: string) {
  const normalizedCurrent = normalizeModelValue(currentModel);
  const options = new Set(modelOptions.map(normalizeModelValue).filter(Boolean));
  if (normalizedCurrent) options.add(normalizedCurrent);
  return Array.from(options).sort((a, b) => a.localeCompare(b));
}

function languageFromClassName(className: string | undefined) {
  const match = /language-([\w-]+)/.exec(className || "");
  return normalizeLanguage(match?.[1] || "");
}

function normalizeLanguage(language: string) {
  const value = language.toLowerCase();
  if (value === "js") return "javascript";
  if (value === "ts") return "typescript";
  if (value === "tsx") return "tsx";
  if (value === "jsx") return "jsx";
  if (value === "sh" || value === "shell" || value === "zsh") return "bash";
  if (value === "html" || value === "xml" || value === "svg") return value;
  if (value === "json" || value === "jsonc") return "json";
  if (value === "diff" || value === "patch") return "diff";
  if (value === "css") return "css";
  return value || "text";
}

function inferToolLanguage(tool: string, label: string, value: string) {
  const trimmed = value.trim();
  const normalizedTool = tool.toLowerCase();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) return "json";
  if (normalizedTool.includes("bash")) return "bash";
  if (normalizedTool.includes("edit") || label.toLowerCase() === "result") return "diff";
  return "text";
}

function highlightCode(value: string, language: string) {
  const normalized = normalizeLanguage(language);
  const grammar = Prism.languages[normalized];
  if (!grammar) return { html: "", language: "text" };

  try {
    return { html: Prism.highlight(value, grammar, normalized), language: normalized };
  } catch (_) {
    return { html: "", language: "text" };
  }
}

function toolKind(tool: string) {
  const normalized = tool.toLowerCase();
  if (normalized.includes("bash")) return { className: "tool-bash", label: "Command" };
  if (normalized.includes("read")) return { className: "tool-read", label: "Read" };
  if (normalized.includes("write")) return { className: "tool-write", label: "Write" };
  if (normalized.includes("edit")) return { className: "tool-edit", label: "Edit" };
  if (normalized.includes("glob")) return { className: "tool-glob", label: "Search" };
  return { className: "tool-generic", label: "Tool" };
}

function toolStatusMeta(status: string, hidden: boolean, variant: "call" | "result") {
  if (hidden) return { label: "Hidden", tone: "hidden" };

  const normalized = status.trim().toLowerCase();
  if (["running", "pending", "queued", "started", "in_progress", "in-progress"].includes(normalized)) {
    return { label: "Running", tone: "running" };
  }
  if (["success", "succeeded", "complete", "completed", "done", "ok"].includes(normalized)) {
    return { label: "Success", tone: "success" };
  }
  if (["error", "errored", "failed", "failure", "timeout", "cancelled", "canceled"].includes(normalized)) {
    return { label: titleCaseStatus(normalized), tone: "error" };
  }
  if (normalized) return { label: titleCaseStatus(normalized), tone: "neutral" };

  return variant === "result"
    ? { label: "Result", tone: "success" }
    : { label: "Tool call", tone: "neutral" };
}

function titleCaseStatus(status: string) {
  return status
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function partDurationMs(part: MessagePart) {
  const timedPart = part as {
    duration_ms?: unknown;
    time_created_raw?: unknown;
    time_updated_raw?: unknown;
  };
  const explicit = numberValue(timedPart.duration_ms);
  if (explicit !== undefined) return explicit;

  const created = numberValue(timedPart.time_created_raw);
  const updated = numberValue(timedPart.time_updated_raw);
  if (created === undefined || updated === undefined || updated < created) return undefined;
  return updated - created;
}

function formatDurationMs(durationMs: number) {
  const normalized = Math.max(0, Math.round(durationMs));
  if (normalized < 1000) return `${normalized} ms`;
  if (normalized < 60_000) {
    const seconds = normalized / 1000;
    return `${seconds < 10 ? seconds.toFixed(1) : seconds.toFixed(0)} s`;
  }

  const minutes = Math.floor(normalized / 60_000);
  const seconds = Math.round((normalized % 60_000) / 1000);
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

function formatCompareTime(ms: number) {
  if (!ms) return "";
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

function applyStreamEvent(
  setDraft: React.Dispatch<React.SetStateAction<StreamDraft | null>>,
  sessionId: string,
  type: string,
  data: string,
) {
  setDraft((current) => {
    if (!current || current.sessionId !== sessionId) return current;

    if (type === "thinking") {
      return {
        ...current,
        status: "streaming",
        statusLabel: "Thinking",
        thinkingText: appendStreamText(current.thinkingText, data),
      };
    }
    if (type === "text") {
      return {
        ...current,
        status: "streaming",
        statusLabel: "Streaming",
        assistantText: appendStreamText(current.assistantText, data),
      };
    }
    if (type === "tool_use") {
      return {
        ...current,
        status: "streaming",
        statusLabel: "Using tool",
        tools: [...current.tools, toolLabel(data)],
      };
    }
    if (type === "tool_result") {
      return { ...current, status: "streaming", statusLabel: "Processing tool result" };
    }
    if (type === "status") {
      return {
        ...current,
        statusLabel: data === "waiting" ? "Waiting for model" : "Thinking",
      };
    }
    return current;
  });
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

function normalizeModelValue(model: string | undefined) {
  const normalized = (model || "").trim();
  return normalized && normalized.toUpperCase() !== "N/A" ? normalized : "";
}

function appendStreamText(current: string, incoming: string) {
  return current + incoming.replace(/\\n/g, "\n");
}

function toolLabel(data: string) {
  try {
    const parsed = JSON.parse(data) as { tool?: unknown; input?: unknown };
    const tool = stringValue(parsed.tool) || "tool";
    const input = stringValue(parsed.input);
    return input ? `${tool}: ${input.slice(0, 80)}` : tool;
  } catch (_) {
    return data || "tool";
  }
}

function streamErrorText(data: string) {
  try {
    const parsed = JSON.parse(data) as { error?: unknown; message?: unknown };
    return stringValue(parsed.message || parsed.error || data);
  } catch (_) {
    return data || "Stream failed";
  }
}

function parseSseBlock(block: string) {
  let type = "";
  const data: string[] = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) type = line.slice(7);
    if (line.startsWith("data: ")) data.push(line.slice(6));
  }

  return { type, data: data.join("\n") };
}

function parseDonePayload(data: string): { session_id?: string } {
  try {
    return JSON.parse(data || "{}") as { session_id?: string };
  } catch (_) {
    return {};
  }
}

async function responseErrorText(response: Response) {
  try {
    const payload = (await response.json()) as { error?: unknown };
    return stringValue(payload.error) || response.statusText;
  } catch (_) {
    return response.statusText;
  }
}

function isStreamActive(draft: StreamDraft | null) {
  return draft?.status === "connecting" || draft?.status === "streaming";
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

function maxCount(values: number[]) {
  return Math.max(1, ...values);
}

function percentage(value: number, maxValue: number) {
  if (maxValue <= 0) return 0;
  return Math.max(4, Math.min(100, Math.round((value / maxValue) * 100)));
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

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
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
