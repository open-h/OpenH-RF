# SPDX-License-Identifier: Apache-2.0
"""Smoke-tests that run each standalone example script.

Every script is executed in a subprocess so side-effects (cwd changes,
generated files, etc.) are fully isolated.

Each example is exercised exactly once: either as a standalone entry in
LIGHT_SCRIPTS (a one-off script with no reconstruct.py counterpart), or as
an entry in *_CONVERT_RECONSTRUCT_DIRS (convert.py followed by reconstruct.py
in sequence) if it ships both. This grouping is by shape, not by location:
*_CONVERT_RECONSTRUCT_DIRS holds both examples/templates/* dirs and
top-level examples/<name>/ dataset submissions alike. Don't add the same
example to more than one list, or its convert.py runs twice.

Tests are split light/heavy so CI (which only runs "not heavy") stays fast:
heavy tests need network access to download real datasets (Hugging Face Hub,
remote zips, ...) and can take minutes per script.

First sync the `test` extra so pytest/ruff are installed *into the project's
venv* (`.venv/bin/pytest`):

    uv sync --extra test

Run locally with uv:

    uv run pytest tests/test_scripts.py                 # light tests only
    uv run pytest tests/test_scripts.py -m heavy         # heavy tests only
    uv run pytest tests/test_scripts.py -m ""            # everything

Run a single example by its id (path relative to repo root), e.g.:

    uv run pytest tests/test_scripts.py -k "tracked-cirs-phantom" -m heavy -v
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

LIGHT_SCRIPTS = [
    ROOT / "examples" / "save_pipeline_example.py",
]

# Directories whose convert.py + reconstruct.py must run in sequence. Covers
# both examples/templates/* (dummy-data starting points) and top-level
# examples/<name>/ dirs (real dataset submissions) -- both follow the same
# convert.py -> reconstruct.py shape. The scripts resolve paths relative to
# __file__, so generated files land inside the example directory and are
# cleaned up after each test.
LIGHT_CONVERT_RECONSTRUCT_DIRS = [
    ROOT / "examples" / "templates" / "color-doppler",
    ROOT / "examples" / "templates" / "echocardiography",
    ROOT / "examples" / "templates" / "segmentation",
]
HEAVY_CONVERT_RECONSTRUCT_DIRS = [
    # Heavy because convert.py downloads the source dataset (Hugging Face,
    # Zenodo-hosted zip, ...) instead of using bundled/synthetic data.
    ROOT / "examples" / "templates" / "verasonics",
    ROOT / "examples" / "nv-raw2insights-us",
    ROOT / "examples" / "tracked-cirs-phantom",
    ROOT / "examples" / "pala-ulm-ratbrain",
]


def _script_id(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _dir_id(directory: Path) -> str:
    return str(directory.relative_to(ROOT))


def _run(script: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
        env={
            **os.environ,
            "KERAS_BACKEND": "jax",
            # Force JAX to CPU so tests are not subject to GPU availability or
            # cuFFT/OOM failures in the test environment.
            "JAX_PLATFORMS": "cpu",
        },
    )


def _assert_clean_exit(script: Path, result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, (
        f"Script {script.name} failed (exit {result.returncode}).\n"
        f"--- stdout ---\n{result.stdout[-2000:]}\n"
        f"--- stderr ---\n{result.stderr[-2000:]}"
    )


def _run_convert_reconstruct(example_dir: Path, tmp_path: Path) -> None:
    """Run convert.py then reconstruct.py for an example dir, cleaning up afterwards."""
    convert = example_dir / "convert.py"
    reconstruct = example_dir / "reconstruct.py"
    generated = list(example_dir.glob("*.hdf5")) + list(example_dir.glob("*.png"))
    try:
        _assert_clean_exit(convert, _run(convert, tmp_path))
        _assert_clean_exit(reconstruct, _run(reconstruct, tmp_path))
    finally:
        # Remove any files that were not present before the test.
        for f in example_dir.glob("*.hdf5"):
            if f not in generated:
                f.unlink(missing_ok=True)
        for f in example_dir.glob("*.png"):
            if f not in generated:
                f.unlink(missing_ok=True)


@pytest.mark.parametrize("script", LIGHT_SCRIPTS, ids=[_script_id(s) for s in LIGHT_SCRIPTS])
def test_script_runs(script, tmp_path):
    """Run a lightweight example script and assert it exits cleanly."""
    _assert_clean_exit(script, _run(script, tmp_path))


@pytest.mark.parametrize(
    "example_dir",
    LIGHT_CONVERT_RECONSTRUCT_DIRS,
    ids=[_dir_id(d) for d in LIGHT_CONVERT_RECONSTRUCT_DIRS],
)
def test_convert_reconstruct_runs(example_dir, tmp_path):
    """Run convert.py then reconstruct.py for a lightweight example."""
    _run_convert_reconstruct(example_dir, tmp_path)


@pytest.mark.heavy
@pytest.mark.parametrize(
    "example_dir",
    HEAVY_CONVERT_RECONSTRUCT_DIRS,
    ids=[_dir_id(d) for d in HEAVY_CONVERT_RECONSTRUCT_DIRS],
)
def test_heavy_convert_reconstruct_runs(example_dir, tmp_path):
    """Run convert.py then reconstruct.py for an example that needs network access."""
    _run_convert_reconstruct(example_dir, tmp_path)
