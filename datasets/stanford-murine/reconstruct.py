# SPDX-License-Identifier: Apache-2.0
"""Example reconstruction script for the stanford-murine dataset of OpenH-RF.

Dataset link: https://huggingface.co/datasets/nvidia/OpenH-RF/tree/main/stanford-murine

B-mode reconstruction of murine full synthetic aperture, multifocal and
Hadamard-encoded channel data.

Each file bundles three tracks. Every track is reconstructed with its own
pipeline_<track>.yaml: the acquisition parameters come from the track's own
metadata and the YAML adds the reconstruction grid and dynamic range. On top of
the YAML, a baseband FIR low-pass at half the probe bandwidth is inserted after
demodulation; its taps depend on the probe, so `zea process --track <track>`
runs the same pipeline without it. One displayed image is saved per track.

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

HERE = Path(__file__).parent
CONFIG_BY_TRACK = {
    "multifocal": "pipeline_multifocal.yaml",
    "hadamard": "pipeline_hadamard.yaml",
    "synthetic_aperture": "pipeline_synthetic_aperture.yaml",
}

# --- Inputs -----------------------------------------------------------------
# Defaults stream straight from the published corpus. Swap any of these for a
# local path to run against your own copy.
ZEA_FILE = (
    "hf://nvidia/OpenH-RF/stanford-murine/data/RatExperiments/VerasonicsAcq/"
    "Rat3/ExposedLiver/DATA_Tracks_20190319_115804.hdf5"
)
CONFIG_DIR = "hf://nvidia/OpenH-RF/stanford-murine"  # holds the pipeline_*.yaml configs
OUT_DIR = HERE / "assets"  # every PNG is written here


def folded_frequency(frequency: float, sampling_frequency: float) -> float:
    """Fold a frequency into the sampled Nyquist interval."""
    return (frequency + sampling_frequency / 2.0) % sampling_frequency - sampling_frequency / 2.0


def demodulation_filter(
    sampling_frequency: float,
    demodulation_frequency: float,
    probe_bandwidth_percent: float,
    np,
    num_taps: int = 127,
) -> tuple[object, float]:
    """Design a baseband FIR whose passband cannot cross a sampled RF image."""
    from scipy.signal import firwin

    nyquist = sampling_frequency / 2.0
    carrier = abs(folded_frequency(demodulation_frequency, sampling_frequency))
    requested_cutoff = abs(demodulation_frequency) * probe_bandwidth_percent / 200.0
    alias_safe_cutoff = min(carrier, nyquist - carrier) * 0.9
    cutoff = min(requested_cutoff, alias_safe_cutoff)
    if not 0.0 < cutoff < nyquist:
        raise ValueError(
            f"Cannot design demodulation filter for fs={sampling_frequency:g} Hz, "
            f"demodulation_frequency={demodulation_frequency:g} Hz"
        )
    return firwin(num_taps, cutoff, fs=sampling_frequency).astype(np.float32), cutoff


def with_fir_filter(config):
    """Insert the baseband FIR after demodulation.

    Its taps depend on each file's probe bandwidth, so they are computed per track
    below and the step is not part of the pipeline YAMLs; ``zea process`` runs the
    same pipeline without it.
    """
    import zea

    config = zea.Config(config.as_dict())
    operations = list(config.pipeline.operations)
    operations.insert(
        operations.index("demodulate") + 1,
        {"name": "fir_filter", "params": {"axis": -3, "complex_channels": True}},
    )
    config.pipeline.operations = operations
    return config


def reconstruct_track(path: str, output_dir: Path, track_index: int, config, pipeline) -> Path:
    """Reconstruct the first frame of one track with its YAML pipeline plus the FIR."""
    import matplotlib.pyplot as plt
    import numpy as np
    import zea
    from mpl_toolkits.axes_grid1 import make_axes_locatable

    print(f"Processing {path}")
    with zea.File(str(path)) as file:
        track = file.tracks[track_index]
        track_label = track.label
        # Acquisition parameters come from the file; the pipeline YAML adds the
        # reconstruction grid and display settings on top.
        parameters = track.load_parameters()
        parameters.update(config.parameters.as_dict())
        data = track.data.raw_data[:1, parameters.selected_transmits]

    filter_taps, _ = demodulation_filter(
        float(parameters.sampling_frequency),
        float(parameters.demodulation_frequency),
        float(parameters.probe_bandwidth_percent),
        np,
    )
    outputs = pipeline(
        return_numpy=True,
        **{pipeline.key: data},
        **pipeline.prepare_parameters(parameters, fir_filter_taps=filter_taps),
    )
    image = np.squeeze(outputs[pipeline.output_key])
    dynamic_range = tuple(float(v) for v in parameters.dynamic_range)

    stem = Path(path).stem
    out_path = output_dir / f"{stem}_{track_label}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_xlabel("Lateral (mm)")
    ax.set_ylabel("Axial (mm)")
    im = ax.imshow(
        image,
        cmap="gray",
        vmin=dynamic_range[0],
        vmax=dynamic_range[1],
        extent=parameters.extent_imshow * 1000,
    )
    ax.set_title(f"B-mode: {Path(path).stem} ({track_label})")
    colorbar_ax = make_axes_locatable(ax).append_axes("right", size="5%", pad=0.08)
    fig.colorbar(im, cax=colorbar_ax, label="Amplitude (dB)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out_path}")
    return out_path


def reconstruct_file(
    path: str, output_dir: Path, pipeline_configs: dict[str, tuple[object, object]]
) -> list[Path]:
    import zea

    out_paths = []
    with zea.File(str(path)) as file:
        track_labels = [track.label for track in file.tracks]
    for track_index, track_label in enumerate(track_labels):
        if track_label not in pipeline_configs:
            expected = ", ".join(sorted(pipeline_configs))
            raise ValueError(
                f"No config found for track label {track_label!r}; expected one of {expected}"
            )
        config, pipeline = pipeline_configs[track_label]
        out_paths.append(reconstruct_track(path, output_dir, track_index, config, pipeline))
    return out_paths


def main() -> None:
    import zea

    zea.init_device()
    zea.visualize.set_mpl_style()

    # Build each track pipeline once, then reuse it for every track in the file.
    pipeline_configs = {}
    for track_label, filename in CONFIG_BY_TRACK.items():
        config = with_fir_filter(zea.Config.from_path(f"{CONFIG_DIR}/{filename}"))
        pipeline_configs[track_label] = (config, zea.Pipeline.from_config(config))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    reconstruct_file(ZEA_FILE, OUT_DIR, pipeline_configs)


if __name__ == "__main__":
    main()
