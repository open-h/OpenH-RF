# Agents in this repo

Cross-agent instructions for AI tools (Claude Code, Codex CLI, OpenCode,
Copilot CLI, Gemini CLI, etc.) operating on this repository.

## Skills

Project skills live under [`.claude/skills/`](./.claude/skills/), following the
[Claude skill layout](https://docs.claude.com/en/docs/claude-code/skills). Each
skill is a directory containing a `SKILL.md` plus any `references/` and
`scripts/` it needs. The layout is just a directory of portable markdown, so
non-Claude tools can read the same `SKILL.md` directly.

Available skills:

| Skill | Purpose |
|---|---|
| [`.claude/skills/openh-rf-submission-eval/`](./.claude/skills/openh-rf-submission-eval/) | Evaluate a contributor submission to the OpenH-RF initiative against the RFP and submission guide. Produces a structured acceptance report. |

### Invocation per tool

- **Claude Code** — auto-discovered from `.claude/skills/`; invoke via the `Skill` tool (or it triggers automatically when relevant).
- **OpenAI Codex CLI** — point Codex at `.claude/skills/<name>/SKILL.md` via its agent/instruction config.
- **OpenCode** — load `.claude/skills/<name>/SKILL.md` via the project agent loader.
- **Other** — read `.claude/skills/<name>/SKILL.md` directly; the front-matter YAML names the skill and describes its trigger conditions.

The `SKILL.md` content is portable markdown. Only the discovery mechanism is
tool-specific — the rubrics, references, and scripts travel cleanly.

## Conventions

- `pyproject.toml` pins `zea`; use `uv sync` to set up the environment.
- Linux-only is the supported platform; Windows users should use WSL2.
