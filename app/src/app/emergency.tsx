import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useEffect, useState } from 'react';
import {
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { api } from '../lib/api';
import { colors, fonts, radius, spacing } from '../lib/theme';
import type { CareProfile } from '../lib/types';
import { Button, Card, Muted, SectionTitle } from '../components/ui';
import { showAlert } from '../lib/dialogs';

const CACHE_KEY = 'tinyprotocol_care_profile_cache';

export default function Emergency() {
  const qc = useQueryClient();
  const [cached, setCached] = useState<CareProfile | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<CareProfile | null>(null);
  const [saving, setSaving] = useState(false);

  const q = useQuery({ queryKey: ['careProfile'], queryFn: api.getCareProfile });

  // Offline safety: cache every successful fetch; fall back to the cache.
  useEffect(() => {
    if (q.data) AsyncStorage.setItem(CACHE_KEY, JSON.stringify(q.data));
  }, [q.data]);
  useEffect(() => {
    AsyncStorage.getItem(CACHE_KEY).then((raw) => raw && setCached(JSON.parse(raw)));
  }, []);

  const p = q.data ?? cached;
  const offline = !q.data && !!cached;

  const startEdit = () => {
    if (!p) return;
    setDraft(JSON.parse(JSON.stringify(p)));
    setEditing(true);
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      await api.putCareProfile(draft);
      qc.invalidateQueries({ queryKey: ['careProfile'] });
      setEditing(false);
    } catch (e: any) {
      showAlert('Could not save', e.message);
    } finally {
      setSaving(false);
    }
  };

  if (!p) {
    return (
      <View style={{ padding: spacing.xl }}>
        <Muted>{q.isLoading ? 'Loading…' : 'No emergency card yet.'}</Muted>
      </View>
    );
  }

  if (editing && draft) {
    return (
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
        <Muted style={{ marginBottom: spacing.sm }}>One item per line.</Muted>
        <EditList label="ER interventions" value={draft.er_interventions} onChange={(v) => setDraft({ ...draft, er_interventions: v })} />
        <EditList label="When to call" value={draft.when_to_call} onChange={(v) => setDraft({ ...draft, when_to_call: v })} />
        <EditList
          label="Contacts (Label | phone | when)"
          value={draft.contacts.map((c) => `${c.label} | ${c.phone} | ${c.when ?? ''}`)}
          onChange={(lines) =>
            setDraft({
              ...draft,
              contacts: lines
                .map((l) => l.split('|').map((x) => x.trim()))
                .filter((x) => x[0] && x[1])
                .map(([label, phone, when]) => ({ label, phone, when: when || null })),
            })
          }
        />
        <EditList label="Bring to the ER" value={draft.bring_to_er} onChange={(v) => setDraft({ ...draft, bring_to_er: v })} />
        <EditList label="Formula ordering" value={draft.formula_ordering} onChange={(v) => setDraft({ ...draft, formula_ordering: v })} />
        <View style={{ flexDirection: 'row', gap: spacing.md }}>
          <Button title="Cancel" variant="secondary" style={{ flex: 1 }} onPress={() => setEditing(false)} />
          <Button title="Save" style={{ flex: 1 }} onPress={save} loading={saving} />
        </View>
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      {offline && (
        <Muted style={{ textAlign: 'center', marginBottom: spacing.sm }}>
          ⚠︎ Offline — showing the last saved copy.
        </Muted>
      )}

      <Card style={styles.patientCard}>
        <Text style={styles.patientName}>{p.patient.name ?? 'Patient'}</Text>
        <Text style={styles.diagnosis}>{p.patient.diagnosis ?? ''}</Text>
        <Muted>
          {p.patient.dob ? `DOB ${p.patient.dob}` : ''}
          {p.patient.mrn ? ` · MRN ${p.patient.mrn}` : ''}
        </Muted>
      </Card>

      {p.er_interventions.length > 0 && (
        <>
          <SectionTitle>🚨 For ER staff — interventions</SectionTitle>
          <Card style={styles.erCard}>
            {p.er_interventions.map((line, i) => (
              <Text key={i} selectable style={styles.erLine}>
                {line}
              </Text>
            ))}
          </Card>
        </>
      )}

      {p.contacts.length > 0 && (
        <>
          <SectionTitle>📞 Call (tap to dial)</SectionTitle>
          <Card style={{ paddingVertical: 4 }}>
            {p.contacts.map((c, i) => (
              <Pressable
                key={i}
                style={[styles.contactRow, i > 0 && styles.rowBorder]}
                onPress={() => Linking.openURL(`tel:${c.phone.replace(/[^0-9+]/g, '')}`)}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.contactLabel}>{c.label}</Text>
                  {c.when ? <Muted>{c.when}</Muted> : null}
                </View>
                <Text style={styles.phone}>{c.phone}</Text>
              </Pressable>
            ))}
          </Card>
        </>
      )}

      {p.when_to_call.length > 0 && (
        <>
          <SectionTitle>When to call</SectionTitle>
          <Card>
            {p.when_to_call.map((line, i) => (
              <Text key={i} selectable style={styles.line}>
                • {line}
              </Text>
            ))}
          </Card>
        </>
      )}

      {p.bring_to_er.length > 0 && (
        <>
          <SectionTitle>🎒 Bring to the ER</SectionTitle>
          <Card>
            {p.bring_to_er.map((line, i) => (
              <Text key={i} style={styles.line}>
                ☐ {line}
              </Text>
            ))}
          </Card>
        </>
      )}

      {p.formula_ordering.length > 0 && (
        <>
          <SectionTitle>🥫 Formula ordering</SectionTitle>
          <Card>
            {p.formula_ordering.map((line, i) => (
              <Text key={i} selectable style={styles.line}>
                • {line}
              </Text>
            ))}
          </Card>
        </>
      )}

      {p.notes ? <Muted style={{ marginBottom: spacing.md }}>{p.notes}</Muted> : null}

      <Button title="✏️ Edit card" variant="secondary" onPress={startEdit} />
      <Muted style={{ textAlign: 'center', marginTop: spacing.sm }}>
        Verify against the latest clinic letter after every visit.
      </Muted>
    </ScrollView>
  );
}

function EditList({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string[];
  onChange: (v: string[]) => void;
}) {
  return (
    <View style={{ marginBottom: spacing.md }}>
      <Text style={styles.editLabel}>{label}</Text>
      <TextInput
        multiline
        value={value.join('\n')}
        onChangeText={(t) => onChange(t.split('\n').filter((l) => l.trim()))}
        style={styles.editBox}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  patientCard: { borderColor: colors.danger, backgroundColor: '#FFF9F9' },
  patientName: { fontSize: 20, fontFamily: fonts.heavy, color: colors.text },
  diagnosis: { fontSize: 15, fontFamily: fonts.bold, color: colors.danger, marginVertical: 2 },
  erCard: { borderColor: colors.danger, borderWidth: 2 },
  erLine: { color: colors.text, fontSize: 14, fontFamily: fonts.semibold, marginBottom: 6, lineHeight: 20 },
  line: { color: colors.text, fontSize: 14, fontFamily: fonts.regular, marginBottom: 6, lineHeight: 20 },
  contactRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10 },
  rowBorder: { borderTopWidth: 1, borderTopColor: colors.border },
  contactLabel: { fontFamily: fonts.bold, color: colors.text, fontSize: 14 },
  phone: { color: colors.primary, fontFamily: fonts.heavy, fontSize: 15 },
  editLabel: { fontFamily: fonts.bold, color: colors.text, fontSize: 14, marginBottom: 4 },
  editBox: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    minHeight: 90,
    fontSize: 13,
    fontFamily: fonts.regular,
    color: colors.text,
  },
});
