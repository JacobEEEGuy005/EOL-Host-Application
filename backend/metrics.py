"""Lightweight in-memory metrics counter used by adapters and API endpoints.

This is intentionally simple and process-local. It exposes inc/get functions
so components can increment counters without pulling in heavy deps.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict

_c = Counter()


def inc(name: str, n: int = 1) -> None:
    _c[name] += n


def get_all() -> Dict[str, int]:
    return dict(_c)


def reset_all() -> None:
    _c.clear()
