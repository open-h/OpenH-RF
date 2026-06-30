"""Convert: download a Verasonics .mat file and save as a zea HDF5 file.

Downloads a Verasonics workspace .mat file from the zeahub/phantoms dataset on
Hugging Face and converts it to the openh-rf HDF5 format using zea.File.create.
VerasonicsFile reads all scan parameters directly from the .mat file.

.. note::

    The .mat file must be saved in HDF5 format (MATLAB v7.3 or later).
    Older .mat files are not HDF5-compatible and cannot be read by this converter.
    To save in the correct format from MATLAB, use the '-v7.3' flag::

        save("C:/path/to/raw_data.mat", "-v7.3")

Requires:
    pip install huggingface_hub

Usage:
    python examples/templates/verasonics/convert.py
    python examples/templates/verasonics/convert.py --output my_file.hdf5
"""

import argparse
from pathlib import Path

import zea
from huggingface_hub import hf_hub_download
from zea import File, log
from zea.data.convert.verasonics import VerasonicsFile

HF_REPO = "zeahub/phantoms"
HF_FILENAME = "2025_05_19_cirs_planewave.mat"
DEFAULT_OUTPUT = Path(__file__).parent / "verasonics_sample.hdf5"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="CUDA device ID (e.g. 'cuda:0', 'auto:1', or 'cpu')",
    )
    parser.add_argument(
        "--lens-sound-speed",
        type=float,
        default=1000.0,
        help="Speed of sound in the lens material in m/s (default: 1000.0).",
    )
    args = parser.parse_args()

    zea.init_device(device=args.device, verbose=False)

    # Download the .mat file from Hugging Face (cached after first run)
    log.info(f"Downloading {HF_FILENAME} from {HF_REPO}...")
    mat_path = hf_hub_download(
        repo_id=HF_REPO, filename=HF_FILENAME, repo_type="dataset", revision="v0.1.0"
    )

    with VerasonicsFile(mat_path, "r") as vf:
        log.info("Reading Verasonics file...")
        data_dict, scan_dict, probe_dict, custom_elements = vf.read_verasonics_file(
            allow_accumulate=True,
            lens_sound_speed=args.lens_sound_speed,
        )

        # Generate the zea dataset
        log.info("Generating zea dataset...")
        File.create(
            path=str(args.output),
            data=data_dict,
            scan=scan_dict,
            probe=probe_dict,
            description="Verasonics Vantage 256 - CIRS phantom plane-wave acquisition.",
            overwrite=True,
            metadata={
                "subject": {
                    "type": "phantom",
                    "id": "cirs-001",
                },
                "credit": "Whoever collected this dataset",
            },
            custom=custom_elements,  # note requires zea v0.1.0a5 or later
        )

    print(f"Saved: {args.output}  ({args.output.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
