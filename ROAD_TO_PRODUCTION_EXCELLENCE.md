# Road to Production Excellence

**Current baseline:** 63/100  
**Goal:** a production-excellent application across reliability, security, quality, accessibility, testing, deployment, and user experience.

**Last updated:** 2026-10-04 (see [Progress](#progress) for what is done)

> A literal 100/100 is a moving target. This plan defines the practical equivalent: no known release blockers, strong automated confidence, secure defaults, observable operations, and a polished experience validated with users.

## Priority order

1. Make production builds reliable.
2. Add frontend automated testing.
3. Remove lint, accessibility, and React correctness warnings.
4. Harden realtime collaboration and error recovery.
5. Complete security and privacy work.
6. Make deployment and operations repeatable.
7. Validate and polish the user experience.
8. Sustain maintainable architecture and engineering process.

## 1. Production build reliability

### Former blocker (resolved 2026-10-04)

The frontend production build failed while collecting page data:

```text
PageNotFoundError: Cannot find module for page: /_document
```

Cause: `next build` and `next dev` both wrote to `.next`, so a build run while the dev server was up read a
half-written dev output. `next.config.ts` now takes `NEXT_DIST_DIR`, and `make check-web` builds into
`.next-build`. The build passes on a clean folder with Next.js 15.5.27 (verified locally on Node 26; CI runs
the pinned Node 24 LTS).

### Actions

- Reproduce the build with a supported, pinned Node.js LTS version.
- Add `.nvmrc` and/or `engines.node` in `mux/web/package.json`.
- Verify the lockfile and installed dependencies after changing runtimes.
- Investigate and fix or upgrade the pinned `next@15.0.0` dependency as needed.
- Run `make check-web` in continuous integration and block merges/deployments when it fails.

### Done when

- `make check-web` succeeds locally and in CI on a clean checkout.
- The same Node version is used by developers, CI, preview environments, and production.
- The build is required before release.

## 2. Frontend test coverage

### Actions

- Add unit tests for reducers and utilities, including file paths, project import, formatting, runtime selection, and API helpers.
- Add component tests for room loading, file-tree operations, save states, conflict voting, and authentication redirects.
- Add Playwright end-to-end tests covering:
  - sign in and sign out;
  - create and join a room;
  - edit, save, and reload a file;
  - two-user collaboration and conflict handling;
  - code execution and preview;
  - project import and export.
- Capture screenshots/video/traces for failed end-to-end tests.
- Set a coverage target of at least 80% for business-critical frontend logic.

### Done when

- Frontend unit, component, and end-to-end test commands run in CI.
- Core user journeys are tested before release.
- A regression in room editing, saving, collaboration, or auth fails CI.

## 3. Code quality and accessibility

### Findings (all resolved 2026-10-04; lint now reports 0 warnings)

- ~~The room initialization effect has missing React dependencies.~~ It also hid two bugs, both fixed:
  presence updates were dropped (a stale `state` check), and socket subscriptions were never removed
  (cleanup was returned from inside an async function).
- ~~The conflict card effect omits `currentUser.id`.~~ The user's vote is now recomputed (and cleared)
  when the signed-in user changes.
- ~~File-tree `treeitem` nodes lack `aria-selected`.~~
- ~~An unused ESLint suppression remains in the import dialog.~~
- ~~The root layout loads external fonts in a way Next.js warns about.~~ Fonts are self-hosted with
  `next/font` (Mona Sans from `src/app/fonts/`), so pages make no requests to Google.

### Actions

- Stabilize callbacks with `useCallback` or restructure effects, then include complete dependency arrays.
- Reset a conflict card's user-vote state when the active user changes.
- Add appropriate `aria-selected` state and keyboard-navigation tests to the file tree.
- Remove unused linter suppressions.
- Use `next/font` or an equivalent supported font-loading strategy.
- Configure CI to fail on all lint warnings, not only errors.
- Audit focus handling, contrast, semantic landmarks, screen-reader labels, and mobile layouts.

### Done when

- Type checking and linting report zero errors and zero warnings.
- Keyboard-only users can complete every critical flow.
- A screen reader accurately reports selection, state, errors, and dialogs.

## 4. Realtime reliability and recovery

### Actions

- Test WebSocket reconnects, duplicate messages, delayed events, stale file versions, and simultaneous saves.
- Define conflict resolution rules for every write path.
- Add retry/backoff policies for API, socket, sandbox, and authentication failures.
- Clearly tell users when work is unsaved, syncing, conflicted, or safely persisted.
- Test data recovery after browser refresh, reconnect, server restart, and partial network loss.
- Add load tests for concurrent rooms and active participants.

### Done when

- Reconnects do not silently lose edits.
- Concurrent editing has deterministic, user-visible resolution.
- Performance and error behavior are measured at expected peak load.

## 5. Security and privacy

### Actions

- Run dependency, secret, static-analysis, and container-image scans in CI.
- Add request rate limits, payload/file-size limits, upload validation, and audit logs.
- Test every REST and WebSocket operation for authorization bypasses.
- Add adversarial tests for path traversal, malformed events, injection, and sandbox escape attempts.
- Enforce secure production configuration: no development token bypasses, no test keys, and no permissive origins.
- Define retention, deletion, export, and access-control policies for room/project data.

### Done when

- No unresolved critical/high severity security findings remain.
- Access-control tests cover every sensitive operation.
- Production secrets and configuration are managed outside the source tree.

## 6. Deployment and operations

### Actions

- Maintain separate development, staging, and production environments.
- Add CI stages for backend tests, type checks, lint, frontend build, frontend tests, security scanning, and end-to-end smoke tests.
- Deploy preview environments for pull requests.
- Verify database migrations before release and rehearse backup/restore.
- Add structured logs, error tracking, tracing, uptime monitoring, and performance dashboards.
- Document release, rollback, incident-response, and recovery procedures.

### Done when

- Every production release is reproducible from CI.
- A rollback is documented and tested.
- Alerts identify meaningful failures before users report them.

## 7. Product and UX validation

### Actions

- Conduct usability tests with target developers and teams.
- Measure time-to-first-project, successful collaboration sessions, task completion, and recovery from errors.
- Improve onboarding, empty states, loading states, permissions explanations, and error messages.
- Test responsive/mobile behavior where it is intended to be supported.
- Add privacy-respecting analytics to identify abandonment and slow flows.

### Done when

- New users can create, collaborate on, run, and export a project without assistance.
- Usability findings are tracked and resolved before broad release.

## 8. Sustainable engineering process

### Actions

- Record major architectural choices in architecture decision records.
- Enforce formatting, review, protected branches, and required CI checks.
- Keep modules/components focused and define ownership boundaries.
- Schedule dependency updates and periodic security reviews.
- Track reliability, performance, accessibility, and test coverage as ongoing product metrics.

### Done when

- The codebase remains easy to change safely.
- Quality does not depend on individual memory or manual release rituals.

## First seven days

1. ✅ Fix the `next build` failure and verify a clean production build.
2. ✅ Pin Node.js LTS and enforce it in CI.
3. ✅ Resolve every current frontend lint warning.
4. ⬜ Add end-to-end smoke tests for login, room creation, editing, saving, and preview.
5. ✅ Add dependency and secret scanning.
6. ⬜ Add structured frontend/backend error logging and error tracking.
7. 🟡 Make successful checks mandatory for merge and deployment. CI exists; marking its checks as
   required is a GitHub branch-protection setting the repo owner turns on.

## Definition of release excellence

Release only when all of the following are true:

- All backend, frontend, integration, and end-to-end tests pass.
- Type checks, lint, security scans, and production builds have no errors or warnings.
- Critical user paths are tested in a staging environment.
- No known high/critical security issue is open.
- Monitoring, backups, rollback, and incident procedures are proven.
- Accessibility and usability validation has been completed for core flows.

## Progress

### 2026-10-04

**Builds and tooling**
- Production build fixed (see section 1). `make check-web` = type check + ESLint with `--max-warnings=0`
  + production build into `.next-build`.
- Node pinned: `.nvmrc` (24 LTS) at the repo root and in `mux/web`, `engines.node` `>=22.12.0 <27`.
- Next.js 15.0.0 → 15.5.27. `npm run lint` runs ESLint directly (`next lint` is removed in Next.js 16);
  `eslint.config.mjs` ignores build output.

**CI** (`.github/workflows/ci.yml`, on every push to `main` and every pull request)
- *backend*: pytest against a Postgres 16 service, then pyright.
- *web*: `make check-web` on the pinned Node.
- *security*: gitleaks secret scan, `npm audit` of shipped web dependencies (fails on critical), and
  `pip-audit --strict` of the backend dependencies.

**Security**
- Web: the critical Next.js advisories are fixed by the upgrade. Still open (`npm audit --omit=dev`):
  1 high (`postcss` bundled inside Next.js, build-time only) and 1 moderate (Next.js), both fixed only in
  Next.js 16; 2 low (`dompurify` via `monaco-editor`, no fixed release yet). Raise the CI audit level to
  `high` after the Next.js 16 upgrade.
- Backend: `python-jose` (and its vulnerable `ecdsa` dependency) replaced by PyJWT for Supabase token
  checks, including ES256 keys from the project's JWKS. `pip-audit`: no known vulnerabilities.
- Saving a file where a folder is (or inside a file) is refused with 409 instead of a server error.

**Reliability fixes found on the way**
- Room events are stored on disk and rooms rebuild after a restart (section 4: "server restart").
- The WebContainer file sync no longer uploads folders as empty files.

**Next up:** Playwright smoke tests (item 4), error tracking (item 6), required checks on `main` (item 7),
then the Next.js 16 upgrade to close the remaining web advisories.
