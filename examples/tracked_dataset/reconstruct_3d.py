"""Optional 3D reconstruction of the tracked CIRS sample.

Beamforms several tracked frames, max-compounds the B-mode planes into a small
Cartesian voxel grid using the probe poses, writes a ``.vti`` volume, and saves
orthogonal rendered views. Add ``--live`` for an interactive PyVista window.

The reconstruction is pure NumPy + zea; only the rendering needs PyVista, which
is imported lazily so the volume can be built (and tested) without it:

    uv pip install pyvista
"""

import argparse
import os
from pathlib import Path

# Default to the jax backend (installed by `uv sync`) so the script runs under a
# bare `uv run` without first exporting KERAS_BACKEND. An explicit value wins.
os.environ.setdefault("KERAS_BACKEND", "jax")

import numpy as np
import zea
from scipy.spatial.transform import Rotation, Slerp

# Frame sampling + voxel grid (kept as constants to keep the CLI minimal).
FRAME_STEP = 2  # take every Nth image frame
NUM_FRAMES = 10  # number of frames to compound
IMAGE_STRIDE = 2  # subsample each B-mode plane before scattering into voxels
VOXEL_SIZE_M = 0.25e-3  # 0.25 mm isotropic voxels
VIEWS = ("xz", "xy", "yz")  # orthogonal views to render (xz is the image plane)


def interpolate_frame_poses(pose, frame_times):
    """Interpolate tracked probe translation + rotation at the image-frame times."""
    translations = pose.translation
    # Pose sample times in the image clock (explicit timestamps if present, else
    # reconstructed from a constant sampling_frequency).
    if pose.timestamps is not None:
        pose_times = float(pose.start_time_offset) + pose.timestamps
    else:
        pose_times = float(pose.start_time_offset) + np.arange(len(translations)) / float(
            pose.sampling_frequency
        )
    if frame_times[0] < pose_times[0] or frame_times[-1] > pose_times[-1]:
        raise ValueError(
            "Selected image frames are outside the tracked pose time range: "
            f"frames {frame_times[0]:.3f}-{frame_times[-1]:.3f} s, "
            f"poses {pose_times[0]:.3f}-{pose_times[-1]:.3f} s."
        )
    translations_at_frames = np.column_stack(
        [np.interp(frame_times, pose_times, translations[:, axis]) for axis in range(3)]
    ).astype(np.float32)
    rotations_at_frames = Slerp(pose_times, Rotation.from_quat(pose.rotation))(frame_times)
    return translations_at_frames, rotations_at_frames


def beamform_frames(input_path, config, frame_indices):
    """Beamform the selected frames; return B-mode values + image-plane coordinates."""
    zea.init_device()
    with zea.File(input_path) as f:
        track = f.tracks[0]
        parameters = track.load_parameters(**config.parameters)
        raw = track.data.raw_data[frame_indices]
        metadata = f.metadata

    print(f"raw_data frames: {raw.shape}")
    pipeline = zea.Pipeline.from_config(config)
    params = pipeline.prepare_parameters(parameters)
    outputs = pipeline(**{pipeline.key: raw}, **params, return_numpy=True)
    return outputs[pipeline.output_key], outputs["grid"], metadata


def compound_volume(bmode, coordinates, translations, rotations, voxel_size_m):
    """Max-compound tracked B-mode planes into a Cartesian voxel grid.

    Every frame shares the same local image-plane coordinates; each frame's probe
    pose places that plane in world space, and its pixels are scattered into the
    nearest voxels, keeping the maximum value (a max-compounded mosaic — frames
    extend the field of view and overlaps take the max).
    """
    plane_points = coordinates[::IMAGE_STRIDE, ::IMAGE_STRIDE].reshape(-1, 3)
    # Place each frame's plane in world space once, then reuse for bounds + fill.
    world_points = [rot.apply(plane_points) + xyz for rot, xyz in zip(rotations, translations)]

    origin = np.min([pts.min(axis=0) for pts in world_points], axis=0)
    upper = np.max([pts.max(axis=0) for pts in world_points], axis=0)
    dims = np.maximum(np.ceil((upper - origin) / voxel_size_m).astype(int) + 1, 2)

    volume = np.zeros(dims, dtype=np.uint8).ravel()
    frame_values = zea.display.to_8bit(
        bmode[:, ::IMAGE_STRIDE, ::IMAGE_STRIDE], pillow=False
    )
    for pts, values in zip(world_points, frame_values):
        voxel_idx = np.clip(np.rint((pts - origin) / voxel_size_m).astype(int), 0, dims - 1)
        np.maximum.at(volume, np.ravel_multi_index(voxel_idx.T, dims), values.reshape(-1))

    span_mm = (upper - origin) * 1e3
    print(f"Max-compounded volume: {tuple(int(d) for d in dims)} voxels")
    print(f"Volume span: {span_mm[0]:.1f} x {span_mm[1]:.1f} x {span_mm[2]:.1f} mm")
    return volume.reshape(dims), origin


def render_volume(volume, origin_m, voxel_size_m, output_dir, live):
    """Write a .vti volume + orthogonal rendered views. Imports PyVista lazily."""
    import pyvista as pv

    image = pv.ImageData(
        dimensions=np.asarray(volume.shape) + 1,  # +1: values live on cells
        spacing=(voxel_size_m * 1e3,) * 3,
        origin=tuple(origin_m * 1e3),
    )
    image.cell_data["bmode"] = volume.ravel(order="F")

    output_dir.mkdir(parents=True, exist_ok=True)
    volume_path = output_dir / "cirs_3d_volume.vti"
    image.save(volume_path)
    print(f"Saved {volume_path}")

    # Empty voxels are transparent; reconstructed echoes are opaque.
    opacity = [0.0] + [1.0] * 32

    def draw(plotter):
        plotter.set_background("black")
        plotter.add_volume(
            image,
            scalars="bmode",
            cmap="gray",
            opacity=opacity,
            preference="cell",
            shade=False,
            show_scalar_bar=False,
        )
        plotter.add_bounding_box(color="white", line_width=1)

    for view in VIEWS:
        plotter = pv.Plotter(off_screen=True, window_size=(900, 800))
        draw(plotter)
        getattr(plotter, f"view_{view}")()  # built-in orthogonal camera
        screenshot = output_dir / f"cirs_3d_{view}.png"
        plotter.screenshot(screenshot)
        plotter.close()
        print(f"Saved {screenshot}")

    if live:
        plotter = pv.Plotter(window_size=(1000, 800))
        draw(plotter)
        plotter.show(title="Tracked CIRS 3D reconstruction")


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(here / "data" / "cirs_imaging_zea.hdf5"))
    parser.add_argument("--config", default=str(here / "data" / "config.yaml"))
    parser.add_argument("--output-dir", type=Path, default=here / "3d_views")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Open an interactive PyVista window after rendering snapshots.",
    )
    args = parser.parse_args()

    config = zea.Config.from_path(args.config)
    with zea.File(args.input) as f:
        frame_count = f.tracks[0].data.raw_data.shape[0]
        frame_times = f.timestamps

    frame_indices = np.arange(0, frame_count, FRAME_STEP)[:NUM_FRAMES]
    if len(frame_indices) == 0:
        raise ValueError("No frames selected for 3D reconstruction.")
    print(f"Selected frames: {frame_indices.tolist()}")

    bmode, coordinates, metadata = beamform_frames(args.input, config, frame_indices)
    translations, rotations = interpolate_frame_poses(
        metadata.probe_pose, frame_times[frame_indices]
    )
    volume, origin = compound_volume(
        bmode, coordinates, translations, rotations, VOXEL_SIZE_M
    )
    render_volume(volume, origin, VOXEL_SIZE_M, args.output_dir, args.live)


if __name__ == "__main__":
    main()
