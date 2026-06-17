"""Reconstruct: beamform the Verasonics plane-wave phantom using DAS.

Loads the HDF5 file created by convert.py, reads the acquisition parameters and
raw RF data, and runs a delay-and-sum beamforming pipeline configured in
pipeline.yaml. The resulting B-mode image is saved as a PNG file.

Usage:
    python examples/saving/verasonics/reconstruct.py
    python examples/saving/verasonics/reconstruct.py --input my_file.hdf5
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
DEFAULT_INPUT = HERE / "verasonics_sample.hdf5"
DEFAULT_OUTPUT = HERE / "verasonics_bmode.png"
CONFIG = HERE / "pipeline.yaml"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"{args.input} not found. Run convert.py first.")

    # Load beamforming config
    config = Config.from_path(str(CONFIG))

    # Load file: read acquisition parameters (with config overrides) and raw RF data
    with File(str(args.input)) as f:
        parameters = f.load_parameters(
            **config.parameters
        )  # applies grid_size, n_ch, etc. from config
        raw = f.data.raw_data[:]  # (n_frames, n_tx, n_ax, n_el, 1) — RF

    print(f"raw_data shape : {raw.shape}")
    print(f"grid           : {parameters.grid.shape}  (z, x, 3)")

    # Build and run the beamforming pipeline defined in pipeline.yaml
    pipeline = Pipeline.from_config(config)
    inputs = pipeline.prepare_parameters(parameters)
    outputs = pipeline(data=raw, **inputs)

    # Convert the output tensor to a NumPy array and save as PNG
    recon = np.array(outputs["data"])  # (n_frames, grid_z, grid_x)
    image = zea.display.to_8bit(recon[0], dynamic_range=parameters.dynamic_range)

    zea.visualize.set_mpl_style()
    plt.imshow(
        image,
        extent=parameters.extent_imshow,
        cmap="gray",
    )
    plt.xlabel("X (mm)")
    plt.ylabel("Z (mm)")
    plt.savefig(str(args.output), bbox_inches="tight", dpi=100)

    print(f"Reconstructed  : {recon.shape}")
    print(f"Saved          : {args.output}")


if __name__ == "__main__":
    main()
