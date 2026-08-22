import { Ionicons } from '@expo/vector-icons';
import { Tabs, useRouter } from 'expo-router';
import React from 'react';
import { Pressable } from 'react-native';

import { colors } from '../../lib/theme';

/** Five tabs (Apple's 3–5 guidance): the glanceable Home, the Log timeline,
 * Trends, Ask, Care. Settings, day totals and the clinic update are reached
 * from Home / the gear — they are destinations, not places you live. */
// Open on Home, not the Log index (expo-router's default for a group).
export const unstable_settings = { initialRouteName: 'home' };

export default function TabsLayout() {
  const router = useRouter();
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerShadowVisible: false,
        headerTintColor: colors.text,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.muted,
        sceneStyle: { backgroundColor: colors.bg },
        headerRight: () => (
          <Pressable
            onPress={() => router.push('/settings')}
            hitSlop={12}
            style={{ paddingHorizontal: 16, minWidth: 44, minHeight: 44, justifyContent: 'center', alignItems: 'flex-end' }}
          >
            <Ionicons name="settings-outline" color={colors.muted} size={22} />
          </Pressable>
        ),
      }}
    >
      <Tabs.Screen
        name="home"
        options={{
          title: 'Home',
          tabBarIcon: ({ color, size }) => <Ionicons name="pulse" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="index"
        options={{
          title: 'Log',
          tabBarIcon: ({ color, size }) => <Ionicons name="list" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="trends"
        options={{
          title: 'Trends',
          tabBarIcon: ({ color, size }) => <Ionicons name="trending-up" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="ask"
        options={{
          title: 'Ask',
          tabBarIcon: ({ color, size }) => <Ionicons name="sparkles" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="care"
        options={{
          title: 'Care',
          tabBarIcon: ({ color, size }) => <Ionicons name="medkit" color={color} size={size} />,
        }}
      />
    </Tabs>
  );
}
