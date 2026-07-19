import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import { api } from '../lib/api';
import { fmtNum, gToOz, lbOzToG } from '../lib/format';
import { useBaby, useInvalidateLogs, useMedPresets } from '../lib/hooks';
import { colors, eventTheme, fonts, spacing } from '../lib/theme';
import type { DiaperKind, DoseUnit, EventType, PumpSide, Severity } from '../lib/types';
import { Button, Card, Chip, Field, Muted, SectionTitle, Stepper } from '../components/ui';
import { SessionTimer } from '../components/SessionTimer';
import { TimePickerRow } from '../components/TimePickerRow';

const TYPES: EventType[] = [
  'pumping',
  'diaper',
  'weight',
  'spit_up',
  'vomit',
  'fussiness',
  'medication',
  'note',
];

const SEVERITIES: Severity[] = ['small', 'medium', 'large'];

export default function LogEvent() {
  const router = useRouter();
  const { eventId } = useLocalSearchParams<{ eventId?: string }>();
  const editing = !!eventId;
  const { baby } = useBaby();
  const { presets } = useMedPresets();
  const invalidate = useInvalidateLogs();

  const [type, setType] = useState<EventType>('pumping');
  const [severity, setSeverity] = useState<Severity>('small');
  const [medName, setMedName] = useState('');
  const [dose, setDose] = useState(0);
  const [doseUnit, setDoseUnit] = useState<DoseUnit>('ml');
  const [pumpedMl, setPumpedMl] = useState(0);
  const [side, setSide] = useState<PumpSide>('both');
  const [pumpMinutes, setPumpMinutes] = useState(0);
  const [diaperKind, setDiaperKind] = useState<DiaperKind>('pee');
  const [weightLb, setWeightLb] = useState(0);
  const [weightOz, setWeightOz] = useState(0);
  const [note, setNote] = useState('');
  const [when, setWhen] = useState(new Date());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!eventId) return;
    api
      .getEvent(eventId)
      .then((ev) => {
        setType(ev.type);
        setWhen(new Date(ev.occurred_at));
        if (ev.severity) setSeverity(ev.severity);
        if (ev.med_name) setMedName(ev.med_name);
        if (ev.dose_amount) setDose(ev.dose_amount);
        if (ev.dose_unit) setDoseUnit(ev.dose_unit);
        if (ev.pumped_ml) setPumpedMl(ev.pumped_ml);
        if (ev.side) setSide(ev.side);
        if (ev.duration_minutes) setPumpMinutes(ev.duration_minutes);
        if (ev.diaper_kind) setDiaperKind(ev.diaper_kind);
        if (ev.weight_g) {
          const totalOz = gToOz(ev.weight_g);
          setWeightLb(Math.floor(totalOz / 16));
          setWeightOz(Math.round((totalOz % 16) * 10) / 10);
        }
        if (ev.note) setNote(ev.note);
      })
      .catch((e) => Alert.alert('Could not load event', e.message));
  }, [eventId]);

  const theme = eventTheme[type] ?? eventTheme.note;
  const needsSeverity = type === 'spit_up' || type === 'vomit';
  const canSave =
    type === 'medication'
      ? medName.trim().length > 0
      : type === 'note'
        ? note.trim().length > 0
        : type === 'pumping'
          ? pumpedMl > 0
          : type === 'weight'
            ? weightLb > 0 || weightOz > 0
            : true;

  const save = async () => {
    if (!baby) return;
    setBusy(true);
    try {
      const body = {
        occurred_at: when.toISOString(),
        type,
        severity: needsSeverity ? severity : undefined,
        med_name: type === 'medication' ? medName.trim() : undefined,
        dose_amount: type === 'medication' && dose > 0 ? dose : undefined,
        dose_unit: type === 'medication' && dose > 0 ? doseUnit : undefined,
        pumped_ml: type === 'pumping' ? pumpedMl : undefined,
        side: type === 'pumping' ? side : undefined,
        duration_minutes: type === 'pumping' && pumpMinutes > 0 ? pumpMinutes : undefined,
        diaper_kind: type === 'diaper' ? diaperKind : undefined,
        weight_g: type === 'weight' ? lbOzToG(weightLb, weightOz) : undefined,
        note: note.trim() || undefined,
      };
      if (editing) {
        const { type: _t, ...patch } = body; // type can't change on edit
        await api.updateEvent(eventId!, patch);
      } else {
        await api.createEvent(baby.id, body);
      }
      invalidate();
      router.back();
    } catch (e: any) {
      Alert.alert('Could not save event', e.message);
      setBusy(false);
    }
  };

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}
      keyboardShouldPersistTaps="handled"
    >
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: spacing.sm }}>
        {(editing ? TYPES.filter((t) => t === type) : TYPES).map((t) => {
          const th = eventTheme[t];
          return (
            <Chip
              key={t}
              label={`${th.icon} ${th.label}`}
              selected={type === t}
              onPress={() => setType(t)}
              color={th.color}
              softColor={th.soft}
            />
          );
        })}
      </View>

      {type === 'pumping' && (
        <Card>
          <Text style={styles_label}>Timer (optional)</Text>
          <SessionTimer onMinutes={setPumpMinutes} color={theme.color} />
          <Text style={[styles_label, { marginTop: spacing.md }]}>Amount pumped</Text>
          <Stepper value={pumpedMl} onChange={setPumpedMl} step={10} suffix="ml" />
          <Text style={[styles_label, { marginTop: spacing.md }]}>Side</Text>
          <View style={{ flexDirection: 'row' }}>
            {(['left', 'right', 'both'] as PumpSide[]).map((s) => (
              <Chip
                key={s}
                label={s}
                selected={side === s}
                onPress={() => setSide(s)}
                color={theme.color}
                softColor={theme.soft}
              />
            ))}
          </View>
          <Text style={[styles_label, { marginTop: spacing.md }]}>Minutes (from timer, editable)</Text>
          <Stepper value={pumpMinutes} onChange={setPumpMinutes} step={5} suffix="min" />
        </Card>
      )}

      {type === 'diaper' && (
        <Card>
          <Text style={styles_label}>What's in it?</Text>
          <View style={{ flexDirection: 'row' }}>
            {(
              [
                ['pee', '💧 Pee'],
                ['poop', '💩 Poop'],
                ['both', '💧💩 Both'],
              ] as [DiaperKind, string][]
            ).map(([k, label]) => (
              <Chip
                key={k}
                label={label}
                selected={diaperKind === k}
                onPress={() => setDiaperKind(k)}
                color={theme.color}
                softColor={theme.soft}
              />
            ))}
          </View>
          <Muted style={{ marginTop: spacing.xs }}>
            Add color/consistency in the notes if the care team asked you to watch it.
          </Muted>
        </Card>
      )}

      {type === 'weight' && (
        <Card>
          <Text style={styles_label}>Weight</Text>
          <View style={{ flexDirection: 'row', gap: spacing.md }}>
            <View style={{ flex: 1 }}>
              <Muted style={{ marginBottom: 4 }}>pounds</Muted>
              <Stepper value={weightLb} onChange={setWeightLb} step={1} suffix="lb" />
            </View>
            <View style={{ flex: 1 }}>
              <Muted style={{ marginBottom: 4 }}>ounces</Muted>
              <Stepper value={weightOz} onChange={setWeightOz} step={0.5} suffix="oz" />
            </View>
          </View>
          <Muted style={{ marginTop: spacing.xs }}>
            {weightLb > 0 || weightOz > 0
              ? `= ${fmtNum(lbOzToG(weightLb, weightOz) / 1000, 2)} kg — updates the per-kg lysine/protein targets automatically.`
              : 'Updates the per-kg lysine/protein targets automatically.'}
          </Muted>
        </Card>
      )}

      {needsSeverity && (
        <>
          <SectionTitle>How big?</SectionTitle>
          <View style={{ flexDirection: 'row' }}>
            {SEVERITIES.map((s) => (
              <Chip
                key={s}
                label={s}
                selected={severity === s}
                onPress={() => setSeverity(s)}
                color={theme.color}
                softColor={theme.soft}
              />
            ))}
          </View>
        </>
      )}

      {type === 'medication' && (
        <Card style={{ marginTop: spacing.md }}>
          {presets.length > 0 && (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: spacing.sm }}>
              {presets.map((p) => (
                <Chip
                  key={p.id}
                  label={p.name}
                  selected={medName === p.name}
                  onPress={() => {
                    setMedName(p.name);
                    setDoseUnit(p.dose_unit);
                    if (p.default_dose) setDose(p.default_dose);
                  }}
                  color={theme.color}
                  softColor={theme.soft}
                />
              ))}
            </View>
          )}
          <Field label="Medication" value={medName} onChangeText={setMedName} />
          <Text style={styles_label}>Dose</Text>
          <Stepper value={dose} onChange={setDose} step={doseUnit === 'ml' ? 0.5 : 5} suffix={doseUnit} />
          <View style={{ flexDirection: 'row', marginTop: spacing.sm }}>
            {(['ml', 'mg'] as DoseUnit[]).map((u) => (
              <Chip
                key={u}
                label={u}
                selected={doseUnit === u}
                onPress={() => setDoseUnit(u)}
                color={theme.color}
                softColor={theme.soft}
              />
            ))}
          </View>
        </Card>
      )}

      <View style={{ marginTop: spacing.md }}>
        <TimePickerRow value={when} onChange={setWhen} />
      </View>
      <Field
        label={type === 'note' ? 'Note' : 'Notes (optional)'}
        value={note}
        onChangeText={setNote}
        multiline
      />
      {type === 'medication' && !medName.trim() && (
        <Muted style={{ marginBottom: spacing.sm }}>Pick a preset or type the medication name.</Muted>
      )}
      {type === 'pumping' && pumpedMl <= 0 && (
        <Muted style={{ marginBottom: spacing.sm }}>Enter how much you pumped.</Muted>
      )}
      <Button
        title={editing ? 'Save changes' : 'Save event'}
        onPress={save}
        loading={busy}
        disabled={!canSave}
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
