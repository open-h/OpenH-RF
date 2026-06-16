"""
Validate a zea file against the installed zea data spec (programmatic).

Used by dimension 1 (format compliance) as the authoritative check. Rather than
comparing the file against a hand-maintained field list (which drifts out of
date), this reconstructs zea's own ``FileSpec`` from the file via
``FileSpec.from_hdf5`` — which runs every dtype / shape / dimension-consistency
validation the spec defines in its ``__post_init__`` hooks. Compliance is
therefore checked against *the zea version installed in the evaluation
environment*; the reported ``zea_version`` records which spec was applied.

If the spec reconstructs without error, the file is compliant with that zea
version. If it raises, the exception message is the precise violation and
becomes a dimension-1 finding.

Usage:
    python validate_zea_spec.py path/to/sample.hdf5

Exit code 0 = compliant, 1 = non-compliant (machine-readable JSON on stdout).
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Default to the jax backend (installed by `uv sync`) before importing zea.
os.environ.setdefault("KERAS_BACKEND", "jax")


def validate(path: Path) -> dict:
    import h5py
    import zea
    from zea.data.spec import FileSpec

    result = {
        "path": str(path),
        "zea_version": zea.__version__,
        "compliant": False,
        "top_level_groups": [],
        "data_groups": [],
        "has_raw_data": False,
        "errors": [],
    }
    try:
        with h5py.File(str(path), "r") as hf:
            result["top_level_groups"] = sorted(hf.keys())
            if "data" in hf:
                result["data_groups"] = sorted(hf["data"].keys())
                result["has_raw_data"] = "raw_data" in hf["data"]
            # The load-bearing check: reconstructing FileSpec re-runs every
            # validation the installed zea spec defines.
            FileSpec.from_hdf5(hf)
        result["compliant"] = True
    except Exception as e:  # noqa: BLE001 - any spec violation is a finding
        result["errors"].append(f"{type(e).__name__}: {e}")

    # OpenH-RF hard requirement, independent of spec construction.
    if not result["has_raw_data"]:
        result["compliant"] = False
        result["errors"].append(
            "BLOCKER: /data/raw_data is missing — raw pre-beamformed channel "
            "capture data is mandatory for every OpenH-RF submission."
        )
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zea_file", type=Path, help="Path to the .hdf5 zea file")
    args = ap.parse_args()

    r = validate(args.zea_file)
    print(json.dumps(r, indent=2))
    sys.exit(0 if r["compliant"] else 1)
