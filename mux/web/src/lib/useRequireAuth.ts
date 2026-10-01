'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getUser, loginHref } from './supabase';

type AuthUser = Awaited<ReturnType<typeof getUser>>;

// Client-side guard for signed-in screens. Sessions live in localStorage, so this can't run in middleware.
// Returns the user once known; until then (and while redirecting to /login) it returns null.
export function useRequireAuth(): AuthUser | null {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    let cancelled = false;
    getUser()
      .then(u => {
        if (cancelled) return;
        if (u) setUser(u);
        else router.replace(loginHref());
      })
      .catch(() => {
        if (!cancelled) router.replace(loginHref());
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return user;
}
