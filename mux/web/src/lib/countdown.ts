// Countdown helpers for vote and question timers
import { useEffect, useState } from 'react';

// Seconds as m:ss. Done by hand: date-fns formats in local time, which is off by 30 minutes in IST and similar zones.
export function formatCountdown(seconds: number): string {
  const t = Math.max(0, Math.floor(seconds));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
}

const secondsUntil = (iso: string) => {
  const ms = new Date(iso).getTime() - Date.now();
  return Number.isFinite(ms) ? Math.max(0, Math.ceil(ms / 1000)) : 0;
};

// Seconds left until an ISO timestamp, updated every second. Survives remounts because it's derived from the clock.
export function useSecondsUntil(iso: string, active = true): number {
  const [left, setLeft] = useState(() => secondsUntil(iso));
  useEffect(() => {
    setLeft(secondsUntil(iso));
    if (!active) return;
    const interval = setInterval(() => {
      const next = secondsUntil(iso);
      setLeft(next);
      if (next === 0) clearInterval(interval);
    }, 1000);
    return () => clearInterval(interval);
  }, [iso, active]);
  return left;
}
