"""The public demo must be reproducible and independent of private imagery."""
import numpy as np
import pytest

from lunarhdr.publicdemo import synthetic_moon


def test_public_demo_is_deterministic_finite_and_has_lunar_texture():
    first = synthetic_moon(size=256, seed=271828)
    second = synthetic_moon(size=256, seed=271828)
    np.testing.assert_array_equal(first, second)
    assert first.shape == (256, 256, 3)
    assert first.dtype == np.float32
    assert np.isfinite(first).all()
    assert 0 <= first.min() < first.max() <= 1
    assert float(np.std(first[80:170, 80:170])) > .015
    assert float(np.mean(first[100:155, 100:155])) > float(np.mean(first[10:30, 120:170])) * 5
    assert not np.array_equal(first, synthetic_moon(size=256, seed=271829))


def test_public_demo_rejects_unusable_sizes():
    with pytest.raises(ValueError):
        synthetic_moon(size=32)
