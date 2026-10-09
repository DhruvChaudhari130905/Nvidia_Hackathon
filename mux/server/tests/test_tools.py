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
async def test_edit_accepts_edits_sent_as_a_json_string(repo: Path):
    """Nemotron sometimes JSON-encodes the edits array; a bare string used to crash with 'str' has no .get."""
    tools = executor(repo)
    read = await tools.execute("read_file", {"path": "src/App.tsx"})
    ok = await tools.execute(
        "edit_file",
        {"path": "src/App.tsx", "base_version": read["version"], "edits": json.dumps([{"find": "a = 1", "replace": "a = 3"}])},
    )
    assert ok["ok"] is True and "a = 3" in (repo / "src" / "App.tsx").read_text(encoding="utf-8")

    bad = await tools.execute("edit_file", {"path": "src/App.tsx", "base_version": ok["version"], "edits": "not json"})
    assert bad["ok"] is False and "list of" in bad["error"]


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
    assert len(names) == len(set(names)) == 12
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


# images

def openverse(results: list[dict], images: dict[str, tuple[int, str, bytes]]):
    """An httpx transport answering the Openverse search and serving `images` by URL."""
    import httpx

    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen.append(url)
        if url.startswith("https://api.openverse.org/v1/images/?"):
            return httpx.Response(200, json={"results": results})
        if url in images:
            status, mime, body = images[url]
            return httpx.Response(status, headers={"content-type": mime}, content=body)
        return httpx.Response(404)

    return httpx.MockTransport(handle), seen


def hit(i: str, url: str) -> dict:
    return {"id": i, "url": url, "thumbnail": f"https://api.openverse.org/v1/images/{i}/thumb/", "title": f"Necklace {i}",
            "creator": "Ann", "license": "by", "foreign_landing_url": f"https://flickr.com/{i}", "width": 1024, "height": 768}


@pytest.mark.asyncio
async def test_add_image_saves_a_real_photo_into_the_project(repo: Path):
    import base64
    import httpx

    transport, seen = openverse([hit("a", "https://img.example/a.jpg")], {"https://img.example/a.jpg": (200, "image/jpeg", b"JPEG")})
    async with httpx.AsyncClient(transport=transport) as client:
        result = await executor(repo, http=client).execute("add_image", {"query": "gold necklace", "path": "images/necklace.jpg"})

    assert result["ok"] and result["path"] == "images/necklace.jpg"
    assert result["credit"] == "Necklace a by Ann (CC BY), https://flickr.com/a"
    assert (repo / "images" / "necklace.jpg").read_text() == "data:image/jpeg;base64," + base64.b64encode(b"JPEG").decode()
    assert "q=gold+necklace" in seen[0]


@pytest.mark.asyncio
async def test_add_image_falls_back_to_the_thumbnail_and_fixes_the_extension(repo: Path):
    import httpx

    big = b"x" * 2_000_001
    transport, _ = openverse(
        [hit("a", "https://img.example/a.png"), hit("b", "https://img.example/b.png")],
        {
            "https://img.example/a.png": (200, "image/png", big),  # over the room's 2 MB cap
            "https://api.openverse.org/v1/images/a/thumb/": (200, "image/jpeg", b"THUMB"),
        },
    )
    async with httpx.AsyncClient(transport=transport) as client:
        tools = executor(repo, http=client)
        first = await tools.execute("add_image", {"query": "ring", "path": "ring.png"})
        # The same photo isn't used twice in one task; b has no downloadable file, so nothing is left
        second = await tools.execute("add_image", {"query": "ring", "path": "ring2.png"})

    assert first["ok"] and first["path"] == "ring.jpg"  # it's a JPEG, so the path says so
    assert (repo / "ring.jpg").read_text().startswith("data:image/jpeg;base64,")
    assert second == {"ok": False, "error": "no usable photo found for: ring"}


@pytest.mark.asyncio
async def test_add_image_needs_an_image_path(repo: Path):
    result = await executor(repo).execute("add_image", {"query": "ring", "path": "ring.txt"})
    assert result == {"ok": False, "error": "path must end in .jpg, .jpeg, .png or .webp"}


# finishing a task with pictures left undone

@pytest.mark.asyncio
async def test_finish_is_refused_while_pages_still_use_placeholder_images(repo: Path):
    tools = executor(repo)
    await tools.execute("write_file", {"path": "index.html", "content": '<img src="https://via.placeholder.com/300?text=Ring">\n'})

    refused = await tools.execute("finish_task", {"summary": "done"})
    assert refused["ok"] is False
    assert "index.html" in refused["error"] and "via.placeholder.com" in refused["error"]

    (repo / "index.html").write_text('<img src="images/ring.jpg">\n', encoding="utf-8")
    assert (await tools.execute("finish_task", {"summary": "done"}))["ok"] is True


@pytest.mark.asyncio
async def test_finish_is_refused_while_an_added_photo_is_unused(repo: Path):
    import httpx

    transport, _ = openverse([hit("a", "https://img.example/a.jpg")], {"https://img.example/a.jpg": (200, "image/jpeg", b"JPEG")})
    async with httpx.AsyncClient(transport=transport) as client:
        tools = executor(repo, http=client)
        await tools.execute("add_image", {"query": "pearl bracelet", "path": "images/pearl-bracelet.jpg"})
        refused = await tools.execute("finish_task", {"summary": "Added a photo"})
        assert refused["ok"] is False and "images/pearl-bracelet.jpg" in refused["error"]

        (repo / "index.html").write_text('<img src="/images/pearl-bracelet.jpg">\n', encoding="utf-8")
        assert (await tools.execute("finish_task", {"summary": "Added a photo"}))["ok"] is True


@pytest.mark.asyncio
async def test_finish_gives_up_refusing_after_two_tries(repo: Path):
    tools = executor(repo)
    await tools.execute("write_file", {"path": "index.html", "content": '<img src="https://placehold.co/300">\n'})
    assert (await tools.execute("finish_task", {"summary": "done"}))["ok"] is False
    assert (await tools.execute("finish_task", {"summary": "done"}))["ok"] is False
    assert (await tools.execute("finish_task", {"summary": "done"}))["ok"] is True  # never loops forever


@pytest.mark.asyncio
async def test_an_unrelated_task_is_not_held_up_by_old_placeholders(repo: Path):
    (repo / "index.html").write_text('<img src="https://via.placeholder.com/300">\n', encoding="utf-8")
    (repo / "README.md").write_text("Images: https://placehold.co/600\n", encoding="utf-8")
    assert (await executor(repo).execute("finish_task", {"summary": "Bigger font"}))["ok"] is True


# checking the code the coder writes (there's no build in most rooms)

BROKEN_APP = """import React from 'react';
import './index.css';

const products = [
  { id: 3, name: 'Diamond Bracelet', image: '/images/gold-necklace.jpg' }
  { id: 4, name: 'Pearl Earrings', image: '/images/gold-necklace.jpg' },
];

export default function App() {
  return <div>{products.map(p => <img key={p.id} src={p.image} />)}</div>;
}
"""


@pytest.mark.asyncio
async def test_writing_broken_code_reports_the_syntax_error_and_missing_import(repo: Path):
    result = await executor(repo).execute("write_file", {"path": "src/Shop.jsx", "content": BROKEN_APP})
    assert result["ok"] is True  # the file is saved; the problems come back so the coder fixes them
    problems = " | ".join(result["problems"])
    assert "src/Shop.jsx:5" in problems and "','" in problems
    assert "./index.css" in problems


@pytest.mark.asyncio
async def test_valid_code_and_existing_imports_report_nothing(repo: Path):
    (repo / "src" / "index.css").write_text("body {}\n", encoding="utf-8")
    (repo / "src" / "Card.tsx").write_text("export const Card = () => null;\n", encoding="utf-8")
    code = "import './index.css';\nimport { Card } from './Card';\nconst a: number[] = [1,\n 2];\nexport const App = () => <Card />;\n"
    result = await executor(repo).execute("write_file", {"path": "src/Main.tsx", "content": code})
    assert result["ok"] is True and "problems" not in result


@pytest.mark.asyncio
async def test_finish_is_refused_while_any_code_file_is_broken(repo: Path):
    (repo / "src" / "App.jsx").write_text(BROKEN_APP, encoding="utf-8")  # broken before this task started
    tools = executor(repo)
    refused = await tools.execute("finish_task", {"summary": "Changed the ring image"})
    assert refused["ok"] is False and "src/App.jsx:5" in refused["error"]

    (repo / "src" / "App.jsx").write_text(BROKEN_APP.replace("jpg' }\n", "jpg' },\n", 1).replace("import './index.css';\n", ""), encoding="utf-8")
    assert (await tools.execute("finish_task", {"summary": "Fixed it"}))["ok"] is True


@pytest.mark.asyncio
async def test_code_checks_are_skipped_without_the_parser(repo: Path, monkeypatch):
    from mux.agents.coder.tools import codecheck

    monkeypatch.setattr(codecheck, "_parsers", lambda: None)
    result = await executor(repo).execute("write_file", {"path": "src/Shop.jsx", "content": BROKEN_APP})
    assert result["ok"] is True and all("','" not in p for p in result.get("problems", []))


def test_code_check_accepts_a_bare_ampersand_in_jsx_text_and_points_at_the_first_error():
    from mux.agents.coder.tools.codecheck import syntax_errors

    footer = "export const F = () => <p>&copy; 2026 Built with React, TypeScript & Tailwind CSS.</p>;\n"
    assert syntax_errors("src/Footer.tsx", footer) == []
    # An unclosed brace near the end: the error is reported where it is, not at line 1
    broken = "import React from 'react';\n\nexport const A = () => {\n  return (\n    <div>\n      {[1].map(i => (\n        <p>{i}</p>\n      )}\n    </div>\n  );\n};\n"
    (error,) = syntax_errors("src/A.tsx", broken)
    assert not error.startswith("src/A.tsx:1:")


def _read(call_id: str, path: str, body: str) -> list[dict]:
    return [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"path": path})}}]},
        {"role": "tool", "tool_call_id": call_id, "content": json.dumps({"path": path, "content": body, "version": 1})},
    ]


def _edit(call_id: str, path: str) -> list[dict]:
    return [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": "edit_file", "arguments": json.dumps({"path": path, "base_version": 1, "edits": []})}}]},
        {"role": "tool", "tool_call_id": call_id, "content": json.dumps({"ok": True, "path": path, "version": 2})},
    ]


def test_compaction_keeps_the_latest_read_of_each_file():
    a, b = "A" * 500, "B" * 500
    messages = [*_read("r1", "a.ts", a), *_read("r2", "b.ts", b), *_read("r3", "a.ts", a),
                {"role": "assistant", "content": "", "tool_calls": []}]
    out = compact(messages)
    assert out[1]["content"].startswith("[earlier read of a.ts")  # a newer read of a.ts is below
    assert json.loads(out[3]["content"])["content"] == b
    assert json.loads(out[5]["content"])["content"] == a


def test_compaction_drops_reads_of_files_that_changed_since():
    messages = [*_read("r1", "a.ts", "A" * 500), *_edit("e1", "a.ts"), {"role": "assistant", "content": "", "tool_calls": []}]
    out = compact(messages)
    assert out[1]["content"].startswith("[earlier read of a.ts") and "changed" in out[1]["content"]


def test_compaction_keeps_reads_within_a_budget(monkeypatch):
    import mux.agents.coder.compaction as compaction
    monkeypatch.setattr(compaction, "KEPT_READS_BUDGET", 1500)
    messages = [*_read("r1", "a.ts", "A" * 1000), *_read("r2", "b.ts", "B" * 1000),
                {"role": "assistant", "content": "", "tool_calls": []}]
    out = compact(messages)
    assert out[1]["content"].startswith("[earlier read of a.ts")  # the oldest goes first
    assert json.loads(out[3]["content"])["content"] == "B" * 1000
