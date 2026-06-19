---
name: openh-rf-submission-eval
description: Evaluate a submission to the OpenH-RF (open ultrasound channel-data) initiative against the RFP and submission guide. Use this whenever the user wants to review, grade, validate, accept, or QA a proposed contribution to OpenH-RF, OpenH, or any open ultrasound channel/RF dataset — including when they hand over a folder, a Hugging Face link, a zea file, or a data card and ask whether it's ready, whether it meets the bar, what's missing, or whether it can be accepted. Also use when the user wants to auto-fix gaps in a submission, such as generating a missing B-mode pipeline, filling in data-card fields, or rendering a reference reconstruction. Trigger even if the user doesn't say OpenH-RF by name — ultrasound channel data plus a review or intake context is enough.
---

# OpenH-RF Submission Evaluator

This skill reviews a contributor submission to the OpenH-RF initiative and produces a structured acceptance report. Each evaluation dimension is independent and is designed to be dispatched to a sub-agent in parallel.

## Minimum zea version

Every submission must have been written with **zea v0.1.0a3 or later**. The version is stored as the `zea_version` attribute at the HDF5 file root. Files written with v0.1.0a2 or earlier are not eligible — the format spec changed in ways that make older files incompatible. `validate_zea_spec.py` records the installed zea version in its output; flag any `zea_version` in the file that is below `0.1.0a3` as a `blocker`.

## What you're evaluating against

OpenH-RF accepts pre-beamformed ultrasound channel data in the *zea* file format, licensed CC BY 4.0, accompanied by a Hugging Face–style `README.md` (which **is** the data card — Hugging Face renders `README.md` as the dataset landing page; see <https://huggingface.co/docs/hub/datasets-cards>) and a reconstruction pipeline that turns the raw channel data into a B-mode image. **There is exactly one user-facing document: `README.md`. There is no separate `DATA_CARD.md`.** The full requirements live in:

- `references/rfp-summary.md` — RFP scope, tiers, eligibility, timeline
- `references/data-card-template.md` — exact fields the `README.md` must contain, including the YAML frontmatter HF parses
- `references/zea-format-notes.md` — what a valid zea file looks like and what fields it must expose
- `references/phi-checklist.md` — canonical HHS Safe Harbor 18 identifiers (used by dimensions 4 and 7)
- `references/imaging-artifacts.md` — taxonomy of acquisition-induced vs pipeline-induced image artifacts (used by dimension 2)

Read these as needed. Do not try to hold them all in head — pull them in when a specific dimension calls for it.

## Sub-agent personas

Each dimension file opens with a short **Persona** block — a one-paragraph role and disposition. When dispatching a sub-agent for a dimension, the persona is the framing the sub-agent operates under (e.g., "data-format auditor", "ultrasound imaging engineer", "research compliance officer"). The personas are deliberately lightweight: just enough to set tone and rigor, not a full character. They make findings more memorable across dimensions and help calibrate severity ("the compliance officer flagged …" vs "the reproducibility reviewer flagged …").

Do not invent new personas or stretch them. If a dimension's persona feels wrong for a specific submission, fall back to neutral instruction-following — don't drift.

## The seven evaluation dimensions

A submission is scored on seven independent dimensions. Each has its own checklist file under `references/dimensions/`. The dimensions are deliberately decoupled so they can run in parallel as sub-agents:

1. **Format compliance** (`dimensions/01-format.md`) — Is the data actually in zea format? Do the on-disk fields, shapes, and dtypes match the spec?
2. **Reconstruction** (`dimensions/02-reconstruction.md`) — Run the contributor's pipeline. Does it produce a sensible B-mode image? This is the most expensive check.
3. **Metadata sufficiency** (`dimensions/03-metadata.md`) — Are all acquisition hyperparameters (transducer geometry, element count, center frequency, sampling rate, sound speed, transmit sequence, etc.) present and self-consistent? A novice with no contact with the contributor must be able to reconstruct from what's in the file alone.
4. **Data card** (`dimensions/04-data-card.md`) — `README.md` exists at the dataset root, carries valid HF YAML frontmatter (`license`, `pretty_name`, `task_categories`, `tags`), every template section filled in, no placeholder text, statistics aggregate-only (no PHI).
5. **Documentation & clarity** (`dimensions/05-documentation.md`) — Can a graduate student who has never seen this data understand what it is, what task it supports, and how to use it within ~15 minutes of reading? This is the "novice user" check, evaluated against the same `README.md` plus the pipeline and reference images.
6. **Licensing & IP** (`dimensions/06-licensing.md`) — Confirmed CC BY 4.0, no third-party IP encumbrances, consent/IRB status documented.
7. **Ethics & compliance** (`dimensions/07-ethics.md`) — HIPAA Safe Harbor de-identification for human data, ARRIVE 2.0 for animal, IRB approval where required.

Each dimension file contains its own pass/fail criteria, severity rubric, and what evidence to record.

## Workflow

### Step 1: Locate and inventory the submission

The user will hand you a path (local folder, mounted bucket, HF repo). Before evaluating anything, list what's actually there. Expect roughly:

- One or more `.hdf5` files in *zea* format — the channel data; **each acquisition is a single HDF5 file**, and a submission may contain several
- `reconstruct.py` — a single runnable script that reconstructs from the raw channel data and outputs a `.png`
- `pipeline.yaml` — a saved `zea.Pipeline`, **one per track** in the file(s)
- `README.md` at the dataset root — this **is** the data card (HF renders it as the dataset landing page). Must have YAML frontmatter with `license`, `pretty_name`, `task_categories`, `tags`.
- `LICENCE` file declaring **CC BY 4.0** (either spelling — the submission guide uses `LICENCE`)
- 1–2 reference B-mode images (the `.png`(s) `reconstruct.py` produces)
- Possibly: consent/IRB documentation

This is exactly the deliverable set the submission guide requires: zea `.hdf5` files, `reconstruct.py`, `pipeline.yaml` (one per track), `README.md`, and `LICENCE`. A separate `DATA_CARD.md` is **not** part of the expected layout — if one exists, treat it as a contributor-side artifact to be merged into `README.md` and flag the duplication.

Make an `inventory.json` recording what's present, what's missing, and file sizes. If the inventory is grossly incomplete (e.g., no zea file at all), stop and report — there's nothing to evaluate yet.

**Read the proposal first — it is required.** The accepted proposal is the contract: the submission is evaluated partly on whether it delivers what the contributor said they would deliver. Before dispatching any dimension sub-agents, read the contributor's accepted proposal from the source location (typically a PDF in the submission tree). If it isn't in the submission, ask the user for it. **If no accepted proposal can be produced, stop and mark the evaluation `blocked`** — without it you cannot check alignment or honor any negotiated carve-outs. Extract: declared tier, tasks, the **data types / modalities / quantities promised**, license intent, ethics codes, and **any explicit carve-outs** (things the contributor said they would *not* provide). Carve-outs the steering group accepted at proposal review are **not** failures during evaluation — note them and move on. Each dimension sub-agent prompt must include the carve-out list so they don't double-jeopardy the contributor on something already negotiated.

Common carve-out examples: "3D position information will not be provided", "subject demographics aggregate-only", "annotations limited to N frames per acquisition".

**Step 1b — check the submission against the proposal.** OpenH-RF wants submissions that match what was proposed and accepted, not something materially different. Compare the inventory to the proposal and record three things:

- **Delivered as proposed** — promised content that is present. No finding.
- **Under-delivered** — content the proposal promised that is missing or materially smaller than promised, and that is *not* an accepted carve-out. This is a `major` finding (route it to the relevant dimension): the contributor should either deliver it or get a carve-out on record. (Missing `raw_data` is always a `blocker` regardless — see below.)
- **Added beyond the proposal** — content present that the proposal did not mention (extra modalities, tasks, subjects, derived products). This is **not** a reason to reject — additions are welcome — but each addition **must be documented in the data card** (`README.md`). An undocumented addition is a `major` data-card finding ("you included X beyond your proposal; describe it in the data card"). Also note material scope additions for steering-group awareness.

Pass the alignment summary (under-delivered list + added-beyond-proposal list) into the relevant dimension sub-agents alongside the carve-out list.

**Hard requirement — no carve-out applies.** Every OpenH-RF submission **must** include raw pre-beamformed channel capture data (`/data/raw_data` in zea format). This is the core of the dataset and is non-negotiable: a proposal that omits raw channel data does not qualify, and an evaluation that finds `/data/raw_data` missing or empty should mark dimension 1 (Format) `blocker` regardless of what the proposal says.

### Step 2: Dispatch the seven dimension checks in parallel

In Claude Code, spawn one sub-agent per dimension. Each sub-agent:
- Reads only its own `references/dimensions/0X-*.md`
- Reads only the submission artifacts relevant to its dimension (the dimension file says which)
- Returns a structured result: `{dimension, status, severity, findings[], evidence[], suggested_fixes[]}`

`status` is one of: `pass`, `pass_with_notes`, `fail`, `blocked` (couldn't evaluate — usually means a dependency is missing).
`severity` is `info`, `minor`, `major`, `blocker`. A `blocker` on any dimension means the submission cannot be accepted as-is.

If you're not in an environment with sub-agents, run them serially in the order above — format first (cheap, gates everything else), reconstruction last (most expensive).

### Step 3: Auto-fix the fixable

Several common gaps are fixable without going back to the contributor:

- **Missing B-mode pipeline.** If metadata is sufficient (dimension 3 passed) but `reconstruct.py` / `pipeline.yaml` were not included, generate them. The template is at `scripts/pipeline_template.py` — use `zea.Pipeline.from_default()` as the starting point (standard chain: `Cast -> ApplyWindow -> Demodulate -> Beamform(PatchedGrid(TOFCorrection -> DelayAndSum) -> ReshapeGrid) -> EnvelopeDetect -> Normalize -> LogCompress`). Save the script as `reconstruct.py` and the saved pipeline as `pipeline.yaml` (**one per track**, matching the submission guide), then re-run dimension 2 against it.
- **Missing or incomplete `README.md` (the data card).** Generate a single `README.md` — never a separate `DATA_CARD.md` — with HF YAML frontmatter (`license`, `pretty_name`, `task_categories`, `tags`) followed by the data-card sections from `references/data-card-template.md`. Auto-populate the derivable fields (number of samples, total size on disk, per-sample feature table, file format, dataset characterization) from the zea file. Flag the rest as `REQUIRES_CONTRIBUTOR` rather than silently filling. If a `DATA_CARD.md` already exists, merge its content into `README.md` and mark the standalone file for removal.
- **Missing reference B-mode images.** Once you have a working pipeline, render 1–2 representative frames and add them to the submission. Link them from the `Data Validation` section of the `README.md`.

Never auto-fix: license declarations, consent/IRB status, subject metadata, intended-usage descriptions, known-issues. These require the contributor.

### Step 4: Render the acceptance report

Produce `evaluation_report.md` with this exact structure:

```
# OpenH-RF Submission Evaluation: <submission name>

**Overall verdict:** Accept | Accept with revisions | Reject — needs resubmission
**Evaluated on:** <date>
**Reviewer:** Claude (automated)

## Executive scorecard

| # | Category | Result |
|---|---|---|
| 1 | Format compliance | ✅ PASS  /  ❌ FAIL |
| 2 | Reconstruction & image quality | ✅ PASS  /  ❌ FAIL |
| 3 | Metadata sufficiency | ✅ PASS  /  ❌ FAIL |
| 4 | Data card | ✅ PASS  /  ❌ FAIL |
| 5 | Documentation & clarity | ✅ PASS  /  ❌ FAIL |
| 6 | Licensing & IP | ✅ PASS  /  ❌ FAIL |
| 7 | Ethics & compliance | ✅ PASS  /  ❌ FAIL |

**Pass/fail rule per category:** a category is PASS if its severity is `info` or `minor`. It is FAIL if any finding in that category is `major` or `blocker`. This is binary by design — the detailed severity is in the per-dimension section below for reviewers who need it, but the contributor sees pass/fail.

## Proposal alignment

| Aspect | Status |
|---|---|
| Delivered as proposed | <short summary> |
| Under-delivered (promised but missing/smaller) | <list, or "none"> |
| Added beyond proposal (must be documented in data card) | <list, or "none"> |
| Accepted carve-outs honored | <list, or "none"> |

## Feedback for the contributor

One short paragraph (3–5 sentences) per FAILED category, addressed *to the contributor*, second person, plain language. State what's wrong, why it matters, and the concrete fix. No jargon the contributor wouldn't already know. No restating the persona. No throat-clearing ("Thank you for your submission…").

For PASSED categories: one sentence acknowledging it, only if there's something noteworthy. Most PASSED categories get no feedback paragraph.

Example feedback paragraphs:

> **3. Metadata sufficiency — FAIL.** The zea file is missing the speed-of-sound value used during acquisition, which means a downstream user can't reproduce your beamforming. Add `scan/sound_speed` (m/s) as a top-level attribute, or document it in the data card under "Acquisition system". Also worth double-checking: your sampling rate is recorded as 25 MHz but your center frequency is 7.5 MHz — that's only ~3.3× Nyquist; please confirm this is intentional rather than a unit error.

> **6. Licensing & IP — FAIL.** Your data card says "released for academic research" — this is incompatible with CC BY 4.0, which OpenH-RF requires and which explicitly permits commercial use. Please confirm with your institution's legal team that you can release under CC BY 4.0, then update the License section to state that explicitly. If you cannot, the submission can't be accepted under the current RFP.

## Per-dimension findings (detail for reviewers)

### 1. Format compliance
**Status:** pass | pass_with_notes | fail | blocked
**Severity:** info | minor | major | blocker
**Findings:**
- ...
**Evidence:**
- ...
**Suggested fixes:**
- ...

[repeat for each dimension]

## Auto-fixes applied
- [list of changes made, with file paths]

## Action items for the contributor
- [ordered list, blockers first, copy from feedback paragraphs above]

## Reference reconstruction
[Embedded B-mode image(s) produced by the pipeline check]
```

The verdict rule:
- Any category FAILS with `blocker` severity → **Reject — needs resubmission**
- Any category FAILS with `major` severity → **Accept with revisions**
- All categories PASS → **Accept**

## Writing the contributor feedback paragraphs

The feedback paragraphs are the most-read part of the report. Get them right.

**Voice.** Address the contributor as "you". The data is "your dataset", "your pipeline", "your data card". This is a colleague-to-colleague tone — not formal, not breezy.

**Structure each paragraph as:** (1) what's wrong, in one sentence; (2) why it matters for downstream users or for acceptance, in one sentence; (3) the concrete fix, in one to two sentences. If there are multiple problems in the category, pick the one or two most consequential — don't enumerate every minor issue here (those live in the per-dimension findings below).

**Plain language.** "Your pipeline crashes when the third frame is loaded because the channel-data array is rank-3 instead of rank-4" is good. "Tensor rank mismatch in axis enumeration of the channel acquisition manifold" is bad.

**No persona artifacts.** The compliance officer, the reproducibility reviewer, the imaging engineer — those are framings for the sub-agents, not voices the contributor should see. Feedback paragraphs are written in a single, neutral voice.

**Length.** 3–5 sentences. If you find yourself writing more, you're listing minor findings that should stay in the per-dimension section.

### Step 5: Hand back the report and the auto-fixed artifacts

Place the report next to the submission. If you auto-fixed anything, place those files in an `autofix/` subdirectory alongside the report so the contributor can see exactly what was added.

## Important judgment calls

**"Novice user" means.** A graduate student in medical imaging who has not spoken to the contributor and is reading the data card and pipeline cold. Not a complete beginner — they know what beamforming is. The bar is: can they reconstruct a B-mode image and understand what the data is for, from the artifacts alone, without asking questions.

**Tier weighting is not your problem.** The RFP weights in-vivo human data x100 vs phantom x1, but that's for acceptance-priority decisions at the steering-group level. You evaluate quality and completeness regardless of tier. Note the tier in the report but don't let it change the bar.

**Be specific in findings.** "Data card incomplete" is useless. "Data card section 'Subject Metadata' is empty; spec requires aggregate counts of subjects, age range, sex distribution, and probe model" is actionable. Every finding should be specific enough that the contributor knows exactly what to change.

**Don't reject for stylistic issues.** Markdown formatting, prose quality in the description, choice of variable names in the pipeline — note these as `info`, never `major`. The bar is technical correctness and completeness, not polish.

**When in doubt about scope.** If the submission claims a task not in RFP sections 6.1–6.6, that's `info`, not a failure — the RFP welcomes novel applications. Flag it for steering-group review.
