"""omkit/sanitize.py — Shared sanitisation helpers for LLM output and HTML.

``sanitize_llm_output`` is the minimal form used by Frontal: strip
``<think>...</think>`` blocks and trim whitespace. ``sanitize_llm_response``
is the fuller form used by Marrow: also strips code fences, inline base64
images, and normalises embedded JSON. ``sanitize_html`` performs a
conservative HTML escape (removes ``<script>`` and inline event handlers,
escapes the rest).

These helpers are presentation-layer sanitisation. They are **not** a PHI/PII
scrubber — do not rely on them for compliance.

exports: sanitize_llm_output(text) | sanitize_llm_response(text) | sanitize_html(text) | extract_json(text)
rules:   The sanitize module must maintain backward compatibility for all existing function signatures and return types. All sanitization functions must handle None and empty string inputs gracefully without raising exceptions. The module cannot introduce external dependencies or modify global state during execution.
agent:   ollama/qwen3-coder:latest | ollama | 2026-05-01 | codedna-cli | initial CodeDNA annotation pass
message: 
"""
from __future__ import annotations

import html
import json
import re


def sanitize_llm_output(text: str) -> str:
    """Remove <think>...</think> blocks and trim. Matches the historical

    Rules:   Removes all text enclosed in ... delimiters, including newlines, and trims whitespace. Future developers must know this is specifically for removing DeepSeek/Qwen thinking traces.
    ``services/frontal/sanitize.sanitize_llm_output`` behaviour."""
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def sanitize_llm_response(text: str) -> str:
    """Clean LLM response text for display and judging.

    - Strip <think>...</think> blocks (deepseek/qwen thinking)
    - Strip markdown code fences (```json ... ```)
    - Remove inline base64 images (data:image/...)
    - Normalise embedded JSON (consistent key ordering, indentation)

    Matches the historical ``services/marrow/core/sanitize.sanitize_llm_response``
    behaviour exactly.

    Rules:   Removes ... blocks, markdown code fences (```json ... ```), inline base64 images, and normalizes embedded JSON. Must preserve exact historical behavior for compatibility.
    """
    if not text:
        return ""

    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()

    text = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)

    text = text.strip()
    if text.startswith(("{", "[")):
        try:
            parsed = json.loads(text)
            text = json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False)
        except json.JSONDecodeError:
            pass

    return text.strip()


def sanitize_html(text: str) -> str:
    """Escape HTML and strip script tags / inline event handlers.

    Rules:   Escapes HTML and strips script tags and inline event handlers (e.g., onclick, onmouseover). Must ensure no XSS vulnerabilities are introduced.
    """
    if not text:
        return ""
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bon\w+\s*=\s*[\"'][^\"']*[\"']", "", text, flags=re.IGNORECASE)
    text = html.escape(text)
    return text


def extract_json(text: str) -> list | dict | None:
    """Extract JSON array or object from messy LLM output, or None.

    Rules:   Attempts to extract a valid JSON object or array from text by stripping leading non-JSON characters and handling malformed JSON. Future developers must know it may return None if parsing fails or no JSON is found.
    """
    if not text:
        return None

    cleaned = sanitize_llm_response(text)
    if not cleaned:
        return None

    for i, ch in enumerate(cleaned):
        if ch in ("{", "["):
            cleaned = cleaned[i:]
            break
    else:
        return None

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    bracket = cleaned[0]
    close = "}" if bracket == "{" else "]"
    depth = 0
    for i, ch in enumerate(cleaned):
        if ch == bracket:
            depth += 1
        elif ch == close:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[: i + 1])
                except json.JSONDecodeError:
                    return None
    return None
