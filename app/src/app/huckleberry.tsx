import { useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { Alert, Platform, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { api } from '../lib/api';
import { fmtNum, fmtTime } from '../lib/format';
import { useBaby, useFoods } from '../lib/hooks';
import { colors, fonts, spacing } from '../lib/theme';
import type { HbChild, HbImport, HbSplitPart, HbStatus } from '../lib/types';
import { Button, Card, Chip, Field, Muted, SectionTitle, Stepper } from '../components/ui';
import { showAlert } from '../lib/dialogs';

const MAPPED_TYPES = ['Breast Milk', 'Formula', 'Other'] as const;

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

function fmtWhen(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })} · ${fmtTime(iso)}`;
}

function describeImport(imp: HbImport): string {
  if (imp.mode === 'bottle') {
    return `🍼 Bottle · ${imp.bottle_type} · ${fmtNum(imp.amount_ml)} ml`;
  }
  if (imp.mode === 'diaper') {
    const kind = { pee: '💧 pee', poop: '💩 poop', both: '💧💩 both' }[imp.diaper_kind ?? ''] ?? imp.diaper_kind;
    return `Diaper · ${kind}`;
  }
  if (imp.mode === 'pumping') {
    const mins = imp.duration_minutes ? ` · ${fmtNum(imp.duration_minutes)} min` : '';
    return `🥛 Pumped · ${fmtNum(imp.pumped_ml)} ml${mins}`;
  }
  if (imp.mode === 'medication') {
    const dose = imp.dose_amount ? ` · ${fmtNum(imp.dose_amount)} ${imp.dose_unit ?? ''}` : '';
    return `💊 ${imp.med_name}${dose}`;
  }
  return `🤱 Nursed · ${fmtNum(imp.minutes)} min`;
}

export default function Huckleberry() {
  const qc = useQueryClient();
  const { baby } = useBaby();
  const { foods } = useFoods();

  const statusQ = useQuery({
    queryKey: ['hb-status', baby?.id],
    queryFn: () => api.hbStatus(baby!.id),
    enabled: !!baby,
  });
  const importsQ = useQuery({
    queryKey: ['hb-imports', baby?.id],
    queryFn: () => api.hbImports(baby!.id),
    enabled: !!baby && !!statusQ.data?.connected,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['hb-status'] });
    qc.invalidateQueries({ queryKey: ['hb-imports'] });
  };

  if (!baby) return null;
  const status = statusQ.data;

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      {!status ? null : !status.connected ? (
        <ConnectCard babyId={baby.id} onConnected={refresh} />
      ) : (
        <>
          <ConnectedCard babyId={baby.id} status={status} onChanged={refresh} />
          <MappingCard babyId={baby.id} status={status} onChanged={refresh} />
          <ImportsSection
            babyId={baby.id}
            defaultLatchRate={baby.default_latch_rate_ml_per_10min}
            status={status}
            imports={importsQ.data?.items ?? []}
            onChanged={() => {
              refresh();
              // Confirmed imports appear on the timeline & totals.
              qc.invalidateQueries({ queryKey: ['timeline'] });
              qc.invalidateQueries({ queryKey: ['summary'] });
            }}
          />
        </>
      )}
    </ScrollView>
  );
}

// --------------------------------------------------------------------------- //
// Connect
// --------------------------------------------------------------------------- //
function ConnectCard({ babyId, onConnected }: { babyId: string; onConnected: () => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [children, setChildren] = useState<HbChild[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connect = async (childUid?: string) => {
    if (!email.trim() || !password) {
      setError('Enter the Huckleberry account email and password.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await api.hbConnect(babyId, {
        email: email.trim(),
        password,
        ...(childUid ? { child_uid: childUid } : {}),
      });
      if ('needs_child_selection' in resp) {
        setChildren(resp.children);
      } else {
        onConnected();
      }
    } catch (e: any) {
      setError(
        e.status === 401
          ? `Huckleberry rejected this login. If this account signs in with Google or Apple, ` +
            `it has no Huckleberry password — use the account that signs in with email+password, ` +
            `or set a password via "Forgot password" in the Huckleberry app.`
          : e.message,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <SectionTitle>Connect Huckleberry</SectionTitle>
      <Card>
        <Muted style={{ marginBottom: spacing.md }}>
          Feeds logged in Huckleberry sync here automatically every 2 hours. Sign in
          with the Huckleberry account that does the logging — only a sync token is
          stored, never the password.
        </Muted>
        <Field
          label="Huckleberry email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          placeholder="wife@example.com"
        />
        <Field
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          placeholder="••••••••"
        />
        {error ? (
          <Text style={styles.error}>⚠︎ {error}</Text>
        ) : null}
        {children ? (
          <>
            <Text style={styles.label}>Which child?</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
              {children.map((c) => (
                <Chip key={c.uid} label={c.name} selected={false} onPress={() => connect(c.uid)} />
              ))}
            </View>
          </>
        ) : (
          <Button title="Connect" onPress={() => connect()} loading={busy} />
        )}
      </Card>
      <Muted>
        Unofficial integration: it reads your own data via Huckleberry's backend. If
        Huckleberry changes things it may pause until the app is updated.
      </Muted>
    </>
  );
}

// --------------------------------------------------------------------------- //
// Connected: status, auto-import, sync now, disconnect
// --------------------------------------------------------------------------- //
function ConnectedCard({
  babyId,
  status,
  onChanged,
}: {
  babyId: string;
  status: HbStatus;
  onChanged: () => void;
}) {
  const [syncing, setSyncing] = useState(false);

  const syncNow = async () => {
    setSyncing(true);
    try {
      const r = await api.hbSyncNow(babyId);
      onChanged();
      const bits = [
        r.new_pending ? `${r.new_pending} new to review` : null,
        r.auto_imported ? `${r.auto_imported} auto-logged` : null,
        r.updated ? `${r.updated} updated` : null,
        r.deleted_upstream ? `${r.deleted_upstream} removed upstream` : null,
      ].filter(Boolean);
      notify('Synced', bits.length ? bits.join(' · ') : 'Nothing new.');
    } catch (e: any) {
      notify('Sync failed', e.message);
    } finally {
      setSyncing(false);
    }
  };

  const toggleAuto = async (v: boolean) => {
    try {
      await api.hbUpdate(babyId, { auto_import: v });
      onChanged();
    } catch (e: any) {
      notify('Could not save', e.message);
    }
  };

  const disconnect = () =>
    confirmDialog(
      'Disconnect Huckleberry?',
      'Feeds already imported stay. Pending items are discarded.',
      async () => {
        await api.hbDisconnect(babyId);
        onChanged();
      },
    );

  return (
    <>
      <SectionTitle>Huckleberry</SectionTitle>
      <Card>
        <Text style={{ color: colors.text, fontFamily: fonts.semibold }}>
          Connected to {status.child_name} <Muted>({status.hb_email})</Muted>
        </Text>
        <Muted style={{ marginTop: 4 }}>
          {status.status === 'ok'
            ? `Last synced ${status.last_synced_at ? fmtWhen(status.last_synced_at) : 'never'} · syncs every 2 hours`
            : `⚠︎ ${status.last_error ?? 'Sync problem — try reconnecting'}`}
        </Muted>
        <View style={styles.switchRow}>
          <View style={{ flex: 1, paddingRight: spacing.md }}>
            <Text style={{ color: colors.text, fontFamily: fonts.semibold }}>
              Auto-log from Huckleberry
            </Text>
            <Muted>
              Bottles (mixes split automatically), nursing (estimated from your
              latch rate), pumping, diapers and medications. Off = everything
              waits for review below.
            </Muted>
          </View>
          <Switch value={status.auto_import} onValueChange={toggleAuto} />
        </View>
        <Button title="Sync now" onPress={syncNow} loading={syncing} />
        <Button
          title="Disconnect"
          variant="danger"
          onPress={disconnect}
          style={{ marginTop: spacing.sm }}
        />
      </Card>
    </>
  );
}

// --------------------------------------------------------------------------- //
// Bottle type -> food mapping
// --------------------------------------------------------------------------- //
function MappingCard({
  babyId,
  status,
  onChanged,
}: {
  babyId: string;
  status: HbStatus;
  onChanged: () => void;
}) {
  const { foods } = useFoods();
  const liquids = foods.filter((f) => f.unit_basis === 'per_100ml' && !f.archived);
  // Draft split parts being edited, keyed by bottle type (null = not editing).
  const [drafts, setDrafts] = useState<Record<string, HbSplitPart[] | null>>({});

  const remap = async (
    bottleType: string,
    target: string | { food_id: string; parts: number }[] | { mode: 'recipe' },
  ) => {
    try {
      await api.hbUpdate(babyId, { mapping: { [bottleType]: target } });
      setDrafts((d) => ({ ...d, [bottleType]: null }));
      onChanged();
    } catch (e: any) {
      notify('Could not save', e.message);
    }
  };

  const startMix = (bt: string) => {
    const existing = status.mapping[bt]?.split;
    if (existing?.length) {
      setDrafts((d) => ({ ...d, [bt]: existing.map((p) => ({ ...p })) }));
      return;
    }
    const bm = liquids.find((f) => f.category === 'breast_milk');
    const ga1 =
      liquids.find((f) => f.category === 'metabolic_formula') ??
      liquids.find((f) => f.category === 'formula');
    if (!bm || !ga1) {
      notify('Missing foods', 'A mix needs a breast milk and a formula liquid food.');
      return;
    }
    setDrafts((d) => ({
      ...d,
      [bt]: [
        { food_id: bm.id, food_name: bm.name, parts: 40 },
        { food_id: ga1.id, food_name: ga1.name, parts: 20 },
      ],
    }));
  };

  return (
    <>
      <SectionTitle>What Huckleberry bottles mean here</SectionTitle>
      <Card>
        {MAPPED_TYPES.map((bt) => {
          const entry = status.mapping[bt];
          const draft = drafts[bt];
          const isMix = !!draft || !!entry?.split?.length;
          const isRecipe = !draft && !!entry?.recipe;
          return (
            <View key={bt} style={{ marginBottom: spacing.md }}>
              <Text style={styles.label}>
                Huckleberry "{bt}" →
                {isRecipe
                  ? ` split by the recipe in effect${
                      entry?.recipe_summary ? ` (now: ${entry.recipe_summary})` : ' (no recipe yet!)'
                    }`
                  : ''}
                {!draft && entry?.split?.length
                  ? ` mix, ${entry.split
                      .map((p) => `${fmtNum(p.parts)} ${p.food_name ?? ''}`)
                      .join(' + ')} (scaled to the logged ml)`
                  : ''}
              </Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
                {liquids.map((f) => (
                  <Chip
                    key={f.id}
                    label={f.name}
                    selected={!isMix && entry?.food_id === f.id}
                    onPress={() => remap(bt, f.id)}
                  />
                ))}
                <Chip label="Mixed 🍼+⚗️" selected={isMix} onPress={() => startMix(bt)} />
                <Chip label="Per recipe 🧪" selected={isRecipe} onPress={() => remap(bt, { mode: 'recipe' })} />
              </View>
              {draft ? (
                <View style={{ marginTop: spacing.sm }}>
                  {draft.map((p, i) => (
                    <View key={p.food_id} style={{ marginBottom: spacing.sm }}>
                      <Muted style={{ marginBottom: 4 }}>{p.food_name} (parts)</Muted>
                      <Stepper
                        value={p.parts}
                        onChange={(v) =>
                          setDrafts((d) => ({
                            ...d,
                            [bt]: d[bt]!.map((q, j) => (j === i ? { ...q, parts: v } : q)),
                          }))
                        }
                        step={5}
                        suffix="parts"
                      />
                    </View>
                  ))}
                  <Muted style={{ marginBottom: spacing.sm }}>
                    Parts are a ratio: 40+20 means a 45 ml bottle imports as 30 + 15.
                  </Muted>
                  <Button
                    title="Save mix"
                    onPress={() => {
                      if (draft.some((p) => p.parts <= 0)) {
                        notify('Check parts', 'Every part must be greater than 0.');
                        return;
                      }
                      remap(
                        bt,
                        draft.map((p) => ({ food_id: p.food_id, parts: p.parts })),
                      );
                    }}
                  />
                </View>
              ) : null}
            </View>
          );
        })}
        <Muted>
          "Other" is your mixed bottle. "Per recipe" splits each import by the recipe that was in
          effect at that feed's time (Settings → Recipe), so a plan change is a recipe edit, not a
          mapping edit. A fixed ratio is only right while the plan never changes.
        </Muted>
      </Card>
    </>
  );
}

// --------------------------------------------------------------------------- //
// Review imports
// --------------------------------------------------------------------------- //
function ImportsSection({
  babyId,
  defaultLatchRate,
  status,
  imports,
  onChanged,
}: {
  babyId: string;
  defaultLatchRate?: number;
  status: HbStatus;
  imports: HbImport[];
  onChanged: () => void;
}) {
  const pending = imports.filter((i) => i.status === 'pending');
  const deleted = imports.filter((i) => i.status === 'deleted_upstream');

  return (
    <>
      <SectionTitle>
        To review {pending.length + deleted.length > 0 ? `(${pending.length + deleted.length})` : ''}
      </SectionTitle>
      {pending.length + deleted.length === 0 ? (
        <Card>
          <Muted>Nothing waiting — new Huckleberry feeds show up here after each sync.</Muted>
        </Card>
      ) : (
        <>
          {pending.map((imp) => (
            <PendingRow
              key={imp.hb_key}
              babyId={babyId}
              imp={imp}
              defaultRate={status.latch_rate_ml_per_10min ?? defaultLatchRate ?? 20}
              onChanged={onChanged}
            />
          ))}
          {deleted.map((imp) => (
            <DeletedRow key={imp.hb_key} babyId={babyId} imp={imp} onChanged={onChanged} />
          ))}
        </>
      )}
    </>
  );
}

function PendingRow({
  babyId,
  imp,
  defaultRate,
  onChanged,
}: {
  babyId: string;
  imp: HbImport;
  defaultRate: number;
  onChanged: () => void;
}) {
  const [rate, setRate] = useState(defaultRate);
  const [busy, setBusy] = useState(false);
  const isBreast = imp.mode === 'breast';
  const estMl = isBreast ? ((imp.minutes ?? 0) * rate) / 10 : null;

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      onChanged();
    } catch (e: any) {
      notify('Failed', e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <Text style={{ color: colors.text, fontFamily: fonts.bold }}>{fmtWhen(imp.occurred_at)}</Text>
      <Text style={{ color: colors.text, marginTop: 2 }}>{describeImport(imp)}</Text>
      {imp.notes ? <Muted style={{ marginTop: 2 }}>“{imp.notes}”</Muted> : null}
      {isBreast && (
        <>
          <Text style={[styles.label, { marginTop: spacing.sm }]}>
            Estimate rate (ml per 10 min){estMl != null ? ` → ~${fmtNum(estMl)} ml` : ''}
          </Text>
          <Stepper value={rate} onChange={setRate} step={5} suffix="ml" />
        </>
      )}
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
        <Button
          title="Log it"
          onPress={() =>
            act(() =>
              api.hbConfirm(babyId, imp.hb_key, isBreast ? { rate_ml_per_10min: rate } : {}),
            )
          }
          loading={busy}
          style={{ flex: 1 }}
        />
        <Button
          title="Dismiss"
          variant="secondary"
          onPress={() => act(() => api.hbDismiss(babyId, imp.hb_key))}
          disabled={busy}
          style={{ flex: 1 }}
        />
      </View>
    </Card>
  );
}

function DeletedRow({
  babyId,
  imp,
  onChanged,
}: {
  babyId: string;
  imp: HbImport;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);

  const resolve = async (deleteFeed: boolean) => {
    setBusy(true);
    try {
      if (deleteFeed && imp.feed_id) await api.deleteFeed(imp.feed_id);
      await api.hbDismiss(babyId, imp.hb_key);
      onChanged();
    } catch (e: any) {
      notify('Failed', e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card style={{ borderColor: colors.danger }}>
      <Text style={{ color: colors.text, fontFamily: fonts.bold }}>{fmtWhen(imp.occurred_at)}</Text>
      <Text style={{ color: colors.text, marginTop: 2 }}>{describeImport(imp)}</Text>
      <Muted style={{ marginTop: 2 }}>
        This was deleted in Huckleberry after being logged here.
      </Muted>
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
        <Button
          title="Delete here too"
          variant="danger"
          onPress={() => resolve(true)}
          loading={busy}
          style={{ flex: 1 }}
        />
        <Button
          title="Keep the feed"
          variant="secondary"
          onPress={() => resolve(false)}
          disabled={busy}
          style={{ flex: 1 }}
        />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 13, fontFamily: fonts.semibold, color: colors.muted, marginBottom: 6 },
  error: {
    color: colors.danger,
    fontFamily: fonts.semibold,
    fontSize: 13.5,
    marginBottom: spacing.md,
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: spacing.md,
  },
});
