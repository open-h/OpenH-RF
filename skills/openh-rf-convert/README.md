# openh-rf-convert

Agentic Claude Code skill that converts a contributor's source ultrasound dataset
(HDF5, Verasonics `.mat`, `.npz`/`.npy`, `.bin`+`.json` sidecars, HF datasets)
into the OpenH-RF (zea) file format. Companion skill:
[`openh-rf-submission-eval`](../openh-rf-submission-eval/) for graded intake.

Spec + workflow live in [`SKILL.md`](SKILL.md). Per-format source guides in
[`references/sources/`](references/sources/).

## Install

Clone this repository. The committed `.claude/skills/openh-rf-convert` symlink
makes Claude Code auto-discover the skill (Linux/macOS/WSL2; on native Windows,
enable Developer Mode for symlinks). The skill reads
[`../openh-rf-shared/`](../openh-rf-shared/) as a sibling.

## License

Apache-2.0. Datasets this skill helps produce must be CC BY 4.0 per the
OpenH-RF initiative; that is a separate license from this tool.
