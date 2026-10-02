"""Tests for the coder tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mux.agents.coder.compaction import compact
from mux.agents.coder.context import CoderContext, RelevantFile, build_context
from mux.agents.coder.tools import TOOL_SCHEMAS, CoderToolExecutor
from mux.agents.coder.tools.files import FileTools
from mux.agents.coder.tools.plan import PlanTask, PlanTool
from mux.files.repo_map import format_repo_map, map_files
from mux.integrations.tavily import SearchResult, Source


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("const a = 1;\nconst b = 1;\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("", encoding="utf-8")
    return tmp_path


def executor(repo: Path, **kwargs) -> CoderToolExecutor:
    return CoderToolExecutor(FileTools(repo), build_root=str(repo), **kwargs)


# files

@pytest.mark.asyncio
async def test_list_files_accepts_the_path_from_the_schema(repo: Path):
    result = await executor(repo).execute("list_files", {"path": "."})
    assert result == {"ok": True, "files": ["src/App.tsx"]}  # node_modules skipped


@pytest.mark.asyncio
async def test_edit_needs_current_version_and_a_unique_match(repo: Path):
    tools = executor(repo)
    read = await tools.execute("read_file", {"path": "src/App.tsx"})

    stale = await tools.execute("edit_file", {"path": "src/App.tsx", "base_version": "old", "edits": []})
    assert stale["ok"] is False and stale["error"].startswith("stale")

    ambiguous = await tools.execute(
        "edit_file", {"path": "src/App.tsx", "base_version": read["version"], "edits": [{"find": "= 1", "replace": "= 2"}]},
    )
    assert ambiguous["ok"] is False and "2 places" in ambiguous["error"]
    assert (repo / "src" / "App.tsx").read_text(encoding="utf-8") == "const a = 1;\nconst b = 1;\n"

    ok = await tools.execute(
        "edit_file", {"path": "src/App.tsx", "base_version": read["version"], "edits": [{"find": "b = 1", "replace": "b = 2"}]},
    )
    assert ok["ok"] is True and "b = 2" in (repo / "src" / "App.tsx").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_paths_outside_the_repo_are_refused(repo: Path):
    result = await executor(repo).execute("read_file", {"path": "../secret.txt"})
    assert result["ok"] is False and "outside repository" in result["error"]


@pytest.mark.asyncio
async def test_write_file_refuses_to_overwrite(repo: Path):
    result = await executor(repo).execute("write_file", {"path": "src/App.tsx", "content": "x"})
    assert result["ok"] is False and "already exists" in result["error"]


# other tools

@pytest.mark.asyncio
async def test_unknown_tool_and_bad_arguments_return_errors(repo: Path):
    tools = executor(repo)
    assert (await tools.execute("rm_rf", {}))["error"] == "unknown tool: rm_rf"
    assert (await tools.execute("read_file", {"nope": 1}))["ok"] is False


class FakeSearch:
    async def search(self, query: str) -> SearchResult:
        return SearchResult(query, "Use Hono.", [Source("Hono docs", "https://hono.dev", "Fast.")])


@pytest.mark.asyncio
async def test_web_search_uses_the_shared_tavily_client(repo: Path):
    result = await executor(repo, search=FakeSearch()).execute("web_search", {"query": "hono routing"})
    assert result["answer"] == "Use Hono." and result["results"][0]["url"] == "https://hono.dev"
    assert (await executor(repo).execute("web_search", {"query": "x"}))["error"] == "web search is not configured"


@pytest.mark.asyncio
async def test_ask_room_sends_the_card_to_the_room(repo: Path):
    sent = []

    async def on_question(card):
        sent.append(card)

    tools = executor(repo, on_question=on_question)
    card = await tools.execute("ask_room", {"question": "Dark mode?", "options": ["yes", "no"], "default": "no"})
    assert card["ok"] is True and sent == [card]
    bad = await tools.execute("ask_room", {"question": "Q?", "options": ["yes"], "default": "yes"})
    assert bad["ok"] is False and len(sent) == 1


@pytest.mark.asyncio
async def test_update_plan_uses_the_room_plan(repo: Path):
    plan = PlanTool([PlanTask("t2", "Admin list")])
    result = await executor(repo, plan=plan).execute("update_plan", {"task_id": "t2", "split": ["Table", "Filters"]})
    assert [t["id"] for t in result["tasks"]] == ["t2.1", "t2.2"]
    assert (await executor(repo).execute("update_plan", {"task_id": "t2", "status": "done"}))["error"] == "plan is not available"


def test_schemas_are_valid_for_the_api():
    names = [schema["function"]["name"] for schema in TOOL_SCHEMAS]
    assert len(names) == len(set(names)) == 11
    json.dumps(TOOL_SCHEMAS)


# compaction

def test_compaction_keeps_the_latest_turn_and_shrinks_old_arguments():
    big = "x" * 500
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "w1", "type": "function", "function": {"name": "write_file", "arguments": json.dumps({"path": "a.ts", "content": big})}},
        ]},
        {"role": "tool", "tool_call_id": "w1", "content": big},
        {"role": "assistant", "content": "", "tool_calls": []},
        {"role": "tool", "tool_call_id": "r1", "content": big},
        {"role": "tool", "tool_call_id": "r2", "content": big},
    ]
    out = compact(messages)
    assert out[1]["content"].startswith("[previous tool result]")
    assert json.loads(out[0]["tool_calls"][0]["function"]["arguments"]) == {"path": "a.ts", "content": "[500 characters omitted]"}
    assert out[3]["content"] == big and out[4]["content"] == big
    assert messages[1]["content"] == big  # input is not changed


# context and repo map

def test_context_puts_stable_prefix_first_and_marks_clipped_files():
    messages = build_context(CoderContext(
        system_prompt="SYSTEM", conventions="Use Hono.", room_log="App: RSVP", current_task="Build form",
        relevant_files=[RelevantFile("b.ts", "1\n2\n3"), RelevantFile("a.ts", "x")],
        task_files=["b.ts"], max_lines=2,
    ))
    assert messages[0] == {"role": "system", "content": "SYSTEM\n\nCONVENTIONS.md\nUse Hono."}
    files = [m["content"] for m in messages if m["content"].startswith("FILE:")]
    assert files == ["FILE: b.ts\n```text\n1\n2\n... (1 more lines; use read_file for the rest)\n```"]


def test_repo_map_from_manifest_contents():
    entries = map_files({
        "client/src/App.tsx": "export default function App() {}\nconst API_URL = '/api';\n",
        "server/src/index.ts": "app.get('/api/rsvps', handler)\n",
        "node_modules/x/index.js": "export const y = 1;",
    })
    text = format_repo_map(entries)
    assert text == "client/src/App.tsx | exports: App | components: App\nserver/src/index.ts | routes: GET /api/rsvps"
