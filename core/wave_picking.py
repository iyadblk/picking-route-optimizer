"""Multi-operator wave picking."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from core.metrics import RouteMetrics, compute_metrics
from core.optimizer import RouteResult, constrained_route
from core.warehouse import Order, SKU
from data.operators import PICKERS
from data.warehouse_config import WarehouseConfig, ZONES


@dataclass
class OperatorAssignment:
    operator_id: str
    operator_name: str
    sub_order: Order
    route: RouteResult
    metrics: RouteMetrics
    zones: List[str]


@dataclass
class WavePlan:
    operators: List[OperatorAssignment]
    total_distance_m: float
    parallel_time_sec: float
    total_handling_time_sec: float
    handover_time_sec: float = 60.0


def _split_zones(zones: List[str], n_ops: int) -> List[List[str]]:
    ordered = sorted(zones, key=lambda z: ZONES[z].pick_priority)
    if n_ops <= 1 or not ordered:
        return [ordered]
    chunk = max(1, len(ordered) // n_ops)
    chunks: List[List[str]] = []
    for i in range(0, len(ordered), chunk):
        chunks.append(ordered[i: i + chunk])
    while len(chunks) > n_ops:
        last = chunks.pop()
        chunks[-1].extend(last)
    while len(chunks) < n_ops:
        chunks.append([])
    return chunks


def _operator_for_index(i: int) -> tuple:
    p = PICKERS[i % len(PICKERS)]
    return p.op_id, p.name


def plan_wave(
    order: Order,
    n_operators: int,
    config: WarehouseConfig,
) -> WavePlan:
    if n_operators < 1:
        raise ValueError("n_operators >= 1")
    zones = order.zones_covered
    chunks = _split_zones(zones, n_operators)

    ops: List[OperatorAssignment] = []
    for i, chunk in enumerate(chunks):
        op_skus: List[SKU] = [s for s in order.skus if s.zone in chunk]
        if not op_skus:
            continue
        op_id, op_name = _operator_for_index(i)
        sub = Order(
            order_id=f"{order.order_id}-W{i+1}",
            operator_id=op_id,
            operator_name=op_name,
            created_at=order.created_at,
            skus=op_skus,
            deadline_minutes=order.deadline_minutes,
        )
        rt = constrained_route(sub, time_limit_sec=config.solver_time_limit_sec,
                                operator_speed_mps=config.operator_speed_mps)
        mt = compute_metrics(sub, rt, config)
        ops.append(OperatorAssignment(op_id, op_name, sub, rt, mt, chunk))

    if not ops:
        return WavePlan([], 0.0, 0.0, 0.0)

    return WavePlan(
        operators=ops,
        total_distance_m=sum(o.metrics.distance_m for o in ops),
        parallel_time_sec=max(o.metrics.total_time_sec for o in ops),
        total_handling_time_sec=sum(o.metrics.handling_time_sec for o in ops),
    )
