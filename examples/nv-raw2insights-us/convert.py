# SPDX-License-Identifier: Apache-2.0
"""Stream one sample from the public NV-Raw2Insights-US dataset and convert
to openh-rf HDF5 via File.create.

Source: https://huggingface.co/datasets/nvidia/NV-Raw2Insights-US

This is an *example* helper: it shows how the published HF dataset maps onto the
openh-rf (zea) file format. A submission's required files are the .hdf5 data,
reconstruct.py, pipeline.yaml, README.md and LICENSE; this converter is not part
of that set. It is reproducible without a local copy -- `datasets` streams a
single example from the remote parquet shards.

Usage:
    python examples/nv-raw2insights-us/convert.py

Note:
    Requires `datasets` library (`pip install datasets`)

"""

import argparse
import os
from pathlib import Path

# Default to the jax backend (installed by `uv sync`) so the script runs under a
# bare `uv run` without first exporting KERAS_BACKEND. An explicit value wins.
os.environ.setdefault("KERAS_BACKEND", "jax")

import numpy as np
from datasets import load_dataset
from zea import File
from zea.display import to_8bit
from zea.func.ultrasound import log_compress

HF_REPO = "nvidia/NV-Raw2Insights-US"
DEFAULT_OUTPUT = Path("nv_raw2insights_us_sample.hdf5")


def bmode_to_uint8(bmode: np.ndarray, dynamic_range_db: float = 60.0) -> np.ndarray:
    env = np.abs(bmode)
    return to_8bit(
        log_compress(env / env.max()),
        dynamic_range=(-dynamic_range_db, 0),
        pillow=False,
    )


def extent_to_openh(ext: np.ndarray, scale: float) -> np.ndarray:
    """[x_min, x_max, z_max, z_min] -> openh-rf [xmin, xmax, 0, 0, zmin, zmax]."""
    x_min, x_max, z_max, z_min = np.asarray(ext, dtype=np.float64) * scale
    return np.array([x_min, x_max, 0.0, 0.0, z_min, z_max], dtype=np.float32)


def convert_sample(sample: dict, output_path: Path) -> None:
    iq_real = np.asarray(sample["iq_real"], dtype=np.float32)
    iq_imag = np.asarray(sample["iq_imag"], dtype=np.float32)
    bmode = np.asarray(sample["bmode"], dtype=np.float32)
    bmode_focused = np.asarray(sample["bmode_focused"], dtype=np.float32)
    sos_map = np.asarray(sample["sound_speed_map"], dtype=np.float32)
    seg_map = np.asarray(sample["segmentation_map"], dtype=np.uint8)
    elpos = np.asarray(sample["elpos"], dtype=np.float32)

    n_tx, n_el, _ = iq_real.shape

    raw_iq = np.stack([iq_real, iq_imag], axis=-1)
    raw_data = np.transpose(raw_iq, (1, 2, 0, 3))[
        np.newaxis
    ]  # [1, n_tx, n_ax, n_el, 2]

    probe_geometry = elpos.T
    bmode_extent = extent_to_openh(sample["bmode_extent"], scale=1e-3)
    sos_extent = extent_to_openh(sample["sound_speed_extent"], scale=1.0)

    bmode_values = bmode_to_uint8(bmode)[np.newaxis]
    bmode_focused_values = bmode_to_uint8(bmode_focused)[np.newaxis]
    sos_values = sos_map[np.newaxis]
    seg_values = np.stack([seg_map == 0, seg_map == 1], axis=-1)[
        np.newaxis, :, :, np.newaxis, :
    ]

    data = {
        "raw_data": raw_data,
        "image": {
            "values": bmode_values,
            "extent": bmode_extent,
            "description": "B-mode (DAS, c=1540 m/s)",
        },
        "bmode_focused": {
            "values": bmode_focused_values,
            "extent": bmode_extent,
            "description": "B-mode (DBUA aberration-corrected)",
        },
        "sos_map": {
            "values": sos_values,
            "extent": sos_extent,
            "unit": "m/s",
        },
        "segmentation": {
            "values": seg_values,
            "labels": np.array(["background", "inclusion"], dtype=np.str_),
            "extent": bmode_extent,
        },
    }

    scan = {
        "probe_geometry": probe_geometry,
        "sampling_frequency": float(sample["fs"]),
        "center_frequency": float(sample["fc"]),
        "demodulation_frequency": float(sample["fd"]),
        "initial_times": np.full(n_tx, float(sample["t0"]), dtype=np.float32),
        "t0_delays": np.zeros((n_tx, n_el), dtype=np.float32),
        "tx_apodizations": np.eye(n_tx, n_el, dtype=np.float32),
        "focus_distances": np.zeros(n_tx, dtype=np.float32),
        "transmit_origins": probe_geometry,
        "polar_angles": np.zeros(n_tx, dtype=np.float32),
        "azimuth_angles": np.zeros(n_tx, dtype=np.float32),
        "sound_speed": float(sample["c0"]),
    }

    metadata = {
        "subject": {"type": "phantom"},
        "credit": "NV-Raw2Insights-US — NVIDIA (CC-BY-4.0)",
        "annotations": {
            "anatomy": "phantom",
            "label": np.array(["simulation"], dtype=np.str_),
        },
    }

    metrics = {
        "common_midpoint_phase_error": np.array(
            [float(sample["phase_error"])], dtype=np.float32
        ),
    }

    File.create(
        str(output_path),
        data=data,
        scan=scan,
        metadata=metadata,
        metrics=metrics,
        probe_name="Simulated 10L4 Transducer",
        description="NV-Raw2Insights-US FSA phantom simulation (simulated in k-Wave)",
        overwrite=True,
    ).close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--split", default="validation", choices=["train", "validation"]
    )
    parser.add_argument(
        "--index", type=int, default=0, help="Which streamed sample to take"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    print(f"Streaming {HF_REPO} [{args.split}], taking sample {args.index}...")
    ds = load_dataset(HF_REPO, split=args.split, streaming=True)
    sample = next(iter(ds.skip(args.index)))

    print(f"Writing {args.output}...")
    convert_sample(sample, args.output)
    print(f"Done. {args.output} ({args.output.stat().st_size / 1e6:.1f} MB)")

    with File(str(args.output)) as f:
        print(f"Data keys: {list(f.data)}")
        print(f"Scan parameters: {f.scan()}")
        print(f"Metadata: {f.metadata()}")
        print(f"Metrics: {f.metrics()}")


if __name__ == "__main__":
    main()
