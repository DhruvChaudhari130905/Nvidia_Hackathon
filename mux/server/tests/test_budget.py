"""Budget rules: which cap is reached, and the payload the web app reads."""

from mux.rooms.budget import Budget


def test_over():
    assert Budget().over is None
    assert Budget(tokens_used=2_000_000).over == "tokens"
    assert Budget(runs_used=100).over == "runs"
    assert Budget(tokens_used=4, tokens_cap=5).over is None


def test_payload_names_match_the_web_app():
    assert Budget(1, 2, 3, 4).payload().model_dump() == {"tokens_used": 1, "runs_used": 2, "tokens_cap": 3, "runs_cap": 4}
