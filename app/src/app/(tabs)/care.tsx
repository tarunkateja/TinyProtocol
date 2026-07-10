import { useRouter } from 'expo-router';
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import { colors, fonts, radius, spacing } from '../../lib/theme';
import { Muted } from '../../components/ui';

const LINKS: { icon: string; title: string; sub: string; href: string; danger?: boolean }[] = [
  {
    icon: '🆘',
    title: 'Emergency card',
    sub: 'ER instructions, when to call, care-team numbers — works offline',
    href: '/emergency',
    danger: true,
  },
  {
    icon: '📂',
    title: 'Care documents',
    sub: 'Upload clinic letters & lab reports — AI extracts the key info',
    href: '/docs',
  },
  {
    icon: '🧪',
    title: 'Lab results & trends',
    sub: 'Lysine, glutarylcarnitine and more over time',
    href: '/labs',
  },
  {
    icon: '📝',
    title: 'Clinic questions',
    sub: 'Collect questions for the next visit — both parents see them',
    href: '/clinic-notes',
  },
  {
    icon: '📚',
    title: 'GA1 references & sources',
    sub: 'Where the app’s guidance and numbers come from',
    href: '/references',
  },
];

export default function Care() {
  const router = useRouter();
  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      {LINKS.map((l) => (
        <Pressable
          key={l.href}
          onPress={() => router.push(l.href as any)}
          style={[styles.card, l.danger && styles.dangerCard]}
        >
          <Text style={styles.icon}>{l.icon}</Text>
          <Text style={styles.title}>{l.title}</Text>
          <Text style={styles.sub}>{l.sub}</Text>
        </Pressable>
      ))}
      <Muted style={{ textAlign: 'center', marginTop: spacing.sm }}>
        Nothing here is medical advice — always follow your metabolic team.
      </Muted>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  dangerCard: { borderColor: colors.danger, borderWidth: 1.5 },
  icon: { fontSize: 22, marginBottom: 4 },
  title: { fontFamily: fonts.heavy, color: colors.text, fontSize: 16 },
  sub: { fontFamily: fonts.regular, color: colors.muted, fontSize: 13, marginTop: 2 },
});
