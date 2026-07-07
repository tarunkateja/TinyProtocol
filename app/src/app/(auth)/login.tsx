import { Link } from 'expo-router';
import React, { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, StyleSheet, Text, View } from 'react-native';

import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { colors, spacing } from '../../lib/theme';
import { Button, Field, Muted } from '../../components/ui';

export default function Login() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const resp = await api.login({ email: email.trim(), password });
      await signIn(resp.access_token);
    } catch (e: any) {
      Alert.alert('Sign in failed', e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.container}
    >
      <Text style={styles.logo}>🍼 TinyProtocol</Text>
      <Muted style={{ textAlign: 'center', marginBottom: spacing.xl }}>
        Feed & care tracking, built for your baby
      </Muted>
      <Field
        label="Email"
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <Field
        label="Password"
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />
      <Button title="Sign in" onPress={submit} loading={busy} disabled={!email || !password} />
      <View style={styles.links}>
        <Link href="/(auth)/register" style={styles.link}>
          Create a family
        </Link>
        <Link href="/(auth)/join" style={styles.link}>
          Join with invite code
        </Link>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: spacing.xl, backgroundColor: colors.bg },
  logo: { fontSize: 32, fontWeight: '800', textAlign: 'center', color: colors.text, marginBottom: spacing.sm },
  links: { marginTop: spacing.xl, gap: spacing.md, alignItems: 'center' },
  link: { color: colors.primary, fontWeight: '600', fontSize: 15 },
});
