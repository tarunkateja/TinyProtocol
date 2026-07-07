import { useQuery } from '@tanstack/react-query';
import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../../lib/api';
import { addDays, fmtDateHeading, fmtNum, localDateString } from '../../lib/format';
import { useBaby } from '../../lib/hooks';
import { colors, radius, spacing } from '../../lib/theme';
import { Card, Muted, SectionTitle } from '../../components/ui';

export default function Totals() {
  const { baby } = useBaby();
  const [day, setDay] = useState(localDateString());

  const q = useQuery({
    queryKey: ['day', baby?.id, day],
    queryFn: () => api.daySummary(baby!.id, day),
    enabled: !!baby,
  });
  const s = q.data;
  const isToday = day === localDateString();

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
      <View style={styles.dayNav}>
        <Pressable style={styles.navBtn} onPress={() => setDay(addDays(day, -1))}>
          <Text style={styles.navBtnText}>‹</Text>
        </Pressable>
        <Text style={styles.dayTitle}>{fmtDateHeading(day)}</Text>
        <Pressable
          style={[styles.navBtn, isToday && { opacity: 0.3 }]}
          disabled={isToday}
          onPress={() => setDay(addDays(day, 1))}
        >
          <Text style={styles.navBtnText}>›</Text>
        </Pressable>
      </View>

      <SectionTitle>GA1 targets</SectionTitle>
      <TargetBar
        label="Lysine"
        value={s?.lysine_mg ?? 0}
        target={s?.targets.lysine_mg_per_day}
        unit="mg"
        color={colors.metabolic}
      />
      <TargetBar
        label="Natural protein"
        value={s?.natural_protein_g ?? 0}
        target={s?.targets.natural_protein_g_per_day}
        unit="g"
        color={colors.primary}
        digits={2}
      />
      {!s?.targets.lysine_mg_per_day && (
        <Muted style={{ marginBottom: spacing.md }}>
          Set your metabolic team's daily targets in Settings to see progress bars.
        </Muted>
      )}

      <SectionTitle>Intake by source</SectionTitle>
      <Card>
        <Row label="Total fed" value={`${fmtNum(s?.total_ml)} ml`} bold />
        <Row
          label="Breast milk (pumped)"
          value={`${fmtNum(s?.breast_milk.pumped_ml)} ml`}
          color={colors.breastMilk}
        />
        <Row
          label="Breast milk (latch, est.)"
          value={`${fmtNum(s?.breast_milk.latch_estimated_ml)} ml`}
          color={colors.breastMilk}
        />
        {(s?.breast_milk.latch_measured_ml ?? 0) > 0 && (
          <Row
            label="Breast milk (latch, weighed)"
            value={`${fmtNum(s?.breast_milk.latch_measured_ml)} ml`}
            color={colors.breastMilk}
          />
        )}
        <Row label="Formula" value={`${fmtNum(s?.formula_ml)} ml`} color={colors.formula} />
        {(s?.formula_scoops ?? 0) > 0 && (
          <Row label="Formula powder" value={`${fmtNum(s?.formula_scoops)} scoops`} color={colors.formula} />
        )}
        <Row
          label="Metabolic formula"
          value={`${fmtNum(s?.metabolic_formula_scoops)} scoops${(s?.metabolic_formula_ml ?? 0) > 0 ? ` + ${fmtNum(s?.metabolic_formula_ml)} ml` : ''}`}
          color={colors.metabolic}
        />
      </Card>

      <SectionTitle>Day at a glance</SectionTitle>
      <Card>
        <Row label="Feeds" value={String(s?.feed_count ?? 0)} />
        <Row label="Spit-ups" value={String(s?.spit_ups.length ?? 0)} />
        <Row label="Vomits" value={String(s?.vomits.length ?? 0)} />
        <Row label="Meds given" value={String(s?.meds.length ?? 0)} />
      </Card>
    </ScrollView>
  );
}

function TargetBar({
  label,
  value,
  target,
  unit,
  color,
  digits = 1,
}: {
  label: string;
  value: number;
  target?: number | null;
  unit: string;
  color: string;
  digits?: number;
}) {
  const pct = target ? Math.min(100, (100 * value) / target) : 0;
  const over = target ? value > target : false;
  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
        <Text style={{ fontWeight: '700', color: colors.text }}>{label}</Text>
        <Text style={{ fontWeight: '700', color: over ? colors.danger : color }}>
          {fmtNum(value, digits)} {unit}
          {target ? ` / ${fmtNum(target, digits)} ${unit}` : ''}
        </Text>
      </View>
      {target ? (
        <View style={styles.barTrack}>
          <View
            style={[
              styles.barFill,
              { width: `${pct}%`, backgroundColor: over ? colors.danger : color },
            ]}
          />
        </View>
      ) : (
        <Muted>No target set</Muted>
      )}
    </Card>
  );
}

function Row({
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
    <View style={styles.row}>
      <Text style={{ color: colors.text, fontWeight: bold ? '700' : '400' }}>{label}</Text>
      <Text style={{ color: color ?? colors.text, fontWeight: '700' }}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  dayNav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  navBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  navBtnText: { fontSize: 24, fontWeight: '700', color: colors.primary },
  dayTitle: { fontSize: 18, fontWeight: '800', color: colors.text },
  barTrack: {
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.border,
    overflow: 'hidden',
  },
  barFill: { height: 12, borderRadius: 6 },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 7,
  },
});
