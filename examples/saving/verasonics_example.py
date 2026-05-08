# SPDX-License-Identifier: Apache-2.0
"""
Example script to convert a Verasonics .mat file to a zea dataset
using the `VerasonicsFile` class to read the Verasonics workspace `.mat` file
and `zea.File` to save the data to `.hdf5` format.

Note that this can also be done with the CLI: <https://zea.readthedocs.io/en/latest/cli.html#python-m-zea-data-convert-verasonics>

But this script is more flexible and can be adapted to the needs of this project.
"""

from zea import log
from zea.data.convert.verasonics import VerasonicsFile
from zea import File

from huggingface_hub import hf_hub_download

# verasonics_file_path = "hf://zeahub/phantoms/2025_05_19_cirs_planewave.mat"
# first download the file from zeahub to the local filesystem, since the VerasonicsFile class only works with local files
verasonics_file_path = hf_hub_download(
    repo_id="zeahub/phantoms",
    filename="2025_05_19_cirs_planewave.mat",
    repo_type="dataset",
) # TODO: add remote file support to VerasonicsFile class

output_path = "./2025_05_19_cirs_planewave.hdf5"

with VerasonicsFile(verasonics_file_path, "r") as file:
    log.info("Reading Verasonics file...")
    scan_dict = file.read_scan(
        # the index of the buffer to read from, if there are multiple buffers in the file
        buffer_index=0,
        # when rf data has been accumulated on the verasonics (e.g. for pulse inversion)
        allow_accumulate=True,
        # which frames to read, if there are multiple frames in the buffer
        frames="all",
    )
    raw_data = file.read_raw_data(buffer_index=0)

    # Generate the zea dataset
    log.info("Generating openh-rf dataset...")
    File.create(
        path=output_path,
        data={"raw_data": raw_data},
        scan=scan_dict,
        probe_name=file.probe_name,
        us_machine="Verasonics Vantage 256",
        description="Test acquisition on a CIRS phantom.",
    )

    log.info(
        "Saved Verasonics acquisition to './2025_05_19_cirs_planewave.hdf5'.\n"
        "Open it back with `zea.File(...)` to inspect the converted data."
    )
