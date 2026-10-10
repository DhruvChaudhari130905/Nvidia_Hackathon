"""Tool calls Nemotron writes into its message text instead of the tools API (room_db8a580bd5b9)."""

from mux.agents.llm import text_tool_calls


def test_functions_style_call_in_text_becomes_a_tool_call():
    text = 'Writing the page now. <tool_call> FUNCTIONS.write_file({"path": "index.html", "content": "<h1>Hi (there)</h1>"})'
    calls, rest = text_tool_calls(text)
    assert [(c.name, c.arguments) for c in calls] == [("write_file", {"path": "index.html", "content": "<h1>Hi (there)</h1>"})]
    assert rest == "Writing the page now."


def test_json_style_calls_with_closing_tags():
    text = ('<tool_call>{"name": "read_file", "arguments": {"path": "a.css"}}</tool_call>\n'
            '<tool_call>{"name": "list_files", "arguments": "{\\"path\\": \\".\\"}"}</tool_call>')
    calls, rest = text_tool_calls(text)
    assert [(c.name, c.arguments) for c in calls] == [("read_file", {"path": "a.css"}), ("list_files", {"path": "."})]
    assert rest == ""


def test_cut_off_or_plain_text_is_left_alone():
    truncated = '<tool_call> FUNCTIONS.write_file({"path": "styles.css", "content": "body {'
    assert text_tool_calls(truncated) == ([], truncated)
    plain = "No tools needed: the page already has a footer."
    assert text_tool_calls(plain) == ([], plain)
