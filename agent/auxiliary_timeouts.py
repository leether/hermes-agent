"""Profile-configured auxiliary request ceilings without weakening upstream defaults."""
from __future__ import annotations

import math
from typing import Any


def configured_timeout(config: dict[str, Any], default: float) -> float:
    raw = config.get("timeout")
    if raw is not None:
        try:
            return float(raw)
        except (ValueError, TypeError):
            pass
    return default


def bounded_timeout(effective: float, config: dict[str, Any]) -> float:
    """An explicit positive finite max_timeout caps the resolved request, including per-call overrides."""
    raw = config.get("max_timeout")
    if raw is None:
        return effective
    try:
        bound = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("auxiliary max_timeout must be a positive finite number") from exc
    if isinstance(raw, bool) or not math.isfinite(bound) or bound <= 0:
        raise ValueError("auxiliary max_timeout must be a positive finite number")
    return min(effective, bound)
