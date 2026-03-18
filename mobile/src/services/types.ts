/**
 * API Service Types
 *
 * TypeScript types for the Autoflow mobile API client.
 * These types mirror the backend API models in autoflow/api/routes/mobile.py
 */

// ============================================================================
// Base Types
// ============================================================================

export type TaskStatus = 'todo' | 'in_progress' | 'in_review' | 'done' | 'needs_changes' | 'blocked';
export type AgentStatus = 'active' | 'inactive';
export type Priority = 'low' | 'medium' | 'high' | 'critical';
export type Platform = 'ios' | 'android';

// ============================================================================
// Task Status API
// ============================================================================

export interface TaskSummary {
  id: string;
  title: string;
  status: TaskStatus;
  agent: string | null;
  priority: Priority;
  created_at: string;
  updated_at: string;
  spec_id: string;
}

export interface PaginationMeta {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface TasksStatusResponse {
  tasks: TaskSummary[];
  meta: PaginationMeta;
}

export interface TasksStatusQuery {
  status?: TaskStatus;
  agent?: string;
  priority?: Priority;
  limit?: number;
  offset?: number;
}

// ============================================================================
// Agent Status API
// ============================================================================

export interface AgentInfo {
  name: string;
  status: AgentStatus;
  current_task: string | null;
  capabilities: string[];
}

export interface AgentStatusResponse {
  agents: AgentInfo[];
  total_active: number;
  total_inactive: number;
}

// ============================================================================
// Approval API
// ============================================================================

export interface ApprovalRequest {
  user_id: string;
  comment?: string;
}

export interface ApprovalResponse {
  run_id: string;
  approved: boolean;
  processed_at: string;
}

export interface TaskApprovalRequest {
  user_id: string;
  comment?: string;
}

export interface TaskApprovalResponse {
  task_id: string;
  approved: boolean;
  processed_at: string;
}

// ============================================================================
// Device Registration API
// ============================================================================

export interface DeviceTokenRegistrationRequest {
  device_token: string;
  platform: Platform;
}

export interface DeviceTokenRegistrationResponse {
  device_token: string;
  platform: Platform;
  registered_at: string;
  status: string;
}

// ============================================================================
// Error Types
// ============================================================================

export class ApiError extends Error {
  constructor(
    public message: string,
    public status: number,
    public code?: string,
    public details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface ValidationError {
  field: string;
  message: string;
}

export interface ApiErrorResponse {
  detail: string;
  code?: string;
  validation_errors?: ValidationError[];
}

// ============================================================================
// Configuration
// ============================================================================

export interface ApiConfig {
  baseURL: string;
  timeout: number;
  headers?: Record<string, string>;
}

export interface RequestConfig {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  path: string;
  params?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  headers?: Record<string, string>;
}
