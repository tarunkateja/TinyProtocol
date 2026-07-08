import React, { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fonts, radius, spacing } from '../lib/theme';

/** Start/pause/reset timer for latch and pumping sessions. Reports elapsed
 * minutes upward on every tick so the form field stays in sync. */
export function SessionTimer({
  onMinutes,
  color = colors.primary,
}: {
  onMinutes: (minutes: number) => void;
  color?: string;
}) {
  const [running, setRunning] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const startRef = useRef<number | null>(null);
  const baseRef = useRef(0);

  useEffect(() => {
    if (!running) return;
    const iv = setInterval(() => {
      const ms = baseRef.current + (Date.now() - (startRef.current ?? Date.now()));
      setElapsedMs(ms);
      onMinutes(Math.max(0.5, Math.round(ms / 30000) / 2)); // half-minute steps
    }, 1000);
    return () => clearInterval(iv);
  }, [running]);

  const toggle = () => {
    if (running) {
      baseRef.current += Date.now() - (startRef.current ?? Date.now());
      setRunning(false);
    } else {
      startRef.current = Date.now();
      setRunning(true);
    }
  };

  const reset = () => {
    setRunning(false);
    baseRef.current = 0;
    setElapsedMs(0);
  };

  const mm = Math.floor(elapsedMs / 60000);
  const ss = Math.floor((elapsedMs % 60000) / 1000);

  return (
    <View style={styles.row}>
      <Text style={[styles.clock, { color }]}>
        {String(mm).padStart(2, '0')}:{String(ss).padStart(2, '0')}
      </Text>
      <Pressable style={[styles.btn, { backgroundColor: color }]} onPress={toggle}>
        <Text style={styles.btnText}>{running ? 'Pause' : elapsedMs ? 'Resume' : 'Start'}</Text>
      </Pressable>
      {elapsedMs > 0 && !running && (
        <Pressable style={[styles.btn, styles.resetBtn]} onPress={reset}>
          <Text style={[styles.btnText, { color: colors.muted }]}>Reset</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  clock: {
    fontSize: 34,
    fontFamily: fonts.heavy,
    fontVariant: ['tabular-nums'],
    minWidth: 108,
  },
  btn: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: radius.pill,
  },
  resetBtn: { backgroundColor: colors.border },
  btnText: { color: '#fff', fontFamily: fonts.bold, fontSize: 15 },
});
