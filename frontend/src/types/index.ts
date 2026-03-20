/**
 * Type definitions for Autoflow Web UI
 */

// Task Status Types
export type TaskStatus = 'todo' | 'in_progress' | 'in_review' | 'done' | 'needs_changes' | 'blocked';

// Run Status Types
export type RunStatus = 'started' | 'running' | 'completed' | 'failed' | 'blocked' | 'needs_changes';

// Task Priority
export type TaskPriority = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10;

// Task Interface
export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  created_at: string;
  updated_at: string;
  assigned_agent?: string;
  labels: string[];
  dependencies: string[];
  metadata: Record<string, any>;
}

// Run Interface
export interface Run {
  id: string;
  task_id?: string;
  agent: string;
  status: RunStatus;
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
  workdir: string;
  command?: string;
  exit_code?: number;
  output?: string;
  error?: string;
  metadata: Record<string, any>;
}

// System Status Interface
export interface SystemStatus {
  status: 'healthy' | 'unhealthy' | 'degraded';
  version: string;
  state_dir: string;
  initialized: boolean;
  tasks_total: number;
  tasks_by_status: Record<TaskStatus, number>;
  runs_total: number;
  runs_by_status: Record<RunStatus, number>;
  specs_total: number;
  memory_total: number;
}

// WebSocket Message Types
export type WSMessageType = 'connection' | 'task' | 'run' | 'status' | 'error' | 'pong';

export interface WSMessage {
  type: WSMessageType;
  action?: 'created' | 'updated' | 'deleted';
  data?: any;
  status?: string;
  message?: string;
  path?: string;
  timestamp?: string;
}

// API Response Types
export interface APIResponse<T> {
  data?: T;
  error?: string;
  message?: string;
}

export interface TaskListResponse {
  tasks: Task[];
  total: number;
  filtered: boolean;
}

export interface RunListResponse {
  runs: Run[];
  total: number;
  filtered: boolean;
}

// Filter and Search Types
export interface TaskFilters {
  status?: TaskStatus[];
  priority?: TaskPriority[];
  assigned_agent?: string[];
  labels?: string[];
  search?: string;
}

export interface RunFilters {
  status?: RunStatus[];
  agent?: string[];
  task_id?: string;
  search?: string;
}
