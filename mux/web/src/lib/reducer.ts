// Pure reducer function: events -> room state
// This makes replay and rewind free on the client
import type { AppEvent, RoomState, Room, PlanItem, Message, Conflict, Question, FileChange, Checkpoint, Budget, Presence, User, Membership } from '@/types';

export function reduce(events: AppEvent[], initialState?: RoomState): RoomState {
  let state = initialState || createEmptyState();

  for (const event of events) {
    state = applyEvent(state, event);
  }

  return state;
}

export function createEmptyState(): RoomState {
  return {
    room: { id: '', title: '', description: '', owner_id: '', link_access: 'restricted', link_permission: 'editor', budget_tokens_cap: 2000000, budget_runs_cap: 100, head_checkpoint_id: null, created_at: '', members: [] },
    plan: [],
    messages: [],
    conflicts: [],
    questions: [],
    files: new Map(),
    checkpoints: [],
    budget: { tokens_used: 0, runs_used: 0, tokens_cap: 2000000, runs_cap: 100 },
    presence: [],
    current_user: { id: '', email: '', name: '', initials: '', color: '' },
    current_user_membership: { user_id: '', room_id: '', permission: 'viewer', domain_role: 'eng', user: { id: '', email: '', name: '', initials: '', color: '' } },
  };
}

export function applyEvent(state: RoomState, event: AppEvent): RoomState {
  // Create new state object for immutability
  const newState = { ...state };

  switch (event.type) {
    case 'room.created': {
      newState.room = event.payload as any;
      break;
    }
    case 'member.joined': {
      newState.room.members.push(event.payload as any);
      break;
    }
    case 'member.role_changed': {
      const member = newState.room.members.find(m => m.user_id === (event.payload as any).user_id);
      if (member) member.permission = (event.payload as any).permission;
      break;
    }
    case 'sharing.changed': {
      Object.assign(newState.room, event.payload);
      break;
    }
    case 'message.posted': {
      newState.messages = [...newState.messages, event.payload];
      break;
    }
    case 'message.labeled': {
      newState.messages = newState.messages.map(m =>
        m.id === event.payload.message_id
          ? { ...m, label: event.payload.label, rationale: event.payload.rationale, domain: event.payload.domain as any }
          : m
      );
      break;
    }
    case 'plan.drafted': {
      newState.plan = (event.payload as any).items || [];
      break;
    }
    case 'plan.edited': {
      newState.plan = (event.payload as any).items || newState.plan;
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
      newState.plan = newState.plan.map(p =>
        p.id === event.payload.id ? { ...p, ...event.payload.changes } : p
      );
      break;
    }
    case 'coordinator.reply': {
      // Coordinator replies are added as messages
      newState.messages = [...newState.messages, event.payload as any];
      break;
    }
    case 'conflict.opened': {
      newState.conflicts = [...newState.conflicts, event.payload];
      // Mark the task as skipped_conflict
      newState.plan = newState.plan.map(p =>
        p.id === event.payload.task_id ? { ...p, status: 'skipped_conflict' as const } : p
      );
      break;
    }
    case 'conflict.evidence': {
      newState.conflicts = newState.conflicts.map(c =>
        c.id === event.payload.conflict_id ? { ...c, evidence: event.payload.evidence } : c
      );
      break;
    }
    case 'conflict.vote': {
      newState.conflicts = newState.conflicts.map(c => {
        if (c.id !== event.payload.conflict_id) return c;
        return {
          ...c,
          votes: [...c.votes, { conflict_id: event.payload.conflict_id, user_id: event.payload.user_id, option: event.payload.option, weight: event.payload.weight }],
        };
      });
      break;
    }
    case 'conflict.closed': {
      newState.conflicts = newState.conflicts.map(c =>
        c.id === event.payload.conflict_id
          ? { ...c, status: 'closed' as const, result: event.payload.result, resolved_by: event.payload.resolved_by }
          : c
      );
      // Unblock the task
      newState.plan = newState.plan.map(p =>
        p.id === newState.conflicts.find(c => c.id === event.payload.conflict_id)?.task_id
          ? { ...p, status: 'todo' as const, notes: `unblocked · ${event.payload.result}` }
          : p
      );
      break;
    }
    case 'question.opened': {
      newState.questions = [...newState.questions, event.payload];
      newState.plan = newState.plan.map(p =>
        p.id === event.payload.task_id ? { ...p, status: 'skipped_question' as const } : p
      );
      break;
    }
    case 'question.answered': {
      newState.questions = newState.questions.map(q =>
        q.id === event.payload.question_id
          ? { ...q, status: 'answered' as const, answer: event.payload.answer }
          : q
      );
      const question = newState.questions.find(q => q.id === event.payload.question_id);
      if (question) {
        newState.plan = newState.plan.map(p =>
          p.id === question.task_id
            ? { ...p, status: 'todo' as const, notes: `unblocked · ${event.payload.answer.toLowerCase()}` }
            : p
        );
      }
      break;
    }
    case 'question.defaulted': {
      newState.questions = newState.questions.map(q =>
        q.id === event.payload.question_id
          ? { ...q, status: 'defaulted' as const, answer: q.default_option }
          : q
      );
      break;
    }
    case 'task.started': {
      newState.plan = newState.plan.map(p =>
        p.id === event.payload.task_id ? { ...p, status: 'doing' as const } : p
      );
      break;
    }
    case 'task.finished': {
      newState.plan = newState.plan.map(p =>
        p.id === event.payload.task_id ? { ...p, status: 'done' as const } : p
      );
      break;
    }
    case 'task.escalated': {
      // Could track escalation status
      break;
    }
    case 'turn.interrupted': {
      // The current task is interrupted, will be re-planned
      break;
    }
    case 'file.changed': {
      const newFiles = new Map(newState.files);
      newFiles.set(event.payload.path, { hash: event.payload.hash, version: event.payload.version });
      newState.files = newFiles;
      break;
    }
    case 'file.deleted': {
      const newFiles = new Map(newState.files);
      newFiles.delete(event.payload.path);
      newState.files = newFiles;
      break;
    }
    case 'checkpoint.created': {
      newState.checkpoints = [...newState.checkpoints, event.payload];
      newState.room.head_checkpoint_id = event.payload.id;
      break;
    }
    case 'room.rewound': {
      // After rewind, events after the checkpoint are greyed out (active = false)
      // For client state, we can filter or mark them
      newState.checkpoints = newState.checkpoints.filter(c => c.seq <= event.payload.seq);
      break;
    }
    case 'budget.updated': {
      newState.budget = event.payload;
      break;
    }
    case 'room.paused': {
      // Could add a paused flag
      break;
    }
    case 'room.resumed': {
      break;
    }
    case 'presence.join': {
      // The server keeps one presence per user and re-sends presence.join on every join (the REST join,
      // the socket, a second tab): replace the user's entry instead of adding another
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
    case 'agent.text':
    case 'tool.called':
    case 'tool.result':
    case 'build.result':
    case 'test.result':
    case 'log.task_written':
    case 'log.day_written':
    case 'export.started':
    case 'export.finished':
      // These are feed events, already handled in messages or can be added to a separate feed
      break;
  }

  return newState;
}

// Helper to get initial state from server
export async function fetchInitialState(roomId: string): Promise<RoomState> {
  const res = await fetch(`/api/rooms/${roomId}/initial-state`);
  if (!res.ok) throw new Error('Failed to fetch initial state');
  return res.json();
}