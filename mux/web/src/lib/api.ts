// REST client for the room API at /api/rooms (mux/server/mux/api/rooms.py). Changes come back as events on
// the room WebSocket, so most calls return nothing; the UI updates from the events.
import type { Budget, DomainRole, Membership, MessageTo, PlanItem, Room, User } from '@/types';

import { createDemoRoom, demoMessageEvent, getDemoRoom, isDemoMode, listDemoRooms } from './demo';
import { person } from './people';
import { getSocket } from './socket';
import { getAccessToken } from './supabase';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// The server's room shapes (RoomOut, RoomListItem)
interface MemberOut {
  user_id: string;
  permission: Membership['permission'];
  domain_role: DomainRole | null;
}

interface RoomOut {
  id: string;
  owner_id?: string;
  title: string;
  description: string;
  link_access?: Room['link_access'];
  link_permission?: 'editor' | 'viewer' | null;
  head_checkpoint_id?: string | null;
  my_permission?: Membership['permission'];
  permission?: Membership['permission'];
  members: MemberOut[];
  last_seq?: number;
  created_at?: string;
  budget_tokens_cap: number;
  budget_runs_cap: number;
}

export interface FileEntry {
  path: string;
  version: number;
}

export interface FileOut extends FileEntry {
  content: string;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly detail: unknown) {
    super(message);
  }
}

// The server knows people by id only; names fill in from presence (and the signed-in user)
export function toRoom(r: RoomOut, me?: User): Room {
  return {
    id: r.id,
    title: r.title,
    description: r.description,
    owner_id: r.owner_id ?? r.members.find(m => m.permission === 'owner')?.user_id ?? '',
    link_access: r.link_access ?? 'restricted',
    link_permission: r.link_permission ?? 'viewer',
    budget_tokens_cap: r.budget_tokens_cap,
    budget_runs_cap: r.budget_runs_cap,
    head_checkpoint_id: r.head_checkpoint_id ?? null,
    created_at: r.created_at ?? '',
    last_seq: r.last_seq,
    my_permission: r.my_permission ?? r.permission,
    members: r.members.map(m => ({
      user_id: m.user_id, room_id: r.id, permission: m.permission, domain_role: m.domain_role ?? 'eng',
      user: m.user_id === me?.id ? me : person(m.user_id),
    })),
  };
}

// Answers API calls locally in demo mode; room events are pushed through the room socket
async function demoFetch<T>(path: string, options: RequestInit): Promise<T> {
  const method = options.method || 'GET';
  const body = options.body ? JSON.parse(options.body as string) : {};
  const roomMatch = path.match(/^\/api\/rooms\/([^/]+)(\/.*)?$/);

  if (path === '/api/rooms' && method === 'GET') return listDemoRooms() as T;
  if (path === '/api/rooms' && method === 'POST') return createDemoRoom(body.description) as T;
  if (roomMatch && !roomMatch[2] && method === 'GET') return getDemoRoom(roomMatch[1]) as T;
  if (roomMatch && roomMatch[2] === '/sharing') return Object.assign(getDemoRoom(roomMatch[1]), body) as T;
  if (roomMatch && roomMatch[2] === '/messages') {
    for (const event of demoMessageEvent(roomMatch[1], body.text, body.to)) getSocket(roomMatch[1]).injectEvent(event);
  }
  if (roomMatch && roomMatch[2] === '/files' && method === 'GET') return [] as T;
  if (path === '/github/connect' || path.endsWith('/export')) return { url: 'https://github.com' } as T;
  return { path: '', version: (body.base_version ?? 0) + 1, changed: true } as T;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (isDemoMode()) return demoFetch<T>(path, options);
  const token = await getAccessToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || `HTTP ${res.status}`;
    throw new ApiError(message, res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

const room = (id: string, rest = '') => `/api/rooms/${id}${rest}`;
const filePath = (path: string) => path.split('/').map(encodeURIComponent).join('/');
const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

// A title for a room created from its description alone
function titleFrom(description: string): string {
  const words = description.trim().split(/\s+/).slice(0, 8).join(' ');
  return (words.length > 60 ? `${words.slice(0, 59)}…` : words) || 'Untitled room';
}

export const api = {
  // Rooms
  listRooms: async (me?: User) => (await request<RoomOut[]>('/api/rooms')).map(r => (isDemoMode() ? (r as unknown as Room) : toRoom(r, me))),
  getRoom: async (id: string, me?: User) => {
    const r = await request<RoomOut>(room(id));
    return isDemoMode() ? (r as unknown as Room) : toRoom(r, me);
  },
  createRoom: async (description: string, domain_role: DomainRole, title = titleFrom(description)) => {
    const r = await request<RoomOut>('/api/rooms', json('POST', { title, description, domain_role }));
    return isDemoMode() ? (r as unknown as Room) : toRoom(r);
  },
  joinRoom: (id: string, domain_role?: DomainRole) =>
    request<{ permission: Membership['permission'] }>(room(id, '/join'), json('POST', { domain_role })),
  setMember: (id: string, userId: string, permission: 'editor' | 'viewer', domain_role?: DomainRole) =>
    request<void>(room(id, `/members/${userId}`), json('PUT', { permission, domain_role })),
  updateSharing: (id: string, data: { link_access: 'restricted' | 'anyone'; link_permission: 'editor' | 'viewer' }) =>
    request<void>(room(id, '/sharing'), json('PUT', { link_access: data.link_access, link_permission: data.link_permission })),

  // Messages
  sendMessage: (roomId: string, text: string, to: MessageTo = 'agent') =>
    request<unknown>(room(roomId, '/messages'), json('POST', { text, to })),

  // Plan
  updatePlan: (roomId: string, items: PlanItem[]) => request<void>(room(roomId, '/plan'), json('PUT', { items })),
  approvePlan: (roomId: string) => request<void>(room(roomId, '/plan/approve'), { method: 'POST' }),
  updatePlanItem: (roomId: string, taskId: string, changes: Partial<PlanItem>) =>
    request<void>(room(roomId, `/plan/items/${taskId}`), json('PATCH', changes)),

  // Cards
  voteConflict: (roomId: string, conflictId: string, option: string) =>
    request<void>(room(roomId, `/conflicts/${conflictId}/vote`), json('POST', { option })),
  overrideConflict: (roomId: string, conflictId: string, option: string) =>
    request<void>(room(roomId, `/conflicts/${conflictId}/override`), json('POST', { option })),
  answerQuestion: (roomId: string, questionId: string, answer: string) =>
    request<void>(room(roomId, `/questions/${questionId}/answer`), json('POST', { answer })),

  // Files: a save needs the file's lock; a stale base_version is a 409 whose detail has the current version
  listFiles: (roomId: string) => request<FileEntry[]>(room(roomId, '/files')),
  readFile: (roomId: string, path: string) => request<FileOut>(room(roomId, `/files/${filePath(path)}`)),
  lockFile: (roomId: string, path: string) => request<void>(room(roomId, `/locks/${filePath(path)}`), { method: 'POST' }),
  unlockFile: (roomId: string, path: string) => request<void>(room(roomId, `/locks/${filePath(path)}`), { method: 'DELETE' }),
  // baseVersion null creates the file; content null deletes it
  saveFile: (roomId: string, path: string, content: string | null, baseVersion: number | null) =>
    request<{ path: string; version: number | null; changed: boolean }>(
      room(roomId, `/files/${filePath(path)}`), json('PUT', { content, base_version: baseVersion }),
    ),

  // Checkpoints and rewind
  rewind: (roomId: string, checkpointId: string) =>
    request<{ checkpoint_id: string; log: string | null }>(room(roomId, '/rewind'), json('POST', { checkpoint_id: checkpointId })),

  // Budget
  getBudget: (roomId: string) => request<Budget & { paused: boolean }>(room(roomId, '/budget')),
  updateBudget: (roomId: string, tokensCap: number, runsCap: number) =>
    request<Budget & { paused: boolean }>(room(roomId, '/budget'), json('PUT', { tokens_cap: tokensCap, runs_cap: runsCap })),

  // GitHub export comes back after v0; these still answer in demo mode
  connectGitHub: () => request<{ url: string }>('/github/connect'),
  exportToGitHub: (roomId: string, repoName: string, isPrivate: boolean) =>
    request<{ url: string }>(room(roomId, '/export'), json('POST', { repo_name: repoName, private: isPrivate })),

  // Session
  endSession: (roomId: string) => request<{ ended: boolean }>(room(roomId, '/session/end'), { method: 'POST' }),
};
