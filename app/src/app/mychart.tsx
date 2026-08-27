import { useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { Linking, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../lib/api';
import { showAlert } from '../lib/dialogs';
import { fmtNum } from '../lib/format';
import { useBaby } from '../lib/hooks';
import { colors, fonts, spacing } from '../lib/theme';
import type { McImport } from '../lib/types';
import { Button, Card, Muted, SectionTitle } from '../components/ui';

/** MyChart sync: labs, clinic documents and (where Lurie allows) messages,
 * pulled through Epic's official patient APIs. Review-first, like the
 * Huckleberry sync — nothing lands in the log without a confirm. */
export default function MyChart() {
  const qc = useQueryClient();
  const { baby } = useBaby();
  const [busy, setBusy] = useState<string | null>(null);

  const statusQ = useQuery({
    queryKey: ['mc-status', baby?.id],
    queryFn: () => api.mcStatus(baby!.id),
    enabled: !!baby,
    refetchInterval: 15_000, // picks the connection up after the browser dance
  });
  const importsQ = useQuery({
    queryKey: ['mc-imports', baby?.id],
    queryFn: () => api.mcImports(baby!.id, 'pending'),
    enabled: !!baby && !!statusQ.data?.connected,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['mc-status'] });
    qc.invalidateQueries({ queryKey: ['mc-imports'] });
    qc.invalidateQueries({ queryKey: ['labs'] });
  };

  const connect = async () => {
    if (!baby) return;
    try {
      const { url } = await api.mcConnectUrl(baby.id);
      await Linking.openURL(url);
    } catch (e: any) {
      showAlert('Could not start', e.message);
    }
  };

  const syncNow = async () => {
    if (!baby) return;
    setBusy('sync');
    try {
      const r = await api.mcSyncNow(baby.id);
      refresh();
      showAlert('Synced', `${r.new_pending} new item${r.new_pending === 1 ? '' : 's'} to review.`);
    } catch (e: any) {
      showAlert('Sync failed', e.message);
    } finally {
      setBusy(null);
    }
  };

  const confirm = async (imp: McImport) => {
    if (!baby) return;
    setBusy(imp.mc_key);
    try {
      await api.mcConfirm(baby.id, imp.mc_key);
      refresh();
    } catch (e: any) {
      showAlert('Could not import', e.message);
    } finally {
      setBusy(null);
    }
  };

  const dismiss = async (imp: McImport) => {
    if (!baby) return;
    setBusy(imp.mc_key);
    try {
      await api.mcDismiss(baby.id, imp.mc_key);
      refresh();
    } catch (e: any) {
      showAlert('Could not dismiss', e.message);
    } finally {
      setBusy(null);
    }
  };

  if (!baby) return null;
  const s = statusQ.data;
  const items = importsQ.data?.items ?? [];
  const labs = items.filter((i) => i.kind === 'lab');
  const docs = items.filter((i) => i.kind === 'doc');
  const messages = items.filter((i) => i.kind === 'message');

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      {!s ? null : !s.configured ? (
        <Card>
          <Text style={styles.line}>MyChart sync isn't switched on yet.</Text>
          <Muted style={{ marginTop: 4 }}>
            It needs a one-time Epic app registration (free). Ask Claude to walk you through it —
            after that, this screen connects with your MyChart login.
          </Muted>
        </Card>
      ) : !s.connected ? (
        <Card>
          <Text style={styles.line}>
            Connect with your MyChart login (the one with proxy access to {baby.name}). You sign in
            on MyChart's own page — the password never touches this app.
          </Text>
          <Muted style={{ marginTop: 4 }}>
            Pulls lab results and clinic documents through Lurie's official patient API, every 30
            minutes, as review-first items.
          </Muted>
          <Button title="🏥 Connect MyChart" onPress={connect} style={{ marginTop: spacing.md }} />
        </Card>
      ) : (
        <>
          <Card>
            <Text style={styles.line}>
              ✓ Connected{s.last_synced_at ? ` · synced ${new Date(s.last_synced_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}` : ''}
            </Text>
            {s.status === 'auth_expired' ? (
              <>
                <Muted style={{ marginTop: 4 }}>Session expired — reconnect below.</Muted>
                <Button title="Reconnect" onPress={connect} style={{ marginTop: spacing.sm }} />
              </>
            ) : null}
            {s.last_error ? <Muted style={{ marginTop: 4 }}>⚠︎ {s.last_error}</Muted> : null}
            {s.messages_available === false ? (
              <Muted style={{ marginTop: 4 }}>
                Messages: Lurie doesn't expose MyChart messages to apps — paste important ones into
                Care notes instead.
              </Muted>
            ) : null}
            <Button title="Sync now" variant="secondary" onPress={syncNow} loading={busy === 'sync'} style={{ marginTop: spacing.md }} />
          </Card>

          <SectionTitle>Lab results to review ({labs.length})</SectionTitle>
          {labs.length === 0 ? (
            <Muted>Nothing waiting.</Muted>
          ) : (
            labs.map((imp) => (
              <Card key={imp.mc_key} style={{ paddingVertical: spacing.md }}>
                <Text style={styles.itemTitle}>
                  {imp.analyte} {imp.value != null ? `· ${fmtNum(imp.value, 2)} ${imp.unit}` : `· ${imp.value_text ?? ''}`}
                </Text>
                <Muted>
                  {imp.collected_date ?? 'no date'}
                  {imp.reference_range ? ` · ref ${imp.reference_range}` : ''}
                </Muted>
                <View style={styles.actions}>
                  {imp.value != null && (
                    <Button title="Add to Labs" onPress={() => confirm(imp)} loading={busy === imp.mc_key} style={{ flex: 1 }} />
                  )}
                  <Button title="Skip" variant="secondary" onPress={() => dismiss(imp)} style={{ flex: 1 }} />
                </View>
              </Card>
            ))
          )}

          <SectionTitle>Documents to review ({docs.length})</SectionTitle>
          {docs.length === 0 ? (
            <Muted>Nothing waiting.</Muted>
          ) : (
            docs.map((imp) => (
              <Card key={imp.mc_key} style={{ paddingVertical: spacing.md }}>
                <Text style={styles.itemTitle}>{imp.title}</Text>
                <Muted>
                  {imp.doc_date ?? ''}
                  {imp.content_type ? ` · ${imp.content_type === 'application/pdf' ? 'PDF' : 'image'}` : ' · no importable copy'}
                </Muted>
                <View style={styles.actions}>
                  {imp.content_type && (
                    <Button title="Import to Docs" onPress={() => confirm(imp)} loading={busy === imp.mc_key} style={{ flex: 1 }} />
                  )}
                  <Button title="Skip" variant="secondary" onPress={() => dismiss(imp)} style={{ flex: 1 }} />
                </View>
              </Card>
            ))
          )}

          {messages.length > 0 && (
            <>
              <SectionTitle>Messages to review ({messages.length})</SectionTitle>
              {messages.map((imp) => (
                <Card key={imp.mc_key} style={{ paddingVertical: spacing.md }}>
                  <Text style={styles.itemTitle}>
                    {imp.sender ?? 'Care team'} {imp.sent_at ? `· ${imp.sent_at}` : ''}
                  </Text>
                  <Text style={styles.line} numberOfLines={6}>
                    {imp.text}
                  </Text>
                  <View style={styles.actions}>
                    <Button title="Save to Care notes" onPress={() => confirm(imp)} loading={busy === imp.mc_key} style={{ flex: 1 }} />
                    <Button title="Skip" variant="secondary" onPress={() => dismiss(imp)} style={{ flex: 1 }} />
                  </View>
                </Card>
              ))}
            </>
          )}

          <Button
            title="Disconnect MyChart"
            variant="danger"
            onPress={() =>
              showAlert('Disconnect MyChart?', 'Already-imported labs and docs stay.', [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Disconnect',
                  style: 'destructive',
                  onPress: async () => {
                    await api.mcDisconnect(baby.id);
                    refresh();
                  },
                },
              ])
            }
            style={{ marginTop: spacing.lg }}
          />
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  line: { fontSize: 15, color: colors.text, fontFamily: fonts.regular },
  itemTitle: { fontSize: 15, fontFamily: fonts.bold, color: colors.text, marginBottom: 2 },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
});
