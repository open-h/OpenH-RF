"""
Validate a zea file against the installed zea data spec (programmatic).

Used by dimension 1 (format compliance) as the authoritative check. Rather than
comparing the file against a hand-maintained field list (which drifts out of
date), this opens the file with zea and runs zea's own validators against the
zea version installed in the evaluation environment:

  - ``File.validate()``      — fast, zero-IO structural check (a ``data`` group is
    present and every key is a recognised zea data type).
  - ``File.validate_spec()`` — full schema validation: reads the data and checks
    dtypes, shapes, and cross-field dimension consistency as defined by
    ``zea.data.spec.FileSpec`` (loads all arrays into RAM).

The reported ``zea_version`` records which spec was applied. If both validators
pass, the file is compliant with that zea version. If either raises, the
exception message is the precise violation and becomes a dimension-1 finding.

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
    import zea

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
        with zea.File(str(path)) as f:
            result["top_level_groups"] = sorted(f.keys())
            if "data" in f:
                result["data_groups"] = sorted(f["data"].keys())
                result["has_raw_data"] = "raw_data" in f["data"]
            # The load-bearing checks: zea's own validators run against the
            # installed spec. validate() is the cheap structural pass;
            # validate_spec() is the full dtype/shape/dimension-consistency pass.
            f.validate()
            f.validate_spec()
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
