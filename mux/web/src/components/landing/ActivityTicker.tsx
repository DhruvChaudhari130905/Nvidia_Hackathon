import React from 'react';

// Endless strip of room events under the hero, like a live activity log
const EVENTS: { dot: string; who: string; text: string }[] = [
  { dot: 'bg-primary', who: 'NeoCart', text: 'run_build passed · 11.8s' },
  { dot: 'bg-secondary', who: 'Priya', text: 'queued "Member login page"' },
  { dot: 'bg-error-strong', who: 'Metrics', text: 'vote opened · chart library' },
  { dot: 'bg-[#a371f7]', who: 'MUX', text: 'asked: Stripe or fake checkout?' },
  { dot: 'bg-primary', who: 'Lotus Yoga', text: 'checkpoint 4 created' },
  { dot: 'bg-secondary', who: 'Dan', text: 'merged note into task 4' },
  { dot: 'bg-primary', who: 'Habit tracker', text: 'exported to GitHub' },
  { dot: 'bg-[#a371f7]', who: 'Maya', text: 'answered: calendar heatmap' },
  { dot: 'bg-primary', who: 'Recipe box', text: '3 editors joined the room' },
];

export function ActivityTicker() {
  const pill = (e: (typeof EVENTS)[number], i: number) => (
    <span
      key={i}
      className="mx-space-sm flex flex-none items-center gap-space-sm rounded-full border border-outline-variant/30 bg-surface-container/80 px-space-md py-1.5 font-code text-code-sm"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${e.dot}`} />
      <span className="text-on-surface">{e.who}</span>
      <span className="text-on-surface-variant">{e.text}</span>
    </span>
  );
  const row = EVENTS.map(pill);
  // Second lane runs the other way, offset so the two lanes never line up
  const rowB = [...EVENTS.slice(4), ...EVENTS.slice(0, 4)].map(pill);

  return (
    <div className="marquee-mask space-y-space-sm overflow-hidden py-space-md" aria-label="Recent activity across rooms">
      <div className="marquee">
        {row}
        <span aria-hidden="true" className="contents">{row}</span>
      </div>
      <div className="marquee reverse" aria-hidden="true">
        {rowB}
        {rowB}
      </div>
    </div>
  );
}
