"""Fake sandbox that returns recorded build and test results."""

import json
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from mux.sandbox.client import RunResult


class FakeSandbox:
    """`SandboxClient` that replays queued results, matched by longest command prefix."""

    def __init__(self, results: Mapping[str, Sequence[RunResult]]) -> None:
        self._queues = {prefix: deque(rs) for prefix, rs in results.items()}
        self.calls: list[dict[str, Any]] = []
        self._uuids = 0

    @classmethod
    def from_dir(cls, path: Path) -> "FakeSandbox":
        """Load `*.json` recordings: `{command, exit_code, output, duration_s}`."""
        results: dict[str, list[RunResult]] = {}
        for f in sorted(path.glob("*.json")):
            rec = json.loads(f.read_text())
            results.setdefault(rec["command"], []).append(
                RunResult(rec["exit_code"], rec["output"], None, rec["duration_s"])
            )
        return cls(results)

    async def run(
        self,
        *,
        image: str,
        files: Mapping[str, bytes],
        command: str,
        cwd: str,
        disposable: bool,
        timeout_s: int,
    ) -> RunResult:
        """Pop the next result for `command`; `snapshot_uuid` is set only for a passing kept run."""
        self.calls.append(
            {"image": image, "files": dict(files), "command": command, "cwd": cwd,
             "disposable": disposable, "timeout_s": timeout_s}
        )
        matches = [p for p in self._queues if command == p or command.startswith(p + " ")]
        if not matches:
            raise RuntimeError(f"FakeSandbox: no recording matches command {command!r}")
        queue = self._queues[max(matches, key=len)]
        if not queue:
            raise RuntimeError(f"FakeSandbox: recordings exhausted for command {command!r}")
        res = queue.popleft()
        if disposable or res.exit_code != 0:
            return replace(res, snapshot_uuid=None)
        self._uuids += 1
        return replace(res, snapshot_uuid=f"fake-{self._uuids}")
