"""Numerical checks using generated images, never the user's reference artwork."""

import cv2
import numpy as np
import pytest

from lunarhdr.engine import (
    AlignmentResult,
    ImageFrame,
    adjust_image,
    align_images,
    manual_alignment,
    merge_hdr,
    read_image,
    write_image,
)


def srgb(linear):
    linear = np.maximum(linear, 0).astype(np.float32)
    return np.clip(
        np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * linear ** (1 / 2.4) - 0.055),
        0,
        1,
    )


def lunar_scene(size=400):
    """A reproducible lunar limb, craters, maria and weak color differences."""
    rng = np.random.default_rng(148)
    yy, xx = np.mgrid[:size, :size].astype(np.float32)
    cx, cy, radius = size * 0.503, size * 0.491, size * 0.365
    disk = (xx - cx) ** 2 + (yy - cy) ** 2 < radius**2
    noise = rng.random((size, size), dtype=np.float32)
    surface = 0.12 + 0.12 * cv2.GaussianBlur(noise, (0, 0), 2)
    surface += 0.055 * noise
    for _ in range(100):
        x, y = rng.uniform(size * 0.2, size * 0.8, 2)
        r = rng.uniform(2, 13)
        d2 = (xx - x) ** 2 + (yy - y) ** 2
        surface -= rng.uniform(0.01, 0.09) * np.exp(-d2 / (r**2))
        surface += 0.035 * np.exp(-((np.sqrt(d2) - r) / 1.0) ** 2)
    surface += 0.045 * np.sin(xx / 38) * np.cos(yy / 47)
    surface = np.clip(surface, 0.012, 0.4)
    rgb = np.stack((surface * 1.03, surface, surface * (0.98 + xx / size * 0.04)), axis=-1)
    rgb[~disk] = 0.0007
    return rgb.astype(np.float32), disk


def frame(pixels, index):
    return ImageFrame(path=f"synthetic-{index}.tiff", name=f"synthetic-{index}", pixels=pixels, bit_depth=16)


def identity_alignment(images):
    height, width = images[0].shape[:2]
    return AlignmentResult(
        images=images,
        masks=[np.ones((height, width), np.float32) for _ in images],
        matrices=[np.eye(2, 3, dtype=np.float32) for _ in images],
        reports=[],
        reference_index=1,
    )


def transform_points(points, matrix):
    matrix = np.asarray(matrix)
    if matrix.shape == (3, 3):
        transformed = np.c_[points, np.ones(len(points))] @ matrix.T
        return transformed[:, :2] / transformed[:, 2:3]
    return np.c_[points, np.ones(len(points))] @ matrix.T


def test_aligns_translated_rotated_scaled_disks_across_exposures():
    scene, disk = lunar_scene()
    height, width = disk.shape
    source_matrices = []
    images = []
    for index, (angle, scale, dx, dy, ev) in enumerate(
        [(4.0, 0.95, 12.0, -9.0, -2), (0.0, 1.0, 0.0, 0.0, 0), (-3.0, 1.035, -10.0, 8.0, 2)]
    ):
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, scale)
        matrix[:, 2] += (dx, dy)
        observed = cv2.warpAffine(srgb(scene * 2**ev), matrix, (width, height))
        images.append(frame(observed, index))
        source_matrices.append(matrix)

    result = align_images(images, reference_index=1)
    assert len(result.images) == len(result.masks) == len(result.matrices) == 3
    assert result.reference_index == 1
    points = np.array([[200, 200], [140, 140], [140, 260], [260, 140], [260, 260]], dtype=np.float32)
    for index in range(3):
        observed_points = transform_points(points, source_matrices[index])
        recovered_points = transform_points(observed_points, result.matrices[index])
        errors = np.linalg.norm(recovered_points - points, axis=1)
        assert np.median(errors) < 2.5, f"Frame {index} registration error: {errors}"
        assert np.max(errors) < 4.0
        assert result.images[index].shape == scene.shape
        assert result.masks[index].shape == disk.shape
        assert np.isfinite(result.images[index]).all()
        assert np.isfinite(result.masks[index]).all()
        assert np.mean(np.asarray(result.masks[index])[disk]) > 0.9


def test_featureless_disks_report_unverified_rotation():
    images = []
    for index, (cx, cy, radius) in enumerate([(131, 111, 78), (120, 120, 75), (110, 130, 71)]):
        image = np.zeros((240, 240, 3), dtype=np.float32)
        cv2.circle(image, (cx, cy), radius, (1.0, 1.0, 1.0), -1)
        images.append(frame(image, index))
    result = align_images(images, reference_index=1)
    for index in (0, 2):
        report = result.reports[index]
        assert report["method"] in ("disk", "center")
        assert report["confidence"] < 0.5
        assert report["warning"]


def test_clipped_disk_fallback_uses_lunar_limb_instead_of_extended_halo():
    scene, _ = lunar_scene(size=400)
    reference = np.full((600, 600, 3), .001, dtype=np.float32)
    reference[100:500, 100:500] = srgb(scene)
    reference_center = np.float32([400 * .503 + 100, 400 * .491 + 100])
    source_center = reference_center + np.float32([12, -7])
    reference_radius = 400 * .365
    source_radius = reference_radius * 1.06
    yy, xx = np.mgrid[:600, :600].astype(np.float32)
    distance = np.hypot(xx - source_center[0], yy - source_center[1])
    # The clipped lunar face has no reliable surface features. Extended glow
    # remains substantially dimmer than the face but biases low thresholds.
    halo = .7 * np.exp(-np.maximum(distance - source_radius, 0) / 45)
    source = np.where(distance <= source_radius, 1., halo).astype(np.float32)
    source = cv2.GaussianBlur(source, (0, 0), 1.2)
    source = np.repeat(source[..., None], 3, axis=2)
    result = align_images([frame(source, 0), frame(reference, 1)], reference_index=1)
    matrix = result.matrices[0]
    recovered_center = transform_points(source_center[None], matrix)[0]
    measured_scale = float(np.linalg.norm(matrix[0, :2]))
    assert np.linalg.norm(recovered_center - reference_center) < 3
    assert abs(measured_scale - 1 / 1.06) < .035
    assert result.reports[0]["method"] == "disk"
    assert result.reports[0]["confidence"] < .5
    assert result.reports[0]["warning"]


def test_five_exposures_align_and_merge_with_fourth_frame_as_reference():
    scene, disk = lunar_scene(size=320)
    height, width = disk.shape
    evs = (-2, -1, 0, 1, 2)
    transforms = [(2, .96, 9, -5), (-2, 1.02, -7, 5), (1, .99, 3, -4), (0, 1, 0, 0), (-3, 1.03, -8, 7)]
    frames, source_matrices = [], []
    for index, ((angle, scale, dx, dy), ev) in enumerate(zip(transforms, evs)):
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, scale)
        matrix[:, 2] += (dx, dy)
        observed = cv2.warpAffine(srgb(scene * 2**ev), matrix, (width, height))
        frames.append(frame(observed, index))
        source_matrices.append(matrix)
    alignment = align_images(frames, reference_index=3)
    assert len(alignment.images) == len(alignment.reports) == 5
    assert alignment.reference_index == 3
    np.testing.assert_allclose(alignment.matrices[3], np.eye(2, 3), atol=1e-5)
    points = np.float32([[160, 160], [110, 110], [210, 210]])
    for index in range(5):
        recovered = transform_points(transform_points(points, source_matrices[index]), alignment.matrices[index])
        assert np.max(np.linalg.norm(recovered - points, axis=1)) < 3
    composite = merge_hdr(alignment, evs=evs, mode="radiance")
    interior = cv2.erode(disk.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    assert np.mean(np.abs(composite.linear[interior] - scene[interior])) < .015


def test_manual_correction_supports_fifth_frame_without_mutating_baseline():
    scene, _ = lunar_scene(size=128)
    pixels = srgb(scene)
    frames = [frame(pixels.copy(), index) for index in range(5)]
    baseline = identity_alignment([item.pixels.copy() for item in frames])
    baseline.reference_index = 3
    baseline.reports = [{} for _ in frames]
    saved_matrix = baseline.matrices[4].copy()
    result = manual_alignment(baseline, frames, index=4, dx=7, dy=-4)
    repeated = manual_alignment(baseline, frames, index=4, dx=7, dy=-4)
    np.testing.assert_allclose(result.images[4][:-4, 7:], pixels[4:, :-7], atol=1e-6)
    np.testing.assert_array_equal(baseline.images[4], pixels)
    np.testing.assert_array_equal(baseline.matrices[4], saved_matrix)
    np.testing.assert_array_equal(result.images[4], repeated.images[4])
    assert result.reference_index == 3
    assert len(result.images) == 5


def test_radiance_merge_recovers_distinct_clipped_highlights():
    scene, _ = lunar_scene(size=160)
    scene[50:75, 50:75] = 1.3
    scene[85:110, 85:110] = 2.8
    images = [srgb(scene * 2**ev) for ev in (-2, 0, 2)]
    assert np.allclose(images[1][55:70, 55:70], images[1][90:105, 90:105])

    composite = merge_hdr(identity_alignment(images), evs=(-2, 0, 2), mode="radiance")
    low = float(np.mean(composite.linear[55:70, 55:70]))
    high = float(np.mean(composite.linear[90:105, 90:105]))
    assert high > low * 1.65, "HDR must recover highlight values lost by the normal exposure."
    assert high > 1.0, "The exported linear buffer must retain values above SDR white."
    assert np.isfinite(composite.linear).all()
    assert np.isfinite(composite.base).all()
    assert composite.base.shape == scene.shape
    assert 0 <= float(composite.base.min()) <= float(composite.base.max()) <= 1


def test_highlights_clipped_in_every_exposure_stay_bright_and_warn():
    images = [np.ones((32, 32, 3), dtype=np.float32) for _ in range(3)]
    result = merge_hdr(identity_alignment(images), evs=(-2, 0, 2), mode="radiance")
    assert np.isfinite(result.linear).all()
    assert float(np.min(result.linear)) >= 3.9
    assert float(np.mean(result.base)) > 0.5
    assert any("clipped" in warning.lower() for warning in result.warnings)


@pytest.mark.parametrize("mode", ["radiance", "fusion"])
def test_merge_masked_borders_are_finite(mode):
    scene, _ = lunar_scene(size=128)
    alignment = identity_alignment([srgb(scene * 2**ev) for ev in (-2, 0, 2)])
    for image, mask in zip(alignment.images, alignment.masks):
        mask[:, :12] = 0
        image[:, :12] = 0
    result = merge_hdr(alignment, evs=(-2, 0, 2), mode=mode)
    assert np.isfinite(result.base).all()
    if mode == "radiance":
        assert np.isfinite(result.linear).all()
    else:
        assert result.linear is None
    assert result.base.shape == scene.shape


def test_sixteen_bit_tiff_roundtrip_preserves_rgb_precision(tmp_path):
    rng = np.random.default_rng(21)
    pixels = rng.random((40, 51, 3), dtype=np.float32)
    path = tmp_path / "precision.tiff"
    write_image(path, pixels)
    stored = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    assert stored.dtype == np.uint16
    result = read_image(path)
    assert result.bit_depth == 16
    assert result.pixels.shape == pixels.shape
    assert np.max(np.abs(result.pixels - pixels)) <= 2 / 65535


def test_grayscale_import_expands_channels_without_losing_depth(tmp_path):
    gray = np.linspace(0, 65535, 25 * 29, dtype=np.uint16).reshape(25, 29)
    path = tmp_path / "gray.tif"
    assert cv2.imwrite(str(path), gray)
    result = read_image(path)
    assert result.pixels.shape == (25, 29, 3)
    assert result.bit_depth == 16
    for channel in range(3):
        np.testing.assert_allclose(result.pixels[:, :, channel], gray / 65535, atol=1 / 65535)


def test_compressed_sixteen_bit_tiff_preserves_color_channels(tmp_path):
    rgb = np.empty((25, 29, 3), dtype=np.uint16)
    rgb[:] = (52001, 19003, 7007)
    path = tmp_path / "compressed-rgb.tif"
    assert cv2.imwrite(str(path), rgb[:, :, ::-1], [cv2.IMWRITE_TIFF_COMPRESSION, 5])
    result = read_image(path)
    assert result.bit_depth == 16
    np.testing.assert_allclose(result.pixels, rgb / 65535, atol=1 / 65535)


def test_radiance_export_retains_hdr_values(tmp_path):
    linear = np.empty((20, 30, 3), dtype=np.float32)
    linear[:] = (3.5, 0.8, 0.06)
    path = tmp_path / "radiance.hdr"
    write_image(path, srgb(linear), linear_hdr=linear)
    stored = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)[:, :, ::-1]
    assert stored.dtype == np.float32
    assert float(stored.max()) > 3
    np.testing.assert_allclose(stored, linear, atol=0.02)


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"exposure": 3, "contrast": 100, "shadows": 100, "highlights": -100},
        {"saturation": 200, "mineral": 100, "clarity": 100, "sharpness": 100, "denoise": 100},
        {"exposure": -3, "temperature": -100, "saturation": 0, "contrast": -100},
    ],
)
def test_adjustments_are_finite_and_do_not_mutate_source(settings):
    scene, _ = lunar_scene(size=128)
    source = srgb(scene)
    source[0, 0] = 0
    source[0, 1] = 1
    original = source.copy()
    edited = adjust_image(source, settings)
    np.testing.assert_array_equal(source, original)
    assert edited.shape == source.shape
    assert np.isfinite(edited).all()
    assert edited.min() >= 0 and edited.max() <= 1


def test_white_balance_neutralizes_known_lunar_cast_without_changing_luminance():
    scene, disk = lunar_scene(size=160)
    neutral = scene[:, :, 1]
    linear = neutral[..., None] * np.float32([1.3, .9, .6])
    source = srgb(linear)
    original = source.copy()
    edited = adjust_image(source, {"white_balance": 100})
    recovered = np.where(edited <= .04045, edited / 12.92, ((edited + .055) / 1.055) ** 2.4)
    # Every lunar sample started neutral before the known channel multiplier.
    # Balance should remove that cast without changing its linear brightness.
    assert np.mean(np.ptp(recovered[disk], axis=1)) < .001
    weights = np.float32([.2126, .7152, .0722])
    np.testing.assert_allclose(recovered[disk] @ weights, linear[disk] @ weights, atol=1e-5)
    np.testing.assert_array_equal(source, original)
    assert np.isfinite(edited).all()
    assert edited.min() >= 0 and edited.max() <= 1


def test_white_balance_preserves_monochrome_and_default_behavior():
    gray = np.linspace(0, 1, 32 * 45, dtype=np.float32).reshape(32, 45)
    source = np.repeat(gray[..., None], 3, axis=2)
    default = adjust_image(source, {})
    balanced = adjust_image(source, {"white_balance": 100})
    np.testing.assert_array_equal(balanced, default)
    np.testing.assert_array_equal(adjust_image(source, {"white_balance": 0}), default)
    np.testing.assert_array_equal(source[:, :, 0], gray)


def test_invalid_inputs_raise_clear_errors(tmp_path):
    with pytest.raises((FileNotFoundError, ValueError, OSError)):
        read_image(tmp_path / "missing.png")
    with pytest.raises((ValueError, IndexError)):
        align_images([], reference_index=0)
    pixels = np.zeros((32, 32, 3), dtype=np.float32)
    alignment = identity_alignment([pixels.copy() for _ in range(3)])
    with pytest.raises(ValueError):
        merge_hdr(alignment, evs=(0, 1), mode="radiance")
    with pytest.raises(ValueError):
        merge_hdr(alignment, mode="not-a-mode")
    with pytest.raises(ValueError):
        write_image(tmp_path / "unsupported.txt", pixels)
