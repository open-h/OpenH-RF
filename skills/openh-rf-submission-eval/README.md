# openh-rf-submission-eval

A Claude skill for evaluating submissions to the [OpenH-RF](https://github.com/open-h/OpenH-RF) open ultrasound channel-data initiative against the RFP and submission guide.

## What it does

Given a contributor submission (zea file + data card + pipeline), the skill produces a structured acceptance report covering seven independent evaluation dimensions:

1. **Format compliance** — is the file actually in zea format?
2. **Reconstruction** — does the pipeline run and produce a sensible B-mode image, free of pipeline-induced artifacts?
3. **Metadata sufficiency** — can a stranger reconstruct from this without contacting the contributor?
4. **Data card** — complete per template, no placeholder text, no PHI?
5. **Documentation & clarity** — would a first-time user hit walls?
6. **Licensing & IP** — confirmed CC BY 4.0, no encumbrances?
7. **Ethics & compliance** — tier-appropriate (HIPAA Safe Harbor for human data, ARRIVE 2.0 for animal, etc.)

Each dimension is decoupled and designed for parallel sub-agent execution in Claude Code. Each opens with a short persona block (e.g., "data-format auditor", "research compliance officer") that sets the disposition for that dimension.

**The accepted proposal is a required input.** The skill reads it first and checks the submission *against* it: content promised but missing is flagged as under-delivery, and anything added beyond the proposal must be documented in the data card. The goal is a submission that stays aligned with what was proposed and accepted — additions are welcome, but they have to be written down. Without the proposal the skill cannot assess alignment or honor negotiated carve-outs.

## Layout

```
openh-rf-submission-eval/
├── SKILL.md                  # Orchestration: workflow, verdict logic, auto-fix rules
├── references/
│   ├── rfp-summary.md        # OpenH-RF RFP scope and tiers
│   ├── data-card-template.md # Canonical data card template
│   ├── zea-format-notes.md   # zea file format reference
│   ├── phi-checklist.md      # HHS Safe Harbor 18 identifiers
│   ├── imaging-artifacts.md  # Acquisition-induced vs pipeline-induced artifact taxonomy
│   └── dimensions/
│       ├── 01-format.md
│       ├── 02-reconstruction.md
│       ├── 03-metadata.md
│       ├── 04-data-card.md
│       ├── 05-documentation.md
│       ├── 06-licensing.md
│       └── 07-ethics.md
└── scripts/
    ├── pipeline_template.py  # Default DAS->envelope->log B-mode pipeline (auto-fix)
    └── judge_bmode.py        # Objective sanity checks on a reconstructed image
```

## How to install

### As a Claude Code skill

The skill lives at `skills/openh-rf-submission-eval/` in the OpenH-RF repo, with
a committed `.claude/skills/openh-rf-submission-eval` symlink pointing at it.
Clone the repo and Claude Code auto-discovers the skill with no extra setup — on
Linux/macOS/WSL2; on native Windows, enable Developer Mode or use WSL2 so git
materializes the symlink rather than a plain text file.

```bash
git clone <repo-url>
```

To use it outside this repo, symlink (or copy) the skill into your personal
skills directory:

```bash
ln -s "$(pwd)/skills/openh-rf-submission-eval" ~/.claude/skills/openh-rf-submission-eval
```

### As a packaged .skill file

```bash
# Using the skill-creator packaging script
python -m scripts.package_skill /path/to/openh-rf-submission-eval
# Produces openh-rf-submission-eval.skill, which can be uploaded in Claude.ai
```

## How to use

Once installed, ask Claude to evaluate a submission:

> "Evaluate this OpenH-RF submission at `/path/to/submission/`"
>
> "Can we accept the submission at ~/openh-rf/inbox/example-contributor-2026-06/?"

The skill produces `evaluation_report.md` plus, if applicable, an `autofix/` directory containing auto-generated artifacts (B-mode pipeline, reference image, filled-in data-card fields).

## Verdict rules

- Any `blocker` finding → **Reject — needs resubmission**
- Any `major` finding → **Accept with revisions**
- Only `minor`/`info` → **Accept**

## What gets auto-fixed

- Missing B-mode pipeline (generated from `scripts/pipeline_template.py` if metadata is sufficient)
- Derivable data-card fields (sample count, total size, per-sample feature table)
- Missing reference B-mode images (rendered once the pipeline works)

What does **not** get auto-fixed: license declarations, consent/IRB status, subject metadata, intended-usage descriptions, known-issues. These require the contributor.

## License

Apache-2.0, matching the OpenH-RF repository — this skill is software. (Note:
*dataset submissions* evaluated by this skill must be CC BY 4.0, which is the
data license the initiative requires; that is a separate thing from the license
of this tool.)
