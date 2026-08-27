import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import { showAlert } from '../lib/dialogs';
import { fmtNum, fmtWeight, localDateString } from '../lib/format';
import { useBaby, useFoods } from '../lib/hooks';
import { colors, fonts, spacing } from '../lib/theme';
import type { VolumeCategory, VolumeTarget } from '../lib/types';
import { Button, Card, DateField, Muted, SectionTitle, Stepper } from '../components/ui';

/**
 * The Plan hub: everything the metabolic team changes, in one place —
 * recipe, goals (targets), foods, Huckleberry mapping — with one history.
 */

type VolumeDraft = Record<VolumeCategory, { min: number; max: number }>;

const EMPTY_VOLUMES: VolumeDraft = {
  breast_milk: { min: 0, max: 0 },
  formula: { min: 0, max: 0 },
  metabolic_formula: { min: 0, max: 0 },
};

const VOLUME_LABELS: [VolumeCategory, string][] = [
  ['breast_milk', '🍼 Breast milk'],
  ['formula', '🥫 Regular formula'],
  ['metabolic_formula', '⚗️ GA1 / metabolic formula'],
];

const CAT_SHORT: Record<string, string> = {
  breast_milk: 'breast milk',
  formula: 'formula',
  metabolic_formula: 'GA1 formula',
};

export function describeTargets(t: {
  lysine_mg_per_day?: number | null;
  natural_protein_g_per_day?: number | null;
  lysine_mg_per_kg?: number | null;
  natural_protein_g_per_kg?: number | null;
  volume_targets?: { category: string; direction: string; ml_per_day: number }[];
}): string {
  const parts: string[] = [];
  for (const vt of t.volume_targets ?? []) {
    parts.push(`${CAT_SHORT[vt.category] ?? vt.category} ${vt.direction} ${fmtNum(vt.ml_per_day)} ml`);
  }
  if (t.lysine_mg_per_kg) parts.push(`lysine ${fmtNum(t.lysine_mg_per_kg)} mg/kg`);
  else if (t.lysine_mg_per_day) parts.push(`lysine ${fmtNum(t.lysine_mg_per_day)} mg`);
  if (t.natural_protein_g_per_kg) parts.push(`protein ${fmtNum(t.natural_protein_g_per_kg)} g/kg`);
  else if (t.natural_protein_g_per_day) parts.push(`protein ${fmtNum(t.natural_protein_g_per_day)} g`);
  return parts.join(' · ') || 'no goals set';
}

export default function Plan() {
  const router = useRouter();
  const qc = useQueryClient();
  const { baby } = useBaby();
  const { foods } = useFoods();
  const recipeQ = useQuery({
    queryKey: ['recipe-current', baby?.id],
    queryFn: () => api.currentRecipe(baby!.id),
    enabled: !!baby,
  });
  const hbQ = useQuery({
    queryKey: ['hb-status', baby?.id],
    queryFn: () => api.hbStatus(baby!.id),
    enabled: !!baby,
  });
  const historyQ = useQuery({
    queryKey: ['target-history', baby?.id],
    queryFn: () => api.targetHistory(baby!.id),
    enabled: !!baby,
  });
  const mcQ = useQuery({
    queryKey: ['mc-status', baby?.id],
    queryFn: () => api.mcStatus(baby!.id),
    enabled: !!baby,
  });

  const [editingGoals, setEditingGoals] = useState(false);
  const [lysineTarget, setLysineTarget] = useState(0);
  const [proteinTarget, setProteinTarget] = useState(0);
  const [lysinePerKg, setLysinePerKg] = useState(0);
  const [proteinPerKg, setProteinPerKg] = useState(0);
  const [latchRate, setLatchRate] = useState(20);
  const [volumes, setVolumes] = useState<VolumeDraft>(EMPTY_VOLUMES);
  const [effectiveFrom, setEffectiveFrom] = useState(localDateString());
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!baby) return;
    setLysineTarget(baby.targets.lysine_mg_per_day ?? 0);
    setProteinTarget(baby.targets.natural_protein_g_per_day ?? 0);
    setLysinePerKg(baby.targets.lysine_mg_per_kg ?? 0);
    setProteinPerKg(baby.targets.natural_protein_g_per_kg ?? 0);
    setLatchRate(baby.default_latch_rate_ml_per_10min);
    const draft: VolumeDraft = JSON.parse(JSON.stringify(EMPTY_VOLUMES));
    for (const vt of baby.targets.volume_targets ?? []) draft[vt.category][vt.direction] = vt.ml_per_day;
    setVolumes(draft);
  }, [baby?.id, editingGoals]);

  const setVolume = (cat: VolumeCategory, dir: 'min' | 'max', v: number) =>
    setVolumes((cur) => ({ ...cur, [cat]: { ...cur[cat], [dir]: v } }));

  const saveGoals = async () => {
    if (!baby) return;
    const volume_targets: VolumeTarget[] = [];
    for (const [cat] of VOLUME_LABELS) {
      const { min, max } = volumes[cat];
      if (min > 0 && max > 0 && min > max) {
        showAlert('Check goals', `${cat.replace('_', ' ')}: min is larger than max.`);
        return;
      }
      if (min > 0) volume_targets.push({ category: cat, direction: 'min', ml_per_day: min });
      if (max > 0) volume_targets.push({ category: cat, direction: 'max', ml_per_day: max });
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(effectiveFrom.trim())) {
      showAlert('Check date', 'Pick the day these goals took effect.');
      return;
    }
    setSaving(true);
    try {
      await api.updateBaby(baby.id, {
        default_latch_rate_ml_per_10min: latchRate,
        targets: {
          lysine_mg_per_day: lysineTarget > 0 ? lysineTarget : null,
          natural_protein_g_per_day: proteinTarget > 0 ? proteinTarget : null,
          lysine_mg_per_kg: lysinePerKg > 0 ? lysinePerKg : null,
          natural_protein_g_per_kg: proteinPerKg > 0 ? proteinPerKg : null,
          volume_targets,
        },
        targets_effective_from: effectiveFrom.trim(),
      });
      qc.invalidateQueries();
      setEditingGoals(false);
    } catch (e: any) {
      showAlert('Could not save', e.message);
    } finally {
      setSaving(false);
    }
  };

  if (!baby) return null;
  const recipe = recipeQ.data;
  const hbOther = hbQ.data?.connected ? hbQ.data.mapping['Other'] : undefined;

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      <SectionTitle>Recipe · in effect now</SectionTitle>
      <Pressable onPress={() => router.push('/recipe')}>
        <Card>
          {recipe ? (
            <>
              <Text style={styles.big}>
                {fmtNum(recipe.breast_milk_ml)} ml breast milk + {fmtNum(recipe.batch_ml)} ml batch ={' '}
                {fmtNum(recipe.prepared_ml)} ml
              </Text>
              {recipe.powders.length > 0 ? (
                <Text style={styles.line}>
                  Batch: {recipe.powders.map((p) => `${fmtNum(p.grams)} g ${p.name}`).join(' + ')}
                  {recipe.batch_final_volume_ml ? ` → water to ${fmtNum(recipe.batch_final_volume_ml)} ml` : ''}
                </Text>
              ) : null}
              <Muted style={{ marginTop: 4 }}>
                "{recipe.label}" · since{' '}
                {new Date(recipe.effective_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                {recipe.source ? ` · ${recipe.source}` : ''}
              </Muted>
            </>
          ) : (
            <Text style={styles.line}>No recipe yet — add the plan your team gave you.</Text>
          )}
          <Text style={[styles.link, { marginTop: spacing.sm }]}>Recipe history, new recipe, re-split imports ›</Text>
        </Card>
      </Pressable>

      <SectionTitle>Goals · per day</SectionTitle>
      {!editingGoals ? (
        <Card>
          <Text style={styles.line}>{describeTargets(baby.targets)}</Text>
          <Muted style={{ marginTop: 4 }}>
            Current weight: {baby.current_weight_g ? fmtWeight(baby.current_weight_g) : 'none logged yet'}
            {baby.current_weight_g && baby.targets.lysine_mg_per_kg
              ? ` → lysine goal ${fmtNum((baby.targets.lysine_mg_per_kg * baby.current_weight_g) / 1000)} mg/day`
              : ''}
          </Muted>
          <Button
            title="Change goals (with a start date)"
            variant="secondary"
            onPress={() => setEditingGoals(true)}
            style={{ marginTop: spacing.md }}
          />
        </Card>
      ) : (
        <Card>
          <Text style={styles.label}>Lysine (mg/day)</Text>
          <Stepper value={lysineTarget} onChange={setLysineTarget} step={10} suffix="mg" />
          <Text style={[styles.label, { marginTop: spacing.md }]}>Natural protein (g/day)</Text>
          <Stepper value={proteinTarget} onChange={setProteinTarget} step={0.5} suffix="g" />

          <Text style={styles.groupHeader}>Per-kg goals (win over the absolute values once a weight is logged)</Text>
          <View style={{ flexDirection: 'row', gap: spacing.md }}>
            <View style={{ flex: 1 }}>
              <Muted style={{ marginBottom: 4 }}>lysine (mg/kg/day)</Muted>
              <Stepper value={lysinePerKg} onChange={setLysinePerKg} step={5} suffix="mg" />
            </View>
            <View style={{ flex: 1 }}>
              <Muted style={{ marginBottom: 4 }}>protein (g/kg/day)</Muted>
              <Stepper value={proteinPerKg} onChange={setProteinPerKg} step={0.1} suffix="g" />
            </View>
          </View>

          <Text style={styles.groupHeader}>Volume goals (ml/day — 0 = none)</Text>
          {VOLUME_LABELS.map(([cat, label]) => (
            <View key={cat} style={{ marginTop: spacing.sm }}>
              <Text style={styles.label}>{label}</Text>
              <View style={{ flexDirection: 'row', gap: spacing.md }}>
                <View style={{ flex: 1 }}>
                  <Muted style={{ marginBottom: 4 }}>at least (min)</Muted>
                  <Stepper value={volumes[cat].min} onChange={(v) => setVolume(cat, 'min', v)} step={10} suffix="ml" />
                </View>
                <View style={{ flex: 1 }}>
                  <Muted style={{ marginBottom: 4 }}>at most (max)</Muted>
                  <Stepper value={volumes[cat].max} onChange={(v) => setVolume(cat, 'max', v)} step={10} suffix="ml" />
                </View>
              </View>
            </View>
          ))}

          <Text style={[styles.label, { marginTop: spacing.md }]}>Default latch rate (ml per 10 min)</Text>
          <Stepper value={latchRate} onChange={setLatchRate} step={5} suffix="ml" />

          <View style={{ marginTop: spacing.md }}>
            <DateField label="In effect since (past days keep their old goals)" value={effectiveFrom} onChange={setEffectiveFrom} maximumDate={new Date()} />
          </View>
          <Button title="Save goals" onPress={saveGoals} loading={saving} />
          <Button title="Cancel" variant="secondary" onPress={() => setEditingGoals(false)} style={{ marginTop: spacing.sm }} />
        </Card>
      )}

      {(historyQ.data?.length ?? 0) > 0 && (
        <>
          <SectionTitle>Goal history</SectionTitle>
          <Card style={{ paddingVertical: 4 }}>
            {historyQ
              .data!.slice()
              .reverse()
              .map((p, i, arr) => {
                const from = p.effective_date === '0001-01-01' ? 'start' : p.effective_date;
                const until = i === 0 ? 'now' : arr[i - 1].effective_date;
                return (
                  <Pressable
                    key={p.effective_date}
                    onLongPress={() =>
                      showAlert(
                        'Delete this goal period?',
                        `Days from ${from} will fall back to the previous period's goals.`,
                        [
                          { text: 'Cancel', style: 'cancel' },
                          {
                            text: 'Delete',
                            style: 'destructive',
                            onPress: async () => {
                              await api.deleteTargetPeriod(baby.id, p.effective_date);
                              qc.invalidateQueries({ queryKey: ['target-history'] });
                            },
                          },
                        ],
                      )
                    }
                    style={[styles.historyRow, i > 0 && { borderTopWidth: 1, borderTopColor: colors.border }]}
                  >
                    <Text style={styles.historyDates}>
                      {from} → {until}
                    </Text>
                    <Text style={styles.historyTargets}>{describeTargets(p.targets)}</Text>
                  </Pressable>
                );
              })}
          </Card>
          <Muted style={{ marginBottom: spacing.sm }}>
            Past days are judged against the goals in effect then · long-press a period to delete it.
            Recipe history lives on the Recipe screen.
          </Muted>
        </>
      )}

      <SectionTitle>Sources</SectionTitle>
      <Card style={{ paddingVertical: 4 }}>
        <Pressable style={styles.row} onPress={() => router.push('/huckleberry')}>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>🫐 Huckleberry sync</Text>
            <Muted>
              {!hbQ.data?.connected
                ? 'Not connected'
                : `${hbQ.data.pending_count > 0 ? `${hbQ.data.pending_count} to review · ` : ''}"Other" bottles ${
                    hbOther?.recipe ? 'split by recipe' : 'use a fixed ratio'
                  }`}
            </Muted>
          </View>
          <Text style={styles.chev}>›</Text>
        </Pressable>
        <Pressable style={[styles.row, styles.rowBorder]} onPress={() => router.push('/mychart')}>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>🏥 MyChart (labs & documents)</Text>
            <Muted>
              {!mcQ.data?.configured
                ? 'Needs one-time Epic setup'
                : mcQ.data?.connected
                  ? `Connected${(mcQ.data.pending_labs + mcQ.data.pending_docs + mcQ.data.pending_messages) > 0 ? ` · ${mcQ.data.pending_labs + mcQ.data.pending_docs + mcQ.data.pending_messages} to review` : ''}`
                  : 'Not connected'}
            </Muted>
          </View>
          <Text style={styles.chev}>›</Text>
        </Pressable>
        <Pressable style={[styles.row, styles.rowBorder]} onPress={() => router.push('/reminders')}>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>⏰ Feed reminders</Text>
            <Muted>Rhythm reminders anchored to the last feed / med</Muted>
          </View>
          <Text style={styles.chev}>›</Text>
        </Pressable>
      </Card>

      <SectionTitle>Foods & nutrition values</SectionTitle>
      <Muted style={{ marginBottom: spacing.sm }}>
        ⚠︎ Seeded values are estimates — confirm every number with your metabolic dietitian.
      </Muted>
      <Card style={{ paddingVertical: 4 }}>
        {foods.map((f, i) => (
          <Pressable
            key={f.id}
            onPress={() => router.push({ pathname: '/edit-food', params: { id: f.id } })}
            style={[styles.row, i > 0 && styles.rowBorder]}
          >
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>
                {f.name} {f.needs_dietitian_verification ? '⚠︎' : '✓'}
              </Text>
              <Muted>
                {fmtNum(f.natural_protein_g_per_unit, 2)} g protein · {fmtNum(f.lysine_mg_per_unit)} mg lysine{' '}
                {f.unit_basis === 'per_100ml' ? 'per 100ml' : 'per scoop'}
              </Muted>
            </View>
            <Text style={styles.chev}>›</Text>
          </Pressable>
        ))}
      </Card>
      <Button title="＋ Add a food" variant="secondary" onPress={() => router.push({ pathname: '/edit-food' })} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  big: { fontSize: 17, fontFamily: fonts.bold, color: colors.text, marginBottom: 4 },
  line: { fontSize: 15, color: colors.text, fontFamily: fonts.regular },
  link: { fontSize: 13, fontFamily: fonts.bold, color: colors.primary },
  label: { fontSize: 13, fontFamily: fonts.semibold, color: colors.muted, marginBottom: 6 },
  groupHeader: { fontSize: 14, fontFamily: fonts.heavy, color: colors.text, marginTop: spacing.lg, marginBottom: spacing.xs },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, minHeight: 44 },
  rowBorder: { borderTopWidth: 1, borderTopColor: colors.border },
  rowTitle: { fontFamily: fonts.semibold, color: colors.text, fontSize: 15 },
  chev: { color: colors.muted, fontSize: 20, fontFamily: fonts.bold },
  historyRow: { paddingVertical: 10 },
  historyDates: { fontFamily: fonts.bold, color: colors.text, fontSize: 13.5 },
  historyTargets: { fontFamily: fonts.regular, color: colors.muted, fontSize: 13, marginTop: 2 },
});
