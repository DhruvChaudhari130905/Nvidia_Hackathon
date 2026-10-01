// Fallbacks for when an event or member row has only a user id and no embedded user object
import type { Membership, User } from '@/types';
import { colorForId } from './preferences';

export function placeholderUser(id: string): User {
  const name = id ? id.charAt(0).toUpperCase() + id.slice(1) : 'Someone';
  return { id, email: '', name, initials: name.slice(0, 2).toUpperCase(), color: colorForId(id) };
}

// The user behind an id: the embedded object if there is one, then the room's members, then a placeholder
export function resolveUser(id: string, members: Membership[] = [], embedded?: User | null): User {
  return embedded ?? members.find(m => m.user_id === id)?.user ?? placeholderUser(id);
}
