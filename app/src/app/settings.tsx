import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { ScrollView, Share, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import { showAlert } from '../lib/dialogs';
import { fmtAge, fmtNum, gToOz, kgToLbOz, lbOzToG } from '../lib/format';
import { useAuth } from '../lib/auth';
import { useBaby } from '../lib/hooks';
import { colors, fonts, spacing } from '../lib/theme';
import { Button, Card, DateField, Muted, SectionTitle, Stepper } from '../components/ui';

/** Settings is settings again: the baby's facts, the family, reminders,
 * account. The feeding plan (recipe, goals, foods, sync) lives in Plan. */
export default function Settings() {
  const router = useRouter();
  const qc = useQueryClient();
  const { signOut } = useAuth();
  const { baby } = useBaby();
  const meQ = useQuery({ queryKey: ['me'], queryFn: api.me });
  const recipeQ = useQuery({
    queryKey: ['recipe-current', baby?.id],
    queryFn: () => api.currentRecipe(baby!.id),
    enabled: !!baby,
  });

  const [dob, setDob] = useState('');
  const [birthLb, setBirthLb] = useState(0);
  const [birthOz, setBirthOz] = useState(0);
  const [savingAbout, setSavingAbout] = useState(false);

  useEffect(() => {
    if (baby) {
      setDob(baby.date_of_birth ?? '');
      if (baby.birth_weight_g) {
        const totalOz = gToOz(baby.birth_weight_g);
        setBirthLb(Math.floor(totalOz / 16));
        setBirthOz(Math.round((totalOz % 16) * 10) / 10);
      }
    }
  }, [baby?.id]);

  const saveAbout = async () => {
    if (!baby) return;
    const d = dob.trim();
    if (d && (!/^\d{4}-\d{2}-\d{2}$/.test(d) || Number.isNaN(new Date(d).getTime()))) {
      showAlert('Check date', 'Pick a birthday.');
      return;
    }
    setSavingAbout(true);
    try {
      await api.updateBaby(baby.id, {
        ...(d ? { date_of_birth: d } : {}),
        ...(birthLb > 0 || birthOz > 0 ? { birth_weight_g: lbOzToG(birthLb, birthOz) } : {}),
      });
      qc.invalidateQueries();
      showAlert('Saved', `${baby.name}'s details updated.`);
    } catch (e: any) {
      showAlert('Could not save', e.message);
    } finally {
      setSavingAbout(false);
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
      showAlert('Could not save', e.message);
    }
  };

  const invitePartner = async () => {
    try {
      const invite = await api.createInvite();
      await Share.share({
        message: `Join me on TinyProtocol to track ${baby?.name ?? 'our baby'}'s feeds! Open the app, choose "Join with invite code" and enter: ${invite.code}`,
      });
    } catch (e: any) {
      showAlert('Could not create invite', e.message);
    }
  };

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      <SectionTitle>Feeding plan</SectionTitle>
      <Button
        title={`🧪 Recipe, goals, foods & sync${
          recipeQ.data ? ` · ${fmtNum(recipeQ.data.breast_milk_ml)} + ${fmtNum(recipeQ.data.batch_ml)} ml` : ''
        }`}
        variant="secondary"
        onPress={() => router.push('/plan')}
        style={{ marginBottom: spacing.md }}
      />

      {baby && (
        <>
          <SectionTitle>About {baby.name}</SectionTitle>
          <Card>
            <DateField label="Birthday" value={dob} onChange={setDob} maximumDate={new Date()} />
            {/^\d{4}-\d{2}-\d{2}$/.test(dob.trim()) && fmtAge(dob.trim()) !== '' && (
              <Muted style={{ marginBottom: spacing.sm }}>
                {baby.name} is {fmtAge(dob.trim())} old today 🎉
              </Muted>
            )}
            <Text style={styles.label}>Birth weight</Text>
            <View style={{ flexDirection: 'row', gap: spacing.md }}>
              <View style={{ flex: 1 }}>
                <Muted style={{ marginBottom: 4 }}>pounds</Muted>
                <Stepper value={birthLb} onChange={setBirthLb} step={1} suffix="lb" />
              </View>
              <View style={{ flex: 1 }}>
                <Muted style={{ marginBottom: 4 }}>ounces</Muted>
                <Stepper value={birthOz} onChange={setBirthOz} step={0.5} suffix="oz" />
              </View>
            </View>
            <Muted style={{ marginBottom: 4, marginTop: spacing.sm }}>or in kilograms</Muted>
            <Stepper
              value={Math.round(lbOzToG(birthLb, birthOz) / 10) / 100}
              onChange={(kg) => {
                const { lb, oz } = kgToLbOz(Math.max(0, kg));
                setBirthLb(lb);
                setBirthOz(oz);
              }}
              step={0.01}
              suffix="kg"
            />
            <Muted style={{ marginTop: spacing.xs, marginBottom: spacing.sm }}>
              Current weight comes from ⚖️ Weight events — this is just the starting point for the
              growth chart.
            </Muted>
            <Button title="Save" onPress={saveAbout} loading={savingAbout} />
          </Card>
        </>
      )}

      <SectionTitle>Reminders</SectionTitle>
      <Button title="⏰ Feed reminders" variant="secondary" onPress={() => router.push('/reminders')} />

      <SectionTitle>Family</SectionTitle>
      <Card>
        {meQ.data?.family.members.map((m) => (
          <Text key={m.email} style={{ color: colors.text, paddingVertical: 4 }}>
            👤 {m.name} <Muted>({m.email})</Muted>
          </Text>
        ))}
        <Muted style={{ marginTop: 4 }}>Timezone: {meQ.data?.family.timezone}</Muted>
        <Text style={[styles.label, { marginTop: spacing.md }]}>
          Our day starts at (Home & totals reset here, not midnight)
        </Text>
        <Stepper value={dayStartHour} onChange={saveDayStart} step={1} suffix=":00" />
        <Button title="Invite partner" variant="secondary" onPress={invitePartner} style={{ marginTop: spacing.md }} />
      </Card>

      <SectionTitle>Appearance</SectionTitle>
      <Card>
        <Muted>
          Dark mode follows your phone's setting (Settings → Display → Dark, or a schedule) — handy
          for night feeds.
        </Muted>
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
});
