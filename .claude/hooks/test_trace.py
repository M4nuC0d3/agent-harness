#!/usr/bin/env python3
"""Behavioural tests for the PostToolUse trace hook.

The trace is the only hook output another tool reads back, and it was the only
hook with no test: guard, preflight and the docs had suites, `trace.py` had
none. A format nothing asserts is a format that drifts.

Every case below is a property the trace has to keep:

  * the five original fields stay exactly as they were (old jq keeps working)
  * the envelope is present and versioned (a reader can tell what it is holding)
  * values are never persisted — only parameter names
  * a malformed or unexpected event never breaks the session

    python3 .claude/hooks/test_trace.py .claude/hooks/trace.py

Stdlib only. Runs the hook as a subprocess in a scratch directory, exactly as
Claude Code and Codex run it.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

TRACE = Path(sys.argv[1] if len(sys.argv) > 1 else "trace.py").resolve()
LEGACY_FIELDS = ["ts", "session", "agent", "tool", "summary"]

failures: list[str] = []


def check(label: str, ok: bool, why: str = "") -> None:
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}" + ("" if ok else f" — {why}"))
    if not ok:
        failures.append(label)


def run(event: object, *, raw: str | None = None) -> tuple[int, list[dict]]:
    """Run the hook in a scratch cwd; return its exit code and the trace lines."""
    payload = raw if raw is not None else json.dumps(event)
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [sys.executable, str(TRACE)],
            input=payload,
            text=True,
            capture_output=True,
            cwd=tmp,
        )
        path = Path(tmp) / ".agent" / "trace.jsonl"
        lines = []
        if path.exists():
            lines = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
    return proc.returncode, lines


def expected_version() -> str:
    """What harness_version() should resolve to for the hook under test."""
    manifest = TRACE.resolve().parents[2] / ".claude-plugin" / "plugin.json"
    try:
        version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return "unknown"
    return version if isinstance(version, str) and version else "unknown"


def main() -> int:
    print("Backwards compatibility — the original five fields:")
    rc, lines = run(
        {
            "session_id": "sess-1",
            "subagent_type": "implementer",
            "tool_name": "Bash",
            "tool_input": {"command": "mvn -q verify"},
        }
    )
    check("exit code is 0", rc == 0, f"got {rc}")
    check("one line written", len(lines) == 1, f"got {len(lines)}")
    record = lines[0] if lines else {}
    for field in LEGACY_FIELDS:
        check(f"{field} is still present", field in record, "an old jq filter would break")
    check("session carries the session id", record.get("session") == "sess-1",
          f"got {record.get('session')!r}")
    check("agent is read from subagent_type", record.get("agent") == "implementer",
          f"got {record.get('agent')!r}")
    check("summary is still the command", record.get("summary") == "mvn -q verify",
          f"got {record.get('summary')!r}")

    print("\nThe versioned envelope:")
    check("schema is an int", isinstance(record.get("schema"), int),
          f"got {record.get('schema')!r}")
    check("event names the kind of line", record.get("event") == "tool_call",
          f"got {record.get('event')!r}")
    check("harness records the producing version",
          record.get("harness") == expected_version(),
          f"got {record.get('harness')!r}, expected {expected_version()!r}")
    check("harness is never empty", bool(record.get("harness")),
          "an unlabelled line cannot be compared across versions")
    check("args lists the parameter names", record.get("args") == ["command"],
          f"got {record.get('args')!r}")

    print("\nValues are never persisted:")
    rc, lines = run(
        {
            "session_id": "sess-2",
            "tool_name": "Read",
            "tool_input": {"file_path": "/repo/x.txt", "api_key": "SUPERSECRET"},
        }
    )
    blob = json.dumps(lines)
    check("the secret value is absent", "SUPERSECRET" not in blob, "trace leaked a value")
    check("the parameter name is present", lines and "api_key" in lines[0].get("args", []),
          f"got {lines[0].get('args') if lines else None}")

    print("\nThe top-level command shape (no tool_name):")
    rc, lines = run({"command": "npm ci", "cwd": "/repo", "sandbox": False})
    check("exit code is 0", rc == 0, f"got {rc}")
    check("tool is inferred as Bash", lines and lines[0].get("tool") == "Bash",
          f"got {lines[0].get('tool') if lines else None}")
    check("args is empty when there is no tool_input",
          lines and lines[0].get("args") == [], f"got {lines[0].get('args') if lines else None}")

    print("\nA failing trace must never break the session:")
    rc, lines = run(None, raw="not json at all")
    check("unparseable stdin exits 0", rc == 0, f"got {rc}")
    check("unparseable stdin writes nothing", lines == [], f"wrote {lines}")

    rc, lines = run({"tool_name": "Weird", "tool_input": ["not", "a", "mapping"]})
    check("an unexpected tool_input shape exits 0", rc == 0, f"got {rc}")
    check("an unexpected tool_input shape still writes a line", len(lines) == 1,
          f"got {len(lines)}")

    rc, lines = run([1, 2, 3])
    check("a non-object event exits 0", rc == 0, f"got {rc}")

    print("\nThe file stays valid JSONL across calls:")
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(3):
            subprocess.run(
                [sys.executable, str(TRACE)],
                input=json.dumps({"session_id": "s", "tool_name": f"T{i}", "tool_input": {}}),
                text=True,
                capture_output=True,
                cwd=tmp,
            )
        raw = (Path(tmp) / ".agent" / "trace.jsonl").read_text(encoding="utf-8")
    parsed = [json.loads(line) for line in raw.splitlines() if line.strip()]
    check("three calls append three lines", len(parsed) == 3, f"got {len(parsed)}")
    check("every line parses on its own", all(isinstance(p, dict) for p in parsed))

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        return 1
    print("trace format is stable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
