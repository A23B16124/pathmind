"""
Task 1 — JSON repair for malformed LLM output.

LLMs under load return: truncated JSON, trailing commas, nested fences,
unicode escapes, mixed markdown+json, single-quoted keys, etc.

repair_llm_json(text) → dict  (never raises, returns {} on total failure)
"""

from __future__ import annotations

import json
import re


# ---------------------------------------------------------------------------
# Step 1: strip markdown fences
# ---------------------------------------------------------------------------

def _strip_fences(s: str) -> str:
    s = s.strip()
    # Handle nested or multiple fences
    while s.startswith("```"):
        parts = s.split("```", 2)
        if len(parts) < 2:
            break
        inner = parts[1]
        if inner.startswith("json"):
            inner = inner[4:]
        s = inner.strip()
    return s.strip().rstrip("`").strip()


# ---------------------------------------------------------------------------
# Step 2: extract first {...} or [...] block (skips leading prose)
# ---------------------------------------------------------------------------

def _extract_json_block(s: str) -> str:
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = s.find(start_char)
        if start == -1:
            continue
        # Walk to find balanced closing
        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(s[start:], start):
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
    return s


# ---------------------------------------------------------------------------
# Step 3: common fixups
# ---------------------------------------------------------------------------

def _fix_common(s: str) -> str:
    # Trailing commas before ] or }
    s = re.sub(r',\s*([}\]])', r'\1', s)
    # Single-quoted keys/values → double-quoted (simple heuristic)
    s = re.sub(r"(?<![\\])'([^']*?)'", r'"\1"', s)
    # Python True/False/None → JSON true/false/null
    s = re.sub(r'\bTrue\b', 'true', s)
    s = re.sub(r'\bFalse\b', 'false', s)
    s = re.sub(r'\bNone\b', 'null', s)
    # Remove comments (// and #)
    s = re.sub(r'//[^\n]*', '', s)
    s = re.sub(r'#[^\n]*', '', s)
    return s


# ---------------------------------------------------------------------------
# Step 4: truncation repair (add missing closing braces/brackets)
# ---------------------------------------------------------------------------

def _repair_truncated(s: str) -> str:
    opens = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in '{[':
            opens.append(ch)
        elif ch in '}]':
            if opens:
                opens.pop()

    if in_string:
        s += '"'
    for ch in reversed(opens):
        s += '}' if ch == '{' else ']'
    return s


# ---------------------------------------------------------------------------
# Step 5: regex key extraction fallback
# Extracts "key": value pairs from a broken blob
# ---------------------------------------------------------------------------

_KEY_VALUE_RE = re.compile(
    r'"([^"]+)"\s*:\s*'
    r'("(?:[^"\\]|\\.)*"'        # quoted string
    r'|-?\d+(?:\.\d+)?'           # number
    r'|true|false|null'           # literals
    r'|\[.*?\]'                   # simple array (non-greedy)
    r')',
    re.DOTALL,
)

def _regex_extract(s: str) -> dict:
    result = {}
    for m in _KEY_VALUE_RE.finditer(s):
        try:
            result[m.group(1)] = json.loads(m.group(2))
        except Exception:
            result[m.group(1)] = m.group(2)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def repair_llm_json(text: str) -> dict:
    """
    Parse LLM output as JSON. Returns {} only if completely unparseable.
    Never raises.
    """
    if not text or not text.strip():
        return {}

    # Pass 1: standard parse on stripped fences
    s = _strip_fences(text)
    s = _extract_json_block(s)
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except Exception:
        pass

    # Pass 2: fix common issues + retry
    s2 = _fix_common(s)
    try:
        v = json.loads(s2)
        return v if isinstance(v, dict) else {}
    except Exception:
        pass

    # Pass 3: truncation repair
    s3 = _repair_truncated(s2)
    try:
        v = json.loads(s3)
        return v if isinstance(v, dict) else {}
    except Exception:
        pass

    # Pass 4: regex key extraction (last resort, lossy)
    extracted = _regex_extract(text)
    return extracted if extracted else {}
