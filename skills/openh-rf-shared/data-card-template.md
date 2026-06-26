# OpenH-RF data card template (canonical)

Copy of the contributor-facing template. Use this as the ground truth when checking dimension 4.

The data card is delivered as a **single `README.md`** at the dataset root. Hugging Face renders `README.md` as the dataset landing page (<https://huggingface.co/docs/hub/datasets-cards>), so this is the only user-facing document — there is no separate `DATA_CARD.md`.

## YAML frontmatter (required)

The `README.md` must open with a YAML block between `---` fences. HF parses this for license, search, and modality. Minimum fields:

```yaml
---
pretty_name: "OpenH-RF — <contributor / dataset name>"
license: cc-by-4.0
task_categories:
  - <hf-task>            # e.g. image-segmentation, image-classification
tags:
  - ultrasound
  - rf                   # or iq, depending on data_type
  - openh-rf
  # optional modality override: 3d, audio, geospatial, image, tabular, text, timeseries, video
  - 3d
language:
  - en
size_categories:
  - n<1K                 # or 1K<n<10K, 10K<n<100K, etc.
---
```

Declaring `license: cc-by-4.0` in the frontmatter is what makes HF display the license badge on the dataset page — a separate `LICENSE` file is still good practice, but the frontmatter line is the load-bearing one for the HF UI.

The markdown sections below all live in the **body** of the `README.md`, after the closing `---` of the frontmatter.

---

## Dataset Description
One short paragraph: what the data is, what it captures (acquisition modality, anatomy, task focus), and the intended research contribution. Note whether it is clinical, phantom, simulated, or in vivo animal data.

## Dataset Contributor(s)
Contributing organization and primary point of contact.

## Dataset Creation Date
MM/DD/YYYY.

## License / Terms of Use
OpenH-RF requires **CC BY 4.0**. Confirm that the contributed data is cleared for this license (IP, patient consent, institutional review).

## Intended Usage
Briefly describe the application or task — e.g., sound speed estimation, advanced beamforming, segmentation, aberration correction.

## Dataset Characterization
- **Data Collection Method:** clinical / phantom / synthetic / animal
- **Labeling Method:** N/A, human-annotated, synthetic ground truth, derived
- **Acquisition system:** transducer geometry, element count, center frequency, sampling rate

## Dataset Format
All sub-datasets are submitted in the *zea* file format. Note any pre-processing applied before packaging — refocus/resample IP abstraction, demodulation, decimation, etc.

## Dataset Quantification
- Number of samples / frames / acquisitions
- Train / validation / test split (if applicable)
- Total size on disk
- Per-sample feature table (name, shape, dtype, units, description)

## Subject Metadata
Aggregate statistics only — no PHI. Include where applicable: number of subjects, age range, sex distribution, anatomical region(s), pathology distribution, scanner/probe model.

## Data Validation
A `zea.Pipeline` that reconstructs a representative sample from the raw channel data (e.g., DAS → envelope → normalization → log compression to B-mode). Include the pipeline script and 1–2 example output images.

## Known Issues
Calibration quirks, missing fields, unit inconsistencies, artifacts, edge cases.

## Ethical Considerations
Consent status, de-identification approach, IRB or equivalent approval, any usage caveats.
