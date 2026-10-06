// Checks lib/rewind.ts against the rewind cases the server's tests use. Run: npm run check:rewind
import { readFileSync } from 'node:fs';
import { computeActive, headOf } from '../src/lib/rewind.ts';

const scenario = JSON.parse(readFileSync(new URL('../../packages/schema/fixtures/rewind_scenario.json', import.meta.url), 'utf8'));
let failed = 0;
for (const step of scenario.steps) {
  const events = scenario.events.filter((e: { seq: number }) => e.seq <= step.after_seq);
  const head = scenario.checkpoints[step.head];
  const got = [...computeActive(events, head)].sort((a, b) => a - b);
  const derived = headOf(events);
  const ok = JSON.stringify(got) === JSON.stringify(step.active) && derived === head;
  if (!ok) {
    failed += 1;
    console.error(`after seq ${step.after_seq}, head ${step.head}: got ${got} (head ${derived}), want ${step.active}`);
  }
}
console.log(failed ? `${failed} of ${scenario.steps.length} rewind cases failed` : `${scenario.steps.length} rewind cases pass`);
process.exit(failed ? 1 : 0);
