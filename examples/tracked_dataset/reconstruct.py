"""Beamform the tracked CIRS zea sample and plot the probe trajectory.

Loads raw RF + scan + probe pose from the file, runs the configured beamforming
pipeline, and renders one B-mode image plus x/y/z probe translation at the
ultrasound frame times.
"""

import argparse
import os
from pathlib import Path

# Default to the jax backend (installed by `uv sync`) so the script runs under a
# bare `uv run` without first exporting KERAS_BACKEND. An explicit value wins.
os.environ.setdefault("KERAS_BACKEND", "jax")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import zea


def coordinates_to_imshow_extent_mm(coordinates):
    return [
        coordinates[0, 0, 0] * 1e3,
        coordinates[0, -1, 0] * 1e3,
        coordinates[-1, 0, 2] * 1e3,
        coordinates[0, 0, 2] * 1e3,
    ]


def translations_at_frame_times(pose, frame_times_s):
    translations = pose.translation
    # Pose sample times in the image clock: explicit per-sample timestamps when
    # present, otherwise reconstructed from a constant sampling_frequency.
    if pose.timestamps is not None:
        pose_times_s = float(pose.start_time_offset) + pose.timestamps
    else:
        pose_times_s = float(pose.start_time_offset) + np.arange(len(translations)) / float(
            pose.sampling_frequency
        )
    if frame_times_s[0] < pose_times_s[0] or frame_times_s[-1] > pose_times_s[-1]:
        raise ValueError("Image frame times are outside the tracked pose time range.")

    frame_translations = np.column_stack(
        [
            np.interp(frame_times_s, pose_times_s, translations[:, axis])
            for axis in range(translations.shape[1])
        ]
    )
    return (frame_translations - frame_translations[0]) * 1e3


def main():
    case_root = Path(__file__).resolve().parent
    default_input = str(case_root / "data" / "cirs_imaging_zea.hdf5")
    default_config = str(case_root / "data" / "config.yaml")
    default_output = case_root / "cirs_bmode_trajectory.png"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=default_input)
    parser.add_argument("--config", default=default_config)
    parser.add_argument("--output", type=Path, default=default_output)
    parser.add_argument("--frame-index", type=int, default=0)
    args = parser.parse_args()

    if not args.input.startswith("hf://") and not Path(args.input).exists():
        raise FileNotFoundError(f"{args.input} not found.")

    config = zea.Config.from_path(args.config)

    zea.init_device()

    with zea.File(args.input) as f:
        track = f.tracks[0]
        frame_count = track.data.raw_data.shape[0]
        frame_times_s = f.timestamps
        parameters = track.load_parameters(**config.parameters)
        raw = track.data.raw_data[args.frame_index : args.frame_index + 1]
        metadata = f.metadata

    print(f"raw_data frame: {raw.shape} ({frame_count} frames in file)")

    pipeline = zea.Pipeline.from_config(config)
    params = pipeline.prepare_parameters(parameters)
    outputs = pipeline(**{pipeline.key: raw}, **params, return_numpy=True)
    bmode_map = {
        "values": outputs[pipeline.output_key][0],
        "coordinates": outputs["grid"],
    }
    bmode_display = zea.display.to_8bit(bmode_map["values"], pillow=False)
    print(f"Reconstructed: {bmode_map['values'].shape}")

    pose = metadata.probe_pose
    trajectory_mm = translations_at_frame_times(pose, frame_times_s)
    frame_time_s = frame_times_s[args.frame_index]
    last_frame_time_s = frame_times_s[-1]

    fig, axes = plt.subplot_mosaic(
        [["bmode", "x"], ["bmode", "y"], ["bmode", "z"]],
        figsize=(11, 7.5),
        gridspec_kw={"width_ratios": [1, 1.3]},
    )

    axes["bmode"].imshow(
        bmode_display,
        aspect="equal",
        cmap="gray",
        extent=coordinates_to_imshow_extent_mm(bmode_map["coordinates"]),
    )
    axes["bmode"].set(
        title=f"B-mode frame {args.frame_index}\nreconstructed: {bmode_map['values'].shape}",
        xlabel="Lateral [mm]",
        ylabel="Depth [mm]",
    )

    for i, label in enumerate(("x", "y", "z")):
        axis = axes[label]
        values_mm = trajectory_mm[:, i]
        axis.plot(frame_times_s, values_mm, color="tab:blue", marker="o", markersize=3)
        axis.axvline(
            frame_time_s,
            color="tab:red",
            linewidth=1.2,
            alpha=0.8,
            label="selected image",
        )
        axis.axvline(
            last_frame_time_s,
            color="tab:red",
            linewidth=1.2,
            linestyle="--",
            label="last image",
        )
        axis.set(
            title=f"Probe {label}(t)",
            xlabel="Time [s]",
            ylabel=f"{label} offset [mm]",
        )
        axis.grid(True, color="0.85", linewidth=0.8)
        if i == 0:
            axis.legend(loc="upper right", fontsize=8, frameon=False)

    fig.suptitle("CIRS zea reconstruction and tracked probe trajectory", y=0.98)
    plt.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.output, dpi=150, bbox_inches="tight")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
