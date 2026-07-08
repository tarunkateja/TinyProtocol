import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, Share, StyleSheet, Text, View } from 'react-native';

import { api } from '../../lib/api';
import { fmtNum } from '../../lib/format';
import { useAuth } from '../../lib/auth';
import { useBaby, useFoods } from '../../lib/hooks';
import { colors, fonts, spacing } from '../../lib/theme';
import type { VolumeCategory, VolumeTarget } from '../../lib/types';
import { Button, Card, Field, Muted, SectionTitle, Stepper } from '../../components/ui';

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

export default function Settings() {
  const router = useRouter();
  const qc = useQueryClient();
  const { signOut } = useAuth();
  const { baby } = useBaby();
  const { foods } = useFoods();
  const meQ = useQuery({ queryKey: ['me'], queryFn: api.me });

  const [lysineTarget, setLysineTarget] = useState(0);
  const [proteinTarget, setProteinTarget] = useState(0);
  const [lysinePerKg, setLysinePerKg] = useState(0);
  const [proteinPerKg, setProteinPerKg] = useState(0);
  const [latchRate, setLatchRate] = useState(20);
  const [volumes, setVolumes] = useState<VolumeDraft>(EMPTY_VOLUMES);
  const [savingTargets, setSavingTargets] = useState(false);

  useEffect(() => {
    if (baby) {
      setLysineTarget(baby.targets.lysine_mg_per_day ?? 0);
      setProteinTarget(baby.targets.natural_protein_g_per_day ?? 0);
      setLysinePerKg(baby.targets.lysine_mg_per_kg ?? 0);
      setProteinPerKg(baby.targets.natural_protein_g_per_kg ?? 0);
      setLatchRate(baby.default_latch_rate_ml_per_10min);
      const draft: VolumeDraft = JSON.parse(JSON.stringify(EMPTY_VOLUMES));
      for (const vt of baby.targets.volume_targets ?? []) {
        draft[vt.category][vt.direction] = vt.ml_per_day;
      }
      setVolumes(draft);
    }
  }, [baby?.id]);

  const setVolume = (cat: VolumeCategory, dir: 'min' | 'max', v: number) =>
    setVolumes((cur) => ({ ...cur, [cat]: { ...cur[cat], [dir]: v } }));

  const saveBaby = async () => {
    if (!baby) return;
    const volume_targets: VolumeTarget[] = [];
    for (const [cat] of VOLUME_LABELS) {
      const { min, max } = volumes[cat];
      if (min > 0 && max > 0 && min > max) {
        Alert.alert('Check targets', `${cat.replace('_', ' ')}: min is larger than max.`);
        return;
      }
      if (min > 0) volume_targets.push({ category: cat, direction: 'min', ml_per_day: min });
      if (max > 0) volume_targets.push({ category: cat, direction: 'max', ml_per_day: max });
    }
    setSavingTargets(true);
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
      });
      qc.invalidateQueries();
      Alert.alert('Saved', 'Targets updated.');
    } catch (e: any) {
      Alert.alert('Could not save', e.message);
    } finally {
      setSavingTargets(false);
    }
  };

  const [dayStartHour, setDayStartHour] = useState(0);
  useEffect(() => {
    const ds = meQ.data?.family.day_start ?? '00:00';
    setDayStartHour(Number(ds.split(':')[0]) || 0);
  }, [meQ.data?.family.day_start]);

  const saveDayStart = async (h: number) => {
    const hour = Math.min(23, Math.max(0, Math.round(h)));
    setDayStartHour(hour);
    try {
      await api.updateFamily({ day_start: `${String(hour).padStart(2, '0')}:00` });
      qc.invalidateQueries();
    } catch (e: any) {
      Alert.alert('Could not save', e.message);
    }
  };

  const invitePartner = async () => {
    try {
      const invite = await api.createInvite();
      await Share.share({
        message: `Join me on TinyProtocol to track ${baby?.name ?? 'our baby'}'s feeds! Open the app, choose "Join with invite code" and enter: ${invite.code}`,
      });
    } catch (e: any) {
      Alert.alert('Could not create invite', e.message);
    }
  };

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      {baby && (
        <>
          <SectionTitle>
            {baby.name} — daily targets (from your metabolic team)
          </SectionTitle>
          <Card>
            <Text style={styles.label}>Lysine target (mg/day)</Text>
            <Stepper value={lysineTarget} onChange={setLysineTarget} step={10} suffix="mg" />
            <Text style={[styles.label, { marginTop: spacing.md }]}>
              Natural protein target (g/day)
            </Text>
            <Stepper value={proteinTarget} onChange={setProteinTarget} step={0.5} suffix="g" />
            <Text style={[styles.label, { marginTop: spacing.md }]}>
              Default latch rate (ml per 10 min)
            </Text>
            <Stepper value={latchRate} onChange={setLatchRate} step={5} suffix="ml" />

            <Text style={styles.volumeHeader}>
              Per-kg targets (recommended — recompute as {baby.name} grows)
            </Text>
            <Muted style={{ marginBottom: spacing.xs }}>
              Current weight:{' '}
              {baby.current_weight_g
                ? `${fmtNum(baby.current_weight_g / 1000, 2)} kg`
                : 'none logged yet — log a ⚖️ Weight event'}
              {baby.current_weight_g && lysinePerKg > 0
                ? ` → lysine target ${fmtNum((lysinePerKg * baby.current_weight_g) / 1000)} mg/day`
                : ''}
            </Muted>
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
            <Muted style={{ marginBottom: spacing.xs, marginTop: spacing.xs }}>
              Per-kg wins over the absolute values above once a weight is logged.
            </Muted>

            <Text style={styles.volumeHeader}>Volume targets (ml/day — 0 = no target)</Text>
            {VOLUME_LABELS.map(([cat, label]) => (
              <View key={cat} style={{ marginTop: spacing.sm }}>
                <Text style={styles.label}>{label}</Text>
                <View style={{ flexDirection: 'row', gap: spacing.md }}>
                  <View style={{ flex: 1 }}>
                    <Muted style={{ marginBottom: 4 }}>at least (min)</Muted>
                    <Stepper
                      value={volumes[cat].min}
                      onChange={(v) => setVolume(cat, 'min', v)}
                      step={10}
                      suffix="ml"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Muted style={{ marginBottom: 4 }}>at most (max)</Muted>
                    <Stepper
                      value={volumes[cat].max}
                      onChange={(v) => setVolume(cat, 'max', v)}
                      step={10}
                      suffix="ml"
                    />
                  </View>
                </View>
              </View>
            ))}
            <Muted style={{ marginTop: spacing.sm }}>
              Your case: breast milk max 400, GA1 formula min 120. Powder scoops don't
              count toward ml — log GA1 as the "prepared" liquid food.
            </Muted>

            <Button
              title="Save"
              onPress={saveBaby}
              loading={savingTargets}
              style={{ marginTop: spacing.md }}
            />
          </Card>
        </>
      )}

      <SectionTitle>Foods & nutrition values</SectionTitle>
      <Muted style={{ marginBottom: spacing.sm }}>
        ⚠︎ Seeded values are estimates — confirm every number with your metabolic dietitian,
        then edit them here.
      </Muted>
      <Card style={{ paddingVertical: 4 }}>
        {foods.map((f, i) => (
          <Pressable
            key={f.id}
            onPress={() => router.push({ pathname: '/edit-food', params: { id: f.id } })}
            style={[styles.foodRow, i > 0 && { borderTopWidth: 1, borderTopColor: colors.border }]}
          >
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '600', color: colors.text }}>
                {f.name} {f.needs_dietitian_verification ? '⚠︎' : '✓'}
              </Text>
              <Muted>
                {fmtNum(f.natural_protein_g_per_unit, 2)} g protein · {fmtNum(f.lysine_mg_per_unit)} mg
                lysine {f.unit_basis === 'per_100ml' ? 'per 100ml' : 'per scoop'}
              </Muted>
            </View>
            <Text style={{ color: colors.muted, fontSize: 18 }}>›</Text>
          </Pressable>
        ))}
      </Card>

      <Button
        title="＋ Add a food"
        variant="secondary"
        onPress={() => router.push({ pathname: '/edit-food' })}
        style={{ marginBottom: spacing.md }}
      />

      <SectionTitle>Care & safety</SectionTitle>
      <Button
        title="🆘 Emergency card"
        variant="secondary"
        onPress={() => router.push('/emergency')}
        style={{ marginBottom: spacing.sm }}
      />
      <Button
        title="📂 Care documents (AI-processed)"
        variant="secondary"
        onPress={() => router.push('/docs')}
        style={{ marginBottom: spacing.sm }}
      />
      <Button
        title="🧪 Lab results & trends"
        variant="secondary"
        onPress={() => router.push('/labs')}
        style={{ marginBottom: spacing.sm }}
      />
      <Button
        title="📝 Clinic questions"
        variant="secondary"
        onPress={() => router.push('/clinic-notes')}
        style={{ marginBottom: spacing.sm }}
      />
      <Button
        title="📚 GA1 references & sources"
        variant="secondary"
        onPress={() => router.push('/references')}
      />

      <SectionTitle>Reminders</SectionTitle>
      <Button
        title="⏰ Feed reminders"
        variant="secondary"
        onPress={() => router.push('/reminders')}
      />

      <SectionTitle>Family</SectionTitle>
      <Card>
        {meQ.data?.family.members.map((m) => (
          <Text key={m.email} style={{ color: colors.text, paddingVertical: 4 }}>
            👤 {m.name} <Muted>({m.email})</Muted>
          </Text>
        ))}
        <Muted style={{ marginTop: 4 }}>Timezone: {meQ.data?.family.timezone}</Muted>
        <Text style={[styles.label, { marginTop: spacing.md }]}>
          Our day starts at (Today & Totals reset here, not midnight)
        </Text>
        <Stepper value={dayStartHour} onChange={saveDayStart} step={1} suffix=":00" />
        <Button
          title="Invite partner"
          variant="secondary"
          onPress={invitePartner}
          style={{ marginTop: spacing.md }}
        />
      </Card>

      <Button title="Sign out" variant="danger" onPress={signOut} style={{ marginTop: spacing.lg }} />
      <Muted style={{ textAlign: 'center', marginTop: spacing.lg }}>
        TinyProtocol is not medical advice. Always follow your metabolic team's guidance.
      </Muted>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 13, fontFamily: fonts.semibold, color: colors.muted, marginBottom: 6 },
  volumeHeader: {
    fontSize: 14,
    fontFamily: fonts.heavy,
    color: colors.text,
    marginTop: spacing.lg,
  },
  foodRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
  },
});
