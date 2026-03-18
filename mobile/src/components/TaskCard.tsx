import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Colors, Spacing, Typography } from '@/constants/theme';

export interface TaskCardProps {
  id: string;
  title: string;
  status: 'running' | 'completed' | 'failed' | 'pending';
  progress: number;
  updatedAt?: string;
  onPress?: (taskId: string) => void;
}

export const TaskCard: React.FC<TaskCardProps> = ({
  id,
  title,
  status,
  progress,
  updatedAt,
  onPress,
}) => {
  const getStatusColor = (taskStatus: string) => {
    switch (taskStatus) {
      case 'running':
        return Colors.primary;
      case 'completed':
        return Colors.success;
      case 'failed':
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

  const CardWrapper = onPress ? TouchableOpacity : View;
  const wrapperProps = onPress ? { onPress: () => onPress(id) } : {};

  return (
    <CardWrapper style={styles.card} {...wrapperProps}>
      <View style={styles.cardHeader}>
        <Text style={styles.cardTitle}>{title}</Text>
        <View
          style={[
            styles.statusBadge,
            { backgroundColor: getStatusColor(status) },
          ]}
        >
          <Text style={styles.statusText}>{status}</Text>
        </View>
      </View>
      <View style={styles.cardFooter}>
        <View style={styles.progressBarContainer}>
          <View
            style={[styles.progressBar, { width: `${Math.min(100, Math.max(0, progress))}%` }]}
          />
        </View>
        {updatedAt && (
          <Text style={styles.timeText}>{formatDate(updatedAt)}</Text>
        )}
      </View>
    </CardWrapper>
  );
};

const styles = StyleSheet.create({
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
    marginBottom: Spacing.sm,
  },
  cardTitle: {
    ...Typography.body,
    fontWeight: '600',
    flex: 1,
    marginRight: Spacing.sm,
  },
  cardFooter: {
    gap: Spacing.sm,
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
  },
  progressBar: {
    height: '100%',
    backgroundColor: Colors.primary,
    borderRadius: 2,
  },
  timeText: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
});
