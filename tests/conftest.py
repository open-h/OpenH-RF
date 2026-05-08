import os

import pytest


@pytest.fixture(autouse=True)
def run_in_tmpdir(tmp_path, monkeypatch):
    """Run every script test inside a temporary directory so generated files
    (HDF5, YAML, images, etc.) don't pollute the repo."""
    monkeypatch.chdir(tmp_path)
    # Some scripts reference ./temp/
    os.makedirs(tmp_path / "temp", exist_ok=True)
