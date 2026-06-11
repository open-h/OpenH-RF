# Tracked CIRS dataset

Convert a tracked CIRS phantom acquisition from
[openh-rf/tracked_CIRS_simulated](https://huggingface.co/datasets/openh-rf/tracked_CIRS_simulated),
then beamform it and visualize the probe trajectory and 3D reconstruction.

Environment setup is in the [main README](../../README.md).

```bash
# 1. create ZEA HDF5 + config from the default HF raw files
python examples/tracked_dataset/convert_cirs_tracked.py

# 2. beamform the converted dataset, write B-mode + trajectory PNG
python examples/tracked_dataset/reconstruct_cirs_tracked.py

# 3. max-compound the converted dataset, write VTI + side-view PNGs; add --live for an interactive view
python examples/tracked_dataset/reconstruct_cirs_tracked_3d.py
```
