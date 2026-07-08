export type FoodCategory = 'breast_milk' | 'formula' | 'metabolic_formula' | 'other';
export type UnitBasis = 'per_100ml' | 'per_scoop';
export type DoseUnit = 'mg' | 'ml';

export interface Food {
  id: string;
  name: string;
  category: FoodCategory;
  unit_basis: UnitBasis;
  natural_protein_g_per_unit: number;
  lysine_mg_per_unit: number;
  description?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  needs_dietitian_verification: boolean;
  archived: boolean;
}

export interface MedPreset {
  id: string;
  name: string;
  dose_unit: DoseUnit;
  default_dose?: number | null;
  concentration_mg_per_ml?: number | null;
  notes?: string | null;
}

export type VolumeCategory = 'breast_milk' | 'formula' | 'metabolic_formula';

export interface VolumeTarget {
  category: VolumeCategory;
  direction: 'min' | 'max';
  ml_per_day: number;
}

export interface Targets {
  lysine_mg_per_day?: number | null;
  natural_protein_g_per_day?: number | null;
  volume_targets?: VolumeTarget[];
}

export interface Baby {
  id: string;
  name: string;
  date_of_birth?: string | null;
  conditions: string[];
  default_latch_rate_ml_per_10min: number;
  targets: Targets;
}

export type FeedComponentIn =
  | { kind: 'liquid'; food_id: string; volume_ml: number }
  | { kind: 'powder'; food_id: string; scoops: number }
  | {
      kind: 'latch';
      food_id: string;
      minutes: number;
      rate_ml_per_10min: number;
      measured_ml?: number | null;
    };

export interface ComponentSnapshot {
  kind: 'liquid' | 'powder' | 'latch';
  food_id: string;
  food_name: string;
  food_category: FoodCategory;
  effective_ml: number;
  natural_protein_g: number;
  lysine_mg: number;
  is_estimated: boolean;
  volume_ml?: number;
  scoops?: number;
  minutes?: number;
  rate_ml_per_10min?: number;
  measured_ml?: number | null;
}

export interface FeedTotals {
  total_ml: number;
  breast_milk_ml: number;
  formula_ml: number;
  metabolic_formula_ml: number;
  other_ml: number;
  formula_scoops: number;
  metabolic_formula_scoops: number;
  natural_protein_g: number;
  lysine_mg: number;
}

export interface Feed {
  item_type: 'FEED';
  id: string;
  baby_id: string;
  occurred_at: string;
  components: ComponentSnapshot[];
  totals: FeedTotals;
  notes?: string | null;
}

export type EventType =
  | 'spit_up'
  | 'vomit'
  | 'fussiness'
  | 'medication'
  | 'note'
  | 'pumping'
  | 'diaper';
export type Severity = 'small' | 'medium' | 'large';
export type PumpSide = 'left' | 'right' | 'both';
export type DiaperKind = 'pee' | 'poop' | 'both';

export interface CareEvent {
  item_type: 'EVENT';
  id: string;
  baby_id: string;
  occurred_at: string;
  type: EventType;
  severity?: Severity | null;
  related_feed_id?: string | null;
  med_name?: string | null;
  dose_amount?: number | null;
  dose_unit?: DoseUnit | null;
  pumped_ml?: number | null;
  side?: PumpSide | null;
  duration_minutes?: number | null;
  diaper_kind?: DiaperKind | null;
  note?: string | null;
}

export interface FeedPreset {
  id: string;
  name: string;
  components: FeedComponentIn[];
}

export interface ChatMeta {
  id: string;
  baby_id: string;
  title: string;
  created_by: string;
  updated_at: string;
}

export interface ChatFull extends ChatMeta {
  messages: { role: 'user' | 'assistant'; content: string; at?: string }[];
}

export interface ChatReply {
  chat: ChatFull;
  reply: string;
}

export type TimelineEntry = Feed | CareEvent;

export interface BreastMilkBreakdown {
  pumped_ml: number;
  latch_estimated_ml: number;
  latch_measured_ml: number;
  total_ml: number;
}

export interface Summary {
  baby_id: string;
  baby_name: string;
  window_from: string;
  window_to: string;
  day?: string | null;
  feed_count: number;
  total_ml: number;
  breast_milk: BreastMilkBreakdown;
  formula_ml: number;
  formula_scoops: number;
  metabolic_formula_ml: number;
  metabolic_formula_scoops: number;
  other_ml: number;
  natural_protein_g: number;
  lysine_mg: number;
  targets: Targets;
  pct_of_lysine_target?: number | null;
  pct_of_protein_target?: number | null;
  volume_targets: {
    category: VolumeCategory;
    direction: 'min' | 'max';
    target_ml: number;
    actual_ml: number;
    estimated_ml: number;
    status: 'under' | 'met' | 'over';
  }[];
  pumped_output_ml: number;
  pumping_sessions: number;
  pumped_vs_fed: { pumped_ml: number; fed_ml: number; net_ml: number };
  diapers: { pee: number; poop: number; changes: number };
  window_label: string;
  feeds: { id: string; occurred_at: string; total_ml: number; description: string }[];
  spit_ups: EventBrief[];
  vomits: EventBrief[];
  fussiness: EventBrief[];
  meds: { occurred_at: string; med_name: string; dose_amount?: number | null; dose_unit?: string | null }[];
  notes: EventBrief[];
  summary_text: string;
}

export interface EventBrief {
  id: string;
  occurred_at: string;
  type: EventType;
  severity?: Severity | null;
  note?: string | null;
}

export interface User {
  id: string;
  email: string;
  name: string;
  family_id: string;
}

export interface TokenResponse {
  access_token: string;
  user: User;
}

export interface RhythmConfig {
  enabled: boolean;
  interval_hours: number;
}

export interface Family {
  id: string;
  name?: string | null;
  timezone: string;
  day_start: string; // "HH:MM" — when the family's day begins
  rhythms: { feed: RhythmConfig; med: RhythmConfig };
  members: { email: string; name: string; role: string }[];
}
