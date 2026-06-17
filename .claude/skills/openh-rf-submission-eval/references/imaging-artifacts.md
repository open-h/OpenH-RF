# Ultrasound image artifact taxonomy

A reference for dimension 2 (reconstruction). The central question this file answers:

> *Is this artifact in the image because of the physics of the acquisition (which is fine — it's the real data), or because the pipeline did something wrong (which is what we're here to catch)?*

You can let acquisition-induced artifacts through. You cannot let pipeline-induced ones through.

---

## Part 1: Acquisition-induced artifacts (these are FINE)

These come from the physics of how ultrasound waves interact with tissue. They're features of the real data and a downstream user needs them preserved. **Note them as `info` if interesting, never as findings against the submission.**

### Acoustic shadowing
A dark anechoic band *behind* a highly attenuating or reflective structure (bone, calcification, gas, stone). Looks like a vertical dark stripe extending down from the bright structure.
- *How to tell it's real*: there's a clear bright reflector at the top of the shadow.
- *Diagnostic value*: actually useful — shadows behind kidney stones, gallstones, calcifications.

### Acoustic enhancement
The opposite: a bright region *behind* a structure that attenuates less than surrounding tissue (e.g., a fluid-filled cyst).
- *How to tell it's real*: there's a clear hypoechoic structure (fluid pocket) above the bright region.

### Reverberation (real)
Multiple parallel echoes from sound bouncing between two strong reflectors. Common at strong tissue/air or tissue/metal interfaces (lung pleura, mechanical valves, catheter wires).
- *How to tell it's real*: the reverb spacing matches a physically plausible reflector-to-reflector distance, and the artifact *fades with depth* (each bounce loses energy).

### Comet tail / ring-down
A reverberation variant — a short, intense, parallel-line trailing pattern from a small strong reflector (gas bubbles, metal fragments).
- *How to tell it's real*: associated with a known strong reflector.

### Mirror image
A duplicated image of a real structure on the other side of a highly reflective interface (commonly diaphragm in liver imaging).
- *How to tell it's real*: located symmetrically across an obvious reflective surface.

### Edge / refraction artifacts
Bright lines or shadowing at sharp tissue boundaries due to refraction of the beam.
- *How to tell it's real*: localized to anatomical edges.

### Attenuation
General loss of signal with depth. Image gets darker the deeper you go.
- *How to tell it's real*: it's monotonic and roughly exponential.

---

## Part 2: Pipeline-induced artifacts (these are BUGS)

These come from errors in how the reconstruction was performed. They should not be in a correctly-built B-mode image and indicate a fix is needed.

### Sign-flipped / inverted intensities
The image looks like a photographic negative. Bright tissue is dark, anechoic regions are bright.
- *Cause*: log compression applied without taking the magnitude first, or a sign error in the envelope.
- *Severity*: `blocker`. The image is wrong.

### Wraparound / aliasing in azimuth
Structures appear to "wrap" from one side of the image to the other.
- *Cause*: angular aliasing in plane-wave compounding, or insufficient lateral spacing relative to wavelength.
- *Severity*: `major` if dominant, `minor` if subtle.

### Spectral / decimation aliasing
Repeating banded pattern in the axial direction, often regular.
- *Cause*: undersampled axial data, or IQ-demodulated data treated as RF (or vice versa).
- *Severity*: `major`. Reconstruction parameters disagree with the data.

### Dominant ringing
The image has obvious oscillating bright/dark bands not associated with any anatomy.
- *Cause*: usually a missing or wrong apodization, or a Gibbs-like effect from a hard truncation.
- *Severity*: `major` if it dominates the image. `minor` if mild and at edges.

### Geometric distortion inconsistent with scan geometry
The image's spatial aspect ratio or curvature doesn't match what the probe + scan geometry imply (e.g., a linear-probe image showing curvilinear sector geometry).
- *Cause*: wrong scan-geometry parameters used in beamforming.
- *Severity*: `blocker`. The reconstruction is geometrically wrong; downstream users will derive wrong measurements.

### Severe banding from beamforming bugs
Discrete vertical or radial bands corresponding to individual transmit events that didn't blend properly.
- *Cause*: missing or wrong per-transmit weighting in coherent compounding.
- *Severity*: `major`.

### NaN holes mid-image
Patches of NaN or zero in the interior of the image (not at the edges where it's normal).
- *Cause*: division by zero in normalization, log of zero, or a beamforming bug at certain depths.
- *Severity*: `blocker`.

### All-noise output
The image has no spatial structure — just speckle-like noise everywhere.
- *Cause*: beamforming delays are wrong (wrong sound speed, wrong element positions), so coherent summing doesn't actually align echoes.
- *Severity*: `blocker`.

### Low effective resolution
Image is much blurrier than the probe's nominal resolution would predict.
- *Cause*: typically a too-small effective aperture, missing apodization, or wrong sound speed.
- *Severity*: `major` if dramatic, `minor` if subtle.

### Demodulation phase error
For IQ data: lateral position errors that look like the image is slightly sheared.
- *Cause*: wrong demodulation frequency, or RF/IQ misidentification.
- *Severity*: `major`.

---

## Part 3: The judgment call

The tricky cases:

- **Reverberation behind a strong reflector**: real (Part 1) or beamforming aliasing (Part 2)? Look at *spacing* — physical reverb has spacing equal to reflector-pair distance. Aliasing reverb has spacing that's a divisor of the array geometry.
- **Banding**: anatomical (real fascial layers) or beamforming (per-transmit banding)? Banding aligned with the transmit pattern is the pipeline. Banding aligned with depth is anatomy.
- **Resolution loss**: real low-frequency probe vs aperture/sound-speed bug? Compare to the probe's nameplate center frequency. If a 10 MHz probe is producing 3 MHz resolution, that's a bug.

When you can't tell, **say so explicitly** in the finding and downgrade to `minor` with a question for the contributor — not `major` based on a guess.

## Sources

The taxonomy in Part 1 is grounded in standard radiology references on B-mode artifacts (acoustic shadowing/enhancement, reverberation, mirror image, comet tail/ring-down, refraction edge artifacts). The pipeline-induced taxonomy in Part 2 reflects common failure modes in signal-processing-based reconstruction; it's drawn from typical bugs in academic and open-source beamforming pipelines.
