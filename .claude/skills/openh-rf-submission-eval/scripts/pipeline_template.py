"""
B-mode reconstruction pipeline template for OpenH-RF submissions.

Used by the openh-rf-submission-eval skill when a submission is missing
its reconstruction script. Fill in / adjust the operations as needed, then
run against the submission's zea file.

Standard chain:
    raw channel data -> DAS beamforming -> envelope detection -> normalize -> log compression

The canonical Pipeline docs are at
https://zea.readthedocs.io/en/openh-rf-latest/pipeline.html — but note that the
working pattern is:

    pipeline = zea.Pipeline(operations=[...])           # or Pipeline.from_path("pipeline.yaml")
    params   = pipeline.prepare_parameters(probe, scan) # geometry/grid from the file
    outputs  = pipeline(**{pipeline.key: raw}, **params)
    image    = keras.ops.convert_to_numpy(outputs[pipeline.output_key])[frame]
"""

import os
from pathlib import Path

# Default to the jax backend (installed by `uv sync`) before importing keras/zea.
os.environ.setdefault("KERAS_BACKEND", "jax")

import keras
import numpy as np
import zea
from zea.ops import Beamform, EnvelopeDetect, LogCompress, Normalize


def build_pipeline() -> "zea.Pipeline":
    """Construct a default DAS -> envelope -> normalize -> log-compress pipeline.

    The operations are geometry-agnostic; per-acquisition parameters (probe
    geometry, sound speed, sampling frequency, transmit sequence, grid) are
    derived from the zea file at run time via ``prepare_parameters`` — this is
    what makes the pipeline portable across submissions.
    """
    return zea.Pipeline(
        operations=[
            Beamform(
                beamformer="delay_and_sum",
                num_patches=200,  # raise if you hit out-of-memory during beamforming
            ),
            EnvelopeDetect(),
            Normalize(),
            LogCompress(),
        ]
    )


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
        probe = f.probe()
        scan = f.scan()
        raw = f.data.raw_data[:]

    pipeline = pipeline or build_pipeline()
    params = pipeline.prepare_parameters(probe, scan)
    outputs = pipeline(**{pipeline.key: raw}, **params)
    return keras.ops.convert_to_numpy(outputs[pipeline.output_key])[frame_index]


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
