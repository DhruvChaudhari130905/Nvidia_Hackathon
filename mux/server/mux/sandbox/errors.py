"""Dedupes and caps the error lines that the sandbox's report script prints.

Parsing happens inside the sandbox (`infra/sandbox-image/mux-report.mjs`), before the 8 KB output cut,
and the script prints `file:line: message` lines. This module only dedupes and caps them (R7).
"""

import re

MAX_ERRORS = 5
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# `file:line: message`. The file has no colon or leading space, the line is digits, the message is non-blank.
LINE_RE = re.compile(r"^(?P<file>[^\s:][^:]*):(?P<line>\d+): (?P<message>.*\S.*)$")


def normalize_message(m: str) -> str:
    """Strip colour codes, collapse whitespace, lowercase: the dedupe form of a message."""
    return " ".join(_ANSI_RE.sub("", m).split()).lower()


def dedupe(output: str) -> list[str]:
    """The first five distinct `file:line: message` lines, keyed on (file, line, normalized message).

    Other lines (summaries, noise, a line cut off by truncation) are skipped.
    """
    seen: set[tuple[str, int, str]] = set()
    out: list[str] = []
    for raw in output.splitlines():
        m = LINE_RE.match(_ANSI_RE.sub("", raw).strip())
        if not m:
            continue
        file, line, msg = m["file"], int(m["line"]), " ".join(m["message"].split())
        key = (file, line, normalize_message(msg))
        if key in seen:
            continue
        seen.add(key)
        out.append(f"{file}:{line}: {msg}")
        if len(out) == MAX_ERRORS:
            break
    return out


def fallback(raw: str) -> list[str]:
    """Last five non-empty lines of raw output, for when the script printed nothing parseable."""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return lines[-MAX_ERRORS:]
