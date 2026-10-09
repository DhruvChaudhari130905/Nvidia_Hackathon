# MCP tools for the coder: design

**Date:** 2026-10-09 · **Status:** approved in conversation, awaiting spec review

## Goal

Let the coder agent use tools from MCP (Model Context Protocol) servers, so a room can give it access to
things like GitHub issues, a database, or docs search without MUX building each integration.

Two sources of servers:

- **(A) Server-wide**, from an `mcp.json` file the person running the MUX server edits. Local (stdio,
  runs a command on the server) and remote (streamable HTTP) servers are both allowed. Available to every
  room; each room's owner switches them on for that room.
- **(B) Per room**, added by the room's owner in the UI. **Remote (https) only**: a room owner must never
  be able to run a command on the MUX server.

## Decisions

| Question | Decision |
|---|---|
| Which agent gets MCP tools | The coder only. The coordinator routes messages and doesn't need them. |
| Approval | Every MCP tool has a mode, `auto` (default) or `ask`. The owner sets it per tool. `ask` puts an Allow / Deny question card in the room and waits; no answer before it expires means Deny. |
| Visibility | Every MCP call appears in the feed like built-in tool calls (`tool.called` / `tool.result`), including for `auto` tools. Everyone in the room can see which MCP tools are on. |
| Where room settings live | Room events (the event log), like sharing, invites and the room password. No database change. |
| Connection lifetime | Connect when a coder task starts, disconnect when it ends. No connections are kept between tasks. |
| Admin servers default | Off in every room until that room's owner turns them on. |

## Architecture

```
mcp.json (admin) ─┐
                  ├─► McpCatalog: for one room, the enabled servers and each tool's on/off + auto/ask
room events ──────┘                      │
(owner, via UI)                          ▼
                       McpToolset: one per coder task
                        • connects to each enabled server (mcp SDK: stdio / streamable HTTP)
                        • offers their enabled tools to the model as  <server>__<tool>
                        • routes those calls to the right session; `ask` tools wait for the room
                        • closes every session when the task ends
                                         │
                       wraps CoderToolExecutor (built-in tools, unchanged)
```

### New modules (`mux/server/mux/mcp/`)

- **`config.py`**: loads `mcp.json` (path from the `MCP_CONFIG_PATH` setting, default `./mcp.json`
  relative to `mux/server`). Format matches Claude Desktop's:
  ```json
  {"mcpServers": {
    "github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "..."}},
    "docs":   {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer ..."}}
  }}
  ```
  An entry with neither `command` nor `url`, or with an invalid name, is logged and skipped. A missing
  file means no admin servers. Read once at startup.
- **`names.py`**: server names are `[a-z0-9_-]{1,32}`. Tool names offered to the model are
  `<server>__<tool>`, with characters outside `[A-Za-z0-9_-]` replaced by `_`, cut to 64 characters, and
  kept unique within the task (a numeric suffix on a clash).
- **`secrets.py`**: Fernet encryption of room-server header values with `MCP_ENCRYPTION_KEY`. If the key
  isn't set, adding or updating a room server that has headers is refused (400) instead of encrypting with
  a key that a restart would lose.
- **`urls.py`**: validates room-server URLs: `https` only; the host must not resolve to a loopback,
  private, link-local, or unspecified address (covers localhost, 10/8, 172.16/12, 192.168/16,
  169.254.169.254, `::1`, `fc00::/7`). `MCP_ALLOW_PRIVATE_URLS=true` lifts both rules for local
  development. Checked when the server is added or refreshed and again when connecting.
- **`client.py`**: `connect(server) -> session` and `list_tools(session)` over the `mcp` SDK, with a
  10 s connect timeout. One place that knows the SDK.
- **`toolset.py`**: `McpToolset`, described below.
- **`catalog.py`**: `McpCatalog.for_room(actor, admin_config)` combines the admin servers that room has
  switched on with the room's own servers and the per-tool settings.

### Room state and events

The room actor gains `mcp_servers: dict[str, RoomMcpServer]` (room servers) and
`mcp_admin_enabled: set[str]` plus per-tool settings for admin servers. Rebuilt from these events:

| Event | Fields | Sent to browsers as |
|---|---|---|
| `room_mcp_server_saved` | name, url, encrypted headers, tool list (name, description, input schema), per-tool settings | `mcp.changed` with name, url, header *names* only, tools and settings |
| `room_mcp_server_removed` | name | `mcp.changed` |
| `room_mcp_admin_toggled` | server name, enabled, per-tool settings | `mcp.changed` |

Header values never appear in a wire payload, an API response, or a log line. Per-tool settings are
`{tool_name: {"enabled": bool, "mode": "auto" | "ask"}}`; a tool missing from the map is enabled and `auto`.

### API (`mux/server/mux/api/mcp.py`, mounted under `/rooms/{id}/mcp`)

| Method and path | Who | What |
|---|---|---|
| `GET /rooms/{id}/mcp` | viewer | Admin servers (name, kind, enabled here, tools if loaded) and room servers (name, url, header names, tools, settings) |
| `POST /rooms/{id}/mcp/servers` | owner | Add a room server `{name, url, headers?}`: validates, connects, lists tools, saves. 400 on validation, 502 if it can't connect or list tools (nothing saved) |
| `POST /rooms/{id}/mcp/servers/{name}/refresh` | owner | Reconnect and replace the saved tool list (settings for tools that still exist are kept) |
| `PATCH /rooms/{id}/mcp/servers/{name}` | owner | Change headers and/or per-tool settings |
| `DELETE /rooms/{id}/mcp/servers/{name}` | owner | Remove |
| `PATCH /rooms/{id}/mcp/admin/{name}` | owner | Turn an admin server on/off for this room and set its per-tool settings |
| `POST /rooms/{id}/mcp/admin/{name}/refresh` | owner | Connect and cache the admin server's tool list (in memory, shared by all rooms) |

Limits: at most 10 room servers per room; a name can't be reused for a different server in the same room.

### `McpToolset` (one per coder task)

Built in `RoomRuntime._run` next to the existing `CoderToolExecutor` and wrapping it:

- `async __aenter__`: connects to every enabled server in turn (the SDK's connections must be opened and closed in the coder's own task). A server that fails is left out and
  the feed gets `mcp.unavailable` with the server name and the error. Tool lists come from the live
  session, filtered by the room's per-tool settings.
- `schemas()`: built-in schemas plus one OpenAI-style function schema per MCP tool (its `inputSchema` as
  `parameters`, its description prefixed with `[MCP: <server>]`).
- `execute(name, arguments)`: names with `__` that match an MCP tool go to that session's `call_tool`
  with a 60 s timeout; everything else goes to the wrapped executor. Results become
  `{"ok": not isError, "content": <text parts joined>}`, cut to 20,000 characters with a note when cut.
  Exceptions and timeouts become `{"ok": False, "error": ...}`.
- `ask` mode: before calling, awaits `ask_and_wait("The coder wants to use <tool>", ["Allow", "Deny"],
  default="Deny")` with the arguments in the card. Deny returns `{"ok": False, "error": "The room denied this tool call"}`.
- `async __aexit__`: closes every session (stdio processes are ended).

The `_Narrated` wrapper sits outside `McpToolset`, so MCP calls reach the feed with no extra code.

`RoomRuntime` gains `ask_and_wait(question, options, default, task_id) -> str`: it calls the existing
`_ask` and awaits an `asyncio.Future` that `_answered` resolves (`_default_answer` resolves it with the
default on expiry). The existing fire-and-forget `ask_room` flow is unchanged.

### Web UI

- A **Tools** button in the room's top bar opens an MCP panel (a dialog like Share).
- Everyone sees the list of servers and which tools are on.
- The owner also sees: a switch per admin server; **Add server** (name, https URL, optional header
  name + value, shown as a password field); **Refresh** and **Remove** per room server; and per tool an
  on/off switch and an `auto` / `ask first` selector.
- Errors from the API are shown in the dialog (e.g. "Could not connect: ...", "Private addresses aren't allowed").
- The feed shows `mcp.unavailable` notices like other agent notices.
- Types and API client calls added to `web/src/types/index.ts` and `web/src/lib/api.ts`; demo mode returns
  an empty MCP list.

### Settings and docs

- New server settings: `MCP_CONFIG_PATH`, `MCP_ENCRYPTION_KEY`, `MCP_ALLOW_PRIVATE_URLS` (in
  `config.py` and `.env.example`). `mcp.json` is git-ignored; an `mcp.example.json` is committed.
- New dependency: `mcp` (the official Python SDK) in `pyproject.toml`.
- `docs/03-getting-started.md` gains an "MCP tools" section: adding admin servers, adding room servers,
  approvals, and the security limits.

## Error handling summary

| Situation | Result |
|---|---|
| `mcp.json` missing | No admin servers |
| `mcp.json` entry invalid | That entry skipped, logged |
| Room server URL not https / private | 400, nothing saved |
| Headers given, no `MCP_ENCRYPTION_KEY` | 400, nothing saved |
| Can't connect or list tools when adding | 502 with the reason, nothing saved |
| Server down at task start | Its tools are left out of that task; `mcp.unavailable` in the feed |
| Tool call error or timeout | `{"ok": false, "error": ...}` to the coder; shown in the feed |
| `ask` tool, no answer before expiry | Treated as Deny |

## Testing

- **Toolset** (`tests/test_mcp_toolset.py`), against an in-process MCP server built with the SDK's
  `FastMCP` (in-memory transport): tool names and schemas, routing to MCP vs built-in, disabled tools
  hidden, `ask` + Allow, `ask` + Deny, `ask` + expiry, call timeout, a server that fails to connect, output
  truncation, sessions closed at the end.
- **Config and URLs** (`tests/test_mcp_config.py`): valid and invalid `mcp.json` entries; https-only and
  private-address refusal; the development override.
- **API** (`tests/test_api.py`): only the owner can change MCP settings; viewers can read them; header
  values never appear in API responses or the socket dump; refused without `MCP_ENCRYPTION_KEY` when
  headers are given; settings survive rehydration; the 10-server limit.
- **Web**: `tsc`, lint and build.

## Out of scope

- MCP tools for the coordinator.
- MCP resources and prompts (tools only).
- OAuth sign-in flows for remote MCP servers (a static header token only).
- Keeping MCP connections open between tasks.
- Room owners adding local (stdio) servers.
