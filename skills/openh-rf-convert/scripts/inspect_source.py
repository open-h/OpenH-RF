"""Inspect a source ultrasound dataset and emit a structured field inventory (JSON).

Step 1 of the openh-rf-convert skill: discover a source file's structure without
guessing, so the mapping interview can PROPOSE source->zea field mappings for the
contributor to confirm. Supports HDF5 (incl. USTB UFF), MATLAB .mat (v7.3 via
h5py, older via scipy), NumPy .npz/.npy, raw .bin + .json metadata sidecars.
Unknown types get a best-effort note.

Usage:
    python inspect_source.py path/to/sample.{hdf5,uff,mat,npz,npy,bin,json}

Prints JSON: {"path","type","fields":[{"name","shape","dtype","stats","attrs"}],...}
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def _to_jsonable(v):
    """Recursively coerce HDF5 attribute values to JSON-safe Python.

    HDF5 attributes often carry numpy scalars, bytes, or arrays of bytes
    (variable-length strings). Each of those needs decoding before json.dumps
    will accept it, and nested containers (ndarray of bytes, list of bytes)
    only show up under real-world sources like USTB's UFF.
    """
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    if isinstance(v, np.generic):
        return _to_jsonable(v.item())
    if isinstance(v, np.ndarray):
        if v.size <= 8:
            return [_to_jsonable(x) for x in v.tolist()]
        return f"<ndarray shape={list(v.shape)}>"
    if isinstance(v, (list, tuple)):
        return [_to_jsonable(x) for x in v]
    return v


def _stats(arr):
    """Cheap numeric summary on a (sub-sampled) array; None if non-numeric/empty."""
    try:
        a = np.asarray(arr)
        if a.size == 0 or not np.issubdtype(a.dtype, np.number):
            return None
        flat = a.ravel()
        if flat.size > 100_000:
            flat = flat[:: max(1, flat.size // 100_000)]
        return {
            "min": float(np.nanmin(flat)),
            "max": float(np.nanmax(flat)),
            "mean": float(np.nanmean(flat)),
        }
    except Exception:
        return None


def _field(name, shape, dtype, stats=None, attrs=None):
    return {
        "name": name,
        "shape": list(shape) if shape is not None else None,
        "dtype": str(dtype),
        "stats": stats,
        "attrs": attrs or {},
    }


def _deref_field(name, obj, h5py):
    """Build a field entry for an HDF5 object-reference dataset.

    MATLAB v7.3 .mat stores raw channel data (RcvData) and every struct-array
    field (TX/*, Receive/*) as HDF5 object references into the "#refs#" table.
    A bare dtype "object" with no shape hides the real array, so we follow the
    first non-null reference and report the dereferenced target's shape/dtype.
    """
    attrs = {k: _to_jsonable(v) for k, v in obj.attrs.items()}
    n_refs = int(obj.size)
    try:
        ref = next(r for r in obj[()].flat if r)
        target = obj.file[ref]
        if not isinstance(target, h5py.Dataset):
            # A reference to a Group (e.g. a MATLAB struct), not an array — it
            # has no shape/dtype to report. Note it rather than crash.
            fld = _field(name, obj.shape, "object-ref", None, attrs)
            fld["object_refs"] = n_refs
            fld["deref_kind"] = "group"
            return fld
        stats = _stats(target[()]) if 0 < target.size < 5_000_000 else None
        fld = _field(name, obj.shape, "object-ref", stats, attrs)
        fld["object_refs"] = n_refs
        fld["deref_shape"] = list(target.shape)
        fld["deref_dtype"] = str(target.dtype)
        return fld
    except (StopIteration, ValueError, KeyError, TypeError, AttributeError):
        fld = _field(name, obj.shape, "object-ref", None, attrs)
        fld["object_refs"] = n_refs
        fld["note"] = "unresolved ref"
        return fld


def inspect_hdf5(path):
    import h5py

    fields = []

    def visit(name, obj):
        # MATLAB v7.3 buries many (often tens of thousands of) anonymous
        # object-reference targets under the
        # "#refs#" group; skip emitting them (a bare `return` lets visititems
        # keep walking — never return a truthy value, which aborts the walk).
        if name.startswith("#refs#"):
            return
        if isinstance(obj, h5py.Dataset):
            if h5py.check_dtype(ref=obj.dtype) is not None:
                fields.append(_deref_field(name, obj, h5py))
                return
            attrs = {k: _to_jsonable(v) for k, v in obj.attrs.items()}
            stats = _stats(obj[()]) if 0 < obj.size < 5_000_000 else None
            fields.append(_field(name, obj.shape, obj.dtype, stats, attrs))

    with h5py.File(str(path), "r") as f:
        f.visititems(visit)
        root_attrs = {k: _to_jsonable(v) for k, v in f.attrs.items()}
    return {"type": "hdf5", "fields": fields, "root_attrs": root_attrs}


def inspect_mat(path):
    # v7.3 .mat files are HDF5; older are not.
    try:
        out = inspect_hdf5(path)
        out["type"] = "mat (v7.3 / hdf5)"
        return out
    except OSError:
        from scipy.io import loadmat

        m = loadmat(str(path), squeeze_me=False, struct_as_record=False)
        fields = []
        for name, val in m.items():
            if name.startswith("__"):
                continue
            arr = np.asarray(val)
            fields.append(_field(name, arr.shape, arr.dtype, _stats(arr)))
        return {"type": "mat (<=v7)", "fields": fields}


def inspect_npz(path):
    fields = []
    with np.load(str(path), allow_pickle=False) as data:
        for name in data.files:
            arr = data[name]
            fields.append(_field(name, arr.shape, arr.dtype, _stats(arr)))
    return {"type": "npz", "fields": fields}


def inspect_npy(path):
    arr = np.load(str(path), allow_pickle=False)
    return {"type": "npy", "fields": [_field(Path(path).stem, arr.shape, arr.dtype, _stats(arr))]}


_BIN_DTYPES = {
    "int8": 1,
    "uint8": 1,
    "int16": 2,
    "int32": 4,
    "float32": 4,
    "float64": 8,
    "complex64": 8,
    "complex128": 16,
}


def _compact_json(obj, max_list=16):
    """Recursively shorten long scalar lists so a metadata dump stays readable."""
    if isinstance(obj, dict):
        return {k: _compact_json(v, max_list) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) > max_list and all(not isinstance(x, (dict, list)) for x in obj):
            return obj[:8] + [f"...(+{len(obj) - 8} more; {len(obj)} total)"]
        return [_compact_json(x, max_list) for x in obj]
    return obj


def inspect_json(path):
    """A .json metadata sidecar: surface its contents and find the companion .bin.

    Raw exports often ship as one or more JSON sidecars (acquisition / sequence /
    subject) next to a .bin. The JSON is the authoritative layout + acquisition
    source: map its fields to /scan and /probe and use its declared dtype/dims to
    reshape the bin.
    """
    meta = json.loads(path.read_text(encoding="utf-8"))
    sidecar_bins = [
        {"name": b.name, "bytes": b.stat().st_size} for b in sorted(path.parent.glob("*.bin"))
    ]
    return {
        "type": "json",
        "fields": [],
        "json_metadata": _compact_json(meta),
        "sidecar_bins": sidecar_bins,
        "note": (
            "JSON metadata sidecar — the authoritative layout + acquisition "
            "source for a companion .bin. Map its fields to /scan and /probe and "
            "use the declared dtype/dimensions to reshape the .bin. Confirm it "
            "describes RAW channel data, not beamformed pixels."
        ),
    }


def inspect_bin(path):
    """A raw .bin blob: report byte size, per-dtype element counts, and sidecars.

    A .bin carries no shape/dtype/endianness/interleaving — those come from the
    sidecar JSON(s). We never load the buffer; we report its size and, for each
    candidate dtype, how many elements it would hold, so the layout can be
    reconciled against the JSON-declared dimensions.
    """
    n = path.stat().st_size
    element_count_if = {name: n // size for name, size in _BIN_DTYPES.items() if n % size == 0}
    sidecar_json = {}
    for j in sorted(path.parent.glob("*.json")):
        try:
            sidecar_json[j.name] = _compact_json(json.loads(j.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            sidecar_json[j.name] = "<unparseable JSON>"
    return {
        "type": "bin",
        "fields": [],
        "bytes": n,
        "element_count_if": element_count_if,
        "sidecar_json": sidecar_json,
        "note": (
            "Raw binary blob — shape, dtype, endianness, and RF/IQ interleaving "
            "come from the sidecar JSON(s), not the bytes. Load with "
            "np.fromfile(dtype=...).reshape(...); cross-check that prod(shape) "
            "matches the element_count_if entry for that dtype. Watch endianness "
            "('<' little vs '>' big) and IQ interleaving (interleaved I/Q -> "
            "n_ch=2, or a complex dtype split into real/imag)."
        ),
    }


DISPATCH = {
    ".hdf5": inspect_hdf5,
    ".h5": inspect_hdf5,
    # USTB UFF (Ultrasound File Format) files are HDF5 internally — same reader.
    ".uff": inspect_hdf5,
    ".mat": inspect_mat,
    ".npz": inspect_npz,
    ".npy": inspect_npy,
    ".bin": inspect_bin,
    ".json": inspect_json,
}


def inspect(path: Path) -> dict:
    handler = DISPATCH.get(path.suffix.lower())
    if handler is None:
        return {
            "type": "unknown",
            "fields": [],
            "note": (
                f"Unrecognised extension {path.suffix!r}; describe the layout in the interview."
            ),
        }
    out = handler(path)
    out["path"] = str(path)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path, help="Path to a sample source file")
    args = ap.parse_args()
    if not args.source.exists():
        print(json.dumps({"error": f"{args.source} not found"}), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(inspect(args.source), indent=2))


if __name__ == "__main__":
    main()
