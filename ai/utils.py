"""Small, dependency-free helpers."""
from __future__ import annotations

import json
import re
from typing import Any

# Marker a worker appends to separate its full result from the short, distilled
# summary the coordinator keeps in context. Chosen to be unlikely in real output
# and easy to split on. See ai/context.py for why summaries matter.
SUMMARY_MARKER = "===SUMMARY==="


def approx_tokens(text: str) -> int:
    """Very rough token estimate (~4 chars/token) — no tokenizer dependency.

    Used only to *budget* context, never for billing. Good enough to decide
    "does this fit in the sub-agent's context allowance?".
    """
    return max(1, len(text or "") // 4)


def split_summary(text: str) -> tuple[str, str]:
    """Split a worker response into (full_body, summary).

    Workers are asked to append ``===SUMMARY===`` followed by a short recap.
    If the marker is absent (some models ignore the instruction, and the mock
    provider may too), summary is "" and the caller falls back to truncation.
    """
    if SUMMARY_MARKER in text:
        body, _, summary = text.partition(SUMMARY_MARKER)
        return body.strip(), summary.strip()
    return text.strip(), ""


def truncate_tokens(text: str, max_tokens: int) -> str:
    """Trim text to ~max_tokens, cutting on a word boundary and marking the cut.

    This is the deterministic, zero-cost fallback for compaction when no
    summarizer model is used.
    """
    text = (text or "").strip()
    if approx_tokens(text) <= max_tokens:
        return text
    keep_chars = max_tokens * 4
    clipped = text[:keep_chars].rsplit(" ", 1)[0]
    return clipped.rstrip() + " …[truncated]"


def extract_json(text: str) -> Any:
    """Best-effort extraction of the first JSON value from a model response.

    Tolerates ```json fences and surrounding prose, which models sometimes add
    even when told not to. Raises ValueError if nothing parseable is found.
    """
    text = text.strip()

    # 1) strip a ```json ... ``` (or plain ``` ... ```) code fence if present
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    # 2) try to parse the whole thing directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3) fall back to the first {...} or [...] block
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError(f"No JSON found in model output: {text[:200]!r}")
