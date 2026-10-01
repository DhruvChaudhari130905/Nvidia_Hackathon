// Boots the in-browser WebContainer. Syncing files and running commands lives in runtime.ts
// (the shell terminal); the live preview will build on that rather than on separate helpers here.

import type { WebContainer } from '@webcontainer/api';

// Only one WebContainer can be booted per page, so every caller shares the same boot
let bootPromise: Promise<WebContainer> | null = null;

export async function initWebContainer(): Promise<WebContainer | null> {
  if (typeof window === 'undefined') return null;
  if (!bootPromise) {
    // Dynamic import to avoid SSR issues
    bootPromise = import('@webcontainer/api')
      .then(({ WebContainer }) => WebContainer.boot({ workdirName: 'project' }))
      .catch(err => {
        bootPromise = null; // allow a retry
        throw err;
      });
  }
  return bootPromise;
}
