"""Deterministic, display-only finishing for raster previews and exports.

``background='add'`` adds an explicitly synthetic star field. Neither background
editing nor signatures belong in the unmodified linear radiance export. All
operations work on a copy; normalized cropping precedes the text signature.
"""
from __future__ import annotations

import math

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .engine import _detect_disk, _luma, _rgb, _small


def _protected_surface(image: np.ndarray) -> np.ndarray:
    """Protect the lunar disk plus a margin, independently of its color."""
    small, ratio = _small(image, limit=1000)
    disk = _detect_disk(small)
    mask = np.zeros(image.shape[:2], np.uint8)
    if disk:
        center = tuple(round(coordinate / ratio) for coordinate in disk["center"])
        cv2.circle(mask, center, round(disk["radius"] * 1.12 / ratio), 1, -1)
    else:
        # With no reliable disk, still protect contiguous bright objects. A
        # blank sky remains editable; dark lunar terrain inside a detected disk
        # is always protected by the circle above.
        gray = _luma(image)
        mask = np.uint8(gray > max(.08, float(np.percentile(gray, 99.5)) * .35))
        radius = max(2, round(min(image.shape[:2]) * .008))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
        mask = cv2.dilate(mask, kernel)
    return mask.astype(bool)


def _remove_stars(image: np.ndarray, protected: np.ndarray) -> np.ndarray:
    """Replace compact bright background points with a local RGB background."""
    gray = _luma(image)
    radius = max(2, min(18, round(min(image.shape[:2]) / 160)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
    baseline = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
    residual = np.maximum(gray - baseline, 0)
    outside = residual[~protected]
    if outside.size == 0:
        return image
    median = float(np.median(outside))
    mad = float(np.median(np.abs(outside - median)))
    threshold = max(.025, median + 5 * 1.4826 * mad)
    candidates = np.uint8((residual > threshold) & ~protected)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidates, connectivity=8)
    accepted = np.zeros(count, np.uint8)
    for index in range(1, count):
        _, _, width, height, area = stats[index]
        if area <= math.pi * radius * radius * 1.5 and max(width, height) <= radius * 2 + 3 and max(width, height) / max(min(width, height), 1) <= 3:
            accepted[index] = 1
    selected = accepted[labels]
    if not np.any(selected):
        return image
    selected = cv2.dilate(selected, np.ones((3, 3), np.uint8))
    selected[protected] = 0
    # Opening removes the compact peak while retaining broad smooth halo and
    # sky gradients. Only selected small regions are replaced, not the sky.
    background = cv2.morphologyEx(image, cv2.MORPH_OPEN, kernel)
    background = cv2.GaussianBlur(background, (0, 0), .6)
    result = image.copy()
    result[selected.astype(bool)] = background[selected.astype(bool)]
    return result


def _add_stars(image: np.ndarray, protected: np.ndarray, strength: float) -> np.ndarray:
    """Screen-blend Gaussian points at stable, normalized synthetic positions."""
    if strength <= 0:
        return image
    height, width = image.shape[:2]
    random = np.random.default_rng(731942)
    # Generate the same normalized candidates at every preview/export size.
    candidates = random.random((200, 5))
    number = round(20 + 1.5 * strength)
    result = image.copy()
    scale = min(height, width) / 900.
    for x, y, size, brightness, color in candidates[:number]:
        cx, cy = x * (width - 1), y * (height - 1)
        if protected[round(cy), round(cx)]:
            continue
        sigma = max(.32, (.5 + size ** 3 * 1.2) * scale)
        radius = max(2, math.ceil(sigma * 3))
        left, right = max(0, math.floor(cx) - radius), min(width, math.floor(cx) + radius + 2)
        top, bottom = max(0, math.floor(cy) - radius), min(height, math.floor(cy) + radius + 2)
        yy, xx = np.mgrid[top:bottom, left:right].astype(np.float32)
        opacity = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma * sigma))
        opacity *= (.30 + .60 * brightness) * (.35 + strength / 100 * .65)
        opacity[protected[top:bottom, left:right]] = 0
        tint = np.float32([1., .98, .91]) if color < .5 else np.float32([.90, .96, 1.])
        layer = opacity[..., None] * tint
        patch = result[top:bottom, left:right]
        blended = 1 - (1 - patch) * (1 - layer)
        result[top:bottom, left:right] = np.where(protected[top:bottom, left:right, None], patch, blended)
    return result


def _crop(image: np.ndarray, rect) -> np.ndarray:
    try:
        if len(rect) != 4:
            raise ValueError
        x, y, width, height = (float(value) for value in rect)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Crop must contain normalized x, y, width and height.") from exc
    if not all(math.isfinite(value) for value in (x, y, width, height)) or x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1.000001 or y + height > 1.000001:
        raise ValueError("Crop must stay within the image and have positive width and height.")
    source_height, source_width = image.shape[:2]
    left, top = round(x * source_width), round(y * source_height)
    right, bottom = min(source_width, round((x + width) * source_width)), min(source_height, round((y + height) * source_height))
    if right - left < 2 or bottom - top < 2:
        raise ValueError("Crop must contain at least 2 × 2 pixels.")
    return np.ascontiguousarray(image[top:bottom, left:right])


def _signature(image: np.ndarray, text: str) -> np.ndarray:
    text = " ".join(str(text).split())[:160]
    height, width = image.shape[:2]
    if not text or min(height, width) < 24:
        return image
    margin = max(4, round(min(height, width) * .025))
    size = max(6, round(min(height, width) * .032))
    font = ImageFont.load_default(size=size)
    left, top, right, bottom = font.getbbox(text)
    available = max(1, width - margin * 2)
    preferred_width = min(available, width * .48)
    if right - left > preferred_width:
        size = max(1, math.floor(size * preferred_width / max(right - left, 1)))
        font = ImageFont.load_default(size=size)
        left, top, right, bottom = font.getbbox(text)
    x = width - margin - right
    y = height - margin - bottom
    text_mask = Image.new("L", (width, height))
    ImageDraw.Draw(text_mask).text((x, y), text, font=font, fill=255)
    alpha = np.asarray(text_mask, np.float32) / 255 * .82
    offset = max(1, round(min(height, width) / 500))
    shadow = cv2.warpAffine(alpha, np.float32([[1, 0, offset], [0, 1, offset]]), (width, height))
    shadow = cv2.GaussianBlur(shadow, (0, 0), max(.5, offset * .6)) * .65
    # Composite float masks instead of converting the image through Pillow:
    # TIFF precision outside the text is retained exactly.
    result = image * (1 - shadow[..., None])
    return result * (1 - alpha[..., None]) + np.float32([.97, .98, 1.]) * alpha[..., None]


def finish_image(pixels: np.ndarray, options: dict | None = None) -> np.ndarray:
    """Apply optional raster-only finishing in full-image coordinates.

    Options: background (original/remove/add), stars_strength (0–100; controls
    added synthetic stars), crop_enabled and crop_rect (normalized x,y,w,h),
    signature_enabled and signature_text. Disabled/default options are a no-op.
    Star edits precede cropping so their positions stay stable; signature size
    and bottom-right placement follow the cropped output dimensions.
    """
    image = _rgb(pixels).copy()
    options = {} if options is None else dict(options)
    mode = options.get("background", "original")
    if mode not in ("original", "remove", "add"):
        raise ValueError("Background mode must be original, remove or add.")
    if mode != "original":
        protected = _protected_surface(image)
        if mode == "remove":
            image = _remove_stars(image, protected)
        else:
            try:
                strength = float(options.get("stars_strength", 50))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Synthetic star strength must be a finite number.") from exc
            if not math.isfinite(strength):
                raise ValueError("Synthetic star strength must be a finite number.")
            image = _add_stars(image, protected, float(np.clip(strength, 0, 100)))
    if options.get("crop_enabled", False):
        image = _crop(image, options.get("crop_rect", (0, 0, 1, 1)))
    if options.get("signature_enabled", False):
        image = _signature(image, options.get("signature_text", "Lunar HDR"))
    return np.ascontiguousarray(np.clip(image, 0, 1), dtype=np.float32)
