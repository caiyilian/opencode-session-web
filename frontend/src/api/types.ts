export interface ApiErrorPayload {
  error: string;
}

export interface StatsDirectory {
  path: string;
  count: number;
}

export interface StatsModel {
  model: string;
  count: number;
}

export interface RecentSession {
  id: string;
  title: string;
  directory: string;
  time_updated: string;
}

export interface StatsResponse {
  total_sessions: number;
  total_projects: number;
  total_cost: number;
  total_tokens_input: number;
  total_tokens_output: number;
  top_directories: StatsDirectory[];
  top_models: StatsModel[];
  recent_sessions: RecentSession[];
}

export interface DirectorySummary {
  path: string;
  name: string;
  session_count: number;
  last_active: string;
  recently_active: boolean;
}

export interface DirectoriesResponse {
  directories: DirectorySummary[];
}

export interface SessionSummary {
  id: string;
  title: string;
  directory: string;
  project: string;
  model: string;
  agent: string;
  time_created: string;
  time_updated: string;
  time_updated_raw: number;
  cost: number;
  tokens_input: number;
  tokens_output: number;
  message_count: number;
}

export interface SessionsResponse {
  sessions: SessionSummary[];
  total: number;
}

export interface SessionDetail {
  id: string;
  title: string;
  directory: string;
  project: string;
  model: string;
  agent: string;
  time_created: number;
  time_updated: number;
  time_created_fmt: string;
  time_updated_fmt: string;
  cost: number;
  tokens_input: number;
  tokens_output: number;
}

export interface MessageTokens {
  input?: number;
  output?: number;
}

export type MessagePart =
  | { type: "text"; text: string }
  | { type: "reasoning"; text: string }
  | {
      type: "tool";
      tool: string;
      input?: string;
      description?: string;
      output?: string;
      is_hidden?: boolean;
    }
  | {
      type: "tool_result";
      tool_name: string;
      content?: string;
      status?: string;
      is_hidden?: boolean;
    }
  | {
      type: "step-finish";
      tokens?: Record<string, number>;
      cost?: number;
      reason?: string;
    }
  | { type: string; [key: string]: unknown };

export interface SessionMessage {
  id: string;
  role: "user" | "assistant" | "tool" | string;
  parts: MessagePart[];
  time_created: string;
  time_created_raw: number;
  tokens: MessageTokens;
}

export interface SessionDetailResponse {
  session: SessionDetail;
  messages: SessionMessage[];
  message_count: number;
}

export interface AvailableModelsResponse {
  models: string[];
}

export interface UsedModelSummary {
  name: string;
  count: number;
}

export interface UsedModelsResponse {
  models: UsedModelSummary[];
}

export interface MutationResponse {
  status?: string;
  message?: string;
}
