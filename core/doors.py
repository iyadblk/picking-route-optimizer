"""Anti-cold-leak door detection and time-penalty model.

A leg between two waypoints is said to "cross a door" if it transitions
between zones whose boundary contains a door. We accept the zone change
as a proxy for the actual crossing (geometric exact intersection is
unnecessary here — every cross-zone leg passes near a door in practice).
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from data.warehouse_config import DOORS, ZONES


def _zone_at(x: float, y: float) -> str:
    for z in ZONES.values():
        if z.contains(x, y):
            return z.code
    return "OUTSIDE"


def door_crossings_on_leg(
    p: Tuple[float, float], q: Tuple[float, float]
) -> List[str]:
    """Return labels of doors crossed when walking from p to q."""
    z1 = _zone_at(*p)
    z2 = _zone_at(*q)
    if z1 == z2:
        return []
    crossed: List[str] = []
    for door in DOORS:
        # crossing the frozen door means moving in/out of FROZEN
        if door.zone_in == "FROZEN" and (z1 == "FROZEN") != (z2 == "FROZEN"):
            crossed.append(door.label)
        elif door.zone_in == "FRESH" and (z1 == "FRESH") != (z2 == "FRESH"):
            crossed.append(door.label)
    return crossed


def door_delay_seconds_on_leg(
    p: Tuple[float, float], q: Tuple[float, float]
) -> float:
    crossed = door_crossings_on_leg(p, q)
    if not crossed:
        return 0.0
    by_label = {d.label: d for d in DOORS}
    return sum(by_label[lbl].delay_seconds for lbl in crossed)


def door_count_on_route(
    points: List[Tuple[float, float]], route_idx: List[int]
) -> int:
    n = 0
    for a, b in zip(route_idx[:-1], route_idx[1:]):
        n += len(door_crossings_on_leg(points[a], points[b]))
    return n


def door_delay_total_seconds(
    points: List[Tuple[float, float]],
    route_idx: List[int],
    operator_speed_mps: float = 1.2,
) -> float:
    """Sum of all door delays incurred on a route."""
    total = 0.0
    for a, b in zip(route_idx[:-1], route_idx[1:]):
        total += door_delay_seconds_on_leg(points[a], points[b])
    return total
