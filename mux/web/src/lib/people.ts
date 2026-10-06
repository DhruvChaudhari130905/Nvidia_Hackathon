// Display data for people the server only knows by id: a name (from presence, or a short id), initials and a
// colour that stays the same for a given id.
import type { User } from '@/types';

export const AGENT_ID = 'agent';
export const AGENT: User = { id: AGENT_ID, email: '', name: 'MUX', initials: 'H', color: '#3b82f6' };

export function person(id: string, name?: string | null, known?: User): User {
  if (id === AGENT_ID || id === 'system') return AGENT;
  if (known && !name) return known;
  const display = name || known?.name || `User ${id.slice(0, 4)}`;
  const initials = display.split(/\s+/).map(p => p[0]).join('').slice(0, 2).toUpperCase() || '?';
  return { id, email: known?.email ?? '', name: display, initials, color: known?.color ?? colorFor(id), avatar_url: known?.avatar_url };
}

function colorFor(id: string): string {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360;
  return `hsl(${h}, 65%, 60%)`;
}
