import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, Share, StyleSheet, Text, View } from 'react-native';

import { api } from '../../lib/api';
import { fmtNum } from '../../lib/format';
import { useAuth } from '../../lib/auth';
import { useBaby, useFoods } from '../../lib/hooks';
import { colors, spacing } from '../../lib/theme';
import { Button, Card, Field, Muted, SectionTitle, Stepper } from '../../components/ui';

export default function Settings() {
  const router = useRouter();
  const qc = useQueryClient();
  const { signOut } = useAuth();
  const { baby } = useBaby();
  const { foods } = useFoods();
  const meQ = useQuery({ queryKey: ['me'], queryFn: api.me });

  const [lysineTarget, setLysineTarget] = useState(0);
  const [proteinTarget, setProteinTarget] = useState(0);
  const [latchRate, setLatchRate] = useState(20);
  const [savingTargets, setSavingTargets] = useState(false);

  useEffect(() => {
    if (baby) {
      setLysineTarget(baby.targets.lysine_mg_per_day ?? 0);
      setProteinTarget(baby.targets.natural_protein_g_per_day ?? 0);
      setLatchRate(baby.default_latch_rate_ml_per_10min);
    }
  }, [baby?.id]);

  const saveBaby = async () => {
    if (!baby) return;
    setSavingTargets(true);
    try {
      await api.updateBaby(baby.id, {
        default_latch_rate_ml_per_10min: latchRate,
        targets: {
          lysine_mg_per_day: lysineTarget > 0 ? lysineTarget : null,
          natural_protein_g_per_day: proteinTarget > 0 ? proteinTarget : null,
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

      <SectionTitle>Family</SectionTitle>
      <Card>
        {meQ.data?.family.members.map((m) => (
          <Text key={m.email} style={{ color: colors.text, paddingVertical: 4 }}>
            👤 {m.name} <Muted>({m.email})</Muted>
          </Text>
        ))}
        <Muted style={{ marginTop: 4 }}>Timezone: {meQ.data?.family.timezone}</Muted>
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
  label: { fontSize: 13, fontWeight: '600', color: colors.muted, marginBottom: 6 },
  foodRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
  },
});
