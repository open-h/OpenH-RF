# SPDX-License-Identifier: Apache-2.0
"""Example how to reconstruct a B-mode image from raw RF ultrasound channel data.

Given a zea file (.hdf5) containing raw RF ultrasound channel data and a configuration file (.yaml)
describing the processing pipeline, this example demonstrates how to reconstruct a B-mode image
from the raw data. This can serve as a starting point for your own reconstruction pipeline.

For other more specific examples see the `examples` folder.
"""

import os

os.environ.setdefault("KERAS_BACKEND", "jax")

import keras
import zea

zea.init_device()  # for GPU acceleration
zea.visualize.set_mpl_style()  # for plotting

# can change to your own path (local or huggingface) of matching dataset file and config
path = "hf://zeahub/zea-cardiac-2026"
config_path = "hf://zeahub/zea-cardiac-2026/config.yaml"
revision = "v0.1.0"

config = zea.Config.from_path(config_path, revision=revision)

config.parameters.dynamic_range = (-60, 0)

file_idx = 2
num_frames = 1

# alternatively use zea.File
with zea.Dataset(path, revision=revision, lazy=True) as dataset:
    file = dataset[file_idx]
    parameters = file.load_parameters()
    parameters.update(config.parameters)

    # data has shape (num_frames, num_transmits, n_ax, n_el, n_ch)
    data = file.data.raw_data[:num_frames, parameters.selected_transmits, ...]


pipeline = zea.Pipeline.from_config(config)

inputs = pipeline.prepare_parameters(parameters)

inputs = {pipeline.key: data, **inputs}
outputs = pipeline(**inputs)
image = outputs[pipeline.output_key]

image = keras.ops.convert_to_numpy(image)
image = keras.ops.squeeze(image)
image = zea.display.to_8bit(image, dynamic_range=parameters.dynamic_range)

image.save("image.png")
print("Succesfully saved image to './image.png'")
