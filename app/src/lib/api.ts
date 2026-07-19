import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

import type {
  Baby,
  CareDoc,
  CareEvent,
  CareProfile,
  ClinicNote,
  DocCreated,
  LabResult,
  ChatFull,
  ChatMeta,
  ChatReply,
  DailyIntakeSeries,
  Family,
  Feed,
  FeedComponentIn,
  FeedPreset,
  Food,
  HbChildSelection,
  HbImport,
  HbStatus,
  HbSyncResult,
  MedPreset,
  Summary,
  Targets,
  TimelineEntry,
  TokenResponse,
  WeightSeries,
} from './types';

export const API_URL =
  process.env.EXPO_PUBLIC_API_URL ?? 'https://z7yrwag4b4.execute-api.us-east-1.amazonaws.com';

const TOKEN_KEY = 'tinyprotocol_token';

// SecureStore has no web implementation; fall back to localStorage so the
// web build (used for dev checks) can run.
const store =
  Platform.OS === 'web'
    ? {
        getItemAsync: async (k: string) => globalThis.localStorage?.getItem(k) ?? null,
        setItemAsync: async (k: string, v: string) => {
          globalThis.localStorage?.setItem(k, v);
        },
        deleteItemAsync: async (k: string) => {
          globalThis.localStorage?.removeItem(k);
        },
      }
    : SecureStore;

let _token: string | null = null;

export async function loadToken(): Promise<string | null> {
  if (_token) return _token;
  _token = await store.getItemAsync(TOKEN_KEY);
  return _token;
}

export async function setToken(token: string | null) {
  _token = token;
  if (token) await store.setItemAsync(TOKEN_KEY, token);
  else await store.deleteItemAsync(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (_token) headers.Authorization = `Bearer ${_token}`;

  const resp = await fetch(`${API_URL}/v1${path}`, { ...options, headers });
  if (!resp.ok) {
    let detail = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (typeof body.detail === 'string') detail = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg)
        detail = body.detail[0].msg;
    } catch {}
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' });

export const api = {
  // auth
  register: (body: {
    email: string;
    password: string;
    name: string;
    timezone: string;
    baby?: { name: string; conditions: string[] };
  }) => post<TokenResponse>('/auth/register', body),
  login: (body: { email: string; password: string }) =>
    post<TokenResponse>('/auth/login', body),
  join: (body: { email: string; password: string; name: string; invite_code: string }) =>
    post<TokenResponse>('/auth/join', body),
  createInvite: () => post<{ code: string; expires_at: string }>('/auth/invites'),
  me: () => get<{ user: TokenResponse['user']; family: Family }>('/me'),
  updateFamily: (body: Partial<Pick<Family, 'name' | 'timezone' | 'day_start' | 'rhythms'>>) =>
    patch<Family>('/family', body),

  // babies
  listBabies: () => get<Baby[]>('/babies'),
  createBaby: (body: { name: string; conditions?: string[] }) =>
    post<Baby>('/babies', body),
  updateBaby: (
    id: string,
    body: Partial<{
      name: string;
      date_of_birth: string;
      birth_weight_g: number;
      default_latch_rate_ml_per_10min: number;
      targets: Targets;
      // When the new targets took effect (YYYY-MM-DD, defaults to today).
      targets_effective_from: string;
    }>,
  ) => patch<Baby>(`/babies/${id}`, body),
  targetHistory: (id: string) =>
    get<{ effective_date: string; targets: Targets }[]>(`/babies/${id}/target-history`),
  deleteTargetPeriod: (id: string, effectiveDate: string) =>
    del(`/babies/${id}/target-history/${effectiveDate}`),

  // foods
  listFoods: () => get<Food[]>('/foods'),
  createFood: (body: Partial<Food>) => post<Food>('/foods', body),
  updateFood: (id: string, body: Partial<Food>) => patch<Food>(`/foods/${id}`, body),
  listMedPresets: () => get<MedPreset[]>('/med-presets'),

  // feed presets
  listFeedPresets: () => get<FeedPreset[]>('/feed-presets'),
  createFeedPreset: (body: { name: string; components: FeedComponentIn[] }) =>
    post<FeedPreset>('/feed-presets', body),
  deleteFeedPreset: (id: string) => del<void>(`/feed-presets/${id}`),

  // feeds & events
  createFeed: (
    babyId: string,
    body: { occurred_at: string; components: FeedComponentIn[]; notes?: string },
  ) => post<Feed>(`/babies/${babyId}/feeds`, body),
  getFeed: (id: string) => get<Feed>(`/feeds/${id}`),
  updateFeed: (
    id: string,
    body: { occurred_at?: string; components?: FeedComponentIn[]; notes?: string },
  ) => patch<Feed>(`/feeds/${id}`, body),
  deleteFeed: (id: string) => del<void>(`/feeds/${id}`),
  createEvent: (babyId: string, body: Partial<CareEvent> & { occurred_at: string; type: string }) =>
    post<CareEvent>(`/babies/${babyId}/events`, body),
  getEvent: (id: string) => get<CareEvent>(`/events/${id}`),
  updateEvent: (id: string, body: Partial<CareEvent>) =>
    patch<CareEvent>(`/events/${id}`, body),
  deleteEvent: (id: string) => del<void>(`/events/${id}`),

  // assistant — shared family chat sessions
  listChats: () => get<ChatMeta[]>('/assistant/chats'),
  getChat: (id: string) => get<ChatFull>(`/assistant/chats/${id}`),
  deleteChat: (id: string) => del<void>(`/assistant/chats/${id}`),
  createChat: (babyId: string, content: string) =>
    post<ChatReply>(`/babies/${babyId}/assistant/chats`, { content }),
  sendChatMessage: (chatId: string, content: string) =>
    post<ChatReply>(`/assistant/chats/${chatId}/messages`, { content }),

  // care & safety (v3)
  getCareProfile: () => get<CareProfile>('/care-profile'),
  putCareProfile: (body: CareProfile) => request<CareProfile>('/care-profile', {
    method: 'PUT',
    body: JSON.stringify(body),
  }),
  listClinicNotes: () => get<ClinicNote[]>('/clinic-notes'),
  createClinicNote: (text: string) => post<ClinicNote>('/clinic-notes', { text }),
  updateClinicNote: (id: string, body: { text?: string; done?: boolean }) =>
    patch<ClinicNote>(`/clinic-notes/${id}`, body),
  deleteClinicNote: (id: string) => del<void>(`/clinic-notes/${id}`),
  listLabs: () => get<LabResult[]>('/labs'),
  createLab: (body: {
    analyte: string;
    value: number;
    unit: string;
    collected_date: string;
    source_doc_id?: string;
  }) =>
    post<LabResult>('/labs', body),
  deleteLab: (id: string) => del<void>(`/labs/${id}`),
  createDoc: (body: { filename: string; content_type: string; title?: string }) =>
    post<DocCreated>('/docs', body),
  listDocs: () => get<CareDoc[]>('/docs'),
  getDoc: (id: string) => get<CareDoc>(`/docs/${id}`),
  processDoc: (id: string) => post<CareDoc>(`/docs/${id}/process`),
  docDownloadUrl: (id: string) => get<{ url: string }>(`/docs/${id}/download`),
  deleteDoc: (id: string) => del<void>(`/docs/${id}`),

  // Huckleberry sync
  hbStatus: (babyId: string) => get<HbStatus>(`/babies/${babyId}/huckleberry`),
  hbConnect: (babyId: string, body: { email: string; password: string; child_uid?: string }) =>
    post<HbStatus | HbChildSelection>(`/babies/${babyId}/huckleberry/connect`, body),
  hbUpdate: (
    babyId: string,
    body: {
      auto_import?: boolean;
      mapping?: Record<string, string | { food_id: string; parts: number }[]>;
      latch_rate_ml_per_10min?: number;
    },
  ) => patch<HbStatus>(`/babies/${babyId}/huckleberry`, body),
  hbDisconnect: (babyId: string) => del<void>(`/babies/${babyId}/huckleberry`),
  hbSyncNow: (babyId: string) => post<HbSyncResult>(`/babies/${babyId}/huckleberry/sync`),
  hbImports: (babyId: string, status?: string) =>
    get<{ items: HbImport[] }>(
      `/babies/${babyId}/huckleberry/imports${status ? `?status=${status}` : ''}`,
    ),
  hbConfirm: (
    babyId: string,
    hbKey: string,
    body: { volume_ml?: number; rate_ml_per_10min?: number; measured_ml?: number } = {},
  ) =>
    post<Feed>(
      `/babies/${babyId}/huckleberry/imports/${encodeURIComponent(hbKey)}/confirm`,
      body,
    ),
  hbDismiss: (babyId: string, hbKey: string) =>
    post<void>(`/babies/${babyId}/huckleberry/imports/${encodeURIComponent(hbKey)}/dismiss`),

  // reads
  timeline: (babyId: string, params?: { from?: string; to?: string; cursor?: string }) => {
    const q = new URLSearchParams();
    if (params?.from) q.set('from', params.from);
    if (params?.to) q.set('to', params.to);
    if (params?.cursor) q.set('cursor', params.cursor);
    const qs = q.toString();
    return get<{ items: TimelineEntry[]; next_cursor: string | null }>(
      `/babies/${babyId}/timeline${qs ? `?${qs}` : ''}`,
    );
  },
  daySummary: (babyId: string, day: string) =>
    get<Summary>(`/babies/${babyId}/days/${day}`),
  dailyIntake: (babyId: string, from: string, to: string) =>
    get<DailyIntakeSeries>(`/babies/${babyId}/analytics/daily?from=${from}&to=${to}`),
  weightHistory: (babyId: string) =>
    get<WeightSeries>(`/babies/${babyId}/analytics/weights`),
  rollingSummary: (
    babyId: string,
    window: {
      hours?: number;
      sinceLocalTime?: string;
      // Explicit local range, e.g. fromLocal '2026-07-09T08:00:00'.
      fromLocal?: string;
      toLocal?: string;
    },
  ) =>
    get<Summary>(
      `/babies/${babyId}/summary?` +
        (window.fromLocal
          ? `from_local=${window.fromLocal}` +
            (window.toLocal ? `&to_local=${window.toLocal}` : '')
          : window.sinceLocalTime
            ? `since_local_time=${window.sinceLocalTime}`
            : `hours=${window.hours ?? 24}`),
    ),
};
