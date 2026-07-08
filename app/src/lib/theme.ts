export const colors = {
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

/** One color identity per loggable thing — used on timeline cards, log
 * screens, and totals so each event type is recognizable at a glance. */
export const eventTheme: Record<string, EventTheme> = {
  feed: { color: '#D96A9C', soft: '#FBE9F1', icon: '🍼', label: 'Feed' },
  pumping: { color: '#2F9E96', soft: '#E1F2F0', icon: '🥛', label: 'Pumping' },
  diaper: { color: '#D99A2B', soft: '#FAF0DC', icon: '🧷', label: 'Diaper' },
  medication: { color: '#4A7FD4', soft: '#E7EEFA', icon: '💊', label: 'Medication' },
  spit_up: { color: '#E07B39', soft: '#FBECE0', icon: '💧', label: 'Spit-up' },
  vomit: { color: '#D64550', soft: '#FAE3E5', icon: '🤮', label: 'Vomit' },
  fussiness: { color: '#9061C2', soft: '#F0E7F9', icon: '😾', label: 'Fussy' },
  note: { color: '#7A7488', soft: '#F0EEF4', icon: '📝', label: 'Note' },
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };

export const radius = { sm: 8, md: 12, lg: 16, pill: 999 };
