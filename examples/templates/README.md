# Templates

The examples in this directory are **templates**, intended to provide a starting point for writing your own `convert.py`, and `reconstruct.py` scripts, along with a `pipeline.yaml` defining a beamforming pipeline and associated parameters. The templates show:

- how to structure scan parameters, probe geometry, and metadata for a given modality;
- which fields are required versus optional in the openh-rf format;
- how to call `zea.File.create` and verify the result.

For most templates, we have included dummy data to indicate the correct data types and tensor shapes for the variables supported by the `zea` data format. In the Verasonics template, we have included real Verasonics data saved in
.mat format from the Verasonics matlab workspace. For more information on the data format, please refer to the
[`zea` data format reference](https://zea.readthedocs.io/en/v0.1.0a2/data-acquisition.html#zea-data-format-reference).
