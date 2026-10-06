"""The event contract: every emitted event type has a payload model, and the exported schema is current."""

import re
from pathlib import Path

from scripts.export_schema import OUT, render

from mux.events.models import EVENT_PAYLOADS

MUX = Path(__file__).resolve().parents[1] / "mux"
# an event type as the first argument of emit/broadcast/log_event/reserve, or of a (type, payload) change tuple
EMITTED = re.compile(r'(?:emit|broadcast|log_event|reserve)\(\s*"([a-z_]+\.[a-z_.]+)"|(?<![\w.])\("([a-z_]+\.[a-z_.]+)",\s*\w')


def test_the_exported_schema_is_current():
    assert OUT.read_text() == render(), "run: .venv/bin/python -m scripts.export_schema"


def test_every_emitted_event_type_has_a_payload():
    found = {a or b for f in MUX.rglob("*.py") for a, b in EMITTED.findall(f.read_text())}
    assert {"message.labeled", "conflict.closed", "file.changed", "plan.item_updated"} <= found  # the scan works
    assert found - set(EVENT_PAYLOADS) == set()
