# SPDX-License-Identifier: Apache-2.0
"""Example reconstruction script for the strasbourg-basel dataset of OpenH-RF.

Dataset link: https://huggingface.co/datasets/nvidia/OpenH-RF/tree/main/strasbourg-basel

B-mode reconstruction of focused, walking-aperture bone channel data (BoneSRF).

All nine scans reconstruct the same way; only the input file and the frame
chosen as that scan's reference differ.

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
from zea import Config, File, Pipeline

HERE = Path(__file__).parent
DATA = HERE / "data"
CONFIG = HERE / "pipeline.yaml"
OUTPUT_DIR = HERE / "reference_bmodes"

# The frame each scan's committed reference_bmodes/<scan>.png was rendered from.
REFERENCE_FRAME = {
    "phantom1_distal": 130,
    "phantom1_proximal": 100,
    "phantom1_wholebone": 150,
    "phantom2_distal": 40,
    "phantom2_proximal": 40,
    "phantom2_wholebone": 45,
    "phantom3_distal": 100,
    "phantom3_proximal": 0,
    "phantom3_wholebone": 100,
}

# --- Inputs -----------------------------------------------------------------
# Defaults stream straight from the published corpus. Swap any of these for a
# local path to run against your own copy.
SCAN = "hf://nvidia/OpenH-RF/strasbourg-basel/BoneSRF/data/phantom2_proximal.hdf5"
FRAME = None  # frame to beamform (default: that scan's reference frame)
DEVICE = None  # CUDA device ID (e.g. 'cuda:0', 'auto:1', or 'cpu')


def reconstruct(source: str, scan: str, frame: int, config: Config) -> None:
    """Beamform one frame of one scan and write reference_bmodes/<scan>.png.

    ``source`` is a local path or an ``hf://`` URI and stays a string throughout
    -- pathlib collapses the ``//`` in a URI.
    """
    # Each file is a full multi-frame sweep (~20-24 GB); only this frame is read.
    with File(str(source)) as f:
        parameters = f.load_parameters(**config.parameters)  # dynamic_range etc.
        raw = f.data.raw_data[frame : frame + 1]  # (1, n_tx, n_ax, n_el, n_ch)

    print(f"{scan}: frame {frame}, raw_data {raw.shape}, grid {parameters.grid.shape}")

    pipeline = Pipeline.from_config(config)
    outputs = pipeline(data=raw, **pipeline.prepare_parameters(parameters))

    recon = np.array(outputs["data"])  # (n_frames, grid_z, grid_x, n_ch)
    # No envelope_detect in pipeline.yaml (see its comments), so the trailing
    # n_ch=1 axis survives to the output; squeeze it for a 2D image.
    image = zea.display.to_8bit(np.squeeze(recon[0]), dynamic_range=parameters.dynamic_range)

    zea.visualize.set_mpl_style()
    plt.figure()
    # extent_imshow is in meters; convert to mm to match the axis labels below.
    plt.imshow(image, extent=np.array(parameters.extent_imshow) * 1e3, cmap="gray")
    plt.axis("off")
    out = OUTPUT_DIR / f"{scan}.png"
    plt.savefig(str(out), bbox_inches="tight", pad_inches=0, dpi=100)
    plt.close()
    print(f"  saved {out.relative_to(HERE)}")


def main():
    if SCAN:
        sources = {Path(SCAN).stem: str(SCAN)}
    else:
        sources = {scan: str(DATA / f"{scan}.hdf5") for scan in REFERENCE_FRAME}
    scans = list(sources)
    unknown = [s for s in scans if s not in REFERENCE_FRAME]
    if unknown:
        raise SystemExit(f"unknown scan(s) {unknown}; expected one of {list(REFERENCE_FRAME)}")
    if FRAME is not None and len(scans) > 1:
        raise SystemExit("FRAME applies to a single scan; name one")

    zea.init_device(device=DEVICE, verbose=False)
    OUTPUT_DIR.mkdir(exist_ok=True)
    config = Config.from_path(str(CONFIG))

    for scan, source in sources.items():
        reconstruct(source, scan, FRAME if FRAME is not None else REFERENCE_FRAME[scan], config)


if __name__ == "__main__":
    main()
