// ESLint flat config. `next lint` is deprecated, so `npm run lint` calls eslint directly.
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { FlatCompat } from '@eslint/eslintrc';

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  { ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts', 'src/types/generated/**'] },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    rules: {
      // `const { [key]: _removed, ...rest } = obj` is how we drop a key
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', destructuredArrayIgnorePattern: '^_' }],
      // Meant for pages/_document; with the app router the fonts in app/layout.tsx load on every page
      '@next/next/no-page-custom-font': 'off',
    },
  },
];

export default config;
