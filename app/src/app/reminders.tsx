import AsyncStorage from '@react-native-async-storage/async-storage';
import DateTimePicker from '@react-native-community/datetimepicker';
import * as Notifications from 'expo-notifications';
import { useQuery } from '@tanstack/react-query';
import React, { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { api } from '../lib/api';
import {
  FeedRhythm,
  RhythmKind,
  ensureNotifPermission,
  getFeedRhythm,
  nextFeedDue,
  setFeedRhythm,
  syncFeedReminder,
} from '../lib/feedReminder';
import { useBaby } from '../lib/hooks';
import { colors, fonts, radius, spacing } from '../lib/theme';
import { Button, Card, Muted, SectionTitle, Stepper } from '../components/ui';

interface Reminder {
  notifId: string;
  label: string;
  kind: 'once' | 'daily';
}

const STORE_KEY = 'tinyprotocol_reminders';

async function loadReminders(): Promise<Reminder[]> {
  const raw = await AsyncStorage.getItem(STORE_KEY);
  return raw ? JSON.parse(raw) : [];
}

async function saveReminders(list: Reminder[]) {
  await AsyncStorage.setItem(STORE_KEY, JSON.stringify(list));
}

export function fmtInterval(hours: number): string {
  const h = Math.floor(hours);
  const m = Math.round((hours % 1) * 60);
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

export default function Reminders() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [dailyTime, setDailyTime] = useState(new Date());
  const [rhythm, setRhythm] = useState<FeedRhythm | null>(null);
  const [medRhythm, setMedRhythm] = useState<FeedRhythm | null>(null);
  const [onceH, setOnceH] = useState(2);
  const [onceM, setOnceM] = useState(30);

  const { baby } = useBaby();
  const timelineQ = useQuery({
    queryKey: ['timeline', baby?.id],
    queryFn: () => api.timeline(baby!.id),
    enabled: !!baby,
  });
  const lastFeedAt =
    timelineQ.data?.items.find((i) => i.item_type === 'FEED')?.occurred_at ?? null;
  const lastMedAt =
    timelineQ.data?.items.find(
      (i) => i.item_type === 'EVENT' && i.type === 'medication',
    )?.occurred_at ?? null;

  useEffect(() => {
    loadReminders().then(setReminders);
    getFeedRhythm('feed').then(setRhythm);
    getFeedRhythm('med').then(setMedRhythm);
  }, []);

  const updateRhythm = async (
    patch: Partial<FeedRhythm>,
    kind: RhythmKind = 'feed',
  ) => {
    if (patch.enabled && !(await ensureNotifPermission())) return;
    await setFeedRhythm(patch, kind);
    const next = await syncFeedReminder(kind === 'feed' ? lastFeedAt : lastMedAt, kind);
    (kind === 'feed' ? setRhythm : setMedRhythm)(next);
  };

  const due = rhythm ? nextFeedDue(rhythm, lastFeedAt) : null;
  const medDue = medRhythm ? nextFeedDue(medRhythm, lastMedAt) : null;

  const persist = async (list: Reminder[]) => {
    setReminders(list);
    await saveReminders(list);
  };

  const addOneOff = async (hours: number) => {
    if (!(await ensureNotifPermission())) return;
    const notifId = await Notifications.scheduleNotificationAsync({
      content: {
        title: '🍼 Feed time',
        body: `You asked to be reminded ${fmtInterval(hours)} ago.`,
        sound: true,
      },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
        seconds: hours * 3600,
      },
    });
    const at = new Date(Date.now() + hours * 3600_000);
    await persist([
      ...reminders,
      {
        notifId,
        kind: 'once',
        label: `Once at ${at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} (in ${fmtInterval(hours)})`,
      },
    ]);
  };

  const addDaily = async () => {
    if (!(await ensureNotifPermission())) return;
    const hour = dailyTime.getHours();
    const minute = dailyTime.getMinutes();
    const notifId = await Notifications.scheduleNotificationAsync({
      content: { title: '🍼 Feed time', body: 'Time for the next feed.', sound: true },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.DAILY,
        hour,
        minute,
      },
    });
    const label = `Daily at ${dailyTime.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
    await persist([...reminders, { notifId, kind: 'daily', label }]);
  };

  const remove = async (r: Reminder) => {
    await Notifications.cancelScheduledNotificationAsync(r.notifId).catch(() => {});
    await persist(reminders.filter((x) => x.notifId !== r.notifId));
  };

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}
    >
      <Muted style={{ marginBottom: spacing.sm }}>
        Reminders fire on this phone only (even with the app closed). Your partner sets
        their own on their phone.
      </Muted>

      <SectionTitle>Feed rhythm (auto-reschedules)</SectionTitle>
      <RhythmCard
        title="Remind after every feed"
        desc="Counts from the LAST LOGGED FEED — log a feed and the reminder moves automatically."
        rhythm={rhythm}
        due={due}
        lastAt={lastFeedAt}
        chips={[2, 2.5, 3, 3.5, 4]}
        onUpdate={(patch) => updateRhythm(patch, 'feed')}
        emptyHint="Log a feed to start the clock."
      />

      <SectionTitle>Medication rhythm (auto-reschedules)</SectionTitle>
      <RhythmCard
        title="Remind after every dose"
        desc="Counts from the LAST LOGGED MEDICATION — e.g. dose at 11:30 PM with 8 h → reminder at 7:30 AM; log the next dose and it moves again."
        rhythm={medRhythm}
        due={medDue}
        lastAt={lastMedAt}
        chips={[4, 6, 8, 12]}
        onUpdate={(patch) => updateRhythm(patch, 'med')}
        emptyHint="Log a medication event to start the clock."
      />

      <SectionTitle>Remind me once</SectionTitle>
      <Card>
        <View style={{ flexDirection: 'row', gap: spacing.md }}>
          <View style={{ flex: 1 }}>
            <Muted style={{ marginBottom: 4 }}>hours</Muted>
            <Stepper value={onceH} onChange={(v) => setOnceH(Math.max(0, v))} step={1} suffix="h" />
          </View>
          <View style={{ flex: 1 }}>
            <Muted style={{ marginBottom: 4 }}>minutes</Muted>
            <Stepper
              value={onceM}
              onChange={(v) => setOnceM(Math.min(55, Math.max(0, v)))}
              step={5}
              suffix="m"
            />
          </View>
        </View>
        <Button
          title={`⏰ Remind me in ${fmtInterval(onceH + onceM / 60)}`}
          onPress={() => addOneOff(onceH + onceM / 60)}
          disabled={onceH + onceM / 60 <= 0}
          style={{ marginTop: spacing.sm }}
        />
      </Card>

      <SectionTitle>Every day at…</SectionTitle>
      <Card>
        <DateTimePicker
          value={dailyTime}
          mode="time"
          display="spinner"
          themeVariant="light"
          textColor={colors.text}
          onChange={(_, d) => d && setDailyTime(d)}
        />
        <Button title="Add daily reminder" onPress={addDaily} />
      </Card>

      <SectionTitle>Scheduled</SectionTitle>
      {reminders.length === 0 ? (
        <Muted>No reminders yet.</Muted>
      ) : (
        <Card style={{ paddingVertical: 4 }}>
          {reminders.map((r, i) => (
            <View
              key={r.notifId}
              style={[styles.row, i > 0 && { borderTopWidth: 1, borderTopColor: colors.border }]}
            >
              <Text style={styles.rowText}>
                {r.kind === 'daily' ? '🔁' : '⏰'} {r.label}
              </Text>
              <Pressable onPress={() => remove(r)}>
                <Text style={{ color: colors.danger, fontFamily: fonts.bold }}>Remove</Text>
              </Pressable>
            </View>
          ))}
        </Card>
      )}
    </ScrollView>
  );
}

function RhythmCard({
  title,
  desc,
  rhythm,
  due,
  lastAt,
  chips,
  onUpdate,
  emptyHint,
}: {
  title: string;
  desc: string;
  rhythm: FeedRhythm | null;
  due: Date | null;
  lastAt: string | null;
  chips: number[];
  onUpdate: (patch: Partial<FeedRhythm>) => void;
  emptyHint: string;
}) {
  return (
    <Card>
      <View style={styles.rhythmRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.rhythmTitle}>{title}</Text>
          <Muted>{desc}</Muted>
        </View>
        <Switch
          value={rhythm?.enabled ?? false}
          onValueChange={(v) => onUpdate({ enabled: v })}
        />
      </View>
      {rhythm?.enabled && (
        <>
          <Text style={[styles.rhythmTitle, { marginTop: spacing.md }]}>
            Remind every {fmtInterval(rhythm.intervalHours)}
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginTop: 4 }}>
            {chips.map((h) => (
              <Pressable
                key={h}
                style={[styles.chip, rhythm.intervalHours === h && styles.chipActive]}
                onPress={() => onUpdate({ intervalHours: h })}
              >
                <Text style={[styles.chipText, rhythm.intervalHours === h && { color: '#fff' }]}>
                  {fmtInterval(h)}
                </Text>
              </Pressable>
            ))}
          </View>
          <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.xs }}>
            <View style={{ flex: 1 }}>
              <Muted style={{ marginBottom: 4 }}>hours</Muted>
              <Stepper
                value={Math.floor(rhythm.intervalHours)}
                onChange={(h) =>
                  onUpdate({
                    intervalHours: Math.max(
                      0.25,
                      Math.max(0, h) + (Math.round((rhythm.intervalHours % 1) * 60) % 60) / 60,
                    ),
                  })
                }
                step={1}
                suffix="h"
              />
            </View>
            <View style={{ flex: 1 }}>
              <Muted style={{ marginBottom: 4 }}>minutes</Muted>
              <Stepper
                value={Math.round((rhythm.intervalHours % 1) * 60)}
                onChange={(m) =>
                  onUpdate({
                    intervalHours: Math.max(
                      0.25,
                      Math.floor(rhythm.intervalHours) + Math.min(55, Math.max(0, m)) / 60,
                    ),
                  })
                }
                step={5}
                suffix="m"
              />
            </View>
          </View>
          <Muted style={{ marginTop: spacing.sm }}>
            {due && lastAt
              ? `Next: ${due.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} (from the last log — moves automatically)`
              : emptyHint}
          </Muted>
        </>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  rhythmRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  rhythmTitle: { fontFamily: fonts.bold, color: colors.text, fontSize: 15, marginBottom: 2 },
  chip: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.pill,
    paddingHorizontal: 16,
    paddingVertical: 10,
    marginRight: spacing.sm,
    marginBottom: spacing.sm,
  },
  chipActive: { backgroundColor: colors.primary },
  chipText: { color: colors.text, fontFamily: fonts.bold, fontSize: 14 },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
  },
  rowText: { color: colors.text, fontFamily: fonts.semibold, fontSize: 14, flex: 1 },
});
