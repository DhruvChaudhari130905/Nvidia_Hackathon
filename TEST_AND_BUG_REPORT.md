# Test and Bug Report

**Date:** 2026-10-04  
**Scope:** Current working tree (including existing uncommitted changes). No application files were modified during testing.

## Result summary

| Area | Command | Result |
| --- | --- | --- |
| Backend tests | `cd mux/server && .venv/bin/pytest -q` | **Pass — 222 passed** |
| Backend type checking | `make typecheck-server` | **Pass — 0 errors, 0 warnings** |
| Frontend TypeScript | `cd mux/web && npx tsc --noEmit` | **Pass** |
| Frontend lint | `cd mux/web && npm run lint` | **Pass with 5 warnings** |
| Frontend production build | `cd mux/web && npm run build` | **Fail** |

The database-backed backend tests were run against the documented local Docker PostgreSQL service on port `5433` (`server-postgres-1`, PostgreSQL 16). All tests passed once that service was reachable.

## Confirmed blocker

### P0 — Frontend production build cannot complete

- **Command:** `make check-web`
- **Observed error:** During `next build`, after compilation, type checking, and linting, the build stops in **Collecting page data** with:

  ```text
  unhandledRejection Error [PageNotFoundError]: Cannot find module for page: /_document
  ```

- **Impact:** A deployable production frontend cannot be produced. This blocks CI/CD if it runs `make check-web` or `npm run build`.
- **Relevant configuration:** [mux/web/package.json](mux/web/package.json) pins Next.js to `15.0.0`. The test machine used Node.js `v26.10.0`; the project does not declare a Node version/engine constraint.
- **Suggested investigation:** Reproduce under a supported, pinned Node LTS release, then upgrade/patch Next.js if needed. Add an `engines.node` field and enforce the same version in local development and CI. Do not assume the build error is only an application route issue until it is reproduced with a supported runtime.

## Lint findings to address

These did not fail lint, but they identify likely correctness or accessibility issues.

| Priority | Finding | Location | Risk / recommended change |
| --- | --- | --- | --- |
| P1 | `useEffect` has missing dependencies: `loadInitialFiles`, `pullServerFiles`, and `state` | [mux/web/src/app/room/[roomId]/page.tsx](mux/web/src/app/room/[roomId]/page.tsx#L166) | The room initialization effect can retain stale functions/state when dependencies change. Stabilize callbacks with `useCallback` or restructure the effect and include its dependencies. |
| P2 | `useEffect` has missing dependency `currentUser.id` | [mux/web/src/components/side/ConflictCard.tsx](mux/web/src/components/side/ConflictCard.tsx#L48) | A switch of authenticated user without a new `conflict` object can show the previous user's vote. Include `currentUser.id` and reset `userVote` when there is no matching vote. |
| P2 | `treeitem` lacks required `aria-selected` | [mux/web/src/components/center/FileTree.tsx](mux/web/src/components/center/FileTree.tsx#L345) | Screen-reader users do not receive the selection state of the directory tree. Add `aria-selected={isTarget}` (or the appropriate selected-node state). |
| P3 | Unused `eslint-disable` directive | `mux/web/src/components/center/ImportProjectDialog.tsx:50` | Remove it so future suppressions remain meaningful. |
| P3 | External font stylesheet is loaded directly in the root layout | [mux/web/src/app/layout.tsx](mux/web/src/app/layout.tsx#L20) | Next warns that this loading pattern is discouraged. Use `next/font` or otherwise revise the font strategy to avoid page-scoped/preload behavior. |

## Coverage gap

The frontend has no test script or discovered unit/integration/end-to-end test suite. Type checking and linting run, but the current frontend build failure means there is no successful production-level verification either. Add at least component/unit coverage for room initialization, conflict voting, and file-tree accessibility, then add an end-to-end smoke test that builds and loads a room.

## Re-run checklist

```bash
# Start the documented database when it is not already running.
make db-up

# Backend (expects the test DB at localhost:5433).
make test-server
make typecheck-server

# Frontend.
make check-web
```

