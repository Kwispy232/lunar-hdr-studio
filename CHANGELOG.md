# Changes

## 0.3.0

- Fixed PNG export when the desktop launcher starts the app in `/`: the save dialog now defaults to an absolute writable Pictures folder, with a home-folder fallback.
- Remember the destination after a successful export; accept empty/variant dialog filters and report destination-specific write errors without discarding the composite.
- Added mouse-selected crop, reset crop, and optional editable text signature.
- Added original background, star suppression, and explicitly synthetic star overlay modes.
- Apply the same finishing options to preview and PNG/JPEG/16-bit TIFF. Linear HDR keeps the uncropped radiance data.
- Replaced the private reference photograph with original, visibly labeled procedural demo artwork for public distribution.
- Added cross-platform tests/builds for macOS Apple Silicon, macOS Intel, Windows x64 and Linux x64.

## 0.2.0

- FITS image import, including native linear samples, exposure metadata and compressed image HDUs.
- Two or more exposures, selectable reference, manual alignment and exposure values.
- RGB FITS with retained Bayer sensor metadata, halo-aware disk fallback and clipping protection.
- Lunar color neutralization for Mineral Moon processing.
