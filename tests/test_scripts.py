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
    ROOT / "examples" / "saving" / "color_doppler_example.py",
    ROOT / "examples" / "saving" / "echocardiography_example.py",
    ROOT / "examples" / "saving" / "segmentation_map_example.py",
]
HEAVY_SCRIPTS = [
    ROOT / "examples" / "saving" / "verasonics_example.py",
    ROOT / "examples" / "nv-raw2insights-us" / "convert.py",
]


def _script_id(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _run(script: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "KERAS_BACKEND": "jax"},
    )


def _assert_clean_exit(script: Path, result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, (
        f"Script {script.name} failed (exit {result.returncode}).\n"
        f"--- stdout ---\n{result.stdout[-2000:]}\n"
        f"--- stderr ---\n{result.stderr[-2000:]}"
    )


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
