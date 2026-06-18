# Agents in this repo

Cross-agent instructions for AI tools (Claude Code, Codex CLI, OpenCode,
Copilot CLI, Gemini CLI, etc.) operating on this repository.

## Skills

Project skills live under [`skills/`](./skills/). Each skill is a directory
containing a `SKILL.md` plus any `references/` and `scripts/` it needs. The
layout is plain markdown — any agent that can read files can use it.

Available skills:

| Skill | Purpose |
|---|---|
| [`skills/openh-rf-submission-eval/`](./skills/openh-rf-submission-eval/) | Evaluate a contributor submission to the OpenH-RF initiative against the RFP and submission guide. Produces a structured acceptance report. |

### Invocation per tool

- **Claude Code** — reference `skills/<name>/SKILL.md` from a `CLAUDE.md` or invoke via the `Skill` tool. (Auto-discovery requires the skill to be in `.claude/skills/`; symlink if preferred.)
- **OpenAI Codex CLI** — point Codex at `skills/<name>/SKILL.md` via its agent/instruction config.
- **OpenCode** — load `skills/<name>/SKILL.md` via the project agent loader.
- **Other** — read `skills/<name>/SKILL.md` directly; the front-matter YAML names the skill and describes its trigger conditions.

The `SKILL.md` content is portable markdown. Only the discovery mechanism is
tool-specific — the rubrics, references, and scripts travel cleanly.

## Conventions

- `pyproject.toml` pins `zea`; use `uv sync` to set up the environment.
- Linux-only is the supported platform; Windows users should use WSL2.
