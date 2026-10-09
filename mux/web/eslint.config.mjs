// ESLint 9 flat config wrapping Next's legacy preset. `npm run lint` runs ESLint directly
// (`next lint` is removed in Next.js 16).
import { FlatCompat } from '@eslint/eslintrc';

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const config = [
  { ignores: ['.next/**', '.next-build/**', 'out/**', 'node_modules/**', 'next-env.d.ts'] },
  ...compat.extends('next/core-web-vitals'),
];

export default config;
