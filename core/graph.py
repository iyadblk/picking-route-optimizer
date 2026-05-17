"""Distance and time matrices for an order."""
from __future__ import annotations

from typing import List, Sequence, Tuple

import networkx as nx
import numpy as np

from core.doors import door_delay_seconds_on_leg
from core.warehouse import Order, points_for_order, labels_for_order


def manhattan_distance(p: Tuple[float, float], q: Tuple[float, float]) -> float:
    return abs(p[0] - q[0]) + abs(p[1] - q[1])


def distance_matrix(points: Sequence[Tuple[float, float]]) -> np.ndarray:
    n = len(points)
    m = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            d = manhattan_distance(points[i], points[j])
            m[i, j] = d
            m[j, i] = d
    return m


def time_matrix(
    points: Sequence[Tuple[float, float]],
    operator_speed_mps: float,
) -> np.ndarray:
    """Travel time including door delays (seconds)."""
    n = len(points)
    m = np.zeros((n, n), dtype=float)
    speed = max(operator_speed_mps, 1e-6)
    for i in range(n):
        for j in range(i + 1, n):
            walk = manhattan_distance(points[i], points[j]) / speed
            door = door_delay_seconds_on_leg(points[i], points[j])
            t = walk + door
            m[i, j] = t
            m[j, i] = t
    return m


def build_order_graph(order: Order) -> nx.Graph:
    points = points_for_order(order)
    labels = labels_for_order(order)
    g = nx.Graph()
    for idx, (pt, lbl) in enumerate(zip(points, labels)):
        kind = "dock" if idx == 0 else "sku"
        g.add_node(idx, label=lbl, pos=pt, kind=kind)
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            g.add_edge(i, j, weight=manhattan_distance(points[i], points[j]))
    return g


def route_distance(
    points: Sequence[Tuple[float, float]], order_idx: Sequence[int]
) -> float:
    return sum(manhattan_distance(points[a], points[b])
               for a, b in zip(order_idx[:-1], order_idx[1:]))


def aisle_changes(order: Order, route_idx: Sequence[int]) -> int:
    aisles_seq: List[str] = []
    for i in route_idx:
        aisles_seq.append("DOCK" if i == 0 else order.skus[i - 1].aisle)
    changes = 0
    for a, b in zip(aisles_seq[:-1], aisles_seq[1:]):
        if a != b and a != "DOCK" and b != "DOCK":
            changes += 1
    return changes


def cross_aisle_uses(order: Order, route_idx: Sequence[int]) -> int:
    """Approximate count of cross-aisle uses (legs that change aisle within zone)."""
    n = 0
    for a, b in zip(route_idx[:-1], route_idx[1:]):
        if a == 0 or b == 0:
            continue
        sa = order.skus[a - 1]
        sb = order.skus[b - 1]
        if sa.aisle != sb.aisle and sa.zone == sb.zone:
            n += 1
    return n
