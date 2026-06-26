# Default source mapping

Fallback when no per-format file in `sources/` matches. The target spec
is `zea.data.spec.{DataSpec, ScanSpec, ProbeSpec, MetadataSpec}` and
<https://zea.readthedocs.io/en/openh-rf-latest/>; this file only covers
how to **find** each zea field on the source side.

## Top-level: name hints by zea field

| zea field | common source names | unit notes |
|---|---|---|
| `data.raw_data` | rank-3/4/5 array, often `int16` or complex | a.u. (uncalibrated ADC). See "raw_data shape" below |
| `scan.sampling_frequency` | `fs`, `Fs`, `samplingRate`, `ADCRate`, `Receive.decimSampleRate` | MHz → Hz (×1e6) |
| `scan.center_frequency` | `fc`, `f0`, `centerFreq`, `Trans.frequency` | MHz → Hz; may be `(n_tx,)` |
| `scan.demodulation_frequency` | `demodFreq`, `Receive.demodFrequency` | MHz → Hz. RF sources often store 0 → substitute `center_frequency` (zea requires > 0) |
| `scan.sound_speed` | `c`, `speedOfSound`, `Resource.Parameters.speedOfSound` | m/s as-is; default 1540 only if confirmed |
| `scan.t0_delays` | `TX.Delay`, or derived for steered plane wave | wavelengths → s; **must be ≥ 0** — see plane-wave block |
| `scan.tx_apodizations` | `TX.Apod` | dimensionless; default `ones((n_tx, n_el))` |
| `scan.focus_distances` | `TX.focus`, `sequence/.../source/distance` | wavelengths → m; `0` for plane wave (sources often store `Inf`) |
| `scan.transmit_origins` | `TX.Origin`, `sequence/.../source/(x,y,z)` | wavelengths → m; `0` for plane wave |
| `scan.polar_angles` | `TX.Steer`, `sequence/.../source/azimuth` | already radians, or deg → rad (×π/180) |
| `scan.initial_times` | `t0`, `startTime`, `Receive.startDepth`-derived | broadcast scalar → `(n_tx,)`; may need per-tx shift (plane-wave block) |
| `probe.probe_geometry` | `Trans.ElementPos`, `elpos`, `xele`, HDF5 `probe/geometry` | rows of (x,y,z) → `(n_el, 3)`; wavelengths → m, mm → m. 1-D `(n_el,)` ⇒ stack with y=z=0 |
| `probe.element_width` | `Trans.elementWidth`, HDF5 `probe/element_width` | wavelengths or mm → m; fall back to `0.9 * pitch` if absent or 0 (zea requires > 0) |
| `probe.type` | (infer) | uniform-x with y=z=0 ⇒ `linear`; same with rotations ⇒ `phased`; arc ⇒ `curved` |
| `probe.name` | `Trans.name`, device attrs in `root_attrs` | model string |

## raw_data shape

Target: `(n_frames, n_tx, n_ax, n_el, n_ch)`.

- Biggest axis ≈ **n_ax** (axial samples, often thousands).
- Axis matching the probe element count ≈ **n_el**.
- Axis matching the transmit count ≈ **n_tx**.
- **n_ch = 2 (IQ)** if dtype is complex or there's a length-2 channel axis;
  otherwise **n_ch = 1 (RF)**. Stack split real/imag along the channel axis.
- Propose the transpose explicitly before generating code.

## Steered plane-wave `t0_delays` + per-tx `initial_times`

This is the single biggest source of axial smearing if done wrong:

```python
# Wavefront-at-origin: element x_i sees the wavefront at t_i = +(x_i · sin θ)/c.
# zea requires t0_delays >= 0, so subtract per-tx min — and bump
# initial_times by the same shift so the sample-to-time mapping stays
# consistent across transmits.
raw_t0d = x[None, :] * np.sin(polar_angles)[:, None] / c
shift_per_tx = -raw_t0d.min(axis=1)              # (n_tx,) ≥ 0
t0_delays = raw_t0d - raw_t0d.min(axis=1, keepdims=True)
initial_times = source_initial_time + sequence_delay + shift_per_tx
```

Plane wave vs focused (no explicit enum in zea):
- Plane: `focus_distances=0`, `transmit_origins=0`, `polar_angles ≠ 0`
- Focused: finite `focus_distances`, per-scanline `transmit_origins`
- Diverging: negative / virtual focus

## `/metadata/probe_pose` (tracked data)

| sub-field | source | notes |
|---|---|---|
| `translation` | tip position `(T, 3)` | mm → m |
| `rotation` | Euler `(T, 3)` or quaternion `(T, 4)` | label `rotation_representation`; quaternion order matters (`wxyz` vs `xyzw`) |
| `start_time_offset` | offset of first pose from first transmit | may be negative |
| `timestamps` or `sampling_frequency` | one required | places poses in time |

Axes: x = lateral, y = elevation, z = axial.

## Verasonics `.mat` (consolidated)

zea ships a supported Verasonics converter that handles most of this end-to-end:
<https://zea.readthedocs.io/en/openh-rf-latest/_autosummary/zea.data.convert.verasonics.html>.
Use it directly when it fits. The mapping below is for the manual path (or to
sanity-check the converter's output).

Every `TX/*` and `Receive/*` field in v7.3 `.mat` is a struct-array of HDF5
object references; the inspector surfaces them as `object_refs` +
`deref_shape`. Dereference (`f[ref]`) to read.

| zea | Verasonics source | shape | transform |
|---|---|---|---|
| `raw_data` | `RcvData` (ref → `int16`) | acquisition buffer per frame | window per transmit (see below) |
| `t0_delays` | `TX/Delay` (λ) | `(n_tx, n_el)` | × (1/fc); then per-tx min-shift |
| `tx_apodizations` | `TX/Apod` | `(n_tx, n_el)` | as-is; ones if absent |
| `polar_angles` | `TX/Steer` (col 0) | `(n_tx,)` | radians as-is |
| `transmit_origins` | `TX/Origin` (λ) | `(n_tx, 3)` | × (c/fc) |
| `focus_distances` | `TX/focus` (λ) | `(n_tx,)` | × (c/fc) |
| `probe_geometry` | `Trans/ElementPos` rows x,y,z (λ) | `(5, n_el)` → `.T[:, :3]` | × (c/fc) |
| `center_frequency` | `Trans/frequency` (MHz) | scalar | × 1e6 |
| `demodulation_frequency` | `Receive/demodFrequency` (MHz) | scalar | × 1e6 |
| `sampling_frequency` | `Receive/decimSampleRate` (MHz) | scalar | × 1e6 |
| `sound_speed` | `Resource/Parameters/speedOfSound` | scalar | m/s as-is |

**Reshaping `RcvData` → `raw_data`.** Single object reference; `deref_shape`
is h5py's reversed (column-major) view `(frames, channels, samples)`. Read
shape/dtype, **never `[()]`** the buffer (often GB). Transpose to MATLAB-native
`(samples, channels, frames)` and slice per receive window — boundaries from
`Receive.startSample` / `Receive.endSample` (MATLAB 1-based; subtract 1). Some
sequences use `Receive.aperture` (element multiplex: one logical transmit =
multiple receive events, overlapping ranges averaged). After windowing,
transpose to `(n_frames, n_tx, n_ax, n_el, n_ch)` and verify by reconstructing.
