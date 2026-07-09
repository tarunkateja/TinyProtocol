import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { api } from '../../lib/api';
import { effectiveDayOf, effectiveDayString, fmtDateHeading, fmtNum, fmtTime } from '../../lib/format';
import { DEFAULT_RHYTHMS, nextDue, syncRhythmNotification } from '../../lib/feedReminder';
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
  const timelineQ = useInfiniteQuery({
    queryKey: ['timeline', baby?.id],
    queryFn: ({ pageParam }) => api.timeline(baby!.id, { cursor: pageParam || undefined }),
    initialPageParam: '',
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: !!baby,
  });

  const items = useMemo(
    () => timelineQ.data?.pages.flatMap((p) => p.items) ?? [],
    [timelineQ.data],
  );

  const dayStart = family?.day_start ?? '00:00';

  // Rows = day headers + entries (gaps only within the same day).
  const rows = useMemo(() => {
    const out: Row[] = [];
    let currentDay = '';
    const effToday = effectiveDayString(dayStart);
    items.forEach((item, i) => {
      const day = effectiveDayOf(item.occurred_at, dayStart);
      if (day !== currentDay) {
        currentDay = day;
        out.push({ kind: 'header', key: `h-${day}`, label: fmtDateHeading(day, effToday) });
      }
      const next = items[i + 1];
      const sameDayNext =
        next && effectiveDayOf(next.occurred_at, dayStart) === day ? next : undefined;
      out.push({ kind: 'entry', key: item.id, item, next: sameDayNext });
    });
    return out;
  }, [items, dayStart]);

  const lastFeedAt = useMemo(() => {
    const feed = items.find((i) => i.item_type === 'FEED');
    return feed?.occurred_at ?? null;
  }, [items]);

  const lastMedAt = useMemo(() => {
    const med = items.find((i) => i.item_type === 'EVENT' && i.type === 'medication');
    return med?.occurred_at ?? null;
  }, [items]);

  const rhythms = family?.rhythms ?? DEFAULT_RHYTHMS;
  const [, setTick] = useState(0);

  // Re-anchor this phone's notifications to the newest feed/med using the
  // family-shared config; re-runs on focus (e.g. after Reminders changes).
  useFocusEffect(
    useCallback(() => {
      if (!family) return;
      syncRhythmNotification('feed', rhythms.feed, lastFeedAt);
      syncRhythmNotification('med', rhythms.med, lastMedAt);
    }, [family, rhythms.feed.enabled, rhythms.feed.interval_hours, rhythms.med.enabled, rhythms.med.interval_hours, lastFeedAt, lastMedAt]),
  );

  // Minute tick so the countdown stays fresh.
  useEffect(() => {
    const iv = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(iv);
  }, []);

  if (!baby && !isLoading) return <NoBaby />;
  if (!baby) return null;

  const s = dayQ.data;
  const due = nextDue(rhythms.feed, lastFeedAt);
  const medDue = nextDue(rhythms.med, lastMedAt);
  const bmMax = s?.volume_targets.find(
    (v) => v.category === 'breast_milk' && v.direction === 'max',
  );
  const ga1Min = s?.volume_targets.find(
    (v) => v.category === 'metabolic_formula' && v.direction === 'min',
  );

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
      <Pressable style={styles.sosBtn} onPress={() => router.push('/emergency')} hitSlop={8}>
        <Text style={styles.sosText}>🆘 Emergency</Text>
      </Pressable>
      <FlatList
        data={rows}
        keyExtractor={(row) => row.key}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120 }}
        onEndReached={() => timelineQ.hasNextPage && timelineQ.fetchNextPage()}
        onEndReachedThreshold={0.4}
        ListFooterComponent={
          timelineQ.isFetchingNextPage ? (
            <ActivityIndicator color={colors.primary} style={{ marginVertical: spacing.md }} />
          ) : null
        }
        refreshControl={
          <RefreshControl
            refreshing={timelineQ.isRefetching && !timelineQ.isFetchingNextPage}
            onRefresh={() => {
              timelineQ.refetch();
              dayQ.refetch();
            }}
          />
        }
        ListHeaderComponent={
          <>
            {family && !rhythms.feed.enabled && !rhythms.med.enabled && (
              <Pressable onPress={() => router.push('/reminders')}>
                <View style={styles.rhythmSetup}>
                  <Text style={styles.rhythmSetupText}>
                    ⏰ Set feed & med reminders (auto-repeat after each log)
                  </Text>
                </View>
              </Pressable>
            )}
            {due && (
              <RhythmBanner
                due={due}
                intervalHours={rhythms.feed.interval_hours}
                icon="🍼"
                noun="feed"
                onPress={() => router.push('/reminders')}
              />
            )}
            {medDue && (
              <RhythmBanner
                due={medDue}
                intervalHours={rhythms.med.interval_hours}
                icon="💊"
                noun="dose"
                color={eventTheme.medication.color}
                soft={eventTheme.medication.soft}
                onPress={() => router.push('/reminders')}
              />
            )}
            <View style={styles.statsRow}>
              <Stat label="total milk today" value={`${fmtNum(s?.total_ml)} ml`} />
              <Stat
                label="breast milk"
                value={`${fmtNum(s?.breast_milk.total_ml)} ml`}
                sub={
                  bmMax ? `of ${fmtNum(bmMax.target_ml)} max` : undefined
                }
                color={eventTheme.feed.color}
              />
              <Stat
                label="GA1 formula"
                value={`${fmtNum(s?.metabolic_formula_ml)} ml`}
                sub={ga1Min ? `of ${fmtNum(ga1Min.target_ml)} min` : undefined}
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
        renderItem={({ item: row }) => {
          if (row.kind === 'header') {
            return (
              <View style={styles.dayHeader}>
                <View style={styles.dayHeaderLine} />
                <Text style={styles.dayHeaderText}>{row.label}</Text>
                <View style={styles.dayHeaderLine} />
              </View>
            );
          }
          const { item, next } = row;
          return (
            <>
              {item.item_type === 'FEED' ? (
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
              )}
              {next ? (
                <TimeGap newer={item.occurred_at} older={next.occurred_at} />
              ) : (
                <View style={{ height: spacing.sm }} />
              )}
            </>
          );
        }}
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

type Row =
  | { kind: 'header'; key: string; label: string }
  | { kind: 'entry'; key: string; item: TimelineEntry; next?: TimelineEntry };

/** Visual breathing room between entries, proportional to the elapsed time —
 * a burst of activity reads dense, a long overnight stretch reads long. */
function TimeGap({ newer, older }: { newer: string; older: string }) {
  const mins = Math.max(0, (new Date(newer).getTime() - new Date(older).getTime()) / 60000);
  // 30m ≈ 18px … capped at ~80px for very long gaps.
  const height = Math.min(80, 6 + (mins / 60) * 24);
  return (
    <View style={styles.gapWrap}>
      <View style={[styles.gapLine, { height }]} />
      {mins >= 25 && (
        <Text style={styles.gapLabel}>{fmtCountdown(mins * 60000)} apart</Text>
      )}
    </View>
  );
}

function RhythmBanner({
  due,
  intervalHours,
  icon,
  noun,
  color,
  soft,
  onPress,
}: {
  due: Date;
  intervalHours: number;
  icon: string;
  noun: string;
  color?: string;
  soft?: string;
  onPress: () => void;
}) {
  const overdue = due.getTime() < Date.now();
  return (
    <Pressable onPress={onPress}>
      <View
        style={[
          styles.rhythmBanner,
          soft && color && { backgroundColor: soft, borderColor: color },
          overdue && styles.rhythmOverdue,
        ]}
      >
        <Text style={styles.rhythmText}>
          {overdue
            ? `${icon} ${noun[0].toUpperCase() + noun.slice(1)} due — ${fmtCountdown(Date.now() - due.getTime())} overdue`
            : `${icon} Next ${noun} ≈ ${due.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} · in ${fmtCountdown(due.getTime() - Date.now())}`}
        </Text>
        <Muted>every {intervalHours} h · tap to adjust</Muted>
      </View>
    </Pressable>
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

/** How the feed was given — shown in the heading with a shade variation
 * inside the rose family so kinds are tellable apart at a glance. */
function feedKind(feed: Feed): { label: string; icon: string; color: string } {
  const comps = feed.components;
  if (comps.some((c) => c.kind === 'latch'))
    return { label: 'Latch', icon: '🤱', color: '#A84479' }; // deepest rose
  const cats = new Set(comps.map((c) => c.food_category));
  const hasPowder = comps.some((c) => c.kind === 'powder');
  if (cats.size > 1 || hasPowder)
    return { label: 'Mixed bottle', icon: '🧪', color: '#C75D92' };
  if (cats.has('metabolic_formula'))
    return { label: 'GA1 bottle', icon: '⚗️', color: '#B95FA3' }; // mauve-rose
  if (cats.has('formula'))
    return { label: 'Formula bottle', icon: '🥫', color: '#E08BB5' }; // light rose
  return { label: 'Breast milk bottle', icon: '🍼', color: '#D96A9C' }; // base rose
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
  const kind = feedKind(feed);
  const desc = feed.components
    .map((c) => {
      if (c.kind === 'liquid') return `${fmtNum(c.volume_ml)}ml ${c.food_name}`;
      if (c.kind === 'powder') return `${fmtNum(c.scoops)} scoop ${c.food_name}`;
      return `${fmtNum(c.minutes)}min latch (${c.is_estimated ? '≈' : ''}${fmtNum(c.effective_ml)}ml)`;
    })
    .join(' + ');
  return (
    <EntryCard
      theme={{ color: kind.color, soft: eventTheme.feed.soft, icon: kind.icon }}
      title={`${fmtNum(feed.totals.total_ml)} ml · ${kind.label}`}
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
  } else if (event.type === 'weight') {
    title = `Weight · ${fmtNum((event.weight_g ?? 0) / 1000, 2)} kg`;
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
  sosBtn: {
    alignSelf: 'flex-end',
    marginTop: spacing.sm,
    marginRight: spacing.lg,
    backgroundColor: '#FAE3E5',
    borderWidth: 1,
    borderColor: colors.danger,
    borderRadius: radius.pill,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  sosText: { color: colors.danger, fontFamily: fonts.heavy, fontSize: 13 },
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
  gapWrap: { alignItems: 'center', marginBottom: spacing.sm },
  gapLine: {
    width: 2,
    borderRadius: 1,
    backgroundColor: colors.border,
  },
  gapLabel: {
    position: 'absolute',
    top: '50%',
    marginTop: -8,
    backgroundColor: colors.bg,
    paddingHorizontal: 8,
    color: colors.muted,
    fontFamily: fonts.semibold,
    fontSize: 11,
  },
  dayHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginVertical: spacing.sm,
  },
  dayHeaderLine: { flex: 1, height: 1, backgroundColor: colors.border },
  dayHeaderText: {
    color: colors.text,
    fontFamily: fonts.heavy,
    fontSize: 14,
    backgroundColor: colors.primarySoft,
    borderRadius: radius.pill,
    paddingHorizontal: 14,
    paddingVertical: 5,
    overflow: 'hidden',
  },
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
