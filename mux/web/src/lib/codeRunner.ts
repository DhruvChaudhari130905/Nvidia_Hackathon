// "Run file" for single files. JavaScript/TypeScript run in the room's WebContainer terminal; languages a
// browser can't compile or interpret (Python, C, C++, Java, Go, Rust, …) are sent to Wandbox
// (wandbox.org), a free online compiler service. Note that those files leave the browser.

export type Runner =
  | { kind: 'shell'; command: string; language: string }
  | { kind: 'remote'; language: string };

import { PROJECT_DIR } from './terminalCwd';

// Absolute paths, so a file runs the same whatever folder the terminal is in
const SHELL: Record<string, (path: string) => string> = {
  js: p => `node ${quote(p)}`,
  mjs: p => `node ${quote(p)}`,
  cjs: p => `node ${quote(p)}`,
  ts: p => `npx -y tsx ${quote(p)}`,
  mts: p => `npx -y tsx ${quote(p)}`,
};

// Extension → Wandbox language name (as listed by /api/list.json)
const REMOTE: Record<string, string> = {
  py: 'Python', c: 'C', cpp: 'C++', cc: 'C++', cxx: 'C++', java: 'Java', go: 'Go', rs: 'Rust', rb: 'Ruby', php: 'PHP',
  cs: 'C#', swift: 'Swift', lua: 'Lua', r: 'R', sh: 'Bash script', hs: 'Haskell', scala: 'Scala', jl: 'Julia',
  zig: 'Zig', pl: 'Perl', ex: 'Elixir', exs: 'Elixir', erl: 'Erlang', ml: 'OCaml', nim: 'Nim', d: 'D', pas: 'Pascal',
  sql: 'SQL', groovy: 'Groovy', cr: 'Crystal',
};

// Files the program may include/import, sent alongside the main file
const COMPANIONS: Record<string, RegExp> = {
  C: /\.(h|c)$/i,
  'C++': /\.(h|hh|hpp|hxx|cpp|cc|cxx)$/i,
  Python: /\.py$/i,
};

const LANGUAGE_NAMES: Record<string, string> = { js: 'JavaScript', mjs: 'JavaScript', cjs: 'JavaScript', ts: 'TypeScript', mts: 'TypeScript' };

const ext = (path: string) => path.split('.').pop()?.toLowerCase() ?? '';
const quote = (p: string) => (/^[\w./-]+$/.test(p) ? p : `'${p.replace(/'/g, `'\\''`)}'`);

export function runnerFor(path: string): Runner | null {
  const e = ext(path);
  if (SHELL[e]) return { kind: 'shell', command: SHELL[e](`${PROJECT_DIR}/${path}`), language: LANGUAGE_NAMES[e] };
  if (REMOTE[e]) return { kind: 'remote', language: REMOTE[e] };
  return null;
}

// JavaScript and TypeScript can also run remotely when the browser can't start a WebContainer
export function remoteFallback(path: string): Runner | null {
  const e = ext(path);
  if (['js', 'mjs', 'cjs'].includes(e)) return { kind: 'remote', language: 'JavaScript' };
  if (['ts', 'mts'].includes(e)) return { kind: 'remote', language: 'TypeScript' };
  return null;
}

export function canRun(path: string): boolean {
  return runnerFor(path) !== null;
}

// ───────────── Wandbox ─────────────

const CONSENT_KEY = 'mux_remote_run_ok';

// Asks (once per browser) before sending code to wandbox.org. False when the user declines.
export function remoteRunAllowed(): boolean {
  try {
    if (window.localStorage.getItem(CONSENT_KEY) === '1') return true;
  } catch {
    // storage blocked; ask every time
  }
  const ok = window.confirm(
    'Running this file sends its source code (and headers or modules next to it) to wandbox.org, a free third-party compiler service.\n\nContinue?',
  );
  if (ok) {
    try {
      window.localStorage.setItem(CONSENT_KEY, '1');
    } catch {
      // ignore
    }
  }
  return ok;
}

const API = 'https://wandbox.org/api';
let compilers: Promise<{ name: string; language: string; 'display-name': string; version: string }[]> | null = null;

function listCompilers() {
  if (!compilers) {
    compilers = fetch(`${API}/list.json`)
      .then(r => {
        if (!r.ok) throw new Error(`Wandbox list failed (${r.status})`);
        return r.json();
      })
      .catch(err => {
        compilers = null;
        throw err;
      });
  }
  return compilers;
}

async function pickCompiler(language: string) {
  const list = (await listCompilers()).filter(c => c.language === language);
  // Prefer a released Python 3 over "head" builds; elsewhere the service lists the newest first
  const preferred = language === 'Python' ? list.find(c => /^cpython-3\.\d+/.test(c.name)) : list.find(c => !/head/.test(c.name));
  const chosen = preferred ?? list[0];
  if (!chosen) throw new Error(`No ${language} compiler available`);
  return chosen;
}

export interface RunResult {
  ok: boolean;
  exitCode: string;
  compilerName: string;
  compileOutput: string; // compiler warnings and errors
  stdout: string;
  stderr: string;
  ms: number;
}

export async function runRemote(
  path: string,
  language: string,
  files: Map<string, { content: string }>,
  stdin: string,
  signal?: AbortSignal,
): Promise<RunResult> {
  const started = performance.now();
  const compiler = await pickCompiler(language);
  let code = files.get(path)?.content ?? '';

  // Wandbox saves Java as prog.java, so a public top-level class would fail to compile
  if (language === 'Java') code = code.replace(/^(\s*)public\s+((?:final\s+|abstract\s+)*)class\s+/m, '$1$2class ');

  const dir = path.includes('/') ? path.slice(0, path.lastIndexOf('/') + 1) : '';
  const companion = COMPANIONS[language];
  const codes = companion
    ? Array.from(files)
        .filter(([p]) => p !== path && p.startsWith(dir) && !p.slice(dir.length).includes('/') && companion.test(p))
        // A second file with main() would clash at link time, so only headers come along for C/C++
        .filter(([p]) => language === 'Python' || /\.(h|hh|hpp|hxx)$/i.test(p))
        .map(([p, f]) => ({ file: p.slice(dir.length), code: f.content }))
    : [];

  const options = language === 'C++' ? 'warning,c++2b' : language === 'C' ? 'warning,c17' : '';
  const res = await fetch(`${API}/compile.json`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ compiler: compiler.name, code, codes, stdin, options, save: false }),
    signal,
  });
  if (!res.ok) throw new Error(`Run service error (${res.status}). Try again in a moment.`);
  const out = await res.json();
  const exitCode = String(out.status ?? (out.signal ? `signal ${out.signal}` : '?'));
  return {
    ok: exitCode === '0',
    exitCode: out.signal ? `killed by ${out.signal}` : exitCode,
    compilerName: `${compiler['display-name']} ${compiler.version}`,
    compileOutput: [out.compiler_output, out.compiler_error].filter(Boolean).join(''),
    stdout: out.program_output ?? '',
    stderr: out.program_error ?? '',
    ms: Math.round(performance.now() - started),
  };
}
