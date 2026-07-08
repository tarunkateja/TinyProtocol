import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import { Alert } from 'react-native';

/** "Feed rhythm": remind N hours after the LAST LOGGED FEED. Every time a
 * feed is logged, the pending reminder is cancelled and rescheduled from the
 * new feed's time — phone-local, like all reminders. */

const KEY = 'tinyprotocol_feed_rhythm';

export interface FeedRhythm {
  enabled: boolean;
  intervalHours: number;
  notifId?: string | null;
  // What the current notification was scheduled from — used to skip
  // rescheduling when nothing changed.
  anchorFeedAt?: string | null;
  anchorInterval?: number | null;
}

const DEFAULTS: FeedRhythm = { enabled: false, intervalHours: 2.5 };

export async function getFeedRhythm(): Promise<FeedRhythm> {
  const raw = await AsyncStorage.getItem(KEY);
  return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : { ...DEFAULTS };
}

export async function setFeedRhythm(patch: Partial<FeedRhythm>): Promise<FeedRhythm> {
  const cfg = { ...(await getFeedRhythm()), ...patch };
  await AsyncStorage.setItem(KEY, JSON.stringify(cfg));
  return cfg;
}

export async function ensureNotifPermission(): Promise<boolean> {
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

/** Reconcile the scheduled notification with the latest feed. Safe to call
 * often — it no-ops when nothing changed. Returns the current config. */
export async function syncFeedReminder(lastFeedAt: string | null): Promise<FeedRhythm> {
  const cfg = await getFeedRhythm();

  if (!cfg.enabled || !lastFeedAt) {
    if (cfg.notifId) {
      await Notifications.cancelScheduledNotificationAsync(cfg.notifId).catch(() => {});
      return setFeedRhythm({ notifId: null, anchorFeedAt: null, anchorInterval: null });
    }
    return cfg;
  }

  const unchanged =
    cfg.anchorFeedAt === lastFeedAt && cfg.anchorInterval === cfg.intervalHours;
  if (unchanged && cfg.notifId) return cfg;

  if (cfg.notifId) {
    await Notifications.cancelScheduledNotificationAsync(cfg.notifId).catch(() => {});
  }

  const targetMs = new Date(lastFeedAt).getTime() + cfg.intervalHours * 3600_000;
  const seconds = Math.round((targetMs - Date.now()) / 1000);
  let notifId: string | null = null;
  if (seconds > 30) {
    notifId = await Notifications.scheduleNotificationAsync({
      content: {
        title: '🍼 Feed time',
        body: `It's been ${cfg.intervalHours} h since the last feed.`,
        sound: true,
      },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
        seconds,
      },
    });
  }
  return setFeedRhythm({
    notifId,
    anchorFeedAt: lastFeedAt,
    anchorInterval: cfg.intervalHours,
  });
}

/** The next due time implied by the rhythm, for UI display. */
export function nextFeedDue(cfg: FeedRhythm, lastFeedAt: string | null): Date | null {
  if (!cfg.enabled || !lastFeedAt) return null;
  return new Date(new Date(lastFeedAt).getTime() + cfg.intervalHours * 3600_000);
}
