# USTB UFF → zea

[UFF](https://www.ustb.no/) is the USTB project's HDF5-based container. Sample
files at <https://zenodo.org/records/20261898>.

**Authoritative spec:** the MATLAB class hierarchy at
<https://github.com/unioslo/USTB/tree/master/%2Buff>. Class names map 1:1 onto
HDF5 group paths inside a `.uff` file (e.g. `uff.channel_data` →
`/channel_data`, `uff.wave` → `/channel_data/sequence/sequence_NNNN`). Open
`+uff/<class>.m` for the field list of that class.

The authoritative target spec is `zea.data.spec.{DataSpec, ScanSpec,
ProbeSpec}`. This file only covers source-side specifics.

## File format

UFF files are **HDF5 internally** (the inspector dispatches `.uff` to the HDF5
handler). Variable-length string attrs come out as `bytes`-arrays; the
inspector decodes them recursively.

## Top-level layout

```
channel_data/
├── data/{real, imag}        IQ data, both (n_tx, n_el, n_ax)
   OR
├── data                     RF data, (n_el, n_ax) for n_tx=1, else (n_tx, n_el, n_ax)
├── sampling_frequency       (1,1) Hz
├── modulation_frequency     (1,1) Hz — demod freq for IQ; 0 for RF
├── pulse/center_frequency   (1,1) Hz
├── sound_speed              (1,1) m/s
├── initial_time             (1,1) s
├── probe/
│   ├── geometry             (7, n_el) — rows: x, y, z, theta, phi, width, height
│   ├── element_width        (1,1)
│   └── pitch                (1,1)
└── sequence/
    ├── source/{azimuth, elevation, distance}  ← single-transmit form (n_tx=1)
    └── sequence_NNNN/                          ← multi-transmit form (n_tx > 1)
        ├── source/{azimuth, elevation, distance}
        └── delay            per-transmit time offset (s); usually 0
```

## Source → target table

| zea target | UFF source | transform |
|---|---|---|
| `data.raw_data` | `channel_data/data` (RF) or `data/{real,imag}` (IQ) | stack + transpose to `(n_frames, n_tx, n_ax, n_el, n_ch)`, float32 |
| `scan.sampling_frequency` | `channel_data/sampling_frequency` | scalar, Hz, as-is |
| `scan.center_frequency` | `channel_data/pulse/center_frequency` | scalar, Hz |
| `scan.demodulation_frequency` | `channel_data/modulation_frequency` | scalar; if ≤ 0 use `center_frequency` |
| `scan.sound_speed` | `channel_data/sound_speed` | m/s, as-is |
| `scan.initial_times` | `initial_time + sequence/.../delay + shift_per_tx` | see Tip 4 |
| `scan.polar_angles` | `sequence/.../source/azimuth` | already in radians |
| `scan.t0_delays` | derived | see Tip 4 |
| `scan.tx_apodizations` | not stored | `ones((n_tx, n_el))` |
| `scan.focus_distances` | `sequence/.../source/distance` | `0` for plane wave (UFF stores `Inf`) |
| `scan.transmit_origins` | not stored | `zeros((n_tx, 3))` for plane wave |
| `probe.probe_geometry` | `probe/geometry[:3, :]` | transpose to `(n_el, 3)` |
| `probe.element_width` | `probe/element_width` | scalar; fallback `0.9 * pitch` if 0 |
| `probe.type` | (infer) | `linear`/`phased`/`curved` from geometry |

## Tips

**Tip 1 — two transmit-sequence shapes.** Single-transmit files have
`sequence/source/*` directly; multi-transmit have `sequence/sequence_NNNN/*`.
Detect via `list(ch["sequence"].keys())`.

**Tip 2 — two data shapes.** IQ as `data/{real,imag}` with `n_ch=2`; RF as
single `data` array with `n_ch=1` (and one fewer axis when `n_tx=1`).

**Tip 3 — `probe/geometry` row 5 (element_width) is unreliable.** It's often
`0`, and on some UFF files `probe/element_width` is missing entirely (PICMUS).
Guard the lookup with `"element_width" in ch["probe"]` and fall back to
`0.9 * pitch` when absent or zero. zea rejects `element_width <= 0`.

**Tip 4 — steered plane wave: `t0_delays` AND `initial_times`.** This is the
single biggest source of axial smearing if you get it wrong. USTB stores
everything in a "wavefront-at-origin" reference (where `initial_time` and
`sequence.delay` are 0). zea computes `tx_delay` as
`min over elements of (rx_delays + t0_delays)`, which only matches USTB's
analytical plane-wave formula when t0_delays are referenced to wavefront-at-origin.
But zea also requires `t0_delays >= 0`, so we have to shift. The fix:

```python
# Wavefront-at-origin reference: element at x_i sees the wavefront at
# t_i = (x_i · sin θ) / c. For positive θ the wave propagates in +x →
# element at -x_max fires first.
raw_t0d = x[None, :] * np.sin(polar_angles)[:, None] / c
shift_per_tx = -raw_t0d.min(axis=1)              # (n_tx,), non-negative
t0_delays = raw_t0d - raw_t0d.min(axis=1, keepdims=True)
# CRITICAL: bump initial_times by the same per-tx shift, so the
# sample-to-time mapping stays consistent across transmits.
initial_times = source_initial_time + sequence_delay + shift_per_tx
```

For PICMUS at ±16°, `shift_per_tx ≈ 3.41 μs` ≈ 17.8 samples at 5.21 MHz IQ.
Without the per-transmit `initial_times` bump, coherent compound smears
axially. Verified against USTB MATLAB ground truth.

**Tip 5 — `demodulation_frequency = 0` for RF sources.** zea requires
positive; substitute `center_frequency`.

**Tip 6 — IQ reconstruction needs a custom pipeline.** `Pipeline.from_default()`
crashes on `n_ch=2` because its `Demodulate` op isn't a no-op for IQ inputs:

```python
default = zea.Pipeline.from_default()
ops = [op for op in default.operations if op.__class__.__name__ != "Demodulate"]
pipe = zea.Pipeline(ops)
```

## Open questions (not yet exercised)

- Multi-frame UFF (`N_frames > 1`) — where does the frame axis sit?
- Focused / scanline UFF — `source.distance` finite
- Retrospective Transmit Beamforming (RTB) UFF files
- UFF with explicit `t0_delays` stored as data
