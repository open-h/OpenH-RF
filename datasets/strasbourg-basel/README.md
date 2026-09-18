---
pretty_name: "OpenH-RF — BoneSRF Robot-Tracked Fractured-Femur Phantom Dataset"
license: cc-by-4.0
task_categories:
  - other
tags:
  - ultrasound
  - rf
  - openh-rf
  - tracked-ultrasound
  - robot-tracked
  - probe-pose
  - phantom
  - bone
  - fracture
  - beamforming
  - ct
  - segmentation
language:
  - en
size_categories:
  - n<1K
---

<p align="center">
  <img src="assets/bonesrf_logo.png" alt="BoneSRF" width="200">
</p>

# BoneSRF

**BoneSRF** (Bone Surface Reflection) is an ultrasound channel-data dataset built
around a simple question: can pre-beamformed RF data recovered from a handheld,
point-of-care scanner support bone-surface / fracture-reflection research? It
contributes three 3D-printed, fractured femur phantoms — scanned, beamformed-RF-
inverted, and packaged in the OpenH-RF `zea` format — to the OpenH-RF initiative.

Nine scans in total: each of the three phantoms was swept three times (`distal`,
`proximal`, `wholebone`), giving nine `zea` HDF5 files in [`data/`](data/). Every
scan is **robot-tracked** — the probe was mounted on a robotic arm and its pose
independently recorded — and every file also carries that phantom's **CT scan and
multi-label segmentation** inside it.

## Dataset Description

The channel data in this dataset is **not a direct per-element sensor recording**.
A Clarius handheld probe does not expose its raw per-element channel data, only its
own internally beamformed RF output. Every `raw_data` array here is therefore a
numerical estimate: the per-element channel data consistent with the probe's known
per-scanline focused acquisition geometry (transmit delays, apodization, walking
sub-aperture) that, if beamformed the same way, would reproduce the real Clarius
output. This estimate is recovered by solving a conjugate-gradient least-squares
(CGLS) inversion of a zea `DASOperator` built from that acquisition geometry,
against the real beamformed phantom scans as the inversion target.

This is phantom data — not simulated, clinical, or in-vivo — intended for
full-matrix-capture-style beamforming and image-reconstruction research at a
bone-tissue interface, and as a worked example of recovering pre-beamformed data
from beamformed-only ultrasound exports.

### How the data was generated

1. **Real acquisition.** A Clarius handheld-probe-class linear array (L20HD3) was
   used to scan each phantom, producing the probe's own beamformed RF output — this
   is the *real*, physically acquired data, not simulated.
2. **Inversion.** The beamformed RF is inverted back into pre-beamformed,
   per-element channel data using
   [`das-inverse` (`clarius` branch)](https://github.com/sankethvedula/das-inverse/tree/clarius)
   — a CGLS solver over a `zea.inverse.DASOperator` forward model of the probe's
   focused, walking-sub-aperture transmit sequence (`invert_clarius_beamformed.py`).
   The result is what this dataset calls "simulated" channel data: not
   sensor-captured, but numerically consistent with the real beamformed acquisition
   it was inverted from.
3. **Packaging.** The inverted channel data, transmit-sequence metadata, probe
   geometry, per-frame probe pose, and the phantom's CT + segmentation are written
   out as one `zea` HDF5 file per scan, matching the OpenH-RF format spec.

### Probe tracking

Every scan is **tracked**: the probe was mounted on a robotic arm, and its pose was
independently recorded via a trakSTAR electromagnetic tracking system with a fixed
fCal image-to-probe calibration. The tracking stream is packaged **per-frame
indexed** inside each file's metadata (`metadata/probe_pose`: translation, rotation,
timestamps) — `metadata/probe_pose[i]` corresponds directly to `raw_data[i]`, index
for index. It does not need a separate sidecar file, and the raw tracking capture is
not shipped — only the recovered, aligned pose stream.

### The three phantoms

Each phantom is a 3D-printed femur, modeled from a CC BY 4.0–licensed femur bone
dataset, with a fracture pattern simulated differently for each of the three. Each
printed femur is immersed in ultrasound-coupling gel and scanned by a robotic arm,
which gives repeatable, controlled probe trajectories instead of a freehand scan.
Each phantom is scanned three times, at three positions along the bone:

- **`distal`** — a sweep over the distal region of the femur
- **`proximal`** — a sweep over the proximal region of the femur
- **`wholebone`** — a sweep covering the full length of the femur

**Fracture design:** `REQUIRES_CONTRIBUTOR` — the specific fracture pattern
simulated in each phantom (location; type: transverse / oblique / comminuted /
hairline; displacement) has not yet been documented. The CT segmentation carried in
each file is ground truth for the physical phantom geometry in the meantime.

## Folder structure

```
BoneSRF/
├── README.md              ← this file (dataset overview + data card for all nine scans)
├── LICENCE                (CC BY 4.0)
├── pipeline.yaml          (saved zea.Pipeline — one pipeline, shared by all nine scans)
├── reconstruct.py         (runs pipeline.yaml on any scan → reference_bmodes/<scan>.png)
├── data/
│   ├── phantom1_distal.hdf5      (zea channel data + per-frame probe pose + CT)
│   ├── phantom1_proximal.hdf5
│   ├── phantom1_wholebone.hdf5
│   ├── phantom2_*.hdf5           (same three sweeps)
│   └── phantom3_*.hdf5           (same three sweeps)
└── reference_bmodes/
    └── <scan>.png                (one reference reconstruction per scan)
```

Every file in `data/` stands alone: it holds the (CGLS-recovered) pre-beamformed
channel data, the full transmit-sequence and probe metadata needed to beamform it,
the per-frame tracked probe pose, and the CT + segmentation of the phantom it
depicts.

## Reconstructing a B-mode

`reconstruct.py` loads the saved `zea.Pipeline` from `pipeline.yaml` and runs it on
one frame of one scan:

```bash
python reconstruct.py                          # all nine, at their reference frames
python reconstruct.py phantom2_wholebone          # one scan, at its reference frame
python reconstruct.py phantom1_distal --frame 40 --device cpu
```

The pipeline is `cast` → `apply_window` → `beamform` (delay-and-sum with a
physically-motivated per-transmit `pfield` weighting, since this is a per-scanline
focused walking-sub-aperture acquisition rather than full synthetic aperture) →
`keras.ops.abs` → axial-only Gaussian blur → `normalize` → `log_compress`, with
display parameters (dynamic range, p-field settings) also read from `pipeline.yaml`.
Acquisition geometry comes from each file's own `scan`/`probe` groups.

This intentionally avoids `zea.inverse`: that module is for the CGLS inversion that
*produced* these files, not for reconstructing from them. Runtime is ~30 s per frame
on CPU. Each file is a full multi-frame sweep of 20.24 GB to 24.49 GB, but only the requested
frame is read.

## Dataset Contributor(s)

Sidaty El Hadramy, Philippe C. Cattin, Juan Verde — IHU Strasbourg and the
Department of Biomedical Engineering, University of Basel.

## Dataset Creation Date

Original Clarius acquisitions: 19/06/2026 (`phantom1_distal`) and 25/06/2026
(`phantom1_proximal`, acquisition ID `20260625-ihu-04_BoneSRF-01_proximal_robot_r3`).
The acquisition date of the other seven sweeps was not separately recorded — see
[Known Issues](#known-issues). Converted to `zea` format 21/07/2026–05/08/2026 and
re-converted 13/08/2026–14/08/2026 to align probe tracking to `raw_data`
frame-by-frame. CT and segmentation embedded into the files 09/09/2026.

## License / Terms of Use

CC BY 4.0 — see [`LICENCE`](LICENCE). Confirmed by the contributor as cleared for
CC BY 4.0 release (phantom data; no patient consent or third-party IP encumbrance
applies). The CT and segmentation data carried inside the files is released under
the same terms. The femur geometry underlying the 3D-printed phantoms is itself
sourced from a CC BY 4.0–licensed bone model dataset.

## Intended Usage

Full-matrix-capture-style beamforming research on recovered (not directly sensed)
channel data at a bone-tissue interface: delay-and-sum reconstruction, adaptive or
aberration-correction beamforming benchmarking, robot/EM-tracked probe-pose fusion
research, and as a reference example for recovering pre-beamformed data from
beamformed-only ultrasound exports (e.g. other handheld/point-of-care scanners with
the same limitation).

## Dataset Characterization

- **Data Collection Method:** phantom (3D-printed, bone-mimicking femur, immersed in
  ultrasound-coupling gel); scanned with a Clarius handheld-probe-class linear array
  mounted on and moved by a robotic arm; raw channel data recovered via CGLS
  inversion of the probe's beamformed RF output (not a direct per-element
  recording); probe pose independently tracked via a trakSTAR EM tracking system,
  fCal-calibrated.
- **Labeling Method:** a CT scan of each 3D-printed phantom and a multi-label
  segmentation of it (authored in 3D Slicer) are carried **inside each of that
  phantom's three files**, under `custom/ct/` and `custom/ct_segmentation/` — see
  [CT reference imaging](#ct-reference-imaging). There are no annotations on the RF
  data itself.
- **Acquisition system:** Clarius L20HD3, 192-element linear array, 0.130 mm pitch
  (24.8 mm aperture), 10 MHz center frequency, 30 MHz sampling frequency, 1540 m/s
  sound speed, ~5.1 cm imaging depth (1984–2016 axial samples depending on scan),
  single fixed transmit focus at 25.3–25.8 mm (verified: `focus_distances` is
  constant across all 192 transmits within each scan), 192 focused transmits per
  frame (one per lateral scanline, no steering), walking sub-aperture per scanline —
  Hanning-windowed, 47–97 of 192 elements active per transmit (mean ~84, i.e.
  roughly a quarter to a half of the array, narrowest at the array edges).

## CT reference imaging

Each phantom's CT scan and its multi-label 3D Slicer segmentation are carried inside
**every one** of that phantom's three `zea` files, under `custom/ct/` and
`custom/ct_segmentation/`. They are not shipped as separate `.nrrd` sidecars, so no
file depends on another.

| Dataset | Contents |
|---|---|
| `custom/ct/volume` | CT volume, `int16`, stored `(k, j, i)` (slice, row, column) |
| `custom/ct/spacing`, `origin`, `direction`, `affine` | Grid geometry in SI metres; `affine` maps voxel index `(i, j, k, 1)` to an LPS position |
| `custom/ct/nrrd_header` | Verbatim header of the source NRRD (distances in millimetres) |
| `custom/ct_segmentation/labelmap` | Layered binary labelmap on the same grid, `uint8` |
| `custom/ct_segmentation/segment_*` | Per-segment name, label value, layer, colour, bounding box and 3D Slicer ID |

Grid geometry differs per phantom:

| Phantom | CT grid | Stored array | Source spacing (mm) |
|---|---|---|---|
| phantom1 | `512 × 512 × 594` | `(594, 512, 512)` | `0.546875 × 0.546875 × 0.6` |
| phantom2 | `512 × 512 × 574` | `(574, 512, 512)` | `0.50390625 × 0.50390625 × 0.6` |
| phantom3 | `512 × 512 × 594` | `(594, 512, 512)` | `0.5625 × 0.5625 × 0.6` |

Each segmentation has three segments, corresponding directly to the three RF sweeps
of that phantom. **Label values repeat across layers** — 3D Slicer keeps segments on
separate internal labelmap layers — so read a segment's mask as
`labelmap[..., segment_layers[s]] == segment_label_values[s]` rather than treating
the array as one flat labelmap:

| Segment | `segment_label_values` | `segment_layers` | Corresponds to |
|---|---|---|---|
| `BoneSRF-1_Proximal` | 1 | 0 | `phantom1_proximal` |
| `BoneSRF-1_Distal` | 2 | 0 | `phantom1_distal` |
| `BoneSRF-1_Complete` | 1 | 1 | `phantom1_wholebone` |
| `BoneSRF-2_Complete` | 1 | 0 | `phantom2_wholebone` |
| `BoneSRF-2_Distal` | 1 | 1 | `phantom2_distal` |
| `BoneSRF-2_Proximal` | 2 | 1 | `phantom2_proximal` |
| `BoneSRF-3_Proximal` | 2 | 0 | `phantom3_proximal` |
| `BoneSRF-3_Distal` | 3 | 0 | `phantom3_distal` |
| `BoneSRF-3_Complete` | 1 | 1 | `phantom3_wholebone` |

The CT is reference imaging of the physical phantom in scanner (LPS) space. It is
**not spatially registered** to the RF frames or to the tracked probe poses; no
CT↔ultrasound registration is provided with this submission.

## Dataset Format

Submitted in the [`zea` file format](https://zea.readthedocs.io/en/openh-rf-latest/)
as nine HDF5 files in [`data/`](data/), blosc-compressed.

The channel data was recovered from the probe's real, beamformed RF output by
CGLS-inverting a `zea.inverse.DASOperator` built from the known acquisition
geometry. `t0_delays`, `tx_apodizations`, `focus_distances`, `transmit_origins`,
`polar_angles`, and `waveforms_two_way` are copied directly from the values that
inversion's DAS operator was built with — not re-derived or guessed. The source
`.npz` had no explicit `demodulation_frequency`; it was substituted with
`center_frequency` per the standard convention for RF (non-IQ) sources (verified:
`demodulation_frequency` = `center_frequency` = 10 MHz in every file).

Probe pose (`metadata/probe_pose`: translation, rotation, timestamps) was recovered
from the trakSTAR tracking capture via a fixed fCal image-to-probe calibration,
resampled onto each `raw_data` frame's own acquisition time before conversion, and
packaged as a **per-frame indexed signal** (`metadata/probe_pose[i]` ↔
`raw_data[i]`).

CT and segmentation (an addition beyond the original proposal) were copied verbatim
out of the `.nrrd` files that previously shipped alongside the RF data, so that
every file is self-contained; the verbatim source NRRD headers are preserved with
them. Grid geometry is converted from the NRRD's millimetres to zea's SI metres.

**Reading these files requires `h5py` built against HDF5 ≥ 2.0** (e.g. `h5py` ≥
3.16) — see [Known Issues](#known-issues).

### Fields

Every file has the same field structure; `n_frames` and `n_ax` vary per scan (see
[the nine scans](#the-nine-scans)).

| Field | Shape | dtype | Units | Description |
|---|---|---|---|---|
| `raw_data` | `(n_frames, 192, n_ax, 192, 1)` | float32 | a.u. | RF channel data: frame × transmit × axial sample × element × channel |
| `scan.sampling_frequency` | scalar | float32 | Hz | 30 MHz |
| `scan.center_frequency` | scalar | float32 | Hz | 10 MHz (`demodulation_frequency` is identical) |
| `scan.sound_speed` | scalar | float32 | m/s | 1540 |
| `scan.t0_delays` | `(192, 192)` | float32 | s | Per-element transmit delay per transmit (focused walking sub-aperture) |
| `scan.tx_apodizations` | `(192, 192)` | float32 | — | Hanning-windowed walking sub-aperture (47–97 elements active per transmit) |
| `scan.focus_distances` | `(192,)` | float32 | m | Constant within a scan (single fixed focus) |
| `scan.polar_angles` | `(192,)` | float32 | rad | Constant, 0.0 (no steering; purely translated scanlines) |
| `scan.transmit_origins` | `(192, 3)` | float32 | m | Per-transmit origin along the array |
| `scan.waveforms_two_way` | `(192, 303)` | float32 | a.u. | Two-way pulse waveform per transmit |
| `scan.initial_times` | `(192,)` | float32 | s | Per-transmit acquisition start time |
| `scan.time_to_next_transmit` | `(n_frames, 192)` | float32 | s | Inter-transmit interval |
| `probe.probe_geometry` | `(192, 3)` | float32 | m | Element positions (linear array, y = z = 0); confirms 0.130 mm pitch / 24.8 mm aperture |
| `metadata.probe_pose.translation` | `(n_frames, 3)` | float32 | m | Tracked probe position, one entry per `raw_data` frame (index-aligned) |
| `metadata.probe_pose.rotation` | `(n_frames, 4)` | float32 | — | Quaternion (xyzw), tracked probe orientation, index-aligned with `raw_data` |
| `metadata.probe_pose.timestamps` | `(n_frames,)` | float32 | s | Pose time, relative to the first frame |
| `custom.ct.volume` | `(n_k, n_j, n_i)` | int16 | a.u. | CT volume, `(k, j, i)`; nominally Hounsfield units (source header records no unit) |
| `custom.ct.affine` | `(4, 4)` | float64 | m | Voxel index `(i, j, k, 1)` → LPS position in metres |
| `custom.ct_segmentation.labelmap` | `(n_k, n_j, n_i, 2)` | uint8 | — | Layered 3D Slicer labelmap on the CT grid; mask = `labelmap[..., layer] == label_value` |
| `custom.ct_segmentation.segment_names` | `(3,)` | str | — | Segment names |
| `custom.ct_segmentation.segment_label_values` | `(3,)` | uint8 | — | Label value of each segment within its own layer |
| `custom.ct_segmentation.segment_layers` | `(3,)` | uint8 | — | Index into the last axis of `labelmap` holding each segment |

## Dataset Quantification

**Current OpenH-RF release:** 9 HDF5 files; 200.75 GB (200,745,025,536 bytes) stored; root `zea_version` **0.1.6**. Sizes include all HDF5 contents and use decimal units (MB = 10^6 bytes, GB = 10^9 bytes, TB = 10^12 bytes), not decoded-array memory or original-source download sizes.

Nine acquisitions, one continuous sweep each; 1428 frames in total, 200.75 GB of stored HDF5 data. No train / val / test split (each file is a single reference acquisition).
Every value below was read back from the files themselves.

| Scan | Frames | Poses | `n_ax` | Focus | Reference frame | Size on disk |
|---|---|---|---|---|---|---|
| `phantom1_distal` | 144 | 144 | 2016 | 25.70 mm | 130 | 20,534,067,200 B (20.53 GB) |
| `phantom1_proximal` | 174 | 174 | 2000 | 25.55 mm | 100 | 24,492,900,352 B (24.49 GB) |
| `phantom1_wholebone` | 158 | 158 | 1984 | 25.30 mm | 150 | 21,930,508,288 B (21.93 GB) |
| `phantom2_distal` | 162 | 162 | 2000 | 25.65 mm | 40 | 22,799,908,864 B (22.80 GB) |
| `phantom2_proximal` | 142 | 142 | 2016 | 25.75 mm | 40 | 20,236,337,152 B (20.24 GB) |
| `phantom2_wholebone` | 155 | 155 | 2016 | 25.80 mm | 45 | 21,953,183,744 B (21.95 GB) |
| `phantom3_distal` | 166 | 166 | 1984 | 25.30 mm | 100 | 23,042,916,352 B (23.04 GB) |
| `phantom3_proximal` | 167 | 167 | 2016 | 25.80 mm | 0 | 23,672,127,488 B (23.67 GB) |
| `phantom3_wholebone` | 159 | 159 | 1984 | 25.35 mm | 100 | 22,083,076,096 B (22.08 GB) |

## Subject Metadata

3D-printed, bone-mimicking musculoskeletal phantoms ("BoneSRF" — bone surface
reflection targets); no human or animal subject. Scanned with a robot-mounted
Clarius L20HD3 linear array at 10 MHz / ~5.1 cm depth / single transmit focus.

## Data Validation

Every file was validated against the installed `zea` data spec — `File.validate()`
(structural) and `File.validate_spec()` (full dtype / shape / dimension consistency)
— and all nine report compliant, with `/data/raw_data` present and non-empty.
`reconstruct.py` runs end-to-end on every scan and is deterministic across runs; the
images in [`reference_bmodes/`](reference_bmodes/) are its output.

## Known Issues
- **Acquisition dates are incomplete.** Only `phantom1_distal` (19/06/2026) and
  `phantom1_proximal` (25/06/2026) have a recorded original Clarius acquisition date;
  the other seven sweeps do not carry one in the file or in the source capture.
- **No CT↔ultrasound registration.** The CT lives in scanner LPS space and the probe
  poses in trakSTAR tracker space. Nothing in this submission relates the two.
- **CT intensity units are unverified.** The source NRRD headers record no unit. The
  value range (−1024 … ~500) is consistent with Hounsfield units, but this has not
  been confirmed by the contributor.

## Ethical Considerations

3D-printed phantom data; no human or animal subjects; no PHI.
