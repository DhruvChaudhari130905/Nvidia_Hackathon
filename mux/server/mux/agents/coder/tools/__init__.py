"""Tool registry and the tool schemas sent to the model."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable

from mux.integrations.tavily import WebSearch

from mux.sandbox.runner import Runner

from .ask import ask_room
from .build import run_build, run_tests
from .files import ActorFileTools, FileTools, RoomFileTools
from .finish import finish_task
from .plan import PlanTool, update_plan
from .search import web_search

QuestionCallback = Callable[[dict[str, Any]], Awaitable[Any] | Any]
_CHANGES_FILES = {"write_file", "edit_file", "delete_file"}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file or a line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": ["integer", "null"]},
                    "end_line": {"type": ["integer", "null"]},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files under a directory, relative to the repository root. Use \".\" for all files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file. Fails if the file exists; use edit_file instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit an existing file. base_version is the version number from read_file. Each find must match exactly one place.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "base_version": {"type": "integer"},
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "find": {"type": "string"},
                                "replace": {"type": "string"},
                            },
                            "required": ["find", "replace"],
                        },
                    },
                },
                "required": ["path", "base_version", "edits"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file using its version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "base_version": {"type": "integer"},
                },
                "required": ["path", "base_version"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_build",
            "description": "Run the project build.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run relevant tests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": ["string", "null"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_room",
            "description": "Ask the room a question with options.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "default": {"type": "string"},
                },
                "required": ["question", "options", "default"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_plan",
            "description": "Update or split the current plan task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "status": {"type": ["string", "null"], "enum": ["todo", "doing", "done", None]},
                    "split": {"type": ["array", "null"], "items": {"type": "string"}},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "Mark the current task complete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                },
                "required": ["summary"],
            },
        },
    },
]


class CoderToolExecutor:
    """Dispatch model tool calls to coder tools. Tool errors come back as {"ok": False, "error": ...}.

    Production passes `RoomFileTools` and a sandbox `runner`: builds and tests then run in the Nebius
    sandbox on the room's live manifest (Q51). Local npm runs only when `build_root` is given explicitly,
    for development on a laptop; with neither, run_build and run_tests return an error.
    """

    def __init__(
        self,
        files: FileTools | RoomFileTools | ActorFileTools,
        *,
        runner: Runner | None = None,
        build_root: str | None = None,
        search: WebSearch | None = None,
        plan: PlanTool | None = None,
        on_question: QuestionCallback | None = None,
    ) -> None:
        if runner is not None and not isinstance(files, RoomFileTools):
            raise TypeError("a sandbox runner builds the room's files, so it needs RoomFileTools")
        self.files = files
        self.runner = runner
        self.build_root = build_root
        self.search = search
        self.plan = plan
        self.on_question = on_question
        # Snapshot of the last passing sandbox build, cleared by any file change so it always matches the
        # current files. The checkpoint writer reads it (§10).
        self.snapshot_uuid: str | None = None

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        handlers: dict[str, Callable[..., Any]] = {
            "read_file": self.files.read_file,
            "list_files": self.files.list_files,
            "write_file": self.files.write_file,
            "edit_file": self.files.edit_file,
            "delete_file": self.files.delete_file,
            "run_build": self._run_build,
            "run_tests": self._run_tests,
            "web_search": lambda query: web_search(self.search, query),
            "ask_room": self._ask_room,
            "update_plan": lambda **kwargs: update_plan(**kwargs, plan=self.plan),
            "finish_task": finish_task,
        }
        handler = handlers.get(name)
        if handler is None:
            return {"ok": False, "error": f"unknown tool: {name}"}
        try:
            result = handler(**arguments)
            result = await result if inspect.isawaitable(result) else result
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if name in _CHANGES_FILES and isinstance(result, dict) and result.get("ok"):
            self.snapshot_uuid = None
        return result

    async def _run_build(self) -> dict[str, Any]:
        if self.runner is not None:
            assert isinstance(self.files, RoomFileTools)
            res = await self.runner.build(self.files.files.manifest)
            self.snapshot_uuid = res.snapshot_uuid
            return {"ok": res.passed, "passed": res.passed, "operation": "build", "errors": res.errors,
                    "duration_s": res.duration_s}
        if self.build_root is None:
            return {"ok": False, "passed": False, "operation": "build", "errors": ["builds are not configured"]}
        # builds block for minutes, so they run in a thread instead of stalling every room
        return await asyncio.to_thread(run_build, self.build_root)

    async def _run_tests(self, pattern: str | None = None) -> dict[str, Any]:
        if self.runner is not None:
            assert isinstance(self.files, RoomFileTools)
            res = await self.runner.test(self.files.files.manifest, pattern)
            return {"ok": res.passed, "passed": res.passed, "operation": "tests", "errors": res.failures,
                    "passed_count": res.passed_count, "failed_count": res.failed_count}
        if self.build_root is None:
            return {"ok": False, "passed": False, "operation": "tests", "errors": ["tests are not configured"]}
        return await asyncio.to_thread(run_tests, self.build_root, pattern)

    async def _ask_room(self, **arguments: Any) -> dict[str, Any]:
        card = ask_room(**arguments)
        if card["ok"] and self.on_question is not None:
            sent = self.on_question(card)
            if inspect.isawaitable(sent):
                await sent
        return card
