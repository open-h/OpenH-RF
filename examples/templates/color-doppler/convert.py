"""Convert: create a synthetic duplex dataset with B-mode and Doppler tracks.

Demonstrates zea multi-track storage for duplex imaging by writing separate
tracks for B-mode and color-Doppler acquisitions in one HDF5 file.

All data is synthetic (random noise). Replace the arrays with real acquisitions
to use this script with actual scanner output.

Usage:
    python examples/saving/color-doppler/convert.py
"""

from pathlib import Path

import numpy as np
from zea import File
from zea.beamform.pixelgrid import cartesian_pixel_grid

OUTPUT = Path(__file__).parent / "color_doppler.hdf5"

# ------------------------------------------------------------------
# Dimensions
# ------------------------------------------------------------------
n_frames = 4
n_el = 128  # receive elements
n_ax_bmode = 2048  # axial samples per channel for B-mode
n_ax_doppler = 1024  # axial samples per channel for Doppler
map_h, map_w = 128, 64
n_tx_bmode = 8
n_tx_doppler = 16
xlims = (-10e-3, 10e-3)
zlims = (0.0, 30e-3)

# ------------------------------------------------------------------
# Probe geometry: linear array
# ------------------------------------------------------------------
pitch = 3e-4  # element pitch in metres
probe_geometry = np.zeros((n_el, 3), dtype=np.float32)
probe_geometry[:, 0] = (np.arange(n_el) - (n_el - 1) / 2) * pitch


# ------------------------------------------------------------------
# Duplex tracks: B-mode and color-Doppler
# ------------------------------------------------------------------
def make_scan(n_tx: int, time_to_next_tx: float, focused: bool) -> dict:
    """Create per-track scan parameters for either B-mode or Doppler."""
    focus_value = np.float32(
        0.03 if focused else 0.0
    )  # 0.0 indicates plane-wave in this example
    return {
        "sampling_frequency": np.float32(40e6),
        "center_frequency": np.float32(5e6),
        "demodulation_frequency": np.float32(5e6),
        "sound_speed": np.float32(1540.0),
        "initial_times": np.zeros(n_tx, dtype=np.float32),
        "t0_delays": np.zeros((n_tx, n_el), dtype=np.float32),
        "tx_apodizations": np.ones((n_tx, n_el), dtype=np.float32),
        "focus_distances": np.full(n_tx, focus_value, dtype=np.float32),
        "transmit_origins": np.zeros((n_tx, 3), dtype=np.float32),
        "polar_angles": np.linspace(-0.15, 0.15, n_tx, dtype=np.float32),
        "time_to_next_transmit": np.full(
            (n_frames, n_tx), np.float32(time_to_next_tx), dtype=np.float32
        ),
    }


map_coordinates = cartesian_pixel_grid(
    xlims=xlims,
    zlims=zlims,
    grid_size_x=map_w,
    grid_size_z=map_h,
)

# Since we have two different transmit schemes in our acquisition,
# we store the raw data and corresponding scan parameters necessary for
# processing in separatete tracks for B-mode and Doppler.
# This will enable conventiently loading only the relevant track for each processing pipeline.
tracks = [
    {
        "label": "bmode",
        "data": {
            "raw_data": np.random.randn(
                n_frames, n_tx_bmode, n_ax_bmode, n_el, 1
            ).astype(np.float32),
            "image": {
                # Optional pre-computed B-mode stored with the B-mode track
                "values": np.random.randint(
                    0, 255, (n_frames, map_h, map_w), dtype=np.uint8
                ),
                "coordinates": map_coordinates,
            },
        },
        "scan": make_scan(n_tx=n_tx_bmode, time_to_next_tx=1e-4, focused=True),
    },
    {
        "label": "doppler",
        "data": {
            "raw_data": np.random.randn(
                n_frames, n_tx_doppler, n_ax_doppler, n_el, 1
            ).astype(np.float32),
            "color_doppler": {
                # Velocity map in m/s (positive = toward transducer, negative = away)
                "values": np.random.randn(n_frames, map_h, map_w).astype(np.float32),
                "coordinates": map_coordinates,
            },
        },
        "scan": make_scan(n_tx=n_tx_doppler, time_to_next_tx=2e-4, focused=False),
    },
]

# One track index per global transmit event, repeated for each frame.
track_schedule = np.tile([0] * n_tx_bmode + [1] * n_tx_doppler, n_frames).astype(
    np.int32
)

# ------------------------------------------------------------------
# Optional metadata: subject info and annotations
# ------------------------------------------------------------------
metadata = {
    "credit": "color-doppler convert.py",
    "subject": {"id": "subject_002", "type": "human", "age": 62, "sex": "F"},
    "annotations": {
        "anatomy": "carotid",
        "view": np.array(["longitudinal"] * n_frames, dtype=np.str_),
    },
}

# ------------------------------------------------------------------
# Create and verify the file
# ------------------------------------------------------------------
File.create(
    path=str(OUTPUT),
    tracks=tracks,
    probe={"name": "L12-3", "probe_geometry": probe_geometry},
    track_schedule=track_schedule,
    metadata=metadata,
    us_machine="Simulated",
    description="Synthetic color-Doppler dataset for tutorial purposes.",
    overwrite=True,
)

with File(str(OUTPUT)) as f:
    print(f"Saved: {OUTPUT}")
    print(f"  tracks         : {f.track_labels}")
    bmode_track = f.get_track("bmode")
    doppler_track = f.get_track("doppler")
    print(f"  bmode raw_data : {bmode_track.data.raw_data.shape}")
    print(f"  bmode image    : {bmode_track.data.image.values.shape}")
    print(f"  doppler raw_data: {doppler_track.data.raw_data.shape}")
    print(f"  doppler map    : {doppler_track.data.color_doppler.values.shape}")
    print(f"  schedule shape : {f.track_schedule.shape}")
    print(f"  subject        : {f.metadata.subject.type}, age {f.metadata.subject.age}")
