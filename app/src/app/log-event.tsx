import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import { api } from '../lib/api';
import { useBaby, useInvalidateLogs, useMedPresets } from '../lib/hooks';
import { colors, spacing } from '../lib/theme';
import type { DoseUnit, EventType, Severity } from '../lib/types';
import { Button, Card, Chip, Field, Muted, SectionTitle, Stepper } from '../components/ui';
import { TimePickerRow } from '../components/TimePickerRow';

const TYPES: { key: EventType; label: string }[] = [
  { key: 'spit_up', label: '💧 Spit-up' },
  { key: 'vomit', label: '🤮 Vomit' },
  { key: 'fussiness', label: '😾 Fussy' },
  { key: 'medication', label: '💊 Meds' },
  { key: 'note', label: '📝 Note' },
];

const SEVERITIES: Severity[] = ['small', 'medium', 'large'];

export default function LogEvent() {
  const router = useRouter();
  const { baby } = useBaby();
  const { presets } = useMedPresets();
  const invalidate = useInvalidateLogs();

  const [type, setType] = useState<EventType>('spit_up');
  const [severity, setSeverity] = useState<Severity>('small');
  const [medName, setMedName] = useState('');
  const [dose, setDose] = useState(0);
  const [doseUnit, setDoseUnit] = useState<DoseUnit>('ml');
  const [note, setNote] = useState('');
  const [when, setWhen] = useState(new Date());
  const [busy, setBusy] = useState(false);

  const needsSeverity = type === 'spit_up' || type === 'vomit';
  const canSave =
    type === 'medication' ? medName.trim().length > 0 : type === 'note' ? note.trim().length > 0 : true;

  const save = async () => {
    if (!baby) return;
    setBusy(true);
    try {
      await api.createEvent(baby.id, {
        occurred_at: when.toISOString(),
        type,
        severity: needsSeverity ? severity : undefined,
        med_name: type === 'medication' ? medName.trim() : undefined,
        dose_amount: type === 'medication' && dose > 0 ? dose : undefined,
        dose_unit: type === 'medication' && dose > 0 ? doseUnit : undefined,
        note: note.trim() || undefined,
      });
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
        {TYPES.map((t) => (
          <Chip key={t.key} label={t.label} selected={type === t.key} onPress={() => setType(t.key)} />
        ))}
      </View>

      {needsSeverity && (
        <>
          <SectionTitle>How big?</SectionTitle>
          <View style={{ flexDirection: 'row' }}>
            {SEVERITIES.map((s) => (
              <Chip key={s} label={s} selected={severity === s} onPress={() => setSeverity(s)} />
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
                />
              ))}
            </View>
          )}
          <Field label="Medication" value={medName} onChangeText={setMedName} />
          <Text style={{ fontSize: 13, fontWeight: '600', color: colors.muted, marginBottom: 6 }}>
            Dose
          </Text>
          <Stepper value={dose} onChange={setDose} step={doseUnit === 'ml' ? 0.5 : 5} suffix={doseUnit} />
          <View style={{ flexDirection: 'row', marginTop: spacing.sm }}>
            {(['ml', 'mg'] as DoseUnit[]).map((u) => (
              <Chip key={u} label={u} selected={doseUnit === u} onPress={() => setDoseUnit(u)} />
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
      <Button title="Save event" onPress={save} loading={busy} disabled={!canSave} />
    </ScrollView>
  );
}
