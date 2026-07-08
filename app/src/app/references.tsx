import React from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import { colors, fonts, spacing } from '../lib/theme';
import { Card, Muted, SectionTitle } from '../components/ui';

const REFERENCES = [
  {
    title: 'BIMDG — GA1 Dietary Emergency Guidelines',
    what:
      'The UK metabolic-group protocol for GA1 sick days: start the emergency regimen (lysine-free formula + glucose polymer, day AND night) at the first fever, vomiting, diarrhea, or poor feeding; control fever; escalate to hospital if the regimen is not tolerated.',
    url: 'https://bimdg.org.uk/wp-content/uploads/2024/11/03112024_175726_GA1_DIETARY_EMERGENCY_GUIDELINES_WITH_LINKS_2017_294207_05042017.pdf',
    accessed: 'Jul 2026',
  },
  {
    title: 'GOV.UK — Glutaric aciduria type 1: detailed information',
    what:
      'Plain-language GA1 overview for families: why illness is dangerous (encephalopathic crisis risk, highest under age 6), when to contact the metabolic team, and why an emergency letter should travel with the baby.',
    url: 'https://www.gov.uk/government/publications/ga1-suspected-description-in-brief/glutaric-aciduria-type-1-ga1-detailed-information',
    accessed: 'Jul 2026',
  },
  {
    title: 'GMDI/SERN — GA1 Nutrition Management Guideline',
    what:
      'The US dietitian guideline behind per-kg targets: lysine intake for GA1 infants 0–6 months is typically 65–100 mg/kg/day, adjusted against growth and plasma amino-acid results — which is why this app recalculates targets from weight.',
    url: 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7602866/',
    accessed: 'Jul 2026',
  },
  {
    title: 'WHO Child Growth Standards',
    what:
      'The reference curves for infant weight — useful context for the weights you log here; your pediatrician plots Tara against these.',
    url: 'https://www.who.int/tools/child-growth-standards/standards',
    accessed: 'Jul 2026',
  },
  {
    title: 'USDA FoodData Central — Milk, human, mature (FDC 171279)',
    what:
      'Source of the seeded breast-milk nutrition values: 1.03 g protein and 68 mg lysine per 100 g (≈1.0 g / 70 mg per 100 ml after density conversion). Formula values must come from your product label.',
    url: 'https://fdc.nal.usda.gov/fdc-app.html#/food-details/171279/nutrients',
    accessed: 'Jul 2026',
  },
];

export default function References() {
  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 60 }}>
      <Muted style={{ marginBottom: spacing.sm }}>
        Where this app's GA1 guidance and numbers come from. Tara's own clinic
        documents live under Care documents — those always take precedence.
      </Muted>
      {REFERENCES.map((r) => (
        <Card key={r.title} style={{ marginBottom: spacing.sm }}>
          <Text style={styles.title}>{r.title}</Text>
          <Text style={styles.what}>{r.what}</Text>
          <Pressable onPress={() => Linking.openURL(r.url)}>
            <Text style={styles.link}>🔗 Open source (accessed {r.accessed})</Text>
          </Pressable>
        </Card>
      ))}
      <SectionTitle>Important</SectionTitle>
      <Card>
        <Text style={styles.what}>
          Nothing in this app is medical advice. Targets, regimens, and doses come from
          Tara's metabolic team at Lurie Children's — these references exist so you can
          read the underlying guidance and ask better questions, not to replace it.
        </Text>
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  title: { fontFamily: fonts.heavy, color: colors.text, fontSize: 15, marginBottom: 4 },
  what: { fontFamily: fonts.regular, color: colors.text, fontSize: 13.5, lineHeight: 20 },
  link: { color: colors.primary, fontFamily: fonts.bold, fontSize: 13, marginTop: 8 },
});
