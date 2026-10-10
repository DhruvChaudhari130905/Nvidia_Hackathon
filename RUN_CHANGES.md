# Run Session: Changes Log

Everything done on MUX from the start, oldest first. The 2026-10-07 session is logged in full at the end.

## Project history before 2026-10-07
- **2026-09-30:** Initial commit. Added the MUX scaffold, demos and design docs.
- **2026-10-01:** Built out the web app: rooms, sandbox, pricing, docs and the room workspace.
- **2026-10-02:** Added the P-Agent-A coordinator, Tavily research and memory. Added the Agent/Team toggle in the composer and team notes, which the coordinator sees as context only. Added the coder agent with its tools, a repo map and a token eval. Added the README, the docs folder and session logs, and recorded open decisions Q40–Q55.
- **2026-10-04:** Added the database layer and routed the coder's saves and builds through it. Implemented the room backend (actor, registry, API, WebSocket) with review fixes (PR #2). Made the project runnable, connected the web app to the room backend and ran the coordinator and coder in every room.

## 2026-10-09 → 2026-10-10 (branch `dhruv/room-agents`, now on `main`)

**Joining rooms** (`bb37c35`)
- Teams can join by viewer link, Supabase email invite or room password, with a lockout after failed attempts. `make tunnel` lets teammates on other machines join.
- Fixed uploads being refused for files that already exist, and duplicate presence entries.

**MCP tools in rooms** (design spec, plan, then `a71861d` … `67fa874`)
- Server-wide MCP servers load from `mcp.json` (example included). Room owners add, refresh and configure their own servers through the room MCP API and the new **Tools** dialog.
- Room MCP server URLs are checked (private and non-global addresses are refused) and their tokens are encrypted. Settings are kept as room events.
- The coder gets the room's MCP tools for one task, asking the room first where an owner set that.
- Each server's connection runs in its own task, so a server that hangs or crashes fails only its own calls. Tokens and header values are kept out of error text.

**Coder and coordinator fixes**
- `f22b609`, `64c0682`: the coder no longer re-reads files until it runs out of turns. Compaction keeps the latest read of each file in full, within a 60k-character budget, and repeating a call when no file changed counts as a loop.
- `6b2bdbd`: the coordinator is told whether building is in progress, waiting or blocked on **Approve plan**, and may not promise work it can't do.
- `4112212`: "Review my project" creates a read-only review task, and its written review appears in the feed. The coder's task summaries now show in the feed.

**Per-room AI providers** (design spec, plan, then `b15c47f` … `73ff43a`)
- Each room can run its agents on its own OpenAI-compatible provider (Nebius Token Factory, OpenAI, Anthropic, OpenRouter, Groq, Together or a custom URL), choosing a model for each role: Coordinator, Coder and Coder when stuck.
- Saving sends one tiny request to each model to check the key and the model ids. Keys are encrypted with `ROOM_SECRETS_KEY`, which MCP tokens now share (the old `MCP_ENCRYPTION_KEY` still works). Model errors are reported in the room.
- Security review fixes: provider redirects aren't followed, the base URL is checked again before each use, keys are kept out of logged tracebacks, review tasks get no MCP tools, and the save check doesn't retry and gives up after 20 s.

**Dashboard imports reach the server** (`80a4bd5`)
- Projects imported from the dashboard were only kept in the browser, so the agents never saw them. Each file is now saved to the room like an in-room upload.

**Room kickoff: "Plan it with me"** (design spec, plan, then `ba464dc` … `e2cc7bc`)
- The create and import dialogs and the empty plan offer **Plan it with me**: the planner reads the project, asks the team questions, then drafts a plan.
- Review fixes: the kickoff no longer waits forever for a project read that won't run (it times out and plans from the description), chat requests sent during the kickoff aren't dropped, and change requests sent during a read-only task become tasks.

**Real code reviews** (`8e16b88`)
- A room review now covers every source file (not lockfiles, assets or build output), has a `search_code` tool and 60 turns, and doesn't see the plan.
- It can't finish until it has read the files, and must report Critical/Important/Minor findings with file:line, scenario and fix, plus a verdict and "Files reviewed: N of M". After two refusals its summary is accepted as written, so it can't get stuck.

**Skills engine** (design spec, plan, then `1fba38f` … `3214c32`)
- MUX reads skill folders (`SKILL.md`, the Claude Code format) from `SKILLS_PATH` and flags skills that need Claude Code itself.
- Rooms switch skills on in the **Tools** dialog; the choice is kept as a room event and shown in the feed. The coder loads a skill with `use_skill`. An example skill and docs were added.
- Review fixes: a source file that can't be read no longer blocks a review, loading a skill again never counts as a loop, supporting files over 1 MB aren't read into memory, and `SKILL.md` files with a BOM or a colon in an unquoted description now load.

## This session (2026-10-10)
- **How to use a Claude API key in MUX:** get the key at console.anthropic.com (**Settings → API Keys**, after adding credits under **Billing**). Then set `ROOM_SECRETS_KEY` in `mux/server/.env`, open the room's **AI model** dialog, choose **Anthropic**, paste the `sk-ant-…` key and click **Save**. The default models are Haiku 4.5, Sonnet 5.5 and Opus 5.5. To make Claude the server-wide default instead, set the `TOKEN_FACTORY_*` and `MODEL_*` variables to the Anthropic URL, key and model ids (not tested).
- **Pushed to `main`:** `dhruv/room-agents` was fast-forwarded onto `origin/main` (`3707b6e..3214c32`, 46 commits). Before pushing I checked that no `.env` files or API keys were in the commits. `Concept.txt`, `package-lock.json` and `mux/package-lock.json` are still uncommitted.

---

# 2026-10-07 session

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
