// MUX frontend types. The UI works on these shapes; lib/reducer.ts builds them from the server's events,
// whose payload types are generated from the server's models (types/server.ts, npm run gen:types).
import type { EventPayloads } from './server';

export type UserRole = 'owner' | 'editor' | 'viewer';
export type DomainRole = 'pm' | 'design' | 'eng';
// plan: the first message to a room with no plan, which drafted one
export type MessageLabel = 'merge' | 'queue' | 'interrupt' | 'conflict' | 'chat' | 'plan';
// agent: instructions for the coordinator (the default). team: notes between people, never sent to the coordinator
export type MessageTo = 'agent' | 'team';
// blocked: the coder gave up on the task; a person sets it back to todo to retry
export type PlanItemStatus = 'draft' | 'todo' | 'doing' | 'done' | 'skipped_conflict' | 'skipped_question' | 'blocked';
export type ConflictStatus = 'open' | 'voting' | 'closed';
export type QuestionStatus = 'open' | 'answered' | 'defaulted';

export interface User {
  id: string;
  email: string;
  name: string;
  avatar_url?: string;
  initials: string;
  color: string;
}

export interface Membership {
  user_id: string;
  room_id: string;
  permission: UserRole;
  domain_role: DomainRole;
  user: User;
}

export interface Room {
  id: string;
  title: string;
  description: string;
  owner_id: string;
  link_access: 'restricted' | 'anyone';
  link_permission: UserRole;
  budget_tokens_cap: number;
  budget_runs_cap: number;
  head_checkpoint_id: string | null;
  created_at: string;
  updated_at?: string;
  members: Membership[];
  // Events up to this seq are history when the room opens; later ones are live (notifications)
  last_seq?: number;
  my_permission?: UserRole; // the signed-in user's access (also for people who opened the link)
}

export interface PlanItem {
  id: string;
  title: string;
  status: PlanItemStatus;
  owner_role?: DomainRole | null;
  notes?: string | null;
  merged_notes?: string[];
}

export interface Message {
  id: string;
  seq?: number; // the event that posted it, for greying out after a rewind
  room_id: string;
  user_id: string; // 'agent' for the coordinator and the coder
  text: string;
  to?: MessageTo;
  // Unset while the coordinator hasn't labeled it yet; team notes never get one
  label?: MessageLabel;
  rationale?: string;
  domain?: 'ui' | 'architecture' | 'scope' | null;
  add_plan_item?: { title: string; after_task_id?: string };
  open_conflict?: {
    with_message_ids: string[];
    summary: string;
    options: string[];
    research_queries: string[];
  };
  reply?: string;
  task_id?: string | null; // the task a queue, merge or interrupt went into
  created_at: string;
  user: User;
  streaming?: boolean; // the coder's turn still arriving (agent.text.delta); replaced by its agent.text
  tool?: ToolCall; // set on a coder tool call, drawn as one short line instead of a message
}

export interface ToolCall {
  name: string;
  detail: string; // the argument worth showing: a path, a query
  ok?: boolean; // unset until its tool.result arrives
  summary?: string;
}

export interface Conflict {
  id: string;
  room_id: string;
  task_id: string; // the first held task; task_ids lists all of them
  task_ids: string[];
  message_ids: string[];
  summary: string;
  options: string[];
  evidence: { query: string; summary: string; citations: string[] }[];
  domain: 'ui' | 'architecture' | 'scope';
  status: ConflictStatus;
  result?: string;
  resolved_by?: string; // votes, owner or domain (tie rules), or override
  totals?: Record<string, number>;
  created_at: string;
  expires_at: string; // '' while the research runs
  votes: Vote[];
}

export interface Vote {
  conflict_id: string;
  user_id: string;
  option: string;
  weight: number;
}

export interface Question {
  id: string;
  room_id: string;
  task_id: string | null;
  text: string;
  options: string[];
  default_option: string;
  answer?: string;
  status: QuestionStatus;
  expires_at: string;
  created_at: string;
}

export interface FileChange {
  path: string;
  hash: string;
  version: number;
  diff_summary?: string;
  author_id: string;
  is_manual: boolean;
  created_at: string;
}

export interface Checkpoint {
  id: string;
  room_id: string;
  seq: number;
  start_seq: number;
  manifest_id: string;
  sandbox_snapshot_uuid: string | null;
  plan: PlanItem[]; // the plan when it was saved
  parent_id: string | null;
  created_at: string;
}

export interface Budget {
  tokens_used: number;
  runs_used: number;
  tokens_cap: number;
  runs_cap: number;
}

export interface Presence {
  user_id: string;
  user: User;
  tab: 'feed' | 'preview' | 'code' | 'cards';
  typing?: boolean;
  active: boolean;
  last_seen: string;
}

export interface RoomState {
  room: Room;
  plan: PlanItem[];
  messages: Message[];
  conflicts: Conflict[];
  questions: Question[];
  // Versions seen in file.changed and room.rewound events. The template's files (checkpoint C0) and files a rewind
  // removes are not in events, so the page loads the full list from GET /files.
  files: Map<string, { hash: string; version: number }>;
  locks: Map<string, string>; // path -> user id holding the soft lock
  checkpoints: Checkpoint[];
  head_checkpoint_id: string | null;
  active: Set<number>; // seqs not greyed out by a rewind (lib/rewind.ts)
  budget: Budget;
  paused: boolean;
  presence: Presence[];
  people: Record<string, User>; // everyone seen in the room, for names and avatars
  current_user: User;
  current_user_membership: Membership;
}

// ---- events: the server's envelope, with payloads typed per event type ----

export type EventType = keyof EventPayloads;

export interface BaseEvent {
  seq: number; // presence and agent.text.delta carry the last stored seq
  room_id: string;
  type: EventType;
  actor: string; // a user id, "agent" or "system"
  ts: string;
}

export type AppEvent = { [K in EventType]: BaseEvent & { type: K; payload: EventPayloads[K] } }[EventType];
export type EventOf<K extends EventType> = Extract<AppEvent, { type: K }>;
