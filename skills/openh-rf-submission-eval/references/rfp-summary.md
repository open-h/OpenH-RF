# OpenH-RF RFP summary

Condensed reference for evaluators. Full RFP is the authoritative source — pull it up if a corner case arises.

## What OpenH-RF is

A collaborative dataset initiative (Stanford, TU Eindhoven, NVIDIA) targeting ≥20,000 pre-beamformed ultrasound channel-capture measurements with task labels, released CC BY 4.0 on Hugging Face. Goal: enable end-to-end foundation models for ultrasound.

## Accepted task groups

- **6.1 Generalized Reconstruction** — compressed sensing, super-resolution, reverb suppression, adaptive transmit, aberration correction, harmonic imaging
- **6.2 Blood Flow** — color/power Doppler, slow flow, functional ultrasound, CEUS, ULM
- **6.3 Quantitative** — attenuation, sound speed, backscatter coefficient
- **6.4 Motion** — tissue Doppler, shear wave elastography, strain
- **6.5 Interpretation** — segmentation, VQA, narration, radiological reports
- **6.6 Other** — continuous monitoring, USCT, passive cavitation, molecular imaging, neuromodulation, histotripsy

## Tier weighting

For steering-group prioritization, not for pass/fail evaluation:

| Tier | Weight |
|---|---|
| In-vivo human (clinical platform) | ×100 |
| In-vivo human (research platform) | ×40 |
| In-vivo animal | ×20 |
| Ex-vivo animal tissue | ×4 |
| Phantom / table-top | ×1 |
| Simulation | ×1 |

## Hard requirements

- Channel-capture (pre-beamformed) data, not beamformed images
- *zea* file format
- CC BY 4.0 license
- HIPAA Safe Harbor (or local equivalent) for human data
- ARRIVE 2.0 for animal data
- IRB approval where applicable
- No third-party IP encumbrances

## Encouraged but not required

- Time-aligned narration/description
- Anonymized correlated patient metadata (BMI, age, gender)
- Operator expertise labels (expert/intermediate/novice)
- Quality and success labels (excellent/good/poor; failure/recovery/success)
- Time-aligned video of acquisition
- 6DoF probe tracking

## Timeline (for context only — submissions arriving outside these windows are still evaluated normally)

- RFP released: Mar 16, 2026
- Proposal deadline: Jun 10, 2026
- Data collection window: May 1 – July 12, 2026
- Cleanup/standardization: through Aug 1, 2026
- Model training: Aug 1 – Sep 1, 2026
- Public release: October 2026
