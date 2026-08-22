import { Appearance, DynamicColorIOS, Platform } from 'react-native';

/**
 * Palette with dark mode for night feeds.
 *
 * Every screen builds its StyleSheet at module load from `colors`, so the
 * values can't change at runtime. On iOS we sidestep that with
 * DynamicColorIOS: the OS resolves light/dark natively and re-renders on its
 * own when the phone switches (including scheduled dark mode). Android and
 * web get a static palette chosen at launch from the system setting.
 */
const LIGHT = {
  bg: '#FBF7F1',
  card: '#FFFFFF',
  text: '#332E40',
  muted: '#8D8699',
  border: '#EFE7DC',
  primary: '#6C5FC7',
  primarySoft: '#ECE9FA',
  danger: '#D64550',
  success: '#3E8E5A',

  breastMilk: '#D96A9C',
  breastMilkSoft: '#FBE9F1',
  formula: '#3E8E87',
  formulaSoft: '#E3F2F0',
  metabolic: '#C98A2D',
  metabolicSoft: '#FAF0DE',
  event: '#7A7488',
  eventSoft: '#F0EEF4',
};

const DARK: typeof LIGHT = {
  bg: '#17151C',
  card: '#221F2A',
  text: '#EFEAF6',
  muted: '#9C95AA',
  border: '#332F3E',
  primary: '#9A8FE8',
  primarySoft: '#2C2748',
  danger: '#F06B74',
  success: '#5FBF7E',

  breastMilk: '#E98AB6',
  breastMilkSoft: '#3A2631',
  formula: '#5FB8AF',
  formulaSoft: '#1F3533',
  metabolic: '#E0A94E',
  metabolicSoft: '#3A2F1C',
  event: '#A39CB3',
  eventSoft: '#2A2733',
};

const startupDark = Appearance.getColorScheme() === 'dark';

/** A color that follows the system appearance (iOS live; others at launch).
 * Typed as string so the rest of the app stays unchanged — React Native
 * accepts the native dynamic color object anywhere a color string goes. */
export function dyn(light: string, dark: string): string {
  if (Platform.OS === 'ios' && typeof DynamicColorIOS === 'function') {
    return DynamicColorIOS({ light, dark }) as unknown as string;
  }
  return startupDark ? dark : light;
}

export const colors: typeof LIGHT = Object.fromEntries(
  (Object.keys(LIGHT) as (keyof typeof LIGHT)[]).map((k) => [k, dyn(LIGHT[k], DARK[k])]),
) as typeof LIGHT;

/** Plain hex for the scheme in effect at launch — for the few APIs that
 * need a real string (e.g. app-level status bar, web CSS). */
export const isDarkAtLaunch = startupDark;
export const staticColors = startupDark ? DARK : LIGHT;

export const fonts = {
  regular: 'Nunito_400Regular',
  semibold: 'Nunito_600SemiBold',
  bold: 'Nunito_700Bold',
  heavy: 'Nunito_800ExtraBold',
};

export interface EventTheme {
  color: string;
  soft: string;
  icon: string;
  label: string;
}

const ev = (light: string, dark: string, softLight: string, softDark: string, icon: string, label: string): EventTheme => ({
  color: dyn(light, dark),
  soft: dyn(softLight, softDark),
  icon,
  label,
});

/** One color identity per loggable thing — used on timeline cards, log
 * screens, and totals so each event type is recognizable at a glance. */
export const eventTheme: Record<string, EventTheme> = {
  feed: ev('#D96A9C', '#E98AB6', '#FBE9F1', '#3A2631', '🍼', 'Feed'),
  pumping: ev('#2F9E96', '#5FB8AF', '#E1F2F0', '#1F3533', '🥛', 'Pumping'),
  diaper: ev('#D99A2B', '#E0A94E', '#FAF0DC', '#3A2F1C', '🧷', 'Diaper'),
  medication: ev('#4A7FD4', '#7FA6EA', '#E7EEFA', '#1F2A44', '💊', 'Medication'),
  spit_up: ev('#E07B39', '#EE9A62', '#FBECE0', '#3C2A1E', '💧', 'Spit-up'),
  vomit: ev('#D64550', '#F06B74', '#FAE3E5', '#3D2226', '🤮', 'Vomit'),
  fussiness: ev('#9061C2', '#B48AE0', '#F0E7F9', '#2F2540', '😾', 'Fussy'),
  note: ev('#7A7488', '#A39CB3', '#F0EEF4', '#2A2733', '📝', 'Note'),
  weight: ev('#3E8E5A', '#5FBF7E', '#E3F2E9', '#1E3327', '⚖️', 'Weight'),
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };

export const radius = { sm: 8, md: 12, lg: 16, pill: 999 };
