# SPDX-License-Identifier: Apache-2.0
"""A minimal ULM chain on clutter-filtered IQ buffers (pure NumPy/SciPy).

Per buffer of the clutter-filtered movie from ``reconstruct.py``: localize
bubbles in every frame, link them into tracks, and draw the tracks into a
density map.

1. **Motion** (:func:`tissue_stability`). Buffers where the tissue moves
   (breathing, heartbeat, the probe) leave clutter that the SVD filter does not
   remove and that tracks into false vessels, so ``reconstruct.py`` skips them
   for ULM; the Power Doppler still uses them.
2. **Localize** (:func:`localize`). The noise floor of the filtered movie changes
   with depth (TGC, attenuation, the skull), so each depth row is divided by its
   median ``|IQ|`` over the buffer, and local maxima above a threshold are
   bubbles, refined to sub-pixel by a 3-point Gaussian fit per axis. (A
   per-pixel median would be finer still, but where bubbles pass often it rises
   with them and erases the vessels themselves.)
3. **Track** (:func:`track`). The simple tracker of deep-ulm-pipeline
   (``tracking/simple/tracker.py``): frame by frame, a Hungarian assignment of
   detections to the last position of each open track, gated at
   ``max_linking_distance``; tracks missing more than ``max_gap`` frames close,
   unmatched detections open new tracks, and only tracks of ``>= min_length``
   detections are kept. Flickering interference seldom survives that; a bubble
   moving along a vessel does.
4. **Render** (:func:`density_map`). Each track is smoothed with a moving
   average, resampled densely along its path, and adds 1 to every super-resolved
   pixel it crosses -- once per track, so a slow bubble does not paint a blob
   (as deep-ulm-pipeline's ``tracks_to_map``).

Everything works in **beamforming-grid pixel coordinates** ``(z, x)`` and frames;
distances and thresholds are therefore in pixels.
"""

import numpy as np
from scipy.ndimage import maximum_filter, uniform_filter1d
from scipy.optimize import linear_sum_assignment


def tissue_stability(iq_bf, block=20):
    """How still the tissue is over one beamformed (unfiltered) buffer.

    ``iq_bf`` is ``(n_frames, Nz, Nx, 2)`` in zea's ``[I, Q]`` convention. Returns
    the lowest correlation between the envelope of the buffer's first ``block``
    frames and that of any later ``block`` frames: ~1 for a still buffer. A buffer
    too short to compare two blocks counts as still.
    """
    env = np.hypot(iq_bf[..., 0], iq_bf[..., 1])
    ref = env[:block].mean(axis=0).ravel()
    return min(
        (
            np.corrcoef(ref, env[k : k + block].mean(axis=0).ravel())[0, 1]
            for k in range(block, len(env) - block + 1, block)
        ),
        default=1.0,
    )


def localize(iq_cf, threshold, min_distance):
    """Bubble positions in every frame of one filtered buffer ``(n, Nz, Nx)``.

    A bubble is a local maximum in a ``(2 * min_distance + 1)`` square window whose
    ``|IQ|`` exceeds ``threshold`` times the median ``|IQ|`` of its depth row.
    Returns a list with, per frame, a ``(k, 2)`` array of sub-pixel ``(z, x)``.
    """
    mag = np.abs(iq_cf).astype(np.float32)
    noise = np.median(mag, axis=(0, 2), keepdims=True)  # per depth row
    snr = mag / np.maximum(noise, 1e-3 * np.median(noise))
    width = 2 * min_distance + 1
    peak = (snr == maximum_filter(snr, size=(1, width, width))) & (snr > threshold)
    peak[:, [0, -1], :] = peak[:, :, [0, -1]] = False  # the fit needs both neighbours
    f, z, x = np.nonzero(peak)

    log = np.log(np.maximum(snr, 1e-6))  # some pixels are exactly 0

    def offset(before, at, after):  # vertex of the parabola through 3 log samples
        curv = before - 2 * at + after
        return np.clip(0.5 * (before - after) / np.where(curv < 0, curv, -np.inf), -0.5, 0.5)

    dz = offset(log[f, z - 1, x], log[f, z, x], log[f, z + 1, x])
    dx = offset(log[f, z, x - 1], log[f, z, x], log[f, z, x + 1])
    points = np.stack([z + dz, x + dx], axis=1)
    return np.split(points, np.searchsorted(f, np.arange(1, len(mag))))


def track(locs, max_linking_distance, max_gap, min_length):
    """Link per-frame detections into tracks.

    ``locs`` is :func:`localize`'s output. Returns a list of ``(len, 3)`` arrays of
    ``(frame, z, x)``, with ``frame`` counted from the start of ``locs``.
    """
    open_tracks, closed = [], []  # each track: [list of (frame, z, x), frames missed]
    for frame, points in enumerate(locs):
        matched = np.zeros(len(points), bool)
        for t in open_tracks:
            t[1] += 1
        if open_tracks and len(points):
            last = np.array([t[0][-1][1:] for t in open_tracks])
            cost = np.linalg.norm(last[:, None] - points[None], axis=-1)
            # Gate before the assignment, so a far detection can't steal a track
            # from a near one.
            cost[cost > max_linking_distance] = 1e9  # out of reach: never linked
            rows, cols = linear_sum_assignment(cost)
            for r, c in zip(rows, cols):
                if cost[r, c] < 1e9:
                    open_tracks[r][0].append((frame, *points[c]))
                    open_tracks[r][1] = 0
                    matched[c] = True
        closed += [t for t in open_tracks if t[1] > max_gap]
        open_tracks = [t for t in open_tracks if t[1] <= max_gap]
        open_tracks += [[[(frame, *p)], 0] for p in points[~matched]]
    closed += open_tracks
    return [np.array(t[0], dtype=np.float32) for t in closed if len(t[0]) >= min_length]


def density_map(tracks, grid_shape, super_res, smooth):
    """Number of tracks crossing each pixel of a ``super_res``-times finer grid.

    ``grid_shape`` is the beamforming grid ``(Nz, Nx)``; each track is smoothed
    with a ``smooth``-frame moving average first.
    """
    shape = (grid_shape[0] * super_res, grid_shape[1] * super_res)
    density = np.zeros(shape[0] * shape[1])
    for t in tracks:
        zx = t[:, 1:].astype(np.float64)
        window = min(smooth, len(zx) - 1 + len(zx) % 2)  # odd, at most the track length
        zx = uniform_filter1d(zx, window, axis=0, mode="nearest")
        # Resample every half super-res pixel along the path, so no pixel is skipped.
        arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(zx, axis=0), axis=1))])
        s = np.arange(0, arc[-1] + 1e-9, 0.5 / super_res)
        pix = np.round(np.stack([np.interp(s, arc, zx[:, k]) for k in (0, 1)], 1) * super_res)
        pix = pix.astype(int)
        ok = (pix[:, 0] >= 0) & (pix[:, 0] < shape[0]) & (pix[:, 1] >= 0) & (pix[:, 1] < shape[1])
        density[np.unique(pix[ok, 0] * shape[1] + pix[ok, 1])] += 1
    return density.reshape(shape)
