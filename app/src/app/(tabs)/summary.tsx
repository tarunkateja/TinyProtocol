import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Clipboard from 'expo-clipboard';
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { api } from '../../lib/api';
import { useBaby } from '../../lib/hooks';
import { colors, fonts, radius, spacing } from '../../lib/theme';
import { Button, Card, Chip, Muted, SectionTitle } from '../../components/ui';

type Window = { label: string; hours?: number; since?: string; prompt: string };

const WINDOWS: Window[] = [
  { label: 'Since 7 AM', since: '07:00', prompt: 'covering everything since 7:00 AM today' },
  { label: 'Since 8 AM', since: '08:00', prompt: 'covering everything since 8:00 AM today' },
  { label: '12h', hours: 12, prompt: 'covering the last 12 hours' },
  { label: '24h', hours: 24, prompt: 'covering the last 24 hours' },
  { label: '48h', hours: 48, prompt: 'covering the last 48 hours' },
];

export default function SummaryScreen() {
  const { baby } = useBaby();
  const qc = useQueryClient();
  const [win, setWin] = useState<Window>(WINDOWS[3]); // 24h default
  const [draft, setDraft] = useState<string | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);

  const q = useQuery({
    queryKey: ['summary', baby?.id, win.label],
    queryFn: () =>
      api.rollingSummary(baby!.id, { hours: win.hours, sinceLocalTime: win.since }),
    enabled: !!baby,
    refetchOnMount: 'always',
  });
  const s = q.data;

  const makeDraft = async () => {
    if (!baby || drafting) return;
    setDrafting(true);
    setDraft(null);
    try {
      const resp = await api.createChat(
        baby.id,
        `Draft a concise update for our metabolic team ${win.prompt}. Include exact intake numbers, targets, meds, and any spit-ups/vomits.`,
      );
      setDraft(resp.reply);
      qc.invalidateQueries({ queryKey: ['chats'] });
    } catch (e: any) {
      Alert.alert('Could not draft', e.message);
    } finally {
      setDrafting(false);
    }
  };

  const copy = async (text: string) => {
    await Clipboard.setStringAsync(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: spacing.sm }}>
        {WINDOWS.map((w) => (
          <Chip
            key={w.label}
            label={w.label}
            selected={win.label === w.label}
            onPress={() => {
              setWin(w);
              setDraft(null);
            }}
          />
        ))}
      </View>

      <Button
        title={drafting ? 'Drafting…' : '✨ Draft update for the care team'}
        onPress={makeDraft}
        loading={drafting}
      />
      <Muted style={{ textAlign: 'center', marginTop: spacing.xs, marginBottom: spacing.sm }}>
        Uses your real logs for the selected window · saved in Ask history too
      </Muted>

      {draft && (
        <Card style={styles.draftCard}>
          <Text selectable style={styles.draftText}>
            {draft}
          </Text>
          <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.md }}>
            <Button title="Share" style={{ flex: 1 }} onPress={() => Share.share({ message: draft })} />
            <Button
              title={copied ? '✓ Copied' : 'Copy'}
              variant="secondary"
              style={{ flex: 1 }}
              onPress={() => copy(draft)}
            />
          </View>
          <Muted style={{ marginTop: spacing.sm, textAlign: 'center' }}>
            Review the numbers before sending — AI can make mistakes.
          </Muted>
        </Card>
      )}

      <SectionTitle>Quick stats ({win.label.toLowerCase()})</SectionTitle>
      <Pressable onPress={() => setShowRaw(!showRaw)}>
        <Card style={styles.textCard}>
          <Text selectable style={styles.summaryText} numberOfLines={showRaw ? undefined : 8}>
            {q.isLoading ? 'Loading…' : s?.summary_text || 'Nothing logged in this window.'}
          </Text>
          {!showRaw && (s?.summary_text?.split('\n').length ?? 0) > 8 && (
            <Text style={styles.moreLink}>Show all ▾</Text>
          )}
        </Card>
      </Pressable>
      <View style={{ flexDirection: 'row', gap: spacing.md }}>
        <Button
          title="Share raw stats"
          variant="secondary"
          style={{ flex: 1 }}
          onPress={() => s && Share.share({ message: s.summary_text })}
        />
        <Button
          title="Copy raw stats"
          variant="secondary"
          style={{ flex: 1 }}
          onPress={() => s && copy(s.summary_text)}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  draftCard: {
    backgroundColor: '#FFFDF9',
    borderColor: colors.primary,
  },
  draftText: {
    fontSize: 15,
    lineHeight: 22,
    color: colors.text,
    fontFamily: fonts.regular,
  },
  textCard: {
    backgroundColor: '#FFFDF9',
    borderRadius: radius.lg,
    marginBottom: spacing.md,
  },
  summaryText: {
    fontFamily: 'Menlo',
    fontSize: 13,
    lineHeight: 20,
    color: colors.text,
  },
  moreLink: {
    color: colors.primary,
    fontFamily: fonts.bold,
    fontSize: 13,
    marginTop: 8,
  },
});
