import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import { showAlert } from './dialogs';

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
  notifId?: string | null; // legacy single id
  notifIds?: string[];
  anchorAt?: string | null;
  anchorInterval?: number | null;
}

async function cancelAll(state: ScheduleState) {
  for (const id of [state.notifId, ...(state.notifIds ?? [])]) {
    if (id) await Notifications.cancelScheduledNotificationAsync(id).catch(() => {});
  }
}

/** Feeds escalate: prolonged fasting risks catabolism for a GA1 baby. */
const ESCALATIONS: Record<RhythmKind, { afterMin: number; title: string; body: (h: number) => string }[]> = {
  feed: [
    { afterMin: 0, title: '🍼 Feed time', body: (h) => `It's been ${h} h since the last feed.` },
    { afterMin: 20, title: '🍼 Feed overdue — 20 min', body: () => 'No feed logged yet. Time to feed.' },
    {
      afterMin: 40,
      title: '⚠️ Feed 40 min overdue',
      body: () =>
        'Long gaps risk catabolism for a GA1 baby. Feed now — if she refuses feeds, follow your sick-day steps and call the metabolic team.',
    },
  ],
  med: [
    { afterMin: 0, title: '💊 Medication time', body: (h) => `It's been ${h} h since the last dose.` },
  ],
};

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
    showAlert(
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
    if (state.notifId || state.notifIds?.length) {
      await cancelAll(state);
      await setState(kind, {});
    }
    return;
  }

  const unchanged =
    state.anchorAt === lastAt && state.anchorInterval === cfg.interval_hours;
  if (unchanged && (state.notifId || state.notifIds?.length)) return;

  await cancelAll(state);

  const targetMs = new Date(lastAt).getTime() + cfg.interval_hours * 3600_000;
  const notifIds: string[] = [];
  for (const step of ESCALATIONS[kind]) {
    const seconds = Math.round((targetMs + step.afterMin * 60_000 - Date.now()) / 1000);
    if (seconds <= 30) continue;
    notifIds.push(
      await Notifications.scheduleNotificationAsync({
        content: { title: step.title, body: step.body(cfg.interval_hours), sound: true },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
          seconds,
        },
      }),
    );
  }
  await setState(kind, {
    notifIds,
    anchorAt: lastAt,
    anchorInterval: cfg.interval_hours,
  });
}

/** The next due time implied by a rhythm, for UI display. */
export function nextDue(cfg: RhythmConfig | undefined, lastAt: string | null): Date | null {
  if (!cfg?.enabled || !lastAt) return null;
  return new Date(new Date(lastAt).getTime() + cfg.interval_hours * 3600_000);
}
