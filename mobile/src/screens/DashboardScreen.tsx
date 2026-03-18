import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Colors, Spacing, Typography } from '@/constants/theme';

interface AgentStatus {
  id: string;
  name: string;
  status: 'active' | 'idle' | 'error';
  currentTask?: string;
}

interface TaskSummary {
  id: string;
  title: string;
  status: 'running' | 'completed' | 'failed' | 'pending';
  progress: number;
}

export const DashboardScreen: React.FC = () => {
  const [refreshing, setRefreshing] = React.useState(false);
  const [agentStatuses, setAgentStatuses] = React.useState<AgentStatus[]>([]);
  const [recentTasks, setRecentTasks] = React.useState<TaskSummary[]>([]);

  const loadDashboardData = React.useCallback(async () => {
    // TODO: Implement API call to fetch dashboard data
    setAgentStatuses([]);
    setRecentTasks([]);
  }, []);

  useFocusEffect(
    React.useCallback(() => {
      loadDashboardData();
    }, [loadDashboardData])
  );

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true);
    await loadDashboardData();
    setRefreshing(false);
  }, [loadDashboardData]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
      case 'running':
        return Colors.primary;
      case 'completed':
        return Colors.success;
      case 'error':
      case 'failed':
        return Colors.danger;
      case 'idle':
      case 'pending':
        return Colors.textSecondary;
      default:
        return Colors.textSecondary;
    }
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      <Text style={styles.title}>Dashboard</Text>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Active Agents</Text>
        {agentStatuses.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyStateText}>No active agents</Text>
          </View>
        ) : (
          agentStatuses.map((agent) => (
            <View key={agent.id} style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.cardTitle}>{agent.name}</Text>
                <View
                  style={[
                    styles.statusBadge,
                    { backgroundColor: getStatusColor(agent.status) },
                  ]}
                >
                  <Text style={styles.statusText}>{agent.status}</Text>
                </View>
              </View>
              {agent.currentTask && (
                <Text style={styles.cardSubtext}>{agent.currentTask}</Text>
              )}
            </View>
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
            <View key={task.id} style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.cardTitle}>{task.title}</Text>
                <View
                  style={[
                    styles.statusBadge,
                    { backgroundColor: getStatusColor(task.status) },
                  ]}
                >
                  <Text style={styles.statusText}>{task.status}</Text>
                </View>
              </View>
              <View style={styles.progressBarContainer}>
                <View
                  style={[
                    styles.progressBar,
                    { width: `${task.progress}%` },
                  ]}
                />
              </View>
            </View>
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
  card: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.xs,
  },
  cardTitle: {
    ...Typography.body,
    fontWeight: '600',
    flex: 1,
  },
  cardSubtext: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  statusBadge: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    borderRadius: 12,
  },
  statusText: {
    ...Typography.caption,
    color: '#fff',
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  progressBarContainer: {
    height: 4,
    backgroundColor: Colors.background,
    borderRadius: 2,
    marginTop: Spacing.sm,
  },
  progressBar: {
    height: '100%',
    backgroundColor: Colors.primary,
    borderRadius: 2,
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
});
