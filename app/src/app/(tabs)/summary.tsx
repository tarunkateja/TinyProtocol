import DateTimePicker from '@react-native-community/datetimepicker';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as Clipboard from 'expo-clipboard';
import React, { useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { api } from '../../lib/api';
import { fmtLbOz, fmtNum } from '../../lib/format';
import { useBaby } from '../../lib/hooks';
import { colors, fonts, radius, spacing } from '../../lib/theme';
import type { Summary } from '../../lib/types';
import { Button, Card, Chip, Muted, SectionTitle } from '../../components/ui';

type Window = { label: string; hours?: number; since?: string; custom?: boolean; prompt: string };

const WINDOWS: Window[] = [
  { label: 'Since 8 AM', since: '08:00', prompt: 'covering everything since 8:00 AM today' },
  { label: '12h', hours: 12, prompt: 'covering the last 12 hours' },
  { label: '24h', hours: 24, prompt: 'covering the last 24 hours' },
  { label: '48h', hours: 48, prompt: 'covering the last 48 hours' },
  { label: 'Custom', custom: true, prompt: 'covering the selected time range' },
];

/** Naive local ISO (no timezone) — the backend interprets it in family tz. */
function localIso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:00`;
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function fmtDay(iso: string): string {
  return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric' });
}

type TimelineKind = 'feeds' | 'meds' | 'pumping' | 'events';

const TIMELINE_KINDS: { key: TimelineKind; label: string }[] = [
  { key: 'feeds', label: '🍼 Feeds' },
  { key: 'meds', label: '💊 Meds' },
  { key: 'pumping', label: '🫙 Pumping' },
  { key: 'events', label: '📋 Events' },
];

/** The crisp bullet timeline: time — what happened, only what was asked for.
 *  Multi-part feeds show as one total ("60ml mixed*"); the recipe goes in a
 *  single footnote at the bottom instead of cluttering every bullet. */
function timelineLines(
  s: Summary,
  multiDay: boolean,
  include: Set<TimelineKind>,
): { lines: string[]; footnotes: string[] } {
  const entries: { at: string; text: string }[] = [];
  const footnotes: string[] = [];
  if (include.has('feeds')) {
    for (const f of s.feeds) {
      if (f.description.includes(' + ')) {
        entries.push({ at: f.occurred_at, text: `${fmtNum(f.total_ml)}ml mixed*` });
        const note = `* mixed ${fmtNum(f.total_ml)}ml = ${f.description}`;
        if (!footnotes.includes(note)) footnotes.push(note);
      } else {
        entries.push({ at: f.occurred_at, text: f.description });
      }
    }
  }
  if (include.has('meds')) {
    for (const m of s.meds ?? []) {
      const dose = m.dose_amount
        ? ` ${fmtNum(m.dose_amount)} ${m.dose_unit ?? ''}`.trimEnd()
        : '';
      entries.push({ at: m.occurred_at, text: `💊 ${m.med_name}${dose}` });
    }
  }
  if (include.has('pumping')) {
    for (const p of s.pumpings ?? []) {
      entries.push({ at: p.occurred_at, text: `🫙 pumped ${fmtNum(p.pumped_ml)}ml` });
    }
  }
  if (include.has('events')) {
    for (const w of s.weights ?? []) {
      entries.push({ at: w.occurred_at, text: `⚖️ weight ${fmtLbOz(w.weight_g)}` });
    }
    for (const [label, evs] of [
      ['spit-up', s.spit_ups],
      ['vomit', s.vomits],
      ['fussy', s.fussiness],
    ] as const) {
      for (const e of evs ?? []) {
        entries.push({
          at: e.occurred_at,
          text: `${label}${e.severity ? ` (${e.severity})` : ''}${e.note ? ` — ${e.note}` : ''}`,
        });
      }
    }
    for (const n of s.notes ?? []) {
      entries.push({ at: n.occurred_at, text: `note: ${n.note ?? ''}` });
    }
  }
  entries.sort((a, b) => a.at.localeCompare(b.at));
  return {
    lines: entries.map(
      (e) => `• ${multiDay ? `${fmtDay(e.at)} ` : ''}${fmtTime(e.at)} — ${e.text}`,
    ),
    footnotes,
  };
}

export default function SummaryScreen() {
  const { baby } = useBaby();
  const qc = useQueryClient();
  const [win, setWin] = useState<Window>(WINDOWS[2]); // 24h default
  const [draft, setDraft] = useState<string | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  // Custom range: defaults to this morning 8 AM → now.
  const [fromDt, setFromDt] = useState<Date>(() => {
    const d = new Date();
    d.setHours(8, 0, 0, 0);
    if (d > new Date()) d.setDate(d.getDate() - 1);
    return d;
  });
  const [toDt, setToDt] = useState<Date>(() => new Date());

  const rangeValid = !win.custom || fromDt < toDt;
  const q = useQuery({
    queryKey: [
      'summary',
      baby?.id,
      win.label,
      win.custom ? localIso(fromDt) : '',
      win.custom ? localIso(toDt) : '',
    ],
    queryFn: () =>
      api.rollingSummary(
        baby!.id,
        win.custom
          ? { fromLocal: localIso(fromDt), toLocal: localIso(toDt) }
          : { hours: win.hours, sinceLocalTime: win.since },
      ),
    enabled: !!baby && rangeValid,
    refetchOnMount: 'always',
  });
  const s = q.data;

  // What goes in the shareable timeline — feeds only by default.
  const [include, setInclude] = useState<Set<TimelineKind>>(new Set(['feeds']));
  const toggleKind = (k: TimelineKind) =>
    setInclude((cur) => {
      const next = new Set(cur);
      next.has(k) ? next.delete(k) : next.add(k);
      return next;
    });

  const multiDay = win.custom
    ? fromDt.toDateString() !== toDt.toDateString()
    : (win.hours ?? 0) > 24;
  const { lines, footnotes } = s
    ? timelineLines(s, multiDay, include)
    : { lines: [], footnotes: [] };
  const timelineBody = [...lines, ...(footnotes.length ? ['', ...footnotes] : [])].join('\n');
  const timelineText = s ? `${s.baby_name} — ${s.window_label}\n${timelineBody}` : '';

  const makeDraft = async () => {
    if (!baby || drafting) return;
    setDrafting(true);
    setDraft(null);
    try {
      const range = win.custom
        ? `covering ${localIso(fromDt).replace('T', ' ')} to ${localIso(toDt).replace('T', ' ')} (local time)`
        : win.prompt;
      const resp = await api.createChat(
        baby.id,
        `Draft a concise update for our metabolic team ${range}. Include exact intake numbers, targets, meds, and any spit-ups/vomits.`,
      );
      setDraft(resp.reply);
      qc.invalidateQueries({ queryKey: ['chats'] });
    } catch (e: any) {
      Alert.alert('Could not draft', e.message);
    } finally {
      setDrafting(false);
    }
  };

  const copy = async (text: string, which: string) => {
    await Clipboard.setStringAsync(text);
    setCopied(which);
    setTimeout(() => setCopied(null), 1500);
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
              if (w.custom) setToDt(new Date());
            }}
          />
        ))}
      </View>

      {win.custom && (
        <Card style={{ marginBottom: spacing.sm }}>
          <View style={styles.pickerRow}>
            <Text style={styles.pickerLabel}>From</Text>
            <DateTimePicker
              value={fromDt}
              mode="datetime"
              themeVariant="light"
              textColor={colors.text}
              maximumDate={new Date()}
              onChange={(_, d) => d && setFromDt(d)}
            />
          </View>
          <View style={styles.pickerRow}>
            <Text style={styles.pickerLabel}>To</Text>
            <DateTimePicker
              value={toDt}
              mode="datetime"
              themeVariant="light"
              textColor={colors.text}
              maximumDate={new Date()}
              onChange={(_, d) => d && setToDt(d)}
            />
          </View>
          {!rangeValid && <Muted>"From" must be before "to".</Muted>}
        </Card>
      )}

      <SectionTitle>Timeline{s ? ` (${s.window_label})` : ''}</SectionTitle>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: spacing.xs }}>
        {TIMELINE_KINDS.map((k) => (
          <Chip
            key={k.key}
            label={k.label}
            selected={include.has(k.key)}
            onPress={() => toggleKind(k.key)}
          />
        ))}
      </View>
      <Card style={styles.textCard}>
        {q.isLoading || !rangeValid ? (
          <Muted>{rangeValid ? 'Loading…' : 'Pick a valid range.'}</Muted>
        ) : lines.length === 0 ? (
          <Muted>
            {include.size === 0
              ? 'Pick at least one type above.'
              : 'Nothing logged in this window.'}
          </Muted>
        ) : (
          <Text selectable style={styles.timelineText}>
            {timelineBody}
          </Text>
        )}
      </Card>
      {lines.length > 0 && (
        <View style={{ flexDirection: 'row', gap: spacing.md, marginBottom: spacing.md }}>
          <Button
            title="Share"
            variant="secondary"
            style={{ flex: 1 }}
            onPress={() => Share.share({ message: timelineText })}
          />
          <Button
            title={copied === 'timeline' ? '✓ Copied' : 'Copy'}
            variant="secondary"
            style={{ flex: 1 }}
            onPress={() => copy(timelineText, 'timeline')}
          />
        </View>
      )}

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

      <SectionTitle>Full stats (targets, totals)</SectionTitle>
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
          title={copied === 'raw' ? '✓ Copied' : 'Copy raw stats'}
          variant="secondary"
          style={{ flex: 1 }}
          onPress={() => s && copy(s.summary_text, 'raw')}
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
  timelineText: {
    fontFamily: fonts.regular,
    fontSize: 14.5,
    lineHeight: 24,
    color: colors.text,
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
  pickerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  pickerLabel: {
    fontFamily: fonts.semibold,
    color: colors.muted,
    fontSize: 13,
    width: 44,
  },
});
