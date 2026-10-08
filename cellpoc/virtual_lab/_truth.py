"""The hidden "true" behaviour of the tablet. PRIVATE to the virtual lab.

Nothing outside cellpoc/virtual_lab may import this file: the decision engine must
discover the behaviour by experiment, exactly as it would with a real lab. The
numbers below are an illustrative placeholder, to be replaced by a client's real
model (or real instruments).
"""
from __future__ import annotations

from ..contracts import Formulation

# Centre and half-width of each ingredient's range in the illustrative design space.
# Ingredients are rescaled to roughly -1 ... +1 so the formulas below stay readable.
_CENTRE = {"drug": 20.0, "filler": 55.0, "binder": 4.0, "disintegrant": 4.5, "lubricant": 1.125}
_HALF = {"drug": 10.0, "filler": 15.0, "binder": 2.0, "disintegrant": 3.5, "lubricant": 0.875}


def _scaled(formulation: Formulation) -> tuple[float, float, float, float, float]:
    v = formulation.as_dict()
    return tuple((v[k] - _CENTRE[k]) / _HALF[k] for k in _CENTRE)  # type: ignore[return-value]


def true_dissolution_pct(formulation: Formulation, offset: float = 0.0) -> float:
    """Dissolution at 30 minutes, with no measurement noise.

    `offset` shifts the whole dissolution surface up or down. It exists only so the same
    truth can be made easier or harder (more or fewer recipes truly good) for sensitivity runs.
    """
    d, f, b, s, l = _scaled(formulation)
    value = (73.5 + offset
             + 9.0 * s - 3.0 * s * s      # disintegrant helps, with diminishing returns
             - 7.0 * b                     # binder slows release
             - 5.0 * l                     # lubricant is water-repellent
             - 4.0 * d                     # more drug, slower dissolving
             + 2.0 * f
             + 2.5 * s * b)                # disintegrant partly offsets binder
    return min(100.0, max(0.0, value))


def true_hardness_kp(formulation: Formulation) -> float:
    """Tablet hardness in kP, with no measurement noise."""
    d, f, b, s, l = _scaled(formulation)
    value = (8.0
             + 2.2 * b - 0.5 * b * b       # binder strengthens, with diminishing returns
             + 1.2 * f
             + 0.4 * b * f
             - 1.5 * l                     # lubricant weakens the compact
             - 0.8 * s
             - 0.6 * d)
    return max(0.0, value)
