<!-- Copy everything below into AGENTS.md, replacing the block between
     HARNESS:PROJECT-START and HARNESS:PROJECT-END. Keep the markers.
     Budget: ~25 lines. CLAUDE.md + AGENTS.md are always loaded and
     test_docs.py fails the build past 200 lines total. -->

## Project facts

```
<dir>/     <what it is>            → <dir>/AGENTS.md
<dir>/     <what it is>            → <dir>/AGENTS.md
```

<One or two sentences: what this repo is, and where per-stack commands live.>
Rules that hold repo-wide:

- **<Rule>.** <The one-line version an agent can act on.>
- **<Rule>.** <Prefer rules with a checkable outcome over style preferences.>
- **Done = <your gate>** — <the command, and what "green" means>.

<!-- Guidance, delete before committing:
     · Only what applies EVERYWHERE. This block is inherited into every
       package; per-package detail goes in that package's AGENTS.md
       (templates/package-AGENTS.template.md), which narrows but never restates.
     · A rule an agent must NOT miss belongs here even if it feels
       package-specific — Codex may never reach a nested file from the root.
     · No @imports. Claude Code resolves them, Codex does not.
     · Name commands the sandbox actually permits. A wrapper that writes outside
       the working directory (./mvnw, some npx flows) fails as a sandbox error
       and reads like a tooling bug.
     · Repeated workflows belong in a skill, not here. -->
