import DateTimePicker from '@react-native-community/datetimepicker';
import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, radius, spacing } from '../lib/theme';
import { fmtRelative } from '../lib/format';

const QUICK = [
  { label: 'Now', mins: 0 },
  { label: '15m ago', mins: 15 },
  { label: '30m ago', mins: 30 },
  { label: '1h ago', mins: 60 },
];

export function TimePickerRow({
  value,
  onChange,
}: {
  value: Date;
  onChange: (d: Date) => void;
}) {
  const [showPicker, setShowPicker] = useState(false);

  return (
    <View style={{ marginBottom: spacing.md }}>
      <Text style={styles.label}>When</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        {QUICK.map((q) => (
          <Pressable
            key={q.label}
            style={styles.quick}
            onPress={() => onChange(new Date(Date.now() - q.mins * 60000))}
          >
            <Text style={styles.quickText}>{q.label}</Text>
          </Pressable>
        ))}
        <Pressable style={[styles.quick, styles.timeChip]} onPress={() => setShowPicker(!showPicker)}>
          <Text style={[styles.quickText, { color: '#fff' }]}>
            {value.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} · {fmtRelative(value)}
          </Text>
        </Pressable>
      </View>
      {showPicker && (
        <DateTimePicker
          value={value}
          mode="datetime"
          display="spinner"
          maximumDate={new Date()}
          onChange={(_, d) => d && onChange(d)}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 13, fontWeight: '600', color: colors.muted, marginBottom: 6 },
  quick: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    marginRight: spacing.sm,
    marginBottom: spacing.sm,
  },
  timeChip: { backgroundColor: colors.primary },
  quickText: { fontWeight: '600', color: colors.text, fontSize: 13 },
});
