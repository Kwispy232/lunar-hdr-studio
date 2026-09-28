# Changes

## 0.5.0

- Translated the complete application interface, tooltips, status messages and dialogs to English.
- Added a first-run introduction and a reusable offline guide, available from the top-right **?** button, F1 and the Help menu.
- Added searchable instructions for import and FITS/EV, alignment, HDR/fusion, every development slider, Mineral Moon, stars, crop, signatures, export and troubleshooting.
- Remember guide dismissal between launches without changing the editing session; help remains accessible during processing.
- Added seven behavioral help/onboarding tests and included the offline guide in packaged startup verification.

## 0.4.0

- Improved Mineral Moon color separation using measured surface color differences, with luminance and gamut protection. Exposure glow remains controlled by the source stack and exposure adjustments.
- Made English the primary README, retained a linked Slovak translation, and replaced the documentation's synthetic preview with a result from real lunar FITS captures.
- Added the MIT license for original project code and included it in standalone packages.
- Added portable clone-and-run setup for Python 3.11–3.14 on macOS, Windows and Linux. Launchers reuse matching dependencies, preserve command-line arguments and support `--check`.
- Added clean-checkout launcher tests and a packaged startup check on all four CI targets.

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
