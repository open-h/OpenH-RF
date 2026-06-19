# zea file format notes

> **Authoritative check is programmatic.** For dimension 1, run
> `scripts/validate_zea_spec.py <file>` — it runs zea's own validators
> (`File.validate` + `File.validate_spec`) against the zea version installed in
> the eval environment (the spec *as code*, which cannot drift from these notes).
> The notes below are a human-readable companion for interpreting results and
> spotting recommended-but-not-required fields; if they ever disagree with the
> installed zea spec, **the installed spec wins**.

## Live documentation — fetch these instead of relying on the summary below

These pages are accessible to agents via WebFetch and are always up to date:

| Page | Content |
|---|---|
| **<https://zea.readthedocs.io/en/openh-rf-latest/data-acquisition.html>** | Full field-level spec: groups, dtypes, shapes, units, required vs optional |
| <https://zea.readthedocs.io/en/openh-rf-latest/pipeline.html> | Pipeline ops, `Pipeline.from_default()`, `return_numpy`, device selection |
| <https://zea.readthedocs.io/en/openh-rf-latest/> | Full zea docs index |
| <https://github.com/tue-bmd/zea> | Source (use for version history / changelog) |

**When in doubt, fetch the live spec page** — the summary below is a quick-reference digest and may lag the installed version.

## Minimum version

Every OpenH-RF submission must have been written with **zea ≥ v0.1.0a3** (recorded as the `zea_version` attribute at the HDF5 root). Files from v0.1.0a2 or earlier are ineligible — flag as `blocker`.

## Key facts (quick reference)

A zea file is standard HDF5. `zea.File` is a thin wrapper around `h5py.File`. Files have a `.hdf5` extension — there is no `.zea` extension.

SI units throughout (Hz, s, m, V, rad); field names are `snake_case`.

## Top-level structure

A zea file is HDF5-backed. **Single-track** files have `data/` + `scan/` at the
root; **multi-track** files replace those with a `tracks/` group (each track has
its own `data/` + `scan/`), with `probe/` and `metadata/` shared.

```
file.hdf5
├── attrs: us_machine, description, zea_version, acquisition_time   (all optional)
├── data/        # raw + derived data products          (single-track)
├── scan/        # acquisition parameters                (single-track)
├── probe/       # transducer geometry/specs             (shared)
├── metadata/    # subject, annotations, signals, pose   (optional)
├── metrics/     # quality metrics                       (optional)
└── tracks/      # multi-track only: track_0/, track_1/ … each with data/ + scan/
    track_schedule  # optional int32 (n_total_tx): maps each transmit to a track
```

## `/data` — raw and derived products

A single-track file must contain **`raw_data` or at least one derived product**;
OpenH-RF additionally **requires `raw_data`** (enforced by `validate_zea_spec.py`,
since zea's generic spec does not).

| Field | Dtype | Shape | Units | Notes |
|---|---|---|---|---|
| `raw_data` | float32 / int16 | `(n_frames, n_tx, n_ax, n_el, n_ch)` | a.u. | Raw channel data |

Derived products are each a **sub-group** with a `values` array plus optional
`coordinates` and metadata (`labels`, `description`, `unit`, `min`, `max`):

- `aligned_data` — ToF-corrected: `(n_frames, n_tx, n_ax, n_el, n_ch)`
- `beamformed_data` — beamsummed: `(n_frames, z, x, [y], n_ch)`
- `envelope_data` — `(n_frames, z, x, [y])`
- `image` — log-compressed B-mode: `(n_frames, z, x, [y])`, float32/uint8
- `segmentation` — `(n_frames, z, x, [y], n_labels)`, **bool**, with `labels` (class names)
- `sos_map`, `strain_percentage_map`, `shear_wave_elastography_map`,
  `tissue_doppler`, `color_doppler` — spatial maps (m/s, %, etc.)
- `<custom>` — arbitrary key, validated as a generic `Map` (`values` + optional
  `coordinates`). zea emits a warning for non-standard keys; record as `minor`.

**Coordinates are point-based.** Spatial products carry an optional `coordinates`
array of shape `(*spatial, 3)` giving the per-pixel Cartesian position in metres,
ordered `(x, y, z)` — e.g. 2D `(n_frames, z, x, 3)`, 3D `(n_frames, z, x, y, 3)`.
This replaces the older extent-based representation.

## `/scan` — acquisition parameters

Required unless marked optional.

| Field | Dtype | Shape | Units | Req | Notes |
|---|---|---|---|---|---|
| `sampling_frequency` | float32 | scalar | Hz | yes | A/D rate |
| `center_frequency` | float32 | scalar or `(n_tx)` | Hz | yes | Transmit pulse center freq |
| `demodulation_frequency` | float32 | scalar or `(n_tx)` | Hz | yes | IQ demod freq |
| `initial_times` | float32 | `(n_tx)` | s | yes | A/D start time per transmit |
| `t0_delays` | float32 | `(n_tx, n_el)` | s | yes | Transmit delay per element |
| `tx_apodizations` | float32 | `(n_tx, n_el)` | – | yes | Transmit weighting |
| `focus_distances` | float32 | `(n_tx)` | m | yes | Focal distance per transmit |
| `transmit_origins` | float32 | `(n_tx, 3)` | m | yes | Beam origin (x,y,z) |
| `polar_angles` | float32 | `(n_tx)` | rad | yes | Beam polar angle |
| `time_to_next_transmit` | float32 | `(n_frames, n_tx)` or `(n_timing_intervals)` | s | no | Inter-transmit time |
| `azimuth_angles` | float32 | `(n_tx)` | rad | no | Beam azimuth |
| `sound_speed` | float32 | scalar | m/s | no | Medium speed of sound |
| `tgc_gain_curve` | float32 | `(n_ax)` | – | no | Time-gain compensation |
| `waveforms_one_way` / `waveforms_two_way` | float32 | `(n_tx, n_samples_*)` | V | no | Transmit waveforms |

Transmit *type* (focused / plane-wave / diverging / synthetic-aperture) is
expressed through `t0_delays`, `focus_distances`, `polar_angles`, and
`transmit_origins` rather than a single enum.

## `/probe` — transducer (all fields optional)

| Field | Dtype | Shape | Units | Notes |
|---|---|---|---|---|
| `name` | str | scalar | – | Probe model |
| `type` | str | scalar | – | `linear`, `phased`, `curved`, `matrix`, … |
| `probe_geometry` | float32 | `(n_el, 3)` | m | Element positions (x,y,z) — `n_el` and pitch derive from this |
| `probe_center_frequency` | float32 | scalar | Hz | Nominal center freq |
| `probe_bandwidth_percent` | float32 | scalar | % | Fractional bandwidth |
| `element_width` | float32 | scalar | m | |
| `element_height` | float32 | scalar | m | Elevation aperture |
| `lens_sound_speed` | float32 | scalar | m/s | |
| `lens_thickness` | float32 | scalar | m | |

Note: there is **no** `geometry_type`, `n_elements`, `pitch`, or `radius` field —
geometry is the explicit `probe_geometry` point cloud.

## `/metadata` — subject, annotations, signals, pose (all optional)

Root: `credit` (str), `text_report` (str). Sub-groups:

- **`subject`**: `id` (str), `type` (str, e.g. "human"/"phantom"), `age` (uint8, yr),
  `sex` (str), `fat_percentage` (float32). **De-identify** — see PHI checklist.
- **`annotations`** (per-frame or scalar str): `anatomy`, `view`, `label`,
  `image_quality`.
- **`probe_pose`** — transducer tracking:

  | Field | Dtype | Shape | Units | Req | Notes |
  |---|---|---|---|---|---|
  | `translation` | float32 | `(T, 3)` | m | yes | Tip position (x,y,z) |
  | `rotation` | float32 | `(T, 3)` or `(T, 4)` | – | yes | Euler or quaternion |
  | `rotation_representation` | str | scalar | – | yes | `euler_xyz`, `quaternion_wxyz`, or `quaternion_xyzw` |
  | `start_time_offset` | float32 | scalar | s | yes | Offset from first transmit (±) |
  | `sampling_frequency` | float32 | scalar | Hz | no* | Pose rate |
  | `timestamps` | float32 | `(T)` | s | no* | Per-sample times, relative to sample 0 |

  *One of `sampling_frequency` or `timestamps` is needed to place poses in time.
  Convention: **x = lateral, y = elevation (out-of-plane), z = axial (depth)**.

- **`ecg` / `voice_narration` / custom `SignalND`**: `samples` (1D), plus
  `start_time_offset` (s) and one of `sampling_frequency` / `timestamps`.

## `/metrics` — quality (optional)

`common_midpoint_phase_error` `(n_frames)`, `coherence_factor` `(n_frames)`.

> The field tables above are a digest. For complete dtype, shape, and unit details fetch <https://zea.readthedocs.io/en/openh-rf-latest/data-acquisition.html>.

## Things that must never be there

- Patient names, MRNs, DOBs, addresses, free-text identifiers
- Filenames embedding identifiers; institutional IDs tied to a patient
- Study codes that map back to identifiable records

## Validation order (fail fast)

1. Opens? (`zea.File(path)`)
2. Required groups present? (`data`+`scan`, or `tracks`; `raw_data` for OpenH-RF)
3. Spot-check shapes/dtypes against the tables above
4. Validate units on a few key scalars (`sampling_frequency` Hz, `sound_speed` m/s,
   `probe_geometry` m)
5. Then proceed to deeper metadata / pose checks
