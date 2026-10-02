"""run_build and run_tests for local development only.

These run npm on the machine that calls them. The coder writes the code being built, so
production must call P-DB's sandbox runner (mux/sandbox/runner.py) instead; never run this on
the backend server. Error parsing belongs in mux/sandbox/errors.py once P-DB builds it.

Returns at most 5 deduplicated errors as file:line: message.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Sequence


_MAX_ERRORS = 5

_ERROR_PATTERNS = (
    re.compile(
        r"(?P<file>[^\s:()]+):(?P<line>\d+)"
        r"(?::\d+)?\s*[:|-]\s*(?P<message>.+)"
    ),
    re.compile(
        r"(?P<file>[^\s:()]+)\((?P<line>\d+)"
        r"(?:,\d+)?\)\s*[:|-]\s*(?P<message>.+)"
    ),
)


def run_build(
    root: str | Path = ".",
    command: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run the project's build command."""
    return _run(
        root=root,
        command=command or ("npm", "run", "build"),
        operation="build",
    )


def run_tests(
    root: str | Path = ".",
    pattern: str | None = None,
    command: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run the project's tests."""
    if command is None:
        command = ("npm", "test")

        if pattern:
            command = (*command, "--", pattern)

    return _run(
        root=root,
        command=command,
        operation="tests",
    )


def _run(
    *,
    root: str | Path,
    command: Sequence[str],
    operation: str,
) -> dict[str, Any]:
    """Execute one validation command and normalize its output."""
    cwd = Path(root).resolve()

    if not cwd.is_dir():
        return {
            "ok": False,
            "passed": False,
            "operation": operation,
            "errors": [
                f"{cwd}:1: repository directory not found"
            ],
        }

    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
    except FileNotFoundError:
        executable = command[0] if command else "command"

        return {
            "ok": False,
            "passed": False,
            "operation": operation,
            "errors": [
                f"{executable}:1: command not found"
            ],
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "passed": False,
            "operation": operation,
            "errors": [
                f"{command[0]}:1: command timed out"
            ],
        }
    except OSError as exc:
        return {
            "ok": False,
            "passed": False,
            "operation": operation,
            "errors": [
                f"{command[0]}:1: {exc}"
            ],
        }

    output = "\n".join(
        part
        for part in (
            completed.stdout,
            completed.stderr,
        )
        if part
    )

    passed = completed.returncode == 0

    result: dict[str, Any] = {
        "ok": passed,
        "passed": passed,
        "operation": operation,
        "exit_code": completed.returncode,
    }

    if not passed:
        result["errors"] = _extract_errors(output)

        if not result["errors"]:
            result["errors"] = [
                f"{command[0]}:1: command failed with exit code "
                f"{completed.returncode}"
            ]

    return result


def _extract_errors(output: str) -> list[str]:
    """Extract at most five unique file:line:message errors."""
    errors: list[str] = []
    seen: set[str] = set()

    for raw_line in output.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        normalized = _parse_error(line)

        if normalized is None:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        errors.append(normalized)

        if len(errors) >= _MAX_ERRORS:
            break

    return errors


def _parse_error(line: str) -> str | None:
    """Convert common compiler/test errors to file:line: message."""
    for pattern in _ERROR_PATTERNS:
        match = pattern.search(line)

        if match:
            file_name = match.group("file")
            line_number = match.group("line")
            message = " ".join(
                match.group("message").split()
            )

            return f"{file_name}:{line_number}: {message}"

    return None
