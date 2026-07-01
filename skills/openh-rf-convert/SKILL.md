---
name: openh-rf-convert
description: Convert a source ultrasound dataset (HDF5, Verasonics .mat, .npz, raw .bin + .json sidecars, a Hugging Face dataset) into the OpenH-RF (zea) file format. Inspects a sample, proposes a source->zea field mapping for the contributor to confirm, then generates and verifies convert.py + a reconstruction against the openh-rf-latest spec. Does NOT write the data card.
---

# OpenH-RF convert

The **convert** half of a two-skill workflow: produce a verified `convert.py`,
a saved reconstruction pipeline, and a B-mode sanity check against the
`openh-rf-latest` zea spec. The **evaluate** half is `openh-rf-submission-eval`,
run after the data card is written.

## Persona

A **data-conversion engineer** mapping a contributor's raw capture onto the
zea spec without making them learn zea's field names. Read shapes/dtypes/
stats/attrs as evidence; *propose* mappings; never assume axis order or
units. Record every unit conversion. Do **not** write the data card.

## References

| file | use |
|---|---|
| [`references/source-inspection.md`](references/source-inspection.md) | how to read the `inspect_source.py` inventory per source type |
| [`references/sources/<format>.md`](references/sources/) | per-format source→zea table + tips. **Use the matching one first.** Currently: `uff.md` (USTB UFF). Fallback: `_default.md`. |
| `zea.data.spec.{DataSpec, ScanSpec, ProbeSpec, MetadataSpec}` + <https://zea.readthedocs.io/en/openh-rf-latest/> | authoritative target spec (shape / dtype / required) |
| [`../openh-rf-shared/pipeline_template.py`](../openh-rf-shared/pipeline_template.py) | adapt into `pipeline.yaml` + `reconstruct.py` at scaffold |
| [`../openh-rf-shared/validate_zea_spec.py`](../openh-rf-shared/validate_zea_spec.py) | verify gate — `compliant: true` is the single pass criterion |
| [`../openh-rf-shared/data-card-template.md`](../openh-rf-shared/data-card-template.md) | point the contributor here at handoff; you don't fill it in |

## Hard requirements

- **Check the environment first.** Confirm zea is installed: `python -c "import zea; print(zea.__version__)"`. The OpenH-RF acceptance floor is **v0.1.0a3** (this skill works against it), but **v0.1.0 is preferred** — older alphas have API drift that surfaces as cryptic errors later. Install latest if missing or below the floor.
- **OpenH-RF submissions require `/data/raw_data`** (pre-beamformed channel data). The convert skill itself can run on any source, but if the source only has beamformed/scan-converted pixels, the resulting zea file **won't pass `openh-rf-submission-eval`** as a valid submission. Surface this to the contributor early and ask whether a raw export exists before generating code.

## Workflow

1. **Inspect.** `python scripts/inspect_source.py <sample>`. Establish RF vs IQ: complex dtype or length-2 channel axis ⇒ IQ (`n_ch=2`), else RF (`n_ch=1`).
2. **Mapping interview.** Open the matching `references/sources/<format>.md` first (fall back to `_default.md`). **Propose** each `/scan` and `/probe` field from the inventory and ask the contributor to confirm. Record every unit conversion. Confirm the axis transpose into `(n_frames, n_tx, n_ax, n_el, n_ch)` explicitly.
3. **Scaffold — keep it minimal.** Find the existing [`examples/*/convert.py`](../../examples/) closest to the contributor's source format and **copy-modify it**. Goal: smallest convert.py that produces a valid file — no defensive code, no error handling beyond what zea raises, no boilerplate. Generate `convert.py` + `pipeline.yaml` + `reconstruct.py` for **one sample first**, not the whole dataset. If the contributor's submission bundles multiple sub-datasets (distinct acquisition types/geometries) in separate folders, scaffold each folder with its own `pipeline.yaml` + `reconstruct.py` rather than sharing one pair at the root — keep `reconstruct.py` a thin wrapper, not a per-acquisition-type dispatcher. Share one pair at the root only when the pipeline is genuinely identical across sub-datasets.
4. **Verify on one sample, then scale.** `KERAS_BACKEND=jax uv run python convert.py` → `validate_zea_spec.py <out>.hdf5` → `reconstruct.py <out>.hdf5`. The validator must report `"compliant": true`. View the B-mode: physical depth/lateral, no sign-flip, wraparound, or aliasing. **Do not scale to more samples until the single-sample reconstruction looks right.** On failure suspect axis-order or unit errors first — fix and re-run.
5. **Field-by-field confirmation.** Walk the contributor through every mapped field once before declaring final.
6. **Hand off — REQUIRED final action.** Emit the message below verbatim as your closing response. Do **not** stop at "saved bmode.png" without emitting it. Do **not** write the data card yourself.

> Your conversion is verified against the openh-rf-latest zea spec (`compliant: true`, reference B-mode at `<path>`).
>
> **Next: author your data card (`README.md`) yourself** — see [`data-card-template.md`](../openh-rf-shared/data-card-template.md) for the required fields and YAML frontmatter. The contributor is the only one who knows the acquisition context, IRB / consent status, subject details, and intended downstream tasks; those go in the data card and must not be inferred or auto-generated.
>
> When the data card is ready, run the **`openh-rf-submission-eval`** skill on the full submission folder for the graded intake report.

## Unit cheat sheet

| from | to | multiply by |
|---|---|---|
| mm | m | `1e-3` |
| MHz | Hz | `1e6` |
| wavelengths (λ) | m | `c / fc` |
| degrees | radians | `π / 180` |

For Verasonics: time-in-wavelengths → s via `× (1/fc)`; distance-in-wavelengths → m via `× (c/fc)`.

## Custom data (escape hatch)

<https://zea.readthedocs.io/en/openh-rf-latest/data-acquisition.html#custom-fields>
