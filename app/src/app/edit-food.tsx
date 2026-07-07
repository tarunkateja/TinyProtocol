import { useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useState } from 'react';
import { Alert, ScrollView, Switch, Text, View } from 'react-native';

import { api } from '../lib/api';
import { useFoods } from '../lib/hooks';
import { colors, spacing } from '../lib/theme';
import { Button, Card, Field, Muted, Stepper } from '../components/ui';

export default function EditFood() {
  const router = useRouter();
  const qc = useQueryClient();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { foods } = useFoods();
  const food = foods.find((f) => f.id === id);

  const [name, setName] = useState(food?.name ?? '');
  const [protein, setProtein] = useState(food?.natural_protein_g_per_unit ?? 0);
  const [lysine, setLysine] = useState(food?.lysine_mg_per_unit ?? 0);
  const [verified, setVerified] = useState(food ? !food.needs_dietitian_verification : false);
  const [busy, setBusy] = useState(false);

  if (!food) return null;
  const unit = food.unit_basis === 'per_100ml' ? 'per 100 ml' : 'per scoop';

  const save = async () => {
    setBusy(true);
    try {
      await api.updateFood(food.id, {
        name: name.trim(),
        natural_protein_g_per_unit: protein,
        lysine_mg_per_unit: lysine,
        needs_dietitian_verification: !verified,
      });
      qc.invalidateQueries({ queryKey: ['foods'] });
      router.back();
    } catch (e: any) {
      Alert.alert('Could not save', e.message);
      setBusy(false);
    }
  };

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg }}
      keyboardShouldPersistTaps="handled"
    >
      {food.description ? <Muted style={{ marginBottom: spacing.md }}>{food.description}</Muted> : null}
      <Field label="Name" value={name} onChangeText={setName} />
      <Card>
        <Text style={styles_label}>Natural protein (g {unit})</Text>
        <Stepper value={protein} onChange={setProtein} step={0.1} suffix="g" />
        <Text style={[styles_label, { marginTop: spacing.md }]}>Lysine (mg {unit})</Text>
        <Stepper value={lysine} onChange={setLysine} step={5} suffix="mg" />
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: spacing.lg,
          }}
        >
          <Text style={{ color: colors.text, fontWeight: '600' }}>
            Verified with our dietitian
          </Text>
          <Switch value={verified} onValueChange={setVerified} />
        </View>
      </Card>
      <Button title="Save" onPress={save} loading={busy} disabled={!name.trim()} />
    </ScrollView>
  );
}

const styles_label = {
  fontSize: 13,
  fontWeight: '600' as const,
  color: colors.muted,
  marginBottom: 6,
};
