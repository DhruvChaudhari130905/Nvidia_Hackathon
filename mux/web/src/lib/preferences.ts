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

// Forget the last room if it is this one (it no longer exists), so the header stops linking to it
// Fired when the last room is forgotten, so a header already on screen stops linking to it
export const LAST_ROOM_CHANGED = 'mux:last-room-changed';

export function clearLastRoom(roomId: string) {
  try {
    if (getLastRoom()?.id !== roomId) return;
    window.localStorage.removeItem(LAST_ROOM_KEY);
    window.dispatchEvent(new Event(LAST_ROOM_CHANGED));
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

// Whether the room's feed (left), decisions & plan (right) and timeline (bottom) panels are open
export type RoomPanel = 'feed' | 'side' | 'timeline';

export function getPanelOpen(panel: RoomPanel): boolean {
  try {
    return window.localStorage.getItem(`mux_panel_${panel}`) !== 'closed';
  } catch {
    return true;
  }
}

export function setPanelOpen(panel: RoomPanel, open: boolean) {
  try {
    window.localStorage.setItem(`mux_panel_${panel}`, open ? 'open' : 'closed');
  } catch {
    // storage unavailable; the layout just won't persist
  }
}
