// API client for REST commands
import type { Room, Message, MessageTo, PlanItem, Conflict, Question, Budget, Checkpoint, User, Membership } from '@/types';

import { createDemoRoom, deleteDemoRoom, demoMessageEvent, getDemoRoom, isDemoMode, listDemoRooms, nextDemoSeq } from './demo';
import { getSocket } from './socket';
import { getAccessToken } from './supabase';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Answers API calls locally in demo mode; room events are pushed through the room socket
async function demoFetch<T>(path: string, options: RequestInit): Promise<T> {
  const method = options.method || 'GET';
  const body = options.body ? JSON.parse(options.body as string) : {};
  // Query strings (`/close?reason=…`) don't change which call this is
  const roomMatch = path.split('?')[0].match(/^\/rooms\/([^/]+)(\/.*)?$/);

  if (path === '/rooms' && method === 'GET') return listDemoRooms() as T;
  if (path === '/rooms' && method === 'POST') return createDemoRoom(body.description) as T;
  if (roomMatch && !roomMatch[2] && method === 'GET') return getDemoRoom(roomMatch[1]) as T;
  if (roomMatch && roomMatch[2] === '/close') {
    deleteDemoRoom(roomMatch[1]);
    return { room_id: roomMatch[1], closed: true } as T;
  }
  if (roomMatch && roomMatch[2] === '/sharing') return Object.assign(getDemoRoom(roomMatch[1]), body) as T;
  if (roomMatch && roomMatch[2] === '/messages') {
    getSocket(roomMatch[1]).injectEvent(demoMessageEvent(roomMatch[1], body.text, body.to));
  }
  if (path === '/github/connect' || path.endsWith('/export')) return { url: 'https://github.com' } as T;
  return { accepted: true, seq: nextDemoSeq(), version: (body.base_version ?? 0) + 1 } as T;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function fetchWithAuth<T>(path: string, options: RequestInit = {}): Promise<T> {
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
    const error = await res.json().catch(() => ({ message: 'Request failed' }));
    // FastAPI puts the reason in `detail` (a list of field errors for a 422)
    const detail = typeof error.detail === 'string' ? error.detail : error.detail && JSON.stringify(error.detail);
    throw new ApiError(error.message || detail || `HTTP ${res.status}`, res.status);
  }

  if (res.status === 204) return {} as T;
  return res.json();
}

export const api = {
  // Rooms
  listRooms: () => fetchWithAuth<Room[]>('/rooms'),
  getRoom: (id: string) => fetchWithAuth<Room>(`/rooms/${id}`),
  createRoom: (description: string, domain_role: 'pm' | 'design' | 'eng') =>
    fetchWithAuth<Room>('/rooms', {
      method: 'POST',
      body: JSON.stringify({ description, domain_role }),
    }),
  // Owner only. The room stops and disappears for everyone; the server keeps its history but never reopens it
  closeRoom: (id: string, reason?: string) =>
    fetchWithAuth<{ room_id: string; closed: boolean }>(
      `/rooms/${id}/close${reason ? `?reason=${encodeURIComponent(reason)}` : ''}`,
      { method: 'POST' },
    ),
  updateSharing: (id: string, data: { link_access: 'restricted' | 'anyone'; link_permission: 'editor' | 'viewer'; invites?: string[] }) =>
    fetchWithAuth<Room>(`/rooms/${id}/sharing`, { method: 'PATCH', body: JSON.stringify(data) }),

  // Messages
  sendMessage: (roomId: string, text: string, to: MessageTo = 'agent') =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ text, to }),
    }),

  // Plan
  updatePlan: (roomId: string, items: PlanItem[]) =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/plan`, {
      method: 'PATCH',
      body: JSON.stringify({ items }),
    }),
  approvePlan: (roomId: string) =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/plan/approve`, { method: 'POST' }),

  // Conflicts
  voteConflict: (roomId: string, conflictId: string, option: string) =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/conflicts/${conflictId}/vote`, {
      method: 'POST',
      body: JSON.stringify({ option }),
    }),
  overrideConflict: (roomId: string, conflictId: string, option: string) =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/conflicts/${conflictId}/override`, {
      method: 'POST',
      body: JSON.stringify({ option }),
    }),

  // Questions
  answerQuestion: (roomId: string, questionId: string, answer: string) =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/questions/${questionId}/answer`, {
      method: 'POST',
      body: JSON.stringify({ answer }),
    }),

  // Files
  lockFile: (roomId: string, path: string) =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/files/lock`, {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  unlockFile: (roomId: string, path: string) =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/files/unlock`, {
      method: 'POST',
      body: JSON.stringify({ path }),
    }),
  readFile: (roomId: string, path: string) =>
    fetchWithAuth<{ path: string; content: string }>(
      `/api/files/${roomId}/files/${path.split('/').map(encodeURIComponent).join('/')}`,
    ),
  saveFile: (roomId: string, path: string, content: string, baseVersion: number) =>
    fetchWithAuth<{ accepted: true; seq: number; version: number }>(`/rooms/${roomId}/files`, {
      method: 'PUT',
      body: JSON.stringify({ path, content, base_version: baseVersion }),
    }),

  // A file that only exists in this browser (never saved to the room) is already gone on the server
  deleteFile: (roomId: string, path: string) =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/files?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
      .catch(error => {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }),

  // Rewind
  rewind: (roomId: string, checkpointId: string) =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/rewind`, {
      method: 'POST',
      body: JSON.stringify({ checkpoint_id: checkpointId }),
    }),

  // Budget
  updateBudget: (roomId: string, tokensCap?: number, runsCap?: number) =>
    fetchWithAuth<Budget>(`/rooms/${roomId}/budget`, {
      method: 'PATCH',
      body: JSON.stringify({ tokens_cap: tokensCap, runs_cap: runsCap }),
    }),

  // GitHub
  // `next`: the app page GitHub returns to after connecting (the profile page by default)
  connectGitHub: (next?: string) =>
    fetchWithAuth<{ url: string }>(`/github/connect${next ? `?next=${encodeURIComponent(next)}` : ''}`),
  githubStatus: () => fetchWithAuth<{ connected: boolean; username: string | null }>('/api/export/github/status'),
  exportToGitHub: (roomId: string, repoName: string, isPrivate: boolean) =>
    fetchWithAuth<{ url: string }>(`/rooms/${roomId}/export`, {
      method: 'POST',
      body: JSON.stringify({ repo_name: repoName, private: isPrivate }),
    }),

  // Session
  endSession: (roomId: string) =>
    fetchWithAuth<{ accepted: true; seq: number }>(`/rooms/${roomId}/end-session`, { method: 'POST' }),
};