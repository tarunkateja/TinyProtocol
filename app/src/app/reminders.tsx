import AsyncStorage from '@react-native-async-storage/async-storage';
import DateTimePicker from '@react-native-community/datetimepicker';
import * as Notifications from 'expo-notifications';
import React, { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { colors, fonts, radius, spacing } from '../lib/theme';
import { Button, Card, Muted, SectionTitle } from '../components/ui';

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

async function ensurePermission(): Promise<boolean> {
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) return true;
  const req = await Notifications.requestPermissionsAsync();
  if (!req.granted) {
    Alert.alert(
      'Notifications are off',
      'Allow notifications for TinyProtocol in iPhone Settings to get feed reminders.',
    );
    return false;
  }
  return true;
}

export default function Reminders() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [dailyTime, setDailyTime] = useState(new Date());

  useEffect(() => {
    loadReminders().then(setReminders);
  }, []);

  const persist = async (list: Reminder[]) => {
    setReminders(list);
    await saveReminders(list);
  };

  const addOneOff = async (hours: number) => {
    if (!(await ensurePermission())) return;
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
    if (!(await ensurePermission())) return;
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
