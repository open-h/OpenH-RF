# SPDX-License-Identifier: Apache-2.0
"""Save a pipeline to a YAML configuration file

This example demonstrates how a zea pipeline can be saved to a YAML configuration file and
then loaded back into a zea Config object. This allows for easy sharing and reproducibility of
processing pipelines without needing to share the code itself.

We will show a typical ultrasound signal processing pipeline that requires all needed steps to go
from raw RF ultrasound channel data to a final B-mode image. The pipeline will serve as a basis for
most use cases, although certain data and applications require slight changes to the pipeline.
For examples of configuration files see:

- PICMUS: https://huggingface.co/datasets/zeahub/picmus/blob/main/config_rf.yaml
- zea-cardiac-2026: https://huggingface.co/datasets/zeahub/zea-cardiac-2026/blob/main/config.yaml
- zea-carotid-2023: https://huggingface.co/datasets/zeahub/zea-carotid-2023/blob/main/config.yaml

Which can be automatically loaded from Hugging Face using:

- `config = zea.Config.from_path("hf://zeahub/picmus/config_rf.yaml")`
- `config = zea.Config.from_path("hf://zeahub/zea-cardiac-2026/config.yaml")`
- `config = zea.Config.from_path("hf://zeahub/zea-carotid-2023/config.yaml")`

"""

import zea
from zea.ops import (
    Beamform,
    Demodulate,
    Downsample,
    EnvelopeDetect,
    LogCompress,
    Normalize,
)

pipeline = zea.Pipeline(
    operations=[
        Demodulate(),
        Downsample(factor=4),
        Beamform(
            beamformer="delay_multiply_and_sum",
            enable_pfield=True,
        ),
        EnvelopeDetect(),
        Normalize(),
        LogCompress(),
    ],
)

pipeline.to_yaml("pipeline.yaml")

config = zea.Config.from_path("pipeline.yaml")
print(config)

# <Config {'pipeline': {'operations': [{'name': 'demodulate'}, {'name': 'downsample'}, {'name': 'beamform', 'params': {'beamformer': 'delay_multiply_and_sum', 'enable_pfield': True}}, {'name': 'envelope_detect'}, {'name': 'normalize'}, {'name': 'log_compress'}]}}> # noqa: E501
