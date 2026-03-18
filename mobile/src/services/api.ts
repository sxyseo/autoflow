/**
 * API Service Layer
 *
 * REST client for communicating with the Autoflow backend API.
 * Provides type-safe methods for all mobile endpoints.
 *
 * Base URL: /api/v1/mobile
 */

import type {
  AgentStatusResponse,
  ApiConfig,
  ApiError,
  ApiErrorResponse,
  ApprovalRequest,
  ApprovalResponse,
  DeviceTokenRegistrationRequest,
  DeviceTokenRegistrationResponse,
  RequestConfig,
  TaskApprovalRequest,
  TaskApprovalResponse,
  TasksStatusQuery,
  TasksStatusResponse,
} from './types';

const DEFAULT_TIMEOUT = 30000; // 30 seconds

/**
 * Get the base API URL from environment or use default
 */
const getBaseURL = (): string => {
  // In development, use localhost
  // In production, this should be configured via environment variables
  if (__DEV__) {
    return 'http://localhost:8000';
  }
  return 'https://api.autoflow.dev'; // Production URL
};

/**
 * Default API configuration
 */
const defaultConfig: ApiConfig = {
  baseURL: getBaseURL(),
  timeout: DEFAULT_TIMEOUT,
};

/**
 * API Client class
 */
class ApiClient {
  private config: ApiConfig;
  private authToken: string | null = null;

  constructor(config: Partial<ApiConfig> = {}) {
    this.config = { ...defaultConfig, ...config };
  }

  /**
   * Set authentication token
   */
  public setAuthToken(token: string): void {
    this.authToken = token;
  }

  /**
   * Clear authentication token
   */
  public clearAuthToken(): void {
    this.authToken = null;
  }

  /**
   * Get default headers
   */
  private getDefaultHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    };

    if (this.authToken) {
      headers.Authorization = `Bearer ${this.authToken}`;
    }

    return { ...headers, ...this.config.headers };
  }

  /**
   * Build query string from parameters
   */
  private buildQueryString(params?: Record<string, string | number | boolean | undefined>): string {
    if (!params || Object.keys(params).length === 0) {
      return '';
    }

    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });

    return `?${searchParams.toString()}`;
  }

  /**
   * Create an AbortController with timeout
   */
  private createTimeoutController(): AbortController {
    const controller = new AbortController();
    setTimeout(() => controller.abort(), this.config.timeout);
    return controller;
  }

  /**
   * Handle API errors
   */
  private async handleError(response: Response): Promise<never> {
    let errorData: ApiErrorResponse = { detail: response.statusText };

    try {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        errorData = await response.json();
      }
    } catch {
      // Use default error data if JSON parsing fails
    }

    throw new ApiError(
      errorData.detail,
      response.status,
      errorData.code,
      errorData.validation_errors
    );
  }

  /**
   * Make an HTTP request
   */
  private async request<T>(config: RequestConfig): Promise<T> {
    const { method, path, params, body, headers } = config;
    const queryString = this.buildQueryString(params);
    const url = `${this.config.baseURL}/api/v1/mobile${path}${queryString}`;

    const controller = this.createTimeoutController();

    try {
      const response = await fetch(url, {
        method,
        headers: { ...this.getDefaultHeaders(), ...headers },
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      if (!response.ok) {
        return this.handleError(response);
      }

      // Handle 204 No Content
      if (response.status === 204) {
        return undefined as T;
      }

      const data = await response.json();
      return data;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }

      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new ApiError('Request timeout', 408, 'TIMEOUT');
        }
        throw new ApiError(error.message, 0, 'NETWORK_ERROR');
      }

      throw new ApiError('Unknown error occurred', 0, 'UNKNOWN_ERROR');
    }
  }

  /**
   * Make a GET request
   */
  private get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
    return this.request<T>({ method: 'GET', path, params });
  }

  /**
   * Make a POST request
   */
  private post<T>(path: string, body?: unknown, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
    return this.request<T>({ method: 'POST', path, body, params });
  }

  /**
   * Make a PUT request
   */
  private put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>({ method: 'PUT', path, body });
  }

  /**
   * Make a DELETE request
   */
  private delete<T>(path: string): Promise<T> {
    return this.request<T>({ method: 'DELETE', path });
  }

  // ==========================================================================
  // Task Status API
  // ==========================================================================

  /**
   * Get task status with optional filtering and pagination
   * GET /api/v1/mobile/tasks/status
   */
  async getTasksStatus(query?: TasksStatusQuery): Promise<TasksStatusResponse> {
    const params = {
      status: query?.status,
      agent: query?.agent,
      priority: query?.priority,
      limit: query?.limit,
      offset: query?.offset,
    };
    return this.get<TasksStatusResponse>('/tasks/status', params);
  }

  // ==========================================================================
  // Agent Status API
  // ==========================================================================

  /**
   * Get agent status information
   * GET /api/v1/mobile/agents/status
   */
  async getAgentsStatus(): Promise<AgentStatusResponse> {
    return this.get<AgentStatusResponse>('/agents/status');
  }

  // ==========================================================================
  // Approval API
  // ==========================================================================

  /**
   * Approve a run output
   * POST /api/v1/mobile/runs/{run_id}/approve
   */
  async approveRun(runId: string, request: ApprovalRequest): Promise<ApprovalResponse> {
    return this.post<ApprovalResponse>(`/runs/${runId}/approve`, request);
  }

  /**
   * Approve a task
   * POST /api/v1/mobile/tasks/{task_id}/approve
   */
  async approveTask(taskId: string, request: TaskApprovalRequest): Promise<TaskApprovalResponse> {
    return this.post<TaskApprovalResponse>(`/tasks/${taskId}/approve`, request);
  }

  /**
   * Reject a task
   * POST /api/v1/mobile/tasks/{task_id}/reject
   */
  async rejectTask(taskId: string, request: TaskApprovalRequest): Promise<TaskApprovalResponse> {
    return this.post<TaskApprovalResponse>(`/tasks/${taskId}/reject`, request);
  }

  // ==========================================================================
  // Device Registration API
  // ==========================================================================

  /**
   * Register a device token for push notifications
   * POST /api/v1/mobile/auth/register-device
   */
  async registerDevice(
    request: DeviceTokenRegistrationRequest
  ): Promise<DeviceTokenRegistrationResponse> {
    return this.post<DeviceTokenRegistrationResponse>('/auth/register-device', request);
  }

  // ==========================================================================
  // Health Check
  // ==========================================================================

  /**
   * Health check endpoint
   * GET /api/v1/health
   */
  async healthCheck(): Promise<{ status: string }> {
    const url = `${this.config.baseURL}/api/v1/health`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new ApiError('Health check failed', response.status);
    }
    return response.json();
  }
}

// ==========================================================================
// Singleton Instance
// ==========================================================================

/**
 * Global API client instance
 */
export const api = new ApiClient();

/**
 * Configure the API client
 */
export const configureApi = (config: Partial<ApiConfig>): void => {
  const client = new ApiClient(config);
  // Copy methods to global instance
  Object.assign(api, client);
};

/**
 * Export types
 */
export type { ApiConfig, ApiError, RequestConfig };
