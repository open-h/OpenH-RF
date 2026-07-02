"""Reconstruct: load the echocardiography dataset and beamform the raw RF data.

Defines a DAS beamforming pipeline in code, saves it (together with some beamforming
parameters) to pipeline.yaml, then loads that YAML back and runs it on the HDF5 file
created by convert.py. The dataset is a focused-transmit phased-array acquisition, so
the pipeline beamforms on a polar grid and scan-converts to Cartesian for display.
The resulting B-mode image is saved as a PNG file.

Note: the raw data in this example is synthetic (random noise), so the
output image will appear as unstructured noise — this is expected.

Usage:
    python examples/templates/echocardiography/reconstruct.py
"""

import os

os.environ["MPLBACKEND"] = "Agg"  # use non-interactive backend for matplotlib

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import zea
from zea import Config, File, Pipeline
from zea.ops import (
    Beamform,
    EnvelopeDetect,
    LogCompress,
    Normalize,
    ScanConvert,
)

HERE = Path(__file__).parent
INPUT = HERE / "echocardiography.hdf5"
CONFIG = HERE / "pipeline.yaml"
OUTPUT = HERE / "echocardiography_bmode.png"

# Custom reconstruction parameters. These are passed to load_parameters and
# override (or fill in) values read from the HDF5 file.
#
# The dataset contains focused-transmit RF data (n_ch=1) from a phased array,
# beamformed on a polar grid.
PARAMETERS = {
    "selected_transmits": "all",
    "n_ch": 1,  # RF data
    "grid_size_x": 200,  # lateral pixels
    "grid_size_z": 400,  # axial pixels
    "pixels_per_wavelength": 2,
    "f_number": 0.6,
    "grid_type": "polar",  # beamform on a polar grid
    "polar_limits": [-0.785398, 0.785398],
    "zlims": [0.0, 0.04],  # metres
}


def build_pipeline() -> Pipeline:
    """Define the delay-and-sum beamforming pipeline in code."""
    return Pipeline(
        operations=[
            Beamform(beamformer="delay_and_sum", num_patches=100),
            EnvelopeDetect(),
            Normalize(),
            LogCompress(),
            ScanConvert(),  # scan convert to Cartesian grid for display
        ],
        validate=False,
    )


def write_config(pipeline: Pipeline, path: Path) -> None:
    """Serialize the pipeline and acquisition parameters to a YAML config file."""
    config = pipeline.to_config()
    config["parameters"] = PARAMETERS
    config.to_yaml(str(path))


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

    # Define the beamforming pipeline in code, save it (with the acquisition
    # parameters) to pipeline.yaml, then load that YAML back in.
    write_config(build_pipeline(), CONFIG)
    config = Config.from_path(str(CONFIG))

    # Load file: read acquisition parameters (with config overrides) and raw data
    with File(str(INPUT)) as f:
        parameters = f.load_parameters(
            **config.parameters
        )  # applies grid_size, xlims, etc. from config
        raw = f.data.raw_data[:]  # (n_frames, n_tx, n_ax, n_el, n_ch)

    print(f"raw_data shape : {raw.shape}")
    print(f"grid           : {parameters.grid.shape}  (z, x, 3)")

    # Build and run the beamforming pipeline loaded from pipeline.yaml
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
