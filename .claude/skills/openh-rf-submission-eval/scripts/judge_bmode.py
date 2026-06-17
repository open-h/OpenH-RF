"""
Objective sanity checks on a reconstructed B-mode image.

Used by dimension 2 (reconstruction) as a cheap, deterministic gate *before*
the perceptual judgment. It does NOT assess image quality or similarity to a
reference — that is done by the dimension-2 evaluator viewing the rendered
image directly (multimodal vision). This script only answers: did the pipeline
plausibly produce a real image rather than noise, a constant, or NaNs?

(SSIM-vs-reference was removed: B-mode reconstructions and stored references
typically live on different physical grids / scales and are not pixel-registered,
which makes SSIM collapse toward zero even for visually-matching images. The
"does this match the reference" question is now answered perceptually by the
vision model — see references/dimensions/02-reconstruction.md.)
"""

from pathlib import Path

import numpy as np


def judge(image: np.ndarray) -> dict:
    """Run objective sanity checks on a B-mode image.

    Args:
        image: 2D float array, the reconstructed B-mode image

    Returns:
        dict with keys: passed (bool), checks (dict of check_name -> dict)
    """
    checks = {}

    # 1. Basic shape / dtype
    checks["is_2d"] = {
        "passed": image.ndim == 2,
        "detail": f"ndim={image.ndim}",
    }
    checks["is_finite"] = {
        "passed": bool(np.all(np.isfinite(image))),
        "detail": f"nan_count={int(np.isnan(image).sum())}, "
                  f"inf_count={int(np.isinf(image).sum())}",
    }

    # 2. Not degenerate
    checks["has_variance"] = {
        "passed": float(np.std(image)) > 1e-6,
        "detail": f"std={float(np.std(image)):.4g}",
    }
    checks["not_all_one_value"] = {
        "passed": len(np.unique(image)) > 10,
        "detail": f"unique_values={len(np.unique(image))}",
    }

    # 3. Dynamic range plausible for log-compressed B-mode
    rng = float(image.max() - image.min())
    checks["dynamic_range_plausible"] = {
        # Either normalized to [0, 1] with some spread, or dB-scale
        "passed": 0.05 < rng < 200,
        "detail": f"range={rng:.4g}, min={float(image.min()):.4g}, "
                  f"max={float(image.max()):.4g}",
    }

    # 4. Spatial structure — variance along each axis
    axial_std = float(np.std(image.mean(axis=1)))
    lateral_std = float(np.std(image.mean(axis=0)))
    checks["has_axial_structure"] = {
        "passed": axial_std > 1e-4,
        "detail": f"axial_profile_std={axial_std:.4g}",
    }
    checks["has_lateral_structure"] = {
        "passed": lateral_std > 1e-4,
        "detail": f"lateral_profile_std={lateral_std:.4g}",
    }

    passed = all(c["passed"] for c in checks.values())
    return {"passed": passed, "checks": checks}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("image_npy", type=Path,
                        help="Path to .npy file containing the reconstructed image")
    args = parser.parse_args()

    img = np.load(args.image_npy)
    result = judge(img)
    print(json.dumps(result, indent=2))
