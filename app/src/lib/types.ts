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
  lysine_mg_per_kg?: number | null;
  natural_protein_g_per_kg?: number | null;
  volume_targets?: VolumeTarget[];
}

export interface Baby {
  id: string;
  name: string;
  date_of_birth?: string | null;
  birth_weight_g?: number | null;
  conditions: string[];
  default_latch_rate_ml_per_10min: number;
  targets: Targets;
  current_weight_g?: number | null;
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
  | 'diaper'
  | 'weight';
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
  diaper_color?: string | null;
  diaper_consistency?: string | null;
  weight_g?: number | null;
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
  lysine_target_basis: string;
  protein_target_basis: string;
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
  pumpings: {
    id: string;
    occurred_at: string;
    pumped_ml: number;
    side?: string | null;
    duration_minutes?: number | null;
  }[];
  diaper_events: { id: string; occurred_at: string; diaper_kind: string; note?: string | null }[];
  weights: { id: string; occurred_at: string; weight_g: number }[];
  spit_ups: EventBrief[];
  vomits: EventBrief[];
  fussiness: EventBrief[];
  meds: { occurred_at: string; med_name: string; dose_amount?: number | null; dose_unit?: string | null }[];
  notes: EventBrief[];
  summary_text: string;
}

export interface DailyIntakeDay {
  day: string; // YYYY-MM-DD
  feed_count: number;
  total_ml: number;
  breast_milk_ml: number; // includes latch estimates
  formula_ml: number;
  metabolic_formula_ml: number;
  other_ml: number;
}

export interface DiaperDay {
  day: string;
  changes: number;
  pee: number;
  poop: number;
}

export interface PoopEvent {
  id: string;
  occurred_at: string;
  diaper_kind: DiaperKind;
  color?: string | null;
  consistency?: string | null;
  note?: string | null;
  gap_hours?: number | null; // since the previous poop
}

export interface DiaperSeries {
  baby_id: string;
  from_day: string;
  to_day: string;
  days: DiaperDay[];
  poops: PoopEvent[];
  last_poop_at?: string | null;
  hours_since_last_poop?: number | null;
  longest_gap_hours?: number | null;
  longest_gap_ended_at?: string | null;
  avg_gap_hours?: number | null;
}

export interface DailyIntakeSeries {
  baby_id: string;
  from_day: string;
  to_day: string;
  days: DailyIntakeDay[];
}

export interface WeightPoint {
  id: string;
  occurred_at: string;
  weight_g: number;
}

export interface WeightSeries {
  baby_id: string;
  date_of_birth?: string | null;
  birth_weight_g?: number | null;
  weights: WeightPoint[]; // ascending
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


// ---- v3: care & safety ----
export interface CareContact {
  label: string;
  phone: string;
  when?: string | null;
}

export interface CareProfile {
  patient: { name?: string | null; mrn?: string | null; dob?: string | null; diagnosis?: string | null };
  er_interventions: string[];
  when_to_call: string[];
  contacts: CareContact[];
  bring_to_er: string[];
  formula_ordering: string[];
  notes?: string | null;
  updated_at?: string | null;
}

export interface ClinicNote {
  id: string;
  text: string;
  done: boolean;
  created_by: string;
  created_at: string;
}

export interface LabResult {
  id: string;
  analyte: string;
  value: number;
  unit: string;
  collected_date: string;
  source_doc_id?: string | null;
}

export interface ExtractedLab {
  analyte: string;
  value: number;
  unit: string;
  collected_date: string;
}

export type DocStatus = 'uploaded' | 'processing' | 'ready' | 'error';

export interface CareDoc {
  id: string;
  title: string;
  filename: string;
  content_type: string;
  status: DocStatus;
  error?: string | null;
  summary?: string | null;
  extracted?: {
    doc_type: string;
    summary_points: string[];
    contacts: CareContact[];
    key_facts: string[];
    // Lab values found in the doc, awaiting parent review — empty
    // collected_date means the test date wasn't visible in the document.
    lab_results?: ExtractedLab[];
  } | null;
  lab_results_added: number;
  created_at: string;
}

export interface DocCreated {
  doc: CareDoc;
  upload_url: string;
  upload_content_type: string;
}

// --------------------------------------------------------------------------- //
// Huckleberry sync
// --------------------------------------------------------------------------- //
export type HbImportStatus = 'pending' | 'imported' | 'dismissed' | 'deleted_upstream';

export interface HbChild {
  uid: string;
  name: string;
}

export interface HbSplitPart {
  food_id: string;
  food_name?: string | null;
  parts: number;
}

export interface HbMappingEntry {
  food_id?: string | null;
  food_name?: string | null;
  split?: HbSplitPart[] | null;
  // Mixed bottle split by the recipe in effect at the feed's time.
  recipe?: boolean;
  recipe_summary?: string | null;
}

export interface HbStatus {
  connected: boolean;
  hb_email?: string | null;
  child_name?: string | null;
  auto_import: boolean;
  mapping: Record<string, HbMappingEntry>;
  latch_rate_ml_per_10min?: number | null;
  last_synced_at?: string | null;
  status?: string | null;
  last_error?: string | null;
  pending_count: number;
}

// Returned by connect when the Huckleberry account has several children.
export interface HbChildSelection {
  needs_child_selection: true;
  children: HbChild[];
}

export interface HbImport {
  baby_id: string;
  hb_key: string;
  status: HbImportStatus;
  mode: 'bottle' | 'breast' | 'diaper' | 'medication' | 'pumping';
  occurred_at: string;
  bottle_type?: string | null;
  amount_ml?: number | null;
  minutes?: number | null;
  diaper_kind?: string | null;
  pumped_ml?: number | null;
  side?: string | null;
  duration_minutes?: number | null;
  med_name?: string | null;
  dose_amount?: number | null;
  dose_unit?: string | null;
  notes?: string | null;
  food_id?: string | null;
  feed_id?: string | null;
}

export interface HbSyncResult {
  fetched: number;
  new_pending: number;
  auto_imported: number;
  updated: number;
  deleted_upstream: number;
}

// --------------------------------------------------------------------------- //
// Feeding recipes (effective-dated plan history)
// --------------------------------------------------------------------------- //
export interface RecipePowder {
  name: string;
  grams: number;
  food_id?: string | null;
}

export interface RecipeIn {
  label: string;
  effective_at: string; // ISO datetime
  breast_milk_ml: number;
  batch_ml: number;
  powders: RecipePowder[];
  batch_final_volume_ml?: number | null;
  feeds_per_day?: number | null;
  breast_milk_food_id?: string | null;
  batch_food_id?: string | null;
  source?: string | null;
  notes?: string | null;
}

export interface Recipe extends RecipeIn {
  id: string;
  created_at: string;
  prepared_ml: number;
  feeds_per_batch?: number | null;
}

export interface ResplitChange {
  feed_id: string;
  occurred_at: string;
  total_ml: number;
  recipe_label: string;
  before: Record<string, number>;
  after: Record<string, number>;
}

export interface ResplitResult {
  applied: boolean;
  changes: ResplitChange[];
  unchanged: number;
  skipped_no_recipe: number;
  skipped_unlinked: number;
}

// --------------------------------------------------------------------------- //
// MyChart (Epic patient FHIR) sync
// --------------------------------------------------------------------------- //
export type McImportKind = 'lab' | 'doc' | 'message';
export type McImportStatus = 'pending' | 'imported' | 'dismissed';

export interface McStatus {
  connected: boolean;
  configured: boolean;
  fhir_base?: string | null;
  scopes?: string | null;
  last_synced_at?: string | null;
  status?: string | null;
  last_error?: string | null;
  pending_labs: number;
  pending_docs: number;
  pending_messages: number;
  messages_available?: boolean | null;
}

export interface McImport {
  baby_id: string;
  mc_key: string;
  kind: McImportKind;
  status: McImportStatus;
  analyte?: string | null;
  value?: number | null;
  unit?: string | null;
  value_text?: string | null;
  reference_range?: string | null;
  collected_date?: string | null;
  title?: string | null;
  doc_date?: string | null;
  content_type?: string | null;
  sender?: string | null;
  sent_at?: string | null;
  text?: string | null;
}

export interface McSyncResult {
  labs_found: number;
  docs_found: number;
  messages_found: number;
  new_pending: number;
  messages_available?: boolean | null;
}
