import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
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
import { fmtNum, fmtTime, localDateString } from '../../lib/format';
import { useBaby, useInvalidateLogs } from '../../lib/hooks';
import { colors, radius, spacing } from '../../lib/theme';
import type { CareEvent, Feed, TimelineEntry } from '../../lib/types';
import { Button, Card, Field, Muted } from '../../components/ui';

const EVENT_META: Record<string, { icon: string; label: string }> = {
  spit_up: { icon: '💧', label: 'Spit-up' },
  vomit: { icon: '🤮', label: 'Vomit' },
  fussiness: { icon: '😾', label: 'Fussy' },
  medication: { icon: '💊', label: 'Medication' },
  note: { icon: '📝', label: 'Note' },
};

export default function Today() {
  const router = useRouter();
  const { baby, isLoading } = useBaby();
  const invalidate = useInvalidateLogs();

  const today = localDateString();
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

  if (!baby && !isLoading) return <NoBaby />;
  if (!baby) return null;

  const s = dayQ.data;

  const confirmDelete = (entry: TimelineEntry) => {
    const isFeed = entry.item_type === 'FEED';
    Alert.alert(`Delete this ${isFeed ? 'feed' : 'event'}?`, 'This cannot be undone.', [
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
          <View style={styles.statsRow}>
            <Stat label="fed today" value={`${fmtNum(s?.total_ml)} ml`} />
            <Stat
              label="breast milk"
              value={`${fmtNum(s?.breast_milk.total_ml)} ml`}
              color={colors.breastMilk}
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
        }
        ListEmptyComponent={
          <Muted style={{ textAlign: 'center', marginTop: 40 }}>
            {timelineQ.isLoading ? 'Loading…' : 'No feeds or events logged yet.'}
          </Muted>
        }
        renderItem={({ item }) =>
          item.item_type === 'FEED' ? (
            <FeedRow feed={item} onLongPress={() => confirmDelete(item)} />
          ) : (
            <EventRow event={item} onLongPress={() => confirmDelete(item)} />
          )
        }
      />
      <View style={styles.fabRow}>
        <Button
          title="＋ Feed"
          onPress={() => router.push('/log-feed')}
          style={{ flex: 1 }}
        />
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

function FeedRow({ feed, onLongPress }: { feed: Feed; onLongPress: () => void }) {
  const desc = feed.components
    .map((c) => {
      if (c.kind === 'liquid') return `${fmtNum(c.volume_ml)}ml ${c.food_name}`;
      if (c.kind === 'powder') return `${fmtNum(c.scoops)} scoop ${c.food_name}`;
      return `${fmtNum(c.minutes)}min latch (${c.is_estimated ? '≈' : ''}${fmtNum(c.effective_ml)}ml)`;
    })
    .join(' + ');
  return (
    <Pressable onLongPress={onLongPress}>
      <Card style={{ marginBottom: spacing.sm }}>
        <View style={styles.rowTop}>
          <Text style={styles.rowTitle}>🍼 {fmtNum(feed.totals.total_ml)} ml</Text>
          <Muted>{fmtTime(feed.occurred_at)}</Muted>
        </View>
        <Text style={styles.rowDesc}>{desc}</Text>
        {feed.totals.lysine_mg > 0 && (
          <Muted style={{ marginTop: 4 }}>
            {fmtNum(feed.totals.natural_protein_g, 2)} g protein · {fmtNum(feed.totals.lysine_mg)} mg lysine
          </Muted>
        )}
        {feed.notes ? <Muted style={{ marginTop: 4 }}>{feed.notes}</Muted> : null}
      </Card>
    </Pressable>
  );
}

function EventRow({ event, onLongPress }: { event: CareEvent; onLongPress: () => void }) {
  const meta = EVENT_META[event.type] ?? EVENT_META.note;
  const bits = [
    event.severity,
    event.med_name,
    event.dose_amount ? `${fmtNum(event.dose_amount)} ${event.dose_unit ?? ''}` : null,
    event.note,
  ].filter(Boolean);
  return (
    <Pressable onLongPress={onLongPress}>
      <Card style={{ marginBottom: spacing.sm, backgroundColor: colors.eventSoft }}>
        <View style={styles.rowTop}>
          <Text style={styles.rowTitle}>
            {meta.icon} {meta.label}
          </Text>
          <Muted>{fmtTime(event.occurred_at)}</Muted>
        </View>
        {bits.length > 0 && <Text style={styles.rowDesc}>{bits.join(' · ')}</Text>}
      </Card>
    </Pressable>
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
  statValue: { fontSize: 17, fontWeight: '800' },
  rowTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  rowTitle: { fontSize: 16, fontWeight: '700', color: colors.text },
  rowDesc: { color: colors.text, marginTop: 4, fontSize: 14 },
  fabRow: {
    position: 'absolute',
    bottom: spacing.lg,
    left: spacing.lg,
    right: spacing.lg,
    flexDirection: 'row',
    gap: spacing.md,
  },
});
