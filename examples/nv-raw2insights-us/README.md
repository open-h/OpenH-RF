---
pretty_name: NV-Raw2Insights-US Simulations
license: cc-by-4.0
task_categories:
  - image-segmentation
  - other
tags:
  - ultrasound
  - rf
  - openh-rf
  - medical-imaging
  - simulation
  - beamforming
  - sound-speed-estimation
  - phase-aberration
language:
  - en
size_categories:
  - n<1K
---

# NV-Raw2Insights-US → OpenH-RF

A worked **submission example**: convert one sample of the public
[`nvidia/NV-Raw2Insights-US`](https://huggingface.co/datasets/nvidia/NV-Raw2Insights-US)
dataset into the OpenH-RF (`zea`) file format, then reconstruct a B-mode from the
raw channel data to validate it.

This directory follows the OpenH-RF Sub-Dataset Submission Guide. The **required
submission files** are:

| File | Role |
|------|------|
| `*.hdf5` | Acquisition(s) in [`zea` file format](https://zea.readthedocs.io/en/v0.1.0a2/data-acquisition.html) (one file per acquisition) |
| [`reconstruct.py`](reconstruct.py) | Reference reconstruction → `.png`, driven by a `zea.Pipeline` |
| [`pipeline.yaml`](pipeline.yaml) | The saved reconstruction pipeline |
| `README.md` | This data card |
| [`LICENSE`](LICENSE) | CC BY 4.0 |

[`convert.py`](convert.py) is an **illustrative helper**, not part of the required
set — it shows how the published HF dataset maps onto the `zea` format.

## Running this example

Environment setup is in the [main README](../../README.md). After `uv sync` and
`export KERAS_BACKEND=jax`:

```bash
# 1. stream one sample from HF, write the zea-format HDF5
uv run python examples/nv-raw2insights-us/convert.py

# 2. beamform the raw channel data in code (writes pipeline.yaml + the 7-panel PNG)
uv run python examples/nv-raw2insights-us/reconstruct.py
```

---

# Data Card — NV-Raw2Insights-US Simulations

## Dataset Description

NV-Raw2Insights-US Simulations is a simulated full synthetic aperture (FSA)
ultrasound dataset for training and evaluating neural networks on sound speed
estimation, phase aberration correction, and tissue segmentation. Each sample is
a single-frame FSA acquisition from a 180-element linear array simulated (k-Wave)
over a heterogeneous tissue phantom containing cysts. It provides raw baseband IQ
channel data alongside ground-truth sound speed maps, binary cyst segmentation
masks, and phase aberration values. **Data type: simulated.**

Source dataset: <https://huggingface.co/datasets/nvidia/NV-Raw2Insights-US>

## Dataset Contributor(s)

NVIDIA Corporation. Contact: [wsimson@nvidia.com](mailto:wsimson@nvidia.com).

## Dataset Creation Date

12/01/2025

## License / Terms of Use

[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/legalcode.en).
The data is cleared for this license (synthetic data, no patient information).

## Intended Usage

Developing and benchmarking methods for ultrasound image reconstruction
(learned beamforming), sound speed estimation, phase aberration correction, and
tissue segmentation from raw channel data.

## Dataset Characterization

- **Data Collection Method:** synthetic (k-Wave acoustic simulation)
- **Labeling Method:** synthetic ground truth (from simulation parameters)
- **Acquisition system:** simulated 180-element linear array (10L4-style),
  full synthetic aperture; sampling ~13.3 MHz, center frequency ~6.5 MHz,
  background sound speed 1540 m/s.

## Dataset Format

Submitted in the [`zea` file format](https://zea.readthedocs.io/en/v0.1.0a2/data-acquisition.html)
(one HDF5 file per acquisition). `convert.py` maps the source HF Arrow features
onto `zea` groups: raw IQ channel data, stored B-modes, the sound-speed map, the
segmentation, scan parameters, and the per-sample phase-error metric. B-modes are
log-compressed to 8-bit before storage. Each spatial map carries a per-pixel
`coordinates` array (the point-based openh-rf spec) rather than a bounding-box
extent; `convert.py` builds these with `zea.beamform.pixelgrid.cartesian_pixel_grid`.

Per-sample contents of the converted HDF5:

| Group / field | Shape | Dtype | Units | Description |
|---|---|---|---|---|
| `data/raw_data` | `[1, n_tx, n_ax, n_el, 2]` | float32 | -- | Raw baseband IQ channel data; last axis is `[I, Q]` |
| `data/image` | `[1, z, x]` (+ `coordinates` `[z, x, 3]`) | uint8 | dB | Stored DAS B-mode (log-compressed) |
| `data/bmode_focused` | `[1, z, x]` (+ `coordinates` `[z, x, 3]`) | uint8 | dB | Stored DBUA aberration-corrected B-mode |
| `data/sos_map` | `[1, z, x]` (+ `coordinates` `[z, x, 3]`) | float32 | m/s | Ground-truth speed-of-sound map (coarser grid than the B-mode) |
| `data/segmentation` | `[1, z, x, 2]` (+ `coordinates` `[z, x, 3]`) | bool | -- | Cyst masks; `labels = [background, inclusion]` |
| `scan/*` | -- | -- | -- | Probe geometry, sampling/center/demod frequency, t0, sound speed, … |
| `metrics/common_midpoint_phase_error` | `[1]` | float32 | radians | Per-sample phase aberration error |

All `coordinates` arrays are per-pixel Cartesian positions in metres, last axis
`[x, y, z]` (y = 0 for these 2-D maps).

## Dataset Quantification

- 923 samples (830 train / 93 validation) in the source dataset.
- ~265 MB per sample; ~245 GB total for the full source dataset.
- This example converts a single streamed sample (~250 MB HDF5).

## Subject Metadata

Not applicable — fully synthetic phantom data; no human or animal subjects, no PHI.

## Data Validation

[`reconstruct.py`](reconstruct.py) builds a `zea.Pipeline` of DAS beamforming →
envelope detection → normalization → log-compression **in code** and reconstructs
a B-mode directly from `raw_data` — showing the raw-to-image flow without any
config file. It also saves the pipeline to [`pipeline.yaml`](pipeline.yaml) as a
shareable recipe. Comparing the reconstruction against the stored B-mode is a
sanity check that the acquisition parameters and probe geometry are recorded
correctly, and serves as a reproducible reference reconstruction. The script also
renders the speed-of-sound map, a SoS-corrected reconstruction, and the
segmentation overlay (7-panel figure).

## Known Issues

- The source HF dataset uses mixed units: `bmode_extent` is in millimetres while
  `sound_speed_extent` and `elpos` are in metres. `convert.py` normalizes these
  to metres on write.
- The source `bmode_extent` z-axis ordering is `[x_min, x_max, z_max, z_min]`
  (z_max before z_min); `convert.py` reorders it to the `zea` convention.

## Ethical Considerations

NVIDIA believes Trustworthy AI is a shared responsibility and we have established
policies and practices to enable development for a wide array of AI applications.
This is fully synthetic data with no patient information. When downloaded or used
in accordance with our terms of service, developers should ensure this dataset
meets requirements for the relevant industry and use case. Please report quality,
risk, or security concerns
[here](https://www.nvidia.com/en-us/support/submit-security-vulnerability/).

## Citation

```bibtex
@misc{nv_raw2insights_us_simulations_2026,
  title={NV-Raw2Insights-US Simulations},
  author={Simson, Walter and Huver, Sean},
  year={2026},
  publisher={NVIDIA Corporation},
  howpublished={\url{https://huggingface.co/datasets/nvidia/NV-Raw2Insights-US}},
  license={CC BY 4.0}
}
```
