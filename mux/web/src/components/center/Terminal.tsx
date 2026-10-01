'use client';

import React, { useEffect, useRef, useState } from 'react';

// Sandbox shell for the room. File commands (ls, cat, touch, rm, mv, echo >, npm install…)
// act on the room's real files; npm scripts produce simulated output until the room's WebContainer
// is connected.

export interface TerminalFs {
  files: Map<string, { content: string }>;
  write: (path: string, content: string) => void | Promise<void>;
  remove: (paths: string[]) => void;
  rename: (from: string, to: string) => void;
  open: (path: string) => void;
  problems: { errors: number; warnings: number; list: { path: string; line: number; message: string; severity: 'error' | 'warning' }[] };
}

type Kind = 'cmd' | 'out' | 'err' | 'ok' | 'dim' | 'info' | 'warn';
interface Line {
  id: number;
  kind: Kind;
  text: string;
  cwd?: string;
}

const COMMANDS = [
  'help', 'clear', 'ls', 'cd', 'pwd', 'cat', 'head', 'tail', 'wc', 'touch', 'mkdir', 'rm', 'mv', 'cp', 'echo', 'tree',
  'grep', 'open', 'code', 'npm', 'node', 'git', 'history', 'whoami', 'date', 'exit',
];

const HELP = `Sandbox shell · commands work on this room's files
  ls [dir]            list files          cd <dir>        change directory
  cat <file>          print a file        head/tail <f>   first/last 10 lines
  touch <file>        create empty file   mkdir <dir>     create a folder
  rm [-r] <path>      delete              mv / cp <a> <b> move / copy
  echo text > file    write (>> appends)  grep <text>     search file contents
  tree                show the project    open <file>     open in the editor
  npm install <pkg>   add a dependency    npm run <name>  run a package.json script
  git status/diff     what changed
  history · clear · exit                  ↑/↓ history · Tab completes · Ctrl+C stops · Ctrl+L clears`;

let lineId = 0;
const mk = (kind: Kind, text: string, cwd?: string): Line => ({ id: ++lineId, kind, text, cwd });

function norm(cwd: string, p = ''): string {
  const parts = (p.startsWith('/') || p.startsWith('~') ? p.replace(/^~\/?/, '').replace(/^\//, '') : `${cwd}/${p}`).split('/');
  const out: string[] = [];
  for (const part of parts) {
    if (!part || part === '.') continue;
    if (part === '..') out.pop();
    else out.push(part);
  }
  return out.join('/');
}

function dirsOf(files: Map<string, unknown>): Set<string> {
  const set = new Set<string>(['']);
  files.forEach((_, p) => {
    const parts = p.split('/');
    for (let i = 1; i < parts.length; i++) set.add(parts.slice(0, i).join('/'));
  });
  return set;
}

function tokenize(line: string): string[] {
  const out: string[] = [];
  const re = /"([^"]*)"|'([^']*)'|(\S+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line))) out.push(m[1] ?? m[2] ?? m[3]);
  return out;
}

interface TerminalProps {
  fs: TerminalFs;
  active: boolean;
  onExit: () => void;
}

export function Terminal({ fs, active, onExit }: TerminalProps) {
  const [lines, setLines] = useState<Line[]>(() => [
    mk('info', 'MUX sandbox shell — file commands act on this room’s files. Type `help` to see commands.'),
  ]);
  const [cwd, setCwdState] = useState('');
  // Chained commands (cd src && ls) run before React re-renders, so they read the directory from a ref
  const cwdRef = useRef('');
  const setCwd = (dir: string) => {
    cwdRef.current = dir;
    setCwdState(dir);
  };
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [histIdx, setHistIdx] = useState<number | null>(null);
  const [running, setRunning] = useState<string | null>(null); // long-running script, e.g. "dev"
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const snapshot = useRef(new Map(Array.from(fs.files).map(([p, f]) => [p, f.content]))); // for git status/diff
  const lastContents = useRef(new Map(Array.from(fs.files).map(([p, f]) => [p, f.content])));
  const fsRef = useRef(fs);
  fsRef.current = fs;

  const print = (...ls: Line[]) => setLines(prev => [...prev, ...ls].slice(-800));

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [lines]);

  useEffect(() => {
    if (active) inputRef.current?.focus();
  }, [active]);

  // While the dev server "runs", report file changes the way Vite's HMR does
  useEffect(() => {
    const changed: string[] = [];
    fs.files.forEach((f, p) => {
      if (lastContents.current.get(p) !== f.content) changed.push(p);
    });
    lastContents.current = new Map(Array.from(fs.files).map(([p, f]) => [p, f.content]));
    if (running === 'dev' && changed.length) {
      const t = new Date().toLocaleTimeString([], { hour12: false });
      print(...changed.map(p => mk(p.endsWith('.css') || p.endsWith('.tsx') || p.endsWith('.jsx') ? 'ok' : 'dim', `${t} [vite] ${p.endsWith('.html') || p === 'package.json' ? 'page reload' : 'hmr update'} /${p}`)));
    }
  }, [fs.files, running]);

  type PackageJson = { dependencies?: Record<string, string>; devDependencies?: Record<string, string>; scripts?: Record<string, string>; [key: string]: unknown };
  const readPkg = (): { pkg: PackageJson | null; error?: string } => {
    const raw = fsRef.current.files.get('package.json')?.content;
    if (raw === undefined) return { pkg: null, error: 'npm ERR! enoent Could not read package.json' };
    try {
      return { pkg: JSON.parse(raw) };
    } catch {
      return { pkg: null, error: 'npm ERR! package.json is not valid JSON' };
    }
  };

  const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

  const exec = async (raw: string): Promise<boolean> => {
    const { files } = fsRef.current;
    const cwd = cwdRef.current;
    const dirs = dirsOf(files);
    // echo with redirection is parsed before tokenizing so quotes stay intact
    const redirect = raw.match(/^echo\s+(.*?)\s*(>>?)\s*(\S+)\s*$/);
    if (redirect) {
      const text = redirect[1].replace(/^["']|["']$/g, '');
      const path = norm(cwd, redirect[3]);
      if (dirs.has(path)) return print(mk('err', `echo: ${redirect[3]}: Is a directory`)), false;
      const prev = files.get(path)?.content ?? '';
      await fsRef.current.write(path, redirect[2] === '>>' ? `${prev}${prev && !prev.endsWith('\n') ? '\n' : ''}${text}\n` : `${text}\n`);
      return true;
    }

    const [cmd, ...args] = tokenize(raw);
    const flags = args.filter(a => a.startsWith('-'));
    const params = args.filter(a => !a.startsWith('-'));
    const need = (n: number, usage: string) => {
      if (params.length < n) {
        print(mk('err', `usage: ${usage}`));
        return false;
      }
      return true;
    };
    const fileAt = (p: string) => {
      const path = norm(cwd, p);
      if (dirs.has(path)) return print(mk('err', `${cmd}: ${p}: Is a directory`)), null;
      const f = files.get(path);
      if (!f) return print(mk('err', `${cmd}: ${p}: No such file or directory`)), null;
      return { path, content: f.content };
    };

    switch (cmd) {
      case 'help':
        print(mk('out', HELP));
        return true;
      case 'clear':
        setLines([]);
        return true;
      case 'pwd':
        print(mk('out', `/workspace${cwd ? `/${cwd}` : ''}`));
        return true;
      case 'whoami':
        print(mk('out', 'demo-user'));
        return true;
      case 'date':
        print(mk('out', new Date().toString()));
        return true;
      case 'history':
        print(mk('out', history.map((h, i) => `${String(i + 1).padStart(4)}  ${h}`).join('\n') || ''));
        return true;
      case 'exit':
        onExit();
        return true;
      case 'cd': {
        const target = norm(cwd, params[0] ?? '~');
        if (!dirs.has(target)) return print(mk('err', `cd: no such directory: ${params[0]}`)), false;
        setCwd(target);
        return true;
      }
      case 'ls': {
        const target = norm(cwd, params[0] ?? '.');
        if (files.has(target)) return print(mk('out', target.split('/').pop()!)), true;
        if (!dirs.has(target)) return print(mk('err', `ls: ${params[0]}: No such file or directory`)), false;
        const prefix = target ? `${target}/` : '';
        const entries = new Map<string, boolean>();
        files.forEach((_, p) => {
          if (!p.startsWith(prefix)) return;
          const rest = p.slice(prefix.length).split('/');
          if (!flags.includes('-a') && rest[0].startsWith('.')) return;
          entries.set(rest[0], rest.length > 1 || (entries.get(rest[0]) ?? false));
        });
        const sorted = Array.from(entries).sort(([a, ad], [b, bd]) => (ad === bd ? a.localeCompare(b) : ad ? -1 : 1));
        if (flags.some(f => f.includes('l'))) {
          print(...sorted.map(([n, d]) => mk(d ? 'info' : 'out', d ? `drwxr-xr-x  ${n}/` : `-rw-r--r--  ${String((files.get(prefix + n)?.content.length ?? 0)).padStart(6)}  ${n}`)));
        } else {
          print(mk('out', sorted.map(([n, d]) => (d ? `${n}/` : n)).join('   ') || ''));
        }
        return true;
      }
      case 'tree': {
        const root = norm(cwd, params[0] ?? '.');
        const prefix = root ? `${root}/` : '';
        const paths = Array.from(files.keys()).filter(p => p.startsWith(prefix)).sort();
        const out: string[] = [root ? `${root}/` : '.'];
        const seen = new Set<string>();
        paths.forEach(p => {
          const parts = p.slice(prefix.length).split('/');
          parts.forEach((part, i) => {
            const key = parts.slice(0, i + 1).join('/');
            if (seen.has(key)) return;
            seen.add(key);
            out.push(`${'│   '.repeat(i)}├── ${part}${i < parts.length - 1 ? '/' : ''}`);
          });
        });
        print(mk('out', out.join('\n')), mk('dim', `${paths.length} files`));
        return true;
      }
      case 'cat': {
        if (!need(1, 'cat <file>')) return false;
        let ok = true;
        for (const p of params) {
          const f = fileAt(p);
          if (f) print(mk('out', f.content.replace(/\n$/, '')));
          else ok = false;
        }
        return ok;
      }
      case 'head':
      case 'tail': {
        if (!need(1, `${cmd} [-n N] <file>`)) return false;
        const nIdx = args.indexOf('-n');
        const n = nIdx >= 0 ? parseInt(args[nIdx + 1], 10) || 10 : 10;
        const f = fileAt(params[params.length - 1]);
        if (!f) return false;
        const ls = f.content.replace(/\n$/, '').split('\n');
        print(mk('out', (cmd === 'head' ? ls.slice(0, n) : ls.slice(-n)).join('\n')));
        return true;
      }
      case 'wc': {
        if (!need(1, 'wc [-l] <file>')) return false;
        const f = fileAt(params[0]);
        if (!f) return false;
        const lc = f.content.split('\n').length - (f.content.endsWith('\n') ? 1 : 0);
        print(mk('out', flags.includes('-l') ? `${lc} ${params[0]}` : `${lc} ${f.content.split(/\s+/).filter(Boolean).length} ${f.content.length} ${params[0]}`));
        return true;
      }
      case 'touch': {
        if (!need(1, 'touch <file>')) return false;
        for (const p of params) {
          const path = norm(cwd, p);
          if (!files.has(path)) await fsRef.current.write(path, '');
        }
        return true;
      }
      case 'mkdir': {
        if (!need(1, 'mkdir <dir>')) return false;
        for (const p of params) {
          const path = norm(cwd, p);
          if (dirs.has(path)) {
            if (!flags.includes('-p')) print(mk('err', `mkdir: ${p}: File exists`));
            continue;
          }
          // Folders only exist through their files, so a .gitkeep keeps the new one around
          await fsRef.current.write(`${path}/.gitkeep`, '');
        }
        return true;
      }
      case 'rm': {
        if (!need(1, 'rm [-r] <path>')) return false;
        const recursive = flags.some(f => f.includes('r'));
        const doomed: string[] = [];
        for (const p of params) {
          const path = norm(cwd, p);
          if (files.has(path)) doomed.push(path);
          else if (dirs.has(path) && path) {
            if (!recursive) {
              print(mk('err', `rm: ${p}: is a directory (use rm -r)`));
              continue;
            }
            files.forEach((_, fp) => { if (fp.startsWith(`${path}/`)) doomed.push(fp); });
          } else print(mk('err', `rm: ${p}: No such file or directory`));
        }
        if (doomed.length) fsRef.current.remove(doomed);
        return true;
      }
      case 'mv':
      case 'cp': {
        if (!need(2, `${cmd} <from> <to>`)) return false;
        const from = norm(cwd, params[0]);
        let to = norm(cwd, params[1]);
        const src = files.get(from);
        if (!src) return print(mk('err', `${cmd}: ${params[0]}: No such file`)), false;
        if (dirs.has(to)) to = `${to ? `${to}/` : ''}${from.split('/').pop()}`;
        if (cmd === 'mv') fsRef.current.rename(from, to);
        else await fsRef.current.write(to, src.content);
        return true;
      }
      case 'grep': {
        if (!need(1, 'grep [-i] <text> [path]')) return false;
        const ci = flags.includes('-i');
        const needle = ci ? params[0].toLowerCase() : params[0];
        const scope = params[1] ? norm(cwd, params[1]) : cwd;
        const hits: Line[] = [];
        files.forEach((f, p) => {
          if (scope && p !== scope && !p.startsWith(`${scope}/`)) return;
          f.content.split('\n').forEach((ln, i) => {
            if ((ci ? ln.toLowerCase() : ln).includes(needle)) hits.push(mk('out', `${p}:${i + 1}: ${ln.trim()}`));
          });
        });
        print(...(hits.length ? hits.slice(0, 200) : [mk('dim', 'no matches')]));
        return hits.length > 0;
      }
      case 'open':
      case 'code': {
        if (!need(1, `${cmd} <file>`)) return false;
        const f = fileAt(params[0]);
        if (!f) return false;
        fsRef.current.open(f.path);
        print(mk('dim', `opened ${f.path}`));
        return true;
      }
      case 'node':
        print(mk('out', args[0] === '-v' || args[0] === '--version' ? 'v20.11.1' : 'node: the sandbox runs Node in the room’s WebContainer; use npm scripts here.'));
        return true;
      case 'git': {
        const sub = params[0];
        const current = new Map(Array.from(files).map(([p, f]) => [p, f.content]));
        const added = Array.from(current.keys()).filter(p => !snapshot.current.has(p));
        const deleted = Array.from(snapshot.current.keys()).filter(p => !current.has(p));
        const modified = Array.from(current.keys()).filter(p => snapshot.current.has(p) && snapshot.current.get(p) !== current.get(p));
        if (sub === 'status') {
          if (!added.length && !deleted.length && !modified.length) return print(mk('out', 'On branch main\nnothing to commit, working tree clean')), true;
          print(mk('out', 'On branch main\nChanges since this terminal opened:'));
          print(...modified.map(p => mk('warn', `\tmodified:   ${p}`)), ...added.map(p => mk('ok', `\tnew file:   ${p}`)), ...deleted.map(p => mk('err', `\tdeleted:    ${p}`)));
          return true;
        }
        if (sub === 'diff') {
          const only = params[1] ? norm(cwd, params[1]) : null;
          const targets = [...modified, ...added].filter(p => !only || p === only);
          if (!targets.length) return print(mk('dim', 'no changes')), true;
          targets.forEach(p => {
            const before = (snapshot.current.get(p) ?? '').split('\n');
            const after = (current.get(p) ?? '').split('\n');
            print(mk('info', `diff --git a/${p} b/${p}`));
            const removed = before.filter(l => !after.includes(l));
            const addedLines = after.filter(l => !before.includes(l));
            print(...removed.slice(0, 40).map(l => mk('err', `- ${l}`)), ...addedLines.slice(0, 40).map(l => mk('ok', `+ ${l}`)));
          });
          return true;
        }
        print(mk('err', `git: '${sub ?? ''}' is not supported here (try git status, git diff). Use Export to GitHub to push.`));
        return false;
      }
      case 'npm': {
        const sub = params[0];
        if (args[0] === '-v' || args[0] === '--version') return print(mk('out', '10.2.4')), true;
        if (sub === 'install' || sub === 'i' || sub === 'add' || sub === 'uninstall' || sub === 'remove' || sub === 'rm') {
          const { pkg, error } = readPkg();
          if (!pkg) return print(mk('err', error!)), false;
          const names = params.slice(1);
          const dev = flags.includes('-D') || flags.includes('--save-dev');
          setBusy(true);
          await sleep(500 + names.length * 250);
          setBusy(false);
          if (!names.length) {
            const count = Object.keys(pkg.dependencies ?? {}).length + Object.keys(pkg.devDependencies ?? {}).length;
            print(mk('out', `\nup to date, audited ${count * 17 + 3} packages in 1s\n\nfound 0 vulnerabilities`));
            return true;
          }
          const removing = sub === 'uninstall' || sub === 'remove' || sub === 'rm';
          names.forEach(n => {
            const [name, version] = n.startsWith('@') ? [`@${n.slice(1).split('@')[0]}`, n.slice(1).split('@')[1]] : n.split('@');
            if (removing) {
              delete pkg.dependencies?.[name];
              delete pkg.devDependencies?.[name];
            } else {
              const key = dev ? 'devDependencies' : 'dependencies';
              pkg[key] = { ...(pkg[key] ?? {}), [name]: version ? `^${version.replace(/^\^/, '')}` : 'latest' };
              pkg[key] = Object.fromEntries(Object.entries(pkg[key]).sort(([a], [b]) => a.localeCompare(b)));
            }
          });
          await fsRef.current.write('package.json', `${JSON.stringify(pkg, null, 2)}\n`);
          print(mk('out', `\n${removing ? 'removed' : 'added'} ${names.length * 3 + 1} packages, and audited ${names.length * 12 + 180} packages in ${(0.8 + names.length * 0.4).toFixed(1)}s`), mk('ok', `${removing ? '−' : '+'} ${names.join(', ')}${dev && !removing ? ' (dev)' : ''} → package.json`));
          return true;
        }
        const script = sub === 'run' ? params[1] : sub === 'test' || sub === 'start' ? sub : null;
        if (!script) {
          print(mk('err', sub ? `npm: unknown command "${sub}"` : 'usage: npm install <pkg> | npm run <script> | npm test'));
          return false;
        }
        const { pkg, error } = readPkg();
        if (!pkg) return print(mk('err', error!)), false;
        const scripts: Record<string, string> = pkg.scripts ?? {};
        if (!scripts[script] && script !== 'test') {
          print(mk('err', `npm ERR! Missing script: "${script}"`), mk('dim', `Available: ${Object.keys(scripts).join(', ') || 'none'}`));
          return false;
        }
        print(mk('dim', `\n> ${pkg.name ?? 'app'}@${pkg.version ?? '0.0.0'} ${script}\n> ${scripts[script] ?? 'vitest run'}\n`));
        if (script === 'dev' || script.startsWith('dev:') || script === 'start' || script.startsWith('preview')) {
          setBusy(true);
          await sleep(700);
          setBusy(false);
          const port = script.startsWith('preview') ? 4173 : 5173;
          print(
            mk('ok', `  VITE v5.0.0  ready in ${320 + Math.round(Math.random() * 200)} ms`),
            mk('out', `\n  ➜  Local:   http://localhost:${port}/\n  ➜  Network: use --host to expose`),
            mk('dim', '\n  watching for file changes… press Ctrl+C to stop\n  (simulated here — the room’s WebContainer serves the real preview)'),
          );
          setRunning('dev');
          return true;
        }
        if (script === 'test') {
          setBusy(true);
          await sleep(800);
          setBusy(false);
          const tests = Array.from(files.keys()).filter(p => /\.(test|spec)\.[jt]sx?$/.test(p));
          if (!tests.length) return print(mk('warn', 'No test files found (looked for *.test.ts / *.spec.tsx)')), false;
          print(...tests.map(t => mk('ok', ` ✓ ${t}`)), mk('ok', `\n Test Files  ${tests.length} passed (${tests.length})`));
          return true;
        }
        // build / lint / anything else: fail on editor errors, otherwise succeed
        setBusy(true);
        await sleep(900);
        setBusy(false);
        const { errors, list } = fsRef.current.problems;
        if (errors > 0) {
          print(...list.filter(p => p.severity === 'error').slice(0, 20).map(p => mk('err', `${p.path}:${p.line} - error: ${p.message}`)), mk('err', `\nFound ${errors} error${errors === 1 ? '' : 's'}. Build failed.`));
          return false;
        }
        const code = Array.from(files).filter(([p]) => /\.(tsx?|jsx?|css)$/.test(p));
        const kb = (n: number) => `${(n / 1024).toFixed(2)} kB`;
        const js = code.filter(([p]) => !p.endsWith('.css')).reduce((n, [, f]) => n + f.content.length, 0);
        const css = code.filter(([p]) => p.endsWith('.css')).reduce((n, [, f]) => n + f.content.length, 0);
        print(
          mk('out', `vite v5.0.0 building for production...\n✓ ${code.length + 30} modules transformed.`),
          mk('dim', `dist/index.html                 0.46 kB\ndist/assets/index.css           ${kb(css * 0.7 + 800)}\ndist/assets/index.js            ${kb(js * 0.6 + 142_000)}`),
          mk('ok', `✓ built in ${(0.9 + code.length * 0.05).toFixed(2)}s`),
        );
        return true;
      }
      default:
        print(mk('err', `command not found: ${cmd}. Type \`help\` for the list.`));
        return false;
    }
  };

  const submit = async () => {
    const raw = input.trim();
    print(mk('cmd', input, cwd));
    setInput('');
    setHistIdx(null);
    if (!raw) return;
    setHistory(prev => (prev[prev.length - 1] === raw ? prev : [...prev, raw].slice(-200)));
    for (const part of raw.split('&&').map(s => s.trim()).filter(Boolean)) {
      const ok = await exec(part);
      if (!ok) break;
    }
  };

  const complete = () => {
    const tokens = input.split(' ');
    const last = tokens[tokens.length - 1];
    let options: string[];
    if (tokens.length === 1) {
      options = COMMANDS.filter(c => c.startsWith(last));
    } else {
      const slash = last.lastIndexOf('/');
      const dirPart = slash >= 0 ? last.slice(0, slash + 1) : '';
      const base = norm(cwd, dirPart || '.');
      const prefix = base ? `${base}/` : '';
      const names = new Set<string>();
      fs.files.forEach((_, p) => {
        if (!p.startsWith(prefix)) return;
        const rest = p.slice(prefix.length).split('/');
        names.add(rest.length > 1 ? `${rest[0]}/` : rest[0]);
      });
      options = Array.from(names).filter(n => n.startsWith(last.slice(slash + 1))).map(n => dirPart + n);
    }
    if (options.length === 1) {
      tokens[tokens.length - 1] = options[0];
      setInput(tokens.join(' ') + (options[0].endsWith('/') ? '' : ' '));
    } else if (options.length > 1) {
      print(mk('cmd', input, cwd), mk('dim', options.join('   ')));
      const common = options.reduce((a, b) => {
        let i = 0;
        while (i < a.length && a[i] === b[i]) i++;
        return a.slice(0, i);
      });
      if (common.length > last.length) {
        tokens[tokens.length - 1] = common;
        setInput(tokens.join(' '));
      }
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'c' && e.ctrlKey) {
      e.preventDefault();
      print(mk('cmd', `${input}^C`, cwd));
      if (running) print(mk('dim', 'dev server stopped'));
      setRunning(null);
      setInput('');
      return;
    }
    if (e.key === 'l' && e.ctrlKey) {
      e.preventDefault();
      setLines([]);
      return;
    }
    if (running || busy) {
      if (e.key === 'Enter') e.preventDefault();
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      submit();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      complete();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!history.length) return;
      const i = histIdx === null ? history.length - 1 : Math.max(0, histIdx - 1);
      setHistIdx(i);
      setInput(history[i]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (histIdx === null) return;
      const i = histIdx + 1;
      if (i >= history.length) {
        setHistIdx(null);
        setInput('');
      } else {
        setHistIdx(i);
        setInput(history[i]);
      }
    }
  };

  const prompt = (dir: string) => (
    <>
      <span className="text-[#3fb950]">demo@mux</span>
      <span className="text-[var(--faint)]">:</span>
      <span className="text-[var(--coord)]">~{dir ? `/${dir}` : ''}</span>
      <span className="text-[var(--faint)]">$ </span>
    </>
  );

  const color: Record<Kind, string> = {
    cmd: 'text-[var(--ink)]',
    out: 'text-[#c9d1d9]',
    err: 'text-[#ff7b72]',
    ok: 'text-[#3fb950]',
    dim: 'text-[var(--faint)]',
    info: 'text-[var(--coder)]',
    warn: 'text-[#d29922]',
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--code-bg)] font-mono text-[12.5px] leading-[1.55]" onClick={() => inputRef.current?.focus()} data-terminal>
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto px-3 py-2">
        {lines.map(l => (
          <div key={l.id} className={`whitespace-pre-wrap break-words ${color[l.kind]}`}>
            {l.kind === 'cmd' && prompt(l.cwd ?? '')}
            {l.text}
          </div>
        ))}
        <div className="flex items-center">
          {!running && prompt(cwd)}
          {busy && <span className="mr-2 inline-block h-3 w-3 animate-spin rounded-full border-[1.5px] border-[var(--coder)] border-t-transparent" />}
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            spellCheck={false}
            autoComplete="off"
            aria-label="Terminal input"
            className="min-w-0 flex-1 bg-transparent text-[var(--ink)] caret-[var(--coder)] outline-none"
            placeholder={running ? 'dev server running — Ctrl+C to stop' : ''}
          />
        </div>
      </div>
    </div>
  );
}
