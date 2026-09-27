# Validation for 0.4.0

This document distinguishes the verified 0.3.0 baseline from checks for the upcoming 0.4.0 release. Local testing was performed on September 27, 2026, using macOS 26.6.2 on Apple silicon, Python 3.11.15, Qt 6.11.2 and OpenCV 5.0.0.

## Current release status

- **Verified baseline:** all 92 tests, standalone builds and artifact uploads passed on macOS Apple silicon, macOS Intel, Windows x64 and Ubuntu 24.04 x64 in [GitHub Actions run 36306875039](https://github.com/Kwispy232/lunar-hdr-studio/actions/runs/36306875039), commit `fe90af8`.
- **0.4.0 launcher checks:** 11 tests passed locally on macOS. The suite contains 11 cases on Unix and 10 on Windows because Windows has one entry script rather than two. Execution of the Windows cases awaits the new CI run.
- **0.4.0 full suite:** all 113 tests passed locally on macOS, including 10 new selective Mineral Moon regressions and 11 launcher tests. Windows collects 112 tests because only one launcher applies.
- **Pending release checks:** packaged application startup checks and the new four-platform CI run. The baseline run above predates these changes.

## Image processing coverage

The verified baseline covers:

- Registration of textured lunar disks across exposure differences, translation, scale and rotation; arbitrary exposure counts; and a selectable reference frame.
- Low confidence and a manual-review warning for disks without usable surface detail. A clipped disk's bright limb is distinguished from a wider surrounding halo.
- Recovery of highlight differences missing from the normal exposure, and protection of usable surface contrast when exposure fusion includes a clipped input.
- Validity masks, image boundaries, preservation of native linear samples and bright fallback behavior when every exposure is clipped.
- Integer and floating-point FITS, `BSCALE/BZERO`, `BLANK`, nonfinite values, monochrome and RGB layouts, gzip files, image extensions and compressed image HDUs.
- Exposure metadata, counts versus per-second units, incompatible units and declared or integer-limit saturation. FITS brackets are tested against known relative radiance so that display normalization cannot silently change their exposure relationship.
- RGB FITS with stale Bayer metadata, which are accepted with a warning, and undeveloped 2D CFA or spectral/time cubes, which are rejected.
- Neutralization of an overall color cast, preservation of luminance, unchanged grayscale data, finite output and unchanged source arrays.
- 16-bit TIFF precision, compressed TIFF input, grayscale import, HDR values above 1 and invalid-input errors.

The additional 0.4.0 Mineral Moon checks target selective enhancement of existing surface colors, preservation of grayscale and luminance, and protection of the surrounding background. All 10 additional mineral-color regressions passed in the complete 113-test local run.

## Interface, finishing and export

The 0.3.0 baseline includes 21 interface/export regressions and 11 finishing tests. Coverage includes startup with an unrelated working directory, an absolute Pictures export destination, an empty file-dialog filter, PNG/TIFF/HDR export, permission errors and a successful retry after an export failure.

Raster exports include the selected crop, signature and star treatment. Linear HDR exports retain the full base radiance merge without creative adjustments. Tests also check matching preview/comparison dimensions after cropping and restoration of controls through Reset.

The following integration flow was exercised locally:

1. Import five FITS frames, append two, change the reference and remove a frame.
2. Populate EV from `EXPTIME`, edit EV manually and preserve those overrides during subsequent list changes.
3. Merge HDR, manually adjust the sixth frame and export 16-bit TIFF.
4. Reject an invalid import without losing the existing session, then remove every frame and verify that merge/export controls become unavailable.

Other exercised flows include the synthetic demo, Natural and Mineral Moon presets, before/after comparison, PNG and linear HDR export. Changing EV invalidates an outdated composite for export; replacing input frames invalidates their registration. The first import of real data replaces the demo session.

## Source startup and clean-checkout checks

The 0.4.0 launchers locate Python 3.11–3.14, create a repository-local `.venv` when needed and check installed versions against the pinned requirements. A matching environment is reused without calling pip or requiring network access. An incomplete or unsupported environment produces an actionable message and is not overwritten.

Local automated checks cover real first-run virtual-environment creation without downloading application dependencies, reuse of already installed packages, a checkout path containing spaces, startup from another working directory, argument forwarding, `--check`, dependency updates and readable installation failures. The Unix entry scripts retain executable permissions, and shell syntax checks passed.

A separate clean source snapshot, in a temporary path containing spaces, passed both `--check` and the real application's `--smoke-test` from another working directory. It reused the existing installed environment and performed no package installation. The smoke check exercised application startup and readiness of the procedural demo preview.

The local macOS Documents file provider sometimes marks Qt plugin files as hidden, which prevents Qt from discovering them. For this source smoke check only, the platform plugins were copied to a system temporary directory. This local environment workaround is not included in the application or launchers.

## Native macOS application checks

Earlier standalone Mac packages successfully imported five synthetic FITS, including a compressed image HDU, and created an HDR result through the interface. A later package also imported four real RGB FITS captures and exposed the reference selector, fusion mode, exposure-time warning and color-neutralization control. Fusion and export calculations were additionally checked through the same processing engine from source.

The final 0.3.0 standalone package was launched through macOS LaunchServices. After merging the synthetic demo, a crop and text signature were selected through the interface and exported as PNG. The save dialog opened in Pictures; the written file was reloaded and confirmed as valid RGB PNG, 890 × 868 pixels. Clicking Mineral Moon applied its slider settings.

The Mac package's signature was verified after extraction into a clean temporary directory. This is an ad-hoc signature, not Apple Developer notarization. New 0.4.0 package checks remain pending as listed above.

## Real-image checks and image provenance

Local processing was also exercised on four real DWARF RGB FITS captures containing stale `BAYERPAT` metadata. Two detailed frames registered using surface features with a median matching-point residual below one quarter of a pixel. A clipped exposure used disk-edge registration, low confidence and a manual-review warning.

The README now includes an app-processed photographic example from maintainer-supplied lunar FITS. Its provenance and permitted use are documented in [docs/IMAGES.md](docs/IMAGES.md). The raw FITS, their original filenames, private filesystem paths and the original reference photograph remain excluded from the public repository and distribution packages.

The application's bundled demo remains a separate, labeled procedural image. Automated image fixtures are also generated synthetically; they do not require private photographs.

## Platform verification limits

The previous four-platform CI run passed all 92 tests and produced the four release archives. Their ZIP integrity, expected application executables and bundled license entries were checked after download. Interface tests in CI use Qt's offscreen platform.

Interactive use has been tested on macOS. Windows and Linux builds and automated tests do not constitute interactive testing on physical Windows or Linux computers. The latest release checks and downloadable artifacts are available in [GitHub Actions](https://github.com/Kwispy232/lunar-hdr-studio/actions/workflows/build.yml).
