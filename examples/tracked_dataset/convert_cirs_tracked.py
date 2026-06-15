"""Convert the tracked CIRS raw HF files to a local OpenH-RF/zea dataset."""

import argparse
from pathlib import Path

import h5py
import numpy as np
from huggingface_hub import hf_hub_download
from scipy.spatial.transform import Rotation
from zea import File, Pipeline
from zea.ops import (
    Beamform,
    Demodulate,
    Downsample,
    EnvelopeDetect,
    LogCompress,
    Normalize,
)


def load_imaging(path):
    """Read the raw RF frames, image timestamps, and scan metadata."""
    with h5py.File(path, "r") as handle:
        raw_data = np.asarray(handle["raw_data"], dtype=np.float32)
        # One absolute nanosecond timestamp per ultrasound image frame.
        image_times_ns = np.asarray(handle["time_stamp"], dtype=np.int64)
        scan = {
            key: np.asarray(value)
            for key, value in handle["scan"].items()
            if key != "zlims"
        }
        zlims = np.asarray(handle["scan"]["zlims"], dtype=np.float32)

    return raw_data, image_times_ns, scan, zlims


def load_probe_pose(path, image_times_ns):
    """Parse timestamped 4x4 tracking matrices into ``zea`` probe-pose metadata."""
    rows = [
        line.split()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # Each row is a flattened 4x4 pose matrix followed by an absolute ns timestamp.
    matrices = np.asarray([row[:16] for row in rows], dtype=np.float64).reshape(-1, 4, 4)
    pose_times_ns = np.asarray([row[16] for row in rows], dtype=np.int64)

    probe_pose = {
        # Source tracking translations are millimetres; zea stores metres.
        "translation": (matrices[:, 3, :3] * 1e-3).astype(np.float32),
        "rotation": Rotation.from_matrix(matrices[:, :3, :3]).as_quat().astype(np.float32),
        "rotation_representation": "quaternion_xyzw",
        "start_time_offset": np.float32((pose_times_ns[0] - image_times_ns[0]) / 1e9),
        "timestamps": ((pose_times_ns - pose_times_ns[0]) * 1e-9).astype(np.float32),
    }
    return probe_pose, pose_times_ns


def write_config(path, zlims):
    pipeline = Pipeline(
        operations=[
            Demodulate(),
            Downsample(factor=4),
            Beamform(beamformer="delay_and_sum"),
            EnvelopeDetect(),
            Normalize(),
            LogCompress(),
        ]
    )
    config = pipeline.to_config()
    config.update_recursive(
        {
            "parameters": {"zlims": [float(zlims[0]), float(zlims[1])]},
        }
    )
    config.to_yaml(path)


def main():
    case_root = Path(__file__).resolve().parent
    hf_repo = "Felixdu11/tracked_CIRS_simulated"
    default_output = case_root / "data" / "cirs_imaging_zea.hdf5"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=default_output)
    args = parser.parse_args()

    output_path = args.output
    config_path = output_path.parent / "config.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Pull the raw source files from HF; the converted zea files are written locally.
    imaging_path = Path(
        hf_hub_download(
            repo_id=hf_repo,
            filename="raw/cirs_imaging.hdf5",
            repo_type="dataset",
        )
    )
    tracking_path = Path(
        hf_hub_download(
            repo_id=hf_repo,
            filename="raw/cirs_tracking.ts",
            repo_type="dataset",
        )
    )
    raw_data, image_times_ns, scan, zlims = load_imaging(imaging_path)
    probe = {
        "name": "simulated_probe",
        "type": "linear",
        "probe_geometry": scan.pop("probe_geometry"),
        "element_width": scan.pop("element_width"),
        "probe_center_frequency": scan["center_frequency"],
    }
    # Store the image cadence as the scan transmit sequence.
    frame_intervals_ns = np.diff(image_times_ns)
    scan["time_to_next_transmit"] = (frame_intervals_ns * 1e-9).astype(np.float32)

    probe_pose, pose_times_ns = load_probe_pose(tracking_path, image_times_ns)

    # Store raw RF plus scan metadata, and attach independently sampled tracking.
    File.create(
        str(output_path),
        tracks=[{"data": {"raw_data": raw_data}, "scan": scan}],
        track_schedule=np.zeros(raw_data.shape[0] * raw_data.shape[1], dtype=np.int32),
        probe=probe,
        metadata={
            "subject": {"id": "cirs_phantom", "type": "phantom"},
            "probe_pose": probe_pose,
        },
        description="Simulated UltraRay CIRS RF acquisition",
        overwrite=True,
    )
    write_config(config_path, zlims)


if __name__ == "__main__":
    main()
