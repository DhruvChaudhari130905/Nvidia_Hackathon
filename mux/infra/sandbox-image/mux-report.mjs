#!/usr/bin/env node
// Runs a build or test command inside the sandbox and prints a short report the backend parses
// (mux/server/mux/sandbox/runner.py). The sandbox cuts output at 8 KB, so the raw output is never printed:
//   - at most 20 lines `file:line: message` (paths relative to the project)
//   - when nothing could be parsed and the command failed, the last 20 lines of its output instead
//   - test mode only: a last line `MUX_SUMMARY {"passed": n, "failed": m}`
// The exit code is the command's.
//
// Usage: mux-report build '<command>'
//        mux-report test '<command>' [file pattern]

import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, relative } from 'node:path'

const MAX_LINES = 20
const ROOT = process.cwd()
const ANSI = /\x1b\[[0-9;]*[A-Za-z]/g

const [mode, command, ...args] = process.argv.slice(2)
if (!['build', 'test'].includes(mode) || !command) {
  console.error("usage: mux-report build|test '<command>' [args...]")
  process.exit(2)
}

const quote = s => `'${String(s).replace(/'/g, `'\\''`)}'`

function run(cmd) {
  const res = spawnSync('sh', ['-c', cmd], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
  const output = `${res.stdout ?? ''}\n${res.stderr ?? ''}`.replace(ANSI, '')
  return { code: res.status ?? 1, output }
}

// A path as the project sees it: relative to the project root, forward slashes
function projectPath(p) {
  const rel = p.startsWith('/') ? relative(ROOT, p) : p
  return rel.replace(/\\/g, '/').replace(/^\.\//, '')
}

const oneLine = s => s.split(`${ROOT}/`).join('').replace(/\s+/g, ' ').trim()

const TSC = /^(?<file>[^\s(][^(]*)\((?<line>\d+),\d+\): error (?<code>TS\d+): (?<msg>.*)$/
const LOCATED = /(?<file>(?:\/|\.\/)?[\w@.\-/]+\.(?:tsx?|jsx?|mjs|cjs|css|html|json))[:(](?<line>\d+)[:,]\d+\)?/

function buildReport(output) {
  const lines = []
  const all = output.split('\n')
  for (let i = 0; i < all.length; i++) {
    const raw = all[i].trim()
    const tsc = TSC.exec(raw)
    if (tsc) {
      lines.push(`${projectPath(tsc.groups.file)}:${tsc.groups.line}: ${tsc.groups.code}: ${oneLine(tsc.groups.msg)}`)
      continue
    }
    // Vite / esbuild / Rollup: "file:line:col: ERROR: msg", "[vite:esbuild] Transform failed ... file: path:line:col"
    const loc = LOCATED.exec(raw)
    if (loc && /error|failed|could not|cannot|unexpected|expected/i.test(raw + (all[i + 1] ?? ''))) {
      const file = projectPath(loc.groups.file)
      if (file.startsWith('node_modules/') || file.startsWith('..')) continue
      const after = oneLine(raw.slice(loc.index + loc[0].length).replace(/^[:\s-]+/, '').replace(/^ERROR:\s*/, ''))
      const before = oneLine(raw.slice(0, loc.index).replace(/^\[[\w:-]+\]\s*/, '').replace(/\bfile:\s*$/, ''))
      const msg = after || before || oneLine(all[i + 1] ?? '') || 'error'
      lines.push(`${file}:${loc.groups.line}: ${msg}`)
    }
  }
  return lines
}

// A failing test's location: the first stack frame in a test or source file of the project
function stackLocation(text) {
  for (const m of text.matchAll(new RegExp(LOCATED.source, 'g'))) {
    const file = projectPath(m.groups.file)
    if (!file.startsWith('node_modules/') && !file.startsWith('..')) return { file, line: m.groups.line }
  }
  return null
}

function testReport(reportFile) {
  const report = JSON.parse(readFileSync(reportFile, 'utf8'))
  const lines = []
  let loadFailures = 0
  for (const suite of report.testResults ?? []) {
    const file = projectPath(suite.name ?? '')
    const failed = (suite.assertionResults ?? []).filter(a => a.status === 'failed')
    for (const a of failed) {
      const message = (a.failureMessages ?? []).join('\n')
      const where = a.location ? { file, line: a.location.line } : stackLocation(message) ?? { file, line: 1 }
      const first = oneLine(message.split('\n').find(l => l.trim()) ?? 'failed')
      lines.push(`${where.file}:${where.line}: ${a.fullName ?? a.title}: ${first}`)
    }
    // A file that failed to load (syntax error, failing import) has no assertions, only a message
    if (!failed.length && suite.status === 'failed') {
      loadFailures += 1
      if (!suite.message) continue
      const where = stackLocation(suite.message) ?? { file, line: 1 }
      lines.push(`${where.file}:${where.line}: ${oneLine(suite.message.split('\n')[0])}`)
    }
  }
  return {
    lines,
    passed: report.numPassedTests ?? 0,
    // a file that failed to load counts as one failure
    failed: (report.numFailedTests ?? 0) + loadFailures,
  }
}

function tail(output) {
  return output.split('\n').map(l => l.trimEnd()).filter(Boolean).slice(-MAX_LINES)
}

let lines = []
let code
if (mode === 'build') {
  const res = run(command)
  code = res.code
  lines = code === 0 ? [] : buildReport(res.output)
  if (code !== 0 && lines.length === 0) lines = tail(res.output)
} else {
  const reportFile = join(tmpdir(), `mux-vitest-${process.pid}.json`)
  const res = run([command, '--reporter=json', `--outputFile=${quote(reportFile)}`, ...args.map(quote)].join(' '))
  code = res.code
  let summary = null
  if (existsSync(reportFile)) {
    try {
      const r = testReport(reportFile)
      lines = r.lines
      summary = { passed: r.passed, failed: r.failed }
    } catch {
      summary = null
    }
    rmSync(reportFile, { force: true })
  }
  if (code !== 0 && lines.length === 0) lines = tail(res.output)
  const out = [...new Set(lines)].slice(0, MAX_LINES).join('\n')
  if (out) console.log(out)
  if (summary) console.log(`MUX_SUMMARY ${JSON.stringify(summary)}`)
  process.exit(code)
}
const out = [...new Set(lines)].slice(0, MAX_LINES).join('\n')
if (out) console.log(out)
process.exit(code)
