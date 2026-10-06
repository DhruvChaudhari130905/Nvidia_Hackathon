// Pure reducer: the server's events -> room state. Replay, live updates and rewind all go through applyEvent.
// The server sends the room's facts (ids, payloads in types/server.ts); this file turns them into the shapes the
// UI draws (types/index.ts): names and avatars for people, feed messages for agent activity, card status.
import type { AppEvent, Checkpoint, Conflict, EventOf, Membership, Message, PlanItem, Presence, Question, Room, RoomState, User } from '@/types';
import { AGENT, AGENT_ID, person } from './people';
import { computeActive } from './rewind';

const DEFAULT_BUDGET = { tokens_used: 0, runs_used: 0, tokens_cap: 2_000_000, runs_cap: 100 };
const NOBODY: User = { id: '', email: '', name: '', initials: '', color: '' };

export function createEmptyState(room?: Room, currentUser?: User): RoomState {
  const people: Record<string, User> = {};
  for (const m of room?.members ?? []) people[m.user_id] = m.user;
  if (currentUser) people[currentUser.id] = currentUser;
  const me = room?.members.find(m => m.user_id === currentUser?.id);
  return {
    room: room ?? {
      id: '', title: '', description: '', owner_id: '', link_access: 'restricted', link_permission: 'editor',
      budget_tokens_cap: DEFAULT_BUDGET.tokens_cap, budget_runs_cap: DEFAULT_BUDGET.runs_cap,
      head_checkpoint_id: null, created_at: '', members: [],
    },
    plan: [],
    messages: [],
    conflicts: [],
    questions: [],
    files: new Map(),
    locks: new Map(),
    checkpoints: [],
    head_checkpoint_id: room?.head_checkpoint_id ?? null,
    active: new Set(),
    budget: { ...DEFAULT_BUDGET, tokens_cap: room?.budget_tokens_cap ?? DEFAULT_BUDGET.tokens_cap, runs_cap: room?.budget_runs_cap ?? DEFAULT_BUDGET.runs_cap },
    paused: false,
    presence: [],
    people,
    current_user: currentUser ?? NOBODY,
    current_user_membership: me ?? { user_id: currentUser?.id ?? '', room_id: room?.id ?? '', permission: 'viewer', domain_role: 'eng', user: currentUser ?? NOBODY },
  };
}

export function reduce(events: AppEvent[], initialState?: RoomState): RoomState {
  return events.reduce(applyEvent, initialState ?? createEmptyState());
}

// Stored events seen so far (rewind greying needs all of them); presence and text deltas are never stored
const history = new WeakMap<RoomState, { seq: number; type: string; payload: unknown }[]>();
const BROADCAST_ONLY = new Set(['presence.join', 'presence.leave', 'presence.typing', 'presence.tab', 'agent.text.delta']);

export function applyEvent(state: RoomState, event: AppEvent): RoomState {
  const next = apply({ ...state }, event);
  if (BROADCAST_ONLY.has(event.type)) {
    history.set(next, history.get(state) ?? []);
    return next;
  }
  const events = [...(history.get(state) ?? []), { seq: event.seq, type: event.type, payload: event.payload }];
  history.set(next, events);
  if (event.type === 'checkpoint.created' || event.type === 'room.rewound') {
    next.active = computeActive(events, next.head_checkpoint_id);
  } else {
    next.active = new Set(state.active).add(event.seq); // anything after the last head change is active
  }
  return next;
}

function apply(s: RoomState, event: AppEvent): RoomState {
  switch (event.type) {
    case 'room.created':
      s.room = { ...s.room, owner_id: event.payload.owner_id, title: event.payload.title, description: event.payload.description ?? '' };
      break;
    case 'member.joined': {
      const user = personOf(s, event.payload.user_id);
      const member: Membership = {
        user_id: event.payload.user_id, room_id: event.room_id, permission: event.payload.permission,
        domain_role: event.payload.domain_role ?? 'eng', user,
      };
      s.room = { ...s.room, members: [...s.room.members.filter(m => m.user_id !== member.user_id), member] };
      break;
    }
    case 'member.role_changed':
      s.room = {
        ...s.room,
        members: s.room.members.map(m => (m.user_id === event.payload.user_id ? { ...m, permission: event.payload.permission } : m)),
      };
      break;
    case 'sharing.changed':
      s.room = { ...s.room, link_access: event.payload.link_access, link_permission: event.payload.link_permission ?? 'viewer' };
      break;

    // ---- messages and the agent's feed ----
    case 'message.posted': {
      const p = event.payload;
      s.messages = [...s.messages, {
        id: p.id, seq: event.seq, room_id: event.room_id, user_id: p.user_id, text: p.text, to: p.to,
        created_at: event.ts, user: personOf(s, p.user_id),
      }];
      break;
    }
    case 'message.labeled': {
      const p = event.payload;
      s.messages = s.messages.map(m =>
        m.id === p.message_id ? { ...m, label: p.label, rationale: p.rationale, domain: p.domain ?? null, task_id: p.task_id } : m,
      );
      break;
    }
    case 'coordinator.reply':
      s.messages = [...s.messages, agentMessage(event, event.payload.text)];
      break;
    case 'agent.text':
      s.messages = [...s.messages, agentMessage(event, event.payload.text)];
      break;
    case 'build.result':
    case 'test.result': {
      const what = event.type === 'build.result' ? 'Build' : 'Tests';
      const errors = event.payload.errors ?? [];
      const text = event.payload.passed ? `${what} passed.` : `${what} failed: ${errors[0] ?? 'see the log'}`;
      s.messages = [...s.messages, agentMessage(event, text)];
      break;
    }
    case 'turn.interrupted':
      s.messages = [...s.messages, agentMessage(event, `Stopped task ${event.payload.task_id} to start it again: ${event.payload.reason}.`)];
      break;

    // ---- plan ----
    case 'plan.drafted':
    case 'plan.edited':
      s.plan = event.payload.items.map(planItem);
      break;
    case 'plan.approved':
      s.plan = s.plan.map(p => (p.status === 'draft' ? { ...p, status: 'todo' } : p));
      break;
    case 'plan.item_added':
      s.plan = [...s.plan, planItem(event.payload)];
      break;
    case 'plan.item_updated': {
      const { id, changes } = event.payload;
      s.plan = s.plan.map(p => (p.id === id ? { ...p, ...(changes as Partial<PlanItem>) } : p));
      break;
    }
    case 'task.started':
      s.plan = s.plan.map(p => (p.id === event.payload.task_id ? { ...p, status: 'doing' } : p));
      break;
    case 'task.finished':
      s.plan = s.plan.map(p => (p.id === event.payload.task_id ? { ...p, status: 'done' } : p));
      break;

    // ---- cards (the plan changes that go with them arrive as their own plan events) ----
    case 'conflict.opened': {
      const p = event.payload;
      const conflict: Conflict = {
        id: p.id, room_id: event.room_id, task_id: p.task_ids[0] ?? '', task_ids: p.task_ids, message_ids: p.message_ids,
        summary: p.summary, options: [...p.options], evidence: [], domain: p.domain, status: 'open',
        created_at: event.ts, expires_at: '', votes: [],
      };
      s.conflicts = [...s.conflicts, conflict];
      break;
    }
    case 'conflict.evidence': {
      const p = event.payload;
      const evidence = p.summary
        ? [{ query: (p.queries ?? []).join(' · '), summary: p.summary, citations: (p.citations ?? []).map(c => c.url) }]
        : [];
      s.conflicts = s.conflicts.map(c => (c.id === p.conflict_id ? { ...c, status: 'voting', evidence, expires_at: p.expires_at } : c));
      break;
    }
    case 'conflict.vote': {
      const v = event.payload;
      s.conflicts = s.conflicts.map(c =>
        c.id === v.conflict_id ? { ...c, votes: [...c.votes.filter(x => x.user_id !== v.user_id), v] } : c, // a later vote replaces
      );
      break;
    }
    case 'conflict.closed': {
      const p = event.payload;
      s.conflicts = s.conflicts.map(c =>
        c.id === p.conflict_id ? { ...c, status: 'closed', result: p.result, resolved_by: p.resolved_by, totals: p.totals } : c,
      );
      break;
    }
    case 'question.opened': {
      const p = event.payload;
      const question: Question = {
        id: p.id, room_id: event.room_id, task_id: p.task_id, text: p.text, options: [...p.options], default_option: p.default,
        status: 'open', expires_at: p.expires_at, created_at: event.ts,
      };
      s.questions = [...s.questions, question];
      break;
    }
    case 'question.answered':
      s.questions = s.questions.map(q => (q.id === event.payload.question_id ? { ...q, status: 'answered', answer: event.payload.answer } : q));
      break;
    case 'question.defaulted':
      s.questions = s.questions.map(q => (q.id === event.payload.question_id ? { ...q, status: 'defaulted', answer: event.payload.answer } : q));
      break;

    // ---- files ----
    case 'file.changed': {
      const files = new Map(s.files);
      if (event.payload.deleted || event.payload.hash === null) files.delete(event.payload.path);
      else files.set(event.payload.path, { hash: event.payload.hash, version: event.payload.version });
      s.files = files;
      break;
    }
    case 'file.locked':
      s.locks = new Map(s.locks).set(event.payload.path, event.payload.user_id);
      break;
    case 'file.unlocked': {
      const locks = new Map(s.locks);
      locks.delete(event.payload.path);
      s.locks = locks;
      break;
    }

    // ---- checkpoints and rewind ----
    case 'checkpoint.created': {
      const p = event.payload;
      const checkpoint: Checkpoint = {
        id: p.checkpoint_id, room_id: event.room_id, seq: event.seq, start_seq: p.start_seq, manifest_id: p.manifest_id,
        sandbox_snapshot_uuid: p.sandbox_snapshot_uuid, plan: s.plan, parent_id: p.parent_id, created_at: event.ts,
      };
      s.checkpoints = [...s.checkpoints, checkpoint];
      s.head_checkpoint_id = checkpoint.id;
      s.room = { ...s.room, head_checkpoint_id: checkpoint.id };
      break;
    }
    case 'room.rewound': {
      const p = event.payload;
      s.head_checkpoint_id = p.checkpoint_id;
      s.room = { ...s.room, head_checkpoint_id: p.checkpoint_id };
      const target = s.checkpoints.find(c => c.id === p.checkpoint_id);
      s.plan = (p.plan?.length ? p.plan.map(planItem) : target?.plan) ?? s.plan;
      // Versions of the files whose content changed; removed files show up when the page reloads the file list
      const files = new Map(s.files);
      for (const [path, version] of Object.entries(p.versions)) {
        const old = files.get(path);
        files.set(path, { hash: old?.hash ?? '', version });
      }
      s.files = files;
      break;
    }

    // ---- budget and sitting ----
    case 'budget.updated':
      s.budget = event.payload;
      break;
    case 'room.paused':
      s.paused = true;
      break;
    case 'room.resumed':
      s.paused = false;
      break;

    // ---- presence (never stored) ----
    case 'presence.join': {
      const p = event.payload;
      const user = person(p.user_id, p.name, s.people[p.user_id]);
      s.people = { ...s.people, [p.user_id]: user };
      // messages posted before the name was known get it now
      s.messages = s.messages.map(m => (m.user_id === p.user_id ? { ...m, user } : m));
      const entry: Presence = { user_id: p.user_id, user, tab: p.tab ?? 'feed', typing: p.typing, active: true, last_seen: event.ts };
      s.presence = [...s.presence.filter(x => x.user_id !== p.user_id), entry];
      break;
    }
    case 'presence.leave':
      s.presence = s.presence.filter(p => p.user_id !== event.payload.user_id);
      break;
    case 'presence.typing':
      s.presence = s.presence.map(p => (p.user_id === event.payload.user_id ? { ...p, typing: event.payload.typing } : p));
      break;
    case 'presence.tab':
      s.presence = s.presence.map(p => (p.user_id === event.payload.user_id ? { ...p, tab: event.payload.tab } : p));
      break;

    // agent.text.delta streams a turn whose full text arrives as agent.text; logs, sitting.ended and tool
    // calls are not shown in the feed
    default:
      break;
  }
  return s;
}

function personOf(s: RoomState, id: string): User {
  return s.people[id] ?? person(id);
}

function planItem(p: { id: string; title: string; status?: PlanItem['status']; owner_role?: PlanItem['owner_role']; notes?: string | null; merged_notes?: string[] }): PlanItem {
  return { id: p.id, title: p.title, status: p.status ?? 'draft', owner_role: p.owner_role, notes: p.notes, merged_notes: p.merged_notes ?? [] };
}

function agentMessage(
  event: EventOf<'coordinator.reply' | 'agent.text' | 'build.result' | 'test.result' | 'turn.interrupted'>,
  text: string,
): Message {
  return { id: `e${event.seq}`, seq: event.seq, room_id: event.room_id, user_id: AGENT_ID, text, to: 'agent', created_at: event.ts, user: AGENT };
}
