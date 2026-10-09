# Skills engine: design (plugins, part 1 of 3)

**Date:** 2026-10-09 · **Status:** approved in conversation, awaiting spec review

## Where this fits

MUX gets a Plugins feature like Claude Code's, built in three parts:

1. **Skills engine (this spec):** skill folders on the server, per-room switches, and the coder loading a
   skill's instructions when a task needs them.
2. **Plugins and marketplaces:** install Claude Code plugins (`.claude-plugin/plugin.json`) from
   marketplaces (`.claude-plugin/marketplace.json`) by git, pinned to a commit; a Plugins catalog in the room;
   a plugin's skills feed this engine, its MCP servers feed Tools, its commands feed part 3. The official
   Claude marketplace is an option the server admin switches on, not on by default.
3. **Commands:** a plugin's `commands/*.md` become `/commands` in the room's chat box.

## Goal

The coder can follow written guidance packs ("skills"), such as frontend-design or test-driven development,
in the same `SKILL.md` format Claude Code uses, so existing skill folders work unchanged. Each room's owner
chooses which skills the room's coder may use. The coder only loads a skill's full text when a task needs it.

## Decisions

| Question | Decision |
|---|---|
| Format | Claude Code's: a folder with `SKILL.md`, YAML frontmatter (`name`, `description`, optional others ignored), then the body. Other files in the folder are the skill's supporting files. |
| Where skills come from | Part 1: folders under the server's skills directory (`SKILLS_PATH`, default `skills`, relative to `mux/server`). Part 2 adds installed plugins' `skills/` folders as another source. |
| Who decides | The server admin puts skills on the server; each room's owner switches them on for the room. Off by default. |
| How the coder uses them | Progressive: the coder's system prompt lists each enabled skill's name and description; a `use_skill(name)` tool returns the full body and the list of supporting files; `read_skill_file(name, path)` reads one supporting file. |
| Which agents | The coder, in normal and review tasks. The coordinator doesn't use skills. |
| Skills written for Claude Code's own tools | Detected by a scan of the body (see Compatibility) and labelled "needs Claude Code" with the reasons. The owner can still switch one on; the label stays visible. |
| Visibility | Each `use_skill` shows in the feed: "Coder is using skill: frontend-design". Everyone in the room sees which skills are on. |

## Architecture

```
SKILLS_PATH/<folder>/SKILL.md ─► SkillLibrary (read at startup, refreshed on demand)
                                     │  name, description, body, files, compatibility
room events (owner) ─► RoomActor.skills_enabled: set[str]
                                     │
RoomRuntime._run ─► enabled skills ─► coder system prompt: "Skills you can use: ..." section
                                  └─► CoderToolExecutor(skills=...) adds use_skill / read_skill_file
```

### `mux/server/mux/skills/library.py`

- `Skill(name, description, body, root: Path, files: list[str], issues: list[str], source: str)`.
  `compatible` is `not issues`.
- `load_skill(folder: Path, source: str) -> Skill | None`: reads `SKILL.md` (at most 200 KB; larger → skipped
  with a log line), parses frontmatter with `yaml.safe_load`; `name` defaults to the folder name; names are
  `^[a-z0-9][a-z0-9_-]{0,63}$` after lowercasing; `description` is required (skipped without one) and cut to
  500 characters. `files`: every other regular file under the folder, relative paths, sorted, at most 100,
  skipping hidden files and symlinks.
- `SkillLibrary(roots: list[tuple[Path, str]])` with `skills() -> dict[str, Skill]` (first root wins on a
  name clash, the clash is logged) and `reload()`. A module-level `library()` returns the server's
  library over `[(Path(settings.skills_path), "server")]`, cached; tests replace it.

### Compatibility (`mux/server/mux/skills/compat.py`)

`claude_code_issues(body: str) -> list[str]`: case-sensitive checks for Claude Code tool names and
features MUX's coder doesn't have, each mapped to a short reason:

| Found | Reason shown |
|---|---|
| `TodoWrite`, `TaskCreate`, `TaskUpdate` | uses Claude Code's task list |
| `Task tool`, `Agent tool`, `subagent` | uses Claude Code sub-agents |
| `Skill tool`, `invoke the Skill` | loads other skills through Claude Code |
| `EnterPlanMode`, `ExitPlanMode` | uses Claude Code's plan mode |
| `git worktree` | uses git worktrees |
| `Bash tool`, `Bash(` | runs shell commands |

Only the first occurrence of each reason counts; the list is sorted.

### Room state and events

| Event | Fields | Sent to browsers as |
|---|---|---|
| `room_skills_set` | `enabled: list[str]` (sorted) | `skills.changed` `{enabled}` |

`RoomActor.skills_enabled: set[str]` rebuilt from it; `set_skills(enabled, user_id)` records it.
A name that no longer exists on the server is kept in the room's list (it may come back) but isn't offered.

### API (`mux/server/mux/api/skills.py`, under `/rooms`)

| Method and path | Who | What |
|---|---|---|
| `GET /rooms/{id}/skills` | viewer | `[{name, description, source, compatible, issues, enabled, files: count}]`, sorted by name |
| `PUT /rooms/{id}/skills` | owner | `{enabled: [names]}`; unknown names → 400; at most 30 enabled |
| `POST /rooms/{id}/skills/reload` | owner | Re-reads the skills folder (picks up skills added on the server) and returns the list |

### Coder integration

- `RoomRuntime._run` passes the room's enabled, existing skills to `CoderToolExecutor(skills=...)` and to
  `_context`.
- `_context` appends to the system prompt (normal and review prompts):
  ```
  Skills you can use (call use_skill with the name before following one; only when the task needs it):
  - frontend-design: Create distinctive, production-grade frontend interfaces...
  ```
  At most 30 skills listed; each description on one line, at most 300 characters.
- New tools, offered only when the room has at least one enabled skill (and in review mode too, as they only read):
  - `use_skill(name)` → `{"ok": true, "name", "instructions": body (at most 30,000 characters, with a note when cut), "files": [...]}`;
    unknown or disabled name → `{"ok": false, "error": "No skill named X is switched on in this room"}`.
  - `read_skill_file(name, path)` → `{"ok": true, "path", "content"}` for a listed file (text, at most 30,000
    characters); anything else → `{"ok": false, "error": ...}`. Paths are matched against the skill's
    `files` list exactly, so no path can leave the skill's folder.
- `_Narrated` posts `skill.used` `{name}` to the feed when `use_skill` succeeds.
- Compaction keeps the latest `use_skill` result in full like a file read (same budget), so the coder
  doesn't reload a skill every turn.

### Web UI

- The Tools dialog (`ToolsDialog.tsx`) gets a **Skills** section above MCP servers: each skill with its
  description, a "needs Claude Code" badge with the reasons as a tooltip, the source, and a switch (owner
  only; others see the state). An owner **Reload** button re-reads the server folder. Part 2 moves this
  into the Plugins catalog.
- The feed shows `skill.used` as a coder line: "Using skill: frontend-design".

### Settings and docs

- `SKILLS_PATH` (default `skills`), documented in `.env.example`; an example skill
  `mux/server/skills/example-clean-code/SKILL.md` ships so the folder isn't empty.
- `docs/03-getting-started.md` gets a "Skills" section: where to put skill folders (including copying
  from `~/.claude/plugins/cache/...` or a skill's repo), switching them on per room, the Claude Code
  compatibility label, and a note to check each skill's license.

## Error handling

| Situation | Result |
|---|---|
| Skills folder missing | No skills; no error |
| `SKILL.md` unreadable, too big, no description, bad name | That skill skipped, logged |
| Two skills with one name | First kept, clash logged |
| Room enables a skill later removed from the server | Kept in the room's list, not offered, shown as "missing" |
| `use_skill` / `read_skill_file` misuse | `{"ok": false, "error"}` to the coder |

## Testing

- Library: frontmatter parsing, name defaults and validation, missing description, size limit, file listing
  (no hidden files, no symlinks), clashes, reload.
- Compatibility: each pattern → its reason; a plain guidance skill → no issues.
- API: viewer reads, owner sets, unknown name 400, limit, reload, survives rehydration.
- Coder: tools offered only with enabled skills; `use_skill` returns the body and files; disabled or
  unknown skill refused; `read_skill_file` only for listed files; review tasks get the skill tools but still
  no write tools; system prompt lists enabled skills; `skill.used` reaches the feed; compaction keeps the
  latest skill text.
- Web: `tsc`, lint, build.

## Out of scope (parts 2 and 3)

Plugins, marketplaces, git installs, per-room uploaded skills, commands, hooks, Claude Code agents.
