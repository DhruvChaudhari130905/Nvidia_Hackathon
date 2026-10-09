"""Tool registry and the tool schemas sent to the model."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable

import httpx

from mux.integrations.tavily import WebSearch

from mux.sandbox.runner import Runner

from .ask import ask_room
from .codecheck import is_code, project_problems
from .build import run_build, run_tests
from .files import ActorFileTools, FileTools, RoomFileTools
from .finish import finish_task
from .images import add_image, picture_problems
from .plan import PlanTool, update_plan
from .search import web_search

QuestionCallback = Callable[[dict[str, Any]], Awaitable[Any] | Any]
_CHANGES_FILES = {"write_file", "edit_file", "delete_file", "add_image"}
READ_ONLY_TOOLS = {"read_file", "list_files", "web_search", "finish_task"}


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
            "name": "add_image",
            "description": (
                "Save a real, openly licensed photo matching the query into the project at path "
                "(.jpg/.png/.webp) and return the saved path and a credit line. Reference the image by "
                "that path. Use this for every picture, one call per distinct picture; never use placeholder "
                "images or invented image URLs. In a Vite/React project save under public/ (e.g. "
                "public/images/ring.jpg) and reference it from code as /images/ring.jpg."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What the photo shows, e.g. 'gold necklace'"},
                    "path": {"type": "string", "description": "Where to save it, e.g. 'public/images/necklace.jpg'"},
                },
                "required": ["query", "path"],
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
        http: httpx.AsyncClient | None = None,
        read_only: bool = False,
    ) -> None:
        if runner is not None and not isinstance(files, RoomFileTools):
            raise TypeError("a sandbox runner builds the room's files, so it needs RoomFileTools")
        self.files = files
        self.runner = runner
        self.build_root = build_root
        self.search = search
        self.plan = plan
        self.on_question = on_question
        self.http = http
        self.read_only = read_only  # a review: reading tools only, and finish_task keeps the review as written
        self._images_used: set[str] = set()  # photos already added during this task
        self._images_added: list[str] = []  # where they were saved
        self._created: set[str] = set()  # files this task created with write_file
        self._finish_refusals = 0
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
            "add_image": self._add_image,
            "ask_room": self._ask_room,
            "update_plan": lambda **kwargs: update_plan(**kwargs, plan=self.plan),
            "finish_task": self._finish_task,
        }
        if self.read_only and name not in READ_ONLY_TOOLS:
            return {"ok": False, "error": f"{name} isn't available in a review: only read, then finish_task with the review"}
        if self.read_only and name == "finish_task":
            review = str(arguments.get("summary") or "").strip()
            return {"ok": True, "summary": review[:6000]} if review else {"ok": False, "error": "summary is required"}
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
            if name == "write_file":
                self._created.add(str(result.get("path", "")))
            # No build runs in most rooms: report syntax errors and missing imports right away instead
            path = str(result.get("path", ""))
            if name in ("write_file", "edit_file") and is_code(path):
                problems = await project_problems(self.files, only=[path])
                if problems:
                    result = {**result, "problems": problems, "note": "Saved, but fix these problems before finishing."}
        return result

    @property
    def can_build(self) -> bool:
        """Whether run_build / run_tests can do anything (a sandbox runner or a local build root)."""
        return self.runner is not None or self.build_root is not None

    def schemas(self) -> list[dict[str, Any]]:
        """The tool schemas to offer the model: the build tools only when builds can run."""
        if self.read_only:
            return [s for s in TOOL_SCHEMAS if s["function"]["name"] in READ_ONLY_TOOLS]
        if self.can_build:
            return TOOL_SCHEMAS
        return [s for s in TOOL_SCHEMAS if s["function"]["name"] not in ("run_build", "run_tests")]

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

    async def _add_image(self, query: str, path: str) -> dict[str, Any]:
        if self.http is not None:
            return await add_image(self.files, self.http, self._images_used, query, path, self._images_added)
        async with httpx.AsyncClient() as client:
            return await add_image(self.files, client, self._images_used, query, path, self._images_added)

    # Refused twice at most, so a model that can't fix it still ends (the turn limit is the other backstop)
    MAX_FINISH_REFUSALS = 2

    async def _finish_task(self, summary: str) -> dict[str, Any]:
        result = finish_task(summary)
        if not result["ok"] or self._finish_refusals >= self.MAX_FINISH_REFUSALS:
            return result
        # A broken file anywhere stops the whole app, so code problems count even in files this task didn't touch
        code = await project_problems(self.files)
        pictures = await picture_problems(self.files, self._images_added, self._created)
        if not code and not pictures:
            return result
        self._finish_refusals += 1
        advice = []
        if code:
            advice.append("Fix the code problems (re-read each file first)")
        if pictures:
            advice.append("replace every placeholder with add_image and use each added photo")
        return {"ok": False, "error": "Not finished yet: " + "; ".join(code + pictures) + ". " + ", and ".join(advice) + ", then finish."}

    async def _ask_room(self, **arguments: Any) -> dict[str, Any]:
        card = ask_room(**arguments)
        if card["ok"] and self.on_question is not None:
            sent = self.on_question(card)
            if inspect.isawaitable(sent):
                await sent
        return card
