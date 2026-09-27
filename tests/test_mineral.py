"""Mineral enhancement should reveal captured chroma without repainting luminance."""

import numpy as np
import pytest

from lunarhdr.engine import adjust_image


LUMA = np.float32([0.2126, 0.7152, 0.0722])
MINERAL_ONLY = dict(mineral=100, saturation=100, white_balance=0, temperature=0)


def encode_srgb(linear):
    linear = np.asarray(linear, dtype=np.float32)
    return np.where(linear <= 0.0031308, linear * 12.92,
                    1.055 * np.maximum(linear, 0) ** (1 / 2.4) - 0.055).astype(np.float32)


def decode_srgb(image):
    image = np.asarray(image, dtype=np.float32)
    return np.where(image <= 0.04045, image / 12.92,
                    ((image + 0.055) / 1.055) ** 2.4).astype(np.float32)


def moon_with_weak_surface_color():
    """A textured disk with measured weak color, a bright halo and a colored star."""
    yy, xx = np.mgrid[:192, :256].astype(np.float32)
    radius = np.hypot(xx - 128, yy - 96)
    disk = radius < 62
    halo = .009 + .025 * np.exp(-((radius - 62) / 60) ** 2)
    texture = .20 + .035 * np.sin(xx / 10) * np.cos(yy / 13)
    luminance = np.where(disk, texture, halo)
    linear = np.repeat(luminance[..., None], 3, axis=2)
    # Mildly colored sky ensures the test catches background color changes too.
    sky_color = np.float32([.96, 1., 1.06])
    sky_color /= sky_color @ LUMA
    linear[~disk] *= sky_color
    warm_direction = np.float32([1., .1, -1.])
    cool_direction = np.float32([-.7, -.1, 1.1])
    warm_direction -= warm_direction @ LUMA
    cool_direction -= cool_direction @ LUMA
    linear[disk & (xx < 126)] += .008 * warm_direction
    linear[disk & (xx >= 126)] += .008 * cool_direction
    star = np.exp(-((xx - 26) ** 2 + (yy - 22) ** 2) / 2)
    linear += star[..., None] * np.float32([.22, .18, .08])
    image = encode_srgb(linear)
    warm_interior = (radius < 45) & (xx < 115)
    cool_interior = (radius < 45) & (xx > 141)
    far_background = radius > 88
    return image, warm_interior, cool_interior, far_background


def opponent_chroma(linear):
    return np.stack((linear[..., 0] - linear[..., 1],
                     linear[..., 2] - linear[..., 1]), axis=-1)


@pytest.mark.parametrize("white_balance", [0, 100])
def test_grayscale_never_acquires_mineral_hues_from_brightness(white_balance):
    yy, xx = np.mgrid[:128, :192].astype(np.float32)
    distance = np.hypot(xx - 96, yy - 64)
    gray = np.where(distance < 45, .10 + .82 * (xx / 192), .025 + .05 * np.exp(-distance / 70))
    gray[4:12, :7] = 0
    gray[4:12, 7:14] = 1
    image = np.repeat(gray[..., None], 3, axis=2).astype(np.float32)
    result = adjust_image(image, dict(MINERAL_ONLY, white_balance=white_balance))
    assert np.max(np.ptp(result, axis=2)) <= 2e-6
    np.testing.assert_allclose(result, image, atol=2e-6, rtol=0)


def test_existing_warm_and_cool_surface_chroma_is_amplified_without_flipping_hues():
    image, warm, cool, _ = moon_with_weak_surface_color()
    before = opponent_chroma(decode_srgb(image))
    after = opponent_chroma(decode_srgb(adjust_image(image, MINERAL_ONLY)))
    for region in (warm, cool):
        captured = np.mean(before[region], axis=0)
        enhanced = np.mean(after[region], axis=0)
        assert np.linalg.norm(enhanced) > 1.5 * np.linalg.norm(captured)
        assert np.all(captured * enhanced > 0), "surface hue was replaced instead of enhanced"
        cosine = float(captured @ enhanced / (np.linalg.norm(captured) * np.linalg.norm(enhanced)))
        assert cosine > .98
    assert np.mean(after[warm, 0]) > 0 and np.mean(after[warm, 1]) < 0
    assert np.mean(after[cool, 0]) < 0 and np.mean(after[cool, 1]) > 0


def test_mineral_only_preserves_linear_luminance_and_existing_glow():
    image, _, _, background = moon_with_weak_surface_color()
    result = adjust_image(image, MINERAL_ONLY)
    before_y = decode_srgb(image) @ LUMA
    after_y = decode_srgb(result) @ LUMA
    np.testing.assert_allclose(after_y, before_y, atol=1e-5, rtol=0)
    np.testing.assert_allclose(result[background], image[background], atol=2e-6, rtol=0)
    assert np.min(after_y[background]) > .005, "the existing sky glow was forced to black"
    assert np.mean(after_y[background]) >= .999 * np.mean(before_y[background])


def test_mineral_processing_never_mutates_or_aliases_its_input():
    image, *_ = moon_with_weak_surface_color()
    original = image.copy()
    image.setflags(write=False)
    result = adjust_image(image, MINERAL_ONLY)
    np.testing.assert_array_equal(image, original)
    assert not np.shares_memory(result, image)
    assert result.shape == image.shape and result.dtype == np.float32
    assert np.isfinite(result).all() and result.min() >= 0 and result.max() <= 1


def test_uniform_color_cast_does_not_become_a_brightness_based_palette():
    yy, xx = np.mgrid[:160, :200].astype(np.float32)
    radius = np.hypot(xx - 100, yy - 80)
    disk = radius < 57
    luminance = np.where(disk, .08 + .40 * (xx / 200), .008)
    color = np.float32([1.03, 1., .965])
    color /= color @ LUMA
    linear = luminance[..., None] * color
    image = encode_srgb(linear)
    result = decode_srgb(adjust_image(image, MINERAL_ONLY))
    interior = radius < 38
    chroma = opponent_chroma(result)[interior]
    directions = chroma / np.maximum(np.linalg.norm(chroma, axis=1, keepdims=True), 1e-8)
    captured = opponent_chroma(linear)[interior]
    captured /= np.linalg.norm(captured, axis=1, keepdims=True)
    assert np.min(np.sum(directions * captured, axis=1)) > .995
    assert np.max(np.std(directions, axis=0)) < .01


@pytest.mark.parametrize("kind", ["black", "white", "tiny_gradient", "clipped_disk"])
def test_missing_or_partial_disk_has_a_finite_graceful_fallback(kind):
    if kind in ("black", "white"):
        image = np.full((48, 64, 3), 0 if kind == "black" else 1, dtype=np.float32)
    elif kind == "tiny_gradient":
        gray = np.linspace(.015, .8, 9 * 17, dtype=np.float32).reshape(9, 17)
        image = np.repeat(gray[..., None], 3, axis=2)
    else:
        yy, xx = np.mgrid[:96, :128].astype(np.float32)
        disk = np.hypot(xx - 128, yy - 48) < 58
        gray = np.where(disk, .32 + .03 * np.sin(yy / 9), .03).astype(np.float32)
        image = gray[..., None] * np.float32([1.01, 1., .99])
    original = image.copy()
    result = adjust_image(image, MINERAL_ONLY)
    assert result.shape == image.shape and np.isfinite(result).all()
    assert result.min() >= 0 and result.max() <= 1
    np.testing.assert_array_equal(image, original)
