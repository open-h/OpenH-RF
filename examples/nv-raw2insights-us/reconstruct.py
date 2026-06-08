# SPDX-License-Identifier: Apache-2.0
"""Beamform an openh-rf HDF5 sample produced by convert.py.

Shows how to go from raw channel data to a B-mode entirely in code with zea:
build the acquisition parameters and the DAS -> envelope -> normalize ->
log-compress pipeline inline, beamform `raw_data`, and render a 7-panel figure
(IQ magnitude, stored DAS B-mode, stored DBUA B-mode, zea-reconstructed B-mode,
speed-of-sound map, zea SoS-corrected B-mode, segmentation overlay). The pipeline
is also saved to pipeline.yaml as a shareable artifact, but nothing here loads it.

This is the reference reconstruction / data-validation script for the
submission: it reproduces a representative B-mode from the raw channel data,
confirming the acquisition parameters and geometry are recorded correctly.

Usage:
    python examples/nv-raw2insights-us/reconstruct.py \
        --input nv_raw2insights_us_sample.hdf5
"""

import argparse
import os
from pathlib import Path

# Default to the jax backend (installed by `uv sync`) so the script runs under a
# bare `uv run` without first exporting KERAS_BACKEND. An explicit value wins.
os.environ.setdefault("KERAS_BACKEND", "jax")

import keras
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import zea
from zea.ops import Beamform, EnvelopeDetect, LogCompress, Normalize

HERE = Path(__file__).parent
DEFAULT_INPUT = Path("nv_raw2insights_us_sample.hdf5")
DEFAULT_OUTPUT = Path("nv_raw2insights_us_reconstructed.png")
DEFAULT_PIPELINE = HERE / "pipeline.yaml"


def coords_to_imshow_mm(coords):
    """openh-rf per-pixel coordinates (z, x, 3), last axis [x, y, z] in metres
    -> mpl imshow extent [left, right, bottom, top] in mm."""
    x = coords[..., 0]
    z = coords[..., 2]
    return [x.min() * 1e3, x.max() * 1e3, z.max() * 1e3, z.min() * 1e3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--pipeline",
        type=Path,
        default=DEFAULT_PIPELINE,
        help="Path to write the saved pipeline recipe (YAML)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"{args.input} not found. Run convert.py first.")

    zea.init_device()

    with zea.File(str(args.input)) as f:
        raw = f.data.raw_data[:]
        img = f.data.image.values[:]
        img_coords = f.data.image.coordinates[:]
        focused = f.data.bmode_focused.values[:]
        focused_coords = f.data.bmode_focused.coordinates[:]
        sos = f.data.sos_map.values[:]
        sos_coords = f.data.sos_map.coordinates[:]
        seg = f.data.segmentation.values[:]
        labels = f.data.segmentation.labels.asstr()[:]
        phase_err = f.metrics.common_midpoint_phase_error

        # Acquisition parameters straight from the file. We only override the
        # reconstruction grid, derived from the stored B-mode's coordinates so
        # the result lines up with it (no hard-coded numbers, no config file).
        nz, nx = img_coords.shape[0], img_coords.shape[1]
        params = f.load_parameters(
            grid_size_x=nx,
            grid_size_z=nz,
            xlims=[float(img_coords[..., 0].min()), float(img_coords[..., 0].max())],
            zlims=[float(img_coords[..., 2].min()), float(img_coords[..., 2].max())],
            n_ch=raw.shape[-1],          # 2 = baseband IQ
            selected_transmits="all",
        )

    print(f"raw_data: {raw.shape}")

    # The reconstruction pipeline, defined in code (DAS -> envelope -> normalize
    # -> log-compress). Saved to pipeline.yaml as a shareable recipe.
    pipeline = zea.Pipeline(
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
    pipeline.to_yaml(str(args.pipeline))
    print(f"Saved pipeline recipe to {args.pipeline}")

    inputs = pipeline.prepare_parameters(params)
    # keras.ops.convert_to_numpy (not np.array) so the output tensor is pulled
    # off the device regardless of backend — e.g. PyTorch needs an explicit
    # .cpu(), which np.array would not do.
    recon = keras.ops.convert_to_numpy(pipeline(data=raw, **inputs)["data"])[0]
    # The reconstruction grid was derived from img_coords above, so its mpl
    # extent equals coords_to_imshow_mm(img_coords) — params.extent_imshow is
    # just the same thing zea already computed for us.
    recon_ext = [v * 1e3 for v in params.extent_imshow]  # metres -> mm
    print(f"Reconstructed: {recon.shape}")

    # SoS-corrected reconstruction: feed the ground-truth sound-speed map (on its
    # own coarser grid) to the beamformer's heterogeneous-medium mode. This is
    # valid here because the acquisition is full synthetic aperture (multistatic).
    sos_frame = sos[0] if sos.ndim == 3 else sos[0, :, :, 0]
    sos_grid_x = np.ascontiguousarray(sos_coords[0, :, 0], dtype=np.float32)
    sos_grid_z = np.ascontiguousarray(sos_coords[:, 0, 2], dtype=np.float32)
    recon_sos = keras.ops.convert_to_numpy(
        pipeline(
            data=raw,
            sos_map=sos_frame,
            sos_grid_x=sos_grid_x,
            sos_grid_z=sos_grid_z,
            **inputs,
        )["data"]
    )[0]
    print(f"Reconstructed with SoS correction: {recon_sos.shape}")

    fig, axes = plt.subplots(1, 7, figsize=(30, 5))

    # 1: IQ magnitude for one transmit event, in dB
    tx_idx = raw.shape[1] // 2
    iq = raw[0, tx_idx, :, :, 0] + 1j * raw[0, tx_idx, :, :, 1]
    iq_db = 20 * np.log10(np.abs(iq) / np.abs(iq).max() + 1e-10)
    axes[0].imshow(iq_db, aspect="auto", cmap="gray", vmin=-80, vmax=0)
    axes[0].set_title(f"IQ magnitude (tx {tx_idx}) [dB]\nraw_data: {raw.shape}")
    axes[0].set_xlabel("Element")
    axes[0].set_ylabel("Axial sample")

    # 2: Stored B-mode (DAS)
    axes[1].imshow(
        img[0], aspect="auto", cmap="gray", extent=coords_to_imshow_mm(img_coords)
    )
    axes[1].set_title(f"B-mode (DAS, stored)\nimage: {img.shape}")
    axes[1].set_xlabel("Lateral [mm]")
    axes[1].set_ylabel("Depth [mm]")

    # 3: Stored DBUA
    axes[2].imshow(
        focused[0], aspect="auto", cmap="gray", extent=coords_to_imshow_mm(focused_coords)
    )
    axes[2].set_title(f"B-mode (DBUA, stored)\nbmode_focused: {focused.shape}")
    axes[2].set_xlabel("Lateral [mm]")
    axes[2].set_ylabel("Depth [mm]")

    # 4: zea-reconstructed B-mode (DAS pipeline on raw_data)
    axes[3].imshow(
        recon, aspect="auto", cmap="gray", vmin=-60, vmax=0, extent=recon_ext
    )
    axes[3].set_title(f"B-mode (DAS, zea)\nreconstructed: {recon.shape}")
    axes[3].set_xlabel("Lateral [mm]")
    axes[3].set_ylabel("Depth [mm]")

    # 5: SOS map
    im = axes[4].imshow(
        sos[0], aspect="auto", cmap="hot", extent=coords_to_imshow_mm(sos_coords)
    )
    plt.colorbar(im, ax=axes[4], label="m/s")
    axes[4].set_title(f"Speed of sound\nsos_map: {sos.shape}")
    axes[4].set_xlabel("Lateral [mm]")
    axes[4].set_ylabel("Depth [mm]")

    # 6: zea-reconstructed B-mode with SoS correction
    axes[5].imshow(
        recon_sos, aspect="auto", cmap="gray", vmin=-60, vmax=0, extent=recon_ext
    )
    axes[5].set_title(f"B-mode (DAS + SoS, zea)\nreconstructed: {recon_sos.shape}")
    axes[5].set_xlabel("Lateral [mm]")
    axes[5].set_ylabel("Depth [mm]")

    # 7: Segmentation overlaid on focused (DBUA) B-mode
    axes[6].imshow(
        focused[0], aspect="auto", cmap="gray", extent=coords_to_imshow_mm(focused_coords)
    )
    # seg is (n_frames, z, x, n_labels); pick the "inclusion" channel by name
    # rather than a hard-coded index, so it stays correct if label order changes.
    inclusion_idx = list(labels).index("inclusion")
    axes[6].imshow(
        seg[0, :, :, inclusion_idx],
        aspect="auto",
        cmap="Reds",
        alpha=0.4,
        extent=coords_to_imshow_mm(img_coords),
    )
    axes[6].set_title(f"Segmentation on DBUA\nlabels: {list(labels)}")
    axes[6].set_xlabel("Lateral [mm]")
    axes[6].set_ylabel("Depth [mm]")

    fig.suptitle(
        f"openh-rf sample (phase error: {phase_err[0]:.2f} rad)", fontsize=14, y=1.02
    )
    plt.tight_layout()
    plt.savefig(args.output, dpi=150, bbox_inches="tight")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
