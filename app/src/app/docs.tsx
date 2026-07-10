import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as ImagePicker from 'expo-image-picker';
import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { api } from '../lib/api';
import { fmtNum } from '../lib/format';
import { colors, fonts, radius, spacing } from '../lib/theme';
import type { CareDoc } from '../lib/types';
import { Button, Card, Field, Muted, SectionTitle } from '../components/ui';

const STATUS_META: Record<string, { label: string; color: string }> = {
  uploaded: { label: 'Uploaded', color: colors.muted },
  processing: { label: 'AI reading…', color: colors.primary },
  ready: { label: '✓ Processed', color: colors.success },
  error: { label: 'Failed — tap to retry', color: colors.danger },
};

export default function Docs() {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const docsQ = useQuery({ queryKey: ['docs'], queryFn: api.listDocs });
  const anyProcessing = docsQ.data?.some(
    (d) => d.status === 'processing' || d.status === 'uploaded',
  );

  // Poll while anything is processing.
  useEffect(() => {
    if (!anyProcessing) return;
    const iv = setInterval(() => qc.invalidateQueries({ queryKey: ['docs'] }), 3000);
    return () => clearInterval(iv);
  }, [anyProcessing]);

  const upload = async (uri: string, filename: string, contentType: string) => {
    setBusy(true);
    try {
      const created = await api.createDoc({ filename, content_type: contentType });
      const result = await FileSystem.uploadAsync(created.upload_url, uri, {
        httpMethod: 'PUT',
        headers: { 'Content-Type': created.upload_content_type },
      });
      if (result.status !== 200) throw new Error(`Upload failed (${result.status})`);
      await api.processDoc(created.doc.id);
      qc.invalidateQueries({ queryKey: ['docs'] });
    } catch (e: any) {
      Alert.alert('Upload failed', e.message);
    } finally {
      setBusy(false);
    }
  };

  const fromCamera = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return;
    const res = await ImagePicker.launchCameraAsync({ quality: 0.8 });
    if (res.canceled || !res.assets[0]) return;
    const a = res.assets[0];
    await upload(a.uri, a.fileName ?? `photo-${Date.now()}.jpg`, a.mimeType ?? 'image/jpeg');
  };

  const fromLibrary = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ quality: 0.8 });
    if (res.canceled || !res.assets[0]) return;
    const a = res.assets[0];
    await upload(a.uri, a.fileName ?? `photo-${Date.now()}.jpg`, a.mimeType ?? 'image/jpeg');
  };

  const fromFiles = async () => {
    const res = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/*'],
      copyToCacheDirectory: true,
    });
    if (res.canceled || !res.assets[0]) return;
    const a = res.assets[0];
    await upload(a.uri, a.name, a.mimeType ?? 'application/pdf');
  };

  const retry = async (doc: CareDoc) => {
    try {
      await api.processDoc(doc.id);
      qc.invalidateQueries({ queryKey: ['docs'] });
    } catch (e: any) {
      Alert.alert('Could not retry', e.message);
    }
  };

  const removeDoc = (doc: CareDoc) => {
    Alert.alert(`Delete "${doc.title}"?`, 'Removes the file and its extracted info.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          await api.deleteDoc(doc.id);
          qc.invalidateQueries({ queryKey: ['docs'] });
        },
      },
    ]);
  };

  const openOriginal = async (doc: CareDoc) => {
    const { url } = await api.docDownloadUrl(doc.id);
    Linking.openURL(url);
  };

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      <Muted style={{ marginBottom: spacing.sm }}>
        Upload clinic handouts, letters, and lab reports — AI extracts the key info.
        Lab values it finds wait for your review: you pick which ones to track.
      </Muted>
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md }}>
        <Button title="📷 Camera" variant="secondary" style={{ flex: 1 }} onPress={fromCamera} />
        <Button title="🖼 Photos" variant="secondary" style={{ flex: 1 }} onPress={fromLibrary} />
        <Button title="📄 Files" variant="secondary" style={{ flex: 1 }} onPress={fromFiles} />
      </View>
      {busy && (
        <View style={{ alignItems: 'center', marginBottom: spacing.md }}>
          <ActivityIndicator color={colors.primary} />
          <Muted>Uploading…</Muted>
        </View>
      )}

      <SectionTitle>Documents</SectionTitle>
      {(docsQ.data ?? []).length === 0 && (
        <Muted>{docsQ.isLoading ? 'Loading…' : 'Nothing uploaded yet.'}</Muted>
      )}
      {(docsQ.data ?? []).map((doc) => {
        const meta = STATUS_META[doc.status];
        const open = openId === doc.id;
        return (
          <Pressable
            key={doc.id}
            onPress={() =>
              doc.status === 'error' ? retry(doc) : setOpenId(open ? null : doc.id)
            }
            onLongPress={() => removeDoc(doc)}
          >
            <Card style={{ marginBottom: spacing.sm }}>
              <View style={styles.rowTop}>
                <Text style={styles.title} numberOfLines={open ? undefined : 1}>
                  {doc.title}
                </Text>
                <Text style={[styles.status, { color: meta.color }]}>{meta.label}</Text>
              </View>
              {doc.status === 'processing' && <ActivityIndicator size="small" color={colors.primary} style={{ alignSelf: 'flex-start', marginTop: 4 }} />}
              {doc.status === 'error' && doc.error ? <Muted>{doc.error}</Muted> : null}
              {open && doc.status === 'ready' && (
                <View style={{ marginTop: spacing.sm }}>
                  {(doc.extracted?.lab_results?.length ?? 0) > 0 && (
                    <LabReview doc={doc} />
                  )}
                  {doc.summary ? (
                    <Text selectable style={styles.summary}>
                      {doc.summary}
                    </Text>
                  ) : null}
                  {(doc.extracted?.key_facts?.length ?? 0) > 0 && (
                    <>
                      <Text style={styles.subhead}>Key facts</Text>
                      {doc.extracted!.key_facts.map((f, i) => (
                        <Text key={i} selectable style={styles.fact}>
                          • {f}
                        </Text>
                      ))}
                    </>
                  )}
                  {(doc.extracted?.contacts?.length ?? 0) > 0 && (
                    <>
                      <Text style={styles.subhead}>Contacts found</Text>
                      {doc.extracted!.contacts.map((c, i) => (
                        <Pressable
                          key={i}
                          onPress={() => Linking.openURL(`tel:${c.phone.replace(/[^0-9+]/g, '')}`)}
                        >
                          <Text style={styles.contact}>
                            {c.label}: {c.phone}
                            {c.when ? ` (${c.when})` : ''}
                          </Text>
                        </Pressable>
                      ))}
                    </>
                  )}
                  <Pressable onPress={() => openOriginal(doc)}>
                    <Text style={styles.link}>📎 Open original</Text>
                  </Pressable>
                </View>
              )}
            </Card>
          </Pressable>
        );
      })}
      <Muted style={{ textAlign: 'center', marginTop: spacing.sm }}>
        Tap a document for its extracted info · long-press to delete.
      </Muted>
    </ScrollView>
  );
}

/** Extracted lab values wait here for review: the parent picks which to
 *  track and confirms the test date (required when the document didn't
 *  show one) — nothing is logged automatically. */
function LabReview({ doc }: { doc: CareDoc }) {
  const qc = useQueryClient();
  const rows = doc.extracted?.lab_results ?? [];
  const extractedDate = rows.find((r) => r.collected_date)?.collected_date ?? '';
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [date, setDate] = useState(extractedDate);
  const [saving, setSaving] = useState(false);

  const labsQ = useQuery({ queryKey: ['labs'], queryFn: api.listLabs });
  const logged = new Set(
    (labsQ.data ?? [])
      .filter((l) => l.source_doc_id === doc.id)
      .map((l) => `${l.analyte}|${l.value}`),
  );

  const toggle = (i: number) => {
    const next = new Set(selected);
    next.has(i) ? next.delete(i) : next.add(i);
    setSelected(next);
  };

  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(date.trim());
  const addSelected = async () => {
    if (!validDate || selected.size === 0) return;
    setSaving(true);
    try {
      for (const i of selected) {
        const r = rows[i];
        await api.createLab({
          analyte: r.analyte,
          value: r.value,
          unit: r.unit,
          collected_date: date.trim(),
          source_doc_id: doc.id,
        });
      }
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ['labs'] });
    } catch (e: any) {
      Alert.alert('Could not save', e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.labReview}>
      <Text style={styles.subhead}>🧪 Lab values found — pick what to track</Text>
      <Muted style={{ marginBottom: 6 }}>
        Nothing is logged automatically. Tap the values you want in Labs.
      </Muted>
      {rows.map((r, i) => {
        const isLogged = logged.has(`${r.analyte}|${r.value}`);
        const isSelected = selected.has(i);
        return (
          <Pressable key={i} onPress={() => !isLogged && toggle(i)} disabled={isLogged}>
            <View style={[styles.labRow, isSelected && styles.labRowSelected]}>
              <Text style={styles.labCheck}>{isLogged ? '✓' : isSelected ? '☑' : '☐'}</Text>
              <Text style={[styles.labName, isLogged && styles.labLogged]}>
                {r.analyte.replace(/_/g, ' ')}
              </Text>
              <Text style={[styles.labValue, isLogged && styles.labLogged]}>
                {fmtNum(r.value)} {r.unit}
                {isLogged ? '  · in Labs' : ''}
              </Text>
            </View>
          </Pressable>
        );
      })}
      {selected.size > 0 && (
        <>
          {!extractedDate && (
            <Text style={styles.dateWarn}>
              ⚠️ The test date wasn't visible in this document — enter it below.
            </Text>
          )}
          <Field
            label="Test date (YYYY-MM-DD)"
            value={date}
            onChangeText={setDate}
            placeholder="2026-07-01"
          />
          <Button
            title={saving ? 'Saving…' : `Add ${selected.size} to Labs`}
            onPress={addSelected}
            disabled={!validDate || saving}
          />
          {!validDate && date.trim().length > 0 && (
            <Muted style={{ marginTop: 4 }}>Date must be YYYY-MM-DD.</Muted>
          )}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  rowTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  title: { fontFamily: fonts.bold, color: colors.text, fontSize: 15, flex: 1 },
  status: { fontFamily: fonts.bold, fontSize: 12 },
  labReview: {
    backgroundColor: '#F2F7F4',
    borderRadius: radius.sm,
    padding: spacing.sm,
    marginBottom: spacing.sm,
  },
  labRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 7,
    paddingHorizontal: 6,
    borderRadius: radius.sm,
  },
  labRowSelected: { backgroundColor: '#E3F2E9' },
  labCheck: { fontSize: 16, color: colors.success, width: 22, textAlign: 'center' },
  labName: { flex: 1, fontFamily: fonts.semibold, color: colors.text, fontSize: 13.5 },
  labValue: { fontFamily: fonts.bold, color: colors.text, fontSize: 13.5 },
  labLogged: { color: colors.muted },
  dateWarn: {
    color: colors.danger,
    fontFamily: fonts.semibold,
    fontSize: 13,
    marginTop: spacing.sm,
    marginBottom: 4,
  },
  summary: { color: colors.text, fontSize: 14, lineHeight: 21, fontFamily: fonts.regular },
  subhead: { fontFamily: fonts.heavy, color: colors.text, fontSize: 13, marginTop: spacing.sm, marginBottom: 4 },
  fact: { color: colors.text, fontSize: 13, lineHeight: 19, fontFamily: fonts.regular },
  contact: { color: colors.primary, fontFamily: fonts.semibold, fontSize: 13, marginBottom: 2 },
  link: { color: colors.primary, fontFamily: fonts.bold, fontSize: 14, marginTop: spacing.sm },
});
