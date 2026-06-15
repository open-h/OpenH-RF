# PALA — In Vivo Rat Brain ULM

## Dataset Description

In vivo ultrasound data of a rat brain acquired for Ultrasound Localization Microscopy (ULM), where flowing intravascular microbubbles are localized to map the cerebral microvasculature beyond the diffraction limit. The brain was imaged after craniotomy (skull removal) in a Sprague-Dawley rat at a 1000 Hz frame rate with a 15 MHz linear probe and plane-wave compounding. This is in vivo animal data; it is one acquisition file from the PALA "in vivo rat brain" dataset released to benchmark microbubble-localization algorithms.

## Dataset Contributor(s)

Chavignon Arthur, Baptiste Heiles, Hingot Vincent, Lopez Pauline, Teston Eliott, Couture Olivier — Sorbonne Université, CNRS, INSERM, Laboratoire d’Imagerie Biomédicale, Paris, France. Source data published on [Zenodo (record 7883227)](https://doi.org/10.5281/zenodo.7883227).

## Dataset Creation Date

Source data deposited on [Zenodo (2023)](https://doi.org/10.5281/zenodo.7883226); converted to zea format 2026/06/13.

## License / Terms of Use

CC BY 4.0 (see `LICENCE`). Attribution required — cite Heiles et al., *Nature Biomedical Engineering*, 2022 ([doi.org/10.1038/s41551-021-00824-8](https://doi.org/10.1038/s41551-021-00824-8)).

## Intended Usage

Microbubble localization and tracking, ULM super-resolution vascular mapping, and benchmarking of localization/beamforming algorithms.

## Dataset Characterization

- **Data collection method:** in vivo animal (Sprague-Dawley rat brain, craniotomy)
- **Labeling method:** unlabeled (no ground-truth annotations; in vivo angiography)
- **Acquisition system:** Verasonics, L22-14v linear array, 128 elements, 0.1 mm pitch (12.7 mm aperture), 15.6 MHz center frequency, 5-angle plane-wave compounding (−6° to +6° in 3° steps), 1000 Hz frame rate. IQ-demodulated data sampled at 15.6 MHz, sound speed 1540 m/s.

## Dataset Format

Submitted in the [`zea` file format](https://zea.readthedocs.io/en/v0.1.0a3/data-acquisition.html)
(one HDF5 file per acquisition). The source Verasonics BS100BW samples are de-interleaved into a complex IQ representation (I and Q stored as the final channel dimension) during conversion (`convert.py`). The packaged sample is a single acquisition file (`RF_002`) of the full ~200,000-frame dataset. This used as an example script for ULM submissions to OpenH-RF.

## Dataset Quantification

- **Samples / frames:** 800 frames (one acquisition file; full Zenodo dataset ≈200,000 frames across 25 files)
- **Train / val / test split:** N/A (benchmark/reference data, no predefined split)
- **Total size on disk:** ~588 MB (`pala_sample.hdf5`)

| Field | Shape | dtype | Units | Description |
|---|---|---|---|---|
| `raw_data` | `(800, 5, 256, 128, 2)` | float32 | — | IQ channel data: frames × transmits × axial × elements × {I, Q} |
| `scan.polar_angles` | `(5,)` | float32 | rad | Plane-wave steering angles |
| `scan.t0_delays` | `(5, 128)` | float32 | s | Transmit delays per element |
| `probe.probe_geometry` | `(128, 3)` | float32 | m | Element positions |

## Subject Metadata

1 Sprague-Dawley rat, brain imaged at a coronal section after craniotomy, with continuous intravenous microbubble (ultrasound contrast agent) injection.

## Data Validation

A `zea.Pipeline` (DAS → tissue suppression → envelope detection → normalization → log compression) is defined in `pipeline.yaml`. Run `reconstruct.py` to reproduce a reference B-mode image from the IQ data.

## Known Issues

- Element width is not stored in the source file and is estimated at 0.09 mm (90% of the 0.1 mm pitch).

## Ethical Considerations

Animal experiments described in the source publication (Heiles et al., 2022) were carried out under the relevant institutional and national ethical approvals for animal research. Animal preparation and contrast-agent perfusion performed at the CYCERON biomedical imaging platform (Caen, France). No human subjects; no PHI.
