# SPDX-License-Identifier: Apache-2.0
"""Example reconstruction script for the twente-cavitation dataset of OpenH-RF.

Dataset link: https://huggingface.co/datasets/nvidia/OpenH-RF/tree/main/twente-cavitation

Passive acoustic map (PAM) reconstruction of one cavitation acquisition.

This is a *passive* acquisition: the L11-4v never transmits (the file records
``tx_apodizations`` as all zeros); a separate 2.25 MHz single-element transducer
insonifies with long pulses and the array only receives. A standard
pulse-echo reconstruction fails twice over because there is no transmit signal 
-- the all-zero ``tx_apodizations`` make the transmit-delay model return inf, 
and the pulse-echo delays sample each pixel before the cavitation signal has 
reached the array.

Both are fixed with two parameter overrides, with no custom operations needed:
``tx_apodizations`` -> ones restores a valid delay computation, and
``initial_times`` -> [-t_c] shifts every pixel's sampling instant to t_c, a
moment *during* the insonification. The chain then aligns purely on receive
curvature, i.e. one-way passive beamforming; averaging the envelope energy over
several sampling instants and over frames approximates time-exposure-acoustics
PAM (Gyongy & Coussios).

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

import keras
import matplotlib.pyplot as plt
import numpy as np
import zea
from mpl_toolkits.axes_grid1 import make_axes_locatable
from zea import Config, File, Pipeline
from zea.ops import (
    Beamform,
    Cast,
    Demodulate,
    EnvelopeDetect,
    LogCompress,
    Normalize,
)


# Grid at half-wavelength sampling over the full aperture.
PARAMETERS = {
    "grid_size_x": 200,#50, use the commented grid_size values for reasonable results when on a CPU to speed up the reconstruction
    "grid_size_z": 300,#75,
    "xlims": [-0.010, 0.010],
    "zlims": [0.010, 0.040],
    "apply_lens_correction": True,
}

# Sampling instants t_c within the 444 us insonification window. Each run of
# the pipeline images the received field at one instant; averaging their
# envelope energies is the "time exposure" integration of classic PAM.
SAMPLING_INSTANTS = np.linspace(100e-6, 400e-6, 6)

# Contributor-suggested minimum variance (PR #490), else delay-and-sum.
BEAMFORMER = "minimum_variance"
BEAMFORMER_KWARGS = {"subarray_size": 32, "diagonal_loading": 1e-2}
FRAMES = 10  # Number of frames to average

HERE = Path(__file__).parent

# --- Inputs -----------------------------------------------------------------
# Defaults stream straight from the published corpus. Swap any of these for a
# local path to run against your own copy.
INPUT = "hf://nvidia/OpenH-RF/twente-cavitation/data/cavitation_bubbles_1000kPa_01mL_per_min.hdf5"
OUTPUT = None  # Output PNG path (default: input file name with a .png extension)
CONFIG = HERE / "pipeline.yaml"
DEVICE = "auto:1"  # Device to use (e.g. 'cpu', 'cuda:0', or 'auto:1')


def build_pipeline() -> Pipeline:
    """Standard zea chain up to envelope detection (energy averaging happens
    across sampling instants/frames, so normalization comes afterwards)."""
    return Pipeline(
        operations=[
            Cast(dtype="float32"),
            Demodulate(),  # RF (n_ch=1) -> IQ before beamforming
            Beamform(beamformer=BEAMFORMER, **BEAMFORMER_KWARGS),
            EnvelopeDetect(),
        ],
        validate=True,
        with_batch_dim=True,
    )


def main():
    global OUTPUT
    if OUTPUT is None:
        OUTPUT = Path(Path(INPUT).stem + ".png")

    zea.init_device(device=DEVICE, verbose=False)

    # Build the pipeline in code and save it (with parameters) to pipeline.yaml,
    # then load that YAML back in so the shipped YAML is exactly what runs.
    pipeline = build_pipeline()
    config = pipeline.to_config()
    config["parameters"] = PARAMETERS
    config.to_yaml(str(CONFIG))
    config = Config.from_path(str(CONFIG))
    pipeline = Pipeline.from_config(config)

    with File(str(INPUT)) as f:
        parameters = f.load_parameters(**config.parameters)
        raw = f.data.raw_data[:FRAMES]  # (n_frames, n_tx, n_ax, n_el, 1)

    # Passive-acquisition overrides (see module docstring).
    parameters["tx_apodizations"] = np.ones_like(np.asarray(parameters["tx_apodizations"]))

    # Accumulate envelope energy over sampling instants (and frames).
    energy = None
    for t_c in SAMPLING_INSTANTS:
        parameters["initial_times"] = np.array([-t_c], dtype=np.float32)
        inputs = pipeline.prepare_parameters(parameters)
        env = keras.ops.convert_to_numpy(pipeline(data=raw, **inputs)["data"])
        frame_energy = (env**2).mean(axis=0)  # average over frames
        energy = frame_energy if energy is None else energy + frame_energy
    amplitude = np.sqrt(energy / len(SAMPLING_INSTANTS))

    # Normalize + log-compress the averaged map with the same zea operations.
    post = Pipeline(operations=[Normalize(), LogCompress()], with_batch_dim=False)
    pam_db = keras.ops.convert_to_numpy(post(data=amplitude)["data"])

    zea.visualize.set_mpl_style()
    extent_mm = [v * 1e3 for v in parameters.extent_imshow]
    fig, ax = plt.subplots(figsize=(6, 8))
    im = ax.imshow(np.clip(pam_db, -20, 0), extent=extent_mm, cmap="inferno")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Z (mm)")
    cax = make_axes_locatable(ax).append_axes("right", size="5%", pad=0.05)
    fig.colorbar(im, cax=cax, label="dB")
    plt.savefig(str(OUTPUT), bbox_inches="tight", dpi=100)
    plt.close()

    print(f"Saved          : {OUTPUT}")

if __name__ == "__main__":
    main()
