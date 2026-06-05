<div align="center">

<img src="assets/openh-rf-header.jpg" alt="OpenH-RF" width="100%">

# OpenH-RF

[![Discord](https://img.shields.io/badge/Discord-Join%20Community-7289DA?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/gNTJeUsH2B)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge)](LICENSE)

*Enabling advanced ultrasound imaging techniques and evaluation through free, openly available and high-quality ultrasound channel capture data.*

</div>

---

## About

OpenH-RF is a collaborative initiative led by [Stanford University](https://med.stanford.edu/ultrasound.html), [Eindhoven University of Technology (TU/e)](https://www.tue.nl/en/research/research-groups/signal-processing-systems/biomedical-diagnostics) and [NVIDIA](https://www.nvidia.com/) to build a large-scale, openly licensed dataset of pre-beamformed (channel capture) medical ultrasound measurements. *The goal:* train general-purpose foundation models capable of multi-task *raw-to-insight* inference across echocardiography, general, fetal and transcranial imaging, blood flow measurement and ultrasound inverse problems.

We aim to curate **20,000+** real and synthetic channel capture measurements spanning reconstruction, flow, quantitative imaging, motion estimation and interpretation tasks — released under **CC BY 4.0**.

## How to Participate

1. **Review the RFP** — Read the [Request for Proposals](assets/OpenH-RF%20Request%20for%20Proposals%20(RFP).pdf) for technical scope, eligibility and evaluation criteria.
2. **Submit a Proposal** — Prepare a concise proposal (≤ 5 pages) describing your dataset, collection methodology and target tasks. Submit to [this Google Form](https://forms.gle/tqiqYSnnar1AekB19).
3. **Contribute Data** — Once approved, prepare your dataset in the OpenH-RF format, implemented in [`zea`](https://github.com/tue-bmd/zea) as documented [here](https://zea.readthedocs.io/en/v0.1.0a1/data-acquisition.html), along with a datacard specifying the CC BY 4.0 license. Approved contributors are given a dedicated shared storage location (S3 or Google Drive) for delivery and a Discord channel for coordination.
4. **Co-author the Release** — Approved contributions are included in the public dataset and foundation model release — contributors are named co-authors in related publications upon project completion.

## Key Dates

| Milestone | Date |
|-----------|------|
| RFP released | March 16, 2026 |
| Proposal submission deadline | June 10, 2026 |
| Data collection window | May – July 2026 |
| Dataset delivery deadline | July 12, 2026 |
| Model training & validation | August – September 2026 |
| Public release (dataset + foundation model) | October 2026 |

## Steering Committee

| Role | Name | Affiliation |
|------|------|-------------|
| AI Lead | Prof. Ruud J.G. van Sloun | TU/e |
| Ultrasound Lead | Prof. Jeremy Dahl | Stanford University |
| Industry Lead | Dr. Walter Simson | NVIDIA |

## Dataset Format

The OpenH-RF format is implemented using the [`zea`](https://github.com/tue-bmd/zea) ultrasound toolbox. See the `zea` documentation for the [data specification](https://zea.readthedocs.io/en/v0.1.0a1/data-acquisition.html). Each example below writes a single `.hdf5` file using `zea` and demonstrates the fields expected for a given modality:

| Example | Modality |
|---------|----------|
| [`examples/saving/echocardiography_example.py`](examples/saving/echocardiography_example.py) | Cardiac ultrasound with strain map, ECG, demographics, annotations, quality metrics |
| [`examples/saving/color_doppler_example.py`](examples/saving/color_doppler_example.py) | B-mode + color Doppler velocity map, ECG, annotations |
| [`examples/saving/segmentation_map_example.py`](examples/saving/segmentation_map_example.py) | Raw RF data with per-frame segmentation masks and view labels |
| [`examples/saving/verasonics_example.py`](examples/saving/verasonics_example.py) | Converting a Verasonics `.mat` workspace to OpenH-RF |
| [`examples/nv-raw2insights-us/`](examples/nv-raw2insights-us/) | Streaming a sample from the public [NV-Raw2Insights-US](https://huggingface.co/datasets/nvidia/NV-Raw2Insights-US) dataset, converting to OpenH-RF, and beamforming back to a B-mode |
| [`examples/save_pipeline_example.py`](examples/save_pipeline_example.py) | Saving a `zea` processing pipeline as a reusable YAML config |

## Setup

This repo uses [`uv`](https://docs.astral.sh/uv/) for environment + dependency management. Install it once: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

```bash
git clone https://github.com/open-h/OpenH-RF
cd OpenH-RF
uv sync
export KERAS_BACKEND=jax
uv run python examples/saving/echocardiography_example.py
```

`uv sync` creates `.venv/` and installs dependencies listed in `pyproject.toml`. Run any script with `uv run python <script>.py`, or activate the venv with `source .venv/bin/activate`.

Pick a backend / accelerator with extras:

| Use case | Command |
|----------|---------|
| JAX (CPU, default)   | `uv sync` |
| JAX + CUDA           | `uv sync --extra gpu` |
| PyTorch              | `uv sync --extra torch` (Linux pip wheels include CUDA by default) |
| TensorFlow (CPU)     | `uv sync --extra tf` |
| TensorFlow + CUDA    | `uv sync --extra tf-gpu` |

Set the matching `KERAS_BACKEND` (`jax`, `torch`, or `tensorflow`) before running examples.

> [!NOTE]
> On Windows, use WSL2.

## Contact

- **Technical questions** — [openh.data+rf@gmail.com](mailto:openh.data+rf@gmail.com)
- **Administrative questions** — [wsimson@nvidia.com](mailto:wsimson@nvidia.com)
- **Community** — [Join our Discord](https://discord.gg/gNTJeUsH2B)

## License

Code in this repository is licensed under the [Apache License 2.0](LICENSE). The released dataset (when published) will be licensed under CC BY 4.0.
