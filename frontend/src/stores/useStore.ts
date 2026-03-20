/**
 * Global Application State Management
 * Using Zustand for simple, scalable state
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import type { Task, Run, SystemStatus, TaskStatus, RunStatus } from '../types';

interface AppState {
  // Task state
  tasks: Task[];
  selectedTask: Task | null;
  taskFilters: {
    status?: TaskStatus[];
    search?: string;
  };

  // Run state
  runs: Run[];
  selectedRun: Run | null;
  activeRuns: Run[];
  runFilters: {
    status?: RunStatus[];
    search?: string;
  };

  // System state
  systemStatus: SystemStatus | null;
  loading: boolean;
  error: string | null;

  // WebSocket state
  wsConnected: boolean;

  // UI state
  currentView: 'dashboard' | 'tasks' | 'runs' | 'settings';
  sidebarOpen: boolean;

  // Actions
  setTasks: (tasks: Task[]) => void;
  setSelectedTask: (task: Task | null) => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  removeTask: (id: string) => void;
  setTaskFilters: (filters: Partial<AppState['taskFilters']>) => void;

  setRuns: (runs: Run[]) => void;
  setSelectedRun: (run: Run | null) => void;
  addRun: (run: Run) => void;
  updateRun: (id: string, updates: Partial<Run>) => void;
  removeRun: (id: string) => void;
  setRunFilters: (filters: Partial<AppState['runFilters']>) => void;

  setSystemStatus: (status: SystemStatus) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  setWsConnected: (connected: boolean) => void;
  setCurrentView: (view: AppState['currentView']) => void;
  toggleSidebar: () => void;
}

export const useStore = create<AppState>()(
  devtools(
    (set, get) => ({
      // Initial state
      tasks: [],
      selectedTask: null,
      taskFilters: {},

      runs: [],
      selectedRun: null,
      activeRuns: [],
      runFilters: {},

      systemStatus: null,
      loading: false,
      error: null,

      wsConnected: false,

      currentView: 'dashboard',
      sidebarOpen: true,

      // Task actions
      setTasks: (tasks) => set({ tasks }),

      setSelectedTask: (task) => set({ selectedTask: task }),

      addTask: (task) => set((state) => ({
        tasks: [...state.tasks, task],
      })),

      updateTask: (id, updates) => set((state) => ({
        tasks: state.tasks.map(task =>
          task.id === id ? { ...task, ...updates } : task
        ),
        selectedTask: state.selectedTask?.id === id
          ? { ...state.selectedTask, ...updates }
          : state.selectedTask,
      })),

      removeTask: (id) => set((state) => ({
        tasks: state.tasks.filter(task => task.id !== id),
        selectedTask: state.selectedTask?.id === id ? null : state.selectedTask,
      })),

      setTaskFilters: (filters) => set((state) => ({
        taskFilters: { ...state.taskFilters, ...filters },
      })),

      // Run actions
      setRuns: (runs) => set((state) => ({
        runs,
        activeRuns: runs.filter(run =>
          run.status === 'started' || run.status === 'running'
        ),
      })),

      setSelectedRun: (run) => set({ selectedRun: run }),

      addRun: (run) => set((state) => ({
        runs: [...state.runs, run],
        activeRuns: [...state.activeRuns, run].filter(r =>
          r.status === 'started' || r.status === 'running'
        ),
      })),

      updateRun: (id, updates) => set((state) => ({
        runs: state.runs.map(run =>
          run.id === id ? { ...run, ...updates } : run
        ),
        selectedRun: state.selectedRun?.id === id
          ? { ...state.selectedRun, ...updates }
          : state.selectedRun,
        activeRuns: state.activeRuns.map(run =>
          run.id === id ? { ...run, ...updates } : run
        ).filter(r =>
          r.status === 'started' || r.status === 'running'
        ),
      })),

      removeRun: (id) => set((state) => ({
        runs: state.runs.filter(run => run.id !== id),
        activeRuns: state.activeRuns.filter(run => run.id !== id),
        selectedRun: state.selectedRun?.id === id ? null : state.selectedRun,
      })),

      setRunFilters: (filters) => set((state) => ({
        runFilters: { ...state.runFilters, ...filters },
      })),

      // System actions
      setSystemStatus: (status) => set({ systemStatus: status }),

      setLoading: (loading) => set({ loading }),

      setError: (error) => set({ error }),

      // WebSocket actions
      setWsConnected: (connected) => set({ wsConnected: connected }),

      // UI actions
      setCurrentView: (view) => set({ currentView: view }),

      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
    }),
    {
      name: 'autoflow-store',
    }
  )
);
