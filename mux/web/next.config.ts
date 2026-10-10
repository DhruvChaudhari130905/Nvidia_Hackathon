// WebContainers need cross-origin isolation, so every page sends COOP and COEP headers.
// COEP is `credentialless` so public images from other sites (photos in a preview, Google / GitHub
// avatars) still load; `require-corp` silently blocks any that don't send a CORP header. Safari has no
// `credentialless`, so it keeps `require-corp` (src/lib/webcontainer.ts boots with the matching mode).

// Safari, but not the Chromium / Firefox browsers that also mention Safari in their user agent
const SAFARI_UA = '^(?!.*(?:Chrome|Chromium|CriOS|FxiOS|EdgiOS|Edg|Firefox|Android)).*Safari.*$';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // A separate output folder lets a production build run while `next dev` is using .next
  distDir: process.env.NEXT_DIST_DIR || '.next',
  // `make tunnel` serves the dev server on a trycloudflare.com address so teammates can join
  allowedDevOrigins: ['*.trycloudflare.com'],
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
          { key: 'Cross-Origin-Embedder-Policy', value: 'credentialless' },
        ],
      },
      {
        // Later rules win for the same header
        source: '/:path*',
        has: [{ type: 'header', key: 'user-agent', value: SAFARI_UA }],
        headers: [{ key: 'Cross-Origin-Embedder-Policy', value: 'require-corp' }],
      },
    ];
  },
  transpilePackages: ['@monaco-editor/react'],
  webpack: (config) => {
    config.externals.push({
      'utf-8-validate': 'commonjs utf-8-validate',
      'bufferutil': 'commonjs bufferutil',
    });
    return config;
  },
};

export default nextConfig;