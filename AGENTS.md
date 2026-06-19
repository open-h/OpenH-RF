# Agents in this repo

Cross-agent instructions for AI tools (Claude Code, Codex CLI, OpenCode,
Copilot CLI, Gemini CLI, etc.) operating on this repository.

## Skills

Project skills live under [`skills/`](./skills/) — a top-level, agent-agnostic
location. Each skill is a directory containing a `SKILL.md` plus any
`references/` and `scripts/` it needs; the layout is portable markdown that any
agent can read directly.

For **Claude Code**, which auto-discovers skills under `.claude/skills/`, a
committed symlink `.claude/skills/<name> → ../../skills/<name>` makes each skill
discoverable with zero setup. The symlink resolves on Linux/macOS and WSL2; on
native Windows, enable Developer Mode or use WSL2 so git materializes the
symlink rather than a plain text file (see the [main README](./README.md) — the
supported platforms are Linux and WSL2).

Available skills:

| Skill | Purpose |
|---|---|
| [`skills/openh-rf-submission-eval/`](./skills/openh-rf-submission-eval/) | Evaluate a contributor submission to the OpenH-RF initiative against the RFP and submission guide. Produces a structured acceptance report. |

### Invocation per tool

- **Claude Code** — auto-discovered via the committed `.claude/skills/` symlink; invoke via the `Skill` tool (or it triggers automatically when relevant).
- **OpenAI Codex CLI** — point Codex at `skills/<name>/SKILL.md` via its agent/instruction config.
- **OpenCode** — load `skills/<name>/SKILL.md` via the project agent loader.
- **Other** — read `skills/<name>/SKILL.md` directly; the front-matter YAML names the skill and describes its trigger conditions.

The `SKILL.md` content is portable markdown. Only the discovery mechanism is
tool-specific — the rubrics, references, and scripts travel cleanly.

## Conventions

- `pyproject.toml` pins `zea`; use `uv sync` to set up the environment.
- Linux-only is the supported platform; Windows users should use WSL2.
