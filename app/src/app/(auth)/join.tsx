import React, { useState } from 'react';
import { ScrollView } from 'react-native';

import { api } from '../../lib/api';
import { useAuth } from '../../lib/auth';
import { colors, spacing } from '../../lib/theme';
import { Button, Field, Muted } from '../../components/ui';
import { showAlert } from '../../lib/dialogs';

export default function Join() {
  const { signIn } = useAuth();
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const resp = await api.join({
        email: email.trim(),
        password,
        name: name.trim(),
        invite_code: code.trim().toUpperCase(),
      });
      await signIn(resp.access_token);
    } catch (e: any) {
      showAlert('Could not join', e.message);
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
      <Muted style={{ marginBottom: spacing.lg }}>
        Ask your partner to create an invite code in Settings → Invite partner.
      </Muted>
      <Field
        label="Invite code"
        autoCapitalize="characters"
        autoCorrect={false}
        value={code}
        onChangeText={setCode}
      />
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
      <Button
        title="Join family"
        onPress={submit}
        loading={busy}
        disabled={!code.trim() || !name.trim() || !email.trim() || password.length < 8}
      />
    </ScrollView>
  );
}
