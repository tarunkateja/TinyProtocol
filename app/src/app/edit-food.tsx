import { useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useState } from 'react';
import { Alert, Linking, Pressable, ScrollView, Switch, Text, View } from 'react-native';

import { api } from '../lib/api';
import { useFoods } from '../lib/hooks';
import { colors, fonts, spacing } from '../lib/theme';
import type { FoodCategory, UnitBasis } from '../lib/types';
import { Button, Card, Chip, Field, Muted, Stepper } from '../components/ui';

const CATEGORIES: [FoodCategory, string][] = [
  ['breast_milk', 'Breast milk'],
  ['formula', 'Formula'],
  ['metabolic_formula', 'Metabolic'],
  ['other', 'Other'],
];

export default function EditFood() {
  const router = useRouter();
  const qc = useQueryClient();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const { foods } = useFoods();
  const food = id ? foods.find((f) => f.id === id) : undefined;
  const creating = !id;

  const [name, setName] = useState(food?.name ?? '');
  const [category, setCategory] = useState<FoodCategory>(food?.category ?? 'formula');
  const [unitBasis, setUnitBasis] = useState<UnitBasis>(food?.unit_basis ?? 'per_100ml');
  const [protein, setProtein] = useState(food?.natural_protein_g_per_unit ?? 0);
  const [lysine, setLysine] = useState(food?.lysine_mg_per_unit ?? 0);
  const [sourceName, setSourceName] = useState(food?.source_name ?? '');
  const [verified, setVerified] = useState(food ? !food.needs_dietitian_verification : false);
  const [busy, setBusy] = useState(false);

  if (id && !food) return null;
  const unit = unitBasis === 'per_100ml' ? 'per 100 ml' : 'per scoop';

  const save = async () => {
    setBusy(true);
    try {
      if (creating) {
        await api.createFood({
          name: name.trim(),
          category,
          unit_basis: unitBasis,
          natural_protein_g_per_unit: protein,
          lysine_mg_per_unit: lysine,
          source_name: sourceName.trim() || undefined,
          needs_dietitian_verification: !verified,
        });
      } else {
        await api.updateFood(food!.id, {
          name: name.trim(),
          natural_protein_g_per_unit: protein,
          lysine_mg_per_unit: lysine,
          source_name: sourceName.trim() || undefined,
          needs_dietitian_verification: !verified,
        });
      }
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
      {food?.description ? (
        <Muted style={{ marginBottom: spacing.md }}>{food.description}</Muted>
      ) : null}
      {food?.source_url ? (
        <Pressable onPress={() => Linking.openURL(food.source_url!)}>
          <Text style={styles_link}>🔗 Source: {food.source_name ?? food.source_url}</Text>
        </Pressable>
      ) : null}

      <Field label="Name" value={name} onChangeText={setName} />

      {creating && (
        <>
          <Text style={styles_label}>Category</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
            {CATEGORIES.map(([c, label]) => (
              <Chip key={c} label={label} selected={category === c} onPress={() => setCategory(c)} />
            ))}
          </View>
          <Text style={[styles_label, { marginTop: spacing.sm }]}>Measured</Text>
          <View style={{ flexDirection: 'row' }}>
            <Chip
              label="per 100 ml (liquid)"
              selected={unitBasis === 'per_100ml'}
              onPress={() => setUnitBasis('per_100ml')}
            />
            <Chip
              label="per scoop (powder)"
              selected={unitBasis === 'per_scoop'}
              onPress={() => setUnitBasis('per_scoop')}
            />
          </View>
        </>
      )}

      <Card style={{ marginTop: spacing.sm }}>
        <Text style={styles_label}>Natural protein (g {unit})</Text>
        <Stepper value={protein} onChange={setProtein} step={0.1} suffix="g" />
        <Text style={[styles_label, { marginTop: spacing.md }]}>Lysine (mg {unit})</Text>
        <Stepper value={lysine} onChange={setLysine} step={5} suffix="mg" />
        <View style={{ marginTop: spacing.md }}>
          <Field
            label="Where are these values from? (label, USDA…)"
            value={sourceName}
            onChangeText={setSourceName}
            placeholder="e.g. Similac 360 label, USDA FDC"
          />
        </View>
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <Text style={{ color: colors.text, fontFamily: fonts.bold }}>
            Verified with our dietitian
          </Text>
          <Switch value={verified} onValueChange={setVerified} />
        </View>
      </Card>
      <Button
        title={creating ? 'Add food' : 'Save'}
        onPress={save}
        loading={busy}
        disabled={!name.trim()}
      />
    </ScrollView>
  );
}

const styles_label = {
  fontSize: 13,
  fontFamily: fonts.semibold,
  color: colors.muted,
  marginBottom: 6,
};

const styles_link = {
  color: colors.primary,
  fontFamily: fonts.semibold,
  fontSize: 14,
  marginBottom: spacing.md,
};
