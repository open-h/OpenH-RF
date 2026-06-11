# Tracked CIRS Simulation -> OpenH-RF

A worked example: convert one tracked CIRS phantom acquisition from
[`Felixdu11/tracked_CIRS_simulated`](https://huggingface.co/datasets/Felixdu11/tracked_CIRS_simulated)
into the OpenH-RF (`zea`) file format, then reconstruct a B-mode image,
visualize the tracked probe trajectory, and optionally max-compound the tracked
frames into a small 3D volume.

## Running this example

Environment setup is in the [main README](../../README.md).

```bash
# 1. download the source files from HF and write the zea-format HDF5 + config
uv run python examples/tracked_dataset/convert_cirs_tracked.py

# 2. beamform one frame and save the B-mode + tracked trajectory figure
uv run python examples/tracked_dataset/reconstruct_cirs_tracked.py

# 3. optional: install the volume renderer used by the 3D example
uv pip install pyvista

# 4. beamform several frames, max-compound them, and save .vti + rendered PNGs
uv run python examples/tracked_dataset/reconstruct_cirs_tracked_3d.py

# add --live to open an interactive PyVista view after rendering
uv run python examples/tracked_dataset/reconstruct_cirs_tracked_3d.py --live
```

---

# Data Card - Tracked CIRS Simulation

## Dataset Description

This example packages a single tracked phantom ultrasound acquisition into the
OpenH-RF format. The source data consists of raw RF image frames stored in
`raw/cirs_imaging.hdf5` plus a separate `raw/cirs_tracking.ts` stream of
timestamped 4x4 probe poses. [`convert_cirs_tracked.py`](convert_cirs_tracked.py)
copies the RF and scan metadata into a `zea` HDF5 file, converts the tracked
translations from millimetres to metres, stores rotations as quaternions, and
writes a reusable beamforming config. The reconstruction scripts then validate
both the RF metadata and the image-to-tracker timing alignment. Data type:
simulated phantom.

Source dataset:
<https://huggingface.co/datasets/Felixdu11/tracked_CIRS_simulated>

## Dataset Contributor(s)

The source dataset is published on Hugging Face under the `Felixdu11`
namespace. Additional contributor or contact metadata is not carried in this
example repository.

## Dataset Creation Date

11 June 2026

## License / Terms of Use

[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/legalcode.en).
The data is cleared for this license (synthetic data, no patient information).

## Intended Usage

Serve as an example of how to convert a tracked ultrasound dataset into the OpenH-RF format, and how to use the stored probe pose metadata for tracked reconstruction and visualization.

## Dataset Characterization

- **Data collection method:** simulated phantom
- **Labeling method:** derived tracking metadata; no segmentation or class labels
- **Acquisition system:** simulated linear probe; probe geometry, element
  width, center frequency, and scan metadata are copied from the source
  `scan` group during conversion

## Dataset Format

The converted output is a single acquisition in the
[`zea` file format](https://zea.readthedocs.io/en/v0.1.0a2/data-acquisition.html).
[`convert_cirs_tracked.py`](convert_cirs_tracked.py) downloads the source
imaging and tracking files, preserves the RF arrays as `float32`, copies the
scan metadata, derives frame-to-frame timing for the transmit schedule, and
stores tracked probe pose in `metadata.probe_pose`. It also writes
`data/config.yaml`, a saved DAS beamforming pipeline used by both reconstruction
examples.

Converted HDF5 contents:

| Group / field | Shape | Dtype | Units | Description |
|---|---|---|---|---|
| `data/raw_data` | `[n_frames, ...]` | float32 | source RF units | Raw RF frames copied from the source imaging file |
| `scan/*` | -- | mixed | source units / seconds | Scan metadata copied from the source `scan` group; `time_to_next_transmit` is derived from image timestamps |
| `metadata/probe_pose.translation` | `[n_pose_samples, 3]` | float32 | m | Probe translations converted from mm to m |
| `metadata/probe_pose.rotation` | `[n_pose_samples, 4]` | float32 | -- | Probe orientations as quaternions in `xyzw` order |
| `metadata/probe_pose.timestamps` | `[n_pose_samples]` | float32 | s | Pose timestamps relative to the first tracked pose sample |
| `metadata/probe_pose.start_time_offset` | scalar | float32 | s | Offset from the first ultrasound image time to the first pose sample |

## Dataset Quantification

- **Samples / frames:** one tracked acquisition with multiple ultrasound frames
  and an independently sampled pose stream
- **Train / val / test split:** N/A
- **Total size on disk:** depends on the downloaded source files and the local
  converted HDF5

## Subject Metadata

Not applicable for human-subject reporting. This is simulated phantom data with
no patient or animal metadata and no PHI.

## Data Validation

[`reconstruct_cirs_tracked.py`](reconstruct_cirs_tracked.py) loads the converted
RF data and `metadata.probe_pose`, beamforms one frame with the saved config,
and plots the x/y/z tracked probe translation at ultrasound frame times. This is
a direct sanity check that the scan metadata, beamforming config, and
image-to-tracker timing line up correctly.

[`reconstruct_cirs_tracked_3d.py`](reconstruct_cirs_tracked_3d.py) interpolates
tracked poses at selected image times, beamforms several frames, max-compounds
them into a Cartesian voxel grid, writes a `.vti` volume, and saves rendered
views from multiple directions. This is an additional check that the stored
poses are usable for downstream tracked-volume reconstruction.

## Known Issues

- The ultrasound image stream and the probe pose stream are sampled
  independently; the reconstruction scripts will raise an error if selected
  image times fall outside the tracked pose time range.
- The 3D visualization example depends on optional `pyvista`, which is not
  installed by default.

## Ethical Considerations

This example uses simulated phantom data only. It contains no human-subject or
animal-subject information and no protected health information.
