"""FITS input with a strict separation between detector signal and preview.

Astropy applies BSCALE/BZERO and integer BLANK semantics. No per-frame offset or
normalization is ever applied to the returned ``linear_pixels``. The separately
stretched ``pixels`` array is for registration and display only.
"""
from __future__ import annotations

from pathlib import Path
import math

import cv2
import numpy as np


FITS_SUFFIXES = (".fits", ".fit", ".fts", ".fits.gz", ".fit.gz", ".fts.gz", ".fits.fz", ".fit.fz", ".fts.fz")


def is_fits_path(path: str | Path) -> bool:
    return str(path).lower().endswith(FITS_SUFFIXES)


def _number(header, key):
    try:
        value = float(header[key])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _preview(linear: np.ndarray, valid: np.ndarray) -> np.ndarray:
    sample = linear[valid > 0]
    if not sample.size:
        raise ValueError("FITS image contains no finite, valid pixels.")
    # One common channel scale preserves the relative RGB color. Negative
    # calibrated background is clipped for display, never subtracted from data.
    white = max(float(np.percentile(sample, 99.8)), 0.)
    if white <= 0:
        return np.zeros_like(linear, dtype=np.float32)
    normalized = np.maximum(linear, 0) / white
    display_linear = np.log1p(normalized * 1.4) / np.log(2.4) * .90
    display = np.where(display_linear <= .0031308, display_linear * 12.92,
                       1.055 * display_linear ** (1 / 2.4) - .055)
    display *= valid[..., None] > 0
    return np.ascontiguousarray(np.clip(display, 0, 1), dtype=np.float32)


def read_fits(path: str | Path, max_dimension: int | None = None) -> dict:
    """Return keyword arguments for engine.ImageFrame, retaining FITS units."""
    try:
        from astropy.io import fits
    except ImportError as exc:
        raise ValueError("FITS support requires Astropy. Install the application's updated requirements.") from exc

    source = Path(path)
    messages = []
    try:
        with fits.open(source, memmap=False, uint=True, ignore_blank=False) as hdus:
            primary_header = hdus[0].header.copy()
            selected = None
            for index, hdu in enumerate(hdus):
                if isinstance(hdu, (fits.PrimaryHDU, fits.ImageHDU, fits.CompImageHDU)) and int(hdu.header.get("NAXIS", 0)) > 0:
                    selected = (index, hdu)
                    break
            if selected is None:
                raise ValueError("FITS file has no image HDU; table-only files are unsupported.")
            index, hdu = selected
            # Save original storage cards before .data access changes scaled
            # image headers to their in-memory floating-point representation.
            original = hdu.header.copy()
            header = primary_header.copy()
            header.update(original)
            bitpix = int(original.get("BITPIX", 0))
            bscale = _number(original, "BSCALE")
            bzero = _number(original, "BZERO")
            bscale = 1. if bscale is None else bscale
            bzero = 0. if bzero is None else bzero
            data = np.array(hdu.data, copy=True)
    except (OSError, ValueError, TypeError, IndexError) as exc:
        raise ValueError(f"Cannot read FITS {source.name}: {exc}") from exc

    cfa_metadata = []
    for key in ("BAYERPAT", "BAYERPATN", "BAYER", "CFAPAT", "CFAPATTERN", "COLORTYP"):
        token = str(header.get(key, "")).strip().upper()
        if token and token not in ("NONE", "FALSE", "NO", "MONO", "MONOCHROME", "RGB", "RGBA"):
            cfa_metadata.append(f"{key}={token}")
    if data.ndim == 2:
        if cfa_metadata:
            raise ValueError(f"{source.name} contains 2D Bayer/CFA data ({', '.join(cfa_metadata)}). Debayer it to RGB or export a monochrome FITS before importing.")
        data = np.repeat(data[..., None], 3, axis=2)
        monochrome = True
    elif data.ndim == 3:
        if data.shape[0] == 3 and data.shape[-1] != 3:
            color_axis = 3  # FITS axis numbering is reverse of NumPy's.
            data = np.moveaxis(data, 0, -1)
        elif data.shape[-1] == 3 and data.shape[0] != 3:
            color_axis = 1
        else:
            raise ValueError("Unsupported or ambiguous FITS cube. Import a 2D monochrome image or a 3 × H × W / H × W × 3 RGB image.")
        axis_type = str(header.get(f"CTYPE{color_axis}", "")).strip().upper()
        if axis_type and axis_type not in ("RGB", "COLOR", "COLOUR", "CHANNEL"):
            raise ValueError(f"FITS axis {color_axis} is {axis_type}, not RGB. Spectral, time and polarization cubes must be exported as separate 2D images.")
        if cfa_metadata:
            # Some camera exporters retain sensor CFA cards after producing
            # three full-resolution color planes (for example DWARF RGB FITS).
            # The actual array layout takes precedence over those stale cards;
            # axis declarations above still reject scientific/non-color cubes.
            messages.append(f"Bayer/CFA sensor metadata ({', '.join(cfa_metadata)}) is present on a three-channel image. Its planes are treated as already demosaiced RGB; they are not debayered again.")
        rgb_declared = axis_type in ("RGB", "COLOR", "COLOUR", "CHANNEL") or str(header.get("COLORTYP", "")).upper() == "RGB"
        if not rgb_declared:
            messages.append("Three FITS planes are interpreted in R, G, B order; no color-axis declaration is present. Export spectral/time cubes as separate images.")
        monochrome = False
    else:
        raise ValueError("Unsupported FITS dimensions. Use a 2D monochrome image or three-channel RGB image; export cube slices separately.")
    if min(data.shape[:2]) < 2:
        raise ValueError("FITS image must have at least 2 × 2 pixels.")
    if data.dtype.kind not in "uif":
        raise ValueError("Unsupported FITS pixel type; use real integer or floating-point image data.")
    finite = np.isfinite(data).all(axis=2)
    # Astropy's uint=True fast path for pseudo-unsigned integer FITS does not
    # always replace BLANK with NaN. BLANK is stored in unscaled integer units.
    blank = _number(original, "BLANK") if bitpix > 0 else None
    if blank is not None:
        physical_blank = np.asarray(blank * bscale + bzero, dtype=data.dtype)
        finite &= ~(data == physical_blank).any(axis=2)
    float_limit = np.finfo(np.float32).max
    magnitude = np.abs(data.astype(np.float64))
    smallest = float(np.nextafter(np.float32(0), np.float32(1)))
    finite &= ((magnitude <= float_limit) & ((magnitude == 0) | (magnitude >= smallest))).all(axis=2)
    invalid_count = int(finite.size - np.count_nonzero(finite))
    if not finite.any():
        raise ValueError("FITS image contains no finite, valid pixels.")
    if invalid_count:
        messages.append(f"{invalid_count:,} FITS pixels are BLANK, non-finite or outside float32 range and will be excluded from the merge.")
    linear = np.asarray(np.where(finite[..., None], data, 0), dtype=np.float32)
    valid = finite.astype(np.float32)

    exposure = None
    for key in ("EXPTIME", "EXPOSURE"):
        candidate = _number(header, key)
        if candidate is not None and candidate > 0:
            exposure = candidate
            break
    if exposure is None:
        messages.append("FITS has no positive EXPTIME/EXPOSURE in seconds; enter relative EV values to describe its exposure.")
    saturation = None
    saturation_source = None
    for key in ("SATURATE", "SATLEVEL", "SATURLEV"):
        candidate = _number(header, key)
        if candidate is not None and candidate > 0:
            saturation, saturation_source = candidate, key
            break
    if saturation is None and bitpix > 0:
        # FITS BITPIX 8 is unsigned; larger positive BITPIX values are signed
        # storage. BZERO commonly maps signed16 storage to unsigned ADU.
        minimum = 0 if bitpix == 8 else -(2 ** (bitpix - 1))
        maximum = 255 if bitpix == 8 else 2 ** (bitpix - 1) - 1
        saturation = max(minimum * bscale + bzero, maximum * bscale + bzero)
        if saturation > 0 and math.isfinite(saturation):
            saturation_source = "integer storage ceiling"
        else:
            saturation = None
    if saturation is None:
        messages.append("No detector saturation level is recorded in this floating-point FITS; finite maxima are retained, not assumed clipped.")

    height, width = linear.shape[:2]
    if max_dimension is not None and max(height, width) > max_dimension:
        ratio = max_dimension / max(height, width)
        size = (max(2, round(width * ratio)), max(2, round(height * ratio)))
        coverage = cv2.resize(valid, size, interpolation=cv2.INTER_AREA)
        weighted = cv2.resize(linear * valid[..., None], size, interpolation=cv2.INTER_AREA)
        linear = np.divide(weighted, np.maximum(coverage[..., None], 1e-8)).astype(np.float32)
        linear[coverage <= 0] = 0
        valid = coverage.astype(np.float32)
    bunit = str(header.get("BUNIT", "")).strip()
    metadata = {
        "source_format": "fits", "monochrome": monochrome,
        "hdu_index": index, "hdu_name": str(header.get("EXTNAME", "PRIMARY" if index == 0 else "IMAGE")),
        "bunit": bunit, "saturation_level": saturation,
        "saturation_source": saturation_source, "original_bitpix": bitpix,
        "bscale": bscale, "bzero": bzero,
        "preview_stretch": "independent display stretch; raw linear signal preserved",
    }
    return dict(path=str(source.resolve()), name=source.name, pixels=_preview(linear, valid),
                bit_depth=abs(bitpix), linear_pixels=np.ascontiguousarray(linear),
                valid_mask=np.ascontiguousarray(valid), exposure_seconds=exposure,
                warnings=messages, metadata=metadata)
