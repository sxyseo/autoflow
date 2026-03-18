import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
  Alert,
} from 'react-native';
import { Colors, Spacing, Typography } from '@/constants/theme';

interface Setting {
  id: string;
  title: string;
  description?: string;
  type: 'toggle' | 'navigation' | 'action';
  value?: boolean;
  onPress?: () => void;
}

export const SettingsScreen: React.FC = () => {
  const [notificationsEnabled, setNotificationsEnabled] = React.useState(true);
  const [biometricAuthEnabled, setBiometricAuthEnabled] = React.useState(true);
  const [apiUrl, setApiUrl] = React.useState('https://api.autoflow.dev');

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout? You will need to authenticate again.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Logout',
          style: 'destructive',
          onPress: () => {
            // TODO: Implement logout logic
            console.log('Logging out...');
          },
        },
      ]
    );
  };

  const handleClearCache = () => {
    Alert.alert(
      'Clear Cache',
      'This will clear all cached data. You will need to sync again.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          style: 'destructive',
          onPress: () => {
            // TODO: Implement cache clearing logic
            console.log('Clearing cache...');
          },
        },
      ]
    );
  };

  const sections: Array<{ title: string; items: Setting[] }> = [
    {
      title: 'Notifications',
      items: [
        {
          id: 'push-notifications',
          title: 'Push Notifications',
          description: 'Receive notifications for task updates',
          type: 'toggle',
          value: notificationsEnabled,
          onPress: () => setNotificationsEnabled(!notificationsEnabled),
        },
        {
          id: 'notify-completion',
          title: 'Task Completion',
          description: 'Notify when tasks complete',
          type: 'toggle',
          value: true,
          onPress: () => console.log('Toggle task completion notifications'),
        },
        {
          id: 'notify-errors',
          title: 'Errors & Failures',
          description: 'Notify when tasks fail or need attention',
          type: 'toggle',
          value: true,
          onPress: () => console.log('Toggle error notifications'),
        },
      ],
    },
    {
      title: 'Security',
      items: [
        {
          id: 'biometric-auth',
          title: 'Biometric Authentication',
          description: 'Require Face ID / fingerprint to open app',
          type: 'toggle',
          value: biometricAuthEnabled,
          onPress: () => setBiometricAuthEnabled(!biometricAuthEnabled),
        },
      ],
    },
    {
      title: 'API Configuration',
      items: [
        {
          id: 'api-url',
          title: 'API Server',
          description: apiUrl,
          type: 'navigation',
          onPress: () => console.log('Configure API URL'),
        },
      ],
    },
    {
      title: 'About',
      items: [
        {
          id: 'version',
          title: 'Version',
          description: '1.0.0',
          type: 'navigation',
          onPress: () => console.log('View version info'),
        },
        {
          id: 'docs',
          title: 'Documentation',
          type: 'navigation',
          onPress: () => console.log('Open documentation'),
        },
      ],
    },
    {
      title: 'Data',
      items: [
        {
          id: 'clear-cache',
          title: 'Clear Cache',
          description: 'Remove all cached data',
          type: 'action',
          onPress: handleClearCache,
        },
      ],
    },
  ];

  const renderSettingItem = (item: Setting) => {
    if (item.type === 'toggle') {
      return (
        <View style={styles.settingItem}>
          <View style={styles.settingInfo}>
            <Text style={styles.settingTitle}>{item.title}</Text>
            {item.description && (
              <Text style={styles.settingDescription}>{item.description}</Text>
            )}
          </View>
          <Switch
            value={item.value}
            onValueChange={item.onPress}
            trackColor={{ false: Colors.border, true: Colors.primary }}
            thumbColor="#fff"
          />
        </View>
      );
    }

    const isDestructive = item.id === 'clear-cache';

    return (
      <TouchableOpacity style={styles.settingItem} onPress={item.onPress}>
        <View style={styles.settingInfo}>
          <Text
            style={[
              styles.settingTitle,
              isDestructive && styles.destructiveText,
            ]}
          >
            {item.title}
          </Text>
          {item.description && (
            <Text style={styles.settingDescription}>{item.description}</Text>
          )}
        </View>
        <Text style={styles.chevron}>›</Text>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.contentContainer}>
        <Text style={styles.title}>Settings</Text>

        {sections.map((section, sectionIndex) => (
          <View key={section.title} style={styles.section}>
            <Text style={styles.sectionTitle}>{section.title}</Text>
            <View style={styles.sectionCard}>
              {section.items.map((item, itemIndex) => (
                <View
                  key={item.id}
                  style={[
                    styles.itemContainer,
                    itemIndex < section.items.length - 1 && styles.itemBorder,
                  ]}
                >
                  {renderSettingItem(item)}
                </View>
              ))}
            </View>
          </View>
        ))}

        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Text style={styles.logoutButtonText}>Logout</Text>
        </TouchableOpacity>
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
    marginBottom: Spacing.lg,
  },
  section: {
    marginBottom: Spacing.lg,
  },
  sectionTitle: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: Spacing.sm,
    marginLeft: Spacing.sm,
  },
  sectionCard: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  itemContainer: {
    padding: Spacing.md,
  },
  itemBorder: {
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  settingItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  settingInfo: {
    flex: 1,
    marginRight: Spacing.md,
  },
  settingTitle: {
    ...Typography.body,
    fontWeight: '500',
    marginBottom: 2,
  },
  settingDescription: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  chevron: {
    ...Typography.body,
    color: Colors.textSecondary,
    fontSize: 20,
  },
  destructiveText: {
    color: Colors.danger,
  },
  logoutButton: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: Spacing.md,
    alignItems: 'center',
    marginTop: Spacing.md,
    marginBottom: Spacing.xl,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 2,
  },
  logoutButtonText: {
    ...Typography.body,
    color: Colors.danger,
    fontWeight: '600',
  },
});
