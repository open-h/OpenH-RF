# SPDX-License-Identifier: Apache-2.0
"""Example reconstruction script for the concordia dataset of OpenH-RF.

Dataset link: https://huggingface.co/datasets/nvidia/OpenH-RF/tree/main/concordia

B-mode reconstruction of full synthetic aperture (FSA) channel data, shown
alongside the capture's label and its scatterer field.

Panels (all on shared equal-aspect mm axes over the imaging FOV, so they line up):
  1. the B-mode reconstructed here from ``data/raw_data``;
  2. the capture's label, if present --
       - ``data/segmentation`` foreground (anechoic / hypoechoic / hyperechoic), or
       - ``data/diverse_source_image`` (diverse class).
     Point-target captures carry no label, so this panel is omitted;
  3. ``data/scatterers`` -- the Field II point-scatterer cloud, coloured by
     |amplitude| on a black background (so it reads like the B-mode: dark = weak
     scatterers, bright = strong). Cropped to the FOV so it aligns with panel 1.

The reconstruction grid is pinned to the field of view of the stored
``data/image``, so the result reproduces that reference B-mode.

Requires zea>=0.1.6 (https://github.com/tue-bmd/zea), the library that does the
ultrasound processing here, together with one of its Keras backends (JAX,
PyTorch or TensorFlow). Installation instructions are at
https://zea.readthedocs.io/en/latest/installation.html.

Usage:
    python reconstruct.py
"""

import os

os.environ.setdefault("KERAS_BACKEND", "jax")
os.environ.setdefault("MPLBACKEND", "Agg")

from pathlib import Path

import numpy as np
import zea
from zea.ops import (
    ApplyWindow,
    Beamform,
    Cast,
    Demodulate,
    EnvelopeDetect,
    LogCompress,
    Normalize,
)

HERE = Path(__file__).parent

# Receive F-number used for every reference reconstruction in this submission's
# data card. zea's own Parameters default (1.0) is NOT what was used to produce
# the reference images -- f_number is a reconstruction-time parameter, not
# something the zea *file* format stores, so it must be supplied explicitly
# here rather than relying on the file alone to reproduce the documented image.
F_NUMBER = 1.75

# --- Inputs -----------------------------------------------------------------
# Defaults stream straight from the published corpus. Swap any of these for a
# local path to run against your own copy.
ZEA_FILE = "hf://nvidia/OpenH-RF/concordia/data/image_0753.hdf5"
FRAME = 0  # Frame index (default: 0)
OUT = HERE / "assets" / "reference_capture.png"
SAVE_YAML = None  # Optionally write the pipeline to a reusable pipeline.yaml


def build_pipeline() -> zea.Pipeline:
    """Return the zea B-mode pipeline used for every reference reconstruction.

    Cast -> ApplyWindow -> Demodulate -> Beamform(...)
    -> EnvelopeDetect -> Normalize -> LogCompress
    """
    # A full synthetic aperture: 128 transmits, one element fired per transmit.
    # The cast is explicit because the raw channel data is int16.
    return zea.Pipeline(
        operations=[
            Cast(dtype="float32"),
            ApplyWindow(),
            Demodulate(),
            Beamform(beamformer="delay_and_sum"),
            EnvelopeDetect(),
            Normalize(output_range=[0.0, 1.0]),
            LogCompress(),
        ]
    )


def _extent_mm(coordinates) -> list:
    """[x_min, x_max, z_max, z_min] in mm for imshow (depth increasing downward)."""
    c = np.asarray(coordinates)
    x, z = c[..., 0] * 1e3, c[..., 2] * 1e3
    return [x.min(), x.max(), z.max(), z.min()]


def _label(ax, title):
    ax.set_title(title)
    ax.set_xlabel("Lateral [mm]")
    ax.set_ylabel("Axial depth [mm]")


def load_capture(zea_path: Path) -> dict:
    """Read a capture in a single pass: channel data, grid, and any overlays.

    The file is opened once because the default inputs stream from the Hub, so
    a second open would re-fetch the same remote object.
    """
    with zea.File(str(zea_path)) as f:
        # Merge scan + probe from the file (single-track file; for multi-track
        # use f.tracks[i].load_parameters() / f.tracks[i].data.raw_data).
        parameters = f.load_parameters()
        raw = f.data.raw_data[:]
        # The reconstruction FOV is a reconstruction-time choice and is NOT part
        # of the zea scan spec, so load_parameters() alone falls back to zea's
        # aperture-wide, full-depth default grid. Pin the grid to this dataset's
        # intended imaging region by reusing the stored reference image's own
        # coordinate grid (data/image), so the reconstruction lands on exactly
        # the same pixels as the documented reference B-mode.
        image_coords = np.asarray(f.data.image.coordinates[:])  # (z, x, 3), metres

        # Which label a capture carries depends on its class: a segmentation
        # mask for anechoic/hypoechoic/hyperechoic, a weight map for diverse,
        # neither for point targets.
        seg_fg = seg_extent = seg_label = None
        if "segmentation" in f.data:
            seg = f.data.segmentation
            seg_fg = np.asarray(seg.values[:])[0, :, :, 1].astype(float)
            seg_extent = _extent_mm(seg.coordinates[:])
            seg_label = list(seg.labels.asstr()[:])[1]

        div_img = div_extent = None
        if "diverse_source_image" in f.data:
            div = f.data.diverse_source_image
            div_img = np.asarray(div.values[:])[0]
            div_extent = _extent_mm(div.coordinates[:])

        sca_amp = sca_pos = None
        if "scatterers" in f.data:
            sca = f.data.scatterers
            sca_amp = np.asarray(sca.values[:])[0, :, 0]
            sca_pos = np.asarray(sca.coordinates[:])[:, 0, :]

    xlims = (float(image_coords[..., 0].min()), float(image_coords[..., 0].max()))
    zlims = (float(image_coords[..., 2].min()), float(image_coords[..., 2].max()))
    # update() keeps every derived acquisition parameter from the file (n_tx,
    # n_ax, ...) and only overlays the FOV grid, invalidating the cached grid.
    parameters.update(xlims=xlims, zlims=zlims, grid_size_x=image_coords.shape[1])

    return {
        "raw": raw,
        "parameters": parameters,
        "seg_fg": seg_fg,
        "seg_extent": seg_extent,
        "seg_label": seg_label,
        "div_img": div_img,
        "div_extent": div_extent,
        "sca_amp": sca_amp,
        "sca_pos": sca_pos,
    }


def reconstruct(raw, parameters, frame_index: int = 0, pipeline=None) -> np.ndarray:
    """Reconstruct a single B-mode frame.

    Returns a 2D float array (log-compressed dB, typically in [-60, 0]) on the
    grid described by ``parameters`` (read parameters.xlims/zlims for axes).
    """
    pipeline = pipeline or build_pipeline()
    inputs = pipeline.prepare_parameters(parameters, f_number=F_NUMBER)
    # return_numpy=True uses keras.ops.convert_to_numpy for multi-backend support.
    outputs = pipeline(**{pipeline.key: raw}, **inputs, return_numpy=True)
    return outputs[pipeline.output_key][frame_index]


def main():
    import matplotlib.pyplot as plt
    from mpl_toolkits.axes_grid1 import make_axes_locatable

    zea.init_device()

    pipe = build_pipeline()
    if SAVE_YAML is not None:
        pipe.to_yaml(str(SAVE_YAML))
        print(f"Saved pipeline to {SAVE_YAML}")

    cap = load_capture(ZEA_FILE)
    params = cap["parameters"]
    bmode = reconstruct(cap["raw"], params, frame_index=FRAME, pipeline=pipe)
    print(f"Reconstructed: {bmode.shape}")

    xlims_mm = np.asarray(params.xlims) * 1e3
    zlims_mm = np.asarray(params.zlims) * 1e3
    # z inverted: depth downward
    extent = [xlims_mm[0], xlims_mm[1], zlims_mm[1], zlims_mm[0]]
    xmin, xmax, zmax, zmin = extent

    panels = ["bmode"]
    if cap["seg_fg"] is not None or cap["div_img"] is not None:
        panels.append("label")
    if cap["sca_amp"] is not None:
        panels.append("scatterers")

    zea.visualize.set_mpl_style()
    fig, axes = plt.subplots(1, len(panels), figsize=(6.5 * len(panels), 6), squeeze=False)
    ax = {name: axes[0][i] for i, name in enumerate(panels)}

    # 1: the reconstruction itself.
    # aspect="equal": 1 mm lateral == 1 mm axial on screen (physically faithful,
    # no stretching). extent is in mm, so the image renders at its true
    # proportions rather than being stretched to fill the axes box.
    ax["bmode"].imshow(bmode, cmap="gray", vmin=-60, vmax=0, extent=extent, aspect="equal")
    _label(ax["bmode"], f"{Path(ZEA_FILE).stem} — B-mode reconstruction, frame {FRAME}")
    cax = make_axes_locatable(ax["bmode"]).append_axes("right", size="5%", pad=0.05)
    fig.colorbar(ax["bmode"].images[0], cax=cax, label="dB")

    # 2: the capture's class-specific label, when it carries one.
    if "label" in ax:
        if cap["seg_fg"] is not None:
            ax["label"].imshow(cap["seg_fg"], cmap="gray", extent=cap["seg_extent"], aspect="equal")
            _label(ax["label"], f"data/segmentation foreground: {cap['seg_label']}")
        else:
            div_img = cap["div_img"]
            ax["label"].imshow(
                div_img,
                cmap="gray",
                vmin=0.0,
                vmax=1.0,
                extent=cap["div_extent"],
                aspect="equal",
            )
            _label(
                ax["label"],
                f"data/diverse_source_image  [{div_img.min():.2f}, {div_img.max():.2f}]",
            )

    # 3: the Field II scatterer cloud the capture was simulated from.
    if "scatterers" in ax:
        sca_pos, sca_amp = cap["sca_pos"], cap["sca_amp"]
        sx, sz = sca_pos[:, 0] * 1e3, sca_pos[:, 2] * 1e3  # mm
        # crop to the reconstruction FOV so this panel aligns with the others
        m = (sx >= xmin) & (sx <= xmax) & (sz >= zmin) & (sz <= zmax)
        mag = np.abs(sca_amp[m])
        vmax = float(np.percentile(mag, 99.0)) if mag.size else 1.0
        axs = ax["scatterers"]
        axs.set_facecolor("black")
        axs.scatter(
            sx[m],
            sz[m],
            c=mag,
            cmap="gray",
            s=0.3,
            vmin=0.0,
            vmax=vmax,
            linewidths=0,
            rasterized=True,
        )
        axs.set_xlim(xmin, xmax)
        axs.set_ylim(zmax, zmin)  # depth downward, matching the image panels
        axs.set_aspect("equal")
        _label(axs, f"data/scatterers  (|amplitude|, {int(m.sum()):,} pts in FOV)")

    fig.tight_layout()
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=150, bbox_inches="tight")
    print(f"Saved reconstruction to {OUT}")


if __name__ == "__main__":
    main()
