# Dataset Title

## Dataset Description

_One short paragraph describing the data: acquisition modality, anatomy, task focus, and intended research contribution. State whether data is clinical, phantom, simulated, or in vivo animal._

## Dataset Contributor(s)

_Contributing organization and primary point of contact._

## Dataset Creation Date

_MM/DD/YYYY_

## License / Terms of Use

CC BY 4.0. _Confirm data is cleared for this license (IP, patient consent, institutional review)._

## Intended Usage

_e.g. Advanced beamforming, sound speed estimation, aberration correction._

## Dataset Characterization

- **Data collection method:** _clinical / phantom / synthetic / animal_
- **Labeling method:** _N/A / human-annotated / synthetic ground truth / derived_
- **Acquisition system:** Verasonics Vantage. _Probe geometry, element count, center frequency X MHz, sampling rate Y MHz._

## Dataset Format

zea file format. _Note any pre-processing applied before packaging (demodulation, decimation, etc.)._

## Dataset Quantification

- **Samples / frames:** _e.g. 100 acquisitions_
- **Train / val / test split:** _e.g. N/A_
- **Total size on disk:** _e.g. 3 GB_

| Field | Shape | dtype | Units | Description |
|---|---|---|---|---|
| `raw_data` | `(N_frames, N_tx, N_ax, N_el, 1)` | float32 | — | Raw RF channel data |
| `image.values` | `(N_frames, H, W, 1)` | uint8 | — | Pre-computed B-mode |

## Subject Metadata

_Aggregate statistics only — no PHI. e.g.: N subjects, age range, sex distribution, anatomical region, pathology distribution, scanner/probe model._

## Data Validation

A `zea.Pipeline` (DAS → envelope detection → normalization → log compression) is defined in `pipeline.yaml`. Run `reconstruct.py` to reproduce the reference B-mode image.

## Known Issues

_Calibration quirks, missing fields, unit inconsistencies, artifacts, edge cases. Write N/A if none._

## Ethical Considerations

_Consent status, de-identification approach, IRB or equivalent approval, usage caveats._
