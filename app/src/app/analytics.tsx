import { useQuery } from '@tanstack/react-query';
import React, { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import {
  addDays,
  effectiveDayString,
  fmtAge,
  fmtDateHeading,
  fmtKg,
  fmtLbOz,
  fmtWeight,
  fmtNum,
  gToOz,
} from '../lib/format';
import { useBaby, useFamily } from '../lib/hooks';
import { colors, eventTheme, fonts, radius, spacing } from '../lib/theme';
import { Card, Chip, Muted, SectionTitle } from '../components/ui';
import type { DailyIntakeDay, DiaperSeries, WeightSeries } from '../lib/types';

const RANGES = [7, 14, 30] as const;
const CHART_HEIGHT = 190;

// Fixed stacking order (bottom → top) so position encodes the source even
// where the hues are close for colorblind readers.
const SERIES = [
  { key: 'breast_milk_ml', label: 'Breast milk', color: colors.breastMilk },
  { key: 'formula_ml', label: 'Formula', color: colors.formula },
  { key: 'metabolic_formula_ml', label: 'GA1 formula', color: colors.metabolic },
  { key: 'other_ml', label: 'Other', color: colors.event },
] as const;

/** Smallest "nice" axis max ≥ the data max, so gridlines land on round numbers. */
function niceMax(max: number): number {
  if (max <= 0) return 100;
  for (const step of [25, 50, 100, 150, 200, 250]) {
    if (max <= step * 4) return step * Math.ceil(max / step);
  }
  return 250 * Math.ceil(max / 250);
}

function fmtShortDay(dateStr: string): string {
  const [, m, d] = dateStr.split('-').map(Number);
  return `${m}/${d}`;
}

export default function Analytics() {
  const { baby } = useBaby();
  const { family } = useFamily();
  const effectiveToday = effectiveDayString(family?.day_start ?? '00:00');
  const [rangeDays, setRangeDays] = useState<(typeof RANGES)[number]>(14);
  const [picked, setPicked] = useState<string | null>(null);

  const from = addDays(effectiveToday, -(rangeDays - 1));
  const q = useQuery({
    queryKey: ['dailyIntake', baby?.id, from, effectiveToday],
    queryFn: () => api.dailyIntake(baby!.id, from, effectiveToday),
    enabled: !!baby,
  });

  const days = q.data?.days ?? [];
  const hasData = days.some((d) => d.feed_count > 0);
  const axisMax = niceMax(Math.max(...days.map((d) => d.total_ml), 0));
  const presentSeries = SERIES.filter((s) => days.some((d) => d[s.key] > 0));
  const lastWithFeeds = [...days].reverse().find((d) => d.feed_count > 0);
  const selected = days.find((d) => d.day === picked) ?? lastWithFeeds ?? days[days.length - 1];

  const avg = useMemo(() => {
    const active = days.filter((d) => d.feed_count > 0);
    if (!active.length) return null;
    return {
      ml: active.reduce((a, d) => a + d.total_ml, 0) / active.length,
      feeds: active.reduce((a, d) => a + d.feed_count, 0) / active.length,
      n: active.length,
    };
  }, [days]);

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
      <View style={styles.chips}>
        {RANGES.map((r) => (
          <Chip
            key={r}
            label={`${r} days`}
            selected={rangeDays === r}
            onPress={() => {
              setRangeDays(r);
              setPicked(null);
            }}
          />
        ))}
      </View>

      <SectionTitle>Daily intake</SectionTitle>
      <Card>
        {q.isLoading ? (
          <ActivityIndicator style={{ height: CHART_HEIGHT }} color={colors.primary} />
        ) : !hasData ? (
          <Muted style={{ paddingVertical: spacing.xl, textAlign: 'center' }}>
            No feeds logged in this range yet.
          </Muted>
        ) : (
          <>
            <View style={styles.plotRow}>
              <View style={styles.yAxis}>
                {[1, 0.75, 0.5, 0.25, 0].map((f) => (
                  <Text key={f} style={styles.yTick}>
                    {Math.round(axisMax * f)}
                  </Text>
                ))}
              </View>
              <View style={styles.plot}>
                {[0.25, 0.5, 0.75, 1].map((f) => (
                  <View key={f} style={[styles.gridline, { bottom: CHART_HEIGHT * f }]} />
                ))}
                <View style={styles.columns}>
                  {days.map((d) => (
                    <Bar
                      key={d.day}
                      day={d}
                      axisMax={axisMax}
                      selected={selected?.day === d.day}
                      onPress={() => setPicked(d.day)}
                    />
                  ))}
                </View>
              </View>
            </View>
            <View style={styles.xLabels}>
              <View style={{ width: 36 }} />
              {days.map((d, i) => {
                // Anchor labels to the last day so "today" is always labeled
                // and never collides with a neighbor.
                const every = Math.ceil(days.length / 7);
                const show = (days.length - 1 - i) % every === 0;
                return (
                  <Text
                    key={d.day}
                    style={[styles.xTick, selected?.day === d.day && styles.xTickSelected]}
                  >
                    {show ? fmtShortDay(d.day) : ''}
                  </Text>
                );
              })}
            </View>
            <View style={styles.legend}>
              {presentSeries.map((s) => (
                <View key={s.key} style={styles.legendItem}>
                  <View style={[styles.legendDot, { backgroundColor: s.color }]} />
                  <Text style={styles.legendText}>{s.label}</Text>
                </View>
              ))}
            </View>
          </>
        )}
      </Card>
      {avg && (
        <Muted style={{ marginTop: spacing.sm }}>
          Average {fmtNum(avg.ml, 0)} ml · {fmtNum(avg.feeds, 1)} feeds per day (over{' '}
          {avg.n} {avg.n === 1 ? 'day' : 'days'} with feeds)
        </Muted>
      )}

      {selected && hasData && (
        <>
          <SectionTitle>{fmtDateHeading(selected.day, effectiveToday)}</SectionTitle>
          <Card>
            <DetailRow label="Total fed" value={`${fmtNum(selected.total_ml)} ml`} bold />
            {SERIES.map((s) =>
              selected[s.key] > 0 || presentSeries.includes(s) ? (
                <DetailRow
                  key={s.key}
                  label={s.label}
                  value={`${fmtNum(selected[s.key])} ml`}
                  color={s.color}
                />
              ) : null,
            )}
            <DetailRow label="Feeds" value={String(selected.feed_count)} />
          </Card>
        </>
      )}

      <Muted style={{ marginTop: spacing.md, marginBottom: spacing.md }}>
        Tap a bar for that day's numbers. Breast milk includes latch estimates. This
        chart only reads the feed log — timestamps are never changed.
      </Muted>

      <SectionTitle>💩 Poop & diapers</SectionTitle>
      <PoopSection babyId={baby?.id} from={from} to={effectiveToday} />

      <SectionTitle>Growth</SectionTitle>
      <GrowthSection babyId={baby?.id} babyName={baby?.name ?? 'baby'} />
    </ScrollView>
  );
}

/** "3d 4h" / "16h" from a number of hours. */
function fmtGap(hours: number | null | undefined): string {
  if (hours == null) return '—';
  const total = Math.round(hours);
  const d = Math.floor(total / 24);
  const h = total % 24;
  return d > 0 ? `${d}d ${h}h` : `${h}h`;
}

function fmtWhen(iso: string): string {
  return new Date(iso).toLocaleString([], {
    weekday: 'short',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

const POOP_COLOR = '#8D6E63';
const POOP_CHART_H = 90;

function PoopSection({ babyId, from, to }: { babyId?: string; from: string; to: string }) {
  const q = useQuery({
    queryKey: ['diaperHistory', babyId, from, to],
    queryFn: () => api.diaperHistory(babyId!, from, to),
    enabled: !!babyId,
  });
  const s: DiaperSeries | undefined = q.data;
  if (q.isLoading || !s) {
    return (
      <Card>
        <ActivityIndicator style={{ height: 60 }} color={colors.primary} />
      </Card>
    );
  }
  const maxPoop = Math.max(1, ...s.days.map((d) => d.poop));
  const poopsNewestFirst = [...s.poops].reverse();
  const sinceLast = s.hours_since_last_poop;
  const sinceLastColor =
    sinceLast == null ? undefined : sinceLast >= 72 ? colors.danger : sinceLast >= 48 ? '#D97706' : undefined;

  return (
    <>
      <Card>
        <View style={styles.growthStats}>
          <GrowthStat label="Since last poop" value={fmtGap(sinceLast)} color={sinceLastColor} />
          <GrowthStat label="Avg between poops" value={fmtGap(s.avg_gap_hours)} />
          <GrowthStat label="Longest gap" value={fmtGap(s.longest_gap_hours)} />
        </View>
        <Muted style={{ marginTop: 4 }}>
          {s.poops.length} {s.poops.length === 1 ? 'poop' : 'poops'} in this range
          {s.last_poop_at ? ` · last ${fmtWhen(s.last_poop_at)}` : ' · no poop on record'}
          {s.longest_gap_ended_at ? ` · longest gap ended ${fmtWhen(s.longest_gap_ended_at)}` : ''}
        </Muted>

        <View style={[styles.columns, { height: POOP_CHART_H, marginTop: spacing.md, alignItems: 'flex-end' }]}>
          {s.days.map((d) => (
            <View key={d.day} style={{ flex: 1, alignItems: 'center', justifyContent: 'flex-end', height: POOP_CHART_H }}>
              {d.poop > 0 ? (
                <Text style={{ fontSize: 10, color: colors.muted, marginBottom: 2 }}>{d.poop}</Text>
              ) : null}
              <View
                style={{
                  width: '60%',
                  height: d.poop > 0 ? Math.max(4, (d.poop / maxPoop) * (POOP_CHART_H - 18)) : 2,
                  backgroundColor: d.poop > 0 ? POOP_COLOR : colors.border,
                  borderRadius: 3,
                }}
              />
            </View>
          ))}
        </View>
        <View style={styles.xLabels}>
          {s.days.map((d, i) => {
            const every = Math.ceil(s.days.length / 7);
            const show = (s.days.length - 1 - i) % every === 0;
            return (
              <Text key={d.day} style={styles.xTick}>
                {show ? fmtShortDay(d.day) : ''}
              </Text>
            );
          })}
        </View>
        <Muted style={{ marginTop: 4 }}>Poops per day · pee changes: {s.days.reduce((a, d) => a + d.pee, 0)} in range</Muted>
      </Card>

      {poopsNewestFirst.length > 0 && (
        <Card style={{ paddingVertical: 4, marginTop: spacing.sm }}>
          {poopsNewestFirst.map((p, i) => (
            <View
              key={p.id}
              style={[styles.detailRow, { flexDirection: 'column', alignItems: 'flex-start' }, i > 0 && { borderTopWidth: 1, borderTopColor: colors.border }]}
            >
              <Text style={{ color: colors.text, fontFamily: fonts.bold }}>
                {fmtWhen(p.occurred_at)}
                <Text style={{ fontFamily: fonts.regular, color: colors.muted }}>
                  {p.gap_hours != null ? `  · after ${fmtGap(p.gap_hours)}` : ''}
                </Text>
              </Text>
              {p.consistency || p.color || p.note ? (
                <Muted>
                  {[p.consistency, p.color, p.note].filter(Boolean).join(' · ')}
                </Muted>
              ) : null}
            </View>
          ))}
        </Card>
      )}
      <Muted style={{ marginTop: spacing.sm, marginBottom: spacing.md }}>
        "After" = time since the previous poop. Consistency and color come from what's logged in
        Huckleberry (or the event here). Ask tab: "how has she been pooping this week?"
      </Muted>
    </>
  );
}

function GrowthSection({ babyId, babyName }: { babyId?: string; babyName: string }) {
  const q = useQuery({
    queryKey: ['weightHistory', babyId],
    queryFn: () => api.weightHistory(babyId!),
    enabled: !!babyId,
  });
  const s = q.data;

  const points = useMemo(() => {
    if (!s) return [];
    const pts = s.weights.map((w) => ({ t: new Date(w.occurred_at).getTime(), g: w.weight_g }));
    if (s.date_of_birth && s.birth_weight_g) {
      const [y, m, d] = s.date_of_birth.split('-').map(Number);
      const birthT = new Date(y, m - 1, d, 12).getTime();
      if (!pts.length || birthT < pts[0].t) pts.unshift({ t: birthT, g: s.birth_weight_g });
    }
    return pts;
  }, [s]);

  const latest = points[points.length - 1];
  const prev = points[points.length - 2];
  const gainOzPerWeek =
    latest && prev && latest.t > prev.t
      ? gToOz(latest.g - prev.g) / ((latest.t - prev.t) / (7 * 86400000))
      : null;
  const gainGPerDay =
    latest && prev && latest.t > prev.t
      ? (latest.g - prev.g) / ((latest.t - prev.t) / 86400000)
      : null;

  return (
    <>
      <Card>
        <View style={styles.growthStats}>
          <GrowthStat
            label="Age"
            value={s?.date_of_birth ? fmtAge(s.date_of_birth) : '—'}
          />
          <GrowthStat
            label="Weight"
            value={latest ? fmtLbOz(latest.g) : '—'}
            color={eventTheme.weight.color}
          />
          <GrowthStat
            label="Gaining"
            value={
              gainOzPerWeek != null
                ? `${gainOzPerWeek >= 0 ? '' : '−'}${fmtNum(Math.abs(gainOzPerWeek), 1)} oz/wk`
                : '—'
            }
          />
        </View>
        {latest ? (
          <Muted style={{ marginTop: 4 }}>
            {fmtKg(latest.g)}
            {gainGPerDay != null
              ? ` · ${gainGPerDay >= 0 ? '+' : '−'}${fmtNum(Math.abs(gainGPerDay), 0)} g/day since the previous weigh-in`
              : ''}
          </Muted>
        ) : null}
        {points.length >= 2 ? (
          <WeightChart points={points} />
        ) : (
          <Muted style={{ marginTop: spacing.sm }}>
            {points.length === 1
              ? 'Log another ⚖️ Weight event to see the curve.'
              : `Log a ⚖️ Weight event (and ${babyName}'s birthday + birth weight in Settings) to chart growth.`}
          </Muted>
        )}
        {!s?.date_of_birth && (
          <Muted style={{ marginTop: spacing.sm }}>
            Set {babyName}'s birthday in Settings to show her age.
          </Muted>
        )}
      </Card>
      <Muted>
        Weights come from ⚖️ Weight events (log one from the + button). Per-kg GA1
        targets always use the newest weight.
      </Muted>
    </>
  );
}

function GrowthStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Muted style={{ fontSize: 12 }}>{label}</Muted>
      <Text style={[styles.growthStatValue, color ? { color } : null]}>{value}</Text>
    </View>
  );
}

const WEIGHT_CHART_H = 150;
const WEIGHT_PAD_TOP = 18; // room for the direct labels above the dots

function WeightChart({ points }: { points: { t: number; g: number }[] }) {
  const [plotW, setPlotW] = useState(0);
  const t0 = points[0].t;
  const t1 = points[points.length - 1].t;
  const gs = points.map((p) => p.g);
  let gMin = Math.min(...gs);
  let gMax = Math.max(...gs);
  const pad = Math.max((gMax - gMin) * 0.15, 100);
  gMin -= pad;
  gMax += pad;

  const usableW = Math.max(plotW - 16, 1); // keep dots off the card edges
  const x = (t: number) => 8 + ((t - t0) / Math.max(t1 - t0, 1)) * usableW;
  const y = (g: number) =>
    WEIGHT_PAD_TOP + (1 - (g - gMin) / (gMax - gMin)) * (WEIGHT_CHART_H - WEIGHT_PAD_TOP);

  const fmtTick = (t: number) => {
    const d = new Date(t);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  return (
    <View style={{ marginTop: spacing.md }}>
      <View
        style={{ height: WEIGHT_CHART_H }}
        onLayout={(e) => setPlotW(e.nativeEvent.layout.width)}
      >
        {plotW > 0 && (
          <>
            {points.slice(1).map((p, i) => {
              const a = points[i];
              const x1 = x(a.t);
              const y1 = y(a.g);
              const x2 = x(p.t);
              const y2 = y(p.g);
              const len = Math.hypot(x2 - x1, y2 - y1);
              const angle = (Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI;
              return (
                <View
                  key={p.t}
                  style={[
                    styles.weightLine,
                    {
                      width: len,
                      left: (x1 + x2) / 2 - len / 2,
                      top: (y1 + y2) / 2 - 1,
                      transform: [{ rotate: `${angle}deg` }],
                    },
                  ]}
                />
              );
            })}
            {points.map((p, i) => (
              <View key={p.t}>
                <View style={[styles.weightDot, { left: x(p.t) - 4, top: y(p.g) - 4 }]} />
                {(i === 0 || i === points.length - 1) && (
                  <Text
                    style={[
                      styles.weightLabel,
                      {
                        top: y(p.g) - 18,
                        ...(i === 0
                          ? { left: Math.max(x(p.t) - 20, 0) }
                          : { right: Math.max(plotW - x(p.t) - 20, 0) }),
                      },
                    ]}
                  >
                    {fmtKg(p.g)}
                  </Text>
                )}
              </View>
            ))}
          </>
        )}
      </View>
      <View style={styles.weightXAxis}>
        <Muted style={{ fontSize: 11 }}>{fmtTick(t0)}</Muted>
        <Muted style={{ fontSize: 11 }}>{fmtTick(t1)}</Muted>
      </View>
    </View>
  );
}

function Bar({
  day,
  axisMax,
  selected,
  onPress,
}: {
  day: DailyIntakeDay;
  axisMax: number;
  selected: boolean;
  onPress: () => void;
}) {
  const segments = SERIES.map((s) => ({ ...s, ml: day[s.key] })).filter((s) => s.ml > 0);
  return (
    <Pressable style={[styles.column, selected && styles.columnSelected]} onPress={onPress}>
      <View style={styles.stack}>
        {segments.map((seg, i) => (
          <View
            key={seg.key}
            style={[
              styles.segment,
              {
                height: Math.max(2, (seg.ml / axisMax) * CHART_HEIGHT),
                backgroundColor: seg.color,
              },
              // Round only the data-end (top of the stack); baseline stays flat.
              i === segments.length - 1 && styles.segmentTop,
            ]}
          />
        ))}
      </View>
    </Pressable>
  );
}

function DetailRow({
  label,
  value,
  bold,
  color,
}: {
  label: string;
  value: string;
  bold?: boolean;
  color?: string;
}) {
  return (
    <View style={styles.detailRow}>
      <Text style={{ color: colors.text, fontFamily: bold ? fonts.bold : fonts.regular }}>
        {label}
      </Text>
      <Text style={{ color: color ?? colors.text, fontFamily: fonts.bold }}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chips: { flexDirection: 'row', marginBottom: spacing.xs },

  plotRow: { flexDirection: 'row' },
  yAxis: { width: 36, height: CHART_HEIGHT, justifyContent: 'space-between' },
  yTick: {
    fontFamily: fonts.regular,
    fontSize: 11,
    color: colors.muted,
    textAlign: 'right',
    paddingRight: 6,
  },
  plot: {
    flex: 1,
    height: CHART_HEIGHT,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  gridline: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 1,
    backgroundColor: colors.border,
    opacity: 0.6,
  },
  columns: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'flex-end',
  },
  column: {
    flex: 1,
    height: CHART_HEIGHT,
    justifyContent: 'flex-end',
    alignItems: 'center',
    borderRadius: radius.sm,
  },
  columnSelected: { backgroundColor: colors.primarySoft },
  stack: {
    width: '58%',
    maxWidth: 22,
    flexDirection: 'column-reverse',
    gap: 2,
  },
  segment: { width: '100%' },
  segmentTop: { borderTopLeftRadius: 4, borderTopRightRadius: 4 },

  xLabels: { flexDirection: 'row', marginTop: 4 },
  xTick: {
    flex: 1,
    fontFamily: fonts.regular,
    fontSize: 10,
    color: colors.muted,
    textAlign: 'center',
  },
  xTickSelected: { fontFamily: fonts.bold, color: colors.primary },

  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginTop: spacing.md,
  },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { fontFamily: fonts.semibold, fontSize: 12, color: colors.text },

  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 7,
  },

  growthStats: { flexDirection: 'row', gap: spacing.md },
  growthStatValue: {
    fontFamily: fonts.heavy,
    fontSize: 17,
    color: colors.text,
    marginTop: 2,
  },
  weightLine: {
    position: 'absolute',
    height: 2,
    borderRadius: 1,
    backgroundColor: eventTheme.weight.color,
  },
  weightDot: {
    position: 'absolute',
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: eventTheme.weight.color,
    borderWidth: 2,
    borderColor: colors.card,
  },
  weightLabel: {
    position: 'absolute',
    fontFamily: fonts.bold,
    fontSize: 11,
    color: colors.text,
  },
  weightXAxis: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
});
