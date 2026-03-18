import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Colors, Spacing, Typography } from '@/constants/theme';
import { api } from '@/services/api';
import type { AgentInfo, TaskSummary as ApiTaskSummary } from '@/services/types';
import { TaskCard } from '@/components/TaskCard';
import { AgentStatusCard } from '@/components/AgentStatusCard';

const POLLING_INTERVAL = 5000; // 5 seconds

interface TaskSummary {
  id: string;
  title: string;
  status: 'running' | 'completed' | 'failed' | 'pending';
  progress: number;
  updatedAt?: string;
}

export const DashboardScreen: React.FC = () => {
  const [refreshing, setRefreshing] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [agentStatuses, setAgentStatuses] = React.useState<AgentInfo[]>([]);
  const [recentTasks, setRecentTasks] = React.useState<TaskSummary[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  // Convert API task summary to display format
  const convertTaskSummary = (apiTask: ApiTaskSummary): TaskSummary => {
    let status: TaskSummary['status'] = 'pending';
    switch (apiTask.status) {
      case 'in_progress':
        status = 'running';
        break;
      case 'done':
        status = 'completed';
        break;
      case 'blocked':
      case 'needs_changes':
        status = 'failed';
        break;
      default:
        status = 'pending';
    }

    return {
      id: apiTask.id,
      title: apiTask.title,
      status,
      progress: status === 'completed' ? 100 : status === 'running' ? 50 : 0,
      updatedAt: apiTask.updated_at,
    };
  };

  const loadDashboardData = React.useCallback(async () => {
    try {
      setError(null);
      const [agentsResponse, tasksResponse] = await Promise.all([
        api.getAgentsStatus(),
        api.getTasksStatus({ limit: 10 }),
      ]);

      setAgentStatuses(agentsResponse.agents);
      setRecentTasks(tasksResponse.tasks.map(convertTaskSummary));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load dashboard data';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Set up polling when screen is focused
  useFocusEffect(
    React.useCallback(() => {
      loadDashboardData();

      const intervalId = setInterval(() => {
        loadDashboardData();
      }, POLLING_INTERVAL);

      return () => {
        clearInterval(intervalId);
      };
    }, [loadDashboardData])
  );

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true);
    await loadDashboardData();
    setRefreshing(false);
  }, [loadDashboardData]);

  const handleTaskPress = (taskId: string) => {
    // TODO: Navigate to task detail screen
  };

  if (loading && agentStatuses.length === 0 && recentTasks.length === 0) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={Colors.primary} />
        <Text style={styles.loadingText}>Loading dashboard...</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      <Text style={styles.title}>Dashboard</Text>

      {error && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Active Agents</Text>
        {agentStatuses.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyStateText}>No active agents</Text>
          </View>
        ) : (
          agentStatuses.map((agent) => (
            <AgentStatusCard
              key={agent.name}
              id={agent.name}
              name={agent.name}
              status={agent.status === 'active' ? 'active' : 'idle'}
              currentTask={agent.current_task || undefined}
              capabilities={agent.capabilities}
            />
          ))
        )}
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Recent Tasks</Text>
        {recentTasks.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyStateText}>No recent tasks</Text>
          </View>
        ) : (
          recentTasks.map((task) => (
            <TaskCard
              key={task.id}
              {...task}
              onPress={handleTaskPress}
            />
          ))
        )}
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  contentContainer: {
    padding: Spacing.md,
  },
  title: {
    ...Typography.title,
    marginBottom: Spacing.lg,
  },
  section: {
    marginBottom: Spacing.lg,
  },
  sectionTitle: {
    ...Typography.heading,
    marginBottom: Spacing.md,
  },
  emptyState: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: Spacing.xl,
    alignItems: 'center',
  },
  emptyStateText: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  loadingContainer: {
    flex: 1,
    backgroundColor: Colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    gap: Spacing.md,
  },
  loadingText: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  errorContainer: {
    backgroundColor: '#FFE5E5',
    borderRadius: 12,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    borderLeftWidth: 4,
    borderLeftColor: Colors.danger,
  },
  errorText: {
    ...Typography.caption,
    color: Colors.danger,
  },
});
