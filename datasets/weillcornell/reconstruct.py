#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Example reconstruction script for the weillcornell dataset of OpenH-RF.

Dataset link: https://huggingface.co/datasets/nvidia/OpenH-RF/tree/main/weillcornell

B-mode reconstruction of plane-wave channel data with its embedded QUS targets.

The acquisition is one normal-incidence plane wave per frame. Alongside the
B-mode, the embedded QUS targets (BSC, Nakagami) for the same frame are printed.

Requires zea>=0.1.6 (https://github.com/tue-bmd/zea), the library that does the
ultrasound processing here, together with one of its Keras backends (JAX,
PyTorch or TensorFlow). Installation instructions are at
https://zea.readthedocs.io/en/latest/installation.html.

Usage:
    python reconstruct.py
"""

import os

os.environ.setdefault("KERAS_BACKEND", "jax")
os.environ.setdefault("MPLBACKEND", "Agg")


from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import zea
from mpl_toolkits.axes_grid1 import make_axes_locatable
from zea import Config, File, Pipeline
from zea.ops import Beamform, Cast, Demodulate, EnvelopeDetect, LogCompress, Normalize

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "pipeline.yaml"

# Common shallow reference grid used for every acquisition, with isotropic
# ~0.073 mm (~lambda/4) pixels so the image keeps its physical aspect ratio.
PARAMETERS = {
    "grid_size_x": 600,
    "grid_size_z": 301,
    "xlims": [-0.021965, 0.021965],
    "zlims": [0.0029568189236411113, 0.02498497892364108],
    "dynamic_range": [-60, 0],
}

# --- Inputs -----------------------------------------------------------------
# Defaults stream straight from the published corpus. Swap any of these for a
# local path to run against your own copy.
ZEA_FILE = "hf://nvidia/OpenH-RF/weillcornell/data/ac10_15m_SK.hdf5"
OUT = HERE / "assets" / "ac10_15m_SK_pipeline.png"
HF_CONFIG = "hf://nvidia/OpenH-RF/weillcornell/pipeline.yaml"
FRAME = 0  # Frame index to reconstruct
DEVICE = None  # Optional zea device, e.g. cpu, cuda:0, auto:0


def build_pipeline() -> Pipeline:
    """Define the delay-and-sum B-mode pipeline in code."""
    return Pipeline(
        operations=[
            Cast(dtype="float32"),
            Demodulate(),
            Beamform(beamformer="delay_and_sum"),
            EnvelopeDetect(),
            Normalize(output_range=[0.0, 1.0]),
            LogCompress(),
        ],
    )


def write_config(pipeline: Pipeline, path: Path) -> None:
    """Serialize the pipeline and reconstruction parameters to pipeline.yaml."""
    config = pipeline.to_config()
    config["parameters"] = PARAMETERS
    config.to_yaml(str(path))


def reconstruct_one(
    zea_file: Path, config: Config, frame: int, device: str | None
) -> tuple[np.ndarray, object]:
    zea.init_device(device=device, verbose=False)
    pipeline = Pipeline.from_config(config)

    with File(str(zea_file)) as f:
        frame_count = f.data.raw_data.shape[0]
        if not 0 <= frame < frame_count:
            raise ValueError(f"FRAME must be in [0, {frame_count - 1}]")
        parameters = f.load_parameters(**config.parameters)
        raw = f.data.raw_data[frame : frame + 1]

    inputs = pipeline.prepare_parameters(parameters)
    outputs = pipeline(data=raw, **inputs, return_numpy=True)
    bmode = np.asarray(outputs["data"][0])
    return bmode, parameters


def save_png(image_db: np.ndarray, parameters, out_path: Path, title: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    extent_mm = [float(v) * 1e3 for v in parameters.extent_imshow]
    fov_ratio = abs(extent_mm[2] - extent_mm[3]) / abs(extent_mm[1] - extent_mm[0])
    zea.visualize.set_mpl_style()
    fig, ax = plt.subplots(figsize=(6.2, 2.0 + 4.8 * fov_ratio), constrained_layout=True)
    im = ax.imshow(
        image_db,
        cmap="gray",
        vmin=float(parameters.dynamic_range[0]),
        vmax=float(parameters.dynamic_range[1]),
        extent=extent_mm,
        aspect="equal",
    )
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("Lateral position (mm)")
    ax.set_ylabel("Axial depth (mm)")
    cax = make_axes_locatable(ax).append_axes("right", size="5%", pad=0.05)
    cbar = fig.colorbar(im, cax=cax)
    cbar.set_label("Envelope (dB)")
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def correlation(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.float64).ravel()
    right = np.asarray(right, dtype=np.float64).ravel()
    finite = np.isfinite(left) & np.isfinite(right)
    left = left[finite]
    right = right[finite]
    if left.size < 2 or np.std(left) == 0.0 or np.std(right) == 0.0:
        return float("nan")
    return float(np.corrcoef(left, right)[0, 1])


def summarize_qus(zea_file: Path, frame: int) -> None:
    with File(str(zea_file)) as file:
        data = file.data
        raw_frame = data.raw_data[frame, 0, :, :, 0]
        bsc = data.theoretical_bsc.values[frame]
        frequency_labels = data.theoretical_bsc.labels[...]
        frequencies_hz = np.asarray(
            [float(label.removeprefix("frequency_hz=")) for label in frequency_labels]
        )
        m_frame = data.nakagami_m_per_frame.values[frame]
        m_pooled = data.nakagami_m_pooled.values[frame]
        omega_frame = data.nakagami_omega_per_frame.values[frame]
        omega_pooled = data.nakagami_omega_pooled.values[frame]
        coordinates_shape = data.nakagami_m_pooled.coordinates.shape
        bsc_unit = data.theoretical_bsc.unit[()]
        m_unit = data.nakagami_m_pooled.unit[()]
        omega_unit = data.nakagami_omega_pooled.unit[()]

    print("QUS targets")
    print(f"  RF frame       : shape={raw_frame.shape}, dtype={raw_frame.dtype}")
    print(f"  QUS grid       : shape={m_pooled.shape}, coordinates={coordinates_shape} [x,y,z] m")
    print(
        f"  Theoretical BSC: shape={bsc.shape}, unit={bsc_unit}, "
        f"band={frequencies_hz[0] * 1e-6:.6f}-{frequencies_hz[-1] * 1e-6:.6f} MHz"
    )

    for name, direct, pooled, unit in (
        ("Nakagami m", m_frame, m_pooled, m_unit),
        ("Nakagami omega", omega_frame, omega_pooled, omega_unit),
    ):
        error = direct - pooled
        print(
            f"  {name:<15}: unit={unit}, frame-to-pooled "
            f"MAE={np.mean(np.abs(error)):.6g}, "
            f"RMSE={np.sqrt(np.mean(error**2)):.6g}, "
            f"correlation={correlation(direct, pooled):.6f}"
        )


def main():
    # Define the beamforming pipeline in code, save it (with the reconstruction
    # parameters) to pipeline.yaml, then load that YAML back in.
    write_config(build_pipeline(), CONFIG)
    config = Config.from_path(str(CONFIG))

    image_db, parameters = reconstruct_one(ZEA_FILE, config, FRAME, DEVICE)
    save_png(image_db, parameters, OUT, f"{Path(ZEA_FILE).stem}, frame {FRAME}")

    print(f"Input          : {ZEA_FILE}")
    print(f"Pipeline       : {CONFIG}")
    print(f"Output         : {OUT}")
    print(
        f"Reconstruction : shape={image_db.shape}, "
        f"min={float(np.nanmin(image_db)):.2f}, "
        f"max={float(np.nanmax(image_db)):.2f}"
    )
    summarize_qus(ZEA_FILE, FRAME)


if __name__ == "__main__":
    main()
