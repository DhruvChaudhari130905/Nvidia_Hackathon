# MUX Coder Conventions

## General

- Keep changes small and directly related to the current task.
- Prefer existing project patterns over introducing new abstractions.
- Do not add dependencies unless the task explicitly requires them.
- Do not generate boilerplate that already exists in the starter template.

## Files

- Read a file before editing it.
- Use line-range reads when only part of a file is needed.
- Use `edit_file` for existing files when possible.
- Never overwrite changes made since the last read.
- Keep filenames and directory structure consistent with the starter template.

## React / TypeScript

- Use TypeScript.
- Keep React components focused and reusable.
- Prefer existing components and utilities before creating duplicates.
- Keep UI state close to the component that owns it unless shared state is required.

## Hono / Backend

- Keep routes small and explicit.
- Validate inputs at the route boundary.
- Reuse existing backend utilities instead of duplicating logic.

## Database

- Use the database approach already provided by the starter template.
- Do not introduce a second persistence mechanism.

## Validation

- Run the build after meaningful changes.
- Run relevant tests when available.
- Fix build errors before declaring the task complete.
- Do not claim success without a successful validation result.

## Task Completion

- Implement only the current task.
- If the task is blocked by a decision, use `ask_room`.
- When complete, call `finish_task` with a concise summary of what changed.