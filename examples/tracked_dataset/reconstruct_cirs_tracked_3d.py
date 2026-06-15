"""Optional 3D reconstruction of the tracked CIRS sample.

This example beamforms several tracked frames, max-compounds the B-mode slices
into a small Cartesian voxel grid using the probe poses, and saves
volume-rendered views from each side. Add ``--live`` to open an interactive
PyVista window.

Install the optional renderer before running:

    uv pip install pyvista
"""

import argparse
from pathlib import Path

import numpy as np
import pyvista as pv
import zea
from scipy.spatial.transform import Rotation, Slerp


def volume_to_image_data(volume, origin_m, voxel_size_m):
    spacing_mm = (voxel_size_m * 1e3,) * 3
    image = pv.ImageData(
        dimensions=np.asarray(volume.shape) + 1,
        spacing=spacing_mm,
        origin=tuple(origin_m * 1e3),
    )
    image.cell_data["bmode"] = volume.ravel(order="F")
    return image


def add_volume(plotter, image, background_color, volume_opacity):
    plotter.set_background(background_color)
    plotter.add_volume(
        image,
        scalars="bmode",
        cmap="gray",
        opacity=volume_opacity,
        preference="cell",
        shade=False,
        show_scalar_bar=False,
    )
    plotter.add_bounding_box(color="white", line_width=1)
    axes = plotter.add_axes()
    for caption in (
        axes.GetXAxisCaptionActor2D(),
        axes.GetYAxisCaptionActor2D(),
        axes.GetZAxisCaptionActor2D(),
    ):
        caption.GetCaptionTextProperty().SetColor(1.0, 1.0, 1.0)


def camera_from_direction(image, direction, zoom=1.1):
    bounds = np.array(image.bounds).reshape(3, 2)
    center = bounds.mean(axis=1)
    distance = max(bounds[:, 1] - bounds[:, 0]) * 2.2
    direction = np.asarray(direction, dtype=float)
    camera_position = center + direction * distance
    view_up = (0, 0, -1) if direction[2] == 0 else (1, 0, 0)
    return camera_position, center, view_up, zoom


def interpolate_frame_poses(pose, frame_times):
    """Interpolate tracked probe poses at image-frame timestamps."""
    translations = pose.translation
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

    interpolated_translations = np.column_stack(
        [
            np.interp(frame_times, pose_times, translations[:, axis])
            for axis in range(translations.shape[1])
        ]
    )
    rotations = Rotation.from_quat(pose.rotation)
    interpolated_rotations = Slerp(pose_times, rotations)(frame_times)
    return interpolated_translations.astype(np.float32), interpolated_rotations


def beamform_frames(input_path, config, frame_indices):
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

    bmode_map = {
        "values": outputs[pipeline.output_key],
        "coordinates": outputs["grid"],
    }
    return bmode_map, metadata


def compound_volume(
    bmode_map,
    pose,
    frame_times,
    image_stride,
    voxel_size_m,
):
    translations, rotations = interpolate_frame_poses(
        pose,
        frame_times,
    )

    # Reuse the same local image-plane coordinates for every tracked frame.
    bmode = bmode_map["values"]
    coordinates = bmode_map["coordinates"]
    plane_points = coordinates[::image_stride, ::image_stride].reshape(-1, 3)

    # First pass: find the world-space bounds
    point_min = np.full(3, np.inf, dtype=np.float32)
    point_max = np.full(3, -np.inf, dtype=np.float32)
    for rotation, translation in zip(rotations, translations):
        points = rotation.apply(plane_points) + translation
        point_min = np.minimum(point_min, points.min(axis=0))
        point_max = np.maximum(point_max, points.max(axis=0))

    origin = point_min
    upper = point_max
    dimensions = np.ceil((upper - origin) / voxel_size_m).astype(int) + 1
    dimensions = np.maximum(dimensions, 2)

    volume = np.zeros(dimensions, dtype=np.uint8)
    volume_flat = volume.ravel()
    frame_values = zea.display.to_8bit(
        bmode[:, ::image_stride, ::image_stride],
        pillow=False,
    )
    # Second pass: max-compound each frame directly into the voxel grid.
    for rotation, translation, values in zip(rotations, translations, frame_values):
        points = rotation.apply(plane_points) + translation
        indices = np.rint((points - origin) / voxel_size_m).astype(np.int32)
        indices = np.clip(indices, 0, dimensions - 1)
        flat = np.ravel_multi_index(indices.T, dimensions)
        samples = values.reshape(-1)
        np.maximum.at(volume_flat, flat, samples)

    dimensions_label = tuple(int(value) for value in dimensions)
    volume_span_mm = (upper - origin) * 1e3
    print(f"Max-compounded volume: {dimensions_label} voxels")
    print(
        "Volume span: "
        f"{volume_span_mm[0]:.1f} x {volume_span_mm[1]:.1f} x {volume_span_mm[2]:.1f} mm"
    )

    return volume, origin


def save_volume(volume, origin_m, voxel_size_m, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)

    image = volume_to_image_data(volume, origin_m, voxel_size_m)
    volume_path = output_dir / "cirs_3d_volume.vti"
    image.save(volume_path)
    print(f"Saved {volume_path}")
    return image


def render_views(
    volume,
    origin_m,
    voxel_size_m,
    output_dir,
    view_directions,
    background_color,
    volume_opacity,
):
    image = save_volume(volume, origin_m, voxel_size_m, output_dir)
    for name, direction in view_directions.items():
        plotter = pv.Plotter(off_screen=True, window_size=(1100, 900))
        add_volume(
            plotter,
            image,
            background_color,
            volume_opacity,
        )
        camera_position, center, view_up, zoom = camera_from_direction(image, direction)
        plotter.camera_position = (camera_position, center, view_up)
        plotter.camera.zoom(zoom)
        screenshot = output_dir / f"cirs_3d_{name}.png"
        plotter.screenshot(screenshot)
        plotter.close()
        print(f"Saved {screenshot}")

    return image


def show_live_view(
    image,
    view_directions,
    background_color,
    volume_opacity,
):
    plotter = pv.Plotter(window_size=(1200, 900))
    add_volume(
        plotter,
        image,
        background_color,
        volume_opacity,
    )
    camera_position, center, view_up, zoom = camera_from_direction(
        image,
        view_directions["front"],
        zoom=1.15,
    )
    plotter.camera_position = (camera_position, center, view_up)
    plotter.camera.zoom(zoom)
    plotter.show(title="Tracked CIRS 3D reconstruction")


def main():
    case_root = Path(__file__).resolve().parent
    default_input = str(case_root / "data" / "cirs_imaging_zea.hdf5")
    default_config = str(case_root / "data" / "config.yaml")
    default_output_dir = case_root / "3d_views"
    background_color = "black"
    # Empty voxels sit at the display floor; reconstructed echoes become opaque.
    volume_opacity = [0.0] + [1.0] * 32
    view_directions = {
        "front": (0, 1, 0),
        "left": (1, 0, 0),
        "top": (0, 0, 1),
    }

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=default_input)
    parser.add_argument("--config", default=default_config)
    parser.add_argument("--output-dir", type=Path, default=default_output_dir)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--num-frames", type=int, default=10)
    parser.add_argument("--frame-step", type=int, default=2)
    parser.add_argument("--image-stride", type=int, default=2)
    parser.add_argument("--voxel-size-mm", type=float, default=0.25)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Open an interactive PyVista volume window after rendering snapshots.",
    )
    args = parser.parse_args()

    config = zea.Config.from_path(args.config)

    with zea.File(args.input) as f:
        track = f.tracks[0]
        frame_count = track.data.raw_data.shape[0]
        all_frame_times = track.timestamps[:, 0].astype(np.float64)

    frame_indices = np.arange(args.start_frame, frame_count, args.frame_step)[
        : args.num_frames
    ]
    if len(frame_indices) == 0:
        raise ValueError("No frames selected for 3D reconstruction.")

    frame_times = all_frame_times[frame_indices]
    print(f"Selected frames: {frame_indices.tolist()}")
    bmode_map, metadata = beamform_frames(
        args.input,
        config,
        frame_indices,
    )
    volume, origin = compound_volume(
        bmode_map,
        metadata.probe_pose,
        frame_times,
        args.image_stride,
        args.voxel_size_mm * 1e-3,
    )
    image = render_views(
        volume,
        origin,
        args.voxel_size_mm * 1e-3,
        args.output_dir,
        view_directions,
        background_color,
        volume_opacity,
    )

    if args.live:
        show_live_view(
            image,
            view_directions,
            background_color,
            volume_opacity,
        )


if __name__ == "__main__":
    main()
