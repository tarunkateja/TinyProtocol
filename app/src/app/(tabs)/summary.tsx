import { useQuery } from '@tanstack/react-query';
import * as Clipboard from 'expo-clipboard';
import React, { useState } from 'react';
import { Alert, ScrollView, Share, StyleSheet, Text, View } from 'react-native';

import { api } from '../../lib/api';
import { useBaby } from '../../lib/hooks';
import { colors, radius, spacing } from '../../lib/theme';
import { Button, Card, Chip, Muted } from '../../components/ui';

const WINDOWS = [12, 24, 48];

export default function SummaryScreen() {
  const { baby } = useBaby();
  const [hours, setHours] = useState(24);

  const q = useQuery({
    queryKey: ['summary', baby?.id, hours],
    queryFn: () => api.rollingSummary(baby!.id, hours),
    enabled: !!baby,
    refetchOnMount: 'always',
  });
  const s = q.data;

  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
      <Muted style={{ marginBottom: spacing.sm }}>
        A clean rundown to show or text your care team.
      </Muted>
      <View style={{ flexDirection: 'row', marginBottom: spacing.md }}>
        {WINDOWS.map((h) => (
          <Chip key={h} label={`Last ${h}h`} selected={hours === h} onPress={() => setHours(h)} />
        ))}
      </View>

      <Card style={styles.textCard}>
        <Text style={styles.summaryText}>
          {q.isLoading ? 'Building summary…' : s?.summary_text || 'Nothing logged in this window.'}
        </Text>
      </Card>

      <View style={{ flexDirection: 'row', gap: spacing.md }}>
        <Button
          title="Share"
          style={{ flex: 1 }}
          onPress={() => s && Share.share({ message: s.summary_text })}
        />
        <Button
          title="Copy"
          variant="secondary"
          style={{ flex: 1 }}
          onPress={async () => {
            if (!s) return;
            await Clipboard.setStringAsync(s.summary_text);
            Alert.alert('Copied', 'Summary copied to clipboard.');
          }}
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  textCard: {
    backgroundColor: '#FFFDF9',
    borderRadius: radius.lg,
    marginBottom: spacing.md,
  },
  summaryText: {
    fontFamily: 'Menlo',
    fontSize: 13.5,
    lineHeight: 21,
    color: colors.text,
  },
});
