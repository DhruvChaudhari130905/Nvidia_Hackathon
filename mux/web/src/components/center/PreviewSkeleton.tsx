'use client';

import React from 'react';

export function PreviewSkeleton() {
  return (
    <div className="preview flex items-center justify-center min-h-[400px]">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--coord)] mx-auto mb-4" />
        <p className="text-[var(--muted)]">Starting WebContainer...</p>
        <p className="text-[var(--faint)] text-sm mt-2">This may take a few seconds on first load</p>
      </div>
    </div>
  );
}

export function PreviewError({ error, onRetry }: { error?: string; onRetry: () => void }) {
  return (
    <div className="preview flex items-center justify-center min-h-[400px] text-[var(--conflict)]">
      <div className="text-center">
        <p className="mb-2">Failed to start preview</p>
        {error && <p className="text-sm text-[var(--muted)]">{error}</p>}
        <button className="btn primary mt-4" type="button" onClick={onRetry}>Retry</button>
      </div>
    </div>
  );
}

export function PreviewReady({ children }: { children: React.ReactNode }) {
  return <div className="preview">{children}</div>;
}