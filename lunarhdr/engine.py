"""Local lunar registration, exposure merging and non-destructive finishing.

Image arrays use RGB, display-referred sRGB in [0, 1], unless explicitly named
``linear``. Radiance values are relative to the supplied EV 0 exposure; they are
not a measurement of physical lunar radiance. Processed camera files are assumed
to use the sRGB response. RAW development belongs upstream of this application.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import math
import re

import cv2
import numpy as np
from PIL import Image
import tifffile

from .fits_io import is_fits_path, read_fits


Progress = Callable[[int, str], None]


@dataclass
class ImageFrame:
    path: str
    name: str
    pixels: np.ndarray
    bit_depth: int
    linear_pixels: np.ndarray | None = None
    valid_mask: np.ndarray | None = None
    exposure_seconds: float | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class AlignmentResult:
    images: list[np.ndarray]
    masks: list[np.ndarray]
    matrices: list[np.ndarray]
    reports: list[dict]
    reference_index: int
    linear_images: list[np.ndarray | None] | None = None
    metadata: list[dict] = field(default_factory=list)


@dataclass
class Composite:
    base: np.ndarray
    linear: np.ndarray | None
    mode: str
    warnings: list[str]


def _progress(callback, value: int, message: str) -> None:
    if callback:
        callback(value, message)


def _rgb(array: np.ndarray) -> np.ndarray:
    array = np.asarray(array)
    if array.ndim != 3 or array.shape[2] != 3 or min(array.shape[:2]) < 2:
        raise ValueError("Expected an RGB image with at least 2 × 2 pixels.")
    if not np.isfinite(array).all():
        raise ValueError("Image contains non-finite pixel values.")
    return np.ascontiguousarray(np.clip(array, 0, 1), dtype=np.float32)


def _orient(array: np.ndarray, orientation: int) -> np.ndarray:
    if orientation == 2:
        return np.fliplr(array)
    if orientation == 3:
        return np.rot90(array, 2)
    if orientation == 4:
        return np.flipud(array)
    if orientation == 5:
        return np.swapaxes(array, 0, 1)
    if orientation == 6:
        return np.rot90(array, -1)
    if orientation == 7:
        return np.flip(np.swapaxes(array, 0, 1), axis=(0, 1))
    if orientation == 8:
        return np.rot90(array, 1)
    return array


def read_image(path: str, max_dimension: int | None = None) -> ImageFrame:
    """Read PNG/JPEG/TIFF/FITS without reducing high-bit-depth input to 8 bit.

    EXIF orientation is applied. Alpha is composited over black; multi-page TIFF
    uses its first page. Grayscale input becomes neutral RGB. A max_dimension
    limit changes the working/export resolution and never upscales an image.
    """
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"Image does not exist: {source}")
    if max_dimension is not None and max_dimension < 2:
        raise ValueError("Maximum image dimension must be at least 2 pixels.")
    if is_fits_path(source):
        return ImageFrame(**read_fits(source, max_dimension=max_dimension))
    orientation = 1
    try:
        with Image.open(source) as metadata:
            orientation = int(metadata.getexif().get(274, 1))
    except Exception:
        pass
    try:
        if source.suffix.lower() in (".tif", ".tiff"):
            with tifffile.TiffFile(source) as tif:
                page = tif.pages[0]
                try:
                    array = page.asarray()
                except (ValueError, KeyError):
                    # OpenCV ships LZW/Deflate TIFF codecs; tifffile delegates
                    # some codecs to the optional imagecodecs package.
                    array = cv2.imdecode(np.fromfile(source, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    if array is None:
                        raise ValueError("This TIFF compression could not be decoded. Save as an uncompressed TIFF.")
                    if array.ndim == 3:
                        array = cv2.cvtColor(array, cv2.COLOR_BGRA2RGBA if array.shape[-1] == 4 else cv2.COLOR_BGR2RGB)
                else:
                    if page.planarconfig == 2 and array.ndim == 3:
                        array = np.moveaxis(array, 0, -1)
                    if page.photometric == 0:  # MINISWHITE
                        ceiling = np.iinfo(array.dtype).max if np.issubdtype(array.dtype, np.integer) else 1
                        array = ceiling - array
        else:
            array = cv2.imdecode(np.fromfile(source, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if array is not None and array.ndim == 3:
                if array.shape[-1] == 4:
                    array = cv2.cvtColor(array, cv2.COLOR_BGRA2RGBA)
                else:
                    array = cv2.cvtColor(array, cv2.COLOR_BGR2RGB)
            if array is None:
                with Image.open(source) as image:
                    array = np.asarray(image.convert("RGBA"))
    except Exception as exc:
        raise ValueError(f"Cannot decode image {source.name}: {exc}") from exc
    if array.ndim == 2:
        array = np.repeat(array[..., None], 3, axis=2)
    elif array.ndim == 3 and array.shape[-1] in (1, 2):
        gray = np.repeat(array[..., :1], 3, axis=2)
        array = np.concatenate((gray, array[..., 1:2]), axis=2) if array.shape[-1] == 2 else gray
    if array.ndim != 3 or array.shape[-1] not in (3, 4):
        raise ValueError("Unsupported TIFF layout; use a single RGB or grayscale image.")
    bit_depth = array.dtype.itemsize * 8
    if np.issubdtype(array.dtype, np.integer):
        array = array.astype(np.float32) / float(np.iinfo(array.dtype).max)
    else:
        array = array.astype(np.float32)
    if array.shape[-1] == 4:
        array = array[..., :3] * np.clip(array[..., 3:4], 0, 1)
    array = _rgb(_orient(array, orientation))
    h, w = array.shape[:2]
    if max_dimension is not None and max(h, w) > max_dimension:
        ratio = max_dimension / max(h, w)
        array = cv2.resize(array, (max(2, round(w * ratio)), max(2, round(h * ratio))), interpolation=cv2.INTER_AREA)
    return ImageFrame(str(source.resolve()), source.name, array, bit_depth)


def suggest_exposure_evs(frames: list[ImageFrame], reference_index: int = 1) -> list[float] | None:
    """Suggest relative EVs only when every frame has a valid exposure time."""
    if not 0 <= reference_index < len(frames):
        raise ValueError("Invalid reference image index.")
    times = [frame.exposure_seconds for frame in frames]
    if any(time is None or not math.isfinite(time) or time <= 0 for time in times):
        return None
    reference = times[reference_index]
    return [math.log2(time / reference) for time in times]


def _luma(image: np.ndarray) -> np.ndarray:
    return image @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _linear(image: np.ndarray) -> np.ndarray:
    return np.where(image <= .04045, image / 12.92, ((image + .055) / 1.055) ** 2.4).astype(np.float32)


def _srgb(image: np.ndarray) -> np.ndarray:
    image = np.maximum(image, 0)
    return np.where(image <= .0031308, image * 12.92, 1.055 * image ** (1 / 2.4) - .055).astype(np.float32)


def _small(image: np.ndarray, limit: int = 1600) -> tuple[np.ndarray, float]:
    ratio = min(1., limit / max(image.shape[:2]))
    if ratio < 1:
        return cv2.resize(image, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA), ratio
    return image, ratio


def _detect_disk(image: np.ndarray) -> dict | None:
    """Find the main illuminated disk; a seed, never proof of registration."""
    gray = _luma(image)
    low, high = np.percentile(gray, [15, 99.7])
    if high - low < .006:
        return None
    normalized = np.uint8(np.clip((gray - low) / (high - low), 0, 1) * 255)
    normalized = cv2.GaussianBlur(normalized, (5, 5), 0)
    otsu, _ = cv2.threshold(normalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = max(25, min(150, otsu * .72))
    binary = np.uint8(normalized > threshold) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape
    candidates = [c for c in contours if cv2.contourArea(c) > h * w * .004 and len(c) >= 5]
    if not candidates:
        return None
    contour = max(candidates, key=cv2.contourArea)
    limb_method = "illuminated disk"
    # A clipped moon can sit inside a much wider diffuse halo. The usual low
    # threshold then measures the glow, making the disk artificially shrink
    # during alignment. Prefer a large, compact, nearly circular bright plateau
    # when one exists. Small/jagged bright lunar terrain does not qualify.
    bright = np.uint8(normalized > 230) * 255
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel)
    bright_contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bright_candidates = [c for c in bright_contours if len(c) >= 5 and cv2.contourArea(c) >= cv2.contourArea(contour) * .5]
    if bright_candidates:
        plateau = max(bright_candidates, key=cv2.contourArea)
        (_, _), (axis_a, axis_b), _ = cv2.fitEllipse(plateau)
        plateau_area = cv2.contourArea(plateau)
        perimeter = cv2.arcLength(plateau, True)
        ellipse_area = math.pi * axis_a * axis_b / 4
        compactness = 4 * math.pi * plateau_area / max(perimeter * perimeter, 1)
        if min(axis_a, axis_b) / max(axis_a, axis_b, 1) > .82 and plateau_area / max(ellipse_area, 1) > .9 and compactness > .7:
            contour = plateau
            limb_method = "bright plateau (halo excluded)"
    (cx, cy), (major, minor), _ = cv2.fitEllipse(contour)
    radius = math.sqrt(max(major * minor, 0)) / 2
    if not (3 < radius < max(h, w) * .8) or not (0 <= cx < w and 0 <= cy < h):
        return None
    area = cv2.contourArea(contour)
    circularity = min(1., area / max(math.pi * radius * radius, 1))
    return {"center": (float(cx), float(cy)), "radius": float(radius), "circularity": float(circularity), "limb_method": limb_method}


def _feature_image(image: np.ndarray) -> np.ndarray:
    gray = _luma(image)
    high = max(float(np.percentile(gray, 99.8)), .01)
    mapped = np.log1p(np.maximum(gray, 0) * 10 / high) / np.log(11.)
    mapped = np.uint8(np.clip(mapped, 0, 1) * 255)
    return cv2.createCLAHE(clipLimit=2., tileGridSize=(8, 8)).apply(mapped)


def _feature_mask(shape: tuple, disk: dict | None) -> np.ndarray | None:
    if not disk:
        return None
    mask = np.zeros(shape[:2], dtype=np.uint8)
    # Circular limb aliases do not establish a disk's rotation. Match only
    # interior surface features, with a margin away from that ambiguous edge.
    cv2.circle(mask, tuple(round(v) for v in disk["center"]), round(disk["radius"] * .88), 255, -1)
    return mask


def _surface_features(keypoints, descriptors, disk):
    if descriptors is None or not disk:
        return keypoints, descriptors
    # SIFT can describe the entire uniform disk as a huge central keypoint.
    # Excluding these prevents a featureless circle from implying rotation.
    keep = [i for i, point in enumerate(keypoints) if point.size < disk["radius"] * .35]
    if not keep:
        return [], None
    return [keypoints[i] for i in keep], descriptors[keep]


def _seed_matrix(source, reference, source_shape, reference_shape) -> np.ndarray:
    if source and reference:
        scale = reference["radius"] / source["radius"]
        x = reference["center"][0] - source["center"][0] * scale
        y = reference["center"][1] - source["center"][1] * scale
    else:
        scale = min(reference_shape[1] / source_shape[1], reference_shape[0] / source_shape[0])
        x = (reference_shape[1] - source_shape[1] * scale) / 2
        y = (reference_shape[0] - source_shape[0] * scale) / 2
    return np.float32([[scale, 0, x], [0, scale, y]])


def _warp(image: np.ndarray, matrix: np.ndarray, shape: tuple) -> tuple[np.ndarray, np.ndarray]:
    size = (shape[1], shape[0])
    warped = cv2.warpAffine(image, matrix, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    mask = cv2.warpAffine(np.ones(image.shape[:2], np.float32), matrix, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    return np.clip(warped, 0, 1).astype(np.float32), np.clip(mask, 0, 1).astype(np.float32)


def _frame_mask(frame: ImageFrame) -> np.ndarray:
    if frame.valid_mask is None:
        return np.ones(frame.pixels.shape[:2], np.float32)
    mask = np.asarray(frame.valid_mask, np.float32)
    if mask.shape != frame.pixels.shape[:2] or not np.isfinite(mask).all():
        raise ValueError(f"{frame.name}: invalid pixel mask dimensions or values.")
    return np.clip(mask, 0, 1)


def _warp_frame(frame: ImageFrame, matrix: np.ndarray, shape: tuple) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Warp signal and validity together, excluding missing samples from interpolation."""
    mask = _frame_mask(frame)
    size = (shape[1], shape[0])
    coverage = cv2.warpAffine(mask, matrix, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    def warp_values(values):
        finite_values = np.where(mask[..., None] > 0, values, 0)
        numerator = cv2.warpAffine(finite_values * mask[..., None], matrix, size,
                                   flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        result = numerator / np.maximum(coverage[..., None], 1e-8)
        result[coverage <= 0] = 0
        return result.astype(np.float32)

    display = np.clip(warp_values(_rgb(frame.pixels)), 0, 1)
    linear = None
    if frame.linear_pixels is not None:
        raw = np.asarray(frame.linear_pixels, np.float32)
        if raw.shape != frame.pixels.shape or not np.isfinite(raw[mask > 0]).all():
            raise ValueError(f"{frame.name}: linear signal must match the RGB image and be finite at valid pixels.")
        linear = warp_values(raw)
    return display, np.clip(coverage, 0, 1).astype(np.float32), linear


def _registration(source, reference, source_disk, reference_disk, source_valid=None, reference_valid=None) -> tuple[np.ndarray, dict]:
    seed = _seed_matrix(source_disk, reference_disk, source.shape, reference.shape)
    report = {"method": "disk" if source_disk and reference_disk else "center", "confidence": 0.25 if source_disk and reference_disk else 0., "inliers": 0, "matches": 0, "warning": "Disk-only alignment: lunar texture could not be verified. Inspect the overlay and adjust manually."}
    gray_s, gray_r = _feature_image(source), _feature_image(reference)
    sift = cv2.SIFT_create(nfeatures=6000, contrastThreshold=.012, edgeThreshold=12)
    def feature_mask(image, disk, valid):
        mask = _feature_mask(image.shape, disk)
        if valid is not None:
            valid = cv2.erode(np.uint8(valid > .999) * 255, np.ones((5, 5), np.uint8))
            mask = valid if mask is None else cv2.bitwise_and(mask, valid)
        return mask
    ks, ds = sift.detectAndCompute(gray_s, feature_mask(source, source_disk, source_valid))
    kr, dr = sift.detectAndCompute(gray_r, feature_mask(reference, reference_disk, reference_valid))
    ks, ds = _surface_features(ks, ds, source_disk)
    kr, dr = _surface_features(kr, dr, reference_disk)
    if ds is not None and dr is not None and len(ds) >= 6 and len(dr) >= 6:
        pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(ds, dr, k=2)
        good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .73 * pair[1].distance]
        report["matches"] = len(good)
        if len(good) >= 6:
            src = np.float32([ks[m.queryIdx].pt for m in good])
            dst = np.float32([kr[m.trainIdx].pt for m in good])
            matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.5, maxIters=5000, confidence=.999, refineIters=20)
            if matrix is not None and inliers is not None:
                count = int(inliers.sum())
                scale = float(np.linalg.norm(matrix[0, :2]))
                keep = inliers.ravel().astype(bool)
                residual = np.linalg.norm(cv2.transform(src[:, None, :], matrix).reshape(-1, 2) - dst, axis=1)
                spread = np.ptp(src[keep], axis=0) if count else np.array([0, 0])
                enough_spread = float(np.linalg.norm(spread)) > min(source.shape[:2]) * .12
                reasonable = .1 < scale < 10 and count >= 6 and count / len(good) >= .32 and enough_spread
                if source_disk and reference_disk:
                    projected = matrix[:, :2] @ np.array(source_disk["center"]) + matrix[:, 2]
                    center_error = np.linalg.norm(projected - reference_disk["center"])
                    reasonable &= center_error < reference_disk["radius"] * .3
                if reasonable:
                    report.update(method="SIFT + RANSAC", confidence=float(min(.99, .6 + .3 * count / len(good) + .09 * min(1., count / 50))), inliers=count, residual_px=float(np.median(residual[keep])), warning="")
                    return np.float32(matrix), report
    # Saturated disks retain an edge but not enough distinctive information to
    # determine rotation. Disk fitting is explicitly reported as unverified.
    if not source_disk or not reference_disk:
        report["warning"] = "No reliable lunar disk or texture match. Centered fallback only; manual alignment is required."
    return seed, report


def align_images(frames: list[ImageFrame], reference_index: int = 1, progress: Progress | None = None) -> AlignmentResult:
    if len(frames) < 2:
        raise ValueError("Load at least two exposures to align.")
    if not 0 <= reference_index < len(frames):
        raise ValueError("Invalid reference image index.")
    _progress(progress, 3, "Detecting lunar disks…")
    originals = [_rgb(frame.pixels) for frame in frames]
    small = [_small(image) for image in originals]
    small_masks = [cv2.resize(_frame_mask(frame), (small[index][0].shape[1], small[index][0].shape[0]), interpolation=cv2.INTER_AREA)
                   for index, frame in enumerate(frames)]
    disks = [_detect_disk(image) for image, _ in small]
    reference, reference_ratio = small[reference_index]
    shape = originals[reference_index].shape
    images, masks, matrices, reports, linear_images, metadata = [], [], [], [], [], []
    for index, (source, source_ratio) in enumerate(small):
        _progress(progress, 10 + round(index / len(frames) * 75), f"Matching exposure {index + 1}/{len(frames)}…")
        if index == reference_index:
            matrix = np.float32([[1, 0, 0], [0, 1, 0]])
            report = {"method": "reference", "confidence": 1., "inliers": 0, "matches": 0, "warning": ""}
        else:
            matrix, report = _registration(source, reference, disks[index], disks[reference_index], small_masks[index], small_masks[reference_index])
            matrix[:, :2] *= source_ratio / reference_ratio
            matrix[:, 2] /= reference_ratio
            if "residual_px" in report:
                report["residual_px"] /= reference_ratio
        image, mask, native_linear = _warp_frame(frames[index], matrix, shape)
        report["name"] = frames[index].name
        report["scale"] = float(np.linalg.norm(matrix[0, :2]))
        report["rotation"] = float(math.degrees(math.atan2(matrix[1, 0], matrix[0, 0])))
        report["dx"], report["dy"] = float(matrix[0, 2]), float(matrix[1, 2])
        images.append(image)
        masks.append(mask)
        matrices.append(matrix)
        reports.append(report)
        linear_images.append(native_linear)
        metadata.append({**frames[index].metadata, "exposure_seconds": frames[index].exposure_seconds,
                         "warnings": list(frames[index].warnings), "name": frames[index].name})
    _progress(progress, 100, "Alignment ready")
    return AlignmentResult(images, masks, matrices, reports, reference_index, linear_images, metadata)


def manual_alignment(alignment: AlignmentResult, frames: list[ImageFrame], index: int, dx: float = 0., dy: float = 0., rotation: float = 0., scale: float = 1.) -> AlignmentResult:
    """Apply an absolute correction to the supplied (usually automatic) baseline.

    Positive rotation follows OpenCV's counterclockwise convention, in degrees.
    Positive dx/dy shifts right/down. Pixel shifts use working image resolution.
    """
    if not 0 <= index < len(frames) or len(frames) != len(alignment.images):
        raise ValueError("Invalid image index for manual alignment.")
    if not all(math.isfinite(v) for v in (dx, dy, rotation, scale)) or scale <= 0:
        raise ValueError("Alignment values must be finite and scale positive.")
    h, w = alignment.images[alignment.reference_index].shape[:2]
    correction = cv2.getRotationMatrix2D(((w - 1) / 2, (h - 1) / 2), rotation, scale)
    correction[:, 2] += [dx, dy]
    baseline = np.vstack((alignment.matrices[index], [0, 0, 1]))
    matrix = np.float32(correction @ baseline)
    images, masks = list(alignment.images), list(alignment.masks)
    matrices, reports = list(alignment.matrices), [dict(r) for r in alignment.reports]
    images[index], masks[index], native_linear = _warp_frame(frames[index], matrix, (h, w))
    linear_images = list(alignment.linear_images) if alignment.linear_images is not None else [None] * len(frames)
    linear_images[index] = native_linear
    matrices[index] = matrix
    reports[index].update(
        method="manual correction", manual={"dx": dx, "dy": dy, "rotation": rotation, "scale": scale},
        dx=float(matrix[0, 2]), dy=float(matrix[1, 2]),
        scale=float(np.linalg.norm(matrix[0, :2])),
        rotation=float(math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))),
    )
    metadata = [dict(item) for item in alignment.metadata]
    return AlignmentResult(images, masks, matrices, reports, alignment.reference_index, linear_images, metadata)


def _tone_map(linear: np.ndarray) -> np.ndarray:
    linear = np.maximum(linear, 0)
    luminance = _luma(linear)
    white = max(float(np.percentile(luminance, 99.8)), .0001)
    mapped = np.log1p(luminance * (1.4 / white)) / np.log(2.4) * .90
    color = linear * (mapped / np.maximum(luminance, 1e-8))[..., None]
    return np.clip(_srgb(color), 0, 1).astype(np.float32)


def _fits_unit(value: str) -> tuple[str, bool]:
    unit = "".join(str(value).lower().split())
    unit = unit.replace("seconds", "s").replace("second", "s").replace("sec", "s")
    for notation in ("s**-1", "s^-1", "s-1"):
        unit = unit.replace(notation, "/s")
    is_rate = re.search(r"/s(?:$|[/.*)])", unit) is not None
    return unit, is_rate


def _merge_native_fits(alignment, masks, evs, explicit_evs, warnings, progress) -> Composite:
    """Combine calibrated linear samples without feeding preview stretches back."""
    count = len(alignment.images)
    metadata = alignment.metadata if alignment.metadata else [{} for _ in range(count)]
    if len(metadata) != count:
        raise ValueError("FITS metadata must match the number of aligned exposures.")
    units = [_fits_unit(item.get("bunit", "")) for item in metadata]
    declared_units = {unit for unit, _ in units if unit}
    if len(declared_units) > 1:
        raise ValueError("FITS BUNIT values differ. Convert the exposures to the same physical/count units before a radiance merge, or use display fusion.")
    for unit, is_rate in units:
        count_unit = unit.replace("/s", "") if is_rate else unit
        for pixel_suffix in ("/pixel", "/pixels", "/pix"):
            if count_unit.endswith(pixel_suffix):
                count_unit = count_unit[:-len(pixel_suffix)]
                break
        if count_unit not in ("", "adu", "dn", "count", "counts", "ct", "electron", "electrons", "e-", "photon", "photons"):
            raise ValueError("This FITS BUNIT describes an unsupported calibrated physical unit. Radiance merging supports ADU/DN/count/electron values and their per-second rates; convert units first, or choose display fusion.")
    if any(not unit for unit, _ in units):
        if any(is_rate for _, is_rate in units):
            raise ValueError("Some FITS files use rate units and others have no BUNIT. Add consistent BUNIT metadata before merging their linear signals.")
        warnings.append("Some FITS files have no BUNIT; the merge assumes all files contain compatible native linear counts with the same calibration and gain.")
    rate_data = any(is_rate for _, is_rate in units)
    header_times = [item.get("exposure_seconds") for item in metadata]
    valid_times = [time is not None and math.isfinite(time) and time > 0 for time in header_times]
    calibrated_seconds = False
    if explicit_evs:
        reference_time = header_times[alignment.reference_index]
        if valid_times[alignment.reference_index]:
            times = float(reference_time) * np.exp2(evs.astype(np.float64) - evs[alignment.reference_index])
            calibrated_seconds = True
        else:
            times = np.exp2(evs.astype(np.float64))
    elif all(valid_times):
        times = np.asarray(header_times, np.float64)
        calibrated_seconds = True
    else:
        times = np.ones(count, np.float64)
        warnings.append("Incomplete FITS exposure times: equal exposure is assumed. Enter relative EVs before merging a bracket with different durations.")
    if not np.isfinite(times).all() or (times <= 0).any():
        raise ValueError("FITS exposure durations are outside the supported numeric range.")
    divisors = np.ones(count, np.float64) if rate_data else times
    if rate_data:
        warnings.append("FITS BUNIT already denotes a rate; pixel values are not divided by exposure a second time.")
    elif not calibrated_seconds:
        warnings.append("FITS output uses native linear units relative to EV 0; an absolute count-per-second scale could not be established.")
    shape = alignment.images[0].shape
    signal_sum = np.zeros(shape, np.float64)
    weight_sum = np.zeros(shape[:2], np.float64)
    fallback = np.zeros(shape, np.float64)
    best_quality = np.full(shape[:2], -np.inf, np.float64)
    clipped_everywhere = np.ones(shape[:2], bool)
    any_valid = np.zeros(shape[:2], bool)
    # For count-rate estimates, duration weights favor higher photon statistics.
    # This is not a detector-noise/variance model; no gain is inferred from data.
    exposure_weights = times / np.max(times)
    for index, (raw, mask, divisor, time_weight, item) in enumerate(zip(alignment.linear_images, masks, divisors, exposure_weights, metadata)):
        _progress(progress, 10 + round(index / count * 70), f"Combining linear FITS exposure {index + 1}/{count}…")
        raw = np.asarray(raw, np.float32)
        if raw.shape != shape or not np.isfinite(raw[mask > 0]).all():
            raise ValueError("FITS linear images must match the aligned image dimensions and be finite at valid pixels.")
        valid = mask > 0
        clean = np.where(valid[..., None], raw, 0)
        estimate = clean.astype(np.float64) / divisor
        saturation = item.get("saturation_level")
        clipped = np.zeros(shape[:2], bool)
        highlight_weight = np.ones(shape[:2], np.float32)
        if saturation is not None and math.isfinite(saturation) and saturation > 0:
            peak = clean.max(axis=2).astype(np.float64)
            clipped = peak >= saturation * (1 - 1e-7)
            highlight_weight = np.clip((saturation - peak) / (saturation * .08), 0, 1)
        weight = time_weight * highlight_weight * mask
        signal_sum += estimate * weight[..., None]
        weight_sum += weight
        quality = np.where(clipped, -1e6 - math.log2(float(times[index])), float(time_weight))
        quality = np.where(valid, quality, -np.inf)
        take = quality > best_quality
        fallback[take] = estimate[take]
        best_quality[take] = quality[take]
        any_valid |= valid
        clipped_everywhere &= clipped | ~valid
    linear = np.where((weight_sum > 1e-12)[..., None], signal_sum / np.maximum(weight_sum[..., None], 1e-12), fallback)
    linear[~any_valid] = 0
    if not np.isfinite(linear).all() or np.max(np.abs(linear)) > np.finfo(np.float32).max:
        raise ValueError("Merged FITS signal exceeds float32 range. Rescale every input by the same factor before importing.")
    negative_count = int(np.count_nonzero(np.any(linear < 0, axis=2)))
    if negative_count:
        warnings.append(f"{negative_count:,} merged FITS pixels contain negative calibrated background; negative channels are clipped only in the final HDR/display output for Radiance RGBE compatibility. Native input samples are retained.")
    linear = np.maximum(linear, 0).astype(np.float32)
    clipped_count = int(np.count_nonzero(clipped_everywhere & any_valid))
    if clipped_count:
        warnings.append(f"{clipped_count:,} pixels are saturated in every available FITS exposure; original highlight detail cannot be recovered.")
    missing_count = int(np.count_nonzero(~any_valid))
    if missing_count:
        warnings.append(f"{missing_count:,} output pixels have no valid FITS sample and are displayed as black.")
    _progress(progress, 90, "Tone mapping merged FITS signal…")
    base = _tone_map(linear)
    _progress(progress, 100, "FITS HDR composite ready")
    return Composite(base, linear, "radiance", warnings)


def merge_hdr(alignment: AlignmentResult, evs=None, mode: str = "radiance", progress: Progress | None = None) -> Composite:
    """Merge relative linear radiance, or multiresolution exposure fusion.

    EVs describe exposure, not brightness correction: +2 received four times the
    exposure of EV 0. With evs=None, sRGB images use equal exposure; FITS use
    complete EXPTIME metadata. FITS never pass through an assumed sRGB response.
    Explicit FITS EVs are anchored to the reference's EXPTIME when available.
    Fusion creates a display image, not recoverable HDR data.
    """
    count = len(alignment.images)
    explicit_evs = evs is not None
    evs = np.zeros(count, np.float32) if evs is None else np.asarray(evs, dtype=np.float32)
    if count < 2 or evs.ndim != 1 or len(evs) != count or len(alignment.masks) != count:
        raise ValueError("Provide one EV value and valid mask for each exposure.")
    if not 0 <= alignment.reference_index < count:
        raise ValueError("Invalid reference image index.")
    if not np.isfinite(evs).all() or np.max(np.abs(evs)) > 20:
        raise ValueError("Exposure EV values must be finite and within −20…20.")
    if mode not in ("radiance", "fusion"):
        raise ValueError("Merge mode must be 'radiance' or 'fusion'.")
    images = [_rgb(image) for image in alignment.images]
    shape = images[0].shape
    if any(image.shape != shape for image in images):
        raise ValueError("Aligned image dimensions must match.")
    masks = [np.asarray(mask, np.float32) for mask in alignment.masks]
    if any(mask.shape != shape[:2] or not np.isfinite(mask).all() for mask in masks):
        raise ValueError("Alignment masks must match the image dimensions and be finite.")
    masks = [np.clip(mask, 0, 1) for mask in masks]
    warnings = [f"{r.get('name', 'Exposure')}: {r['warning']}" for r in alignment.reports if r.get("warning")]
    for item in alignment.metadata:
        warnings.extend(f"{item.get('name', 'FITS')}: {message}" for message in item.get("warnings", []))
    native = alignment.linear_images or [None] * count
    if len(native) != count:
        raise ValueError("Native linear images must match the number of aligned exposures.")
    has_native = [image is not None for image in native]
    _progress(progress, 5, "Combining exposures…")
    if mode == "fusion":
        reference = images[alignment.reference_index]
        if any(has_native):
            warnings.append("FITS display fusion combines independently stretched previews. It is a visual composite and does not preserve native linear counts.")
        clipped_masks = []
        for index, image in enumerate(images):
            if has_native[index]:
                item = alignment.metadata[index] if index < len(alignment.metadata) else {}
                saturation = item.get("saturation_level")
                clipped = np.zeros(shape[:2], bool)
                if saturation is not None and math.isfinite(saturation) and saturation > 0:
                    clipped = np.max(native[index], axis=2) >= saturation * (1 - 1e-7)
            else:
                clipped = image.max(axis=2) >= .998
            clipped_masks.append(clipped)
        # A clipped white plateau still influences the low-frequency Mertens
        # pyramid, even when its local contrast is zero. Replace proven clipped
        # samples with a valid other exposure before constructing that pyramid.
        # Prefer the selected reference; never substitute when every input is
        # clipped or missing at that pixel.
        replacement = np.zeros(shape, np.float32)
        replacement_valid = np.zeros(shape[:2], bool)
        fallback = reference.copy()
        fallback_valid = masks[alignment.reference_index] > .999
        order = [alignment.reference_index] + [index for index in range(count) if index != alignment.reference_index]
        for index in order:
            valid = masks[index] > .999
            take = valid & ~clipped_masks[index] & ~replacement_valid
            replacement[take] = images[index][take]
            replacement_valid |= take
            fill = valid & ~fallback_valid
            fallback[fill] = images[index][fill]
            fallback_valid |= fill
        any_valid = np.maximum.reduce(masks) > .999
        all_clipped = np.logical_and.reduce([clip | (mask <= .999) for clip, mask in zip(clipped_masks, masks)]) & any_valid
        if np.any(all_clipped):
            warnings.append(f"{np.count_nonzero(all_clipped):,} pixels are saturated/clipped in every available exposure; fusion cannot recover their highlight detail.")
        prepared = []
        for image, mask, clipped in zip(images, masks, clipped_masks):
            repair = np.uint8(clipped & replacement_valid)
            if np.any(repair):
                repair = cv2.dilate(repair, np.ones((3, 3), np.uint8))
                feather = cv2.GaussianBlur(repair.astype(np.float32), (0, 0), 1.2)
                feather *= replacement_valid
                image = image * (1 - feather[..., None]) + replacement * feather[..., None]
            blend = mask
            if np.any(mask < .999):
                # Smooth the source's finite field-of-view boundary into the
                # reference instead of introducing a bright rectangular edge.
                distance = cv2.distanceTransform(np.uint8(mask > .999), cv2.DIST_L2, 5)
                blend = mask * np.clip(distance / max(12., min(shape[:2]) * .025), 0, 1)
            filled = image * blend[..., None] + fallback * (1 - blend[..., None])
            prepared.append(np.uint8(np.round(filled[..., ::-1] * 255)))
        fused = cv2.createMergeMertens(1., 1., 1.).process(prepared)[..., ::-1]
        # Low-frequency halo energy can still lift the repaired disk through
        # the coarsest pyramid levels. Protect detail wherever saturation is
        # proven by restoring the selected valid exposure with a soft seam.
        # The surrounding unsaturated halo continues to use exposure fusion.
        protect = np.logical_or.reduce([clip & (mask > .999) for clip, mask in zip(clipped_masks, masks)]) & replacement_valid
        if np.any(protect):
            protect = cv2.dilate(protect.astype(np.uint8), np.ones((3, 3), np.uint8))
            feather = cv2.GaussianBlur(protect.astype(np.float32), (0, 0), 2.)
            feather *= replacement_valid
            fused = fused * (1 - feather[..., None]) + replacement * feather[..., None]
        _progress(progress, 100, "Exposure fusion ready")
        return Composite(np.clip(fused, 0, 1).astype(np.float32), None, mode, warnings)
    if any(has_native):
        if not all(has_native):
            raise ValueError("FITS linear counts and sRGB images use incompatible signal scales. Merge them in separate radiance batches, or choose display fusion.")
        return _merge_native_fits(alignment, masks, evs, explicit_evs, warnings, progress)
    radiance_sum = np.zeros(shape, np.float32)
    weight_sum = np.zeros(shape[:2], np.float32)
    fallback = np.zeros(shape, np.float32)
    best_quality = np.full(shape[:2], -np.inf, np.float32)
    clipping_everywhere = np.ones(shape[:2], dtype=bool)
    for index, (image, mask, ev) in enumerate(zip(images, masks, evs)):
        _progress(progress, 10 + round(index / count * 70), f"Recovering exposure {index + 1}/{count}…")
        maximum = image.max(axis=2)
        luminance = _luma(image)
        linear = _linear(image) / float(2. ** ev)
        # Reject clipped channels together to prevent saturated highlights from
        # changing hue. Reject noise near black; never include warped padding.
        exposure_weight = np.exp(-.5 * ((luminance - .48) / .25) ** 2)
        bright_weight = np.clip((.998 - maximum) / .07, 0, 1)
        dark_weight = np.clip(luminance / .025, 0, 1)
        weight = exposure_weight * bright_weight * dark_weight * mask
        radiance_sum += linear * weight[..., None]
        weight_sum += weight
        quality = -np.abs(luminance - .45)
        quality -= np.where(maximum >= .998, 2. + float(ev - evs.min()) * .01, 0.)
        quality = np.where(mask > .999, quality, -10.)
        take = quality > best_quality
        fallback[take] = linear[take]
        best_quality[take] = quality[take]
        clipping_everywhere &= (maximum >= .998) | (mask < .999)
    linear = np.where((weight_sum > 1e-8)[..., None], radiance_sum / np.maximum(weight_sum[..., None], 1e-8), fallback)
    linear[best_quality <= -10] = 0
    valid = np.maximum.reduce(masks) > .999
    clipped = int(np.count_nonzero(clipping_everywhere & valid))
    if clipped:
        warnings.append(f"{clipped:,} pixels are clipped in every available exposure; their original highlight detail cannot be recovered.")
    _progress(progress, 90, "Tone mapping lunar detail…")
    base = _tone_map(linear)
    _progress(progress, 100, "HDR composite ready")
    return Composite(base, linear.astype(np.float32), mode, warnings)


def adjust_image(base: np.ndarray, settings: dict) -> np.ndarray:
    """Render a fresh preview from an unchanged display-referred base image."""
    image = _rgb(base).copy()
    values = {key: float(value) for key, value in settings.items()}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError("Adjustment values must be finite.")
    def value(key, default=0., low=-100., high=100.):
        return float(np.clip(values.get(key, default), low, high))
    white_balance = value("white_balance", low=0) / 100
    if white_balance and not (np.array_equal(image[..., 0], image[..., 1]) and np.array_equal(image[..., 1], image[..., 2])):
        # Estimate the common lunar color cast from useful surface pixels,
        # avoiding black sky, clipped highlights and missing color channels.
        # A single set of gains preserves spatial color differences; it does
        # not assign colors to individual lunar regions.
        display_luma = _luma(image)
        bright_level = max(.05, float(np.percentile(display_luma, 99)) * .35)
        useful = (display_luma > bright_level) & (image.max(axis=2) < .985) & (image.min(axis=2) > .008)
        disk_image, disk_ratio = _small(image, limit=1000)
        disk = _detect_disk(disk_image)
        if disk:
            surface = np.zeros(image.shape[:2], np.uint8)
            center = tuple(round(coordinate / disk_ratio) for coordinate in disk["center"])
            cv2.circle(surface, center, round(disk["radius"] * .85 / disk_ratio), 1, -1)
            useful &= surface.astype(bool)
        if np.count_nonzero(useful) >= 32:
            linear = _linear(image)
            channel_medians = np.median(linear[useful], axis=0)
            neutral_level = float(_luma(channel_medians))
            gains = np.clip(neutral_level / np.maximum(channel_medians, 1e-7), .25, 4.)
            gains = 1 + white_balance * (gains - 1)
            balanced = linear * gains
            luminance = _luma(linear)
            balanced *= (luminance / np.maximum(_luma(balanced), 1e-8))[..., None]
            image = np.clip(_srgb(balanced), 0, 1)
    exposure = value("exposure", low=-6, high=6)
    if exposure:
        image = _srgb(_linear(image) * 2. ** exposure)
    temperature = value("temperature") / 100
    if temperature:
        image *= np.float32([1 + .16 * temperature, 1 + .025 * temperature, 1 - .16 * temperature])
    luminance = np.clip(_luma(image), 0, 1)
    shadows, highlights = value("shadows") / 100, value("highlights") / 100
    if shadows or highlights:
        shadow_mask = (1 - luminance) ** 3
        highlight_mask = luminance ** 3
        target = luminance + shadows * .35 * shadow_mask * np.sqrt(luminance)
        target += highlights * .32 * highlight_mask
        image *= (np.maximum(target, 0) / np.maximum(luminance, 1e-6))[..., None]
    contrast = value("contrast") / 100
    if contrast:
        image = (image - .5) * (2 ** (contrast * 1.35)) + .5
    image = np.clip(image, 0, 1)
    # Lab chroma amplification reveals existing weak lunar color; it does not
    # assign fabricated mineral labels or infer chemical composition.
    saturation = value("saturation", default=100., low=0, high=200) / 100
    mineral = value("mineral", low=0) / 100
    if saturation != 1 or mineral:
        lab = cv2.cvtColor(image.astype(np.float32), cv2.COLOR_RGB2Lab)
        if mineral:
            # Suppress color speckles before amplifying the chroma only.
            a = cv2.GaussianBlur(lab[..., 1], (0, 0), .65 + mineral)
            b = cv2.GaussianBlur(lab[..., 2], (0, 0), .65 + mineral)
            lab[..., 1] = a
            lab[..., 2] = b
        lab[..., 1:] *= saturation * (1 + mineral * 3.)
        image = np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB), 0, 1)
    denoise = value("denoise", low=0) / 100
    if denoise:
        filtered = cv2.bilateralFilter(image.astype(np.float32), 5, .025 + .10 * denoise, 2.5)
        image = image * (1 - denoise) + filtered * denoise
    clarity = value("clarity", low=0) / 100
    if clarity:
        sigma = max(2., min(image.shape[:2]) / 180)
        blurred = cv2.GaussianBlur(image, (0, 0), sigma)
        image += (image - blurred) * clarity * 1.25
    sharpness = value("sharpness", low=0) / 100
    if sharpness:
        blurred = cv2.GaussianBlur(image, (0, 0), .8)
        detail = image - blurred
        gate = np.clip(np.abs(detail) / .008, 0, 1)
        image += detail * gate * sharpness * 1.6
    return np.ascontiguousarray(np.clip(image, 0, 1), dtype=np.float32)


def write_image(path: str, pixels: np.ndarray, linear_hdr: np.ndarray | None = None) -> None:
    """Save PNG/JPEG (8 bit), TIFF (16-bit sRGB), or Radiance .hdr (linear).

    The HDR export represents the merged data before display-only adjustments.
    RGBE uses a shared exponent; it is HDR, not lossless float32 storage.
    """
    target = Path(path).expanduser()
    suffix = target.suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".hdr"):
        raise ValueError("Export as PNG, JPG, 16-bit TIFF, or linear Radiance HDR.")
    image = _rgb(pixels)
    if suffix == ".hdr":
        if linear_hdr is None:
            raise ValueError("Linear HDR export requires a radiance merge; fusion has no linear HDR data.")
        linear_hdr = np.asarray(linear_hdr, np.float32)
        if linear_hdr.shape != image.shape or not np.isfinite(linear_hdr).all() or (linear_hdr < 0).any():
            raise ValueError("Linear HDR data must be finite, nonnegative RGB matching the composite.")
        success, data = cv2.imencode(".hdr", np.ascontiguousarray(linear_hdr[..., ::-1]))
        if not success:
            raise OSError("Could not encode HDR image.")
        data.tofile(target)
    elif suffix in (".tif", ".tiff"):
        tifffile.imwrite(target, np.uint16(np.round(image * 65535)), photometric="rgb", metadata={"ColorSpace": "sRGB", "Software": "Lunar HDR"})
    else:
        output = Image.fromarray(np.uint8(np.round(image * 255)), mode="RGB")
        output.save(target, **({"quality": 97, "subsampling": 0} if suffix in (".jpg", ".jpeg") else {}))
