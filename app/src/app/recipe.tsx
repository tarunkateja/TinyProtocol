import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import React, { useMemo, useState } from 'react';
import { Alert, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import { fmtNum, localDateString } from '../lib/format';
import { useBaby, useFoods } from '../lib/hooks';
import { colors, fonts, spacing } from '../lib/theme';
import type { Recipe, RecipeIn, RecipePowder, ResplitResult, Targets } from '../lib/types';
import { Button, Card, Chip, DateField, DateTimeField, Field, Muted, SectionTitle, Stepper } from '../components/ui';
import { showAlert } from '../lib/dialogs';

// react-native-web silently no-ops Alert.alert — surface feedback on web too.
const notify = (title: string, message?: string) => {
  if (Platform.OS === 'web') window.alert(message ? `${title}\n\n${message}` : title);
  else showAlert(title, message);
};

const confirmDialog = (title: string, message: string, action: () => void) => {
  if (Platform.OS === 'web') {
    if (window.confirm(`${title}\n\n${message}`)) action();
    return;
  }
  showAlert(title, message, [
    { text: 'Cancel', style: 'cancel' },
    { text: 'OK', style: 'destructive', onPress: action },
  ]);
};

const CAT_SHORT: Record<string, string> = {
  breast_milk: 'breast milk',
  formula: 'formula',
  metabolic_formula: 'GA1 formula',
};

function fmtWhen(iso: string): string {
  return new Date(iso).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function localTimeString(d: Date = new Date()): string {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function bottleLine(r: Recipe | RecipeIn): string {
  const parts: string[] = [];
  if (r.breast_milk_ml > 0) parts.push(`${fmtNum(r.breast_milk_ml)} ml breast milk`);
  if (r.batch_ml > 0) parts.push(`${fmtNum(r.batch_ml)} ml batch formula`);
  return `${parts.join(' + ')} = ${fmtNum(r.breast_milk_ml + r.batch_ml)} ml per feed`;
}

function batchLine(r: Recipe | RecipeIn): string | null {
  if (!r.powders.length && !r.batch_final_volume_ml) return null;
  const powders = r.powders.map((p) => `${fmtNum(p.grams)} g ${p.name}`).join(' + ');
  const water = r.batch_final_volume_ml ? ` → water to ${fmtNum(r.batch_final_volume_ml)} ml` : '';
  return `${powders}${water}`;
}

function topoffLine(r: Recipe | RecipeIn): string | null {
  const powders = r.topoff_powders ?? [];
  if (!powders.length && !r.topoff_water_ml) return null;
  const parts = powders.map((p) => `${fmtNum(p.grams)} g ${p.name}`);
  if (r.topoff_water_ml) parts.push(`${fmtNum(r.topoff_water_ml)} ml water`);
  return parts.join(' + ');
}

function describeTargets(t: Targets): string {
  const parts: string[] = [];
  for (const vt of t.volume_targets ?? []) {
    parts.push(`${CAT_SHORT[vt.category] ?? vt.category} ${vt.direction} ${fmtNum(vt.ml_per_day)} ml`);
  }
  if (t.lysine_mg_per_kg) parts.push(`lysine ${fmtNum(t.lysine_mg_per_kg)} mg/kg`);
  else if (t.lysine_mg_per_day) parts.push(`lysine ${fmtNum(t.lysine_mg_per_day)} mg`);
  if (t.natural_protein_g_per_kg) parts.push(`protein ${fmtNum(t.natural_protein_g_per_kg)} g/kg`);
  else if (t.natural_protein_g_per_day) parts.push(`protein ${fmtNum(t.natural_protein_g_per_day)} g`);
  return parts.join(' · ') || 'no goals set';
}

type Draft = {
  label: string;
  date: string;
  time: string;
  breast_milk_ml: number;
  batch_ml: number;
  powders: RecipePowder[];
  batch_final_volume_ml: number;
  feeds_per_day: number;
  topoff_powders: RecipePowder[];
  topoff_water_ml: number;
  topoff_food_id: string | null;
  batch_food_id: string | null;
  source: string;
  notes: string;
};

function draftFrom(r: Recipe | null): Draft {
  const now = new Date();
  return {
    label: '',
    date: localDateString(now),
    time: localTimeString(now),
    breast_milk_ml: r?.breast_milk_ml ?? 55,
    batch_ml: r?.batch_ml ?? 25,
    powders: r?.powders.map((p) => ({ ...p })) ?? [],
    batch_final_volume_ml: r?.batch_final_volume_ml ?? 0,
    feeds_per_day: r?.feeds_per_day ?? 8,
    topoff_powders: r?.topoff_powders?.map((p) => ({ ...p })) ?? [],
    topoff_water_ml: r?.topoff_water_ml ?? 0,
    topoff_food_id: r?.topoff_food_id ?? null,
    batch_food_id: r?.batch_food_id ?? null,
    source: '',
    notes: '',
  };
}

function draftOf(r: Recipe): Draft {
  const d = new Date(r.effective_at);
  return {
    label: r.label,
    date: localDateString(d),
    time: localTimeString(d),
    breast_milk_ml: r.breast_milk_ml,
    batch_ml: r.batch_ml,
    powders: r.powders.map((p) => ({ ...p })),
    batch_final_volume_ml: r.batch_final_volume_ml ?? 0,
    feeds_per_day: r.feeds_per_day ?? 0,
    topoff_powders: r.topoff_powders?.map((p) => ({ ...p })) ?? [],
    topoff_water_ml: r.topoff_water_ml ?? 0,
    topoff_food_id: r.topoff_food_id ?? null,
    batch_food_id: r.batch_food_id ?? null,
    source: r.source ?? '',
    notes: r.notes ?? '',
  };
}

export default function RecipeScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { baby } = useBaby();
  const { foods } = useFoods();
  const recipesQ = useQuery({
    queryKey: ['recipes', baby?.id],
    queryFn: () => api.listRecipes(baby!.id),
    enabled: !!baby,
  });
  const hbQ = useQuery({
    queryKey: ['hb-status', baby?.id],
    queryFn: () => api.hbStatus(baby!.id),
    enabled: !!baby,
  });
  const historyQ = useQuery({
    queryKey: ['target-history', baby?.id],
    queryFn: () => api.targetHistory(baby!.id),
    enabled: !!baby,
  });

  const recipes = recipesQ.data ?? [];
  const current = useMemo(() => {
    const now = Date.now();
    let cur: Recipe | null = null;
    for (const r of recipes) if (new Date(r.effective_at).getTime() <= now) cur = r;
    return cur;
  }, [recipes]);

  // Editing state: null = closed; {id: null} = new recipe.
  const [editing, setEditing] = useState<{ id: string | null; draft: Draft } | null>(null);
  const [saving, setSaving] = useState(false);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['recipes'] });
    qc.invalidateQueries({ queryKey: ['hb-status'] });
  };

  const save = async () => {
    if (!baby || !editing) return;
    const d = editing.draft;
    if (!d.label.trim()) {
      notify('Name it', 'Give the recipe a short label, e.g. "85 ml feeds" or "Post-hospital plan".');
      return;
    }
    const when = new Date(`${d.date}T${d.time}:00`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d.date) || !/^\d{2}:\d{2}$/.test(d.time) || Number.isNaN(when.getTime())) {
      notify('Check the start', 'Date must be YYYY-MM-DD and time HH:MM (24h), e.g. 2026-08-20 22:00.');
      return;
    }
    if (d.breast_milk_ml + d.batch_ml <= 0) {
      notify('Empty bottle', 'A recipe needs breast milk and/or batch formula per feed.');
      return;
    }
    if ([...d.powders, ...d.topoff_powders].some((p) => !p.name.trim() || p.grams <= 0)) {
      notify('Check powders', 'Every powder needs a name and grams above 0.');
      return;
    }
    const body: RecipeIn = {
      label: d.label.trim(),
      effective_at: when.toISOString(),
      breast_milk_ml: d.breast_milk_ml,
      batch_ml: d.batch_ml,
      powders: d.powders.map((p) => ({ name: p.name.trim(), grams: p.grams })),
      batch_final_volume_ml: d.batch_final_volume_ml > 0 ? d.batch_final_volume_ml : null,
      feeds_per_day: d.feeds_per_day > 0 ? Math.round(d.feeds_per_day) : null,
      topoff_powders: d.topoff_powders.map((p) => ({ name: p.name.trim(), grams: p.grams })),
      topoff_water_ml: d.topoff_water_ml > 0 ? d.topoff_water_ml : null,
      topoff_food_id: d.topoff_food_id,
      batch_food_id: d.batch_food_id,
      source: d.source.trim() || null,
      notes: d.notes.trim() || null,
    };
    setSaving(true);
    try {
      if (editing.id) await api.updateRecipe(baby.id, editing.id, body);
      else await api.createRecipe(baby.id, body);
      setEditing(null);
      refresh();
    } catch (e: any) {
      notify('Could not save', e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = (r: Recipe) => {
    if (!baby) return;
    confirmDialog(
      `Delete "${r.label}"?`,
      'Feeds from this period will fall back to the previous recipe the next time they are re-split.',
      async () => {
        try {
          await api.deleteRecipe(baby.id, r.id);
          setEditing(null);
          refresh();
        } catch (e: any) {
          notify('Could not delete', e.message);
        }
      },
    );
  };

  const enableRecipeMode = async () => {
    if (!baby) return;
    try {
      await api.hbUpdate(baby.id, { mapping: { Other: { mode: 'recipe' }, Formula: { mode: 'recipe' } } });
      refresh();
    } catch (e: any) {
      notify('Could not update', e.message);
    }
  };

  // Merged plan history: recipes + goal periods, newest first.
  const timeline = useMemo(() => {
    type Row = { at: string; kind: 'recipe' | 'goals'; text: string; recipe?: Recipe };
    const rows: Row[] = recipes.map((r) => ({
      at: r.effective_at,
      kind: 'recipe',
      text: `${r.label} — ${bottleLine(r)}${batchLine(r) ? ` · ${batchLine(r)}` : ''}${
        topoffLine(r) ? ` · top-ups: ${topoffLine(r)}` : ''
      }`,
      recipe: r,
    }));
    for (const p of historyQ.data ?? []) {
      const at =
        p.effective_date === '0001-01-01'
          ? '0001-01-01T00:00:00Z'
          : new Date(`${p.effective_date}T00:00:00`).toISOString();
      rows.push({ at, kind: 'goals', text: `🎯 Goals — ${describeTargets(p.targets)}` });
    }
    rows.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
    return rows;
  }, [recipes, historyQ.data]);

  if (!baby) return null;
  const hbOther = hbQ.data?.connected ? hbQ.data.mapping['Other'] : undefined;
  const hbFormula = hbQ.data?.connected ? hbQ.data.mapping['Formula'] : undefined;
  const liquidFormulas = foods.filter(
    (f) => f.unit_basis === 'per_100ml' && !f.archived && f.category !== 'breast_milk',
  );
  const foodName = (id: string | null | undefined) => foods.find((f) => f.id === id)?.name;
  const d = editing?.draft;
  const setD = (patch: Partial<Draft>) =>
    setEditing((e) => (e ? { ...e, draft: { ...e.draft, ...patch } } : e));

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ padding: spacing.md }}>
      <SectionTitle>Current recipe</SectionTitle>
      <Card>
        {current ? (
          <>
            <Text style={styles.big}>{bottleLine(current)}</Text>
            {batchLine(current) ? <Text style={styles.line}>⚗️ Batch: {batchLine(current)}</Text> : null}
            <Text style={styles.line}>
              ➕ Top-ups: {topoffLine(current) ?? 'more of the batch'}
              {current.topoff_food_id ? ` → logged as ${foodName(current.topoff_food_id) ?? 'its own food'}` : ''}
            </Text>
            {current.feeds_per_batch ? (
              <Muted>
                One batch covers ~{fmtNum(current.feeds_per_batch)} feeds of {fmtNum(current.batch_ml)} ml
                {current.feeds_per_day
                  ? ` · ${fmtNum(current.feeds_per_day)} feeds/day use ${fmtNum(
                      current.feeds_per_day * current.batch_ml,
                    )} ml, leaving ${fmtNum(
                      (current.batch_final_volume_ml ?? 0) - current.feeds_per_day * current.batch_ml,
                    )} ml for top-offs`
                  : ''}
              </Muted>
            ) : null}
            <Muted style={{ marginTop: spacing.sm }}>
              "{current.label}" · since {fmtWhen(current.effective_at)}
              {current.source ? ` · ${current.source}` : ''}
            </Muted>
            {current.notes ? <Muted style={{ marginTop: 4 }}>{current.notes}</Muted> : null}
          </>
        ) : (
          <Muted>
            No recipe yet. Add the plan your metabolic team gave you — what goes in each bottle and
            how the batch is made. Past plans can be added with their own start dates.
          </Muted>
        )}
        <Text style={[styles.line, { marginTop: spacing.md }]}>
          🎯 Goals: {describeTargets(baby.targets)}
        </Text>
        <Muted>Goals (min/max ml per day, lysine, protein) are edited on the Plan screen with their own start date.</Muted>
        {!editing && (
          <Button
            title={current ? '＋ New recipe (plan changed)' : '＋ Add the recipe'}
            onPress={() => setEditing({ id: null, draft: draftFrom(current) })}
            style={{ marginTop: spacing.md }}
          />
        )}
      </Card>

      {editing && d && (
        <>
          <SectionTitle>{editing.id ? 'Edit recipe' : 'New recipe'}</SectionTitle>
          <Card>
            <Field label="Label" value={d.label} onChangeText={(v) => setD({ label: v })} placeholder='e.g. "85 ml feeds" or "Post-hospital plan"' />
            <DateTimeField
              label="In effect from (feeds after this use it)"
              value={(() => {
                const dt = new Date(`${d.date}T${d.time}:00`);
                return Number.isNaN(dt.getTime()) ? new Date() : dt;
              })()}
              onChange={(dt) => setD({ date: localDateString(dt), time: localTimeString(dt) })}
            />

            <Text style={styles.label}>Each prepared bottle</Text>
            <Muted style={{ marginBottom: 4 }}>🍼 Breast milk</Muted>
            <Stepper value={d.breast_milk_ml} onChange={(v) => setD({ breast_milk_ml: Math.max(0, v) })} step={5} suffix="ml" />
            <Muted style={{ marginBottom: 4, marginTop: spacing.sm }}>⚗️ Batch formula</Muted>
            <Stepper value={d.batch_ml} onChange={(v) => setD({ batch_ml: Math.max(0, v) })} step={5} suffix="ml" />
            <Muted style={{ marginTop: 4 }}>
              = {fmtNum(d.breast_milk_ml + d.batch_ml)} ml per feed. A partial feed splits in this
              ratio; anything above it counts as batch top-off.
            </Muted>

            <Text style={[styles.label, { marginTop: spacing.md }]}>The batch (powders + water)</Text>
            {d.powders.map((p, i) => (
              <View key={i} style={{ flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' }}>
                <View style={{ flex: 3 }}>
                  <Field
                    value={p.name}
                    onChangeText={(v) =>
                      setD({ powders: d.powders.map((q, j) => (j === i ? { ...q, name: v } : q)) })
                    }
                    placeholder="Powder, e.g. GA-1 Anamix"
                  />
                </View>
                <View style={{ flex: 2 }}>
                  <Stepper
                    value={p.grams}
                    onChange={(v) =>
                      setD({ powders: d.powders.map((q, j) => (j === i ? { ...q, grams: Math.max(0, v) } : q)) })
                    }
                    step={1}
                    suffix="g"
                  />
                </View>
                <Pressable
                  onPress={() => setD({ powders: d.powders.filter((_, j) => j !== i) })}
                  style={{ paddingTop: 12, paddingHorizontal: 4 }}
                >
                  <Text style={{ color: colors.danger, fontSize: 18 }}>✕</Text>
                </Pressable>
              </View>
            ))}
            <Button
              title="＋ Add powder"
              variant="secondary"
              onPress={() => setD({ powders: [...d.powders, { name: '', grams: 10 }] })}
              style={{ marginBottom: spacing.md }}
            />
            <Muted style={{ marginBottom: 4 }}>Water to a final volume of</Muted>
            <Stepper value={d.batch_final_volume_ml} onChange={(v) => setD({ batch_final_volume_ml: Math.max(0, v) })} step={10} suffix="ml" />
            <Muted style={{ marginBottom: 4, marginTop: spacing.sm }}>Feeds per day (for the yield estimate)</Muted>
            <Stepper value={d.feeds_per_day} onChange={(v) => setD({ feeds_per_day: Math.max(0, v) })} step={1} />
            {liquidFormulas.length > 1 ? (
              <>
                <Muted style={{ marginBottom: 4, marginTop: spacing.sm }}>Batch is logged as</Muted>
                <View style={styles.chips}>
                  {liquidFormulas.map((f) => (
                    <Chip key={f.id} label={f.name} selected={d.batch_food_id === f.id} onPress={() => setD({ batch_food_id: f.id })} />
                  ))}
                </View>
              </>
            ) : null}

            <Text style={[styles.label, { marginTop: spacing.md }]}>Top-ups (a separate "Formula" bottle)</Text>
            <Muted style={{ marginBottom: spacing.sm }}>
              Leave empty when a top-up is just more of the batch. Fill in when top-ups are made
              separately, e.g. 9 g Pro-Phree in 60 ml water.
            </Muted>
            {d.topoff_powders.map((p, i) => (
              <View key={i} style={{ flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' }}>
                <View style={{ flex: 3 }}>
                  <Field
                    value={p.name}
                    onChangeText={(v) =>
                      setD({ topoff_powders: d.topoff_powders.map((q, j) => (j === i ? { ...q, name: v } : q)) })
                    }
                    placeholder="Powder, e.g. Pro-Phree"
                  />
                </View>
                <View style={{ flex: 2 }}>
                  <Stepper
                    value={p.grams}
                    onChange={(v) =>
                      setD({ topoff_powders: d.topoff_powders.map((q, j) => (j === i ? { ...q, grams: Math.max(0, v) } : q)) })
                    }
                    step={1}
                    suffix="g"
                  />
                </View>
                <Pressable
                  onPress={() => setD({ topoff_powders: d.topoff_powders.filter((_, j) => j !== i) })}
                  style={{ paddingTop: 12, paddingHorizontal: 4 }}
                >
                  <Text style={{ color: colors.danger, fontSize: 18 }}>✕</Text>
                </Pressable>
              </View>
            ))}
            <Button
              title="＋ Add top-up powder"
              variant="secondary"
              onPress={() => setD({ topoff_powders: [...d.topoff_powders, { name: 'Pro-Phree', grams: 9 }] })}
              style={{ marginBottom: spacing.md }}
            />
            <Muted style={{ marginBottom: 4 }}>Water</Muted>
            <Stepper value={d.topoff_water_ml} onChange={(v) => setD({ topoff_water_ml: Math.max(0, v) })} step={10} suffix="ml" />
            <Muted style={{ marginBottom: 4, marginTop: spacing.sm }}>Top-ups are logged as</Muted>
            <View style={styles.chips}>
              <Chip label="Same as batch" selected={!d.topoff_food_id} onPress={() => setD({ topoff_food_id: null })} />
              {liquidFormulas.map((f) => (
                <Chip key={f.id} label={f.name} selected={d.topoff_food_id === f.id} onPress={() => setD({ topoff_food_id: f.id })} />
              ))}
            </View>
            <Muted style={{ marginTop: 4 }}>
              Pick a separate food when top-ups aren't the batch, so totals show them apart. Foods
              are added under Settings → Foods.
            </Muted>

            <Field label="Who ordered it / when" value={d.source} onChangeText={(v) => setD({ source: v })} placeholder="e.g. Madison (dietician) via MyChart, Aug 4" style={{ marginTop: spacing.md }} />
            <Field label="Notes" value={d.notes} onChangeText={(v) => setD({ notes: v })} placeholder="Why it changed, what to watch…" multiline />

            <Button title={editing.id ? 'Save changes' : 'Save recipe'} onPress={save} loading={saving} />
            <Button title="Cancel" variant="secondary" onPress={() => setEditing(null)} style={{ marginTop: spacing.sm }} />
            {editing.id ? (
              <Button
                title="Delete this recipe"
                variant="danger"
                onPress={() => remove(recipes.find((r) => r.id === editing.id)!)}
                style={{ marginTop: spacing.sm }}
              />
            ) : null}
          </Card>
        </>
      )}

      <SectionTitle>Huckleberry bottles</SectionTitle>
      <Card>
        {!hbQ.data?.connected ? (
          <Muted>Huckleberry isn't connected. Connect it from Settings → Sync.</Muted>
        ) : hbOther?.recipe ? (
          <>
            <Text style={styles.line}>✓ "Other" bottles split by the recipe in effect at the feed's time.</Text>
            {hbFormula?.recipe ? (
              <Text style={styles.line}>✓ "Formula" bottles logged as that recipe's top-up.</Text>
            ) : (
              <>
                <Text style={styles.line}>
                  ⚠️ "Formula" bottles always go to {hbFormula?.food_name ?? 'nothing'} — they ignore the
                  recipe's top-up.
                </Text>
                <Button title='Switch "Formula" to: per recipe' onPress={enableRecipeMode} style={{ marginTop: spacing.sm }} />
              </>
            )}
            <Muted style={{ marginTop: 4 }}>
              "Breast Milk" → {hbQ.data.mapping['Breast Milk']?.food_name ?? 'not mapped'}
            </Muted>
            <Muted style={{ marginTop: 4 }}>
              When the plan changes, add a new recipe above — nothing else to configure.
            </Muted>
          </>
        ) : (
          <>
            <Text style={styles.line}>
              "Other" bottles currently use a fixed ratio
              {hbOther?.split?.length
                ? ` (${hbOther.split.map((p) => fmtNum(p.parts)).join(' : ')})`
                : ''}
              , which is wrong for partial feeds once the plan changes.
            </Text>
            <Button
              title="Switch to: split by recipe"
              onPress={enableRecipeMode}
              disabled={recipes.length === 0}
              style={{ marginTop: spacing.sm }}
            />
            {recipes.length === 0 ? <Muted style={{ marginTop: 4 }}>Add a recipe first.</Muted> : null}
          </>
        )}
      </Card>

      {hbOther?.recipe ? <ResplitCard babyId={baby.id} /> : null}

      <SectionTitle>Plan history</SectionTitle>
      {timeline.length === 0 ? (
        <Muted>Nothing yet.</Muted>
      ) : (
        <Card style={{ paddingVertical: 4 }}>
          {timeline.map((row, i, arr) => {
            const until = i === 0 ? 'now' : fmtWhen(arr[i - 1].at);
            const from = row.at.startsWith('0001') ? 'start' : fmtWhen(row.at);
            return (
              <Pressable
                key={`${row.kind}-${row.at}`}
                onPress={() => {
                  if (row.recipe) setEditing({ id: row.recipe.id, draft: draftOf(row.recipe) });
                  else router.push('/plan');
                }}
                onLongPress={() => row.recipe && remove(row.recipe)}
                style={[styles.historyRow, i > 0 && { borderTopWidth: 1, borderTopColor: colors.border }]}
              >
                <Text style={styles.historyDates}>
                  {from} → {until}
                </Text>
                <Text style={styles.historyText}>{row.text}</Text>
              </Pressable>
            );
          })}
        </Card>
      )}
      <Muted style={{ marginBottom: spacing.lg }}>
        Tap a recipe to edit it, long-press to delete. Goals rows open Plan. "→ now" rows are
        what's in effect today.
      </Muted>
    </ScrollView>
  );
}

// --------------------------------------------------------------------------- //
// Re-split already-imported mixed bottles against the recipe history
// --------------------------------------------------------------------------- //
function ResplitCard({ babyId }: { babyId: string }) {
  const qc = useQueryClient();
  const [from, setFrom] = useState(localDateString(new Date(Date.now() - 7 * 86400e3)));
  const [to, setTo] = useState(localDateString());
  const [preview, setPreview] = useState<ResplitResult | null>(null);
  const [busy, setBusy] = useState(false);

  const bounds = () => {
    const f = new Date(`${from}T00:00:00`);
    const t = new Date(`${to}T23:59:59`);
    if (Number.isNaN(f.getTime()) || Number.isNaN(t.getTime())) {
      notify('Check dates', 'Use YYYY-MM-DD.');
      return null;
    }
    return { f: f.toISOString(), t: t.toISOString() };
  };

  const run = async (apply: boolean) => {
    const b = bounds();
    if (!b) return;
    setBusy(true);
    try {
      const res = await api.resplit(babyId, b.f, b.t, apply);
      setPreview(res);
      if (apply) {
        qc.invalidateQueries({ queryKey: ['logs'] });
        qc.invalidateQueries({ queryKey: ['timeline'] });
        qc.invalidateQueries({ queryKey: ['summary'] });
        notify('Done', `${res.changes.length} feed${res.changes.length === 1 ? '' : 's'} re-split.`);
      }
    } catch (e: any) {
      notify('Could not re-split', e.message);
    } finally {
      setBusy(false);
    }
  };

  const fmtSplit = (m: Record<string, number>) =>
    Object.entries(m)
      .map(([name, ml]) => `${fmtNum(ml)} ${name.toLowerCase().startsWith('breast') ? 'bm' : 'formula'}`)
      .join(' + ');

  return (
    <>
      <SectionTitle>Re-split imported mixes</SectionTitle>
      <Card>
        <Muted style={{ marginBottom: spacing.sm }}>
          Already-imported "Other" bottles keep the split they got at import time. After adding or
          backdating a recipe, preview what would change, then apply. Totals never change — only
          breast milk vs formula. Feeds you edited by hand are never touched.
        </Muted>
        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <View style={{ flex: 1 }}>
            <DateField label="From" value={from} onChange={setFrom} maximumDate={new Date()} />
          </View>
          <View style={{ flex: 1 }}>
            <DateField label="To" value={to} onChange={setTo} maximumDate={new Date()} />
          </View>
        </View>
        <Button title="Preview" variant="secondary" onPress={() => run(false)} loading={busy} />
        {preview && (
          <View style={{ marginTop: spacing.md }}>
            <Text style={styles.line}>
              {preview.changes.length} to change · {preview.unchanged} already right
              {preview.skipped_no_recipe ? ` · ${preview.skipped_no_recipe} before any recipe` : ''}
              {preview.skipped_unlinked ? ` · ${preview.skipped_unlinked} skipped` : ''}
            </Text>
            {preview.changes.map((ch) => (
              <View key={ch.feed_id} style={{ paddingVertical: 6, borderTopWidth: 1, borderTopColor: colors.border }}>
                <Text style={styles.historyDates}>
                  {fmtWhen(ch.occurred_at)} · {fmtNum(ch.total_ml)} ml · {ch.recipe_label}
                </Text>
                <Text style={styles.historyText}>
                  {fmtSplit(ch.before)} → {fmtSplit(ch.after)}
                </Text>
              </View>
            ))}
            {!preview.applied && preview.changes.length > 0 && (
              <Button
                title={`Apply to ${preview.changes.length} feed${preview.changes.length === 1 ? '' : 's'}`}
                onPress={() =>
                  confirmDialog(
                    'Re-split these feeds?',
                    'Only the breast milk / formula split changes; totals stay the same.',
                    () => run(true),
                  )
                }
                loading={busy}
                style={{ marginTop: spacing.sm }}
              />
            )}
          </View>
        )}
      </Card>
    </>
  );
}

const styles = StyleSheet.create({
  big: { fontSize: 18, fontFamily: fonts.bold, color: colors.text, marginBottom: 6 },
  line: { fontSize: 15, color: colors.text, marginBottom: 4 },
  label: { fontSize: 13, fontFamily: fonts.semibold, color: colors.muted, marginBottom: 6 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  historyRow: { paddingVertical: 10 },
  historyDates: { fontSize: 13, fontFamily: fonts.semibold, color: colors.muted },
  historyText: { fontSize: 15, color: colors.text, marginTop: 2 },
});
