import { useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import { fmtNum, localDateString } from '../lib/format';
import { colors, fonts, radius, spacing } from '../lib/theme';
import type { LabResult } from '../lib/types';
import { Button, Card, Chip, Field, Muted, SectionTitle, Stepper, DateField } from '../components/ui';
import { showAlert } from '../lib/dialogs';

const COMMON_ANALYTES = ['lysine', 'glutarylcarnitine', 'free_carnitine'];

export default function Labs() {
  const qc = useQueryClient();
  const labsQ = useQuery({ queryKey: ['labs'], queryFn: api.listLabs });
  const [adding, setAdding] = useState(false);
  const [analyte, setAnalyte] = useState('lysine');
  const [customAnalyte, setCustomAnalyte] = useState('');
  const [value, setValue] = useState(0);
  const [unit, setUnit] = useState('umol/L');
  const [date, setDate] = useState(localDateString());

  const grouped = useMemo(() => {
    const by: Record<string, LabResult[]> = {};
    for (const lab of labsQ.data ?? []) {
      (by[lab.analyte] ??= []).push(lab);
    }
    for (const rows of Object.values(by)) {
      rows.sort((a, b) => a.collected_date.localeCompare(b.collected_date));
    }
    return by;
  }, [labsQ.data]);

  const save = async () => {
    const a = analyte === 'custom' ? customAnalyte.trim() : analyte;
    if (!a || value <= 0) return;
    try {
      await api.createLab({ analyte: a, value, unit: unit.trim() || '—', collected_date: date });
      qc.invalidateQueries({ queryKey: ['labs'] });
      setAdding(false);
      setValue(0);
    } catch (e: any) {
      showAlert('Could not save', e.message);
    }
  };

  const remove = (lab: LabResult) => {
    showAlert(`Delete ${lab.analyte} ${fmtNum(lab.value)} ${lab.unit}?`, lab.collected_date, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          await api.deleteLab(lab.id);
          qc.invalidateQueries({ queryKey: ['labs'] });
        },
      },
    ]);
  };

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      <Muted style={{ marginBottom: spacing.sm }}>
        Clinic blood results over time — uploaded lab reports land here automatically,
        or add values by hand. Interpretation belongs to your metabolic team.
      </Muted>
      <Button
        title={adding ? 'Cancel' : '＋ Add result'}
        variant="secondary"
        onPress={() => setAdding(!adding)}
      />

      {adding && (
        <Card style={{ marginTop: spacing.md }}>
          <Text style={styles.label}>Analyte</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
            {[...COMMON_ANALYTES, 'custom'].map((a) => (
              <Chip
                key={a}
                label={a.replace('_', ' ')}
                selected={analyte === a}
                onPress={() => setAnalyte(a)}
              />
            ))}
          </View>
          {analyte === 'custom' && (
            <Field label="Analyte name" value={customAnalyte} onChangeText={setCustomAnalyte} />
          )}
          <Text style={styles.label}>Value</Text>
          <Stepper value={value} onChange={setValue} step={1} />
          <Field label="Unit" value={unit} onChangeText={setUnit} />
          <DateField label="Collected date" value={date} onChange={setDate} maximumDate={new Date()} />
          <Button title="Save result" onPress={save} disabled={value <= 0} />
        </Card>
      )}

      {Object.keys(grouped).length === 0 && (
        <Muted style={{ textAlign: 'center', marginTop: 30 }}>
          {labsQ.isLoading ? 'Loading…' : 'No lab results yet — upload a lab report in Care documents.'}
        </Muted>
      )}

      {Object.entries(grouped).map(([name, rows]) => {
        const latest = rows[rows.length - 1];
        const max = Math.max(...rows.map((r) => r.value));
        return (
          <View key={name}>
            <SectionTitle>{name.replace(/_/g, ' ')}</SectionTitle>
            <Card>
              <Text style={styles.headline}>
                {fmtNum(latest.value)} {latest.unit}
                <Text style={styles.headlineDate}>  · {latest.collected_date}</Text>
              </Text>
              {rows.length > 1 && (
                <View style={styles.sparkRow}>
                  {rows.map((r) => (
                    <View key={r.id} style={styles.sparkCol}>
                      <View
                        style={[
                          styles.sparkBar,
                          {
                            height: Math.max(6, (r.value / max) * 56),
                            backgroundColor: r.id === latest.id ? colors.primary : colors.primarySoft,
                            borderColor: colors.primary,
                          },
                        ]}
                      />
                      <Text style={styles.sparkLabel}>{r.collected_date.slice(5)}</Text>
                    </View>
                  ))}
                </View>
              )}
              {rows
                .slice()
                .reverse()
                .map((r, i) => (
                  <Pressable key={r.id} onLongPress={() => remove(r)}>
                    <View style={[styles.tableRow, i > 0 && styles.rowBorder]}>
                      <Text style={styles.tableDate}>{r.collected_date}</Text>
                      <Text style={styles.tableValue}>
                        {fmtNum(r.value)} {r.unit}
                        {r.source_doc_id ? ' 📄' : ''}
                      </Text>
                    </View>
                  </Pressable>
                ))}
            </Card>
          </View>
        );
      })}
      <Muted style={{ textAlign: 'center', marginTop: spacing.sm }}>
        📄 = extracted from an uploaded report · long-press a row to delete.
      </Muted>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 13, fontFamily: fonts.semibold, color: colors.muted, marginBottom: 6 },
  headline: { fontSize: 22, fontFamily: fonts.heavy, color: colors.text, marginBottom: spacing.sm },
  headlineDate: { fontSize: 13, fontFamily: fonts.regular, color: colors.muted },
  sparkRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 6,
    marginBottom: spacing.md,
    minHeight: 72,
  },
  sparkCol: { alignItems: 'center', flex: 1, maxWidth: 44 },
  sparkBar: { width: '100%', borderRadius: 4, borderWidth: 1 },
  sparkLabel: { fontSize: 9, color: colors.muted, marginTop: 2, fontFamily: fonts.regular },
  tableRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8 },
  rowBorder: { borderTopWidth: 1, borderTopColor: colors.border },
  tableDate: { color: colors.muted, fontFamily: fonts.regular, fontSize: 14 },
  tableValue: { color: colors.text, fontFamily: fonts.bold, fontSize: 14 },
});
