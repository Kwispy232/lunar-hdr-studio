"""Creative finishing must preserve source data and lunar surface detail."""
import numpy as np
import pytest

from lunarhdr.finishing import finish_image


def moon_with_stars():
    height, width = 260, 380
    yy, xx = np.mgrid[:height, :width].astype(np.float32)
    radius = np.sqrt((xx - 194) ** 2 + (yy - 132) ** 2)
    sky = .012 + .035 * np.exp(-(radius / 125) ** 2)
    disk = radius < 82
    surface = .52 + .11 * np.sin(xx / 19) * np.cos(yy / 17)
    gray = np.where(disk, surface, sky)
    for x, y in ((30, 30), (340, 46), (335, 218), (49, 223)):
        gray += .65 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 1.8)
    image = np.repeat(gray[..., None], 3, axis=2).astype(np.float32)
    return image, disk


def test_disabled_finishing_is_exact_and_never_mutates_source():
    image, _ = moon_with_stars()
    original = image.copy()
    np.testing.assert_array_equal(finish_image(image), original)
    np.testing.assert_array_equal(finish_image(image, {"background": "original", "crop_enabled": False, "signature_enabled": False}), original)
    np.testing.assert_array_equal(image, original)


def test_added_stars_are_deterministic_and_leave_lunar_surface_untouched():
    image, disk = moon_with_stars()
    original = image.copy()
    options = {"background": "add", "stars_strength": 80}
    first, second = finish_image(image, options), finish_image(image, options)
    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(first[disk], original[disk])
    np.testing.assert_array_equal(image, original)
    assert np.max(first[~disk] - original[~disk]) > .1
    assert np.isfinite(first).all() and first.min() >= 0 and first.max() <= 1
    np.testing.assert_array_equal(finish_image(image, {"background": "add", "stars_strength": 0}), original)


def test_star_removal_removes_compact_peaks_but_preserves_moon_and_smooth_halo():
    image, disk = moon_with_stars()
    result = finish_image(image, {"background": "remove"})
    np.testing.assert_array_equal(result[disk], image[disk])
    for x, y in ((30, 30), (340, 46), (335, 218), (49, 223)):
        assert result[y, x, 0] < image[y, x, 0] * .2
    np.testing.assert_array_equal(result[20:35, 150:180], image[20:35, 150:180])


def test_normalized_crop_is_applied_after_stars_without_shifting_the_field():
    image, _ = moon_with_stars()
    options = {"background": "add", "stars_strength": 50}
    full = finish_image(image, options)
    cropped = finish_image(image, {**options, "crop_enabled": True, "crop_rect": (.2, .1, .6, .8)})
    expected = full[26:234, 76:304]
    np.testing.assert_array_equal(cropped, expected)
    assert cropped.flags.c_contiguous


def test_signature_follows_crop_and_keeps_unaffected_float_precision():
    random = np.random.default_rng(819)
    image = random.random((220, 340, 3), dtype=np.float32) * .3
    crop = {"crop_enabled": True, "crop_rect": (.1, .1, .7, .8)}
    plain = finish_image(image, crop)
    signed = finish_image(image, {**crop, "signature_enabled": True, "signature_text": "Mráz · Moon"})
    assert signed.shape == plain.shape
    np.testing.assert_array_equal(signed[:signed.shape[0] // 2], plain[:plain.shape[0] // 2])
    assert np.max(np.abs(signed - plain)) > .1
    changed_y, changed_x = np.where(np.any(signed != plain, axis=2))
    assert changed_y.min() > signed.shape[0] * .6
    assert changed_x.min() > signed.shape[1] * .4
    np.testing.assert_array_equal(finish_image(image, {"signature_enabled": True, "signature_text": "   "}), image)


@pytest.mark.parametrize("rect", [(-.1, 0, .5, .5), (0, 0, 0, .5), (.8, 0, .4, 1), (0, 0, 1), (0, 0, np.nan, 1)])
def test_invalid_crops_fail_clearly(rect):
    with pytest.raises(ValueError):
        finish_image(np.zeros((40, 50, 3), np.float32), {"crop_enabled": True, "crop_rect": rect})


def test_invalid_images_and_background_mode_fail_clearly():
    with pytest.raises(ValueError):
        finish_image(np.zeros((40, 50), np.float32))
    with pytest.raises(ValueError):
        finish_image(np.full((40, 50, 3), np.nan, np.float32))
    with pytest.raises(ValueError):
        finish_image(np.zeros((40, 50, 3), np.float32), {"background": "invented"})
