"""Deterministic, original lunar-style test artwork for the public demo.

This is a mathematical scene, not a photograph or a map of the actual Moon.
No external image, user file, or network resource contributes to its pixels.
Regenerate the bundled asset with ``python -m lunarhdr.publicdemo``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def synthetic_moon(size: int = 1000, seed: int = 271828) -> np.ndarray:
    """Return labeled RGB sRGB pixels in [0, 1], generated solely from a seed."""
    if size < 128 or size > 4096:
        raise ValueError("Demo size must be between 128 and 4096 pixels.")
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[:size, :size].astype(np.float32)
    radius = size * .385
    x, y = (xx - size / 2) / radius, (yy - size * .49) / radius
    distance = np.hypot(x, y)
    z = np.sqrt(np.maximum(1 - distance**2, 0))

    relief = np.zeros((size, size), np.float32)
    for grid_size, amplitude in ((9, .055), (24, .032), (75, .022), (180, .012)):
        grid = rng.random((grid_size, grid_size), dtype=np.float32) - .5
        relief += cv2.resize(grid, (size, size), interpolation=cv2.INTER_CUBIC) * amplitude
    albedo = .43 + relief
    maria = np.zeros_like(albedo)
    # Invented basalt-like regions: intentionally no actual lunar geography.
    basins = [(-.44, -.38, .25, .30), (-.10, -.52, .25, .20),
              (.27, -.34, .22, .30), (-.40, -.02, .28, .24),
              (-.06, .07, .29, .25), (.29, .18, .24, .17)]
    for cx, cy, rx, ry in basins:
        elliptical = ((x-cx)/rx)**2 + ((y-cy)/ry)**2
        maria += .11 * np.exp(-elliptical * 1.8)
    albedo -= maria

    for _ in range(180):
        angle = rng.uniform(0, 2*np.pi)
        r_center = np.sqrt(rng.uniform(0, .90**2))
        cx = size/2 + np.cos(angle)*r_center*radius
        cy = size*.49 + np.sin(angle)*r_center*radius
        crater_radius = float(rng.uniform(.004, .038) * radius)
        reach = max(3, int(np.ceil(crater_radius * 1.7)))
        x0, x1 = max(0, int(cx)-reach), min(size, int(cx)+reach+1)
        y0, y1 = max(0, int(cy)-reach), min(size, int(cy)+reach+1)
        dx, dy = xx[y0:y1, x0:x1]-cx, yy[y0:y1, x0:x1]-cy
        radial = np.hypot(dx, dy) / crater_radius
        bowl = -.047*np.exp(-(radial/.66)**4)
        rim = .056*np.exp(-((radial-1)/.17)**2)
        directional = np.clip((-dx-dy)/(crater_radius*1.5), -1, 1)
        albedo[y0:y1, x0:x1] += bowl + rim*(1 + directional*.75)

    light = np.maximum(.24*(-x) + .30*(-y) + .92*z, 0)
    # Keep texture below clipping even in the demonstration's +2 EV frame.
    luminance = np.clip(albedo * (.42 + .58*light), .012, .75) * .45
    chroma = np.sin(x*4.7 + y*2.3)*np.cos(y*5.1 - x*1.2)
    moon = np.stack((luminance*(1 + .033*chroma), luminance,
                     luminance*(1 - .043*chroma)), axis=-1)
    # A restrained artificial sky keeps alignment focused on lunar texture.
    linear = np.full((size, size, 3), .0010, np.float32)
    limb = np.clip((1-distance)*radius + .5, 0, 1)[..., None]
    linear = linear*(1-limb) + moon*limb
    for _ in range(110):
        sx, sy = rng.integers(8, size-8, size=2)
        if distance[sy, sx] > 1.12:
            brightness = float(rng.uniform(.04, .21))
            cv2.circle(linear, (int(sx), int(sy)), max(1, size//900),
                       (brightness, brightness, brightness), -1)
    display = np.where(linear <= .0031308, linear*12.92,
                       1.055*np.maximum(linear, 0)**(1/2.4)-.055)
    display = np.ascontiguousarray(np.round(np.clip(display, 0, 1)*255), dtype=np.uint8)
    scale = max(.29, size/1700)
    cv2.putText(display, "SYNTHETIC DEMO", (int(size*.035), int(size*.05)),
                cv2.FONT_HERSHEY_SIMPLEX, scale, (120, 148, 150), 1, cv2.LINE_AA)
    if size >= 400:
        cv2.putText(display, "PROCEDURAL TEST PATTERN - NOT OBSERVATIONAL DATA",
                    (int(size*.035), int(size*.965)), cv2.FONT_HERSHEY_SIMPLEX,
                    scale*.65, (102, 122, 125), 1, cv2.LINE_AA)
    return display.astype(np.float32)/255


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent / "assets" / "demo_reference.png")
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=271828)
    args = parser.parse_args()
    pixels = np.uint8(np.round(synthetic_moon(args.size, args.seed) * 255))
    success, encoded = cv2.imencode(".png", pixels[..., ::-1])
    if not success:
        raise OSError("Could not encode the synthetic demo image.")
    encoded.tofile(args.output)


if __name__ == "__main__":
    main()
