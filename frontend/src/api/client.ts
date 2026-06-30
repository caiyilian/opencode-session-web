import type {
  AvailableModelsResponse,
  CompareResponse,
  DirectoriesResponse,
  MutationResponse,
  SessionDetailResponse,
  SessionsResponse,
  StatsResponse,
  UsedModelsResponse,
  WorkspaceProjectsResponse,
  WorkspaceTaskResponse,
  WorkspaceTasksResponse,
  WorkspaceTaskStatus,
  WorkspaceGitResponse,
  WorkspaceCommandRunResponse,
  WorkspaceCommandRunsResponse,
  WorkspaceCommandsResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly payload: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface SessionsQuery {
  q?: string;
  dir?: string;
  model?: string;
  limit?: number;
  offset?: number;
}

export interface SessionStreamQuery {
  message: string;
  model?: string;
}

export interface NewSessionStreamRequest {
  directory: string;
  message: string;
  model?: string;
}

export interface ForkSessionStreamRequest {
  message: string;
  model?: string;
}

export interface WorkspaceTasksQuery {
  project_path?: string;
  status?: WorkspaceTaskStatus;
}

export interface CreateWorkspaceTaskRequest {
  title: string;
  description?: string;
  project_path?: string;
  status?: WorkspaceTaskStatus;
  linked_session_ids?: string[];
}

export interface UpdateWorkspaceTaskRequest {
  title?: string;
  description?: string;
  project_path?: string;
  status?: WorkspaceTaskStatus;
  linked_session_ids?: string[];
}

export interface WorkspaceCommandRunsQuery {
  project_path?: string;
  task_id?: string;
  limit?: number;
}

export interface RunWorkspaceCommandRequest {
  project_path: string;
  command_key: string;
  task_id?: string;
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  const payload = await readJson(response);

  if (!response.ok) {
    throw new ApiError(errorMessage(payload) || response.statusText, response.status, payload);
  }

  return payload as T;
}

export function getStats() {
  return apiRequest<StatsResponse>("/api/stats");
}

export function getDirectories() {
  return apiRequest<DirectoriesResponse>("/api/directories");
}

export function getSessions(query: SessionsQuery = {}) {
  return apiRequest<SessionsResponse>(`/api/sessions${queryString(query)}`);
}

export function getSession(sessionId: string) {
  return apiRequest<SessionDetailResponse>(`/api/sessions/${encodeURIComponent(sessionId)}`);
}

export function compareSessions(id1: string, id2: string) {
  const params = new URLSearchParams({ id1, id2 });
  return apiRequest<CompareResponse>(`/api/sessions/compare?${params.toString()}`);
}

export function getSessionStreamUrl(sessionId: string, query: SessionStreamQuery) {
  return `/api/sessions/${encodeURIComponent(sessionId)}/stream${queryString(query)}`;
}

export function createNewSessionStream(payload: NewSessionStreamRequest, signal?: AbortSignal) {
  return fetch("/api/sessions/new", {
    method: "POST",
    headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
}

export function createForkSessionStream(
  sessionId: string,
  payload: ForkSessionStreamRequest,
  signal?: AbortSignal,
) {
  return fetch(`/api/sessions/${encodeURIComponent(sessionId)}/fork`, {
    method: "POST",
    headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
}

export function getAvailableModels() {
  return apiRequest<AvailableModelsResponse>("/api/available-models");
}

export function getUsedModels() {
  return apiRequest<UsedModelsResponse>("/api/models");
}

export function getWorkspaceProjects(limit = 50) {
  return apiRequest<WorkspaceProjectsResponse>(`/api/workspace/projects${queryString({ limit })}`);
}

export function getWorkspaceTasks(query: WorkspaceTasksQuery = {}) {
  return apiRequest<WorkspaceTasksResponse>(`/api/workspace/tasks${queryString(query)}`);
}

export function createWorkspaceTask(payload: CreateWorkspaceTaskRequest) {
  return apiRequest<WorkspaceTaskResponse>("/api/workspace/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateWorkspaceTask(taskId: string, payload: UpdateWorkspaceTaskRequest) {
  return apiRequest<WorkspaceTaskResponse>(`/api/workspace/tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function getWorkspaceGit(projectPath: string) {
  return apiRequest<WorkspaceGitResponse>(
    `/api/workspace/git${queryString({ project_path: projectPath })}`,
  );
}

export function getWorkspaceCommands() {
  return apiRequest<WorkspaceCommandsResponse>("/api/workspace/commands");
}

export function getWorkspaceCommandRuns(query: WorkspaceCommandRunsQuery = {}) {
  return apiRequest<WorkspaceCommandRunsResponse>(
    `/api/workspace/command-runs${queryString(query)}`,
  );
}

export function runWorkspaceCommand(payload: RunWorkspaceCommandRequest) {
  return apiRequest<WorkspaceCommandRunResponse>("/api/workspace/command-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteSession(sessionId: string) {
  return apiRequest<MutationResponse>(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export function undoSession(sessionId: string) {
  return apiRequest<MutationResponse>(`/api/sessions/${encodeURIComponent(sessionId)}/undo`, {
    method: "POST",
  });
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch (_) {
    return null;
  }
}

function errorMessage(payload: unknown): string {
  if (payload && typeof payload === "object" && "error" in payload) {
    return String((payload as { error: unknown }).error || "");
  }
  return "";
}

function queryString(
  query: SessionsQuery | WorkspaceTasksQuery | WorkspaceCommandRunsQuery | { project_path: string },
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}
