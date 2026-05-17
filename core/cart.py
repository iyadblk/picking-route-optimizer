"""Cart capacity check + greedy multi-trip splitter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.warehouse import Order, SKU
from data.warehouse_config import WarehouseConfig


@dataclass
class TripPlan:
    trip_index: int
    order: Order
    total_weight_kg: float
    total_volume_l: float
    weight_pct: float
    volume_pct: float


def needs_split(order: Order, config: WarehouseConfig) -> bool:
    return (
        order.total_weight_kg > config.cart_max_weight_kg
        or order.total_volume_l > config.cart_max_volume_m3 * 1000.0
    )


def split_order_into_trips(order: Order, config: WarehouseConfig) -> List[TripPlan]:
    max_w = config.cart_max_weight_kg
    max_v = config.cart_max_volume_m3 * 1000.0
    sorted_skus: List[SKU] = sorted(
        order.skus, key=lambda s: (s.pick_priority, s.aisle, s.position)
    )

    trips: List[List[SKU]] = []
    cur: List[SKU] = []
    cw, cv = 0.0, 0.0
    for s in sorted_skus:
        w, v = s.total_weight_kg, s.total_volume_l
        if (cw + w > max_w or cv + v > max_v) and cur:
            trips.append(cur)
            cur, cw, cv = [], 0.0, 0.0
        cur.append(s)
        cw += w
        cv += v
    if cur:
        trips.append(cur)

    out: List[TripPlan] = []
    for idx, batch in enumerate(trips, start=1):
        sub = Order(
            order_id=f"{order.order_id}-T{idx}",
            operator_id=order.operator_id,
            operator_name=order.operator_name,
            created_at=order.created_at,
            skus=batch,
            deadline_minutes=order.deadline_minutes,
        )
        tw = sub.total_weight_kg
        tv = sub.total_volume_l
        out.append(TripPlan(
            trip_index=idx,
            order=sub,
            total_weight_kg=tw,
            total_volume_l=tv,
            weight_pct=round(100.0 * tw / max_w, 1),
            volume_pct=round(100.0 * tv / max_v, 1),
        ))
    return out
