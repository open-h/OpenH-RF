"""Convert: download a Verasonics .mat file and save as a zea HDF5 file.

Downloads a Verasonics workspace .mat file from the zeahub/phantoms dataset on
Hugging Face and converts it to the openh-rf HDF5 format using zea.File.create.
VerasonicsFile reads all scan parameters directly from the .mat file.

Requires:
    pip install huggingface_hub

Usage:
    python examples/saving/verasonics/convert.py
    python examples/saving/verasonics/convert.py --output my_file.hdf5
"""

import argparse
from pathlib import Path

from huggingface_hub import hf_hub_download
from zea import File, log
from zea.data.convert.verasonics import VerasonicsFile

HF_REPO = "zeahub/phantoms"
HF_FILENAME = "2025_05_19_cirs_planewave.mat"
DEFAULT_OUTPUT = Path(__file__).parent / "verasonics_sample.hdf5"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    # Download the .mat file from Hugging Face (cached after first run)
    log.info(f"Downloading {HF_FILENAME} from {HF_REPO}...")
    mat_path = hf_hub_download(
        repo_id=HF_REPO, filename=HF_FILENAME, repo_type="dataset", revision="v0.1.0"
    )

    # Create a verasonics .mat file by saving your verasonics workspace in matlab.
    with VerasonicsFile(mat_path, "r") as vf:
        log.info("Reading Verasonics file...")
        data_dict, scan_dict, additional_elements = vf.read_verasonics_file(
            allow_accumulate=True,
        )

        # Generate the zea dataset
        log.info("Generating zea dataset...")
        f = File.create(
            path=str(args.output),
            data=data_dict,
            scan=scan_dict,
            probe=vf.probe.to_probe_spec(),
            description="Verasonics Vantage 256 - CIRS phantom plane-wave acquisition (from .mat file)",
            overwrite=True,
        )
        f.close()

    print(f"Saved: {args.output}  ({args.output.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
