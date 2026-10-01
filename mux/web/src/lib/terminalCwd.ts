// Where a room's terminal starts: the project's own folder. Detected from marker files (package.json,
// go.mod, …), or chosen in the terminal toolbar and remembered per room in this browser.

// The WebContainer project lives here (see workdirName in webcontainer.ts)
export const PROJECT_DIR = '/home/project';

const MARKERS = new Set([
  'package.json', 'requirements.txt', 'pyproject.toml', 'setup.py', 'Pipfile', 'go.mod', 'Cargo.toml',
  'pom.xml', 'build.gradle', 'build.gradle.kts', 'CMakeLists.txt', 'Makefile', 'composer.json', 'Gemfile',
  'deno.json', 'app.json', 'index.html',
]);

// Folders ('' = room root) that look like a project, at most two levels deep, root first
export function projectDirs(paths: string[]): string[] {
  const dirs = new Set<string>();
  for (const p of paths) {
    const parts = p.split('/');
    if (parts.length > 3 || !MARKERS.has(parts[parts.length - 1])) continue;
    if (parts.slice(0, -1).some(d => d === 'node_modules' || d.startsWith('.'))) continue;
    dirs.add(parts.slice(0, -1).join('/'));
  }
  return Array.from(dirs).sort((a, b) => (a === '' ? -1 : b === '' ? 1 : a.localeCompare(b)));
}

// Root when the root is a project (or there are several); the single sub-project otherwise
export function detectStartDir(paths: string[]): string {
  const dirs = projectDirs(paths);
  if (dirs.includes('')) return '';
  return dirs.length === 1 ? dirs[0] : '';
}

const key = (roomId: string) => `mux_terminal_cwd:${roomId}`;

// null = automatic
export function getSavedStartDir(roomId: string): string | null {
  try {
    return localStorage.getItem(key(roomId));
  } catch {
    return null;
  }
}

export function setSavedStartDir(roomId: string, dir: string | null) {
  try {
    if (dir === null) localStorage.removeItem(key(roomId));
    else localStorage.setItem(key(roomId), dir);
  } catch {
    // storage unavailable: the choice lasts for this session only
  }
}

export function absoluteDir(dir: string): string {
  return dir ? `${PROJECT_DIR}/${dir}` : PROJECT_DIR;
}

export function shellQuote(p: string): string {
  return /^[\w./-]+$/.test(p) ? p : `'${p.replace(/'/g, `'\\''`)}'`;
}
