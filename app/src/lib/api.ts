import * as SecureStore from 'expo-secure-store';

import type {
  Baby,
  CareEvent,
  ChatFull,
  ChatMeta,
  ChatReply,
  Family,
  Feed,
  FeedComponentIn,
  FeedPreset,
  Food,
  MedPreset,
  Summary,
  Targets,
  TimelineEntry,
  TokenResponse,
} from './types';

export const API_URL =
  process.env.EXPO_PUBLIC_API_URL ?? 'https://z7yrwag4b4.execute-api.us-east-1.amazonaws.com';

const TOKEN_KEY = 'tinyprotocol_token';

let _token: string | null = null;

export async function loadToken(): Promise<string | null> {
  if (_token) return _token;
  _token = await SecureStore.getItemAsync(TOKEN_KEY);
  return _token;
}

export async function setToken(token: string | null) {
  _token = token;
  if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
  else await SecureStore.deleteItemAsync(TOKEN_KEY);
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
  updateFamily: (body: Partial<Pick<Family, 'name' | 'timezone' | 'day_start'>>) =>
    patch<Family>('/family', body),

  // babies
  listBabies: () => get<Baby[]>('/babies'),
  createBaby: (body: { name: string; conditions?: string[] }) =>
    post<Baby>('/babies', body),
  updateBaby: (
    id: string,
    body: Partial<{
      name: string;
      default_latch_rate_ml_per_10min: number;
      targets: Targets;
    }>,
  ) => patch<Baby>(`/babies/${id}`, body),

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
  rollingSummary: (babyId: string, window: { hours?: number; sinceLocalTime?: string }) =>
    get<Summary>(
      `/babies/${babyId}/summary?` +
        (window.sinceLocalTime
          ? `since_local_time=${window.sinceLocalTime}`
          : `hours=${window.hours ?? 24}`),
    ),
};
