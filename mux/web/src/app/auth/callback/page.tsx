'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { safeNext, supabase } from '@/lib/supabase';
import { Logo, ShaderBackground } from '@/components/shell';

function AuthCallbackHandler() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const handleAuth = async () => {
      const code = searchParams.get('code');
      const next = safeNext(searchParams.get('next'));

      if (code) {
        await supabase.auth.exchangeCodeForSession(code);
      }

      router.push(next);
      router.refresh();
    };

    handleAuth();
  }, [router, searchParams]);

  return <Spinner />;
}

function Spinner() {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-surface font-ui">
      <ShaderBackground className="fixed inset-0 z-0 opacity-40" />
      <div className="relative z-10 flex flex-col items-center gap-space-lg rounded-2xl border border-outline-variant/40 bg-surface-container/90 px-space-xl py-space-xl shadow-2xl backdrop-blur-xl">
        <Logo />
        <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
        <div className="flex items-center gap-space-sm font-code text-code-md text-on-surface-variant">
          <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse" />
          Signing you in…
        </div>
      </div>
    </div>
  );
}

// useSearchParams needs a Suspense boundary so the page can be prerendered
export default function AuthCallback() {
  return (
    <Suspense fallback={<Spinner />}>
      <AuthCallbackHandler />
    </Suspense>
  );
}
