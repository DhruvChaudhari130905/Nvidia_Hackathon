# Run Session: Changes Log

**Date:** 2026-10-07 · **Branch:** `dhruv/room-agents`

## Code changes
**`mux/web/src/lib/runtime.ts`: fix files vanishing from a room when the WebContainer switches rooms**
- Bug: `attachRoom` attached the new room, then wiped the previous room's files. The watcher saw the old files vanish and deleted the same paths from the new room (portfolio2 lost `index.html`, so its preview was white).
- Fix: detach the old room (clear tracked files, room fs and pending events) before the wipe, then attach the new room. Attaches now run one at a time, so the Terminal and Preview can't race.
- Verified: `tsc --noEmit` and `eslint` pass. There's no web test runner.

- Follow-up fix (`npm install` failed with `ENOENT … /home/project/package.json`): a file push already under way could write the new room's files during the wipe and mark them synced. The wipe then deleted them, and the attach push skipped them as "already synced"; "Try again" couldn't recover. Now the wipe runs in the same queue as pushes, and every attach re-sends all files. Verified in headless Chrome with real WebContainers: room A → B → A → B each showed its own app, and both rooms kept all their files. `tsc` and `eslint` pass.

- ~~No reinstall when returning to a room (in-memory `.mux-cache`)~~: replaced by the snapshots below.
- **npm install once per set of dependencies, reloads included** (`lib/packageSnapshots.ts` new, `lib/runtime.ts`)
  - After an install, `node_modules` is exported as a binary snapshot and saved in IndexedDB (`mux-packages`), keyed by a hash of `package.json` and shared by rooms with identical dependencies. Capped at 5 snapshots / 1.5 GB, least recently used dropped first.
  - Preview start: (1) the container's `node_modules` already matches `package.json` (marker) → start; (2) fresh container with a saved snapshot → restore it → start; (3) otherwise `npm install` + save a snapshot.
  - Room switches in one tab keep `node_modules` (the wipe skips it): same dependencies → no install; different → `npm install` brings it in line from npm's in-container cache.
  - WebContainer quirks found in testing: `mount()` silently does nothing for a missing folder or a container that has already installed; mounting into an existing folder works but drops the executable bit on `node_modules/.bin`. So restore only happens on a fresh container: create the folder, mount, wait for it, `chmod +x node_modules/.bin/*`.
  - A dev server crash drops the marker and that snapshot. Deleting a room releases its snapshots; one no other room uses is removed.
  - Verified with real WebContainers (jewellery Vite app): first visit installed (36 MB snapshot); reload → restored in about 1 s, app rendered; another room with the same deps in the same tab → no install; reload → restored; switching to a room with other deps and back → quick `npm install`; no restore warnings. `tsc` and `eslint` pass.

- Follow-up (`npm run start exited (code 1)` right after a skipped install, with Vite printing nothing): not reproduced. With the jewellery room's real files, a fresh start, a cache restore and a skipped install for portfolio2 (same `package.json`) all ran Vite fine. Safety change: when the dev server exits unexpectedly, the "installed" marker is removed, so "Try again" runs `npm install` instead of skipping it and can't get stuck. Verified with a deliberately crashing app: the retry ran `npm install`. Root cause still unknown.

- **Real cause of the Vite crash: one room's files copied into another.** At 23:36 UTC the browser sync rewrote portfolio2 with the jewellery room's files (10 written byte for byte, including `package.json` without Tailwind) and deleted 13 of its own (`postcss.config.js`, `tailwind.config.js`, `index.html`, tsconfigs…). Vite then failed on `Cannot find module 'tailwindcss'`.
  - Mechanism: a room's Preview and Terminal call `updateRoomFs` / `pushRoomFiles` on every render, before their attach has swapped the container. The calls carried no room id, so the sync briefly pointed at the new room while the container held the old room's files.
  - Fix: `updateRoomFs(roomId, …)`, `pushRoomFiles(roomId, …)` and `writeContainerFile(roomId, …)` now do nothing unless that room is the one mounted. Callers updated: `Preview.tsx`, `ShellTerminal.tsx`, `NewProjectMenu.tsx` (+ `BottomPanel.tsx`).
  - Verified with real WebContainers: jewellery → tiny → jewellery → portfolio2 (original Tailwind version), all apps ran, and every room's stored files stayed identical. `tsc` and `eslint` pass. The original contamination wasn't reproduced on demand; the fix removes the mechanism.
  - Data: portfolio2 needs restoring. Re-import `~/Codes/My-Portfolio` with **Replace**.

**Size cap for images, fonts and media raised to 2 MB** (text stays 1 MB)
- New `MAX_ASSET_BYTES` / `maxBytesFor(path)` in `lib/binaryFiles.ts`, used by import (`projectImport.ts`), upload (`FileTree.tsx`), terminal sync (`runtime.ts`) and VS Code sync (`vscodeExport.ts`).
- Verified: `tsc --noEmit` and `eslint src` pass.

**Plan starts empty and fills from chat** (no plan drafted at room creation)
- `mux/server/mux/rooms/runtime.py`: removed the auto `create_plan` on room creation. Each chat request the coordinator labels as new work becomes a plan task, and the coder starts it right away.
- `mux/web/src/components/side/PlanList.tsx`: empty plan shows "empty" plus a hint instead of "drafting…". Tasks added by hand start right away too, unless a draft is waiting for approval.
- `mux/server/tests/test_runtime.py`: tests seed their plan explicitly. New test: an empty room fills its plan from a chat message.
- Verified: backend `pytest` 228 passed; web `tsc` and `eslint` pass. Pyright isn't installed in the venv, so it wasn't run.

**Coder stopped with `400 … Expecting value: line 1 column 52`**
- Bug: when the model wrote a tool call with broken JSON arguments, the coder told it to retry but still sent the broken JSON back in the history. The API parses that history and rejected the whole request.
- `mux/server/mux/agents/coder/loop.py`: invalid or empty arguments are sent back as `{}`. The "Invalid JSON arguments, retry" reply is unchanged.
- `mux/server/mux/agents/llm.py`: arguments that are valid JSON but not an object (a list or a string) also count as invalid.
- New test in `tests/test_coder_loop.py`. Verified: `pytest` 229 passed.

**New room showed the previous room's preview**
- Bug: the previous room's dev server keeps running in the browser container after you leave. Preview showed any running server, so a new room without its own `package.json` showed the old room's app.
- `mux/web/src/lib/runtime.ts`: `runningServers(roomId)` only returns servers when that room is the one mounted in the container. Callers updated in `Preview.tsx` and `ShellTerminal.tsx`.
- Verified: `tsc` and `eslint` pass. Not yet checked in a browser.

**Coder added placeholder boxes instead of real images**
- Cause: the coder can only write text, so it used `via.placeholder.com` grey boxes. The plain-HTML preview also couldn't show room images that page scripts add (`<img src="${product.image}">`).
- New coder tool `add_image(query, path)` (`mux/server/mux/agents/coder/tools/images.py`): finds an openly licensed photo on Openverse (no API key), downloads it (falling back to Openverse's thumbnail, max 2 MB) and saves it into the room as an image file. Returns the path and a credit line.
- `mux/server/mux/agents/coder/prompts.py`: the coder must use `add_image` for pictures, never placeholder services or invented URLs.
- `mux/web/src/lib/staticPreview.ts`: the preview now also swaps in room images that scripts add after the page loads.
- Verified: `pytest` 232 passed (3 new tests); a live Openverse run saved real JPEGs; headless Chrome loaded script-added images; `tsc` and `eslint` pass.

- Follow-up: the `add_image` description now asks for one photo per picture and, in Vite/React projects, a path under `public/` (referenced as `/images/…`).

**Collapsible Feed and Decisions & plan columns**
- A button in each column header hides it. It shrinks to a 40px rail at the edge (label, plus an open-items badge on the right rail), and Preview/Code takes the space. Click the rail to bring it back.
- Hidden columns stay mounted, so chat drafts and scroll position are kept. The choice is remembered per browser (`localStorage`).
- Files: `components/room/PanelRail.tsx` (new), `Feed.tsx`, `SidePanel.tsx`, `app/room/[roomId]/page.tsx`, `lib/preferences.ts`, `app/globals.css`. Narrow screens keep the stacked layout.
- Verified: `tsc` and `eslint` pass. In headless Chrome (demo room at 1500px), the center grew from 810px to 1420px with both hidden, the state survived a reload, and reopening worked.

- Timeline (bottom) collapses too. A button in its header hides the track and leaves a one-line bar ("Timeline · N checkpoints"). "Return to latest" stays visible while rewound. Remembered per browser. Files: `components/timeline/Timeline.tsx`, page, `preferences.ts`, `globals.css`. Verified in headless Chrome: timeline 110px → 33px, the center gained 77px, and the state survived a reload.

**Fullscreen preview**
- A maximize button in the preview's address bar puts the preview frame into browser fullscreen. Click minimize or press Esc to return. It's the same frame, so the running app keeps its state.
- Files: `components/center/Preview.tsx` (`useFullscreen` hook and button in `PreviewFrame`), `app/globals.css`.
- Verified in headless Chrome: the frame went from 781×710 to 1500×900 and back. `tsc` and `eslint` pass.

**Coder finished image tasks half-done**
- Cause: asked for images of "all the jewelleries and jewellers", the coder added one photo, didn't put it on any page, and called `finish_task`. Nothing checked.
- `finish_task` is now refused (with the list of what's left) while a page uses a placeholder image service or a photo added in this task is unused. Placeholders count everywhere only when the task added photos; otherwise only in files the task created, so unrelated tasks aren't held up. Refused at most twice per task.
- Prompt: one photo per item, and a photo isn't done until a page uses it.
- Files: `mux/agents/coder/tools/images.py` (`picture_problems`), `tools/__init__.py`, `prompts.py`; 4 new tests. Verified: `pytest` 236 passed.

**Syntax and import check for the coder's JS/TS** (most rooms have no build runner)
- New `mux/server/mux/agents/coder/tools/codecheck.py`: parses `.js/.jsx/.mjs/.cjs/.ts/.tsx` with tree-sitter and reports the first syntax error per file (`path:line:col` plus the line), and relative imports of files that don't exist. A bare `&` in JSX text is accepted (as Babel/TS do).
- `write_file` / `edit_file` results now include `problems` right away. `finish_task` is refused while any code file is broken (shared 2-refusal cap with the picture check).
- If tree-sitter isn't installed, the syntax part is skipped and import checks still run.
- `pyproject.toml`: added `tree-sitter`, `tree-sitter-javascript`, `tree-sitter-typescript`.
- Verified: `pytest` 241 passed (5 new). Against all real rooms, results match the TypeScript compiler: the portfolio (81 files) is clean, the jewellery `App.jsx` comma and missing `index.css` are caught, and another room's real error is placed at 76:11 like `tsc`.

**Environment issue found: `mux/server/.venv` was copied from `~/Codes/Nvidia_Hackathon`**
- Its `pip`, `pytest`, `uvicorn`, `pyright` and `alembic` scripts run the other project's Python (`~/Codes/Nvidia_Hackathon/mux/server/.venv`). Code still loads from this repo, but libraries come from the other venv.
- My first `pip install` of tree-sitter went into the other project's venv by mistake. I uninstalled it there (nothing else touched) and installed into this venv with `.venv/bin/python -m pip`. Tests now run with `.venv/bin/python -m pytest`.
- Consequence: the running server (`make server`) uses the other venv, so it doesn't see tree-sitter. Syntax checks stay off there until the venv is rebuilt; import checks work.

**Delete room (owner only)**
- Uses the existing backend `POST /rooms/{id}/close` (owner only; a closed room is never reloaded, so it leaves everyone's list and its link 404s; history stays in the server's event log).
- UI: a trash button in the room's top bar and on your own dashboard cards (including the featured card). Hidden for non-owners and for built-in demo sample rooms.
- `components/room/DeleteRoomDialog.tsx` (new): type the room's name to enable **Delete room**. Afterwards it removes this browser's saved copy of the room's files and the header's "Back to …" link.
- Files: `lib/api.ts` (`closeRoom`; the demo handler now ignores query strings), `lib/demo.ts` (`deleteDemoRoom`), `lib/roomFiles.ts` (`deleteRoomFiles`), `lib/preferences.ts` + `components/shell/SiteHeader.tsx` (the header updates when the last room is cleared), `components/room/TopBar.tsx`, `app/dashboard/page.tsx`. New backend test: only the owner can close, and a closed room leaves the list.
- Verified: `pytest` 242 passed; `tsc` and `eslint` pass; in headless Chrome (demo mode), deleting from the room top bar and from a dashboard card both removed the room. The confirm button stays disabled until the name is typed, and sample rooms show no delete button.

## Not code bugs (data only)
- **Jewellery room (`room_f0c75b04aff2`), Vite error:** the coder's `src/App.jsx` is missing a comma (line 7) and imports a `src/index.css` that doesn't exist. The room has no build runner, so the coder never compiled it. Fix by asking the AI in chat, or add the comma by hand.
- **Portfolio room, images missing:** imported before image support existed. Re-import to bring them in. All 36 images now fit under the 2 MB cap.
- **portfolio2, missing files:** `index.html`, `.gitignore`, `README.md`, `components.json`, `eslint.config.js` and `info.md` were deleted by the bug above. Re-import with **Merge** to restore them.

## Environment actions
| # | Action | Command | Result |
|---|--------|---------|--------|
| 1 | Started Docker Desktop (wasn't running) | `open -a Docker` | Ready |
| 2 | Started local Postgres on `:5433` | `make db-up` | Container `server-postgres-1` healthy |
| 3 | Started API on `:8000` (auto-reload) | `make server` | `/health` → 200 `{"status":"healthy"}` |
| 4 | Started web app on `:3000` | `make web` | `/` and `/login` → 200 |

## Planned changes
- Waiting for approval: rebuild `mux/server/.venv` (`rm -rf mux/server/.venv && make setup-server`, then restart `make server`) so the server uses this project's own packages, including tree-sitter.

To stop everything:
- Stop the `make server` / `make web` processes
- `make db-down` to stop Postgres
