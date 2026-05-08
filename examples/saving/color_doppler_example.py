# SPDX-License-Identifier: Apache-2.0
"""Example: Color Doppler dataset.

Shows fields relevant to colour-flow imaging:
B-mode image, color Doppler velocity map, subject info,
ECG signal, and annotations.

ColorDopplerMap values store velocity in m/s (positive = toward
the transducer, negative = away).
"""

import numpy as np

from zea import File

np.random.seed(0)

# ------------------------------------------------------------------
# Dimensions
# ------------------------------------------------------------------
n_frames = 10
n_tx = 16
n_el = 128
n_ax = 2048
map_h, map_w = 128, 64

# ------------------------------------------------------------------
# Probe geometry (linear array)
# ------------------------------------------------------------------
pitch = 3e-4
probe_geometry = np.zeros((n_el, 3), dtype=np.float32)
probe_geometry[:, 0] = (np.arange(n_el) - (n_el - 1) / 2) * pitch

# Spatial extent shared by image and Doppler: (xmin, xmax, ymin, ymax, zmin, zmax) in metres
extent = np.array([-10e-3, 10e-3, -1e-3, 1e-3, 5e-3, 45e-3], dtype=np.float32)

# ------------------------------------------------------------------
# Data: raw RF + B-mode image + color Doppler velocity map
# ------------------------------------------------------------------
data = {
    "raw_data": np.random.randn(n_frames, n_tx, n_ax, n_el, 1).astype(np.float32),
    "image": {
        "values": np.random.randint(
            0, 255, (n_frames, map_h, map_w, 1), dtype=np.uint8
        ),
        "extent": extent,
    },  # optionally include a B-mode image for reference
    "color_doppler": {
        "values": np.random.randn(n_frames, map_h, map_w, 1).astype(
            np.float32
        ),  # velocity in m/s
        "extent": extent,
    },
}

# ------------------------------------------------------------------
# Scan: linear-array plane-wave Doppler
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
    "polar_angles": np.linspace(-0.15, 0.15, n_tx, dtype=np.float32),
    "azimuth_angles": np.zeros(n_tx, dtype=np.float32),
    "sound_speed": 1540.0,
}

# ------------------------------------------------------------------
# Optional Metadata: subject, ECG, annotations
# ------------------------------------------------------------------
metadata = {
    "subject": {"id": "subject_002", "type": "human", "age": 62, "sex": "F"},
    "credit": "color_doppler_example.py",
    "ecg": {
        "samples": np.random.randint(50, 200, (333,), dtype=np.uint8),
        "start_time_offset": 0.0,
        "sampling_frequency": 500.0,
    },
    "annotations": {
        "anatomy": "carotid",
        "view": np.array(["longitudinal"] * n_frames, dtype=np.str_),
        "image_quality": "high",
    },
}

# ------------------------------------------------------------------
# Assemble, save & verify
# ------------------------------------------------------------------
File.create(
    path="color_doppler_dataset.hdf5",
    data=data,
    scan=scan,
    metadata=metadata,
    probe_name="L12-3",
    us_machine="Simulated",
    description="Example color Doppler dataset with synthetic data.",
)

with File("color_doppler_dataset.hdf5") as f:
    print("Color Doppler dataset saved and reloaded successfully.")
    print(f"  raw_data      : {f.data.raw_data.shape}")
    print(f"  image         : {f.data.image.values.shape}")
    print(f"  color_doppler : {f.data.color_doppler.values.shape}")
    m = f.metadata()
    print(f"  subject       : {m.subject.type}, age {m.subject.age}")
    print(f"  ECG           : {m.ecg.samples.shape}")
