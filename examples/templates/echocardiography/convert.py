"""Convert: create a synthetic echocardiography dataset and save as a zea HDF5 file.

Demonstrates how to store raw RF data alongside a strain map, ECG signal,
probe orientation, and rich clinical metadata in the openh-rf format.

All data is synthetic (random noise). Replace the arrays with real acquisitions
to use this script with actual scanner output.

Usage:
    python examples/saving/echocardiography/convert.py
"""

from pathlib import Path

import numpy as np
from zea import File
from zea.beamform.pixelgrid import cartesian_pixel_grid

OUTPUT = Path(__file__).parent / "echocardiography.hdf5"

# ------------------------------------------------------------------
# Dimensions
# ------------------------------------------------------------------
n_frames = 10
n_tx = 64  # focused transmits
n_el = 64  # phased-array elements
n_ax = 1024  # axial samples per channel
img_h = img_w = 128

# ------------------------------------------------------------------
# Probe geometry: phased array
# ------------------------------------------------------------------
pitch = 2e-4  # element pitch in metres
probe_geometry = np.zeros((n_el, 3), dtype=np.float32)
probe_geometry[:, 0] = (np.arange(n_el) - (n_el - 1) / 2) * pitch

# Spatial limits used to generate map coordinates in metres
xlims = (-30e-3, 30e-3)
ylims = (-1e-3, 1e-3)
zlims = (0.0, 80e-3)
map_coordinates = cartesian_pixel_grid(
    xlims=xlims,
    zlims=zlims,
    ylims=ylims,
    grid_size_x=img_w,
    grid_size_y=1,
    grid_size_z=img_h,
)

# ------------------------------------------------------------------
# Data: raw RF + B-mode image + strain map
# ------------------------------------------------------------------
data = {
    "raw_data": np.random.randn(n_frames, n_tx, n_ax, n_el, 1).astype(np.float32),
    "image": {
        # Pre-computed B-mode stored alongside raw data as a reference
        "values": np.random.randint(0, 255, (n_frames, img_h, img_w, 1), dtype=np.uint8),
        "coordinates": map_coordinates,
    },
    "strain_percentage_map": {
        # Myocardial strain map in percent
        "values": (np.random.randn(n_frames, img_h, img_w, 1) * 10).astype(np.float32),
        "coordinates": map_coordinates,
    },
}

# ------------------------------------------------------------------
# Scan parameters: phased-array focused transmit sequence
# ------------------------------------------------------------------
scan = {
    "sampling_frequency": np.float32(20e6),
    "center_frequency": np.float32(2.5e6),
    "demodulation_frequency": np.float32(2.5e6),
    "sound_speed": np.float32(1540.0),
    "initial_times": np.zeros(n_tx, dtype=np.float32),
    "t0_delays": np.zeros((n_tx, n_el), dtype=np.float32),
    "tx_apodizations": np.ones((n_tx, n_el), dtype=np.float32),
    "focus_distances": np.full(n_tx, 60e-3, dtype=np.float32),  # focused at 60 mm
    "transmit_origins": np.zeros((n_tx, 3), dtype=np.float32),
    "polar_angles": np.linspace(-0.5, 0.5, n_tx, dtype=np.float32),
}

# ------------------------------------------------------------------
# Optional metadata: subject, ECG, probe orientation, annotations
# ------------------------------------------------------------------
metadata = {
    "credit": "echocardiography convert.py",
    "subject": {
        "id": "subject_001",
        "type": "human",
        "age": 55,
        "sex": "M",
        "fat_percentage": 22.0,
    },
    "ecg": {
        "samples": np.zeros((500,), dtype=np.float32),
        "start_time_offset": np.float32(0.0),
        "sampling_frequency": np.float32(500.0),
    },
    "annotations": {
        "anatomy": "heart",
        "view": (["a4c", "a2c", "plax"] * 4)[:n_frames],
        "label": "normal",
    },
    "text_report": (
        "Normal LV size and systolic function. "
        "No significant valvular disease. EF estimated at 60%."
    ),
}

# ------------------------------------------------------------------
# Create and verify the file
# ------------------------------------------------------------------
File.create(
    path=str(OUTPUT),
    data=data,
    scan=scan,
    probe={"name": "P4-1", "probe_geometry": probe_geometry},
    metadata=metadata,
    us_machine="Simulated",
    description="Synthetic echocardiography dataset for tutorial purposes.",
    overwrite=True,
)

with File(str(OUTPUT)) as f:
    print(f"Saved: {OUTPUT}")
    print(f"  raw_data   : {f.data.raw_data.shape}")
    print(f"  image      : {f.data.image.values.shape}")
    print(f"  strain     : {f.data.strain_percentage_map.values.shape}")
    print(f"  subject    : {f.metadata.subject.type}, age {f.metadata.subject.age}")
    print(f"  ECG        : {f.metadata.ecg.samples.shape}")
    print(f"  report     : {f.metadata.text_report[:60]}...")
