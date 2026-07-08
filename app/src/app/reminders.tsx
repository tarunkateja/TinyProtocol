import AsyncStorage from '@react-native-async-storage/async-storage';
import DateTimePicker from '@react-native-community/datetimepicker';
import * as Notifications from 'expo-notifications';
import { useQuery } from '@tanstack/react-query';
import React, { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { api } from '../lib/api';
import {
  FeedRhythm,
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

export default function Reminders() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [dailyTime, setDailyTime] = useState(new Date());
  const [rhythm, setRhythm] = useState<FeedRhythm | null>(null);

  const { baby } = useBaby();
  const timelineQ = useQuery({
    queryKey: ['timeline', baby?.id],
    queryFn: () => api.timeline(baby!.id),
    enabled: !!baby,
  });
  const lastFeedAt =
    timelineQ.data?.items.find((i) => i.item_type === 'FEED')?.occurred_at ?? null;

  useEffect(() => {
    loadReminders().then(setReminders);
    getFeedRhythm().then(setRhythm);
  }, []);

  const updateRhythm = async (patch: Partial<FeedRhythm>) => {
    if (patch.enabled && !(await ensureNotifPermission())) return;
    await setFeedRhythm(patch);
    setRhythm(await syncFeedReminder(lastFeedAt));
  };

  const due = rhythm ? nextFeedDue(rhythm, lastFeedAt) : null;

  const persist = async (list: Reminder[]) => {
    setReminders(list);
    await saveReminders(list);
  };

  const addOneOff = async (hours: number) => {
    if (!(await ensureNotifPermission())) return;
    const notifId = await Notifications.scheduleNotificationAsync({
      content: {
        title: '🍼 Feed time',
        body: `It's been ${hours} hours since you set this reminder.`,
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
        label: `Once at ${at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} (in ${hours}h)`,
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
      <Card>
        <View style={styles.rhythmRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.rhythmTitle}>Remind after every feed</Text>
            <Muted>
              Counts from the LAST LOGGED FEED — log a feed and the reminder moves
              automatically (fed at 12:00 with 2.5 h → 2:30; fed at 3:00 → 5:30).
            </Muted>
          </View>
          <Switch
            value={rhythm?.enabled ?? false}
            onValueChange={(v) => updateRhythm({ enabled: v })}
          />
        </View>
        {rhythm?.enabled && (
          <>
            <Text style={[styles.rhythmTitle, { marginTop: spacing.md }]}>Every… (hours)</Text>
            <Stepper
              value={rhythm.intervalHours}
              onChange={(v) => updateRhythm({ intervalHours: Math.max(0.5, v) })}
              step={0.5}
              suffix="h"
            />
            <Muted style={{ marginTop: spacing.sm }}>
              {due
                ? `Next: ${due.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} (based on the last feed)`
                : 'Log a feed to start the clock.'}
            </Muted>
          </>
        )}
      </Card>

      <SectionTitle>Remind me once</SectionTitle>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {[2, 2.5, 3, 4].map((h) => (
          <Pressable key={h} style={styles.chip} onPress={() => addOneOff(h)}>
            <Text style={styles.chipText}>In {h}h</Text>
          </Pressable>
        ))}
      </View>

      <SectionTitle>Every day at…</SectionTitle>
      <Card>
        <DateTimePicker
          value={dailyTime}
          mode="time"
          display="spinner"
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
  chipText: { color: colors.text, fontFamily: fonts.bold, fontSize: 14 },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
  },
  rowText: { color: colors.text, fontFamily: fonts.semibold, fontSize: 14, flex: 1 },
});
