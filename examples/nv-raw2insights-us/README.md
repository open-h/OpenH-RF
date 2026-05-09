# NV-Raw2Insights-US → openh-rf

Convert one sample from [nvidia/NV-Raw2Insights-US](https://huggingface.co/datasets/nvidia/NV-Raw2Insights-US)
to openh-rf HDF5, then beamform and visualize.

Environment setup is in the [main README](../../README.md). After `uv sync`:

```bash
# 1. stream one sample from HF, write HDF5
uv run python examples/nv-raw2insights-us/convert_nv_raw2insights_us.py

# 2. beamform via zea, write 7-panel PNG
uv run python examples/nv-raw2insights-us/reconstruct_nv_raw2insights_us.py
```
