"""Convert: create a synthetic segmentation dataset and save as a zea HDF5 file.

Demonstrates how to store raw RF data alongside a per-class segmentation mask
(with named labels) in the openh-rf format using zea.File.create.

All data is synthetic (random noise). Replace the arrays with real acquisitions
to use this script with actual scanner output.

Usage:
    python examples/saving/segmentation/convert.py
"""

from pathlib import Path

import numpy as np
from zea import File
from zea.beamform.pixelgrid import cartesian_pixel_grid

OUTPUT = Path(__file__).parent / "segmentation.hdf5"

# ------------------------------------------------------------------
# Dimensions
# ------------------------------------------------------------------
n_frames = 3
n_tx = 11  # plane-wave transmit angles
n_el = 128  # receive elements
n_ax = 2048  # axial samples per channel
seg_h, seg_w = 256, 256

# ------------------------------------------------------------------
# Probe geometry: linear array
# ------------------------------------------------------------------
pitch = 3e-4  # element pitch in metres
probe_geometry = np.zeros((n_el, 3), dtype=np.float32)
probe_geometry[:, 0] = (np.arange(n_el) - (n_el - 1) / 2) * pitch

# Spatial limits used to generate map coordinates in metres
xlims = (-10e-3, 10e-3)
zlims = (0.0, 30e-3)

# ------------------------------------------------------------------
# Data: raw RF + segmentation mask
# ------------------------------------------------------------------
# Segmentation labels: integer pixel values map to class names by index
labels = ["background", "vessel_wall", "lumen"]
segmentation_coordinates = cartesian_pixel_grid(
    xlims=xlims,
    zlims=zlims,
    grid_size_x=seg_w,
    grid_size_z=seg_h,
)

data = {
    "raw_data": np.random.randn(n_frames, n_tx, n_ax, n_el, 1).astype(np.float32),
    "segmentation": {
        # Boolean mask of shape (frames, z, x, n_classes)
        "values": np.random.choice([True, False], (n_frames, seg_h, seg_w, len(labels))),
        "labels": labels,
        "coordinates": segmentation_coordinates,
    },
}

# ------------------------------------------------------------------
# Scan parameters: plane-wave transmit sequence
# ------------------------------------------------------------------
scan = {
    "sampling_frequency": np.float32(40e6),
    "center_frequency": np.float32(5e6),
    "demodulation_frequency": np.float32(5e6),
    "sound_speed": np.float32(1540.0),
    "initial_times": np.zeros(n_tx, dtype=np.float32),
    "t0_delays": np.zeros((n_tx, n_el), dtype=np.float32),
    "tx_apodizations": np.ones((n_tx, n_el), dtype=np.float32),
    "focus_distances": np.zeros(n_tx, dtype=np.float32),  # 0 = plane wave
    "transmit_origins": np.zeros((n_tx, 3), dtype=np.float32),
    "polar_angles": np.linspace(-0.3, 0.3, n_tx, dtype=np.float32),
}

# ------------------------------------------------------------------
# Optional metadata: annotations
# ------------------------------------------------------------------
metadata = {
    "credit": "segmentation convert.py",
    "annotations": {
        "anatomy": "carotid",
        "view": "cross-section",
        "label": "normal",
    },
}

# ------------------------------------------------------------------
# Create and verify the file
# ------------------------------------------------------------------
File.create(
    path=str(OUTPUT),
    data=data,
    scan=scan,
    probe={"name": "L7-4", "probe_geometry": probe_geometry},
    metadata=metadata,
    description="Synthetic segmentation dataset for tutorial purposes.",
    overwrite=True,
)

with File(str(OUTPUT)) as f:
    print(f"Saved: {OUTPUT}")
    print(f"  raw_data     : {f.data.raw_data.shape}")
    print(f"  segmentation : {f.data.segmentation.values.shape}")
    print(f"  labels       : {f.data.segmentation.labels.asstr()[:]}")
