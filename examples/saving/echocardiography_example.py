# SPDX-License-Identifier: Apache-2.0
"""Example: Echocardiography dataset with rich metadata.

Shows fields relevant to cardiac ultrasound:
image, strain map, subject demographics, ECG, probe orientation,
annotations, text report, and quality metrics.
"""

import numpy as np

from zea import File

np.random.seed(0)

# ------------------------------------------------------------------
# Dimensions
# ------------------------------------------------------------------
n_frames = 30
n_tx = 64
n_ax = 1024
n_el = 64
img_h = img_w = 128

# ------------------------------------------------------------------
# Probe geometry (phased array)
# ------------------------------------------------------------------
pitch = 2e-4
probe_geometry = np.zeros((n_el, 3), dtype=np.float32)
probe_geometry[:, 0] = (np.arange(n_el) - (n_el - 1) / 2) * pitch

# Spatial extent shared by image and strain: (xmin, xmax, ymin, ymax, zmin, zmax) in metres
extent = np.array([-30e-3, 30e-3, -1e-3, 1e-3, 0.0, 80e-3], dtype=np.float32)

# ------------------------------------------------------------------
# Data: raw RF + B-mode image + strain map
# ------------------------------------------------------------------
data = {
    "raw_data": np.random.randn(n_frames, n_tx, n_ax, n_el, 1).astype(np.float32),
    "image": {
        "values": np.random.randint(
            0, 255, (n_frames, img_h, img_w, 1), dtype=np.uint8
        ),
        "extent": extent,
    },  # optionally include a B-mode image for reference
    "strain_percentage_map": {
        "values": np.random.randn(n_frames, img_h, img_w, 1).astype(np.float32) * 10,
        "extent": extent,
    },  # optionally include strain map
}

# ------------------------------------------------------------------
# Scan: phased-array focused transmit
# ------------------------------------------------------------------
scan = {
    "probe_geometry": probe_geometry,
    "sampling_frequency": 20e6,
    "center_frequency": 2.5e6,
    "demodulation_frequency": 2.5e6,
    "initial_times": np.zeros(n_tx, dtype=np.float32),
    "t0_delays": np.zeros((n_tx, n_el), dtype=np.float32),
    "tx_apodizations": np.ones((n_tx, n_el), dtype=np.float32),
    "focus_distances": np.full(n_tx, 60e-3, dtype=np.float32),
    "transmit_origins": np.zeros((n_tx, 3), dtype=np.float32),
    "polar_angles": np.linspace(-0.5, 0.5, n_tx, dtype=np.float32),
    "azimuth_angles": np.zeros(n_tx, dtype=np.float32),
    "sound_speed": 1540.0,
}

# ------------------------------------------------------------------
# Optional Metadata: subject, ECG, probe orientation, annotations, report
# ------------------------------------------------------------------
metadata = {
    "subject": {"id": "subject_001", "type": "human", "age": 55, "sex": "M", "fat_percentage": 22.0},
    "credit": "echocardiography_example.py",
    "ecg": {
        "samples": np.random.randint(50, 200, (500,), dtype=np.uint8),
        "start_time_offset": 0.0,
        "sampling_frequency": 500.0,
    },
    "probe_orientation": {
        "samples": np.random.randn(100, 6).astype(np.float32) * 0.01,
        "start_time_offset": 0.0,
        "sampling_frequency": 100.0,
    },
    "annotations": {
        "anatomy": "heart",
        "view": np.array(["a4c", "a2c", "plax"] * 10, dtype=np.str_),
        "label": np.array(["normal"] * n_frames, dtype=np.str_),
        "image_quality": "mid",
    },
    "text_report": (
        "Normal LV size and systolic function. "
        "No significant valvular disease. EF estimated at 60%."
    ),
}

# ------------------------------------------------------------------
# Metrics: quality indicators
# ------------------------------------------------------------------
metrics = {
    "coherence_factor": np.random.uniform(0.5, 0.95, n_frames).astype(np.float32),
    "common_midpoint_phase_error": np.random.uniform(0.01, 0.1, n_frames).astype(
        np.float32
    ),
}

# ------------------------------------------------------------------
# Assemble, save & verify
# ------------------------------------------------------------------

File.create(
    path="echocardiography_dataset.hdf5",
    data=data,
    scan=scan,
    metadata=metadata,
    metrics=metrics,
    probe_name="P4-1",
    us_machine="Simulated",
    description="Example echocardiography dataset with synthetic data.",
)

with File("echocardiography_dataset.hdf5") as f:
    print("Echocardiography dataset saved and reloaded successfully.")
    print(f"  raw_data : {f.data.raw_data.shape}")
    print(f"  image    : {f.data.image.values.shape}")
    print(f"  strain   : {f.data.strain_percentage_map.values.shape}")
    m = f.metadata()
    print(f"  subject  : {m.subject.type}, age {m.subject.age}")
    print(f"  ECG      : {m.ecg.samples.shape}")
    print(f"  report   : {m.text_report[:75]}...")
