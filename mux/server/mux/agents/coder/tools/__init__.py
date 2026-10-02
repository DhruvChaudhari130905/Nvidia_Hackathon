"""Tool registry and the tool schemas sent to the model."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable

from mux.integrations.tavily import WebSearch

from .ask import ask_room
from .build import run_build, run_tests
from .files import FileTools
from .finish import finish_task
from .plan import PlanTool, update_plan
from .search import web_search

QuestionCallback = Callable[[dict[str, Any]], Awaitable[Any] | Any]


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
            "description": "Edit an existing file. base_version comes from read_file. Each find must match exactly one place.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "base_version": {"type": "string"},
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
                    "base_version": {"type": "string"},
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
    """Dispatch model tool calls to coder tools. Tool errors come back as {"ok": False, "error": ...}."""

    def __init__(
        self,
        files: FileTools,
        *,
        build_root: str = ".",
        search: WebSearch | None = None,
        plan: PlanTool | None = None,
        on_question: QuestionCallback | None = None,
    ) -> None:
        self.files = files
        self.build_root = build_root
        self.search = search
        self.plan = plan
        self.on_question = on_question

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        handlers: dict[str, Callable[..., Any]] = {
            "read_file": self.files.read_file,
            "list_files": self.files.list_files,
            "write_file": self.files.write_file,
            "edit_file": self.files.edit_file,
            "delete_file": self.files.delete_file,
            # builds and tests block for minutes, so they run in a thread instead of stalling every room
            "run_build": lambda: asyncio.to_thread(run_build, self.build_root),
            "run_tests": lambda pattern=None: asyncio.to_thread(run_tests, self.build_root, pattern),
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
            return await result if inspect.isawaitable(result) else result
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def _ask_room(self, **arguments: Any) -> dict[str, Any]:
        card = ask_room(**arguments)
        if card["ok"] and self.on_question is not None:
            sent = self.on_question(card)
            if inspect.isawaitable(sent):
                await sent
        return card
