---
name: ubc-module-a
pretty_name: "UBC Module A Corrected Synthetic-Channel S-WAVE Phantom Dataset"
license: cc-by-4.0
task_categories:
  - image-to-image
tags:
  - openh-rf
  - zea
  - ultrasound
  - rf
  - elastography
  - phantom
  - synthetic-data
  - 3d
language:
  - en
size_categories:
  - 1K<n<10K
---

# UBC Module A — Synthetic-Channel S-WAVE Liver Fibrosis Phantom

![Example reconstruction](./assets/module_A.png)

*Scan-converted scanline B-mode of a CIRS 039 liver fibrosis phantom, reconstructed from the synthetic channel data in [`acquisitions/`](https://huggingface.co/datasets/nvidia/OpenH-RF/tree/main/ubc/module_A/acquisitions).*

## Dataset Description

This submission contains eight 3-D Shear-Wave Absolute Vibro-Elastography (S-WAVE) acquisitions of CIRS model 039 Shear Wave Liver Fibrosis Phantom samples. The source scanner export contains beamformed 64-line RF rather than measured pre-beamforming channel capture. Accordingly, every submitted zea `raw_data` frame (stored at `/tracks/track_0/data/raw_data`) is explicitly labeled **in-silico/synthetic**: a dense point-scatterer field is estimated from one corrected source line-RF frame and forward-simulated through a documented 64-transmit, 128-receive-element model.

The files are physically delay-consistent and reconstruct with zea-native scanline delay-and-sum. They are not recovered or measured scanner channel data, and they must not be represented as such.

## Dataset Contributor(s)

- Zongze Li <zongze@student.ubc.ca> (dataset-preparation contact)
- Yu Chung Lee
- Qi Zeng
- Wanwen Chen
- Zijian Wu
- Yuxin Chen
- Patrick Boyan Chen
- Michael Frew
- Tajwar Abrar Aleef
- Hamid Moradi
- Mohammad Honarvar
- Septimiu E. Salcudean
- Robert Rohling
- The University of British Columbia (UBC), Department of Electrical and Computer Engineering and School of Biomedical Engineering

## Dataset Creation Date

09/01/2026 for this corrected zea-beamformable synthetic-channel package. The source phantom acquisitions predate this packaging.

## License / Terms of Use

[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/legalcode.en). Retain attribution and identify modifications when reusing the data.

## Intended Usage

The package supports raw-to-B-mode reconstruction tests, ultrasound beamforming research, synthetic-channel modeling, per-plane RF analysis, and 3-D placement using the retained motor-plane geometry. The original proposal described derived S-WAVE elasticity estimates or maps; those products are not available in this release due to missing data. `/custom/labels/factory_elasticity_kpa` is the CIRS factory-rated nominal stiffness, not a derived S-WAVE estimate.

## Dataset Characterization

- Data Collection Method: physical phantom source acquisition followed by a deterministic in-silico channel simulation.
- Labeling Method: CIRS factory-rated nominal phantom elasticity.
- Acquisition System: Ultrasonix/Sonix with 4DEC9-5/10 end-firing 3-D probe.
- Submitted Data Tier: phantom / simulation.
- Simulation Framework: custom deterministic NumPy/SciPy forward simulator; files and reconstruction were validated with zea 0.1.4.

Acquisition and simulation details:

- Source system: Ultrasonix/Sonix with 4DEC9-5/10 end-firing 3-D probe.
- Source content: 20 motor planes × 25 retained temporal RF frames × 64 beamformed scan lines × 5,196 axial samples per case.
- Corrected RF ordering: the 108 stored 16-line events per plane contain two complete setup images at events 0-3 and 4-7, followed by four sector-major groups of 25 temporal frames. Temporal frame `k` is assembled from raw events `[8+k, 33+k, 58+k, 83+k]`.
- Temporal frames: all corrected source frames 0-24 are retained; none are deleted or wrapped.
- Cases / nominal stiffnesses: 1.83, 2.8, 6.2, 6.39, 7.79, 11.63, 17.47, and 21.23 kPa.
- Source line-RF sampling frequency: 40 MHz.
- Source temporal sampling: 250 Hz (4 ms between retained RF frames within a plane); 20 motor planes span approximately 27.78° from first to last centre.
- Simulated channel sampling frequency: 20 MHz.
- Transmit/demodulation center frequency: 4 MHz.
- Sound speed used by simulation and reconstruction: 1,540 m/s.
- Probe geometry: 128 elements on a 10.0-mm-radius convex arc with 0.17-mm pitch and 6.5-mm elevation height.
- Sector: 64 focused lines spanning 124.68°; the manufacturer-listed 149° value is the extended-sector capability, not the normal sector used here.
- Transmit focus: 30 mm; modeled transmit aperture: F/1.5.
- Simulated inter-transmit interval: 250 microseconds; the final interval in each one-frame file is zero because no later transmit is stored in that file.
- Scatterers: 256 per source line (16,384 per output frame), with deterministic frame-specific sub-line and sub-sample jitter.
- Channel trace: 3,546 samples (177.3 microseconds), including a final exact-zero tail of 400 samples (20 microseconds).
- Quantization: `int16`, scaled to an absolute peak of 26,000; no sample reaches int16 full scale.

## Processing the Dataset

The acquisitions can be processed with the `pipeline.yaml` definition in this folder and the [zea library](https://github.com/tue-bmd/zea).

`zea` streams the data from the Hugging Face Hub and processes it according to the pipeline. You can try it out with the following command:

```bash
zea process \
  --dataset hf://nvidia/OpenH-RF/ubc/module_A/acquisitions/case_1.83/ubc_swave_cirs_1.83_p10_f13.hdf5 \
  --config hf://nvidia/OpenH-RF/ubc/module_A/pipeline.yaml
```

Alternatively, you can use the `reconstruct.py` [script](https://github.com/open-h/OpenH-RF/blob/main/datasets/ubc/module_A/reconstruct.py) as provided in the [OpenH-RF GitHub repository](https://github.com/open-h/OpenH-RF).

`reconstruct.py` reconstructs one frame (default `case_1.83/ubc_swave_cirs_1.83_p10_f13.hdf5`); [`reconstruct_multiframe.py`](https://github.com/open-h/OpenH-RF/blob/main/datasets/ubc/module_A/reconstruct_multiframe.py) reconstructs the temporal sequence at one motor plane (`CASE_ID`, `PLANE`, `N_FRAMES`) into an animated GIF.

## Dataset Format

[zea v0.1.4](https://github.com/tue-bmd/zea)

There are 8 × 20 × 25 = **4,000** one-frame HDF5 files. One file per source frame keeps full zea schema validation and reconstruction memory-bounded. For motion analysis, group files by case and motor plane, then order `f00` through `f24`; `/custom/source_provenance/source_timing` retains the source clock index, within-plane temporal offset, and relative plane timestamp.

```text
module_A/
  acquisitions/
    case_1.83/
      ubc_swave_cirs_1.83_p00_f00.hdf5
      ...
    case_2.8/
      ...
    ...
  README.md
  pipeline.yaml
```

Each HDF5 file contains the following per-sample features:

Numeric arrays use zea 0.1.4's native frame-chunked Blosc/Zstd plus bitshuffle compression; reading these arrays requires `hdf5plugin`, which is imported by zea.

| Name | Shape | Dtype | Units | Description |
|---|---:|---|---|---|
| `/tracks/track_0/data/raw_data` | `(1, 64, 3546, 128, 1)` | `int16` | scaled ADC-like counts | Synthetic RF ordered frame, transmit, axial sample, receive element, RF component. |
| `/probe/probe_geometry` | `(128, 3)` | `float32` | m | Curved-array element positions. |
| `/tracks/track_0/scan/polar_angles` | `(64,)` | `float32` | rad | Focused transmit angles. |
| `/tracks/track_0/scan/t0_delays` | `(64, 128)` | `float32` | s | Per-transmit element delays. |
| `/tracks/track_0/data/image/values` | `(1, 256, 64, 1)` | `uint8` | display intensity | Native line-RF reference display; not used as a reconstruction input. |
| `/custom/source_provenance/source_native_line_rf` | `(64, 5196)` | `int16` | source ADC counts | Preserved source beamformed line RF for this selection. |
| `/custom/source_provenance/source_event_indices` | `(4,)` | `int32` | zero-based event index | Original 16-line E-scan event selected for sectors 0-3. |
| `/custom/simulation/scatterer_positions` | `(16384, 3)` | `float32` | m | Point-scatterer positions used for channel simulation. |
| `/custom/source_provenance/*` | mixed | mixed | documented per field | Source indices, plane transform, timing, and excitation settings. |

Synthetic provenance is written at the HDF5 root and on the raw-data dataset: `synthetic=true`, `in_silico=true`, and `data_origin=in-silico/synthetic`.

## Dataset Quantification

- Number of source acquisitions: 8.
- Number of motor planes per acquisition: 20.
- Number of retained temporal RF frames per plane: 25.
- Number of submitted HDF5 samples: 4,000.
- Train / validation / test split: not predefined.
- Per-sample raw tensor: `1 × 64 × 3546 × 128 × 1`, `int16`.
- Per-sample source line-RF tensor: `64 × 5196`, `int16`.
- Exact HDF5 payload size: **108,889,767,936 bytes** (108.890 GB; 101.412 GiB).

## Subject Metadata

The source consists of eight phantom acquisitions only, one for each listed factory-rated stiffness. There are no human or animal subjects and no subject demographics. The phantom model is CIRS model 039 Shear Wave Liver Fibrosis Phantom.

## Data Validation

The contributor reports validation with Python 3.12.3 and zea 0.1.4. The contributor's reconstruction reads only the zea `raw_data` field and acquisition parameters, not the stored image or preserved source line RF:

```text
Cast to float32
  -> RF demodulation
  -> zea delay_and_sum with enable_scanline=true
     and enable_aligned_apodization=true
  -> Envelope detection
  -> 99.5th-percentile normalization
  -> -50..0 dB log compression
  -> sector scan conversion
  -> PNG
```

In scanline mode the output has 64 angular lines—one per stored focused transmit. zea constructs the one-line-per-transmit grid and the one-hot aligned transmit mask internally; no custom `flat_pfield` or transmit-weight code is used.

`pipeline.yaml` records the reconstruction configuration. `zlims: [0.0001, 0.100023]` are line depths from each transmit origin on the curved element surface.

The contributor reports structural checks across all files, plus full zea schema validation and raw-only reconstruction on three distributed samples from each case (24 samples). For those samples, the preserved source line RF was also compared with the original E-scan events.

This HF release includes the HDF5 files, this card, and the pipeline configuration. Review outputs, standalone reconstruction scripts, and validation sidecars are not included.

## Known Issues

- The measured source is beamformed line RF. The submitted 128-channel data are deterministic forward simulations conditioned on that source.
- The simulation preserves source-derived spatial and temporal contrast but cannot recover proprietary scanner receive processing or true measured element-level noise/coupling.
- The stored image is a reference only and is deliberately excluded from the reconstruction path.
- Mechanical excitation frequencies (40, 50, and 60 Hz) are simultaneous. Configured phases are retained in source setting units; absolute actuator-to-ultrasound phase synchronization is not claimed.
- A scanner TGC curve, probe bandwidth, and exact transmit waveform were not available. Reconstruction therefore applies no TGC and uses the documented simulation pulse.

## Ethical Considerations

The data are phantom acquisitions only. There are no human subjects, no PHI, and no patient demographics.
