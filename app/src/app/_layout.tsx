import {
  Nunito_400Regular,
  Nunito_600SemiBold,
  Nunito_700Bold,
  Nunito_800ExtraBold,
  useFonts,
} from '@expo-google-fonts/nunito';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import * as Notifications from 'expo-notifications';
import React, { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';

import { AuthProvider, useAuth } from '../lib/auth';
import { colors, fonts } from '../lib/theme';

SplashScreen.preventAutoHideAsync();

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 15_000 } },
});

function RootNavigator() {
  const { token, ready } = useAuth();
  const [fontsLoaded] = useFonts({
    Nunito_400Regular,
    Nunito_600SemiBold,
    Nunito_700Bold,
    Nunito_800ExtraBold,
  });

  useEffect(() => {
    if (ready && fontsLoaded) SplashScreen.hideAsync();
  }, [ready, fontsLoaded]);

  if (!ready || !fontsLoaded) return null;

  return (
    <Stack
      screenOptions={{
        headerTintColor: colors.text,
        headerStyle: { backgroundColor: colors.bg },
        headerTitleStyle: { fontFamily: fonts.heavy, fontSize: 18 },
        contentStyle: { backgroundColor: colors.bg },
      }}
    >
      <Stack.Protected guard={!!token}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="log-feed"
          options={{ presentation: 'modal', title: 'Log feed' }}
        />
        <Stack.Screen
          name="log-event"
          options={{ presentation: 'modal', title: 'Log event' }}
        />
        <Stack.Screen
          name="edit-food"
          options={{ presentation: 'modal', title: 'Food' }}
        />
        <Stack.Screen
          name="reminders"
          options={{ presentation: 'modal', title: 'Reminders' }}
        />
      </Stack.Protected>
      <Stack.Protected guard={!token}>
        <Stack.Screen name="(auth)/login" options={{ headerShown: false }} />
        <Stack.Screen name="(auth)/register" options={{ title: 'Create account' }} />
        <Stack.Screen name="(auth)/join" options={{ title: 'Join your family' }} />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <StatusBar style="dark" />
        <RootNavigator />
      </AuthProvider>
    </QueryClientProvider>
  );
}
