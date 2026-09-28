import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Clipboard from 'expo-clipboard';
import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, Share, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import { showAlert } from '../lib/dialogs';
import { useBaby, useFamily } from '../lib/hooks';
import { colors, fonts, radius, spacing } from '../lib/theme';
import { Button, Card, Chip, Field, Muted, SectionTitle } from '../components/ui';

/**
 * The dietitian update: the exact feeding-log message the family pastes into
 * MyChart. The backend renders it (one section per family day, one bullet
 * per feed, one total per day, this morning so far); this screen only adds
 * the greeting and the share/copy buttons. Anything that needs a look in the
 * log before sending shows up as a warning above the text.
 */

const DAY_OPTIONS = [1, 2, 3, 5, 7];
const GREETING_KEY = 'tinyprotocol_dietitian_greeting';
const DEFAULT_GREETING = 'Hi Madison,';

function fmtHour(hhmm: string): string {
  const [h, m] = hhmm.split(':').map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return d.toLocaleTimeString([], { hour: 'numeric', minute: m ? '2-digit' : undefined });
}

export default function SummaryScreen() {
  const { baby } = useBaby();
  const { family } = useFamily();
  const qc = useQueryClient();
  const [days, setDays] = useState(3);
  const [withNotes, setWithNotes] = useState(true);
  const [greeting, setGreeting] = useState(DEFAULT_GREETING);
  const [copied, setCopied] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncNote, setSyncNote] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(GREETING_KEY)
      .then((v) => v !== null && setGreeting(v))
      .catch(() => {});
  }, []);
  const changeGreeting = (v: string) => {
    setGreeting(v);
    AsyncStorage.setItem(GREETING_KEY, v).catch(() => {});
  };

  const q = useQuery({
    queryKey: ['dietitian-report', baby?.id, days, withNotes],
    queryFn: () => api.dietitianReport(baby!.id, days, withNotes),
    enabled: !!baby,
    refetchOnMount: 'always',
  });
  const report = q.data;

  const hb = useQuery({
    queryKey: ['hb-status', baby?.id],
    queryFn: () => api.hbStatus(baby!.id),
    enabled: !!baby,
  });

  const raw = useQuery({
    queryKey: ['summary', baby?.id, `${days}d`],
    queryFn: () => api.rollingSummary(baby!.id, { hours: days * 24 }),
    enabled: !!baby,
  });

  const message = [greeting.trim(), report?.text ?? ''].filter(Boolean).join('\n\n');
  const dayStart = family?.day_start ? fmtHour(family.day_start) : '8 AM';

  const copy = async (text: string, which: string) => {
    await Clipboard.setStringAsync(text);
    setCopied(which);
    setTimeout(() => setCopied(null), 1500);
  };

  const syncNow = async () => {
    if (!baby || syncing) return;
    setSyncing(true);
    setSyncNote(null);
    try {
      const r = await api.hbSyncNow(baby.id);
      const bits = [];
      if (r.auto_imported) bits.push(`${r.auto_imported} imported`);
      if (r.new_pending) bits.push(`${r.new_pending} to review`);
      if (r.updated) bits.push(`${r.updated} updated`);
      setSyncNote(bits.length ? `Synced · ${bits.join(' · ')}` : 'Synced · nothing new');
      qc.invalidateQueries({ queryKey: ['dietitian-report'] });
      qc.invalidateQueries({ queryKey: ['hb-status'] });
      qc.invalidateQueries({ queryKey: ['summary'] });
    } catch (e: any) {
      showAlert('Sync failed', e.message);
    } finally {
      setSyncing(false);
    }
  };

  const makeDraft = async () => {
    if (!baby || drafting) return;
    setDrafting(true);
    setDraft(null);
    try {
      const resp = await api.createChat(
        baby.id,
        `Draft a concise update for our metabolic team covering the last ${days} full day${days === 1 ? '' : 's'} and today so far. Include exact intake numbers, targets, meds, and any spit-ups/vomits.`,
      );
      setDraft(resp.reply);
      qc.invalidateQueries({ queryKey: ['chats'] });
    } catch (e: any) {
      showAlert('Could not draft', e.message);
    } finally {
      setDrafting(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: spacing.xs }}>
        {DAY_OPTIONS.map((n) => (
          <Chip
            key={n}
            label={n === 1 ? 'Last day' : `Last ${n} days`}
            selected={days === n}
            onPress={() => setDays(n)}
          />
        ))}
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', marginBottom: spacing.md }}>
        <Chip label="📝 Notes" selected={withNotes} onPress={() => setWithNotes(!withNotes)} />
        <Muted>Full days run {dayStart} → {dayStart}, then today so far.</Muted>
      </View>

      {hb.data?.connected && (
        <View style={styles.syncRow}>
          <Button
            title={syncing ? 'Syncing…' : '🫐 Sync Huckleberry first'}
            variant="secondary"
            loading={syncing}
            onPress={syncNow}
            style={{ flex: 1 }}
          />
          {syncNote ? <Muted style={{ marginLeft: spacing.sm }}>{syncNote}</Muted> : null}
        </View>
      )}

      {report && report.warnings.length > 0 && (
        <Card style={styles.warnCard}>
          <Text style={styles.warnTitle}>Check the log before sending</Text>
          {report.warnings.map((w, i) => (
            <Text key={i} style={styles.warnText}>
              • {w.message}
            </Text>
          ))}
        </Card>
      )}

      <Field
        label="Greeting"
        value={greeting}
        onChangeText={changeGreeting}
        placeholder="Hi Madison,"
        autoCapitalize="sentences"
      />

      <Card style={styles.textCard}>
        {q.isLoading ? (
          <Muted>Loading…</Muted>
        ) : q.isError ? (
          <Muted>Could not load: {(q.error as Error).message}</Muted>
        ) : (
          <Text selectable style={styles.messageText}>
            {message}
          </Text>
        )}
      </Card>
      {report && (
        <View style={{ flexDirection: 'row', gap: spacing.md, marginBottom: spacing.lg }}>
          <Button title="Share" style={{ flex: 1 }} onPress={() => Share.share({ message })} />
          <Button
            title={copied === 'message' ? '✓ Copied' : 'Copy'}
            variant="secondary"
            style={{ flex: 1 }}
            onPress={() => copy(message, 'message')}
          />
        </View>
      )}

      <SectionTitle>More</SectionTitle>
      <Button
        title={drafting ? 'Drafting…' : '✨ Draft a longer update with AI'}
        variant="secondary"
        onPress={makeDraft}
        loading={drafting}
      />
      <Muted style={{ textAlign: 'center', marginTop: spacing.xs, marginBottom: spacing.sm }}>
        Targets, meds, symptoms · saved in Ask history too
      </Muted>
      {draft && (
        <Card style={styles.draftCard}>
          <Text selectable style={styles.messageText}>
            {draft}
          </Text>
          <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.md }}>
            <Button title="Share" style={{ flex: 1 }} onPress={() => Share.share({ message: draft })} />
            <Button
              title={copied === 'draft' ? '✓ Copied' : 'Copy'}
              variant="secondary"
              style={{ flex: 1 }}
              onPress={() => copy(draft, 'draft')}
            />
          </View>
          <Muted style={{ marginTop: spacing.sm, textAlign: 'center' }}>
            Review the numbers before sending — AI can make mistakes.
          </Muted>
        </Card>
      )}

      <Pressable onPress={() => setShowRaw(!showRaw)} style={{ marginTop: spacing.md }}>
        <Card style={styles.textCard}>
          <Text style={styles.rawTitle}>
            Full stats · last {days * 24}h {showRaw ? '▴' : '▾'}
          </Text>
          {showRaw && (
            <Text selectable style={styles.rawText}>
              {raw.isLoading ? 'Loading…' : raw.data?.summary_text || 'Nothing logged in this window.'}
            </Text>
          )}
        </Card>
      </Pressable>
      {showRaw && raw.data && (
        <View style={{ flexDirection: 'row', gap: spacing.md }}>
          <Button
            title="Share stats"
            variant="secondary"
            style={{ flex: 1 }}
            onPress={() => Share.share({ message: raw.data!.summary_text })}
          />
          <Button
            title={copied === 'raw' ? '✓ Copied' : 'Copy stats'}
            variant="secondary"
            style={{ flex: 1 }}
            onPress={() => copy(raw.data!.summary_text, 'raw')}
          />
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  syncRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  warnCard: {
    backgroundColor: colors.metabolicSoft,
    borderColor: colors.metabolic,
    marginBottom: spacing.md,
  },
  warnTitle: {
    fontFamily: fonts.bold,
    fontSize: 14,
    color: colors.text,
    marginBottom: spacing.xs,
  },
  warnText: {
    fontFamily: fonts.regular,
    fontSize: 13.5,
    lineHeight: 20,
    color: colors.text,
  },
  textCard: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    marginBottom: spacing.md,
  },
  draftCard: {
    backgroundColor: colors.card,
    borderColor: colors.primary,
    marginTop: spacing.sm,
  },
  messageText: {
    fontFamily: fonts.regular,
    fontSize: 15,
    lineHeight: 23,
    color: colors.text,
  },
  rawTitle: {
    fontFamily: fonts.semibold,
    fontSize: 14,
    color: colors.muted,
  },
  rawText: {
    fontFamily: 'Menlo',
    fontSize: 13,
    lineHeight: 20,
    color: colors.text,
    marginTop: spacing.sm,
  },
});
