# Source inspection

## Run

```bash
python scripts/inspect_source.py <sample>
```

`<sample>` is one local file: `.hdf5`/`.h5`/`.uff`, `.mat`, `.npz`/`.npy`,
or a raw `.bin` / its `.json` sidecar. The tool only imports
numpy/h5py/scipy (no zea), so plain `python` works. For a Hugging Face
dataset, download one sample first (`hf_hub_download`) and point the tool
at it.

## Output schema

```json
{
  "path": "...",
  "type": "hdf5" | "mat (v7.3 / hdf5)" | "mat (<=v7)" | "npz" | "npy" | "bin" | "json" | "unknown",
  "fields": [
    {"name": "...", "shape": [...], "dtype": "...", "stats": {"min", "max", "mean"} | null, "attrs": {...}}
  ],
  "root_attrs": {...}   // HDF5 only
}
```

Variants by source type:
- **`.bin`** emits `bytes`, `element_count_if` (elements per candidate dtype), and `sidecar_json`.
- **`.json`** emits `json_metadata` (parsed, list-truncated) and `sidecar_bins`.

## What to extract for the mapping interview

- **Channel data**: rank 3–5 array, one large axis (axial samples, often thousands), one axis matching the probe element count. `int16` or a complex dtype reinforces the guess.
- **Scan scalars**: sampling/center/demodulation frequency, sound speed. Small scalar arrays or attribute values. Magnitudes near `1e6–1e7` are Hz; near `1–30` are MHz.
- **Geometry**: element positions, either `(n_el, 3)` Cartesian or `(n_el,)` lateral-only (stack with y=z=0). Values near `1e-3–1e-1` are metres; near `1–50` are likely mm or wavelengths.
- **Per-transmit arrays**: delays `(n_tx, n_el)`, angles `(n_tx,)`, apodizations `(n_tx, n_el)`, focus distances `(n_tx,)`. The shared axis length is your `n_tx` evidence.

## Per-source signals

- **HDF5**: nested groups; `name` is the full path. Units / labels usually in dataset `attrs` — read them.
- **`.uff`** (USTB UFF) is HDF5 internally. See [`sources/uff.md`](sources/uff.md) for the full layout + tips.
- **Verasonics `.mat`** (v7.3): HDF5 underneath. The struct-array fields (`TX/*`, `Receive/*`, `RcvData`) appear as `object-ref` datasets — the inspector dereferences the first ref and reports the target's `deref_shape`/`deref_dtype` so you can read `RcvData`'s shape without materialising it. The full Verasonics→zea table lives in [`sources/_default.md`](sources/_default.md).
- **`.npz` / `.npy`**: no metadata. Every unit and axis meaning must be supplied by the contributor.
- **`.bin` + `.json` sidecars**: the JSON is the authoritative layout. The `.bin` carries no shape/dtype/endianness. Cross-check `prod(json_dims)` against `element_count_if[json_dtype]` — mismatch ⇒ wrong dtype, header offset, or zero-padded tail. Watch endianness (`<` vs `>`) and IQ interleaving (`n_ch=2` or split complex).

## Caveat

**Never assume axis order.** The same shape can be laid out many ways
(`(n_ax, n_el)` vs `(n_el, n_ax)`, frames-first vs frames-last). Use shape +
dtype + stats + element count to **propose** an interpretation, then
**confirm with the contributor** before generating any code.
