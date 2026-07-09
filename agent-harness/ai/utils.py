"""Small, dependency-free helpers."""
from __future__ import annotations

import json
import re
from typing import Any


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
