import { useQuery } from '@tanstack/react-query';
import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { api } from '../../lib/api';
import { effectiveDayString, fmtNum, fmtTime } from '../../lib/format';
import {
  FeedRhythm,
  nextFeedDue,
  syncFeedReminder,
} from '../../lib/feedReminder';
import { useBaby, useFamily, useInvalidateLogs } from '../../lib/hooks';
import { colors, eventTheme, fonts, radius, spacing } from '../../lib/theme';
import type { CareEvent, Feed, TimelineEntry } from '../../lib/types';
import { Button, Card, Field, Muted } from '../../components/ui';

export default function Today() {
  const router = useRouter();
  const { baby, isLoading } = useBaby();
  const { family } = useFamily();
  const invalidate = useInvalidateLogs();

  const today = effectiveDayString(family?.day_start ?? '00:00');
  const dayQ = useQuery({
    queryKey: ['day', baby?.id, today],
    queryFn: () => api.daySummary(baby!.id, today),
    enabled: !!baby,
  });
  const timelineQ = useQuery({
    queryKey: ['timeline', baby?.id],
    queryFn: () => api.timeline(baby!.id),
    enabled: !!baby,
  });

  const lastFeedAt = useMemo(() => {
    const feed = timelineQ.data?.items.find((i) => i.item_type === 'FEED');
    return feed?.occurred_at ?? null;
  }, [timelineQ.data]);

  const [rhythm, setRhythm] = useState<FeedRhythm | null>(null);
  const [, setTick] = useState(0);

  // Re-anchor the reminder to the newest feed; also re-runs on screen focus
  // (e.g. after changing the rhythm in Reminders).
  useFocusEffect(
    useCallback(() => {
      syncFeedReminder(lastFeedAt).then(setRhythm);
    }, [lastFeedAt]),
  );

  // Minute tick so the countdown stays fresh.
  useEffect(() => {
    const iv = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(iv);
  }, []);

  if (!baby && !isLoading) return <NoBaby />;
  if (!baby) return null;

  const s = dayQ.data;
  const due = rhythm ? nextFeedDue(rhythm, lastFeedAt) : null;

  const confirmDelete = (entry: TimelineEntry) => {
    const isFeed = entry.item_type === 'FEED';
    Alert.alert(`Delete this ${isFeed ? 'feed' : 'entry'}?`, 'This cannot be undone.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          await (isFeed ? api.deleteFeed(entry.id) : api.deleteEvent(entry.id));
          invalidate();
        },
      },
    ]);
  };

  return (
    <View style={{ flex: 1 }}>
      <FlatList
        data={timelineQ.data?.items ?? []}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120 }}
        refreshControl={
          <RefreshControl
            refreshing={timelineQ.isRefetching}
            onRefresh={() => {
              timelineQ.refetch();
              dayQ.refetch();
            }}
          />
        }
        ListHeaderComponent={
          <>
            {rhythm && !rhythm.enabled && (
              <Pressable onPress={() => router.push('/reminders')}>
                <View style={styles.rhythmSetup}>
                  <Text style={styles.rhythmSetupText}>
                    ⏰ Set a feed reminder (auto-repeats after each feed)
                  </Text>
                </View>
              </Pressable>
            )}
            {due && (
              <Pressable onPress={() => router.push('/reminders')}>
                <View
                  style={[
                    styles.rhythmBanner,
                    due.getTime() < Date.now() && styles.rhythmOverdue,
                  ]}
                >
                  <Text style={styles.rhythmText}>
                    {due.getTime() < Date.now()
                      ? `🍼 Feed due — ${fmtCountdown(Date.now() - due.getTime())} overdue`
                      : `⏰ Next feed ≈ ${due.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} · in ${fmtCountdown(due.getTime() - Date.now())}`}
                  </Text>
                  <Muted>every {rhythm!.intervalHours} h · tap to adjust</Muted>
                </View>
              </Pressable>
            )}
            <View style={styles.statsRow}>
            <Stat label="fed today" value={`${fmtNum(s?.total_ml)} ml`} />
            <Stat
              label="breast milk"
              value={`${fmtNum(s?.breast_milk.total_ml)} ml`}
              color={eventTheme.feed.color}
            />
            <Stat
              label="lysine"
              value={`${fmtNum(s?.lysine_mg)} mg`}
              sub={
                s?.targets.lysine_mg_per_day
                  ? `of ${fmtNum(s.targets.lysine_mg_per_day)}`
                  : undefined
              }
              color={colors.metabolic}
            />
            </View>
          </>
        }
        ListEmptyComponent={
          <Muted style={{ textAlign: 'center', marginTop: 40 }}>
            {timelineQ.isLoading ? 'Loading…' : 'No feeds or events logged yet.'}
          </Muted>
        }
        renderItem={({ item }) =>
          item.item_type === 'FEED' ? (
            <FeedRow
              feed={item}
              onPress={() => router.push({ pathname: '/log-feed', params: { feedId: item.id } })}
              onLongPress={() => confirmDelete(item)}
            />
          ) : (
            <EventRow
              event={item}
              onPress={() => router.push({ pathname: '/log-event', params: { eventId: item.id } })}
              onLongPress={() => confirmDelete(item)}
            />
          )
        }
      />
      <View style={styles.fabRow}>
        <Button title="＋ Feed" onPress={() => router.push('/log-feed')} style={{ flex: 1 }} />
        <Button
          title="＋ Event"
          onPress={() => router.push('/log-event')}
          variant="secondary"
          style={{ flex: 1 }}
        />
      </View>
    </View>
  );
}

function fmtCountdown(ms: number): string {
  const mins = Math.max(1, Math.round(ms / 60000));
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, '0')}m`;
}

function Stat({
  label,
  value,
  sub,
  color = colors.primary,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
}) {
  return (
    <View style={styles.stat}>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
      <Muted>{sub ? `${label} ${sub}` : label}</Muted>
    </View>
  );
}

function EntryCard({
  theme,
  title,
  time,
  onPress,
  onLongPress,
  children,
}: {
  theme: { color: string; soft: string; icon: string };
  title: string;
  time: string;
  onPress: () => void;
  onLongPress: () => void;
  children?: React.ReactNode;
}) {
  return (
    <Pressable onPress={onPress} onLongPress={onLongPress}>
      <View style={[styles.entry, { borderLeftColor: theme.color }]}>
        <View style={[styles.iconChip, { backgroundColor: theme.soft }]}>
          <Text style={{ fontSize: 17 }}>{theme.icon}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <View style={styles.rowTop}>
            <Text style={[styles.rowTitle, { color: theme.color }]}>{title}</Text>
            <Muted>{time}</Muted>
          </View>
          {children}
        </View>
      </View>
    </Pressable>
  );
}

function FeedRow({
  feed,
  onPress,
  onLongPress,
}: {
  feed: Feed;
  onPress: () => void;
  onLongPress: () => void;
}) {
  const desc = feed.components
    .map((c) => {
      if (c.kind === 'liquid') return `${fmtNum(c.volume_ml)}ml ${c.food_name}`;
      if (c.kind === 'powder') return `${fmtNum(c.scoops)} scoop ${c.food_name}`;
      return `${fmtNum(c.minutes)}min latch (${c.is_estimated ? '≈' : ''}${fmtNum(c.effective_ml)}ml)`;
    })
    .join(' + ');
  return (
    <EntryCard
      theme={eventTheme.feed}
      title={`${fmtNum(feed.totals.total_ml)} ml feed`}
      time={fmtTime(feed.occurred_at)}
      onPress={onPress}
      onLongPress={onLongPress}
    >
      <Text style={styles.rowDesc}>{desc}</Text>
      {feed.totals.lysine_mg > 0 && (
        <Muted style={{ marginTop: 2 }}>
          {fmtNum(feed.totals.natural_protein_g, 2)} g protein · {fmtNum(feed.totals.lysine_mg)} mg lysine
        </Muted>
      )}
      {feed.notes ? <Muted style={{ marginTop: 2 }}>{feed.notes}</Muted> : null}
    </EntryCard>
  );
}

function EventRow({
  event,
  onPress,
  onLongPress,
}: {
  event: CareEvent;
  onPress: () => void;
  onLongPress: () => void;
}) {
  const theme = eventTheme[event.type] ?? eventTheme.note;
  let title = theme.label;
  const bits: string[] = [];
  if (event.type === 'pumping') {
    title = `Pumped ${fmtNum(event.pumped_ml)} ml`;
    if (event.side) bits.push(event.side);
    if (event.duration_minutes) bits.push(`${fmtNum(event.duration_minutes)} min`);
  } else if (event.type === 'diaper') {
    title = `Diaper — ${event.diaper_kind === 'both' ? 'pee + poop' : event.diaper_kind}`;
  } else {
    if (event.severity) bits.push(event.severity);
    if (event.med_name) bits.push(event.med_name);
    if (event.dose_amount) bits.push(`${fmtNum(event.dose_amount)} ${event.dose_unit ?? ''}`);
  }
  if (event.note) bits.push(event.note);
  return (
    <EntryCard
      theme={theme}
      title={title}
      time={fmtTime(event.occurred_at)}
      onPress={onPress}
      onLongPress={onLongPress}
    >
      {bits.length > 0 && <Text style={styles.rowDesc}>{bits.join(' · ')}</Text>}
    </EntryCard>
  );
}

function NoBaby() {
  const [name, setName] = useState('');
  const invalidate = useInvalidateLogs();
  const { refetch } = useBaby();
  return (
    <View style={{ padding: spacing.xl }}>
      <Card>
        <Text style={styles.rowTitle}>Add your baby</Text>
        <Muted style={{ marginBottom: spacing.md }}>
          One quick step before you can start logging.
        </Muted>
        <Field label="Baby's name" value={name} onChangeText={setName} />
        <Button
          title="Add baby"
          disabled={!name.trim()}
          onPress={async () => {
            await api.createBaby({ name: name.trim() });
            invalidate();
            refetch();
          }}
        />
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  rhythmBanner: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.primary,
    padding: spacing.md,
    marginBottom: spacing.sm,
    alignItems: 'center',
  },
  rhythmOverdue: {
    backgroundColor: '#FAE3E5',
    borderColor: colors.danger,
  },
  rhythmText: { fontFamily: fonts.heavy, fontSize: 15, color: colors.text, marginBottom: 2 },
  rhythmSetup: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderStyle: 'dashed',
    padding: spacing.md,
    marginBottom: spacing.sm,
    alignItems: 'center',
  },
  rhythmSetupText: { fontFamily: fonts.semibold, fontSize: 14, color: colors.muted },
  statsRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  stat: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    alignItems: 'center',
  },
  statValue: { fontSize: 17, fontFamily: fonts.heavy },
  entry: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderLeftWidth: 4,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  iconChip: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  rowTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  rowTitle: { fontSize: 15, fontFamily: fonts.heavy, color: colors.text },
  rowDesc: { color: colors.text, marginTop: 2, fontSize: 14, fontFamily: fonts.regular },
  fabRow: {
    position: 'absolute',
    bottom: spacing.lg,
    left: spacing.lg,
    right: spacing.lg,
    flexDirection: 'row',
    gap: spacing.md,
  },
});
