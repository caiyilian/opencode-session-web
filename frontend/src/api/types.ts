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
      status?: string;
      is_hidden?: boolean;
      time_created_raw?: number;
      time_updated_raw?: number;
      duration_ms?: number;
    }
  | {
      type: "tool_result";
      tool_name: string;
      content?: string;
      status?: string;
      is_hidden?: boolean;
      time_created_raw?: number;
      time_updated_raw?: number;
      duration_ms?: number;
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

export interface CompareMessage {
  id: string;
  role: string;
  parts: unknown[];
  content: string;
  time: number;
}

export interface CompareSession {
  id: string;
  title: string;
  model: string;
  directory: string;
  project: string;
  messages: CompareMessage[];
  message_count: number;
  cost: number;
  tokens_input: number;
  tokens_output: number;
}

export interface CompareResponse {
  session1: CompareSession;
  session2: CompareSession;
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

export interface ProjectModelSummary {
  model: string;
  count: number;
}

export interface ProjectRecentSession {
  id: string;
  title: string;
  model: string;
  time_updated: string;
  time_updated_raw: number;
}

export interface ProjectWorkspace {
  path: string;
  name: string;
  session_count: number;
  message_count: number;
  first_active_raw: number;
  last_active_raw: number;
  last_active: string;
  cost: number;
  tokens_input: number;
  tokens_output: number;
  top_models: ProjectModelSummary[];
  recent_sessions: ProjectRecentSession[];
}

export interface WorkspaceProjectsResponse {
  projects: ProjectWorkspace[];
  total: number;
}

export type WorkspaceTaskStatus = "todo" | "in_progress" | "done" | "blocked" | "archived";

export interface WorkspaceTask {
  id: string;
  title: string;
  description: string;
  project_path: string;
  status: WorkspaceTaskStatus;
  linked_session_ids: string[];
  created_at: number;
  updated_at: number;
}

export interface WorkspaceTasksResponse {
  tasks: WorkspaceTask[];
  statuses: WorkspaceTaskStatus[];
  total: number;
}

export interface WorkspaceTaskResponse {
  task: WorkspaceTask;
}

export interface WorkspaceTaskEvent {
  id: string;
  task_id: string;
  event_type: string;
  title: string;
  payload: Record<string, unknown>;
  created_at: number;
}

export interface WorkspaceTaskEventsResponse {
  events: WorkspaceTaskEvent[];
  total: number;
}

export interface WorkspaceTaskReportSession {
  id: string;
  title: string;
  directory: string;
  model: string;
  time_updated: string;
  time_updated_raw: number;
}

export interface GitFileStatus {
  path: string;
  status: string;
}

export interface GitCommitSummary {
  sha: string;
  subject: string;
}

export interface WorkspaceGitSnapshot {
  project_path: string;
  is_git_repo: boolean;
  repo_root: string;
  branch: string;
  dirty_count: number;
  files: GitFileStatus[];
  recent_commits: GitCommitSummary[];
  error: string;
}

export interface WorkspaceGitResponse {
  git: WorkspaceGitSnapshot;
}

export interface WorkspaceCommand {
  key: string;
  label: string;
  argv: string[];
  cwd: string;
  description: string;
}

export interface WorkspaceCommandsResponse {
  commands: WorkspaceCommand[];
}

export type WorkspaceCommandRunStatus = "success" | "failed" | "timeout";

export interface WorkspaceCommandRun {
  id: string;
  project_path: string;
  task_id: string;
  command_key: string;
  command_label: string;
  command_argv: string[];
  cwd: string;
  status: WorkspaceCommandRunStatus;
  exit_code: number | null;
  duration_ms: number;
  output: string;
  started_at: number;
  finished_at: number;
  created_at: number;
}

export interface WorkspaceCommandRunsResponse {
  runs: WorkspaceCommandRun[];
  total: number;
}

export interface WorkspaceCommandRunResponse {
  run: WorkspaceCommandRun;
}

export interface WorkspaceTaskReport {
  task: WorkspaceTask;
  linked_sessions: WorkspaceTaskReportSession[];
  command_runs: WorkspaceCommandRun[];
  events: WorkspaceTaskEvent[];
  git: WorkspaceGitSnapshot | null;
  markdown: string;
}

export interface WorkspaceTaskReportResponse {
  report: WorkspaceTaskReport;
}

export interface WorkspaceTaskDetail {
  task: WorkspaceTask;
  linked_sessions: WorkspaceTaskReportSession[];
  command_runs: WorkspaceCommandRun[];
  events: WorkspaceTaskEvent[];
  git: WorkspaceGitSnapshot | null;
}

export interface WorkspaceTaskDetailResponse {
  detail: WorkspaceTaskDetail;
}
