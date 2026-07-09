import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import { fmtNum } from '../lib/format';
import { useBaby, useFoods, useInvalidateLogs } from '../lib/hooks';
import { colors, eventTheme, fonts, radius, spacing } from '../lib/theme';
import type { FeedComponentIn, FeedPreset, Food } from '../lib/types';
import { Button, Card, Chip, Field, Muted, SectionTitle, Stepper } from '../components/ui';
import { SessionTimer } from '../components/SessionTimer';
import { TimePickerRow } from '../components/TimePickerRow';

type Mode = 'bottle' | 'latch';
type BottleMode = 'breast_milk' | 'formula' | 'ga1' | 'mixed' | 'custom';

const RECIPE_KEY = 'tinyprotocol_mix_recipe';
const DEFAULT_RECIPE = { bm: 40, ga1: 20 };

export default function LogFeed() {
  const router = useRouter();
  const { feedId } = useLocalSearchParams<{ feedId?: string }>();
  const editing = !!feedId;
  const qc = useQueryClient();
  const { baby } = useBaby();
  const { foods } = useFoods();
  const invalidate = useInvalidateLogs();
  const presetsQ = useQuery({ queryKey: ['feedPresets'], queryFn: api.listFeedPresets });

  const [mode, setMode] = useState<Mode>('bottle');
  const [bottleMode, setBottleMode] = useState<BottleMode>('mixed');
  const [when, setWhen] = useState(new Date());
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);

  // Simple modes: one amount. Mixed: one total + a saved ratio.
  const [singleMl, setSingleMl] = useState(0);
  const [mixTotal, setMixTotal] = useState(0);
  const [recipe, setRecipe] = useState(DEFAULT_RECIPE);
  const [showRecipe, setShowRecipe] = useState(false);

  // Custom mode: the full per-food builder.
  const [liquidMl, setLiquidMl] = useState<Record<string, number>>({});
  const [powderScoops, setPowderScoops] = useState<Record<string, number>>({});

  const [minutes, setMinutes] = useState(10);
  const [rate, setRate] = useState<number | null>(null);
  const [measuredMl, setMeasuredMl] = useState(0);

  useEffect(() => {
    if (feedId) return; // editing: the feed's own ratio takes over below
    AsyncStorage.getItem(RECIPE_KEY).then((raw) => {
      const r = raw ? JSON.parse(raw) : DEFAULT_RECIPE;
      setRecipe(r);
      setMixTotal(r.bm + r.ga1); // full bottle by default
    });
  }, []);

  // Editing: load the feed and prefill everything.
  useEffect(() => {
    if (!feedId) return;
    api
      .getFeed(feedId)
      .then((feed) => {
        setWhen(new Date(feed.occurred_at));
        setNotes(feed.notes ?? '');
        const latch = feed.components.find((c) => c.kind === 'latch');
        if (latch && feed.components.length === 1) {
          setMode('latch');
          setMinutes(latch.minutes ?? 10);
          setRate(latch.rate_ml_per_10min ?? null);
          setMeasuredMl(latch.measured_ml ?? 0);
        } else {
          setMode('bottle');
          const liquidsIn = feed.components.filter((c) => c.kind === 'liquid');
          const powdersIn = feed.components.filter((c) => c.kind === 'powder');
          const bmComp = liquidsIn.find((c) => c.food_category === 'breast_milk');
          const ga1Comp = liquidsIn.find((c) => c.food_category === 'metabolic_formula');

          if (powdersIn.length === 0 && liquidsIn.length === 2 && bmComp && ga1Comp) {
            // A breast-milk + GA1 mix: edit as ONE total, split by this
            // feed's own ratio (e.g. logged 40+20, she drank 55 → type 55).
            setBottleMode('mixed');
            setRecipe({ bm: bmComp.volume_ml ?? 0, ga1: ga1Comp.volume_ml ?? 0 });
            setMixTotal((bmComp.volume_ml ?? 0) + (ga1Comp.volume_ml ?? 0));
          } else if (powdersIn.length === 0 && liquidsIn.length === 1) {
            const c = liquidsIn[0];
            setBottleMode(
              c.food_category === 'breast_milk'
                ? 'breast_milk'
                : c.food_category === 'metabolic_formula'
                  ? 'ga1'
                  : 'formula',
            );
            setSingleMl(c.volume_ml ?? 0);
          } else {
            setBottleMode('custom');
            const l: Record<string, number> = {};
            const pw: Record<string, number> = {};
            for (const c of feed.components) {
              if (c.kind === 'liquid') l[c.food_id] = c.volume_ml ?? 0;
              if (c.kind === 'powder') pw[c.food_id] = c.scoops ?? 0;
            }
            setLiquidMl(l);
            setPowderScoops(pw);
          }
        }
      })
      .catch((e) => Alert.alert('Could not load feed', e.message));
  }, [feedId]);

  const saveRecipe = (r: { bm: number; ga1: number }) => {
    setRecipe(r);
    AsyncStorage.setItem(RECIPE_KEY, JSON.stringify(r));
  };

  const liquids = foods.filter((f) => f.unit_basis === 'per_100ml');
  const powders = foods.filter((f) => f.unit_basis === 'per_scoop');
  const bmFood = liquids.find((f) => f.category === 'breast_milk');
  const formulaFood = liquids.find((f) => f.category === 'formula');
  const ga1Food = liquids.find((f) => f.category === 'metabolic_formula');
  const breastMilkFood = bmFood;
  const effectiveRate = rate ?? baby?.default_latch_rate_ml_per_10min ?? 15;
  const latchEstimate = measuredMl > 0 ? measuredMl : (minutes * effectiveRate) / 10;

  // Mixed: split the total by the saved ratio, keeping the sum exact.
  const mixSplit = useMemo(() => {
    const parts = recipe.bm + recipe.ga1;
    if (mixTotal <= 0 || parts <= 0) return null;
    const bm = Math.round(((mixTotal * recipe.bm) / parts) * 10) / 10;
    return { bm, ga1: Math.round((mixTotal - bm) * 10) / 10 };
  }, [mixTotal, recipe]);

  const components: FeedComponentIn[] = useMemo(() => {
    if (mode === 'latch') {
      if (!breastMilkFood || minutes <= 0) return [];
      return [
        {
          kind: 'latch',
          food_id: breastMilkFood.id,
          minutes,
          rate_ml_per_10min: effectiveRate,
          measured_ml: measuredMl > 0 ? measuredMl : undefined,
        },
      ];
    }
    if (bottleMode === 'breast_milk')
      return bmFood && singleMl > 0
        ? [{ kind: 'liquid', food_id: bmFood.id, volume_ml: singleMl }]
        : [];
    if (bottleMode === 'formula')
      return formulaFood && singleMl > 0
        ? [{ kind: 'liquid', food_id: formulaFood.id, volume_ml: singleMl }]
        : [];
    if (bottleMode === 'ga1')
      return ga1Food && singleMl > 0
        ? [{ kind: 'liquid', food_id: ga1Food.id, volume_ml: singleMl }]
        : [];
    if (bottleMode === 'mixed') {
      if (!bmFood || !ga1Food || !mixSplit) return [];
      const out: FeedComponentIn[] = [];
      if (mixSplit.bm > 0) out.push({ kind: 'liquid', food_id: bmFood.id, volume_ml: mixSplit.bm });
      if (mixSplit.ga1 > 0)
        out.push({ kind: 'liquid', food_id: ga1Food.id, volume_ml: mixSplit.ga1 });
      return out;
    }
    // custom
    const out: FeedComponentIn[] = [];
    for (const f of liquids)
      if (liquidMl[f.id] > 0) out.push({ kind: 'liquid', food_id: f.id, volume_ml: liquidMl[f.id] });
    for (const f of powders)
      if (powderScoops[f.id] > 0)
        out.push({ kind: 'powder', food_id: f.id, scoops: powderScoops[f.id] });
    return out;
  }, [
    mode, bottleMode, singleMl, mixSplit, bmFood, formulaFood, ga1Food,
    liquids, powders, liquidMl, powderScoops,
    minutes, effectiveRate, measuredMl, breastMilkFood,
  ]);

  const preview = useMemo(() => {
    let ml = 0, protein = 0, lysine = 0;
    const byId = new Map(foods.map((f) => [f.id, f]));
    for (const c of components) {
      const f = byId.get(c.food_id);
      if (!f) continue;
      const effMl =
        c.kind === 'liquid' ? c.volume_ml : c.kind === 'powder' ? 0
        : c.measured_ml ?? (c.minutes * c.rate_ml_per_10min) / 10;
      const units = c.kind === 'powder' ? c.scoops : effMl / 100;
      ml += effMl;
      protein += units * f.natural_protein_g_per_unit;
      lysine += units * f.lysine_mg_per_unit;
    }
    return { ml, protein, lysine };
  }, [components, foods]);

  const applyPreset = (preset: FeedPreset) => {
    setMode('bottle');
    setBottleMode('custom');
    const liquid: Record<string, number> = {};
    const powder: Record<string, number> = {};
    for (const c of preset.components) {
      if (c.kind === 'liquid') liquid[c.food_id] = c.volume_ml;
      if (c.kind === 'powder') powder[c.food_id] = c.scoops;
    }
    setLiquidMl(liquid);
    setPowderScoops(powder);
  };

  const savePreset = () => {
    const comps = components.filter((c) => c.kind !== 'latch');
    if (comps.length === 0) return;
    const byId = new Map(foods.map((f) => [f.id, f]));
    const defaultName = comps
      .map((c) =>
        c.kind === 'liquid'
          ? `${fmtNum(c.volume_ml)} ${byId.get(c.food_id)?.name ?? ''}`
          : `${fmtNum(c.scoops)} scoop ${byId.get(c.food_id)?.name ?? ''}`,
      )
      .join(' + ');
    Alert.prompt(
      'Save preset',
      'Name this mix so you can log it in one tap.',
      async (name) => {
        try {
          await api.createFeedPreset({ name: name?.trim() || defaultName, components: comps });
          qc.invalidateQueries({ queryKey: ['feedPresets'] });
        } catch (e: any) {
          Alert.alert('Could not save preset', e.message);
        }
      },
      'plain-text',
      defaultName,
    );
  };

  const deletePreset = (preset: FeedPreset) => {
    Alert.alert(`Delete preset "${preset.name}"?`, undefined, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          await api.deleteFeedPreset(preset.id);
          qc.invalidateQueries({ queryKey: ['feedPresets'] });
        },
      },
    ]);
  };

  const save = async () => {
    if (!baby || components.length === 0) return;
    setBusy(true);
    try {
      if (editing) {
        await api.updateFeed(feedId!, {
          occurred_at: when.toISOString(),
          components,
          notes: notes.trim(),
        });
      } else {
        await api.createFeed(baby.id, {
          occurred_at: when.toISOString(),
          components,
          notes: notes.trim() || undefined,
        });
      }
      invalidate();
      router.back();
    } catch (e: any) {
      Alert.alert('Could not save feed', e.message);
      setBusy(false);
    }
  };

  const feedColor = eventTheme.feed.color;
  const feedSoft = eventTheme.feed.soft;

  const BOTTLE_OPTIONS: { key: BottleMode; label: string; disabled?: boolean }[] = [
    { key: 'breast_milk', label: '🍼 Breast milk', disabled: !bmFood },
    { key: 'formula', label: '🥫 Formula', disabled: !formulaFood },
    { key: 'ga1', label: '⚗️ GA1', disabled: !ga1Food },
    { key: 'mixed', label: '🧪 Mixed', disabled: !bmFood || !ga1Food },
    { key: 'custom', label: '⋯ Custom' },
  ];

  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}
      keyboardShouldPersistTaps="handled"
    >
      <View style={{ flexDirection: 'row', marginBottom: spacing.sm }}>
        <Chip label="🍼 Bottle" selected={mode === 'bottle'} onPress={() => setMode('bottle')} color={feedColor} softColor={feedSoft} />
        <Chip label="🤱 Latch" selected={mode === 'latch'} onPress={() => setMode('latch')} color={feedColor} softColor={feedSoft} />
      </View>

      {mode === 'bottle' ? (
        <>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
            {BOTTLE_OPTIONS.filter((o) => !o.disabled).map((o) => (
              <Chip
                key={o.key}
                label={o.label}
                selected={bottleMode === o.key}
                onPress={() => setBottleMode(o.key)}
                color={feedColor}
                softColor={feedSoft}
              />
            ))}
          </View>

          {bottleMode === 'mixed' && (
            <Card>
              <Text style={styles.fieldLabel}>Total amount she drank</Text>
              <Stepper value={mixTotal} onChange={setMixTotal} step={5} suffix="ml" />
              {mixSplit && (
                <Text style={[styles.splitLine, { color: feedColor }]}>
                  = {fmtNum(mixSplit.bm)} ml breast milk + {fmtNum(mixSplit.ga1)} ml GA1
                </Text>
              )}
              <Pressable onPress={() => setShowRecipe(!showRecipe)}>
                <Text style={styles.linkText}>
                  Mix ratio: {fmtNum(recipe.bm)} : {fmtNum(recipe.ga1)} (breast milk : GA1) —{' '}
                  {showRecipe ? 'done' : 'change'}
                </Text>
              </Pressable>
              {showRecipe && (
                <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Muted style={{ marginBottom: 4 }}>breast milk part</Muted>
                    <Stepper
                      value={recipe.bm}
                      onChange={(v) => saveRecipe({ ...recipe, bm: Math.max(0, v) })}
                      step={5}
                      suffix="ml"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Muted style={{ marginBottom: 4 }}>GA1 part</Muted>
                    <Stepper
                      value={recipe.ga1}
                      onChange={(v) => saveRecipe({ ...recipe, ga1: Math.max(0, v) })}
                      step={5}
                      suffix="ml"
                    />
                  </View>
                </View>
              )}
              <Muted style={{ marginTop: spacing.sm }}>
                The split keeps lysine and volume targets exact. Ratio is remembered —
                update it when the metabolic team changes the mix.
              </Muted>
            </Card>
          )}

          {(bottleMode === 'breast_milk' || bottleMode === 'formula' || bottleMode === 'ga1') && (
            <Card>
              <Text style={styles.fieldLabel}>
                {bottleMode === 'breast_milk'
                  ? 'Breast milk (pumped)'
                  : bottleMode === 'formula'
                    ? formulaFood?.name
                    : ga1Food?.name}
              </Text>
              <Stepper value={singleMl} onChange={setSingleMl} step={10} suffix="ml" />
            </Card>
          )}

          {bottleMode === 'custom' && (
            <>
              {(presetsQ.data?.length ?? 0) > 0 && (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginBottom: spacing.xs }}>
                  {presetsQ.data!.map((p) => (
                    <Pressable
                      key={p.id}
                      style={styles.presetChip}
                      onPress={() => applyPreset(p)}
                      onLongPress={() => deletePreset(p)}
                    >
                      <Text style={styles.presetText}>⚡ {p.name}</Text>
                    </Pressable>
                  ))}
                </View>
              )}
              <SectionTitle>Liquids (ml)</SectionTitle>
              {liquids.map((f) => (
                <FoodAmountRow
                  key={f.id}
                  food={f}
                  suffix="ml"
                  step={10}
                  value={liquidMl[f.id] ?? 0}
                  onChange={(v) => setLiquidMl((s) => ({ ...s, [f.id]: v }))}
                />
              ))}
              <SectionTitle>Powder mixed in (scoops)</SectionTitle>
              {powders.map((f) => (
                <FoodAmountRow
                  key={f.id}
                  food={f}
                  suffix="scoops"
                  step={0.5}
                  value={powderScoops[f.id] ?? 0}
                  onChange={(v) => setPowderScoops((s) => ({ ...s, [f.id]: v }))}
                />
              ))}
              {components.length > 0 && (
                <Pressable onPress={savePreset}>
                  <Text style={styles.linkText}>💾 Save this mix as a preset</Text>
                </Pressable>
              )}
            </>
          )}
        </>
      ) : (
        <Card>
          <Text style={styles.fieldLabel}>Timer (or type minutes below)</Text>
          <SessionTimer onMinutes={setMinutes} color={feedColor} />
          <Text style={[styles.fieldLabel, { marginTop: spacing.md }]}>Minutes latched</Text>
          <Stepper value={minutes} onChange={setMinutes} step={5} suffix="min" />
          <Text style={[styles.fieldLabel, { marginTop: spacing.md }]}>
            Est. intake rate (ml per 10 min)
          </Text>
          <Stepper value={effectiveRate} onChange={setRate} step={5} suffix="ml/10min" />
          <Text style={[styles.fieldLabel, { marginTop: spacing.md }]}>
            Weighed amount (optional — overrides the estimate)
          </Text>
          <Stepper value={measuredMl} onChange={setMeasuredMl} step={5} suffix="ml" />
          <Text style={[styles.latchEstimate, { color: feedColor }]}>
            {measuredMl > 0 ? 'Weighed' : 'Estimated'}: {fmtNum(latchEstimate)} ml
          </Text>
        </Card>
      )}

      <TimePickerRow value={when} onChange={setWhen} />
      <Field label="Notes (optional)" value={notes} onChangeText={setNotes} multiline />

      {components.length > 0 && (
        <Muted style={{ marginBottom: spacing.md, textAlign: 'center' }}>
          {fmtNum(preview.ml)} ml · {fmtNum(preview.protein, 2)} g protein · {fmtNum(preview.lysine)} mg lysine
        </Muted>
      )}
      <Button
        title={editing ? 'Save changes' : 'Save feed'}
        onPress={save}
        loading={busy}
        disabled={components.length === 0}
      />
    </ScrollView>
  );
}

function FoodAmountRow({
  food,
  value,
  onChange,
  step,
  suffix,
}: {
  food: Food;
  value: number;
  onChange: (v: number) => void;
  step: number;
  suffix: string;
}) {
  const tint =
    food.category === 'breast_milk'
      ? colors.breastMilk
      : food.category === 'metabolic_formula'
        ? colors.metabolic
        : colors.formula;
  return (
    <Card style={{ marginBottom: spacing.sm, paddingVertical: spacing.md }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
        <View style={[styles.dot, { backgroundColor: tint }]} />
        <Text style={styles.foodName}>{food.name}</Text>
        {food.needs_dietitian_verification && <Text style={styles.verify}> ⚠︎</Text>}
      </View>
      <Stepper value={value} onChange={onChange} step={step} suffix={suffix} />
    </Card>
  );
}

const styles = StyleSheet.create({
  fieldLabel: { fontSize: 13, fontFamily: fonts.semibold, color: colors.muted, marginBottom: 6 },
  foodName: { fontSize: 15, fontFamily: fonts.bold, color: colors.text },
  verify: { color: colors.metabolic, fontSize: 13 },
  dot: { width: 10, height: 10, borderRadius: 5, marginRight: 8 },
  latchEstimate: {
    marginTop: spacing.md,
    fontSize: 17,
    fontFamily: fonts.heavy,
    textAlign: 'center',
  },
  splitLine: {
    fontSize: 15,
    fontFamily: fonts.heavy,
    textAlign: 'center',
    marginVertical: spacing.sm,
  },
  linkText: {
    color: colors.primary,
    fontFamily: fonts.bold,
    fontSize: 14,
    marginTop: spacing.xs,
  },
  presetChip: {
    backgroundColor: eventTheme.feed.soft,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: eventTheme.feed.color,
    paddingHorizontal: 14,
    paddingVertical: 9,
    marginRight: spacing.sm,
    marginBottom: spacing.sm,
  },
  presetText: { color: colors.text, fontFamily: fonts.bold, fontSize: 14 },
});
