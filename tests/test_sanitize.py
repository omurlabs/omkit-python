"""packages/omur-sdk/tests/test_sanitize.py — presentation-layer sanitisation helpers.

exports: test_sanitize_llm_output_strips_think() | test_sanitize_llm_response_strips_code_fence() | test_sanitize_llm_response_removes_base64_image() | test_sanitize_html_removes_script_tag() | test_extract_json_object() | test_extract_json_array() | test_extract_json_returns_none_on_garbage()
used_by: none
rules:   none
agent:   codedna-cli (no-llm) | codedna-cli | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from omur_sdk.sanitize import (
    extract_json,
    sanitize_html,
    sanitize_llm_output,
    sanitize_llm_response,
)


def test_sanitize_llm_output_strips_think():
    raw = "<think>reasoning</think>\nfinal answer"
    assert sanitize_llm_output(raw) == "final answer"


def test_sanitize_llm_response_strips_code_fence():
    raw = "```json\n{\"k\": 1}\n```"
    assert "```" not in sanitize_llm_response(raw)
    assert "\"k\"" in sanitize_llm_response(raw)


def test_sanitize_llm_response_removes_base64_image():
    raw = "here: data:image/png;base64,iVBORw0KGgo= end"
    assert "base64" not in sanitize_llm_response(raw)
    assert "here:" in sanitize_llm_response(raw)


def test_sanitize_html_removes_script_tag():
    raw = "<p>hi</p><script>alert(1)</script>"
    out = sanitize_html(raw)
    assert "<script>" not in out
    assert "&lt;p&gt;hi&lt;/p&gt;" in out


def test_extract_json_object():
    raw = "preamble\n{\"a\": 1, \"b\": 2}\ntrailing"
    assert extract_json(raw) == {"a": 1, "b": 2}


def test_extract_json_array():
    raw = "junk[1, 2, 3]junk"
    assert extract_json(raw) == [1, 2, 3]


def test_extract_json_returns_none_on_garbage():
    assert extract_json("no json here") is None
