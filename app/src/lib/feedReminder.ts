import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import { Alert } from 'react-native';

/** Rhythm reminders: remind N hours after the LAST LOGGED anchor (feeds →
 * newest feed, meds → newest medication event).
 *
 * The CONFIG (enabled + interval) is family-shared and lives on the backend,
 * so both parents see the same banners. Each phone schedules its own local
 * notification; only that scheduling state is stored here. */

export type RhythmKind = 'feed' | 'med';

export interface RhythmConfig {
  enabled: boolean;
  interval_hours: number;
}

export interface FamilyRhythms {
  feed: RhythmConfig;
  med: RhythmConfig;
}

export const DEFAULT_RHYTHMS: FamilyRhythms = {
  feed: { enabled: false, interval_hours: 2.5 },
  med: { enabled: false, interval_hours: 8 },
};

const STATE_KEYS: Record<RhythmKind, string> = {
  feed: 'tinyprotocol_feed_rhythm_state',
  med: 'tinyprotocol_med_rhythm_state',
};

const CONTENT: Record<RhythmKind, (h: number) => { title: string; body: string }> = {
  feed: (h) => ({ title: '🍼 Feed time', body: `It's been ${h} h since the last feed.` }),
  med: (h) => ({ title: '💊 Medication time', body: `It's been ${h} h since the last dose.` }),
};

interface ScheduleState {
  notifId?: string | null;
  anchorAt?: string | null;
  anchorInterval?: number | null;
}

async function getState(kind: RhythmKind): Promise<ScheduleState> {
  const raw = await AsyncStorage.getItem(STATE_KEYS[kind]);
  return raw ? JSON.parse(raw) : {};
}

async function setState(kind: RhythmKind, state: ScheduleState) {
  await AsyncStorage.setItem(STATE_KEYS[kind], JSON.stringify(state));
}

export async function ensureNotifPermission(): Promise<boolean> {
  const current = await Notifications.getPermissionsAsync();
  if (current.granted) return true;
  const req = await Notifications.requestPermissionsAsync();
  if (!req.granted) {
    Alert.alert(
      'Notifications are off',
      'Allow notifications for TinyProtocol in iPhone Settings to get reminders.',
    );
    return false;
  }
  return true;
}

/** Reconcile this phone's scheduled notification with the shared config and
 * the latest anchor. Safe to call often — no-ops when nothing changed. */
export async function syncRhythmNotification(
  kind: RhythmKind,
  cfg: RhythmConfig,
  lastAt: string | null,
): Promise<void> {
  const state = await getState(kind);

  if (!cfg.enabled || !lastAt) {
    if (state.notifId) {
      await Notifications.cancelScheduledNotificationAsync(state.notifId).catch(() => {});
      await setState(kind, {});
    }
    return;
  }

  const unchanged =
    state.anchorAt === lastAt && state.anchorInterval === cfg.interval_hours;
  if (unchanged && state.notifId) return;

  if (state.notifId) {
    await Notifications.cancelScheduledNotificationAsync(state.notifId).catch(() => {});
  }

  const targetMs = new Date(lastAt).getTime() + cfg.interval_hours * 3600_000;
  const seconds = Math.round((targetMs - Date.now()) / 1000);
  let notifId: string | null = null;
  if (seconds > 30) {
    notifId = await Notifications.scheduleNotificationAsync({
      content: { ...CONTENT[kind](cfg.interval_hours), sound: true },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
        seconds,
      },
    });
  }
  await setState(kind, {
    notifId,
    anchorAt: lastAt,
    anchorInterval: cfg.interval_hours,
  });
}

/** The next due time implied by a rhythm, for UI display. */
export function nextDue(cfg: RhythmConfig | undefined, lastAt: string | null): Date | null {
  if (!cfg?.enabled || !lastAt) return null;
  return new Date(new Date(lastAt).getTime() + cfg.interval_hours * 3600_000);
}
