# SPDX-License-Identifier: Apache-2.0
"""Beamform an openh-rf HDF5 sample produced by convert_nv_raw2insights_us.py.

Loads raw IQ + scan from the file via zea.File, runs DAS -> envelope ->
normalize -> log-compress, and renders a 7-panel figure in the same style as
sample_visualization.png (IQ energy, stored DAS B-mode, DBUA B-mode,
zea-reconstructed B-mode, zea SoS-corrected B-mode, speed of sound, segmentation).

Usage:
    python examples/nv-raw2insights-us/reconstruct_nv_raw2insights_us.py \
        --input nv_raw2insights_us_sample.hdf5
"""

import argparse
from pathlib import Path

import keras
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import zea
from zea.ops import Beamform, EnvelopeDetect, LogCompress, Normalize

DEFAULT_INPUT = Path("nv_raw2insights_us_sample.hdf5")
DEFAULT_OUTPUT = Path("nv_raw2insights_us_reconstructed.png")


def ext_to_imshow_mm(ext):
    """openh-rf [xmin, xmax, ymin, ymax, zmin, zmax] (m) -> mpl [left, right, bottom, top] (mm)."""
    return [ext[0] * 1e3, ext[1] * 1e3, ext[5] * 1e3, ext[4] * 1e3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(
            f"{args.input} not found. Run convert_nv_raw2insights_us.py first."
        )

    zea.init_device()

    with zea.File(str(args.input)) as f:
        probe = f.probe()
        scan = f.scan()
        raw = f.data.raw_data[:]
        img = f.data.image.values[:]
        img_ext = f.data.image.extent[:]
        focused = f.data.bmode_focused.values[:]
        focused_ext = f.data.bmode_focused.extent[:]
        sos = f.data.sos_map.values[:]
        sos_ext = f.data.sos_map.extent[:]
        seg = f.data.segmentation.values[:]
        seg_ext = f.data.segmentation.extent[:]
        labels = f.data.segmentation.labels.asstr()[:]
        phase_err = f.metrics().common_midpoint_phase_error

    print(f"raw_data: {raw.shape}")

    pipeline = zea.Pipeline(
        operations=[
            Beamform(
                beamformer="delay_and_sum",
                num_patches=200,  # increase with out-of-memory error
            ),
            EnvelopeDetect(),
            Normalize(),
            LogCompress(),
        ]
    )
    params = pipeline.prepare_parameters(probe, scan)
    outputs = pipeline(**{pipeline.key: raw}, **params)
    recon = keras.ops.convert_to_numpy(outputs[pipeline.output_key])[0]
    grid = keras.ops.convert_to_numpy(params["grid"])  # (nz, nx, 3)
    recon_ext = [
        grid[0, 0, 0] * 1e3,
        grid[0, -1, 0] * 1e3,
        grid[-1, 0, 2] * 1e3,
        grid[0, 0, 2] * 1e3,
    ]
    print(f"Reconstructed: {recon.shape}")

    # Reconstruct with SoS correction
    print(f"sos shape: {sos.shape}")
    # Handle different possible sos shapes: (frames, nz, nx) or (frames, nz, nx, 1)
    sos_frame = sos[0] if sos.ndim == 3 else sos[0, :, :, 0]
    nz_sos, nx_sos = sos_frame.shape[0], sos_frame.shape[1]
    sos_grid_x = np.linspace(sos_ext[0], sos_ext[1], nx_sos, dtype=np.float32)
    sos_grid_z = np.linspace(sos_ext[4], sos_ext[5], nz_sos, dtype=np.float32)

    params_sos = params.copy()
    params_sos["sos_map"] = sos_frame
    params_sos["sos_grid_x"] = sos_grid_x
    params_sos["sos_grid_z"] = sos_grid_z
    outputs_sos = pipeline(**{pipeline.key: raw}, **params_sos)

    recon_sos = keras.ops.convert_to_numpy(outputs_sos[pipeline.output_key])[0]
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
    axes[1].imshow(img[0], aspect="auto", cmap="gray", extent=ext_to_imshow_mm(img_ext))
    axes[1].set_title(f"B-mode (DAS, stored)\nimage: {img.shape}")
    axes[1].set_xlabel("Lateral [mm]")
    axes[1].set_ylabel("Depth [mm]")

    # 3: Stored DBUA
    axes[2].imshow(
        focused[0], aspect="auto", cmap="gray", extent=ext_to_imshow_mm(focused_ext)
    )
    axes[2].set_title(f"B-mode (DBUA, stored)\nbmode_focused: {focused.shape}")
    axes[2].set_xlabel("Lateral [mm]")
    axes[2].set_ylabel("Depth [mm]")

    # 4: zea-reconstructed B-mode (DAS pipeline on raw_data)
    stored_ext = ext_to_imshow_mm(img_ext)
    axes[3].imshow(
        recon, aspect="auto", cmap="gray", vmin=-60, vmax=0, extent=recon_ext
    )
    axes[3].set_xlim(stored_ext[0], stored_ext[1])
    axes[3].set_ylim(stored_ext[2], stored_ext[3])
    axes[3].set_title(f"B-mode (DAS, zea)\nreconstructed: {recon.shape}")
    axes[3].set_xlabel("Lateral [mm]")
    axes[3].set_ylabel("Depth [mm]")

    # 5: SOS map
    im = axes[4].imshow(
        sos[0], aspect="auto", cmap="hot", extent=ext_to_imshow_mm(sos_ext)
    )
    plt.colorbar(im, ax=axes[4], label="m/s")
    axes[4].set_title(f"Speed of sound\nsos_map: {sos.shape}")
    axes[4].set_xlabel("Lateral [mm]")
    axes[4].set_ylabel("Depth [mm]")

    # 6: zea-reconstructed B-mode with SoS correction
    axes[5].imshow(
        recon_sos, aspect="auto", cmap="gray", vmin=-60, vmax=0, extent=recon_ext
    )
    axes[5].set_xlim(stored_ext[0], stored_ext[1])
    axes[5].set_ylim(stored_ext[2], stored_ext[3])
    axes[5].set_title(f"B-mode (DAS + SoS, zea)\nreconstructed: {recon_sos.shape}")
    axes[5].set_xlabel("Lateral [mm]")
    axes[5].set_ylabel("Depth [mm]")

    # 7: Segmentation overlaid on focused (DBUA) B-mode
    axes[6].imshow(
        focused[0], aspect="auto", cmap="gray", extent=ext_to_imshow_mm(focused_ext)
    )
    axes[6].imshow(
        seg[0, :, :, 0, 1],
        aspect="auto",
        cmap="Reds",
        alpha=0.4,
        extent=ext_to_imshow_mm(seg_ext),
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
