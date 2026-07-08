import { useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { api } from '../lib/api';
import { colors, fonts, radius, spacing } from '../lib/theme';
import type { ClinicNote } from '../lib/types';
import { Muted } from '../components/ui';

export default function ClinicNotes() {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const notesQ = useQuery({ queryKey: ['clinicNotes'], queryFn: api.listClinicNotes });

  const refresh = () => qc.invalidateQueries({ queryKey: ['clinicNotes'] });

  const add = async () => {
    const t = text.trim();
    if (!t) return;
    setText('');
    await api.createClinicNote(t);
    refresh();
  };

  const toggle = async (n: ClinicNote) => {
    await api.updateClinicNote(n.id, { done: !n.done });
    refresh();
  };

  const remove = (n: ClinicNote) => {
    Alert.alert('Delete this question?', n.text, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          await api.deleteClinicNote(n.id);
          refresh();
        },
      },
    ]);
  };

  return (
    <View style={{ flex: 1, padding: spacing.lg }}>
      <Muted style={{ marginBottom: spacing.sm }}>
        Jot questions for the metabolic team as they occur — the AI includes open ones
        when drafting clinic updates. Shared with your partner.
      </Muted>
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          placeholder="Ask the team about…"
          placeholderTextColor={colors.muted}
          value={text}
          onChangeText={setText}
          onSubmitEditing={add}
          returnKeyType="done"
        />
        <Pressable style={[styles.addBtn, !text.trim() && { opacity: 0.4 }]} onPress={add} disabled={!text.trim()}>
          <Text style={styles.addText}>＋</Text>
        </Pressable>
      </View>

      <FlatList
        data={notesQ.data ?? []}
        keyExtractor={(n) => n.id}
        refreshing={notesQ.isRefetching}
        onRefresh={() => notesQ.refetch()}
        ListEmptyComponent={
          <Muted style={{ textAlign: 'center', marginTop: 30 }}>
            {notesQ.isLoading ? 'Loading…' : 'No questions yet.'}
          </Muted>
        }
        renderItem={({ item }) => (
          <Pressable style={styles.row} onPress={() => toggle(item)} onLongPress={() => remove(item)}>
            <Text style={styles.check}>{item.done ? '☑' : '☐'}</Text>
            <View style={{ flex: 1 }}>
              <Text style={[styles.noteText, item.done && styles.doneText]}>{item.text}</Text>
              <Muted>{item.created_by}</Muted>
            </View>
          </Pressable>
        )}
      />
      <Muted style={{ textAlign: 'center' }}>Tap to check off · long-press to delete.</Muted>
    </View>
  );
}

const styles = StyleSheet.create({
  inputRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
  input: {
    flex: 1,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    fontFamily: fonts.regular,
    color: colors.text,
  },
  addBtn: {
    width: 46,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addText: { color: '#fff', fontSize: 24, fontFamily: fonts.heavy },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  check: { fontSize: 20, color: colors.primary },
  noteText: { color: colors.text, fontSize: 15, fontFamily: fonts.semibold },
  doneText: { textDecorationLine: 'line-through', color: colors.muted },
});
