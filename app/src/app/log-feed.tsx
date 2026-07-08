import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import { fmtNum } from '../lib/format';
import { useBaby, useFoods, useInvalidateLogs } from '../lib/hooks';
import { colors, eventTheme, fonts, radius, spacing } from '../lib/theme';
import type { Feed, FeedComponentIn, FeedPreset, Food } from '../lib/types';
import { Button, Card, Chip, Field, Muted, SectionTitle, Stepper } from '../components/ui';
import { SessionTimer } from '../components/SessionTimer';
import { TimePickerRow } from '../components/TimePickerRow';

type Mode = 'bottle' | 'latch';

export default function LogFeed() {
  const router = useRouter();
  const qc = useQueryClient();
  const { baby } = useBaby();
  const { foods } = useFoods();
  const invalidate = useInvalidateLogs();
  const presetsQ = useQuery({ queryKey: ['feedPresets'], queryFn: api.listFeedPresets });

  const [mode, setMode] = useState<Mode>('bottle');
  const [when, setWhen] = useState(new Date());
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);

  const [liquidMl, setLiquidMl] = useState<Record<string, number>>({});
  const [powderScoops, setPowderScoops] = useState<Record<string, number>>({});

  const [minutes, setMinutes] = useState(10);
  const [rate, setRate] = useState<number | null>(null);
  const [measuredMl, setMeasuredMl] = useState(0);

  const liquids = foods.filter((f) => f.unit_basis === 'per_100ml');
  const powders = foods.filter((f) => f.unit_basis === 'per_scoop');
  const breastMilkFood = liquids.find((f) => f.category === 'breast_milk');
  const effectiveRate = rate ?? baby?.default_latch_rate_ml_per_10min ?? 20;
  const latchEstimate = measuredMl > 0 ? measuredMl : (minutes * effectiveRate) / 10;

  const components: FeedComponentIn[] = useMemo(() => {
    if (mode === 'latch') {
      if (!breastMilkFood || minutes <= 0) return [];
      return [
        {
          kind: 'latch',
          food_id: breastMilkFood.id,
          minutes,
          rate_ml_per_10min: effectiveRate,
          measured_ml: measuredMl > 0 ? measuredMl : undefined,
        },
      ];
    }
    const out: FeedComponentIn[] = [];
    for (const f of liquids)
      if (liquidMl[f.id] > 0) out.push({ kind: 'liquid', food_id: f.id, volume_ml: liquidMl[f.id] });
    for (const f of powders)
      if (powderScoops[f.id] > 0)
        out.push({ kind: 'powder', food_id: f.id, scoops: powderScoops[f.id] });
    return out;
  }, [mode, liquids, powders, liquidMl, powderScoops, minutes, effectiveRate, measuredMl, breastMilkFood]);

  const preview = useMemo(() => {
    let ml = 0, protein = 0, lysine = 0;
    const byId = new Map(foods.map((f) => [f.id, f]));
    for (const c of components) {
      const f = byId.get(c.food_id);
      if (!f) continue;
      const effMl =
        c.kind === 'liquid' ? c.volume_ml : c.kind === 'powder' ? 0
        : c.measured_ml ?? (c.minutes * c.rate_ml_per_10min) / 10;
      const units = c.kind === 'powder' ? c.scoops : effMl / 100;
      ml += effMl;
      protein += units * f.natural_protein_g_per_unit;
      lysine += units * f.lysine_mg_per_unit;
    }
    return { ml, protein, lysine };
  }, [components, foods]);

  const applyPreset = (preset: FeedPreset) => {
    setMode('bottle');
    const liquid: Record<string, number> = {};
    const powder: Record<string, number> = {};
    for (const c of preset.components) {
      if (c.kind === 'liquid') liquid[c.food_id] = c.volume_ml;
      if (c.kind === 'powder') powder[c.food_id] = c.scoops;
    }
    setLiquidMl(liquid);
    setPowderScoops(powder);
  };

  const savePreset = () => {
    const comps = components.filter((c) => c.kind !== 'latch');
    if (comps.length === 0) return;
    const byId = new Map(foods.map((f) => [f.id, f]));
    const defaultName = comps
      .map((c) =>
        c.kind === 'liquid'
          ? `${fmtNum(c.volume_ml)} ${byId.get(c.food_id)?.name ?? ''}`
          : `${fmtNum(c.scoops)} scoop ${byId.get(c.food_id)?.name ?? ''}`,
      )
      .join(' + ');
    Alert.prompt(
      'Save preset',
      'Name this mix so you can log it in one tap.',
      async (name) => {
        try {
          await api.createFeedPreset({ name: name?.trim() || defaultName, components: comps });
          qc.invalidateQueries({ queryKey: ['feedPresets'] });
        } catch (e: any) {
          Alert.alert('Could not save preset', e.message);
        }
      },
      'plain-text',
      defaultName,
    );
  };

  const deletePreset = (preset: FeedPreset) => {
    Alert.alert(`Delete preset "${preset.name}"?`, undefined, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          await api.deleteFeedPreset(preset.id);
          qc.invalidateQueries({ queryKey: ['feedPresets'] });
        },
      },
    ]);
  };

  const save = async () => {
    if (!baby || components.length === 0) return;
    setBusy(true);
    try {
      await api.createFeed(baby.id, {
        occurred_at: when.toISOString(),
        components,
        notes: notes.trim() || undefined,
      });
      invalidate();
      router.back();
    } catch (e: any) {
      Alert.alert('Could not save feed', e.message);
      setBusy(false);
    }
  };

  const feedColor = eventTheme.feed.color;

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}
      keyboardShouldPersistTaps="handled"
    >
      <View style={{ flexDirection: 'row', marginBottom: spacing.sm }}>
        <Chip label="🍼 Bottle" selected={mode === 'bottle'} onPress={() => setMode('bottle')} color={feedColor} softColor={eventTheme.feed.soft} />
        <Chip label="🤱 Latch" selected={mode === 'latch'} onPress={() => setMode('latch')} color={feedColor} softColor={eventTheme.feed.soft} />
      </View>

      {mode === 'bottle' ? (
        <>
          {(presetsQ.data?.length ?? 0) > 0 && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: spacing.xs }}>
              {presetsQ.data!.map((p) => (
                <Pressable
                  key={p.id}
                  style={styles.presetChip}
                  onPress={() => applyPreset(p)}
                  onLongPress={() => deletePreset(p)}
                >
                  <Text style={styles.presetText}>⚡ {p.name}</Text>
                </Pressable>
              ))}
            </View>
          )}
          <SectionTitle>What's in the bottle?</SectionTitle>
          {liquids.map((f) => (
            <FoodAmountRow
              key={f.id}
              food={f}
              suffix="ml"
              step={10}
              value={liquidMl[f.id] ?? 0}
              onChange={(v) => setLiquidMl((s) => ({ ...s, [f.id]: v }))}
            />
          ))}
          <SectionTitle>Powder mixed in (scoops)</SectionTitle>
          {powders.map((f) => (
            <FoodAmountRow
              key={f.id}
              food={f}
              suffix="scoops"
              step={0.5}
              value={powderScoops[f.id] ?? 0}
              onChange={(v) => setPowderScoops((s) => ({ ...s, [f.id]: v }))}
            />
          ))}
          {components.length > 0 && (
            <Pressable onPress={savePreset}>
              <Text style={styles.saveMix}>💾 Save this mix as a preset</Text>
            </Pressable>
          )}
        </>
      ) : (
        <Card>
          <Text style={styles.fieldLabel}>Timer (or type minutes below)</Text>
          <SessionTimer onMinutes={setMinutes} color={feedColor} />
          <Text style={[styles.fieldLabel, { marginTop: spacing.md }]}>Minutes latched</Text>
          <Stepper value={minutes} onChange={setMinutes} step={5} suffix="min" />
          <Text style={[styles.fieldLabel, { marginTop: spacing.md }]}>
            Est. intake rate (ml per 10 min)
          </Text>
          <Stepper value={effectiveRate} onChange={setRate} step={5} suffix="ml/10min" />
          <Text style={[styles.fieldLabel, { marginTop: spacing.md }]}>
            Weighed amount (optional — overrides the estimate)
          </Text>
          <Stepper value={measuredMl} onChange={setMeasuredMl} step={5} suffix="ml" />
          <Text style={[styles.latchEstimate, { color: feedColor }]}>
            {measuredMl > 0 ? 'Weighed' : 'Estimated'}: {fmtNum(latchEstimate)} ml
          </Text>
        </Card>
      )}

      <TimePickerRow value={when} onChange={setWhen} />
      <Field label="Notes (optional)" value={notes} onChangeText={setNotes} multiline />

      {components.length > 0 && (
        <Muted style={{ marginBottom: spacing.md, textAlign: 'center' }}>
          {fmtNum(preview.ml)} ml · {fmtNum(preview.protein, 2)} g protein · {fmtNum(preview.lysine)} mg lysine
        </Muted>
      )}
      <Button title="Save feed" onPress={save} loading={busy} disabled={components.length === 0} />
    </ScrollView>
  );
}

function FoodAmountRow({
  food,
  value,
  onChange,
  step,
  suffix,
}: {
  food: Food;
  value: number;
  onChange: (v: number) => void;
  step: number;
  suffix: string;
}) {
  const tint =
    food.category === 'breast_milk'
      ? colors.breastMilk
      : food.category === 'metabolic_formula'
        ? colors.metabolic
        : colors.formula;
  return (
    <Card style={{ marginBottom: spacing.sm, paddingVertical: spacing.md }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
        <View style={[styles.dot, { backgroundColor: tint }]} />
        <Text style={styles.foodName}>{food.name}</Text>
        {food.needs_dietitian_verification && <Text style={styles.verify}> ⚠︎</Text>}
      </View>
      <Stepper value={value} onChange={onChange} step={step} suffix={suffix} />
    </Card>
  );
}

const styles = StyleSheet.create({
  fieldLabel: { fontSize: 13, fontFamily: fonts.semibold, color: colors.muted, marginBottom: 6 },
  foodName: { fontSize: 15, fontFamily: fonts.bold, color: colors.text },
  verify: { color: colors.metabolic, fontSize: 13 },
  dot: { width: 10, height: 10, borderRadius: 5, marginRight: 8 },
  latchEstimate: {
    marginTop: spacing.md,
    fontSize: 17,
    fontFamily: fonts.heavy,
    textAlign: 'center',
  },
  presetChip: {
    backgroundColor: eventTheme.feed.soft,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: eventTheme.feed.color,
    paddingHorizontal: 14,
    paddingVertical: 9,
    marginRight: spacing.sm,
    marginBottom: spacing.sm,
  },
  presetText: { color: colors.text, fontFamily: fonts.bold, fontSize: 14 },
  saveMix: {
    color: colors.primary,
    fontFamily: fonts.bold,
    fontSize: 14,
    marginTop: spacing.xs,
    marginBottom: spacing.sm,
  },
});
