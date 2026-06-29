import type {
  AvailableModelsResponse,
  DirectoriesResponse,
  MutationResponse,
  SessionDetailResponse,
  SessionsResponse,
  StatsResponse,
  UsedModelsResponse,
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

export function getAvailableModels() {
  return apiRequest<AvailableModelsResponse>("/api/available-models");
}

export function getUsedModels() {
  return apiRequest<UsedModelsResponse>("/api/models");
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

function queryString(query: SessionsQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}
