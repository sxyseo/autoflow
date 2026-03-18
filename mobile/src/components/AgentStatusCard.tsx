import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, Spacing, Typography } from '@/constants/theme';

export interface AgentStatusCardProps {
  id: string;
  name: string;
  status: 'active' | 'idle' | 'error';
  currentTask?: string;
  capabilities?: string[];
}

export const AgentStatusCard: React.FC<AgentStatusCardProps> = ({
  id,
  name,
  status,
  currentTask,
  capabilities,
}) => {
  const getStatusColor = (agentStatus: string) => {
    switch (agentStatus) {
      case 'active':
        return Colors.success;
      case 'idle':
        return Colors.textSecondary;
      case 'error':
        return Colors.danger;
      default:
        return Colors.textSecondary;
    }
  };

  const getStatusLabel = (agentStatus: string) => {
    switch (agentStatus) {
      case 'active':
        return 'Active';
      case 'idle':
        return 'Idle';
      case 'error':
        return 'Error';
      default:
        return 'Unknown';
    }
  };

  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.cardTitle}>{name}</Text>
        <View
          style={[
            styles.statusBadge,
            { backgroundColor: getStatusColor(status) },
          ]}
        >
          <Text style={styles.statusText}>{getStatusLabel(status)}</Text>
        </View>
      </View>
      {currentTask ? (
        <Text style={styles.currentTaskText} numberOfLines={1}>
          {currentTask}
        </Text>
      ) : (
        <Text style={styles.currentTaskText}>No active task</Text>
      )}
      {capabilities && capabilities.length > 0 && (
        <View style={styles.capabilitiesContainer}>
          {capabilities.slice(0, 3).map((capability, index) => (
            <View key={`${id}-${capability}-${index}`} style={styles.capabilityBadge}>
              <Text style={styles.capabilityText}>{capability}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
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
    marginBottom: Spacing.xs,
  },
  cardTitle: {
    ...Typography.body,
    fontWeight: '600',
    flex: 1,
    marginRight: Spacing.sm,
  },
  currentTaskText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginBottom: Spacing.sm,
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
  },
  capabilitiesContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.xs,
    marginTop: Spacing.xs,
  },
  capabilityBadge: {
    backgroundColor: Colors.background,
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
    borderRadius: 8,
  },
  capabilityText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    fontSize: 12,
  },
});
