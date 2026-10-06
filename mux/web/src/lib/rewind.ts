// Which events a rewind greys out. Mirrors compute_active in mux/server/mux/checkpoints/rewind.py; both are
// checked against packages/schema/fixtures/rewind_scenario.json (scripts/check-rewind.ts here, test_rewind.py there).
// Only type imports, so the check script runs on plain Node.

interface Envelope {
  seq: number;
  type: string;
  payload: unknown;
}

interface Span {
  seq: number;
  start_seq: number;
  parent_id: string | null;
}

// Room-level events are never greyed out (models.is_exempt)
const EXEMPT_TYPES = new Set([
  'room.created', 'sharing.changed', 'budget.updated', 'room.paused', 'room.resumed',
  'room.rewound', 'checkpoint.created', 'message.posted', 'sitting.ended',
]);
const EXEMPT_PREFIXES = ['member.', 'export.'];
const HEAD_CHANGES = new Set(['checkpoint.created', 'room.rewound']);

export function isExempt(type: string): boolean {
  return EXEMPT_TYPES.has(type) || EXEMPT_PREFIXES.some(p => type.startsWith(p));
}

// The head after these events: the latest checkpoint created or rewound to
export function headOf(events: Envelope[]): string | null {
  let head: string | null = null;
  for (const e of events) {
    if (e.type === 'checkpoint.created') head = (e.payload as { checkpoint_id: string }).checkpoint_id;
    else if (e.type === 'room.rewound') head = (e.payload as { checkpoint_id: string }).checkpoint_id;
  }
  return head;
}

// Seqs of the events that are not greyed out with `head` as head (default: the head the events lead to)
export function computeActive(events: Envelope[], head: string | null = headOf(events)): Set<number> {
  if (head === null) return new Set(events.map(e => e.seq));
  const checkpoints = new Map<string, Span>();
  for (const e of events) {
    if (e.type !== 'checkpoint.created') continue;
    const p = e.payload as { checkpoint_id: string; start_seq: number; parent_id: string | null };
    checkpoints.set(p.checkpoint_id, { seq: e.seq, start_seq: p.start_seq, parent_id: p.parent_id });
  }
  const spans: [number, number][] = [];
  for (let id: string | null = head; id !== null; ) {
    const cp = checkpoints.get(id);
    if (!cp) throw new Error(`unknown checkpoint ${id}`);
    spans.push([cp.start_seq, cp.seq]);
    id = cp.parent_id;
  }
  const lastChange = Math.max(0, ...events.filter(e => HEAD_CHANGES.has(e.type)).map(e => e.seq));
  return new Set(
    events
      .filter(e => isExempt(e.type) || e.seq > lastChange || spans.some(([lo, hi]) => lo < e.seq && e.seq <= hi))
      .map(e => e.seq),
  );
}
