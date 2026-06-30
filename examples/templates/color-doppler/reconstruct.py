"""Reconstruct: beamform the B-mode track from a duplex color-Doppler dataset.

Loads the HDF5 file created by convert.py, selects the ``bmode`` track,
reads its parameters and raw channel data, and runs a DAS beamforming
pipeline defined in pipeline.yaml. The resulting B-mode image is saved as a PNG file.

Note: the raw data in this example is synthetic (random noise), so the
output image will appear as unstructured noise — this is expected.

Usage:
    python examples/templates/color-doppler/reconstruct.py
"""

import os

os.environ["MPLBACKEND"] = "Agg"  # use non-interactive backend for matplotlib

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import zea
from zea import Config, File, Pipeline

HERE = Path(__file__).parent
INPUT = HERE / "color_doppler.hdf5"
CONFIG = HERE / "pipeline.yaml"
OUTPUT = HERE / "color_doppler_bmode.png"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="CUDA device ID (e.g. 'cuda:0', 'auto:1', or 'cpu')",
    )
    args = parser.parse_args()

    zea.init_device(device=args.device, verbose=False)

    if not INPUT.exists():
        raise FileNotFoundError(f"{INPUT} not found. Run convert.py first.")

    # Load beamforming config
    config = Config.from_path(str(CONFIG))
    parameter_overrides = dict(config.parameters)
    parameter_overrides.setdefault("ylims", [0.0, 0.0])

    # Load file: select bmode track, then read parameters and raw data
    with File(str(INPUT)) as f:
        bmode_track = f.get_track("bmode")
        parameters = bmode_track.load_parameters(
            **parameter_overrides
        )  # applies grid_size, xlims, etc. from config
        raw = bmode_track.data.raw_data[:]  # (n_frames, n_tx, n_ax, n_el, n_ch)

    print(f"raw_data shape : {raw.shape}")
    print(f"grid           : {parameters.grid.shape}  (z, x, 3)")

    # Build and run the beamforming pipeline defined in pipeline.yaml
    pipeline = Pipeline.from_config(config)
    inputs = pipeline.prepare_parameters(parameters)
    outputs = pipeline(data=raw, **inputs)

    # Convert the output tensor to a NumPy array and save as PNG
    recon = np.array(outputs["data"])  # (n_frames, grid_z, grid_x)
    image = zea.display.to_8bit(recon[0])
    zea.visualize.set_mpl_style()
    plt.imshow(
        image,
        extent=parameters.extent_imshow,
        cmap="gray",
    )
    plt.xlabel("X (mm)")
    plt.ylabel("Z (mm)")
    plt.savefig(str(OUTPUT), bbox_inches="tight", dpi=100)

    print(f"Reconstructed  : {recon.shape}")
    print(f"Saved          : {OUTPUT}")


if __name__ == "__main__":
    main()
