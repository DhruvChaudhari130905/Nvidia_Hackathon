// What the Preview tab can do with a room's files: run a Node app (package.json with a dev/start
// script), offer to add a Vite setup to React/TypeScript sources that have none, or render plain HTML.

type Files = Map<string, { content: string }>;

export type ProjectKind =
  | { kind: 'node'; script: string; packageJson: string }
  | { kind: 'needs-setup'; entry: string | null }
  | { kind: 'static' }
  | { kind: 'empty' };

const SOURCE = /\.(tsx|jsx|ts)$/;

// The first package.json script that serves the app
function runScript(packageJson: string): string | null {
  try {
    const scripts = (JSON.parse(packageJson) as { scripts?: Record<string, string> }).scripts ?? {};
    return ['dev', 'start', 'preview', 'serve'].find(name => typeof scripts[name] === 'string') ?? null;
  } catch {
    return null;
  }
}

function sourceFiles(files: Files): string[] {
  return Array.from(files.keys()).filter(p => SOURCE.test(p) && !p.endsWith('.d.ts') && !p.includes('node_modules/'));
}

// The module a Vite index.html should load: an existing main/index file, else none (one gets created)
function findEntry(files: Files): string | null {
  const candidates = ['src/main.tsx', 'src/main.jsx', 'src/index.tsx', 'src/index.jsx', 'main.tsx', 'index.tsx', 'client/src/main.tsx'];
  return candidates.find(p => files.has(p)) ?? null;
}

export function projectKind(files: Files): ProjectKind {
  const packageJson = files.get('package.json')?.content;
  if (packageJson) {
    const script = runScript(packageJson);
    if (script) return { kind: 'node', script, packageJson };
  }
  if (sourceFiles(files).some(p => /\.(tsx|jsx)$/.test(p))) return { kind: 'needs-setup', entry: findEntry(files) };
  return files.size ? { kind: 'static' } : { kind: 'empty' };
}

function findApp(files: Files): string | null {
  return ['src/App.tsx', 'src/App.jsx', 'App.tsx', 'App.jsx', 'client/src/App.tsx'].find(p => files.has(p)) ?? null;
}

// The files a React + TypeScript project needs to run with Vite. Only missing files are returned, so
// nothing the room already has is overwritten.
export function viteSetupFiles(files: Files, name: string): Map<string, string> {
  const out = new Map<string, string>();
  let entry = findEntry(files);

  if (!entry) {
    // src/main.tsx renders the App component when there is one
    entry = 'src/main.tsx';
    const app = findApp(files)?.replace(/\.(tsx|jsx)$/, '');
    const appImport = app && (app.startsWith('src/') ? `./${app.slice(4)}` : `../${app}`);
    out.set(entry, [
      "import React from 'react';",
      "import { createRoot } from 'react-dom/client';",
      ...(appImport ? [`import App from '${appImport}';`] : []),
      '',
      "createRoot(document.getElementById('root')!).render(",
      '  <React.StrictMode>',
      appImport ? '    <App />' : '    <h1>Hello from MUX</h1>',
      '  </React.StrictMode>,',
      ');',
      '',
    ].join('\n'));
  }

  if (!files.has('index.html')) {
    out.set('index.html', `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${name.replace(/[<>&"]/g, '')}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/${entry}"></script>
  </body>
</html>
`);
  }

  if (!files.has('package.json')) {
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'mux-app';
    out.set('package.json', `${JSON.stringify({
      name: slug,
      private: true,
      version: '0.1.0',
      type: 'module',
      scripts: { dev: 'vite', build: 'tsc --noEmit && vite build', preview: 'vite preview' },
      dependencies: { react: '^18.3.1', 'react-dom': '^18.3.1' },
      devDependencies: {
        '@types/react': '^18.3.3',
        '@types/react-dom': '^18.3.0',
        '@vitejs/plugin-react': '^4.3.1',
        typescript: '^5.5.4',
        vite: '^5.4.0',
      },
    }, null, 2)}\n`);
  }

  if (!['vite.config.ts', 'vite.config.js', 'vite.config.mjs'].some(p => files.has(p))) {
    out.set('vite.config.ts', `import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
});
`);
  }

  if (!files.has('tsconfig.json')) {
    out.set('tsconfig.json', `${JSON.stringify({
      compilerOptions: {
        target: 'ES2020',
        lib: ['ES2020', 'DOM', 'DOM.Iterable'],
        module: 'ESNext',
        moduleResolution: 'bundler',
        jsx: 'react-jsx',
        strict: true,
        skipLibCheck: true,
        noEmit: true,
      },
      include: ['src'],
    }, null, 2)}\n`);
  }
  return out;
}
