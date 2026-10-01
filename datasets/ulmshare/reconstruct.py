# SPDX-License-Identifier: Apache-2.0
"""Example reconstruction script for the ulmshare dataset of OpenH-RF.

Dataset link: https://huggingface.co/datasets/nvidia/OpenH-RF/tree/main/ulmshare

B-mode, power-Doppler and ULM reconstruction of transcranial plane-wave IQ
channel data.

Alongside the B-mode, a tissue-suppression pass gives the clutter-filtered IQ
movie behind the power-Doppler output and the ULM density map (see :mod:`ulm`).
Everything is written into OUT_DIR: ``bmode.png``, ``power_doppler.png``,
``power_doppler_movie.gif`` and ``ulm_density.png``.

Only a fraction of the acquisition is used. By default the Power-Doppler and
ULM outputs are built from the first ``N_FRAMES`` = 50 buffers (20000 frames,
~22 GB) of mouse_10/acquisition_1, an acquisition of 160000 frames (~178 GB),
streamed from the Hub. That gives a recognisable vascular map, though sparser
than the one in the ULMShare paper. Far fewer frames is not much use for ULM:
the first buffers are typically recorded before the microbubble bolus arrives,
so their density map is near-empty. To reproduce the paper, set
``N_FRAMES = None`` to use all frames, streamed or from a local copy (point
``ZEA_FILE`` at it).

The frames are processed one 400-frame acquisition buffer at a time -- stream,
beamform, SVD clutter filter, localize, track -- so memory stays flat however
many frames are used, and the next buffer is read while the current one is
processed. Each stage's output is checkpointed per buffer under zea's cache
directory (``CHECKPOINT_DIR``), so an interrupted run resumes, and re-running
with, e.g., other ULM parameters recomputes only the stages they affect.

Requires zea>=0.1.6 (https://github.com/tue-bmd/zea), the library that does the
ultrasound processing here, together with one of its Keras backends (JAX,
PyTorch or TensorFlow). Installation instructions are at
https://zea.readthedocs.io/en/latest/installation.html.

Usage:
    python reconstruct.py
"""

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager

os.environ.setdefault("KERAS_BACKEND", "jax")
os.environ.setdefault("MPLBACKEND", "Agg")

from pathlib import Path

import h5py
import hdf5plugin  # noqa: F401  (registers the Blosc filter the raw data is compressed with)
import joblib
import keras
import matplotlib.pyplot as plt
import numpy as np
import ulm
import zea
from huggingface_hub import HfFileSystem
from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy.ndimage import gaussian_filter
from tqdm import tqdm
from zea.internal.cache import ZEA_CACHE_DIR, get_function_source, is_cache_disabled
from zea.internal.core import hash_elements
from zea.internal.utils import atomic_write
from zea.io_lib import matplotlib_figure_to_numpy, save_to_gif
from zea.ops import (
    Beamform,
    Cast,
    EnvelopeDetect,
    LogCompress,
    Pipeline,
    TissueSuppression,
)

# ULMShare reference beamforming grid (example_script_one_buffer / process.m).
#
# MATLAB's axes are ``startX:deltaGrid:endX-deltaGrid``: an exact 25 um pitch
# stopping one pitch short of the nominal end. zea's ``linspace(lim0, lim1, n)``
# instead spreads n samples over the whole span, which would give a 25.0627 um
# pitch -- a drift of a full pixel by the far edge, misregistering every track
# handed to MATLAB via export_for_matlab. So the limits passed to zea are the
# MATLAB grid's *last sample* (LAST_X/LAST_Z), while END_X/END_Z stay the nominal
# span for matplotlib's extent (which wants outer pixel edges).
START_X, END_X = -0.5e-2, 0.5e-2  # m
START_Z, END_Z = 0.05e-2, 0.85e-2  # m
DELTA_GRID = 2.5e-5  # m
GRID_SIZE_X = int(round((END_X - START_X) / DELTA_GRID))  # 400
GRID_SIZE_Z = int(round((END_Z - START_Z) / DELTA_GRID))  # 320
LAST_X = START_X + (GRID_SIZE_X - 1) * DELTA_GRID  # 4.975 mm
LAST_Z = START_Z + (GRID_SIZE_Z - 1) * DELTA_GRID  # 8.475 mm
EXTENT_MM = [START_X * 1e3, END_X * 1e3, END_Z * 1e3, START_Z * 1e3]
FNUMBER = 1.4

DYNAMIC_RANGE_DB = 50.0  # B-mode display floor
PD_RANGE_DB = 40.0  # Power-Doppler display range
MOVIE_FPS = 10
# Every movie frame is rendered and held in memory before the GIF is written, so
# a full acquisition (160000 frames for mouse_10) would exhaust RAM and give an unwatchable
# GIF. Longer stacks keep only their first MOVIE_MAX_FRAMES frames.
MOVIE_MAX_FRAMES = 4 * 400
BATCH_SIZE = 8  # frames beamformed per pipeline call
# The IQ channel data is sampled at 5.2 MHz: one axial sample is 148 um, ~6 BF
# pixels. Delay-and-sum interpolates linearly between samples, which dips the
# envelope between them, so bubbles look brighter at sample depths and the ULM
# localizations lock onto rows one sample apart. Band-limited (FFT) upsampling of
# the channel data along depth before beamforming removes that.
AXIAL_UPSAMPLING = 4
# Streaming: raw_data is chunked one frame per chunk, and zea 0.1.6 sends one HTTP
# request per chunk -- one per frame of a full acquisition, which trips the Hugging Face
# rate limit. beamform_stack instead reads through a block cache that fetches up to
# this many bytes per request (fewer when fewer frames are used).
STREAM_BLOCK_BYTES = 64 * 2**20
CLUTTER_FILTER_CUT = 5 / 100  # SVD cutoff as a fraction of frames (process.m)
T_PEAK = 0.0  # MUST adds no pulse-peak offset; zea's default images too deep
# ULMShare records 400-frame buffers, concatenated by convert_acquisition. The
# clutter filter runs per buffer as the reference MATLAB does -- and a
# 1600-frame Casorati SVD does not fit in GPU memory anyway.
FRAMES_PER_BUFFER = 400
# Stage checkpoints (see "Checkpoints" below). The beamformed stage is the big
# one, ~1 MB per frame (~20 GB at the default N_FRAMES); set ZEA_CACHE_DIR to put
# it on a larger disk, or CHECKPOINT = False to keep nothing.
CHECKPOINT = True
CHECKPOINT_DIR = ZEA_CACHE_DIR / "ulmshare"

# ULM parameters (see ulm.py), in beamforming-grid pixels (25 um) and frames
# (1 ms). After the bolus the filtered movie is a dense cloud of overlapping
# bubbles whose interference flickers from frame to frame; only isolated bubbles
# stand out and persist. So a bubble is a local maximum well above the typical
# level at its depth, and it is kept only if it can be followed for a while.
# Buffers where the tissue moves (breathing, heartbeat, the probe) leave clutter
# that the SVD filter does not remove and that tracks into false vessels; ULM
# skips a buffer whose tissue image decorrelates below this within it (see
# ulm.tissue_stability). Still buffers score > 0.98, moving ones 0.85-0.92.
ULM_MIN_TISSUE_CORR = 0.95
ULM_THRESHOLD = 3.0  # detection floor, as a multiple of the depth row's median |IQ|
ULM_MIN_DISTANCE = 2  # local-maximum half-width (~half the PSF)
ULM_MAX_LINKING_DISTANCE = 3.0  # max jump from a track's last position (75 um)
ULM_MAX_GAP = 5  # frames a track may go undetected before it ends
ULM_MIN_TRACK_LENGTH = 10  # detections a track needs to count
ULM_SMOOTH = 9  # moving-average window (frames) along a track before rendering
ULM_SUPER_RES = 4  # density-map pixels per BF pixel per axis (6.25 um)

# --- Inputs -----------------------------------------------------------------
# Defaults stream straight from the published corpus. Swap any of these for a
# local path to run against your own copy.
ZEA_FILE = "hf://nvidia/OpenH-RF/ulmshare/data/mouse_10_acquisition_1_zea.hdf5"
OUT_DIR = Path(__file__).parent  # Directory for all outputs (default: next to this script)
FRAME = 0  # B-mode frame index (default: 0)
# mouse_10/acquisition_1 is ~178 GB / 160000 frames; `None` means all of them,
# which is best done from a local copy. 50 buffers is ~22 GB streamed; see the
# module docstring.
N_FRAMES = 50 * FRAMES_PER_BUFFER  # frames used for Power-Doppler and ULM


def build_pipeline():
    """Build the ULMShare B-mode pipeline.

    Two departures from zea's default chain, both needed to reproduce ULMShare's
    reference, which takes ``20*log10(|IQ|)`` and subtracts the max: no
    ``Normalize`` (it rescales the envelope, changing the dB values), and
    ``clip=False`` (the default clips to -60 dB, truncating the true range).
    :func:`reconstruct` subtracts the max itself.
    """
    return Pipeline(
        [
            Cast(dtype="float32"),
            Beamform(beamformer="delay_and_sum", enable_pfield=False),
            EnvelopeDetect(),
            LogCompress(clip=False),
        ],
        with_batch_dim=True,
        jit_options="pipeline",
    )


def build_tissue_suppression_pipeline(cutoff=CLUTTER_FILTER_CUT):
    """Build the Power-Doppler pipeline: Cast -> Beamform -> TissueSuppression.

    ``filter_type`` is left to zea, which picks ``svd_complex`` from the channel
    axis for this IQ data -- the Hermitian filter ``process.m`` uses. ``cutoff``
    is only what the YAML records; :func:`clutter_filter` overrides it per buffer.
    """
    return Pipeline(
        [
            Cast(dtype="float32"),
            Beamform(beamformer="delay_and_sum", enable_pfield=False),
            TissueSuppression(cutoff=cutoff),
        ],
        with_batch_dim=True,
        jit_options="pipeline",
    )


def matlab_clutter_cutoff(n_frames, cut=CLUTTER_FILTER_CUT):
    """Component count reproducing MATLAB's SVD clutter cut.

    Both codebases build the Hermitian Gram matrix ``XᴴX`` and project onto the
    orthogonal complement of the leading subspace -- the same filter -- but index
    the kept subspace differently. MATLAB keeps ``eig_vect(:, Ncut:end)``
    (1-based, inclusive) so rejects ``Ncut - 1``; zea keeps ``V[:, cutoff:]``
    (0-based) so rejects ``cutoff``. At 400 frames that is 19 vs 20. With this
    correction the two agree to ~1e-3 relative, versus ~2.4e-1 without.
    """
    return max(int(round(n_frames * cut)) - 1, 0)


def load_pipeline(path):
    """Load a pipeline back from a YAML written by :meth:`Pipeline.to_yaml`."""
    return Pipeline.from_path(str(path))


def split_pipeline(pipeline, op_type):
    """Split ``pipeline`` around the first ``op_type`` op.

    Returns ``(head, op)``: a batched pipeline of everything before ``op_type``,
    and the op itself — letting the beamforming front run per frame while the
    across-frames op is applied to the assembled stack.
    """
    ops = list(pipeline.operations)
    idx = next(i for i, o in enumerate(ops) if isinstance(o, op_type))
    head = Pipeline(ops[:idx], with_batch_dim=True, jit_options="pipeline")
    return head, ops[idx]


def _raw_source(zea_file):
    """Return the object holding the raw-data track of ``zea_file``.

    ``convert_one_buffer`` writes a single-track file whose data hangs off the
    file itself; ``convert_acquisition`` writes a ``raw`` track alongside the
    reference summary image. Both layouts are handled so either converter's
    output can be reconstructed.
    """
    # ``track_labels`` rather than ``tracks``: the latter also computes transmit
    # timestamps, warning on every open since these files carry no
    # ``time_to_next_transmit``.
    labels = zea_file.track_labels
    if len(labels) <= 1:
        return zea_file
    if "raw" not in labels:
        raise ValueError(f"No 'raw' track in {zea_file}; found {labels}.")
    return zea_file.tracks[labels.index("raw")]


def _apply_ulmshare_grid(parameters):
    """Set the ULMShare reference BF grid, f-number and ``t_peak``.

    The limits end on the MATLAB grid's last sample, not its nominal end, so
    zea's linspace lands on exactly MATLAB's coordinates -- see the note above.
    """
    parameters.set_transmits("all")
    parameters.xlims = (START_X, LAST_X)
    parameters.zlims = (START_Z, LAST_Z)
    parameters.grid_size_x = GRID_SIZE_X
    parameters.grid_size_z = GRID_SIZE_Z
    parameters.f_number = FNUMBER
    parameters.t_peak = np.full(parameters.n_tx, T_PEAK, dtype=np.float32)
    # The raw data is upsampled along depth before beamforming (upsample_axial).
    parameters.sampling_frequency = float(parameters.sampling_frequency) * AXIAL_UPSAMPLING
    parameters.n_ax = int(parameters.n_ax) * AXIAL_UPSAMPLING
    return parameters


def count_frames(zea_path):
    """Number of frames in the raw-data track of ``zea_path``."""
    with zea.File(str(zea_path)) as f:
        return _raw_source(f).data.raw_data.shape[0]


def log_settings(n_total, n_used):
    """Log a short summary of the input and how much of it is used."""
    zea.log.info("ulmshare reconstruction settings:")
    zea.log.info(f"  input:        {ZEA_FILE}")
    zea.log.info(f"  output dir:   {zea.log.yellow(OUT_DIR)}")
    zea.log.info(f"  B-mode frame: {FRAME}")
    pct = 100 * n_used / n_total
    zea.log.info(f"  PD/ULM:       {n_used}/{n_total} frames ({pct:.1f}% of the acquisition)")
    if checkpoints_enabled():
        # Beamformed IQ: float32 I and Q per grid pixel, per frame.
        size_gb = n_used * GRID_SIZE_Z * GRID_SIZE_X * 2 * 4 / 1e9
        zea.log.info(f"  checkpoints:  {zea.log.yellow(CHECKPOINT_DIR)} (up to ~{size_gb:.1f} GB)")
    else:
        zea.log.info("  checkpoints:  off")
    if n_used < n_total:
        zea.log.warning(
            "Using only part of the acquisition: the ULM map will be much sparser than in "
            "the ULMShare paper. Set N_FRAMES = None (on a local copy) to use all frames."
        )


def reconstruct(zea_path, pipeline, frame_index=0):
    """Reconstruct one B-mode frame (2D dB image), normalised to 0 dB max."""
    with zea.File(str(zea_path)) as f:
        source = _raw_source(f)
        parameters = source.load_parameters()
        raw = upsample_axial(source.data.raw_data[frame_index : frame_index + 1])

    inputs = pipeline.prepare_parameters(_apply_ulmshare_grid(parameters))
    outputs = pipeline(**{pipeline.key: raw}, **inputs, return_numpy=True)
    bmode = np.asarray(outputs[pipeline.output_key])[0]
    return bmode - bmode.max()


@contextmanager
def open_raw_data(zea_path, dataset_name, n_bytes, max_block=STREAM_BLOCK_BYTES):
    """Open the ``raw_data`` h5py dataset of ``zea_path`` for a read of ~``n_bytes``.

    A local file is opened directly. An ``hf://`` file is opened through an LRU
    block cache, so consecutive frame chunks arrive in a few large requests rather
    than one request each. Blocks are ~1/16 of ``n_bytes``: HDF5's own metadata
    reads (superblock, chunk index) each cost one block too, and small blocks keep
    that overhead small, so a short run fetches little more than the frames it uses.
    """
    zea_path = str(zea_path)
    if not zea_path.startswith("hf://"):
        with h5py.File(zea_path, "r") as f:
            yield f[dataset_name]
        return

    block = int(np.clip(n_bytes // 16, 2**18, max_block))
    fobj = HfFileSystem().open(
        "datasets/" + zea_path.removeprefix("hf://"),
        "rb",
        block_size=block,
        cache_type="blockcache",
        cache_options={"maxblocks": 8},
    )
    with fobj, h5py.File(fobj, "r") as f:
        yield f[dataset_name]


def upsample_axial(raw, factor=AXIAL_UPSAMPLING):
    """Band-limited upsampling of IQ channel data along depth (axis 2), by ``factor``.

    Zero-pads the spectrum of the complex ``I + jQ`` signal, so the original
    samples are kept and the new ones lie on the band-limited interpolant.
    ``raw`` is ``(n_frames, n_tx, n_ax, n_el, 2)``; returns float32
    ``(n_frames, n_tx, n_ax * factor, n_el, 2)``.
    """
    if factor == 1:
        return raw
    iq = raw[..., 0].astype(np.complex64) + 1j * raw[..., 1].astype(np.float32)
    n = iq.shape[2]
    spec = np.fft.fft(iq, axis=2)
    padded = np.zeros(iq.shape[:2] + (n * factor,) + iq.shape[3:], dtype=np.complex64)
    half = (n + 1) // 2  # positive frequencies (incl. DC); the rest are negative
    padded[:, :, :half] = spec[:, :, :half]
    padded[:, :, n * factor - (n - half) :] = spec[:, :, half:]
    if n % 2 == 0:  # split the Nyquist bin between +f and -f to keep the signal real-consistent
        padded[:, :, half] = padded[:, :, n * factor - half] = 0.5 * spec[:, :, half]
    up = np.fft.ifft(padded, axis=2) * factor
    return np.stack([up.real, up.imag], axis=-1).astype(np.float32)


def beamform(raw, pipeline, inputs, batch_size=BATCH_SIZE):
    """Beamform raw frames ``(n, ...)`` into an IQ stack ``(n, Nz, Nx, 2)``.

    Each batch is upsampled along depth first (:func:`upsample_axial`), keeping
    the upsampled data to one batch at a time.
    """
    frames = []
    for start in range(0, raw.shape[0], batch_size):
        batch = upsample_axial(raw[start : start + batch_size])
        out = pipeline(**{pipeline.key: batch}, **inputs, return_numpy=True)
        frames.append(np.asarray(out[pipeline.output_key]))
    return np.concatenate(frames, axis=0)


def clutter_filter(iq_bf, op):
    """SVD clutter-filter one beamformed buffer into a complex movie ``(n, Nz, Nx)``.

    Filtering per buffer is what the reference MATLAB does, and a whole-
    acquisition Casorati SVD would not fit in GPU memory. The rejected-component
    count is resolved per buffer (:func:`matlab_clutter_cutoff`), so a short
    trailing buffer gets its own correct cut. The op reads axis 0 as the frame
    axis and takes zea's ``[I, Q]`` channel convention directly.
    """
    op.cutoff = matlab_clutter_cutoff(iq_bf.shape[0])
    filtered = op(data=keras.ops.convert_to_tensor(iq_bf))["data"]
    return keras.ops.convert_to_numpy(keras.ops.view_as_complex(filtered))


def power_doppler_stats(iq_cf, n_movie):
    """What the Power-Doppler outputs need from one filtered buffer.

    ``sum``: frame-summed ``|IQ|``, which adds up across buffers into the
    Power-Doppler image; ``peak``: the buffer's max ``|IQ|``, for the movie's
    whole-stack dB offset; ``movie``: ``|IQ|`` of its first ``n_movie`` frames.
    """
    mag = np.abs(iq_cf)
    return {
        "sum": mag.sum(axis=0, dtype=np.float64),
        "peak": float(mag.max()),
        "movie": mag[:n_movie],
    }


# --- Checkpoints ----------------------------------------------------------------
# Every buffer's stage outputs are saved under zea's cache directory (see
# CHECKPOINT_DIR), so a crashed or re-tuned run resumes where it can: changing a
# ULM parameter reuses the beamformed and filtered stages, and a buffer whose
# outputs are all saved is not streamed again. Each key holds the input file, the
# buffer, every setting of its stage and the ones before it, and the source code
# of the functions that compute it, so any change recomputes what it affects.


def stage_keys(zea_file, start, stop, pipeline_yaml):
    """Checkpoint keys of one buffer's stages, each extending the previous one."""
    src = get_function_source
    bf = [zea_file, start, stop, pipeline_yaml, START_X, LAST_X, START_Z, LAST_Z]
    bf += [GRID_SIZE_X, GRID_SIZE_Z, FNUMBER, T_PEAK, AXIAL_UPSAMPLING]
    bf += [src(beamform), src(_apply_ulmshare_grid), keras.backend.backend()]
    cf = bf + [CLUTTER_FILTER_CUT, src(clutter_filter), src(matlab_clutter_cutoff)]
    n_movie = max(0, min(stop, MOVIE_MAX_FRAMES) - start)
    pd = cf + [n_movie, src(power_doppler_stats)]
    loc = cf + [ULM_MIN_TISSUE_CORR, src(ulm.tissue_stability), ULM_THRESHOLD, ULM_MIN_DISTANCE]
    loc += [src(ulm.localize)]
    trk = loc + [ULM_MAX_LINKING_DISTANCE, ULM_MAX_GAP, ULM_MIN_TRACK_LENGTH, src(ulm.track)]
    keys = {"beamformed": bf, "power_doppler": pd, "localizations": loc, "tracks": trk}
    return {stage: CHECKPOINT_DIR / f"{stage}_{hash_elements(k)}.pkl" for stage, k in keys.items()}


def checkpoints_enabled():
    return CHECKPOINT and not is_cache_disabled()


def load_checkpoint(path):
    """The saved stage output at ``path``, or ``None`` if there is none."""
    if not checkpoints_enabled() or not path.exists():
        return None
    return joblib.load(path)


def save_checkpoint(path, value):
    """Save a stage output atomically, so a crash never leaves a truncated file."""
    if not checkpoints_enabled():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_write(path) as tmp:
        joblib.dump(value, tmp)


def has_checkpoint(path):
    return checkpoints_enabled() and path.exists()


def process_buffer(paths, raw, head, inputs, op, n_movie, status):
    """Run one buffer through beamform -> filter -> localize -> track.

    Loads each stage from its checkpoint where one exists and computes (and
    saves) it otherwise. ``raw`` is only needed when the beamformed stage is not
    saved. Returns ``(power_doppler_stats, tracks)``, where ``tracks`` holds the
    buffer's ``tracks``, its ``n_localizations`` and whether its tissue ``moved``.
    """
    pd = load_checkpoint(paths["power_doppler"])
    tracks = load_checkpoint(paths["tracks"])
    loc = None if tracks is not None else load_checkpoint(paths["localizations"])
    if pd is None or (tracks is None and loc is None):
        iq_bf = load_checkpoint(paths["beamformed"])
        if iq_bf is None:
            status("beamform")
            iq_bf = beamform(raw, head, inputs)
            save_checkpoint(paths["beamformed"], iq_bf)
        need_loc = tracks is None and loc is None
        still = need_loc and ulm.tissue_stability(iq_bf) >= ULM_MIN_TISSUE_CORR
        status("filter")
        iq_cf = clutter_filter(iq_bf, op)
        del iq_bf
        if pd is None:
            pd = power_doppler_stats(iq_cf, n_movie)
            save_checkpoint(paths["power_doppler"], pd)
        if need_loc:
            status("localize")
            # A buffer whose tissue moved gets no localizations (see ulm.tissue_stability).
            if still:
                locs = ulm.localize(iq_cf, threshold=ULM_THRESHOLD, min_distance=ULM_MIN_DISTANCE)
            else:
                locs = [np.zeros((0, 2))] * len(iq_cf)
            loc = {"locs": locs, "moved": not still}
            save_checkpoint(paths["localizations"], loc)
    if tracks is None:
        status("track")
        tracks = {
            "tracks": ulm.track(
                loc["locs"],
                max_linking_distance=ULM_MAX_LINKING_DISTANCE,
                max_gap=ULM_MAX_GAP,
                min_length=ULM_MIN_TRACK_LENGTH,
            ),
            "n_localizations": sum(len(p) for p in loc["locs"]),
            "moved": loc["moved"],
        }
        save_checkpoint(paths["tracks"], tracks)
    return pd, tracks


def process_acquisition(zea_path, ts_pipeline, pipeline_yaml, n_frames):
    """Stream and process ``n_frames`` frames one acquisition buffer at a time.

    Only one buffer (plus the next one being read) is held in memory, so memory
    stays flat however many frames are used. The next buffer's raw data is read
    on a background thread while the current one is processed, and buffers whose
    stages are all checkpointed are not read at all.

    Returns ``(pd_sum, peak, movie_mag, tracks, n_localizations, n_moved)``,
    accumulated over all buffers (``n_moved``: buffers ULM skipped for motion).
    """
    # TissueSuppression works across frames, so the pipeline is split: its
    # Cast -> Beamform head runs per batch of frames, the op itself per buffer.
    head, op = split_pipeline(ts_pipeline, TissueSuppression)
    with zea.File(str(zea_path)) as f:
        source = _raw_source(f)
        inputs = head.prepare_parameters(_apply_ulmshare_grid(source.load_parameters()))
        dataset_name = source.data.raw_data.name
        chunks, itemsize = source.data.raw_data.chunks, source.data.raw_data.dtype.itemsize
    # An uncompressed frame chunk: an upper bound on what one stored frame takes.
    frame_bytes = int(np.prod(chunks)) * itemsize

    buffers = [
        (start, min(start + FRAMES_PER_BUFFER, n_frames))
        for start in range(0, n_frames, FRAMES_PER_BUFFER)
    ]
    paths = [stage_keys(str(zea_path), start, stop, pipeline_yaml) for start, stop in buffers]

    def needs_raw(p):
        done = has_checkpoint(p["power_doppler"]) and (
            has_checkpoint(p["tracks"]) or has_checkpoint(p["localizations"])
        )
        return not done and not has_checkpoint(p["beamformed"])

    to_read = [i for i, p in enumerate(paths) if needs_raw(p)]
    n_cached = len(buffers) - len(to_read)
    if n_cached:
        zea.log.info(f"  {n_cached}/{len(buffers)} buffers resume from checkpoints")

    pd_sum, peak, movie, tracks, n_loc, n_moved = 0.0, 0.0, [], [], 0, 0
    verb = "streaming" if str(zea_path).startswith("hf://") else "reading"
    with ExitStack() as stack:
        pool = stack.enter_context(ThreadPoolExecutor(max_workers=1))
        pending = {}
        if to_read:
            block_bytes = FRAMES_PER_BUFFER * frame_bytes
            raw_data = stack.enter_context(open_raw_data(zea_path, dataset_name, block_bytes))

            def prefetch(i):
                if i < len(to_read):
                    start, stop = buffers[to_read[i]]
                    pending[to_read[i]] = pool.submit(lambda: raw_data[start:stop])

            prefetch(0)
        progbar = stack.enter_context(
            tqdm(total=n_frames, desc=f"{verb} + processing", unit="frame")
        )
        for i, (start, stop) in enumerate(buffers):
            raw = None
            if i in pending:
                progbar.set_postfix_str(verb)
                raw = pending.pop(i).result()
                prefetch(to_read.index(i) + 1)  # read the next buffer meanwhile
            n_movie = max(0, min(stop, MOVIE_MAX_FRAMES) - start)
            pd, buf = process_buffer(
                paths[i], raw, head, inputs, op, n_movie, progbar.set_postfix_str
            )
            pd_sum = pd_sum + pd["sum"]
            peak = max(peak, pd["peak"])
            if n_movie:
                movie.append(pd["movie"])
            tracks.extend(t + np.float32([start, 0, 0]) for t in buf["tracks"])  # global frames
            n_loc += buf["n_localizations"]
            n_moved += buf["moved"]
            progbar.update(stop - start)

    movie = np.concatenate(movie, axis=0) if movie else None
    return pd_sum, peak, movie, tracks, n_loc, n_moved


def save_image(image, out_path, title, label, cmap, vmin=None, vmax=None, ticks=None):
    """Render one 2D map on the reconstruction grid to a PNG."""
    zea.visualize.set_mpl_style()
    fig, ax = plt.subplots(figsize=(4, 6))
    im = ax.imshow(image, cmap=cmap, vmin=vmin, vmax=vmax, extent=EXTENT_MM, aspect="equal")
    ax.set_title(title)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("z (mm)")
    # Colorbar exactly as tall as the image.
    cax = make_axes_locatable(ax).append_axes("right", size="5%", pad=0.1)
    fig.colorbar(im, cax=cax, label=label, ticks=ticks)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    zea.log.success(f"Saved {title} to {zea.log.yellow(out_path)}")


def save_movie_gif(movie, out_path, vmin, vmax, cmap="viridis", fps=MOVIE_FPS):
    """Render a ``(n_frames, Nz, Nx)`` dB movie to an animated GIF."""
    fig, ax = plt.subplots(figsize=(4, 6))
    im = ax.imshow(movie[0], cmap=cmap, vmin=vmin, vmax=vmax, extent=EXTENT_MM, aspect="equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("z (mm)")
    cax = make_axes_locatable(ax).append_axes("right", size="5%", pad=0.1)
    fig.colorbar(im, cax=cax, label="dB", ticks=[vmin, vmax])

    frames = []
    for k in tqdm(range(movie.shape[0]), desc="rendering movie frames"):
        im.set_data(movie[k])
        ax.set_title(f"Power Doppler (dB) — frame {k}")
        frames.append(matplotlib_figure_to_numpy(fig))
    plt.close(fig)

    save_to_gif(np.stack(frames), out_path, fps=fps)  # logs the saved path itself


def render_ulm(density, out_path, super_res=ULM_SUPER_RES):
    """Render a ULM density map to a PNG.

    A light blur makes the sparse splatted counts read as vessels and a gamma < 1
    keeps faint vessels visible; ``vmax`` comes from non-empty cells so the
    mostly-zero background does not collapse the scale. Sigma is specified in BF
    pixels so the look is stable as ``super_res`` changes.
    """
    disp = gaussian_filter(density, sigma=0.1 * super_res) ** 0.5
    nonzero = disp[disp > 0]
    save_image(
        disp,
        out_path,
        title="ULM density map",
        label="sqrt(count)",
        cmap="hot",
        vmin=0,
        vmax=np.percentile(nonzero, 99) if nonzero.size else 1.0,
    )


def main():
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    zea.init_device(verbose=False)

    n_total = count_frames(ZEA_FILE)
    n_used = n_total if N_FRAMES is None else min(N_FRAMES, n_total)
    log_settings(n_total, n_used)
    bmode_yaml = out_dir / "pipeline_bmode.yaml"
    ts_yaml = out_dir / "pipeline_tissue_suppression.yaml"

    # Persist both pipelines, then run the ones loaded back from disk: the
    # reconstruction is then demonstrably the one the YAMLs describe.
    build_pipeline().to_yaml(str(bmode_yaml))
    build_tissue_suppression_pipeline().to_yaml(str(ts_yaml))
    pipeline = load_pipeline(bmode_yaml)
    ts_pipeline = load_pipeline(ts_yaml)
    zea.log.success(
        f"Saved pipelines to {zea.log.yellow(bmode_yaml)} and {zea.log.yellow(ts_yaml)}"
    )

    # ---- B-mode ------------------------------------------------------------ #
    zea.log.info(f"Reconstructing B-mode frame {FRAME} ...")
    bmode = reconstruct(ZEA_FILE, pipeline, frame_index=FRAME)
    zea.log.info(f"  B-mode {bmode.shape} dB range [{bmode.min():.1f}, {bmode.max():.1f}]")
    save_image(
        bmode,
        out_dir / "bmode.png",
        title=f"B-mode (dB) — frame {FRAME}",
        label="dB",
        cmap="gray",
        vmin=-DYNAMIC_RANGE_DB,
        vmax=0,
        ticks=[-DYNAMIC_RANGE_DB, 0],
    )

    # ---- Power-Doppler + ULM, one buffer at a time ------------------------- #
    source = "streaming from the Hub" if ZEA_FILE.startswith("hf://") else "reading from disk"
    zea.log.info(
        f"Processing {n_used} frames ({source}), per {FRAMES_PER_BUFFER}-frame buffer: "
        "beamform -> SVD filter -> localize -> track ..."
    )
    cut = matlab_clutter_cutoff(FRAMES_PER_BUFFER)
    zea.log.info(f"  SVD clutter filter rejects {cut} of {FRAMES_PER_BUFFER} components per buffer")
    pd_sum, peak, movie_mag, tracks, n_loc, n_moved = process_acquisition(
        ZEA_FILE, ts_pipeline, ts_yaml.read_text(), n_used
    )

    pd = 20 * np.log10(pd_sum + 1e-12)
    save_image(
        pd - pd.max(),
        out_dir / "power_doppler.png",
        title="Power Doppler (dB)",
        label="dB",
        cmap="viridis",
        vmin=-PD_RANGE_DB,
        vmax=0,
        ticks=[-PD_RANGE_DB, 0],
    )
    if n_used > MOVIE_MAX_FRAMES:
        zea.log.warning(
            f"Power-Doppler movie limited to the first {MOVIE_MAX_FRAMES}/{n_used} frames "
            "(MOVIE_MAX_FRAMES)."
        )
    zea.log.info(
        f"Rendering Power-Doppler movie ({movie_mag.shape[0]} frames); this takes a few minutes ..."
    )
    # As powerDopplerMovie in the MATLAB: offset by the max over the *whole* stack,
    # not per frame, so brightness stays comparable across frames.
    movie = 20 * np.log10(movie_mag + 1e-12) - 20 * np.log10(peak + 1e-12)
    save_movie_gif(movie, out_dir / "power_doppler_movie.gif", vmin=-PD_RANGE_DB, vmax=0)

    # ---- ULM density map ---------------------------------------------------- #
    n_points = sum(len(t) for t in tracks)
    zea.log.info(
        f"ULM: {n_moved}/{len(range(0, n_used, FRAMES_PER_BUFFER))} buffers skipped for tissue "
        f"motion; {n_loc} localizations -> {len(tracks)} tracks "
        f"(>= {ULM_MIN_TRACK_LENGTH} frames, {n_points} points); building the density map ..."
    )
    density = ulm.density_map(
        tracks, (GRID_SIZE_Z, GRID_SIZE_X), super_res=ULM_SUPER_RES, smooth=ULM_SMOOTH
    )
    render_ulm(density, out_dir / "ulm_density.png")


if __name__ == "__main__":
    main()
