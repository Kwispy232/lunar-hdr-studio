"""FITS data integrity, exposure calibration, and mask regression tests."""

import numpy as np
import pytest
from astropy.io import fits

from lunarhdr.engine import (
    AlignmentResult,
    ImageFrame,
    align_images,
    manual_alignment,
    merge_hdr,
    read_image,
    suggest_exposure_evs,
)
from tests.test_engine import lunar_scene, srgb


def save_fits(path, data, exposure=1.0, **header_values):
    hdu = fits.PrimaryHDU(data)
    if exposure is not None:
        hdu.header["EXPTIME"] = exposure
    for name, value in header_values.items():
        hdu.header[name] = value
    hdu.writeto(path)
    return path


def registered_native(frames, reference_index=0):
    """Already registered data isolates calibration from geometric resampling."""
    return AlignmentResult(
        images=[frame.pixels for frame in frames],
        masks=[frame.valid_mask for frame in frames],
        matrices=[np.eye(2, 3, dtype=np.float32) for _ in frames],
        reports=[{} for _ in frames],
        reference_index=reference_index,
        linear_images=[frame.linear_pixels for frame in frames],
        metadata=[{**frame.metadata, "exposure_seconds": frame.exposure_seconds, "warnings": frame.warnings} for frame in frames],
    )


def test_unsigned_sixteen_bit_fits_preserves_bzero_counts_and_exposure(tmp_path):
    counts = np.arange(17 * 23, dtype=np.uint16).reshape(17, 23) * 160
    counts[0, :3] = (0, 32768, 65535)
    path = save_fits(tmp_path / "unsigned.fit", counts, exposure=0.125, BUNIT="ADU")
    assert fits.getheader(path)["BZERO"] == 32768
    frame = read_image(path)
    assert frame.exposure_seconds == 0.125
    assert frame.metadata["source_format"] == "fits"
    assert frame.metadata["monochrome"] is True
    assert frame.metadata["bunit"] == "ADU"
    assert frame.bit_depth == 16
    for channel in range(3):
        np.testing.assert_array_equal(frame.linear_pixels[:, :, channel], counts)
    assert np.isfinite(frame.pixels).all()


def test_explicit_bscale_and_bzero_are_applied_once(tmp_path):
    stored = np.arange(17 * 23, dtype=np.int16).reshape(17, 23) - 20
    path = save_fits(tmp_path / "scaled.fits", stored, BSCALE=2.0, BZERO=32768.0)
    expected = stored.astype(np.float32) * 2 + 32768
    frame = read_image(path)
    for channel in range(3):
        np.testing.assert_array_equal(frame.linear_pixels[:, :, channel], expected)


def test_float_fits_preserves_native_values_and_masks_nonfinite_samples(tmp_path):
    counts = np.linspace(-0.4, 7800.0, 17 * 23, dtype=np.float32).reshape(17, 23)
    counts[0, 1], counts[1, 1], counts[2, 1] = np.nan, np.inf, -np.inf
    valid = np.isfinite(counts)
    frame = read_image(save_fits(tmp_path / "float.fts", counts))
    assert frame.bit_depth == 32
    np.testing.assert_array_equal(frame.valid_mask > 0, valid)
    np.testing.assert_array_equal(frame.linear_pixels[:, :, 0][valid], counts[valid])
    assert np.isfinite(frame.linear_pixels).all()
    assert np.isfinite(frame.pixels).all()
    assert frame.linear_pixels[0, 0, 0] == counts[0, 0]


def test_integer_blank_is_not_a_valid_sensor_measurement(tmp_path):
    counts = np.arange(17 * 23, dtype=np.int16).reshape(17, 23)
    counts[8, 9] = -32768
    frame = read_image(save_fits(tmp_path / "blank.fits", counts, BLANK=-32768))
    assert frame.valid_mask[8, 9] == 0
    assert np.count_nonzero(frame.valid_mask == 0) == 1
    assert np.isfinite(frame.linear_pixels).all()


def test_unsigned_bzero_blank_uses_stored_sentinel_without_masking_physical_zero(tmp_path):
    counts = np.arange(24, dtype=np.uint16).reshape(4, 6)
    counts[1, 1] = 32768
    path = save_fits(tmp_path / "unsigned-blank.fits", counts, BLANK=0)
    frame = read_image(path)
    assert frame.valid_mask[1, 1] == 0
    assert frame.valid_mask[0, 0] == 1
    assert np.count_nonzero(frame.valid_mask == 0) == 1


@pytest.mark.parametrize("suffix", [".fits", ".fits.gz"])
def test_float64_and_gzip_fits_preserve_native_dynamic_range(tmp_path, suffix):
    counts = np.linspace(.23, 650000.125, 16 * 23, dtype=np.float64).reshape(16, 23)
    path = save_fits(tmp_path / f"double{suffix}", counts, exposure=1.5)
    frame = read_image(path)
    assert frame.bit_depth == 64
    assert frame.exposure_seconds == 1.5
    np.testing.assert_allclose(frame.linear_pixels[:, :, 0], counts, rtol=1e-7)
    assert float(frame.linear_pixels.max()) > 600000


@pytest.mark.parametrize("storage", ["primary", "extension", "compressed"])
@pytest.mark.parametrize("layout", ["mono", "planar_rgb", "interleaved_rgb"])
def test_fits_hdu_and_channel_layouts_keep_native_channel_order(tmp_path, storage, layout):
    ramp = np.arange(16 * 23, dtype=np.uint16).reshape(16, 23)
    rgb = np.stack((ramp + 120, ramp + 700, ramp + 1500), axis=-1)
    if layout == "mono":
        data = ramp
        expected = np.repeat(data[:, :, None], 3, axis=2)
    elif layout == "planar_rgb":
        data = np.moveaxis(rgb, -1, 0)
        expected = rgb
    else:
        data = rgb
        expected = rgb
    path = tmp_path / f"{storage}-{layout}.fits"
    if storage == "primary":
        save_fits(path, data, exposure=3.25)
    else:
        primary = fits.PrimaryHDU()
        primary.header["EXPTIME"] = 3.25
        image = fits.CompImageHDU(data) if storage == "compressed" else fits.ImageHDU(data)
        fits.HDUList([primary, image]).writeto(path)
    frame = read_image(path)
    np.testing.assert_array_equal(frame.linear_pixels, expected)
    assert frame.exposure_seconds == 3.25
    assert frame.metadata["hdu_index"] == (0 if storage == "primary" else 1)


def test_image_hdu_exposure_overrides_primary_metadata(tmp_path):
    primary = fits.PrimaryHDU()
    primary.header["EXPTIME"] = 20.0
    image = fits.ImageHDU(np.ones((16, 23), dtype=np.float32))
    image.header["EXPTIME"] = 0.2
    path = tmp_path / "extension-exposure.fits"
    fits.HDUList([primary, image]).writeto(path)
    assert read_image(path).exposure_seconds == 0.2


@pytest.mark.parametrize("layout", ["planar_rgb", "interleaved_rgb"])
def test_rgb_fits_with_stale_bayer_header_keeps_channels_and_warns(tmp_path, layout):
    # Some capture/stacking programs retain BAYERPAT after producing three
    # color channels. The actual stored layout distinguishes this from 2D CFA.
    ramp = np.arange(16 * 23, dtype=np.uint16).reshape(16, 23)
    rgb = np.stack((ramp + 52000, ramp + 19000, ramp + 7000), axis=-1)
    stored = np.moveaxis(rgb, -1, 0) if layout == "planar_rgb" else rgb
    path = save_fits(tmp_path / f"stale-bayer-{layout}.fits", stored, exposure=.02, BAYERPAT="RGGB")
    frame = read_image(path)
    assert frame.metadata["monochrome"] is False
    assert frame.bit_depth == 16
    assert frame.exposure_seconds == .02
    np.testing.assert_array_equal(frame.linear_pixels, rgb)
    assert np.all(frame.valid_mask == 1)
    assert any("BAYERPAT" in warning and "RGGB" in warning for warning in frame.warnings)


@pytest.mark.parametrize(
    "shape,header",
    [
        ((4, 16, 23), {}),
        ((3, 16, 23), {"CTYPE3": "WAVE"}),
        ((16, 23), {"BAYERPAT": "RGGB"}),
        ((16, 23), {"BAYERPAT": "RGGB", "COLORTYP": "RGB"}),
        ((3, 16, 23), {"CTYPE3": "WAVE", "BAYERPAT": "RGGB"}),
        ((16, 23, 3), {"CTYPE1": "TIME", "BAYERPAT": "RGGB"}),
    ],
)
def test_unsupported_scientific_cubes_and_bayer_data_are_rejected(tmp_path, shape, header):
    path = save_fits(tmp_path / "unsupported.fits", np.ones(shape, np.uint16), **header)
    with pytest.raises(ValueError):
        read_image(path)


def test_five_fits_exposures_recover_native_counts_per_second(tmp_path):
    scene, disk = lunar_scene(size=160)
    rate = scene[:, :, 0] * 4000
    exposures = (0.25, 0.5, 1.0, 2.0, 4.0)
    frames = [
        read_image(save_fits(tmp_path / f"bracket-{index}.fits", rate * duration, exposure=duration, BUNIT="ADU"))
        for index, duration in enumerate(exposures)
    ]
    alignment = align_images(frames, reference_index=3)
    assert alignment.reference_index == 3
    assert len(alignment.linear_images) == 5
    result = merge_hdr(alignment, evs=None, mode="radiance")
    region = disk & (rate > np.percentile(rate[disk], 30))
    np.testing.assert_allclose(result.linear[:, :, 0][region], rate[region], rtol=.003, atol=.3)
    assert float(result.linear.max()) > 500
    explicit = merge_hdr(alignment, evs=(-2, -1, 0, 1, 2), mode="radiance")
    np.testing.assert_allclose(explicit.linear, result.linear, rtol=1e-5, atol=.001)
    suggested = suggest_exposure_evs(frames, reference_index=3)
    np.testing.assert_allclose(suggested, (-3, -2, -1, 0, 1), atol=1e-6)
    anchored = merge_hdr(alignment, evs=suggested, mode="radiance")
    np.testing.assert_allclose(anchored.linear, result.linear, rtol=1e-5, atol=.001)


def test_exposure_suggestions_do_not_invent_missing_metadata(tmp_path):
    data = np.ones((16, 23), dtype=np.float32)
    frames = [
        read_image(save_fits(tmp_path / "known.fits", data, exposure=2)),
        read_image(save_fits(tmp_path / "unknown.fits", data, exposure=None)),
    ]
    assert suggest_exposure_evs(frames, reference_index=0) is None
    with pytest.raises(ValueError):
        suggest_exposure_evs(frames, reference_index=7)


def test_rate_unit_fits_are_not_divided_by_exposure_twice(tmp_path):
    scene, disk = lunar_scene(size=128)
    rate = scene[:, :, 0] * 1500
    frames = [
        read_image(save_fits(tmp_path / f"rate-{index}.fits", rate, exposure=duration, BUNIT="ADU/s"))
        for index, duration in enumerate((.5, 1, 2, 4))
    ]
    alignment = align_images(frames, reference_index=2)
    result = merge_hdr(alignment, evs=None, mode="radiance")
    np.testing.assert_allclose(result.linear[:, :, 0][disk], rate[disk], rtol=.005, atol=.5)


def test_float_maximum_is_not_assumed_to_be_detector_saturation(tmp_path):
    rate = np.full((16, 23), 100.0, dtype=np.float32)
    rate[5:9, 8:12] = 7000
    frames = [
        read_image(save_fits(tmp_path / f"unclipped-{index}.fits", rate * duration, exposure=duration, BUNIT="ADU"))
        for index, duration in enumerate((.5, 2))
    ]
    assert all(frame.metadata["saturation_level"] is None for frame in frames)
    result = merge_hdr(registered_native(frames), evs=None)
    np.testing.assert_allclose(result.linear[:, :, 0], rate, rtol=1e-6)
    assert not any("saturated in every" in warning.lower() for warning in result.warnings)


@pytest.mark.parametrize("storage", ["float_declared_saturation", "uint16_storage_ceiling"])
def test_clipped_native_fits_highlights_recover_from_short_exposure(tmp_path, storage):
    saturation = 1000 if storage == "float_declared_saturation" else 65535
    rate = np.full((20, 25), saturation * .2, dtype=np.float32)
    rate[3:8, 4:10] = saturation * 1.3
    rate[12:17, 14:20] = saturation * 2.6
    frames = []
    for index, duration in enumerate((.25, 1, 4)):
        recorded = np.clip(rate * duration, 0, saturation)
        header = {"BUNIT": "ADU"}
        if storage == "float_declared_saturation":
            header["SATURATE"] = saturation
        else:
            recorded = recorded.astype(np.uint16)
        frames.append(read_image(save_fits(tmp_path / f"clipped-{index}.fits", recorded, exposure=duration, **header)))
    assert np.all(frames[1].linear_pixels[12:17, 14:20] == saturation)
    result = merge_hdr(registered_native(frames, reference_index=1), evs=None)
    np.testing.assert_allclose(result.linear[12:17, 14:20, 0], rate[12:17, 14:20], atol=4, rtol=1e-6)
    assert result.linear[13, 15, 0] > result.linear[4, 5, 0] * 1.9


def test_different_fits_units_are_rejected_for_radiance(tmp_path):
    rate = np.full((16, 23), 100.0, dtype=np.float32)
    frames = [
        read_image(save_fits(tmp_path / f"units-{index}.fits", rate, BUNIT=unit))
        for index, unit in enumerate(("ADU", "electron"))
    ]
    with pytest.raises(ValueError):
        merge_hdr(registered_native(frames), evs=None)


def test_surface_brightness_units_are_not_misread_as_counts_per_second(tmp_path):
    counts = np.full((16, 23), 100.0, dtype=np.float32)
    frames = [
        read_image(save_fits(tmp_path / f"surface-{index}.fits", counts, BUNIT="MJy/sr"))
        for index in range(2)
    ]
    with pytest.raises(ValueError):
        merge_hdr(registered_native(frames), evs=None)
    assert np.isfinite(merge_hdr(registered_native(frames), mode="fusion").base).all()


def test_subpixel_manual_warp_of_fifth_fits_frame_preserves_signal_next_to_holes(tmp_path):
    counts = np.full((24, 30), 4321.5, dtype=np.float32)
    counts[8:12, 10:14] = np.nan
    frames = [
        read_image(save_fits(tmp_path / f"manual-{index}.fits", counts, BUNIT="ADU"))
        for index in range(5)
    ]
    baseline = registered_native(frames, reference_index=2)
    original = baseline.linear_images[4].copy()
    corrected = manual_alignment(baseline, frames, index=4, dx=.5, dy=.5)
    covered = corrected.masks[4] > 0
    fractional = (corrected.masks[4] > 0) & (corrected.masks[4] < 1)
    assert fractional.any()
    np.testing.assert_allclose(corrected.linear_images[4][covered], 4321.5, atol=.001)
    np.testing.assert_array_equal(baseline.linear_images[4], original)
    assert corrected.metadata[4]["bunit"] == "ADU"


def test_fits_masks_survive_alignment_and_exclude_missing_reference_pixels(tmp_path):
    scene, _ = lunar_scene(size=128)
    rate = scene[:, :, 0] * 2000
    frames = []
    for index, duration in enumerate((0.5, 1, 2, 4)):
        data = rate * duration
        if index == 3:
            data[50:60, 60:70] = np.nan
        frames.append(read_image(save_fits(tmp_path / f"masked-{index}.fits", data, exposure=duration)))
    alignment = align_images(frames, reference_index=3)
    assert np.max(alignment.masks[3][50:60, 60:70]) == 0
    result = merge_hdr(alignment, evs=None, mode="radiance")
    assert np.isfinite(result.linear).all()
    # The other exposures contain the same signal after registration. Compare
    # against the warped signal: legitimate subpixel interpolation changes
    # high-frequency crater texture slightly even for nearly identical frames.
    expected = alignment.linear_images[0][52:58, 62:68, 0] / .5
    np.testing.assert_allclose(result.linear[52:58, 62:68, 0], expected, rtol=1e-5, atol=.001)
    assert np.mean(np.abs(result.linear[52:58, 62:68, 0] - rate[52:58, 62:68])) < 2.5


def test_mixed_native_fits_and_srgb_requires_display_fusion(tmp_path):
    scene, _ = lunar_scene(size=128)
    native = read_image(save_fits(tmp_path / "native.fits", scene[:, :, 0] * 1000))
    display = ImageFrame(path="display.png", name="display", pixels=srgb(scene), bit_depth=8)
    alignment = align_images([native, display], reference_index=0)
    with pytest.raises(ValueError):
        merge_hdr(alignment, evs=(0, 0), mode="radiance")
    result = merge_hdr(alignment, evs=(0, 0), mode="fusion")
    assert result.linear is None
    assert np.isfinite(result.base).all()


def test_fits_fusion_keeps_lunar_contrast_when_long_exposure_is_clipped(tmp_path):
    scene, disk = lunar_scene(size=256)
    rate = scene[:, :, 0] * 120000
    frames = [
        read_image(save_fits(
            tmp_path / f"fusion-clipped-{index}.fits",
            np.clip(rate * duration, 0, 65535).astype(np.uint16),
            exposure=duration,
            BUNIT="ADU",
        ))
        for index, duration in enumerate((.25, 1, 50))
    ]
    assert np.all(frames[2].linear_pixels[:, :, 0][disk] == 65535)
    usable = merge_hdr(registered_native(frames[:2], reference_index=1), mode="fusion").base
    with_clipped = merge_hdr(registered_native(frames, reference_index=1), mode="fusion").base
    yy, xx = np.mgrid[:256, :256]
    interior = (xx - 256 * .503) ** 2 + (yy - 256 * .491) ** 2 < (256 * .365 - 16) ** 2
    usable_values = usable[:, :, 0][interior]
    full_values = with_clipped[:, :, 0][interior]
    usable_contrast = float(np.percentile(usable_values, 90) - np.percentile(usable_values, 10))
    full_contrast = float(np.percentile(full_values, 90) - np.percentile(full_values, 10))
    assert full_contrast >= usable_contrast * .90
    assert np.mean(np.abs(full_values - usable_values)) < .04
    assert np.isfinite(with_clipped).all()


def test_all_clipped_fits_fusion_keeps_bright_fallback_and_warns(tmp_path):
    frames = [
        read_image(save_fits(
            tmp_path / f"fusion-all-clipped-{index}.fits",
            np.full((32, 40), 65535, dtype=np.uint16),
            exposure=duration,
            BUNIT="ADU",
        ))
        for index, duration in enumerate((.25, 1, 4))
    ]
    result = merge_hdr(registered_native(frames, reference_index=1), mode="fusion")
    assert result.linear is None
    assert np.isfinite(result.base).all()
    assert float(np.mean(result.base)) > .5
    assert any(("saturat" in warning.lower() or "clipped" in warning.lower())
               and ("all" in warning.lower() or "every" in warning.lower())
               for warning in result.warnings)
