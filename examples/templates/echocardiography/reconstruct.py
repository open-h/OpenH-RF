"""Reconstruct: load the echocardiography dataset and beamform the raw RF data.

Loads the HDF5 file created by convert.py, reads the acquisition parameters and raw
channel data, and runs a DAS beamforming pipeline defined in pipeline.yaml.
The resulting B-mode image is saved as a PNG file.

Note: the raw data in this example is synthetic (random noise), so the
output image will appear as unstructured noise — this is expected.

Usage:
    python examples/saving/echocardiography/reconstruct.py
"""

import os

os.environ["MPLBACKEND"] = "Agg"  # use non-interactive backend for matplotlib
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import zea
from zea import Config, File, Pipeline

HERE = Path(__file__).parent
INPUT = HERE / "echocardiography.hdf5"
CONFIG = HERE / "pipeline.yaml"
OUTPUT = HERE / "echocardiography_bmode.png"


def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"{INPUT} not found. Run convert.py first.")

    # Load beamforming config
    config = Config.from_path(str(CONFIG))

    # Load file: read acquisition parameters (with config overrides) and raw data
    with File(str(INPUT)) as f:
        parameters = f.load_parameters(
            **config.parameters
        )  # applies grid_size, xlims, etc. from config
        raw = f.data.raw_data[:]  # (n_frames, n_tx, n_ax, n_el, n_ch)

    print(f"raw_data shape : {raw.shape}")
    print(f"grid           : {parameters.grid.shape}  (z, x, 3)")

    # Build and run the beamforming pipeline defined in pipeline.yaml
    pipeline = Pipeline.from_config(config)
    inputs = pipeline.prepare_parameters(parameters)
    outputs = pipeline(data=raw, **inputs)

    # Convert the output tensor to a NumPy array and save as PNG
    recon = np.array(outputs["data"])  # (n_frames, grid_z, grid_x)
    image = zea.display.to_8bit(recon[0])
    plt.figure()
    plt.imshow(image, extent=parameters.extent_imshow, cmap="gray")
    plt.tight_layout()
    plt.savefig(str(OUTPUT))
    plt.close()

    print(f"Reconstructed  : {recon.shape}")
    print(f"Saved          : {OUTPUT}")


if __name__ == "__main__":
    main()
