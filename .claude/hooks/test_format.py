#!/usr/bin/env python3
"""Behaviour of the format-on-write hook.

format.py was the one hook with no suite, which is how it kept two bugs that
nothing noticed: it resolved its map next to `__file__` (so a plugin install fed
every consumer the harness author's map), and it matched prefixes against the
absolute path with an unanchored substring test (so `frontend/` also meant
`vendor/legacy/frontend/`, and `""` reached files outside the project).

Both are invisible in review and obvious in a test, which is the whole argument
for this file. `test_docs.py` asserts the hook stays free of stack knowledge;
this asserts it does the right thing with the knowledge it is handed.

    python3 .claude/hooks/test_format.py .claude/hooks/format.py

No real formatter is needed: each case puts a fake one on PATH that appends the
file it was handed to a log, so "did it format, and what" is just the log. Stdlib
only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(sys.argv[1] if len(sys.argv) > 1 else ".claude/hooks/format.py").resolve()

failures: list[str] = []


def check(label: str, ok: bool, why: str = "") -> None:
    print(f"  [{'ok ' if ok else 'FAIL'}] {label}" + ("" if ok else f" — {why}"))
    if not ok:
        failures.append(label)


class Project:
    """A throwaway project tree with the hook and a fake formatter installed.

    hook_dir is deliberately separate from the project root: that is the plugin
    install shape, and the only shape in which the __file__ bug is visible.
    """

    def __init__(self, rules: object | str | None, hook_outside: bool = False,
                 git_init: bool = False) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "project"
        self.log = self.tmp / "ran.log"
        (self.root / ".claude").mkdir(parents=True)

        hook_home = (self.tmp / "plugin-cache") if hook_outside else self.root
        self.hook_dir = hook_home / ".claude" / "hooks"
        self.hook_dir.mkdir(parents=True, exist_ok=True)
        self.hook = self.hook_dir / "format.py"
        shutil.copy(HOOK, self.hook)

        if rules is not None:
            text = rules if isinstance(rules, str) else json.dumps({"rules": rules})
            (self.root / ".claude" / "format.map.json").write_text(text, encoding="utf-8")

        if git_init:
            subprocess.run(["git", "init", "-q"], cwd=self.root, check=True,
                           capture_output=True)

        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        fake = self.bin / "tidy"
        fake.write_text(f'#!/bin/sh\necho "$2" >> "{self.log}"\n', encoding="utf-8")
        fake.chmod(0o755)

    def write(self, rel: str) -> Path:
        """Create a file, relative to the project root (or above it via ../)."""
        target = (self.root / rel).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x=1\n", encoding="utf-8")
        return target

    def fire(self, target: Path, tool: str = "Write") -> int:
        return self._send({"tool_name": tool,
                           "tool_input": {"file_path": str(target)}})

    def fire_patch(self, *rels: str, verb: str = "Update", argv: bool = False) -> int:
        """A Codex apply_patch event: no file_path, an envelope in command.

        Codex reports tool_name apply_patch whatever the matcher said, and one
        patch can name several files — the reason the hook parses rather than
        reads a field.
        """
        body = ["*** Begin Patch"]
        for rel in rels:
            body.append(f"*** {verb} File: {rel}")
            body.append("@@")
        body.append("*** End Patch")
        envelope = "\n".join(body)
        command = ["apply_patch", envelope] if argv else envelope
        return self._send({"tool_name": "apply_patch",
                           "tool_input": {"command": command}})

    def _send(self, payload: dict) -> int:
        env = dict(os.environ,
                   CLAUDE_PROJECT_DIR=str(self.root),
                   PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        done = subprocess.run([sys.executable, str(self.hook)],
                              input=json.dumps(payload), capture_output=True,
                              text=True, env=env, timeout=30)
        return done.returncode

    def fire_from_subdir(self, target: Path) -> int:
        """Codex sets no CLAUDE_PROJECT_DIR and may start below the root."""
        sub = self.root / "frontend"
        env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        env.pop("CLAUDE_PROJECT_DIR", None)
        payload = {"tool_name": "apply_patch",
                   "tool_input": {"command": f"*** Begin Patch\n*** Update File: "
                                             f"{target.relative_to(self.root)}\n"}}
        done = subprocess.run([sys.executable, str(self.hook)],
                              input=json.dumps(payload), capture_output=True,
                              text=True, env=env, cwd=sub, timeout=30)
        return done.returncode

    def formatted(self) -> list[str]:
        if not self.log.exists():
            return []
        return [ln for ln in self.log.read_text(encoding="utf-8").splitlines() if ln]

    def clean(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


TS = {"prefix": "frontend/", "extensions": [".ts"],
      "command": ["tidy", "-i", "{file}"], "requires": "tidy"}


def main() -> int:
    print("A hook must never block a write, whatever the map says:")
    for label, rules in [("no map at all", None),
                         ("malformed map", "{ not json"),
                         ("empty rules", []),
                         ("rule with no command", [{"prefix": "", "extensions": [".ts"]}]),
                         ("formatter not on PATH", [dict(TS, requires="nope-not-here")])]:
        p = Project(rules)
        target = p.write("frontend/app.ts")
        code = p.fire(target)
        check(f"exits 0 — {label}", code == 0, f"exit {code} would block the tool call")
        if label != "no map at all":
            check(f"formats nothing — {label}", p.formatted() == [],
                  f"ran anyway: {p.formatted()}")
        p.clean()

    print("\nThe map is the project's, never the one next to the hook:")
    p = Project([dict(TS, prefix="")], hook_outside=True)
    target = p.write("frontend/app.ts")
    # The plugin cache also holds a map that would match everything. Reading it
    # is the bug: a consumer would inherit rules they cannot see or edit.
    (p.hook_dir.parent / "format.map.json").write_text(
        json.dumps({"rules": [{"prefix": "", "extensions": [".ts"],
                               "command": ["tidy", "-i", "{file}"], "requires": "tidy"}]}),
        encoding="utf-8")
    p.fire(target)
    check("the project's map wins when the hook lives elsewhere",
          p.formatted() == [str(target)],
          "the hook read a map relative to __file__ — that is the plugin's, not the user's")
    p.clean()

    p = Project(None, hook_outside=True)
    target = p.write("frontend/app.ts")
    (p.hook_dir.parent / "format.map.json").write_text(
        json.dumps({"rules": [{"prefix": "", "extensions": [".ts"],
                               "command": ["tidy", "-i", "{file}"], "requires": "tidy"}]}),
        encoding="utf-8")
    p.fire(target)
    check("no project map means no formatting, even with one beside the hook",
          p.formatted() == [], f"formatted from the plugin's map: {p.formatted()}")
    p.clean()

    print("\nPrefixes are anchored at the project root:")
    p = Project([TS])
    top = p.write("frontend/app.ts")
    nested = p.write("vendor/legacy/frontend/old.ts")
    deps = p.write("frontend/node_modules/dep/lib.ts")
    for t in (top, nested, deps):
        p.fire(t)
    check("frontend/ matches the package at the root", str(top) in p.formatted(),
          "the rule the user actually wrote does not fire")
    check("frontend/ does NOT match vendor/legacy/frontend/", str(nested) not in p.formatted(),
          "an unanchored prefix formats trees the map never named")
    # Vendored code *under* the prefix does match, and should: it is genuinely
    # inside the tree the rule names. Excluding it belongs in the formatter's own
    # ignore file (.prettierignore, .editorconfig), not here — an ignore list in
    # the hook would be stack knowledge, which test_docs.py rejects on purpose.
    check("a vendored tree under the prefix is not silently exempt",
          str(deps) in p.formatted(),
          "the hook must not grow its own ignore list — that is the formatter's job")
    p.clean()

    p = Project([{"prefix": "packages/frontend/", "extensions": [".ts"],
                  "command": ["tidy", "-i", "{file}"], "requires": "tidy"}])
    deep = p.write("packages/frontend/app.ts")
    p.fire(deep)
    check("a multi-segment prefix still matches", p.formatted() == [str(deep)],
          "anchoring must not break prefixes that are more than one directory")
    p.clean()

    print("\nA rule can never reach outside the project:")
    p = Project([{"prefix": "", "extensions": [".ts"],
                  "command": ["tidy", "-i", "{file}"], "requires": "tidy"}])
    inside = p.write("frontend/app.ts")
    outside = p.write("../stranger.ts")
    p.fire(inside)
    p.fire(outside)
    check("'' matches every file IN the project", str(inside) in p.formatted(),
          "an empty prefix is documented as matching everything")
    check("'' does not match a file above the project root",
          str(outside) not in p.formatted(),
          "the map is the project's; its reach must be too")
    p.clean()

    print("\nOnly the write tools, and only files that exist:")
    p = Project([dict(TS, prefix="")])
    target = p.write("frontend/app.ts")
    p.fire(target, tool="Bash")
    check("a non-write tool is ignored", p.formatted() == [],
          "the hook is wired for Write|Edit|MultiEdit")
    p.clean()

    p = Project([dict(TS, prefix="")])
    ghost = p.root / "frontend" / "gone.ts"
    code = p.fire(ghost)
    check("a path that is not a file exits 0 and formats nothing",
          code == 0 and p.formatted() == [], "a deleted or renamed file is not an error")
    p.clean()

    print("\nExtensions gate the rule, and the first match wins:")
    p = Project([TS])
    css = p.write("frontend/app.css")
    p.fire(css)
    check("an extension outside the rule is left alone", p.formatted() == [],
          f"formatted a file the rule does not name: {p.formatted()}")
    p.clean()

    p = Project([dict(TS, command=["tidy", "-first", "{file}"]),
                 dict(TS, command=["tidy", "-second", "{file}"])])
    target = p.write("frontend/app.ts")
    p.fire(target)
    check("only the first matching rule runs", len(p.formatted()) == 1,
          f"both rules fired: {p.formatted()}")
    p.clean()

    print("\nCodex reports edits as apply_patch, with an envelope, not a path:")
    p = Project([TS])
    top = p.write("frontend/app.ts")
    p.fire_patch("frontend/app.ts")
    check("a patch envelope names the file to format", p.formatted() == [str(top)],
          "reading tool_input.file_path only — Codex never sends that field")
    p.clean()

    p = Project([TS])
    a = p.write("frontend/a.ts")
    b = p.write("frontend/b.ts")
    p.fire_patch("frontend/a.ts", "frontend/b.ts")
    check("every file in one patch is formatted",
          sorted(p.formatted()) == sorted([str(a), str(b)]),
          "one patch can touch many files; stopping at the first drops the rest")
    p.clean()

    p = Project([TS])
    added = p.write("frontend/new.ts")
    p.fire_patch("frontend/new.ts", verb="Add")
    check("an added file is formatted", p.formatted() == [str(added)],
          "Add File is a write like any other")
    p.clean()

    p = Project([TS])
    p.write("frontend/app.ts")
    p.fire_patch("frontend/app.ts", verb="Delete")
    check("a deleted file is not formatted", p.formatted() == [],
          "there is nothing to format, and the path may already be gone")
    p.clean()

    p = Project([TS])
    boxed = p.write("frontend/app.ts")
    p.fire_patch("frontend/app.ts", argv=True)
    check("the envelope is found when it arrives as argv",
          p.formatted() == [str(boxed)], "command may be a list, not a string")
    p.clean()

    p = Project([TS])
    p.write("frontend/app.ts")
    p.fire_patch("../escape.ts")
    check("an envelope path cannot climb out of the project", p.formatted() == [],
          "envelope paths are relative and attacker-shaped input is still input")
    p.clean()

    p = Project([dict(TS, prefix="")])
    target = p.write("frontend/app.ts")
    code = p._send({"tool_name": "apply_patch", "tool_input": {"command": "not a patch"}})
    check("a command that is not an envelope formats nothing and exits 0",
          code == 0 and p.formatted() == [], "a Bash payload must not be mined for paths")
    p.clean()

    print("\nWithout CLAUDE_PROJECT_DIR the git root anchors the prefixes:")
    p = Project([TS], git_init=True)
    target = p.write("frontend/app.ts")
    p.fire_from_subdir(target)
    check("prefixes still match when Codex starts in a subdirectory",
          p.formatted() == [str(target)],
          "falling back to the working directory makes every prefix in the map miss")
    p.clean()

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        return 1
    print("format-on-write is anchored, project-scoped and never blocking")
    return 0


if __name__ == "__main__":
    sys.exit(main())
