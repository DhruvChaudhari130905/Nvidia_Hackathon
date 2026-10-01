// Starters offered by the terminal's "New project" menu. Each one runs the real scaffolding tool in the
// room's WebContainer shell, inside its own folder, then installs dependencies and starts the dev server.

export interface ProjectTemplate {
  id: string;
  group: 'Web' | 'App';
  label: string;
  detail: string;
  defaultName: string;
  // Files written before the command runs (for starters that need no scaffolding tool)
  files?: (name: string) => Record<string, string>;
  command: (name: string) => string;
}

// create-vite 6 never prompts when given a name and template, so the chained install/dev always runs
const vite = (template: string) => (name: string) =>
  `npm create vite@6 ${name} -- --template ${template} && cd ${name} && npm install && npm run dev`;

export const PROJECT_TEMPLATES: ProjectTemplate[] = [
  { id: 'vite-react', group: 'Web', label: 'React + TypeScript', detail: 'Vite · react-ts', defaultName: 'react-app', command: vite('react-ts') },
  { id: 'vite-vue', group: 'Web', label: 'Vue + TypeScript', detail: 'Vite · vue-ts', defaultName: 'vue-app', command: vite('vue-ts') },
  { id: 'vite-svelte', group: 'Web', label: 'Svelte + TypeScript', detail: 'Vite · svelte-ts', defaultName: 'svelte-app', command: vite('svelte-ts') },
  { id: 'vite-vanilla-ts', group: 'Web', label: 'Vanilla TypeScript', detail: 'Vite · vanilla-ts', defaultName: 'vanilla-ts-app', command: vite('vanilla-ts') },
  { id: 'vite-vanilla', group: 'Web', label: 'Vanilla JavaScript', detail: 'Vite · vanilla', defaultName: 'vanilla-app', command: vite('vanilla') },
  {
    id: 'static',
    group: 'Web',
    label: 'Plain HTML, CSS & JS',
    detail: 'No build step · served with Vite',
    defaultName: 'site',
    files: name => ({
      [`${name}/index.html`]: `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${name}</title>
    <link rel="stylesheet" href="style.css" />
  </head>
  <body>
    <main>
      <h1>Hello from ${name}</h1>
      <button id="counter" type="button">Clicked 0 times</button>
    </main>
    <script type="module" src="main.js"></script>
  </body>
</html>
`,
      [`${name}/style.css`]: `:root { color-scheme: light dark; font-family: system-ui, sans-serif; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; }
main { text-align: center; }
button { font: inherit; padding: 0.6em 1.2em; border-radius: 8px; border: 1px solid currentColor; background: none; cursor: pointer; }
`,
      [`${name}/main.js`]: `const button = document.querySelector('#counter');
let count = 0;
button.addEventListener('click', () => {
  count += 1;
  button.textContent = \`Clicked \${count} time\${count === 1 ? '' : 's'}\`;
});
`,
    }),
    command: name => `cd ${name} && npx -y vite@6`,
  },
  {
    id: 'expo',
    group: 'App',
    label: 'Expo (React Native)',
    detail: 'TypeScript · runs on the web preview',
    defaultName: 'expo-app',
    // The web target needs react-dom, react-native-web and the metro runtime; phones need Expo Go and a tunnel, which a browser can't host
    command: name =>
      `npx -y create-expo-app@latest ${name} --template blank-typescript --yes && cd ${name} && npx expo install react-dom react-native-web @expo/metro-runtime && npx expo start --web`,
  },
];

// Folder names become shell arguments, so keep them to safe characters
export function safeFolderName(name: string, fallback: string): string {
  const clean = name.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, '-').replace(/^[-.]+|-+$/g, '');
  return clean || fallback;
}
