import React, { useState } from 'react';
import { Alert, ScrollView } from 'react-native';

import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { spacing, colors } from '../../lib/theme';
import { Button, Field, Muted, SectionTitle } from '../../components/ui';

export default function Register() {
  const { signIn } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [babyName, setBabyName] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York';
      const resp = await api.register({
        email: email.trim(),
        password,
        name: name.trim(),
        timezone,
        baby: babyName.trim() ? { name: babyName.trim(), conditions: [] } : undefined,
      });
      await signIn(resp.access_token);
    } catch (e: any) {
      Alert.alert('Could not create account', e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.xl }}
      keyboardShouldPersistTaps="handled"
    >
      <SectionTitle>About you</SectionTitle>
      <Field label="Your name" value={name} onChangeText={setName} />
      <Field
        label="Email"
        autoCapitalize="none"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <Field
        label="Password (8+ characters)"
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />
      <SectionTitle>Your baby</SectionTitle>
      <Field label="Baby's name" value={babyName} onChangeText={setBabyName} />
      <Muted style={{ marginBottom: spacing.lg }}>
        You can set targets, conditions, and invite your partner in Settings afterwards.
      </Muted>
      <Button
        title="Create family"
        onPress={submit}
        loading={busy}
        disabled={!name.trim() || !email.trim() || password.length < 8}
      />
    </ScrollView>
  );
}
