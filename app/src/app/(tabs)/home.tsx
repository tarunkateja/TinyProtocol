import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../../lib/api';
import { DEFAULT_RHYTHMS } from '../../lib/feedReminder';
import { addDays, effectiveDayString, fmtKg, fmtLbOz, fmtNum, localDateString } from '../../lib/format';
import { useBaby, useFamily } from '../../lib/hooks';
import { colors, eventTheme, fonts, radius, spacing } from '../../lib/theme';
import { Button, Card, Muted } from '../../components/ui';
import type { Summary } from '../../lib/types';

/** "3d 4h" / "45m" / "2h 10m" from milliseconds. */
function fmtSince(ms: number | null): string {
  if (ms == null) return '—';
  const mins = Math.max(0, Math.round(ms / 60000));
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ${mins % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

function fmtClock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export default function Home() {
  const router = useRouter();
  const { baby } = useBaby();
  const { family } = useFamily();
  const dayStart = family?.day_start ?? '00:00';
  const today = effectiveDayString(dayStart);
  const [, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 60_000);
    return () => clearInterval(t);
  }, []);

  const dayQ = useQuery({
    queryKey: ['day', baby?.id, today],
    queryFn: () => api.daySummary(baby!.id, today),
    enabled: !!baby,
    refetchInterval: 5 * 60_000,
  });
  const latestQ = useQuery({
    queryKey: ['timeline-latest', baby?.id],
    queryFn: () => api.timeline(baby!.id, {}),
    enabled: !!baby,
    refetchInterval: 5 * 60_000,
  });
  const poopQ = useQuery({
    queryKey: ['diaperHistory', baby?.id, addDays(today, -6), today],
    queryFn: () => api.diaperHistory(baby!.id, addDays(today, -6), today),
    enabled: !!baby,
    refetchInterval: 5 * 60_000,
  });
  const weightQ = useQuery({
    queryKey: ['weightHistory', baby?.id],
    queryFn: () => api.weightHistory(baby!.id),
    enabled: !!baby,
  });
  const recipeQ = useQuery({
    queryKey: ['recipe-current', baby?.id],
    queryFn: () => api.currentRecipe(baby!.id),
    enabled: !!baby,
  });
  const hbQ = useQuery({
    queryKey: ['hb-status', baby?.id],
    queryFn: () => api.hbStatus(baby!.id),
    enabled: !!baby,
    refetchInterval: 5 * 60_000,
  });

  const s: Summary | undefined = dayQ.data;
  const lastFeed = latestQ.data?.items.find((i) => i.item_type === 'FEED');
  const lastFeedMs = lastFeed ? Date.now() - new Date(lastFeed.occurred_at).getTime() : null;
  const feedInterval = (family?.rhythms ?? DEFAULT_RHYTHMS).feed.interval_hours;
  const nextFeedAt = lastFeed
    ? new Date(new Date(lastFeed.occurred_at).getTime() + feedInterval * 3600_000)
    : null;

  const poop = poopQ.data;
  const sincePoopH = poop?.hours_since_last_poop ?? null;
  const poopColor =
    sincePoopH == null ? colors.text : sincePoopH >= 72 ? colors.danger : sincePoopH >= 48 ? '#D97706' : colors.text;

  const weight = useMemo(() => {
    const w = weightQ.data?.weights ?? [];
    const latest = w[w.length - 1];
    const prev = w[w.length - 2];
    if (!latest) return null;
    const gPerDay =
      prev && new Date(latest.occurred_at) > new Date(prev.occurred_at)
        ? (latest.weight_g - prev.weight_g) /
          ((new Date(latest.occurred_at).getTime() - new Date(prev.occurred_at).getTime()) / 86400000)
        : null;
    return { g: latest.weight_g, at: latest.occurred_at, gPerDay };
  }, [weightQ.data]);

  const recipe = recipeQ.data;
  const pending = hbQ.data?.connected ? hbQ.data.pending_count : 0;

  const vol = (cat: string) => s?.volume_targets.find((v) => v.category === cat);
  const bm = vol('breast_milk');
  const ga1 = vol('metabolic_formula');
  const lysineTarget = s?.targets.lysine_mg_per_day ?? null;

  if (!baby) return null;

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}>
      {pending > 0 && (
        <Pressable style={styles.banner} onPress={() => router.push('/huckleberry')}>
          <Text style={styles.bannerText}>
            🫐 {pending} Huckleberry {pending === 1 ? 'entry' : 'entries'} to review
          </Text>
          <Text style={styles.bannerArrow}>›</Text>
        </Pressable>
      )}

      <Pressable onPress={() => router.push('/totals')}>
        <Card>
          <View style={styles.rowBetween}>
            <Text style={styles.cardTitle}>Today</Text>
            <Muted>
              since {dayStart.replace(/^0/, '')} · {s?.feed_count ?? 0} {s?.feed_count === 1 ? 'feed' : 'feeds'}
            </Muted>
          </View>
          <TargetRow
            label="Breast milk"
            value={s?.breast_milk.total_ml ?? 0}
            target={bm?.target_ml}
            direction={bm?.direction}
            color={colors.breastMilk}
          />
          <TargetRow
            label="GA1 formula"
            value={s?.metabolic_formula_ml ?? 0}
            target={ga1?.target_ml}
            direction={ga1?.direction}
            color={colors.metabolic}
          />
          <TargetRow
            label="Lysine"
            value={s?.lysine_mg ?? 0}
            target={lysineTarget ?? undefined}
            unit="mg"
            color={colors.primary}
          />
          <View style={[styles.rowBetween, { marginTop: 4 }]}>
            <Muted>{fmtNum(s?.total_ml ?? 0)} ml total</Muted>
            <Text style={styles.link}>Day totals ›</Text>
          </View>
        </Card>
      </Pressable>

      <View style={styles.tiles}>
        <Tile
          label="Last feed"
          value={fmtSince(lastFeedMs)}
          color={eventTheme.feed.color}
          sub={
            lastFeed
              ? `${fmtClock(lastFeed.occurred_at)}, ${fmtNum(lastFeed.totals?.total_ml ?? 0)}ml\nnext ≈ ${nextFeedAt ? fmtClock(nextFeedAt.toISOString()) : '—'}`
              : 'no feeds yet'
          }
          onPress={() => router.push('/')}
        />
        <Tile
          label="Last poop"
          value={sincePoopH == null ? '—' : fmtSince(sincePoopH * 3600_000)}
          color={poopColor}
          sub={
            poop?.last_poop_at
              ? `${new Date(poop.last_poop_at).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })}\navg gap ${poop.avg_gap_hours != null ? fmtSince(poop.avg_gap_hours * 3600_000) : '—'}`
              : 'none on record'
          }
          onPress={() => router.push('/(tabs)/trends')}
        />
        <Tile
          label="Weight"
          value={weight ? fmtKg(weight.g) : '—'}
          color={eventTheme.weight.color}
          sub={
            weight
              ? `${fmtLbOz(weight.g)}\n${weight.gPerDay != null ? `${weight.gPerDay >= 0 ? '+' : '−'}${fmtNum(Math.abs(weight.gPerDay), 0)} g/day` : localDateString(new Date(weight.at))}`
              : 'log a weight'
          }
          onPress={() => router.push({ pathname: '/log-event', params: { type: 'weight' } })}
        />
      </View>

      <Pressable onPress={() => router.push('/plan')}>
        <Card style={{ paddingVertical: spacing.md }}>
          <View style={styles.rowBetween}>
            <View style={{ flex: 1 }}>
              <Muted>Plan in effect</Muted>
              {recipe ? (
                <>
                  <Text style={styles.planLine}>
                    {fmtNum(recipe.breast_milk_ml)} bm + {fmtNum(recipe.batch_ml)} batch = {fmtNum(recipe.prepared_ml)} ml per feed
                  </Text>
                  <Muted>
                    {recipe.powders.map((p) => `${fmtNum(p.grams)} g ${p.name}`).join(' + ')}
                    {recipe.batch_final_volume_ml ? ` → ${fmtNum(recipe.batch_final_volume_ml)} ml` : ''}
                  </Muted>
                </>
              ) : (
                <Text style={styles.planLine}>No recipe yet — add the team's plan</Text>
              )}
            </View>
            <Text style={styles.bannerArrow}>›</Text>
          </View>
        </Card>
      </Pressable>

      <View style={styles.actions}>
        <Button title="🍼 Log feed" onPress={() => router.push('/log-feed')} style={{ flex: 1 }} />
        <Button
          title="📋 Dietitian update"
          variant="secondary"
          onPress={() => router.push('/summary')}
          style={{ flex: 1 }}
        />
      </View>
    </ScrollView>
  );
}

function TargetRow({
  label,
  value,
  target,
  direction,
  unit = 'ml',
  color,
}: {
  label: string;
  value: number;
  target?: number;
  direction?: 'min' | 'max';
  unit?: string;
  color: string;
}) {
  const pct = target ? Math.min(1, value / target) : 0;
  const over = !!target && direction === 'max' && value > target;
  return (
    <View style={{ marginTop: spacing.sm }}>
      <View style={styles.rowBetween}>
        <Text style={styles.rowLabel}>{label}</Text>
        <Muted>
          {fmtNum(value)}
          {target ? ` / ${direction ? `${direction} ` : ''}${fmtNum(target)}` : ''} {unit}
        </Muted>
      </View>
      <View style={styles.barTrack}>
        <View style={[styles.barFill, { width: `${Math.round(pct * 100)}%`, backgroundColor: over ? colors.danger : color }]} />
      </View>
    </View>
  );
}

function Tile({
  label,
  value,
  sub,
  color,
  onPress,
}: {
  label: string;
  value: string;
  sub: string;
  color: string;
  onPress: () => void;
}) {
  return (
    <Pressable style={styles.tile} onPress={onPress}>
      <Muted style={{ fontSize: 12 }}>{label}</Muted>
      <Text style={[styles.tileValue, { color }]} numberOfLines={1} adjustsFontSizeToFit>
        {value}
      </Text>
      <Muted style={{ fontSize: 12 }}>{sub}</Muted>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.primarySoft,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    marginBottom: spacing.md,
    minHeight: 44,
  },
  bannerText: { fontFamily: fonts.bold, fontSize: 14, color: colors.primary },
  bannerArrow: { fontSize: 20, fontFamily: fonts.bold, color: colors.muted },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  cardTitle: { fontSize: 18, fontFamily: fonts.heavy, color: colors.text },
  rowLabel: { fontSize: 14, fontFamily: fonts.semibold, color: colors.text },
  link: { fontSize: 13, fontFamily: fonts.bold, color: colors.primary },
  barTrack: { height: 12, borderRadius: 6, backgroundColor: colors.border, overflow: 'hidden', marginTop: 4 },
  barFill: { height: 12, borderRadius: 6 },
  tiles: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
  tile: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    minHeight: 96,
    gap: 2,
  },
  tileValue: { fontSize: 20, fontFamily: fonts.heavy },
  planLine: { fontSize: 15, fontFamily: fonts.bold, color: colors.text },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs },
});
