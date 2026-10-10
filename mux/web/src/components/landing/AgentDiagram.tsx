'use client';

import React, { useEffect, useRef, useState } from 'react';
import { prefersReducedMotion } from '@/components/shell';

// The product in one picture: eight seats send messages into one agent, which streams code into a
// live preview that builds itself up block by block. Packets are SVG circles moved along the
// paths with getPointAtLength in a single rAF loop; React only renders the caption and the preview.

const VIEW_W = 600;
const VIEW_H = 440;
const CORE = { x: 270, y: 220, r: 46 };
const SEAT_R = 17;
const ORBIT = 205;

type Label = 'merge' | 'queue' | 'conflict' | 'chat';

const SEATS: { name: string; initials: string; color: string; lines: [string, Label][] }[] = [
  { name: 'Dan', initials: 'D', color: '#3b82f6', lines: [['make the buttons blue', 'conflict'], ['add a pricing page', 'queue']] },
  { name: 'Priya', initials: 'P', color: '#06b6d4', lines: [['add a login page', 'queue'], ['cyan feels calmer', 'conflict']] },
  { name: 'Maya', initials: 'M', color: '#a371f7', lines: [['show teacher names', 'merge'], ['bigger headings please', 'merge']] },
  { name: 'Sam', initials: 'S', color: '#3fb950', lines: [['vote: blue', 'chat'], ['checkout with Stripe?', 'queue']] },
  { name: 'Jo', initials: 'J', color: '#f0883e', lines: [['rewind to checkpoint 4', 'chat'], ['add a day filter', 'merge']] },
  { name: 'Lee', initials: 'L', color: '#db61a2', lines: [['ship it', 'chat'], ['dark mode too', 'queue']] },
  { name: 'Ana', initials: 'A', color: '#d29922', lines: [['mobile nav is cramped', 'merge'], ['love the hero', 'chat']] },
  { name: 'You', initials: 'You', color: '#dfe2eb', lines: [['make it pop', 'merge'], ['add a contact form', 'queue']] },
];

const LABEL_STYLE: Record<Label, string> = {
  merge: 'text-coord border-coord/40',
  queue: 'text-queue border-queue/40',
  conflict: 'text-conflict border-conflict/40',
  chat: 'text-muted border-white/15',
};

// Seats sit on the left half of a circle around the core, top to bottom
const SEAT_POS = SEATS.map((_, i) => {
  const angle = ((128 + (i * 104) / (SEATS.length - 1)) * Math.PI) / 180;
  return { x: CORE.x + ORBIT * Math.cos(angle), y: CORE.y - ORBIT * Math.sin(angle) };
});

// Each seat's path curves into the core, fanning in like wires
const SEAT_PATHS = SEAT_POS.map(({ x, y }) => {
  const cx = x + (CORE.x - x) * 0.62;
  const cy = CORE.y + (y - CORE.y) * 0.35;
  return `M${x.toFixed(1)},${y.toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(1)} ${CORE.x},${CORE.y}`;
});

const CARD = { x: 395, y: 112, w: 195, h: 216 };
const OUT_PATH = `M${CORE.x + CORE.r - 4},${CORE.y} C${CORE.x + 90},${CORE.y - 26} ${CARD.x - 40},${CORE.y + 26} ${CARD.x},${CORE.y}`;

// The mini app the agent builds, in the order the blocks appear
const BLOCKS = [
  { x: 12, y: 30, w: 171, h: 14, r: 3, fill: 'rgba(255,255,255,.14)' }, // nav
  { x: 12, y: 56, w: 120, h: 12, r: 3, fill: 'rgba(223,226,235,.75)' }, // title
  { x: 12, y: 74, w: 92, h: 7, r: 2, fill: 'rgba(255,255,255,.22)' }, // subtitle
  { x: 12, y: 94, w: 52, h: 58, r: 5, fill: 'rgba(59,130,246,.30)' }, // card 1
  { x: 71, y: 94, w: 52, h: 58, r: 5, fill: 'rgba(6,182,212,.28)' }, // card 2
  { x: 130, y: 94, w: 53, h: 58, r: 5, fill: 'rgba(163,113,247,.28)' }, // card 3
  { x: 12, y: 166, w: 64, h: 18, r: 9, fill: '#3b82f6' }, // button
];

interface Packet {
  el: SVGCircleElement;
  path: SVGPathElement;
  len: number;
  start: number;
  dur: number;
  done: () => void;
}

export function AgentDiagram() {
  const svgRef = useRef<SVGSVGElement>(null);
  const packetLayer = useRef<SVGGElement>(null);
  const seatPathRefs = useRef<(SVGPathElement | null)[]>([]);
  const outPathRef = useRef<SVGPathElement>(null);
  const seatRingRefs = useRef<(SVGCircleElement | null)[]>([]);
  const coreRingRef = useRef<SVGCircleElement>(null);
  const [built, setBuilt] = useState(BLOCKS.length);
  const [caption, setCaption] = useState<{ seat: number; text: string; label: Label; n: number }>({ seat: 1, text: SEATS[1].lines[0][0], label: SEATS[1].lines[0][1], n: 0 });

  useEffect(() => {
    const svg = svgRef.current;
    const layer = packetLayer.current;
    if (!svg || !layer || prefersReducedMotion()) return;
    setBuilt(0);

    const packets: Packet[] = [];
    const timers: ReturnType<typeof setTimeout>[] = [];
    let frame = 0;
    let running = false;
    let lastSeat = -1;
    let arrivals = 0;
    let sent = 0;

    // Restart a CSS animation on an SVG element by toggling its class
    const ping = (el: Element | null) => {
      if (!el) return;
      el.classList.remove('ping');
      void (el as SVGElement).getBoundingClientRect();
      el.classList.add('ping');
    };

    const spawn = (path: SVGPathElement | null, color: string, r: number, dur: number, done: () => void) => {
      if (!path) return;
      const el = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      el.setAttribute('r', String(r));
      el.setAttribute('fill', color);
      el.setAttribute('filter', 'url(#packet-glow)');
      layer.appendChild(el);
      packets.push({ el, path, len: path.getTotalLength(), start: performance.now(), dur, done });
    };

    const tick = (now: number) => {
      for (let i = packets.length - 1; i >= 0; i--) {
        const p = packets[i];
        const t = Math.min(1, (now - p.start) / p.dur);
        const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        const pt = p.path.getPointAtLength(eased * p.len);
        p.el.setAttribute('cx', pt.x.toFixed(1));
        p.el.setAttribute('cy', pt.y.toFixed(1));
        p.el.setAttribute('opacity', t > 0.92 ? String((1 - t) / 0.08) : '1');
        if (t >= 1) {
          p.el.remove();
          packets.splice(i, 1);
          p.done();
        }
      }
      frame = requestAnimationFrame(tick);
    };

    // A seat speaks: its packet flies to the core; every second arrival sends code to the preview
    const send = () => {
      let seat = Math.floor(Math.random() * SEATS.length);
      if (seat === lastSeat) seat = (seat + 3) % SEATS.length;
      lastSeat = seat;
      const [text, label] = SEATS[seat].lines[sent++ % 2];
      setCaption(c => ({ seat, text, label, n: c.n + 1 }));
      ping(seatRingRefs.current[seat]);
      spawn(seatPathRefs.current[seat], SEATS[seat].color, 4, 1100, () => {
        ping(coreRingRef.current);
        arrivals++;
        if (arrivals % 2 === 0) {
          spawn(outPathRef.current, '#67e8f9', 3.5, 700, () => setBuilt(b => (b >= BLOCKS.length ? 0 : b + 1)));
        }
      });
      timers.push(setTimeout(send, 650 + Math.random() * 650));
    };

    const start = () => {
      if (running) return;
      running = true;
      frame = requestAnimationFrame(tick);
      timers.push(setTimeout(send, 400));
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(frame);
      timers.splice(0).forEach(clearTimeout);
    };
    const visibility = new IntersectionObserver(([entry]) => (entry.isIntersecting && !document.hidden ? start() : stop()));
    visibility.observe(svg);
    const onVis = () => (document.hidden ? stop() : start());
    document.addEventListener('visibilitychange', onVis);

    return () => {
      stop();
      visibility.disconnect();
      document.removeEventListener('visibilitychange', onVis);
      packets.forEach(p => p.el.remove());
    };
  }, []);

  const speaker = SEATS[caption.seat];

  return (
    <div className="relative w-full">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className="agent-diagram h-auto w-full overflow-visible"
        role="img"
        aria-label="Eight teammates send messages to one MUX agent, which writes the code into a live preview."
      >
        <defs>
          <radialGradient id="core-fill" cx="50%" cy="40%" r="65%">
            <stop offset="0%" stopColor="#1e3a8a" />
            <stop offset="70%" stopColor="#0b1220" />
          </radialGradient>
          <radialGradient id="core-halo">
            <stop offset="0%" stopColor="rgba(59,130,246,.45)" />
            <stop offset="100%" stopColor="rgba(59,130,246,0)" />
          </radialGradient>
          <linearGradient id="core-ring" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="50%" stopColor="#06b6d4" />
            <stop offset="100%" stopColor="#a371f7" />
          </linearGradient>
          <linearGradient id="out-wire" x1="0" x2="1">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity=".7" />
            <stop offset="100%" stopColor="#06b6d4" stopOpacity=".2" />
          </linearGradient>
          <filter id="packet-glow" x="-200%" y="-200%" width="500%" height="500%">
            <feGaussianBlur stdDeviation="2.4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Wires */}
        {SEAT_PATHS.map((d, i) => (
          <path key={i} ref={el => { seatPathRefs.current[i] = el; }} d={d} fill="none" stroke={SEATS[i].color} strokeOpacity=".22" strokeWidth="1.25" />
        ))}
        <path ref={outPathRef} d={OUT_PATH} fill="none" stroke="url(#out-wire)" strokeWidth="1.5" strokeDasharray="3 5" className="out-wire" />

        <g ref={packetLayer} />

        {/* Seats */}
        {SEATS.map((s, i) => {
          const { x, y } = SEAT_POS[i];
          const you = s.name === 'You';
          return (
            <g key={s.name}>
              <circle ref={el => { seatRingRefs.current[i] = el; }} cx={x} cy={y} r={SEAT_R} fill="none" stroke={s.color} strokeWidth="2" className="seat-ring" />
              <circle cx={x} cy={y} r={SEAT_R} fill={s.color} stroke="#0d1117" strokeWidth="3" />
              <text x={x} y={y} dy=".35em" textAnchor="middle" className="seat-initials" fill={you ? '#0d1117' : '#fff'} fontSize={you ? 9.5 : 12}>
                {s.initials}
              </text>
              <text x={x - SEAT_R - 8} y={y} dy=".35em" textAnchor="end" className="seat-name">{s.name}</text>
            </g>
          );
        })}

        {/* Agent core */}
        <circle cx={CORE.x} cy={CORE.y} r={CORE.r * 2.1} fill="url(#core-halo)" className="core-halo" />
        <circle ref={coreRingRef} cx={CORE.x} cy={CORE.y} r={CORE.r} fill="none" stroke="#3b82f6" strokeWidth="2" className="core-ping" />
        <circle cx={CORE.x} cy={CORE.y} r={CORE.r} fill="url(#core-fill)" />
        <g className="core-spin" style={{ transformOrigin: `${CORE.x}px ${CORE.y}px` }}>
          <circle cx={CORE.x} cy={CORE.y} r={CORE.r + 7} fill="none" stroke="url(#core-ring)" strokeWidth="2" strokeDasharray="40 18 6 18" strokeLinecap="round" />
        </g>
        <g transform={`translate(${CORE.x - 15} ${CORE.y - 21}) scale(1.25)`} strokeWidth="2" strokeLinecap="round" fill="none">
          <path d="M4 6h5l6 6M4 12h11M4 18h5l6-6" stroke="#93c5fd" />
          <path d="M15 12h5" stroke="#67e8f9" />
          <circle cx="20" cy="12" r="1.5" fill="#67e8f9" stroke="none" />
        </g>
        <text x={CORE.x} y={CORE.y + 30} textAnchor="middle" className="core-label">agent</text>

        {/* Live preview the agent builds */}
        <g transform={`translate(${CARD.x} ${CARD.y})`}>
          <rect width={CARD.w} height={CARD.h} rx="12" fill="rgba(13,17,23,.92)" stroke="rgba(255,255,255,.1)" />
          <circle cx="13" cy="14" r="3" fill="#f85149" fillOpacity=".7" />
          <circle cx="23" cy="14" r="3" fill="#d29922" fillOpacity=".7" />
          <circle cx="33" cy="14" r="3" fill="#3fb950" fillOpacity=".7" />
          <rect x="44" y="9" width="139" height="10" rx="5" fill="rgba(255,255,255,.05)" />
          <text x="52" y="14" dy=".35em" className="card-url">preview · live</text>
          {BLOCKS.map((b, i) => (
            <rect
              key={i}
              x={b.x}
              y={b.y + 8}
              width={b.w}
              height={b.h}
              rx={b.r}
              fill={b.fill}
              className="preview-block"
              data-on={i < built || undefined}
            />
          ))}
          <text x={CARD.w - 12} y={CARD.h - 12} textAnchor="end" className="card-url">
            {Math.min(built, BLOCKS.length)}/{BLOCKS.length} built
          </text>
        </g>
      </svg>

      {/* The latest message, like a one-line feed */}
      <div className="mt-2 flex min-h-[28px] items-center justify-center gap-2 font-display text-sm text-on-surface-variant" aria-hidden="true">
        <span key={caption.n} className="item-in flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: speaker.color }} />
          <span className="font-semibold text-on-surface">{speaker.name}</span>
          <span>“{caption.text}”</span>
          <span className={`rounded border px-1.5 py-px font-code text-[10.5px] ${LABEL_STYLE[caption.label]}`}>{caption.label}</span>
        </span>
      </div>
    </div>
  );
}
