"""Binary room files (images, fonts, media) are stored as base64 data URLs, `data:<mime>;base64,<bytes>`.

The web app creates them on import/upload so they travel through the text-based files API, events and
checkpoints unchanged. Anything that needs the real file (a GitHub push, a sandbox build) decodes them here.
"""

import base64
import binascii
import re

_DATA_URL = re.compile(r"data:[\w.+-]+/[\w.+-]+;base64,([A-Za-z0-9+/]*={0,2})")


def data_url_bytes(content: str) -> bytes | None:
    """The bytes of a binary file stored as a data URL, or None for ordinary text."""
    if not content.startswith("data:") or not (m := _DATA_URL.fullmatch(content)):
        return None
    try:
        return base64.b64decode(m.group(1), validate=True)
    except binascii.Error:
        return None


def file_bytes(data: bytes) -> bytes:
    """What a room file's stored bytes are on disk: data URLs decoded, everything else unchanged."""
    if not data.startswith(b"data:"):
        return data
    try:
        decoded = data_url_bytes(data.decode("ascii"))
    except UnicodeDecodeError:
        return data
    return data if decoded is None else decoded
