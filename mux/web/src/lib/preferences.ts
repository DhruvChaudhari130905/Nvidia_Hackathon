// Per-browser user preferences, kept in localStorage.
import type { DomainRole } from '@/types';

const DEFAULT_ROLE_KEY = 'mux_default_role';
const ROLES: DomainRole[] = ['pm', 'design', 'eng'];

export function getDefaultRole(): DomainRole {
  try {
    const stored = window.localStorage.getItem(DEFAULT_ROLE_KEY) as DomainRole | null;
    return stored && ROLES.includes(stored) ? stored : 'pm';
  } catch {
    return 'pm';
  }
}

export function setDefaultRole(role: DomainRole) {
  try {
    window.localStorage.setItem(DEFAULT_ROLE_KEY, role);
  } catch {
    // storage unavailable; the preference just won't persist
  }
}

// Stable avatar color from the user id, so the same person keeps the same color across pages
export function colorForId(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) | 0;
  return `hsl(${Math.abs(hash) % 360}, 70%, 60%)`;
}

// The last room the user opened, shown in the header's session pill
const LAST_ROOM_KEY = 'mux_last_room';

export interface LastRoom {
  id: string;
  title: string;
  openedAt: number;
}

export function setLastRoom(room: { id: string; title: string }) {
  try {
    window.localStorage.setItem(LAST_ROOM_KEY, JSON.stringify({ id: room.id, title: room.title, openedAt: Date.now() }));
  } catch {
    // storage unavailable
  }
}

export function getLastRoom(): LastRoom | null {
  try {
    const raw = window.localStorage.getItem(LAST_ROOM_KEY);
    return raw ? (JSON.parse(raw) as LastRoom) : null;
  } catch {
    return null;
  }
}
