import DateTimePicker from '@react-native-community/datetimepicker';
import React from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from 'react-native';

import { colors, fonts, radius, spacing } from '../lib/theme';

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Button({
  title,
  onPress,
  variant = 'primary',
  disabled,
  loading,
  style,
}: {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
}) {
  const bg =
    variant === 'primary' ? colors.primary : variant === 'danger' ? colors.danger : colors.primarySoft;
  const fg = variant === 'secondary' ? colors.primary : '#fff';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <Text style={[styles.buttonText, { color: fg }]}>{title}</Text>
      )}
    </Pressable>
  );
}

export function Chip({
  label,
  selected,
  onPress,
  color = colors.primary,
  softColor = colors.primarySoft,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
  color?: string;
  softColor?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.chip,
        { backgroundColor: selected ? color : softColor, borderColor: selected ? color : 'transparent' },
      ]}
    >
      <Text style={{ color: selected ? '#fff' : colors.text, fontFamily: fonts.semibold, fontSize: 14 }}>
        {label}
      </Text>
    </Pressable>
  );
}

export function Field({
  label,
  suffix,
  ...inputProps
}: TextInputProps & { label?: string; suffix?: string }) {
  return (
    <View style={{ marginBottom: spacing.md }}>
      {label ? <Text style={styles.fieldLabel}>{label}</Text> : null}
      <View style={styles.inputRow}>
        <TextInput
          placeholderTextColor={colors.muted}
          style={styles.input}
          {...inputProps}
        />
        {suffix ? <Text style={styles.suffix}>{suffix}</Text> : null}
      </View>
    </View>
  );
}

/** Numeric input with +/- steppers, tuned for one-handed 3am logging. */
export function Stepper({
  value,
  onChange,
  step = 5,
  suffix,
  min = 0,
}: {
  value: number;
  onChange: (v: number) => void;
  step?: number;
  suffix?: string;
  min?: number;
}) {
  const [text, setText] = React.useState<string | null>(null);
  const shown = text ?? (value ? String(value) : '');
  return (
    <View style={styles.stepperRow}>
      <Pressable style={styles.stepBtn} onPress={() => onChange(Math.max(min, +(value - step).toFixed(2)))}>
        <Text style={styles.stepBtnText}>−</Text>
      </Pressable>
      <View style={[styles.inputRow, { flex: 1 }]}>
        <TextInput
          keyboardType="decimal-pad"
          value={shown}
          onChangeText={(t) => {
            setText(t);
            const n = parseFloat(t.replace(',', '.'));
            onChange(Number.isFinite(n) ? n : 0);
          }}
          onBlur={() => setText(null)}
          placeholder="0"
          placeholderTextColor={colors.muted}
          style={[styles.input, { textAlign: 'center' }]}
        />
        {suffix ? <Text style={styles.suffix}>{suffix}</Text> : null}
      </View>
      <Pressable style={styles.stepBtn} onPress={() => onChange(+(value + step).toFixed(2))}>
        <Text style={styles.stepBtnText}>+</Text>
      </Pressable>
    </View>
  );
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

function ymd(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

/** A calendar date (YYYY-MM-DD string). Native: tap to open the system
 * picker (inline on iOS, dialog on Android); web: a typed field. */
export function DateField({
  label,
  value,
  onChange,
  placeholder = 'YYYY-MM-DD',
  maximumDate,
}: {
  label?: string;
  value: string;
  onChange: (ymd: string) => void;
  placeholder?: string;
  maximumDate?: Date;
}) {
  const [open, setOpen] = React.useState(false);
  if (Platform.OS === 'web') {
    return <Field label={label} value={value} onChangeText={onChange} placeholder={placeholder} autoCapitalize="none" />;
  }
  const parsed = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00`) : null;
  const shown = parsed
    ? parsed.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
    : '';
  return (
    <View style={{ marginBottom: spacing.md }}>
      {label ? <Text style={styles.fieldLabel}>{label}</Text> : null}
      <Pressable style={styles.inputRow} onPress={() => setOpen((o) => !o)}>
        <Text style={[styles.input, { paddingVertical: 12 }, !shown && { color: colors.muted }]}>
          {shown || placeholder}
        </Text>
        <Text style={styles.suffix}>{open ? 'done' : 'change'}</Text>
      </Pressable>
      {open && (
        <DateTimePicker
          value={parsed ?? new Date()}
          mode="date"
          display={Platform.OS === 'ios' ? 'inline' : 'default'}
          maximumDate={maximumDate}
          onChange={(e, d) => {
            if (Platform.OS !== 'ios') setOpen(false);
            if (d && e.type !== 'dismissed') onChange(ymd(d));
          }}
        />
      )}
    </View>
  );
}

/** A date + time of day (Date value). Native: system picker; web: two fields. */
export function DateTimeField({
  label,
  value,
  onChange,
  maximumDate,
}: {
  label?: string;
  value: Date;
  onChange: (d: Date) => void;
  maximumDate?: Date;
}) {
  const [open, setOpen] = React.useState(false);
  const [mode, setMode] = React.useState<'date' | 'time'>('date');
  if (Platform.OS === 'web') {
    const date = ymd(value);
    const time = `${pad2(value.getHours())}:${pad2(value.getMinutes())}`;
    const set = (d: string, t: string) => {
      const next = new Date(`${d}T${t}:00`);
      if (!Number.isNaN(next.getTime())) onChange(next);
    };
    return (
      <View style={{ marginBottom: spacing.md }}>
        {label ? <Text style={styles.fieldLabel}>{label}</Text> : null}
        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <View style={{ flex: 3 }}>
            <Field value={date} onChangeText={(v) => set(v, time)} placeholder="YYYY-MM-DD" autoCapitalize="none" />
          </View>
          <View style={{ flex: 2 }}>
            <Field value={time} onChangeText={(v) => set(date, v)} placeholder="HH:MM" autoCapitalize="none" />
          </View>
        </View>
      </View>
    );
  }
  const shown = value.toLocaleString([], {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
  return (
    <View style={{ marginBottom: spacing.md }}>
      {label ? <Text style={styles.fieldLabel}>{label}</Text> : null}
      <Pressable
        style={styles.inputRow}
        onPress={() => {
          setMode('date');
          setOpen((o) => !o);
        }}
      >
        <Text style={[styles.input, { paddingVertical: 12 }]}>{shown}</Text>
        <Text style={styles.suffix}>{open ? 'done' : 'change'}</Text>
      </Pressable>
      {open && (
        <DateTimePicker
          value={value}
          mode={Platform.OS === 'ios' ? 'datetime' : mode}
          display={Platform.OS === 'ios' ? 'spinner' : 'default'}
          maximumDate={maximumDate}
          onChange={(e, d) => {
            if (e.type === 'dismissed') {
              setOpen(false);
              return;
            }
            if (!d) return;
            if (Platform.OS === 'ios') {
              onChange(d);
              return;
            }
            // Android: the dialog is single-purpose — date first, then time.
            if (mode === 'date') {
              const next = new Date(value);
              next.setFullYear(d.getFullYear(), d.getMonth(), d.getDate());
              onChange(next);
              setMode('time');
            } else {
              const next = new Date(value);
              next.setHours(d.getHours(), d.getMinutes(), 0, 0);
              onChange(next);
              setOpen(false);
            }
          }}
        />
      )}
    </View>
  );
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

export function Muted({ children, style }: { children: React.ReactNode; style?: object }) {
  return <Text style={[{ color: colors.muted, fontSize: 13, fontFamily: fonts.regular }, style]}>{children}</Text>;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  button: {
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: { fontSize: 16, fontFamily: fonts.bold },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: radius.pill,
    borderWidth: 1,
    marginRight: spacing.sm,
    marginBottom: spacing.sm,
  },
  fieldLabel: { fontSize: 13, fontFamily: fonts.semibold, color: colors.muted, marginBottom: 6 },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: 12,
  },
  // minWidth 0 lets the input shrink inside narrow flex slots (two-up
  // steppers) on web, where <input> otherwise has an intrinsic min width.
  input: { flex: 1, minWidth: 0, paddingVertical: 12, fontSize: 16, color: colors.text, fontFamily: fonts.regular },
  suffix: { color: colors.muted, fontSize: 14, marginLeft: 6 },
  stepperRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  stepBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepBtnText: { fontSize: 22, fontFamily: fonts.bold, color: colors.primary },
  sectionTitle: {
    fontSize: 15,
    fontFamily: fonts.heavy,
    color: colors.text,
    marginBottom: spacing.sm,
    marginTop: spacing.md,
  },
});
