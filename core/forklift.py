"""Forklift dispatch + replenishment route optimization.

Picker positions hold a small "front-stock" buffer. When a position drops
below RESERVE_STOCK_REPLENISH_THRESHOLD units, a replenishment task is
queued. Forklifts drive from a reserve area at the back of the warehouse to
the picker slot. We solve the forklift's daily route as a TSP using OR-Tools
on the queued replenishment tasks.
"""
from __future__ import annotations

import random
import time as _time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

from core.graph import distance_matrix, manhattan_distance
from core.warehouse import Order
from data.warehouse_config import (
    AISLES,
    AISLE_X,
    FORKLIFT_IDS,
    FORKLIFT_RACK_LEVELS,
    FORKLIFT_RACK_LEVEL_HEIGHT_M,
    FORKLIFT_SPEED_LADEN_MPS,
    FORKLIFT_SPEED_UNLADEN_MPS,
    PRIMARY_DOCK,
    RESERVE_STOCK_REPLENISH_THRESHOLD,
    WAREHOUSE_WIDTH,
    ZONE_OF_AISLE,
    ZONES,
    position_xy,
)
from data.operators import FORKLIFT_DRIVERS


# Pick-priority for forklift task ordering: frozen > fresh > ambient > heavy
FORKLIFT_PRIORITY = {"FROZEN": 1, "FRESH": 2, "AMBIENT": 3, "HEAVY": 4}


@dataclass
class StockSlot:
    aisle: str
    position: int
    units_on_hand: int          # current front-stock
    capacity: int = 12          # max front-stock
    reserve_units: int = 60     # behind / above

    @property
    def needs_replenishment(self) -> bool:
        return self.units_on_hand < RESERVE_STOCK_REPLENISH_THRESHOLD

    @property
    def coord(self) -> Tuple[float, float]:
        return position_xy(self.aisle, self.position)


@dataclass
class ReplenishmentTask:
    aisle: str
    position: int
    units_to_move: int
    zone: str
    priority: int               # lower = pick earlier
    estimated_seconds: float    # forklift trip time

    @property
    def coord(self) -> Tuple[float, float]:
        return position_xy(self.aisle, self.position)


@dataclass
class ForkliftRoute:
    forklift_id: str
    driver_name: str
    tasks: List[ReplenishmentTask]
    total_distance_m: float
    total_time_sec: float
    route_points: List[Tuple[float, float]]


@dataclass
class ForkliftPlan:
    forklift_routes: List[ForkliftRoute]
    pending_tasks: int
    total_distance_m: float
    total_time_sec: float
    unavailable: bool = False


# --------------------------------------------------------------------------- #
# Stock generation (random but seeded by order)
# --------------------------------------------------------------------------- #
def generate_stock_levels(order: Order, seed: int = 0) -> List[StockSlot]:
    """Deterministically derive a stock level per SKU position in the order.

    SKUs in the order are slightly more likely to be low-stock (simulating
    that consumption depleted them).
    """
    rng = random.Random(seed)
    in_order = {(s.aisle, s.position) for s in order.skus}
    slots: List[StockSlot] = []
    for aisle in AISLES:
        zone = ZONES[ZONE_OF_AISLE[aisle]]
        # Sample 6 random positions per aisle
        sampled_positions = rng.sample(
            range(1, zone.positions_per_aisle + 1),
            k=min(6, zone.positions_per_aisle),
        )
        for p in sampled_positions:
            if (aisle, p) in in_order:
                units = rng.randint(0, RESERVE_STOCK_REPLENISH_THRESHOLD - 1)
            else:
                units = rng.randint(0, 12)
            slots.append(StockSlot(aisle=aisle, position=p, units_on_hand=units))
    return slots


# --------------------------------------------------------------------------- #
# Build replenishment tasks from low-stock slots
# --------------------------------------------------------------------------- #
def _reserve_anchor_for_zone(zone_code: str) -> Tuple[float, float]:
    """A symbolic 'reserve' anchor at the top of each zone's leftmost aisle."""
    zone = ZONES[zone_code]
    aisle0 = zone.aisles[0]
    return AISLE_X[aisle0], zone.y_max - 2.0


def build_replenishment_tasks(stock: List[StockSlot]) -> List[ReplenishmentTask]:
    tasks: List[ReplenishmentTask] = []
    for slot in stock:
        if not slot.needs_replenishment:
            continue
        zone_code = ZONE_OF_AISLE[slot.aisle]
        anchor = _reserve_anchor_for_zone(zone_code)
        dist = manhattan_distance(anchor, slot.coord) * 2.0  # round-trip
        # vertical lift: assume mid-rack on average
        lift_extra = (FORKLIFT_RACK_LEVELS / 2.0) * FORKLIFT_RACK_LEVEL_HEIGHT_M / 0.5
        est = dist / FORKLIFT_SPEED_LADEN_MPS + lift_extra + 12.0  # 12s grab/place
        tasks.append(ReplenishmentTask(
            aisle=slot.aisle,
            position=slot.position,
            units_to_move=slot.capacity - slot.units_on_hand,
            zone=zone_code,
            priority=FORKLIFT_PRIORITY[zone_code],
            estimated_seconds=est,
        ))
    # Priority order, then by zone proximity
    tasks.sort(key=lambda t: (t.priority, t.aisle, t.position))
    return tasks


# --------------------------------------------------------------------------- #
# Dispatch tasks to forklifts (round-robin within priority)
# --------------------------------------------------------------------------- #
def dispatch_tasks(
    tasks: List[ReplenishmentTask],
    n_forklifts: int = 2,
) -> Dict[str, List[ReplenishmentTask]]:
    if n_forklifts < 1:
        return {}
    drivers = FORKLIFT_DRIVERS[:n_forklifts]
    assignment: Dict[str, List[ReplenishmentTask]] = {d.fk_id: [] for d in drivers}
    for i, task in enumerate(tasks):
        fk = drivers[i % n_forklifts]
        assignment[fk.fk_id].append(task)
    return assignment


# --------------------------------------------------------------------------- #
# Optimize each forklift's route via OR-Tools (closed loop from dock-H)
# --------------------------------------------------------------------------- #
def _solve_forklift_tour(points: List[Tuple[float, float]], time_limit_sec: int = 3) -> List[int]:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    n = len(points)
    if n <= 2:
        return list(range(n)) + [0]
    matrix = (distance_matrix(points) * 100.0).round().astype(int)
    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def cb(i, j):
        return int(matrix[manager.IndexToNode(i), manager.IndexToNode(j)])

    transit = routing.RegisterTransitCallback(cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)
    p = pywrapcp.DefaultRoutingSearchParameters()
    p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    p.time_limit.FromSeconds(max(1, int(time_limit_sec)))
    sol = routing.SolveWithParameters(p)
    if sol is None:
        return list(range(n)) + [0]
    out = []
    idx = routing.Start(0)
    while not routing.IsEnd(idx):
        out.append(manager.IndexToNode(idx))
        idx = sol.Value(routing.NextVar(idx))
    out.append(manager.IndexToNode(idx))
    return out


def plan_forklift_routes(
    order: Order,
    seed: int,
    n_forklifts: int = 2,
    unavailable: bool = False,
) -> ForkliftPlan:
    if unavailable:
        return ForkliftPlan([], 0, 0.0, 0.0, unavailable=True)

    stock = generate_stock_levels(order, seed=seed)
    tasks = build_replenishment_tasks(stock)
    assignment = dispatch_tasks(tasks, n_forklifts=n_forklifts)
    drivers = FORKLIFT_DRIVERS[:n_forklifts]

    routes: List[ForkliftRoute] = []
    for driver in drivers:
        my_tasks = assignment.get(driver.fk_id, [])
        if not my_tasks:
            routes.append(ForkliftRoute(
                forklift_id=driver.fk_id,
                driver_name=driver.name,
                tasks=[],
                total_distance_m=0.0,
                total_time_sec=0.0,
                route_points=[(PRIMARY_DOCK.x, PRIMARY_DOCK.y)],
            ))
            continue
        # Anchor on dock-H (heavy zone dock), then solve TSP through tasks
        from data.warehouse_config import DOCKS
        dock_h = next(d for d in DOCKS if d.kind == "heavy")
        pts = [(dock_h.x, dock_h.y)] + [t.coord for t in my_tasks]
        seq = _solve_forklift_tour(pts, time_limit_sec=3)
        ordered = [pts[i] for i in seq]
        # distance + time
        total_dist = sum(
            manhattan_distance(a, b) for a, b in zip(ordered[:-1], ordered[1:])
        )
        total_time = (
            total_dist / FORKLIFT_SPEED_LADEN_MPS
            + sum(t.estimated_seconds for t in my_tasks) * 0.4  # only the lift extras
        )
        # Re-order tasks by visit order
        ordered_tasks = [my_tasks[i - 1] for i in seq[1:-1]]
        routes.append(ForkliftRoute(
            forklift_id=driver.fk_id,
            driver_name=driver.name,
            tasks=ordered_tasks,
            total_distance_m=total_dist,
            total_time_sec=total_time,
            route_points=ordered,
        ))

    return ForkliftPlan(
        forklift_routes=routes,
        pending_tasks=len(tasks),
        total_distance_m=sum(r.total_distance_m for r in routes),
        total_time_sec=sum(r.total_time_sec for r in routes),
    )
