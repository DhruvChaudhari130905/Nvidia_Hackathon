"""Binary room files stored as base64 data URLs."""

import base64

from mux.files.binary import data_url_bytes, file_bytes
from mux.integrations.github import _blob_body

PNG = b"\x89PNG\r\n\x1a\n\x00\x00binary"
PNG_URL = "data:image/png;base64," + base64.b64encode(PNG).decode()


def test_data_urls_decode_to_their_bytes():
    assert data_url_bytes(PNG_URL) == PNG
    assert file_bytes(PNG_URL.encode()) == PNG


def test_text_files_are_left_alone():
    for text in ["", "const a = 1;", "data: not a url", "data:image/png;base64,not base64!"]:
        assert data_url_bytes(text) is None
        assert file_bytes(text.encode()) == text.encode()


def test_github_blobs_carry_binary_files_as_base64():
    assert _blob_body("hello") == {"content": "hello", "encoding": "utf-8"}
    assert _blob_body(PNG_URL) == {"content": base64.b64encode(PNG).decode(), "encoding": "base64"}
