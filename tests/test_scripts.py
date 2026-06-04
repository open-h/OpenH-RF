# SPDX-License-Identifier: Apache-2.0
"""Smoke-tests that run each standalone example script.

Every script is executed in a subprocess so side-effects (cwd changes,
generated files, etc.) are fully isolated.
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
HEAVY_SCRIPTS = [
    ROOT / "examples" / "nv-raw2insights-us" / "convert.py",
]

# Template directories whose convert.py + reconstruct.py must run in sequence.
# The scripts resolve paths relative to __file__, so generated files land inside
# the template directory and are cleaned up after each test.
LIGHT_TEMPLATE_DIRS = [
    ROOT / "examples" / "templates" / "color-doppler",
    ROOT / "examples" / "templates" / "echocardiography",
    ROOT / "examples" / "templates" / "segmentation",
]
HEAVY_TEMPLATE_DIRS = [
    ROOT / "examples" / "templates" / "verasonics",
]


def _script_id(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _template_id(directory: Path) -> str:
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


def _run_template(template_dir: Path, tmp_path: Path) -> None:
    """Run convert.py then reconstruct.py for a template, cleaning up afterwards."""
    convert = template_dir / "convert.py"
    reconstruct = template_dir / "reconstruct.py"
    generated = list(template_dir.glob("*.hdf5")) + list(template_dir.glob("*.png"))
    try:
        _assert_clean_exit(convert, _run(convert, tmp_path))
        _assert_clean_exit(reconstruct, _run(reconstruct, tmp_path))
    finally:
        # Remove any files that were not present before the test.
        for f in template_dir.glob("*.hdf5"):
            if f not in generated:
                f.unlink(missing_ok=True)
        for f in template_dir.glob("*.png"):
            if f not in generated:
                f.unlink(missing_ok=True)


@pytest.mark.parametrize(
    "script", LIGHT_SCRIPTS, ids=[_script_id(s) for s in LIGHT_SCRIPTS]
)
def test_script_runs(script, tmp_path):
    """Run a lightweight example script and assert it exits cleanly."""
    _assert_clean_exit(script, _run(script, tmp_path))


@pytest.mark.heavy
@pytest.mark.parametrize(
    "script", HEAVY_SCRIPTS, ids=[_script_id(s) for s in HEAVY_SCRIPTS]
)
def test_heavy_script_runs(script, tmp_path):
    """Run an example script that needs network / HF Hub access."""
    _assert_clean_exit(script, _run(script, tmp_path))


@pytest.mark.parametrize(
    "template_dir",
    LIGHT_TEMPLATE_DIRS,
    ids=[_template_id(d) for d in LIGHT_TEMPLATE_DIRS],
)
def test_template_runs(template_dir, tmp_path):
    """Run convert.py then reconstruct.py for a lightweight template."""
    _run_template(template_dir, tmp_path)


@pytest.mark.heavy
@pytest.mark.parametrize(
    "template_dir",
    HEAVY_TEMPLATE_DIRS,
    ids=[_template_id(d) for d in HEAVY_TEMPLATE_DIRS],
)
def test_heavy_template_runs(template_dir, tmp_path):
    """Run convert.py then reconstruct.py for a template that needs network access."""
    _run_template(template_dir, tmp_path)
