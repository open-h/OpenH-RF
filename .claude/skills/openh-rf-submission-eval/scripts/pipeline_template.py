"""
B-mode reconstruction pipeline template for OpenH-RF submissions.

Used by the openh-rf-submission-eval skill when a submission is missing
its reconstruction script. Fill in / adjust the operations as needed, then
run against the submission's zea file.

The default zea B-mode pipeline is:

    Cast -> ApplyWindow -> Demodulate -> Beamform(PatchedGrid(TOFCorrection -> DelayAndSum) -> ReshapeGrid) -> EnvelopeDetect -> Normalize -> LogCompress

Obtained via ``zea.Pipeline.from_default()``. Key notes:
- Cast(dtype="float32"): most acquisitions store raw_data as int16; this cast
  is required before any float operations.
- Demodulate: pass-through for IQ data (n_ch=2), required for RF data (n_ch=1).
  Demodulating before beamforming gives faster processing and better envelope
  detection. Including it makes the pipeline work correctly for both modalities.

This default pipeline is a useful starting point, but submitters will often need
to make adjustments for their specific data or use case — different beamformers,
custom grid parameters, additional pre/post-processing, etc. zea.Pipeline is
flexible: any sequence of operations is valid as long as the output is a 2D
log-compressed B-mode image. Submitters supply one pipeline.yaml per track in
their file (in practice, most submissions are single-track and have exactly one).

Minimum required zea version: v0.1.0a3 (stored as ``zea_version`` in the HDF5
file). Files written with v0.1.0a2 or earlier are not eligible for OpenH-RF.

The working pattern is:

    with zea.File(str(zea_path)) as f:
        parameters = f.load_parameters()
        raw = f.data.raw_data[:]

    pipeline = zea.Pipeline.from_default()         # or Pipeline.from_path("pipeline.yaml")
    inputs   = pipeline.prepare_parameters(parameters)
    outputs  = pipeline(**{pipeline.key: raw}, **inputs, return_numpy=True)
    image    = outputs[pipeline.output_key][frame_index]  # 2D float, log-compressed dB

Canonical pipeline docs: https://zea.readthedocs.io/en/openh-rf-latest/pipeline.html
"""  # noqa: E501

import os
from pathlib import Path

import numpy as np

# Default to the jax backend (installed by `uv sync`) before importing zea.
os.environ.setdefault("KERAS_BACKEND", "jax")

import zea


def build_pipeline() -> zea.Pipeline:
    """Return the default zea B-mode pipeline.

    Uses Pipeline.from_default() which produces:
        Cast -> ApplyWindow -> Demodulate -> Beamform(...)
        -> EnvelopeDetect -> Normalize -> LogCompress

    Adjust operations as needed for your specific data or use case.
    """
    return zea.Pipeline.from_default()


def reconstruct(
    zea_path: Path,
    frame_index: int = 0,
    pipeline: "zea.Pipeline | None" = None,
) -> np.ndarray:
    """Reconstruct a single B-mode frame from a zea file.

    Returns a 2D float array (log-compressed dB, typically in [-60, 0]).
    """
    zea.init_device()
    with zea.File(str(zea_path)) as f:
        # load_parameters merges scan + probe and derives the reconstruction
        # grid from the file (single-track file; for multi-track use
        # f.tracks[i].load_parameters() / f.tracks[i].data.raw_data).
        parameters = f.load_parameters()
        raw = f.data.raw_data[:]

    pipeline = pipeline or build_pipeline()
    inputs = pipeline.prepare_parameters(parameters)
    # return_numpy=True uses keras.ops.convert_to_numpy for multi-backend support.
    outputs = pipeline(**{pipeline.key: raw}, **inputs, return_numpy=True)
    return outputs[pipeline.output_key][frame_index]


if __name__ == "__main__":
    import argparse

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    parser = argparse.ArgumentParser()
    parser.add_argument("zea_file", type=Path, help="Path to the .hdf5 zea file")
    parser.add_argument("--frame", type=int, default=0, help="Frame index (default: 0)")
    parser.add_argument("--out", type=Path, default=Path("reference_bmode.png"))
    parser.add_argument(
        "--save-yaml",
        type=Path,
        default=None,
        help="Optionally write the pipeline to a reusable pipeline.yaml",
    )
    args = parser.parse_args()

    pipe = build_pipeline()
    if args.save_yaml is not None:
        pipe.to_yaml(str(args.save_yaml))
        print(f"Saved pipeline to {args.save_yaml}")

    bmode = reconstruct(args.zea_file, frame_index=args.frame, pipeline=pipe)

    fig, ax = plt.subplots(figsize=(6, 8))
    ax.imshow(bmode, cmap="gray", vmin=-60, vmax=0, aspect="auto")
    ax.set_title(f"B-mode reconstruction — frame {args.frame}")
    ax.set_xlabel("Lateral")
    ax.set_ylabel("Axial (depth)")
    fig.colorbar(ax.images[0], ax=ax, label="dB")
    fig.tight_layout()
    fig.savefig(args.out, dpi=150, bbox_inches="tight")
    print(f"Saved reconstruction to {args.out}")
