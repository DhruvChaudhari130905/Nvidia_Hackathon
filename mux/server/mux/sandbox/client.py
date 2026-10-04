"""Thin wrapper around the Token Factory Sandboxes Python SDK (`contree-sdk`)."""

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

OUTPUT_LIMIT = 8192  # bytes; the server cuts output at 8 KB anyway


@dataclass
class RunResult:
    """Outcome of one sandbox command."""

    exit_code: int
    output: str
    snapshot_uuid: str | None
    duration_s: float


class SandboxError(Exception):
    """The sandbox could not run the command (timeout, failed or cancelled operation, API error)."""


def _text(stream: object) -> str:
    """SDK output as text: str as is, bytes decoded, anything else (None, IO objects) empty."""
    if isinstance(stream, str):
        return stream
    if isinstance(stream, bytes):
        return stream.decode("utf-8", errors="replace")
    return ""


def join_output(stdout: object, stderr: object) -> str:
    """stdout then stderr, with a newline between so a last stdout line (the report) stays whole."""
    out, err = _text(stdout), _text(stderr)
    if out and err and not out.endswith("\n"):
        out += "\n"
    return out + err


@runtime_checkable
class SandboxClient(Protocol):
    """What the runner needs from a sandbox; `FakeSandbox` satisfies it too."""

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
        """Run `command` in a fresh container from `image` with `files` (absolute path -> bytes) uploaded."""
        ...


class TokenFactorySandboxClient:
    """`SandboxClient` backed by the Token Factory Sandboxes SDK."""

    def __init__(self, api_key: str, base_url: str) -> None:
        # Imported here so the package imports (and fakes work) without the SDK installed.
        # contree-sdk 0.3.x takes the token and base URL directly; the docs' ContreeAsyncClient
        # wrapper (contree_client.httpx) is not shipped with it.
        from contree_sdk import Contree

        self._sdk = Contree(base_url=base_url, token=api_key)

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
        """Run via `image.run(shell=...)`; the snapshot UUID is only returned when not disposable."""
        from contree_sdk.sdk.exceptions.base import ContreeError

        start = time.monotonic()
        try:
            img = await self._sdk.images.use(image)
            # Bytes, decoded by `_text` with replacement: output cut at 8 KB can end mid-character,
            # and asking the SDK for `str` would make it raise UnicodeDecodeError.
            res = await img.run(
                shell=command,
                files=dict(files),
                cwd=cwd,
                timeout=timeout_s,
                disposable=disposable,
                truncate_output_at=OUTPUT_LIMIT,
                stdout=bytes,
                stderr=bytes,
            )
        except (ContreeError, RuntimeError) as e:  # the SDK also raises bare RuntimeErrors on bad responses
            raise SandboxError(str(e) or type(e).__name__) from e
        return RunResult(
            exit_code=res.exit_code,
            output=join_output(res.stdout, res.stderr),
            snapshot_uuid=None if disposable or res.uuid is None else str(res.uuid),
            duration_s=time.monotonic() - start,
        )
