# SPDX-License-Identifier: Apache-2.0
"""Convert: convert channel data from the PALA rat-brain dataset.

The data is available at https://doi.org/10.5281/zenodo.7883226

Usage:
    python examples/pala/convert.py --download
    python examples/pala/convert.py --input path/to/RF_002.hdf5
"""

import argparse
import zipfile
from pathlib import Path

import h5py
import numpy as np
import requests
from tqdm import tqdm
from zea import File

DEFAULT_INPUT = Path(__file__).parent / "RF" / "RF_002.hdf5"
DEFAULT_OUTPUT = Path(__file__).parent / "pala_sample.hdf5"


def convert(path: Path, output_path: Path) -> Path:
    """Convert a PALA HDF5 file to openh-rf format.

    Args:
        path: Path to the source PALA HDF5 file.
        output_path: Destination path for the openh-rf HDF5 file.

    Returns:
        Path to the written output file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(path, "r") as file:
        probe_geometry, probe_name = _probe_geometry(file)
        rf = file["rf"]["rf"]

        sound_speed = _scalar(rf.attrs["speed_of_sound_m_per_s"])
        center_frequency = _scalar(rf.attrs["demod_frequency_MHz"]) * 1e6
        polar_angles = rf.attrs["angles_rad"]
        sampling_frequency = _scalar(rf.attrs["decim_sample_rate_MHz"]) * 1e6 / 4

        raw_data = rf[:].transpose(3, 2, 1, 0)[..., None].astype(np.float32)
        raw_data = _bs100bw_to_iq(raw_data)
        n_frames, n_tx, n_ax, n_el, n_ch = raw_data.shape  # noqa: F841

        waveforms_two_way = _waveform_samples(file["rf"]["pulse"]["Wvfm2Wy"], n_tx)
        waveforms_one_way = _waveform_samples(file["rf"]["pulse"]["Wvfm1Wy"], n_tx)

        wavelength = _scalar(rf.attrs["wavelength_mm"]) * 1e-3
        start_depth_wl = rf.attrs["sampling_range_depth_wv"][0]
        initial_times = np.full(
            n_tx, start_depth_wl * 2 * wavelength / sound_speed, dtype=np.float32
        )

        t0_delays = (file["rf"]["delays"][:].transpose(1, 0) * wavelength / sound_speed).astype(
            np.float32
        )

        # Element width is not stored in the file; 90 % of the pitch is a reasonable guess.
        pitch = 0.1e-3
        element_width = 0.9 * pitch

    data = {"raw_data": raw_data}

    probe = {
        "name": probe_name,
        "type": "linear",
        "probe_geometry": probe_geometry,
        "element_width": element_width,
    }

    scan = {
        "sampling_frequency": float(sampling_frequency),
        "center_frequency": float(center_frequency),
        "demodulation_frequency": float(center_frequency),
        "sound_speed": float(sound_speed),
        "initial_times": initial_times,
        "t0_delays": t0_delays,
        "focus_distances": np.zeros(n_tx, dtype=np.float32),
        "polar_angles": polar_angles.astype(np.float32),
        "azimuth_angles": np.zeros(n_tx, dtype=np.float32),
        "tx_apodizations": np.ones((n_tx, n_el), dtype=np.float32),
        "transmit_origins": np.zeros((n_tx, 3), dtype=np.float32),
        "waveforms_two_way": waveforms_two_way,
        "waveforms_one_way": waveforms_one_way,
    }

    metadata = {
        "credit": (
            "Heiles, Chavignon, Hingot, Lopez, Teston and Couture. Performance benchmarking of "
            "microbubble-localization algorithms for ultrasound localization microscopy, "
            "Nature Biomedical Engineering, 2022, (doi.org/10.1038/s41551-021-00824-8). "
            "Original data available at https://zenodo.org/records/7883227"
        ),
        "subject": {"type": "animal"},
        "annotations": {
            "anatomy": "brain",
            "label": "in vivo",
        },
    }

    File.create(
        str(output_path),
        data=data,
        scan=scan,
        probe=probe,
        metadata=metadata,
        description=(
            f"PALA in-vivo rat brain ultrasound localization microscopy data.\n"
            f"Note:\n"
            f"- Element width is guessed at {element_width * 1e3:.1f} mm."
        ),
        overwrite=True,
    )
    return output_path


def _probe_geometry(file) -> tuple[np.ndarray, str]:
    """Extract probe element positions and name from a PALA HDF5 file.

    Args:
        file: Open h5py File object.

    Returns:
        Tuple of ``(probe_geometry, probe_name)`` where ``probe_geometry`` has
        shape ``(n_el, 3)`` in metres.
    """
    us_probe = file["rf"]["us_probe"]
    probe_name = us_probe.attrs["name"].decode("utf-8")
    probe_x = us_probe[:] * 1e-3
    probe_geometry = np.stack([probe_x, np.zeros_like(probe_x), np.zeros_like(probe_x)], axis=-1)
    return probe_geometry, probe_name


def _waveform_samples(dataset, n_tx: int) -> np.ndarray:
    """Broadcast a single waveform to all transmit events.

    Args:
        dataset: h5py dataset containing the waveform samples.
        n_tx: Number of transmit events.

    Returns:
        Waveform array of shape ``(n_tx, n_samples)``.
    """
    samples = dataset[:]
    return (samples[None] * np.ones((n_tx, 1))).astype(np.float32)


def _scalar(arr) -> float:
    """Reduce an HDF5 attribute or numpy array to a Python float.

    Args:
        arr: Array-like value to reduce.

    Returns:
        Scalar float value.
    """
    while arr.ndim > 0:
        arr = arr[0]
    return float(arr)


def _bs100bw_to_iq(data: np.ndarray) -> np.ndarray:
    """Convert BS100BW data to IQ format ``(n_frames, n_tx, n_ax, n_el, 2)``.

    The BS100BW Verasonics sampling mode interleaves I and Q samples along the
    axial axis. Even samples are I; odd samples are Q (negated).

    Args:
        data: Input array of shape ``(n_frames, n_tx, n_ax_raw, n_el, 1)``.

    Returns:
        IQ array of shape ``(n_frames, n_tx, n_ax, n_el, 2)``.
    """
    return np.stack([data[:, :, ::2, :, 0], -data[:, :, 1::2, :, 0]], axis=-1)


def _download_and_unzip() -> None:
    url = "https://zenodo.org/records/7883227/files/RF_001_to_025.zip"
    print(f"Downloading data from {url}...")
    _download_if_absent(url, dest_dir=Path(__file__).parent)
    zip_path = Path(__file__).parent / "RF_001_to_025.zip"
    if (zip_path.parent / "RF" / "RF_025.hdf5").exists():
        print("Data already extracted. Skipping.")
        return
    print(f"Extracting {zip_path}...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(Path(__file__).parent)


def _download_if_absent(url: str, dest_dir: Path) -> None:
    filename = Path(url).name
    dest_file = dest_dir / filename
    dest_dir.mkdir(parents=True, exist_ok=True)
    if dest_file.exists():
        return

    with requests.get(url, stream=True) as response:
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        block_size = 1024

        try:
            with open(dest_file, "wb") as f:
                with tqdm(total=total_size, unit="B", unit_scale=True, desc=filename) as pbar:
                    for chunk in response.iter_content(block_size):
                        f.write(chunk)
                        pbar.update(len(chunk))
        except KeyboardInterrupt:
            if dest_file.exists():
                dest_file.unlink()
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_path",
        type=Path,
        nargs="?",
        default=DEFAULT_INPUT,
        help="Path to the source PALA HDF5 file.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download and extract the PALA dataset from Zenodo.",
    )
    args = parser.parse_args()

    if args.download:
        _download_and_unzip()

    print(f"Converting {args.input_path} ...")
    out = convert(path=args.input_path, output_path=args.output)
    print(f"Saved: {out}  ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
