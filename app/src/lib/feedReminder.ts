import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import { Alert } from 'react-native';

/** Rhythm reminders: remind N hours after the LAST LOGGED anchor — feeds
 * anchor to the newest feed, meds to the newest medication event. Every new
 * log cancels and reschedules the pending notification. Phone-local. */

export type RhythmKind = 'feed' | 'med';

const KEYS: Record<RhythmKind, string> = {
  feed: 'tinyprotocol_feed_rhythm',
  med: 'tinyprotocol_med_rhythm',
};

const CONTENT: Record<RhythmKind, (h: number) => { title: string; body: string }> = {
  feed: (h) => ({ title: '🍼 Feed time', body: `It's been ${h} h since the last feed.` }),
  med: (h) => ({ title: '💊 Medication time', body: `It's been ${h} h since the last dose.` }),
};

export interface FeedRhythm {
  enabled: boolean;
  intervalHours: number;
  notifId?: string | null;
  anchorFeedAt?: string | null;
  anchorInterval?: number | null;
}

const DEFAULTS: Record<RhythmKind, FeedRhythm> = {
  feed: { enabled: false, intervalHours: 2.5 },
  med: { enabled: false, intervalHours: 8 },
};

export async function getFeedRhythm(kind: RhythmKind = 'feed'): Promise<FeedRhythm> {
  const raw = await AsyncStorage.getItem(KEYS[kind]);
  return raw ? { ...DEFAULTS[kind], ...JSON.parse(raw) } : { ...DEFAULTS[kind] };
}

export async function setFeedRhythm(
  patch: Partial<FeedRhythm>,
  kind: RhythmKind = 'feed',
): Promise<FeedRhythm> {
  const cfg = { ...(await getFeedRhythm(kind)), ...patch };
  await AsyncStorage.setItem(KEYS[kind], JSON.stringify(cfg));
  return cfg;
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

/** Reconcile the scheduled notification with the latest anchor. Safe to call
 * often — it no-ops when nothing changed. Returns the current config. */
export async function syncFeedReminder(
  lastAt: string | null,
  kind: RhythmKind = 'feed',
): Promise<FeedRhythm> {
  const cfg = await getFeedRhythm(kind);

  if (!cfg.enabled || !lastAt) {
    if (cfg.notifId) {
      await Notifications.cancelScheduledNotificationAsync(cfg.notifId).catch(() => {});
      return setFeedRhythm({ notifId: null, anchorFeedAt: null, anchorInterval: null }, kind);
    }
    return cfg;
  }

  const unchanged =
    cfg.anchorFeedAt === lastAt && cfg.anchorInterval === cfg.intervalHours;
  if (unchanged && cfg.notifId) return cfg;

  if (cfg.notifId) {
    await Notifications.cancelScheduledNotificationAsync(cfg.notifId).catch(() => {});
  }

  const targetMs = new Date(lastAt).getTime() + cfg.intervalHours * 3600_000;
  const seconds = Math.round((targetMs - Date.now()) / 1000);
  let notifId: string | null = null;
  if (seconds > 30) {
    notifId = await Notifications.scheduleNotificationAsync({
      content: { ...CONTENT[kind](cfg.intervalHours), sound: true },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
        seconds,
      },
    });
  }
  return setFeedRhythm(
    { notifId, anchorFeedAt: lastAt, anchorInterval: cfg.intervalHours },
    kind,
  );
}

/** The next due time implied by the rhythm, for UI display. */
export function nextFeedDue(cfg: FeedRhythm, lastAt: string | null): Date | null {
  if (!cfg.enabled || !lastAt) return null;
  return new Date(new Date(lastAt).getTime() + cfg.intervalHours * 3600_000);
}
