# SPDX-License-Identifier: Apache-2.0
"""Example: Segmentation dataset created with File.create.

Shows fields relevant to segmentation tasks:
raw RF data, per-frame segmentation mask with class labels,
and per-frame view annotations.

All data is synthetic — replace with real acquisitions.
"""

import numpy as np

from zea import File

np.random.seed(0)

# ------------------------------------------------------------------
# Dimensions
# ------------------------------------------------------------------
n_frames = 3
n_tx = 11
n_el = 128
n_ax = 2048
seg_h, seg_w = 256, 256

# ------------------------------------------------------------------
# Probe geometry (linear array)
# ------------------------------------------------------------------
pitch = 3e-4
probe_geometry = np.zeros((n_el, 3), dtype=np.float32)
probe_geometry[:, 0] = (np.arange(n_el) - (n_el - 1) / 2) * pitch

# Spatial extent: (xmin, xmax, ymin, ymax, zmin, zmax) in metres
extent = np.array([-15e-3, 15e-3, -1e-3, 1e-3, 0.0, 30e-3], dtype=np.float32)

# ------------------------------------------------------------------
# Data: raw RF + segmentation mask
# ------------------------------------------------------------------
# Segmentation labels: integer pixel values map to class names by index
labels = np.array(["background", "vessel_wall", "lumen"], dtype=np.str_)

data = {
    "raw_data": np.random.randn(n_frames, n_tx, n_ax, n_el, 1).astype(np.float32),
    "segmentation": {
        # bool one-hot mask, shape (n_frames, z, x, y, n_labels) — see
        # https://zea--307.org.readthedocs.build/en/307/data-acquisition.html
        "values": np.eye(len(labels), dtype=bool)[
            np.random.randint(0, len(labels), (n_frames, seg_h, seg_w, 1))
        ],
        "labels": labels,
        "extent": extent,
    },
}

# ------------------------------------------------------------------
# Scan: linear-array plane-wave
# ------------------------------------------------------------------
scan = {
    "probe_geometry": probe_geometry,
    "sampling_frequency": 40e6,
    "center_frequency": 5e6,
    "demodulation_frequency": 5e6,
    "initial_times": np.zeros(n_tx, dtype=np.float32),
    "t0_delays": np.zeros((n_tx, n_el), dtype=np.float32),
    "tx_apodizations": np.ones((n_tx, n_el), dtype=np.float32),
    "focus_distances": np.zeros(n_tx, dtype=np.float32),
    "transmit_origins": np.zeros((n_tx, 3), dtype=np.float32),
    "polar_angles": np.linspace(-0.3, 0.3, n_tx, dtype=np.float32),
    "azimuth_angles": np.zeros(n_tx, dtype=np.float32),
    "sound_speed": 1540.0,
}

# ------------------------------------------------------------------
# Metadata: annotations
# ------------------------------------------------------------------
metadata = {
    "credit": "segmentation_map_example.py",
    "annotations": {
        "anatomy": "carotid",
        "view": np.array(["cross-section"] * n_frames, dtype=np.str_),
        "label": np.array(["normal"] * n_frames, dtype=np.str_),
    },
}

# ------------------------------------------------------------------
# Assemble, save & verify
# ------------------------------------------------------------------
File.create(
    path="segmentation_dataset.hdf5",
    data=data,
    scan=scan,
    metadata=metadata,
    description="Example segmentation dataset with synthetic data.",
)

with File("segmentation_dataset.hdf5") as f:
    print("Segmentation dataset saved and reloaded successfully.")
    print(f"raw_data: {f.data.raw_data.shape}")
    print(f"segmentation: {f.data.segmentation.values.shape}")
    print(f"labels {f.data.segmentation.labels.asstr()[:]}")
