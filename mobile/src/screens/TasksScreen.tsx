import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Colors, Spacing, Typography } from '@/constants/theme';

interface Task {
  id: string;
  title: string;
  description: string;
  status: 'running' | 'completed' | 'failed' | 'pending' | 'attention_needed';
  progress: number;
  createdAt: string;
  updatedAt: string;
}

export const TasksScreen: React.FC = () => {
  const [refreshing, setRefreshing] = React.useState(false);
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [filter, setFilter] = React.useState<
    'all' | 'running' | 'completed' | 'failed' | 'pending'
  >('all');

  const loadTasks = React.useCallback(async () => {
    // TODO: Implement API call to fetch tasks
    setTasks([]);
  }, []);

  useFocusEffect(
    React.useCallback(() => {
      loadTasks();
    }, [loadTasks])
  );

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true);
    await loadTasks();
    setRefreshing(false);
  }, [loadTasks]);

  const filteredTasks = React.useMemo(() => {
    if (filter === 'all') return tasks;
    return tasks.filter((task) => task.status === filter);
  }, [tasks, filter]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return Colors.primary;
      case 'completed':
        return Colors.success;
      case 'failed':
      case 'attention_needed':
        return Colors.danger;
      case 'pending':
        return Colors.textSecondary;
      default:
        return Colors.textSecondary;
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  const renderFilterButton = (
    label: string,
    value: 'all' | 'running' | 'completed' | 'failed' | 'pending'
  ) => (
    <TouchableOpacity
      style={[styles.filterButton, filter === value && styles.filterButtonActive]}
      onPress={() => setFilter(value)}
    >
      <Text
        style={[
          styles.filterButtonText,
          filter === value && styles.filterButtonTextActive,
        ]}
      >
        {label}
      </Text>
    </TouchableOpacity>
  );

  const handleTaskPress = (task: Task) => {
    // TODO: Navigate to task detail screen
    console.log('Task pressed:', task.id);
  };

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.contentContainer}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
      >
        <Text style={styles.title}>Tasks</Text>

        <View style={styles.filterContainer}>
          {renderFilterButton('All', 'all')}
          {renderFilterButton('Running', 'running')}
          {renderFilterButton('Done', 'completed')}
          {renderFilterButton('Failed', 'failed')}
        </View>

        {filteredTasks.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyStateText}>No tasks found</Text>
          </View>
        ) : (
          filteredTasks.map((task) => (
            <TouchableOpacity
              key={task.id}
              style={styles.taskCard}
              onPress={() => handleTaskPress(task)}
            >
              <View style={styles.taskHeader}>
                <View style={styles.taskTitleContainer}>
                  <Text style={styles.taskTitle}>{task.title}</Text>
                  <View
                    style={[
                      styles.statusBadge,
                      { backgroundColor: getStatusColor(task.status) },
                    ]}
                  >
                    <Text style={styles.statusText}>
                      {task.status.replace('_', ' ')}
                    </Text>
                  </View>
                </View>
              </View>

              {task.description ? (
                <Text style={styles.taskDescription} numberOfLines={2}>
                  {task.description}
                </Text>
              ) : null}

              <View style={styles.taskFooter}>
                <View style={styles.progressBarContainer}>
                  <View
                    style={[
                      styles.progressBar,
                      { width: `${task.progress}%` },
                    ]}
                  />
                </View>
                <Text style={styles.taskTime}>{formatDate(task.updatedAt)}</Text>
              </View>
            </TouchableOpacity>
          ))
        )}
      </ScrollView>
    </View>
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
    marginBottom: Spacing.md,
  },
  filterContainer: {
    flexDirection: 'row',
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  filterButton: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: 20,
    backgroundColor: Colors.card,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  filterButtonActive: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  filterButtonText: {
    ...Typography.caption,
    color: Colors.text,
    fontWeight: '600',
  },
  filterButtonTextActive: {
    color: '#fff',
  },
  taskCard: {
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
  taskHeader: {
    marginBottom: Spacing.sm,
  },
  taskTitleContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  taskTitle: {
    ...Typography.body,
    fontWeight: '600',
    flex: 1,
    marginRight: Spacing.sm,
  },
  taskDescription: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginBottom: Spacing.md,
  },
  taskFooter: {
    gap: Spacing.sm,
  },
  progressBarContainer: {
    height: 4,
    backgroundColor: Colors.background,
    borderRadius: 2,
  },
  progressBar: {
    height: '100%',
    backgroundColor: Colors.primary,
    borderRadius: 2,
  },
  taskTime: {
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
  emptyState: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: Spacing.xl,
    alignItems: 'center',
    marginTop: Spacing.lg,
  },
  emptyStateText: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
});
