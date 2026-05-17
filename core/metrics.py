"""Metrics: distance, time, cold exposure, door delays, cost, savings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from core.doors import (
    door_count_on_route,
    door_crossings_on_leg,
    door_delay_seconds_on_leg,
    door_delay_total_seconds,
)
from core.graph import aisle_changes, cross_aisle_uses, manhattan_distance
from core.optimizer import RouteResult
from core.warehouse import Order, points_for_order
from data.warehouse_config import WarehouseConfig, ZONES


@dataclass
class RouteMetrics:
    method: str
    distance_m: float
    walking_time_sec: float
    handling_time_sec: float
    door_delay_sec: float
    total_time_sec: float
    cost_eur: float
    aisle_changes: int
    cross_aisle_uses: int
    door_crossings: int
    cold_chain_seconds: float
    avg_step_distance_m: float
    efficiency_score: float


def _frozen_exposure_seconds(order: Order, result: RouteResult, config: WarehouseConfig) -> float:
    """Time elapsed between picking a frozen SKU and reaching the dock."""
    pts = points_for_order(order)
    speed = max(config.operator_speed_mps, 1e-6)
    leg_durations: List[float] = []
    for a, b in zip(result.route[:-1], result.route[1:]):
        walk = manhattan_distance(pts[a], pts[b]) / speed
        door = door_delay_seconds_on_leg(pts[a], pts[b])
        if b == 0:
            leg_durations.append(walk + door)
        else:
            leg_durations.append(walk + door + config.pick_time_sec)
    total = 0.0
    cum_after = 0.0
    for i in range(len(result.route) - 1, 0, -1):
        cum_after += leg_durations[i - 1]
        node = result.route[i]
        if node == 0:
            cum_after = 0.0
            continue
        sku = order.skus[node - 1]
        if sku.zone == "FROZEN":
            total += cum_after
    return total


def compute_metrics(
    order: Order,
    result: RouteResult,
    config: WarehouseConfig,
) -> RouteMetrics:
    pts = points_for_order(order)
    distance = result.distance_m
    walking_time = distance / max(config.operator_speed_mps, 1e-6)
    handling_time = order.size * config.pick_time_sec
    door_delay = door_delay_total_seconds(pts, result.route, config.operator_speed_mps)
    total_time = walking_time + handling_time + door_delay
    cost = (total_time / 3600.0) * config.hourly_cost_eur
    n_steps = max(1, len(result.route) - 1)
    return RouteMetrics(
        method=result.method,
        distance_m=distance,
        walking_time_sec=walking_time,
        handling_time_sec=handling_time,
        door_delay_sec=door_delay,
        total_time_sec=total_time,
        cost_eur=cost,
        aisle_changes=aisle_changes(order, result.route),
        cross_aisle_uses=cross_aisle_uses(order, result.route),
        door_crossings=door_count_on_route(pts, result.route),
        cold_chain_seconds=_frozen_exposure_seconds(order, result, config),
        avg_step_distance_m=distance / n_steps,
        efficiency_score=0.0,
    )


def attach_efficiency(metrics: Dict[str, RouteMetrics]) -> None:
    pos = [m.distance_m for m in metrics.values() if m.distance_m > 0]
    best = min(pos) if pos else 1.0
    for m in metrics.values():
        m.efficiency_score = 100.0 if m.distance_m <= 0 else round(100.0 * best / m.distance_m, 1)


def compare_to_naive(metrics: Dict[str, RouteMetrics]) -> Dict[str, Dict[str, float]]:
    base = metrics["naive"]
    out: Dict[str, Dict[str, float]] = {}
    for name, m in metrics.items():
        d_saved = base.distance_m - m.distance_m
        t_saved = base.total_time_sec - m.total_time_sec
        c_saved = base.cost_eur - m.cost_eur
        pct = (d_saved / base.distance_m * 100.0) if base.distance_m else 0.0
        out[name] = {
            "distance_saved_m": d_saved,
            "time_saved_sec": t_saved,
            "cost_saved_eur": c_saved,
            "distance_saved_pct": pct,
        }
    return out


def annual_projection(
    metrics: Dict[str, RouteMetrics], config: WarehouseConfig
) -> Dict[str, Dict[str, float]]:
    factor = config.orders_per_day * config.working_days_per_year
    base_cost = metrics["naive"].cost_eur * factor
    out: Dict[str, Dict[str, float]] = {}
    for name, m in metrics.items():
        c = m.cost_eur * factor
        d = m.distance_m * factor
        h = (m.total_time_sec * factor) / 3600.0
        out[name] = {
            "annual_distance_m": d,
            "annual_distance_km": d / 1000.0,
            "annual_cost_eur": c,
            "annual_hours": h,
            "annual_savings_vs_naive_eur": base_cost - c,
        }
    return out


def step_by_step(
    order: Order, result: RouteResult, config: WarehouseConfig
) -> pd.DataFrame:
    pts = points_for_order(order)
    rows: List[dict] = []
    cum_dist = 0.0
    cum_time = 0.0
    cart_w = 0.0
    cart_v = 0.0
    speed = max(config.operator_speed_mps, 1e-6)
    for step, (a, b) in enumerate(zip(result.route[:-1], result.route[1:]), start=1):
        leg = manhattan_distance(pts[a], pts[b])
        cum_dist += leg
        cum_time += leg / speed
        door_legs = door_crossings_on_leg(pts[a], pts[b])
        door_delay = door_delay_seconds_on_leg(pts[a], pts[b])
        cum_time += door_delay
        if b == 0:
            cum_time += 0.0
            row = {
                "Step": step,
                "Product": "DOCK",
                "Brand": "-",
                "Zone": "-",
                "Aisle": "-",
                "Position": "-",
                "Side": "-",
                "Leg (m)": round(leg, 1),
                "Door delay (s)": round(door_delay, 1),
                "Door crossed": ", ".join(door_legs) if door_legs else "",
                "Cumul dist (m)": round(cum_dist, 1),
                "Cumul time (min)": round(cum_time / 60.0, 2),
                "Cart kg": round(cart_w, 1),
                "Cart L": round(cart_v, 1),
            }
        else:
            sku = order.skus[b - 1]
            cum_time += config.pick_time_sec
            cart_w += sku.total_weight_kg
            cart_v += sku.total_volume_l
            row = {
                "Step": step,
                "Product": sku.name,
                "Brand": sku.brand,
                "Zone": sku.zone,
                "Aisle": sku.aisle,
                "Position": sku.position,
                "Side": sku.side,
                "Leg (m)": round(leg, 1),
                "Door delay (s)": round(door_delay, 1),
                "Door crossed": ", ".join(door_legs) if door_legs else "",
                "Cumul dist (m)": round(cum_dist, 1),
                "Cumul time (min)": round(cum_time / 60.0, 2),
                "Cart kg": round(cart_w, 1),
                "Cart L": round(cart_v, 1),
            }
        rows.append(row)
    return pd.DataFrame(rows)


def cumulative_distance_curve(order: Order, result: RouteResult) -> List[float]:
    pts = points_for_order(order)
    cum = [0.0]
    for a, b in zip(result.route[:-1], result.route[1:]):
        cum.append(cum[-1] + manhattan_distance(pts[a], pts[b]))
    return cum


def per_zone_distance(order: Order, result: RouteResult) -> Dict[str, float]:
    pts = points_for_order(order)
    out: Dict[str, float] = {z: 0.0 for z in ZONES}
    out["DOCK"] = 0.0
    for a, b in zip(result.route[:-1], result.route[1:]):
        leg = manhattan_distance(pts[a], pts[b])
        if b == 0:
            out["DOCK"] += leg
        else:
            out[order.skus[b - 1].zone] += leg
    return out


def per_zone_sku_count(order: Order) -> Dict[str, int]:
    counts: Dict[str, int] = {z: 0 for z in ZONES}
    for s in order.skus:
        counts[s.zone] += 1
    return counts


def per_zone_time(
    order: Order, result: RouteResult, config: WarehouseConfig
) -> Dict[str, float]:
    """Time spent in each zone (walking + door + handling at SKUs in that zone)."""
    pts = points_for_order(order)
    out: Dict[str, float] = {z: 0.0 for z in ZONES}
    out["DOCK"] = 0.0
    speed = max(config.operator_speed_mps, 1e-6)
    for a, b in zip(result.route[:-1], result.route[1:]):
        leg_t = manhattan_distance(pts[a], pts[b]) / speed
        leg_t += door_delay_seconds_on_leg(pts[a], pts[b])
        if b == 0:
            out["DOCK"] += leg_t
        else:
            sku = order.skus[b - 1]
            out[sku.zone] += leg_t + config.pick_time_sec
    return out


def aisle_visit_sequence(order: Order, result: RouteResult) -> List[str]:
    seq: List[str] = []
    for idx in result.route:
        label = "DOCK" if idx == 0 else order.skus[idx - 1].aisle
        if not seq or seq[-1] != label:
            seq.append(label)
    return seq


def format_minutes(seconds: float) -> str:
    minutes = seconds / 60.0
    if minutes < 1:
        return f"{seconds:.0f}s"
    return f"{minutes:.1f} min"


def format_duration_hms(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"
