// Pure reducer function: events -> room state
// Never changes the state it's given, so replay and rewind are free on the client
import type { AppEvent, RoomState, PlanItem, Membership, Message, User } from '@/types';

export function reduce(events: AppEvent[], initialState?: RoomState): RoomState {
  let state = initialState || createEmptyState();

  for (const event of events) {
    state = applyEvent(state, event);
  }

  return state;
}

const EMPTY_USER: User = { id: '', email: '', name: '', initials: '', color: '' };

export function createEmptyState(roomId = ''): RoomState {
  return {
    room: { id: roomId, title: '', description: '', owner_id: '', link_access: 'restricted', link_permission: 'editor', budget_tokens_cap: 2000000, budget_runs_cap: 100, head_checkpoint_id: null, created_at: '', members: [] },
    plan: [],
    messages: [],
    conflicts: [],
    questions: [],
    files: new Map(),
    checkpoints: [],
    budget: { tokens_used: 0, runs_used: 0, tokens_cap: 2000000, runs_cap: 100 },
    presence: [],
    current_user: EMPTY_USER,
    current_user_membership: { user_id: '', room_id: roomId, permission: 'viewer', domain_role: 'eng', user: EMPTY_USER },
  };
}

const setStatus = (plan: PlanItem[], taskId: string | undefined, changes: Partial<PlanItem>) =>
  taskId === undefined ? plan : plan.map(p => (p.id === taskId ? { ...p, ...changes } : p));

// The backend's coordinator messages carry `author` instead of `user_id`; normalize them
function toMessage(payload: Partial<Message> & { author?: string; role?: string }, event: AppEvent): Message {
  return {
    ...payload,
    id: payload.id ?? `evt-${event.seq}`,
    room_id: payload.room_id ?? event.room_id,
    user_id: payload.user_id ?? payload.author ?? event.actor_id ?? event.actor ?? 'agent',
    text: payload.text ?? payload.reply ?? '',
    label: payload.label ?? 'chat',
    created_at: payload.created_at ?? event.ts,
  } as Message;
}

export function applyEvent(state: RoomState, event: AppEvent): RoomState {
  // Shallow copy; every field that changes below is replaced, never mutated
  const newState = { ...state };

  switch (event.type) {
    case 'room.created': {
      newState.room = { ...newState.room, ...event.payload, members: event.payload.members ?? newState.room.members };
      break;
    }
    case 'member.joined': {
      const member = event.payload as Membership;
      newState.room = {
        ...newState.room,
        members: [...newState.room.members.filter(m => m.user_id !== member.user_id), member],
      };
      break;
    }
    case 'member.role_changed': {
      const { user_id, permission } = event.payload as { user_id: string; permission: Membership['permission'] };
      newState.room = {
        ...newState.room,
        members: newState.room.members.map(m => (m.user_id === user_id ? { ...m, permission } : m)),
      };
      break;
    }
    case 'sharing.changed': {
      newState.room = { ...newState.room, ...event.payload };
      break;
    }
    case 'message.posted': {
      newState.messages = [...newState.messages, toMessage(event.payload, event)];
      break;
    }
    case 'message.labeled': {
      newState.messages = newState.messages.map(m =>
        m.id === event.payload.message_id
          ? { ...m, label: event.payload.label, rationale: event.payload.rationale, domain: event.payload.domain as Message['domain'] }
          : m
      );
      break;
    }
    case 'plan.drafted': {
      newState.plan = (event.payload as { items?: PlanItem[] }).items || [];
      break;
    }
    case 'plan.edited': {
      newState.plan = (event.payload as { items?: PlanItem[] }).items || newState.plan;
      break;
    }
    case 'plan.approved': {
      newState.plan = newState.plan.map(p => (p.status === 'draft' ? { ...p, status: 'todo' as const } : p));
      break;
    }
    case 'plan.item_added': {
      newState.plan = [...newState.plan, event.payload];
      break;
    }
    case 'plan.item_updated': {
      newState.plan = setStatus(newState.plan, event.payload.id, event.payload.changes);
      break;
    }
    case 'coordinator.reply': {
      // Coordinator replies are shown as agent messages
      const reply = toMessage({ user_id: 'agent', label: 'chat', ...event.payload }, event);
      newState.messages = [...newState.messages, reply];
      break;
    }
    case 'conflict.opened': {
      newState.conflicts = [...newState.conflicts, { ...event.payload, votes: event.payload.votes ?? [], evidence: event.payload.evidence ?? [] }];
      newState.plan = setStatus(newState.plan, event.payload.task_id, { status: 'skipped_conflict' });
      break;
    }
    case 'conflict.evidence': {
      newState.conflicts = newState.conflicts.map(c =>
        c.id === event.payload.conflict_id ? { ...c, evidence: event.payload.evidence } : c
      );
      break;
    }
    case 'conflict.vote': {
      const { conflict_id, user_id, option, weight } = event.payload;
      newState.conflicts = newState.conflicts.map(c => {
        if (c.id !== conflict_id) return c;
        // A later vote from the same person replaces their earlier one
        return { ...c, votes: [...c.votes.filter(v => v.user_id !== user_id), { conflict_id, user_id, option, weight }] };
      });
      break;
    }
    case 'conflict.closed': {
      const conflict = newState.conflicts.find(c => c.id === event.payload.conflict_id);
      newState.conflicts = newState.conflicts.map(c =>
        c.id === event.payload.conflict_id
          ? { ...c, status: 'closed' as const, result: event.payload.result, resolved_by: event.payload.resolved_by }
          : c
      );
      // Unblock the task
      newState.plan = setStatus(newState.plan, conflict?.task_id, { status: 'todo', notes: `unblocked · ${event.payload.result}` });
      break;
    }
    case 'question.opened': {
      newState.questions = [...newState.questions, event.payload];
      newState.plan = setStatus(newState.plan, event.payload.task_id, { status: 'skipped_question' });
      break;
    }
    case 'question.answered': {
      const question = newState.questions.find(q => q.id === event.payload.question_id);
      newState.questions = newState.questions.map(q =>
        q.id === event.payload.question_id ? { ...q, status: 'answered' as const, answer: event.payload.answer } : q
      );
      newState.plan = setStatus(newState.plan, question?.task_id, { status: 'todo', notes: `unblocked · ${event.payload.answer.toLowerCase()}` });
      break;
    }
    case 'question.defaulted': {
      const question = newState.questions.find(q => q.id === event.payload.question_id);
      newState.questions = newState.questions.map(q =>
        q.id === event.payload.question_id ? { ...q, status: 'defaulted' as const, answer: q.default_option } : q
      );
      if (question) {
        newState.plan = setStatus(newState.plan, question.task_id, { status: 'todo', notes: `unblocked · default: ${question.default_option.toLowerCase()}` });
      }
      break;
    }
    case 'task.started': {
      newState.plan = setStatus(newState.plan, event.payload.task_id, { status: 'doing' });
      break;
    }
    case 'task.finished': {
      newState.plan = setStatus(newState.plan, event.payload.task_id, { status: 'done' });
      break;
    }
    case 'task.escalated':
    case 'turn.interrupted':
      break;
    case 'file.changed': {
      const newFiles = new Map(newState.files);
      newFiles.set(event.payload.path, { hash: event.payload.hash, version: event.payload.version });
      newState.files = newFiles;
      break;
    }
    case 'checkpoint.created': {
      newState.checkpoints = [...newState.checkpoints, event.payload];
      newState.room = { ...newState.room, head_checkpoint_id: event.payload.id };
      break;
    }
    case 'room.rewound': {
      // Drop checkpoints after the one we rewound to. The payload names the checkpoint; older servers sent its seq.
      const { checkpoint_id, seq } = event.payload;
      const target = checkpoint_id !== undefined ? newState.checkpoints.find(c => c.id === checkpoint_id) : undefined;
      const cutoff = target?.seq ?? seq;
      if (cutoff !== undefined) newState.checkpoints = newState.checkpoints.filter(c => c.seq <= cutoff);
      if (target) newState.room = { ...newState.room, head_checkpoint_id: target.id };
      break;
    }
    case 'budget.updated': {
      newState.budget = event.payload;
      break;
    }
    case 'room.paused':
    case 'room.resumed':
      break;
    case 'presence.join': {
      newState.presence = [...newState.presence.filter(p => p.user_id !== event.payload.user_id), event.payload];
      break;
    }
    case 'presence.leave': {
      newState.presence = newState.presence.filter(p => p.user_id !== event.payload.user_id);
      break;
    }
    case 'presence.typing': {
      newState.presence = newState.presence.map(p =>
        p.user_id === event.payload.user_id ? { ...p, typing: event.payload.typing } : p
      );
      break;
    }
    case 'presence.tab': {
      newState.presence = newState.presence.map(p =>
        p.user_id === event.payload.user_id ? { ...p, tab: event.payload.tab } : p
      );
      break;
    }
    default:
      // Feed-only events (agent.text, tool.*, build.result, log.*, export.*) don't change room state
      break;
  }

  return newState;
}
