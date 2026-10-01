// Making `npm install` fast in the browser (WebContainer) shell.

// Packages with native (C/C++) code: they try to download or compile a binary during install,
// which can't work in a browser, so npm install stalls or fails on them.
const NATIVE: Record<string, string> = {
  'better-sqlite3': 'use sql.js',
  sqlite3: 'use sql.js',
  bcrypt: 'use bcryptjs',
  argon2: 'use bcryptjs or hash-wasm',
  sharp: 'skip image processing here, or use @squoosh/lib / jimp',
  canvas: 'use @napi-rs/canvas off-browser, or skip',
  'node-sass': 'use sass',
  'node-gyp': '',
  re2: 'use the built-in RegExp',
  'cpu-features': '',
  ssh2: '',
  'node-pty': '',
  'zeromq': '',
  'grpc': 'use @grpc/grpc-js',
  'leveldown': 'use memory-level',
  'deasync': '',
  'fibers': '',
  'microtime': '',
};

export interface PackageCheck {
  native: { name: string; tip: string }[];
  total: number;
}

export function checkPackageJson(content: string | undefined): PackageCheck | null {
  if (!content) return null;
  try {
    const pkg = JSON.parse(content);
    const deps: Record<string, string> = { ...pkg.dependencies, ...pkg.devDependencies, ...pkg.optionalDependencies };
    const native = Object.keys(deps).filter(n => n in NATIVE).map(name => ({ name, tip: NATIVE[name] }));
    return { native, total: Object.keys(deps).length };
  } catch {
    return null;
  }
}

// Lines printed in the terminal when the project has packages that can't install in the browser
export function installWarning(check: PackageCheck | null): string[] {
  if (!check?.native.length) return [];
  return [
    `⚠ This project uses native packages that can't be built in the browser: ${check.native.map(n => n.name).join(', ')}`,
    `  npm install may stall on them. Options:`,
    `  • npm install --ignore-scripts   installs everything else (those packages won't work here)`,
    ...check.native.filter(n => n.tip).map(n => `  • ${n.name}: ${n.tip}`),
    `  • or Open in VS Code (activity bar) to install and run it on your computer`,
  ];
}
