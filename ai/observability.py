"""Logging + tracing.

- ``get_logger`` gives a configured stderr logger.
- ``Trace`` writes one JSON line per event to runs/<run_id>.jsonl. That file is
  a complete, greppable, replayable record of everything the harness did:
  every model call, every evaluation, every span with timing.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def get_logger(name: str = "ai", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger


class Trace:
    """Append-only JSONL transcript of a run."""

    def __init__(self, run_id: str, out_dir: str = "runs") -> None:
        self.run_id = run_id
        self.path = Path(out_dir) / f"{run_id}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.log = get_logger()

    def event(self, kind: str, **data: Any) -> None:
        record = {"ts": time.time(), "run_id": self.run_id, "kind": kind, **data}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    @contextmanager
    def span(self, name: str, **data: Any):
        start = time.monotonic()
        self.event("span_start", name=name, **data)
        try:
            yield
        finally:
            self.event("span_end", name=name, seconds=round(time.monotonic() - start, 3))
