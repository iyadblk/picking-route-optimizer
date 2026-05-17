"""Four picking algorithms.

All algorithms return a closed route as a list of node indices that starts
and ends at node 0 (the primary dock). Indices 1..n correspond to
`order.skus[i-1]`.

Algorithms:
  1. naive            - input order
  2. nearest_neighbor - greedy
  3. or_tools         - distance-optimal TSP (GUIDED_LOCAL_SEARCH)
  4. constrained      - zone-priority + U-shape + door-time penalty
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

from core.graph import distance_matrix, route_distance, time_matrix
from core.warehouse import Order, points_for_order
from data.warehouse_config import ZONES


@dataclass
class RouteResult:
    method: str
    route: List[int]               # node indices (closed loop, starts+ends at 0)
    distance_m: float
    solver_time_sec: float
    notes: str = ""


# --------------------------------------------------------------------------- #
# 1. Naive
# --------------------------------------------------------------------------- #
def naive_route(order: Order) -> RouteResult:
    t0 = time.perf_counter()
    n = order.size
    route = [0] + list(range(1, n + 1)) + [0]
    points = points_for_order(order)
    return RouteResult(
        method="naive",
        route=route,
        distance_m=route_distance(points, route),
        solver_time_sec=time.perf_counter() - t0,
        notes="No optimization (baseline)",
    )


# --------------------------------------------------------------------------- #
# 2. Nearest Neighbor
# --------------------------------------------------------------------------- #
def nearest_neighbor_route(order: Order) -> RouteResult:
    t0 = time.perf_counter()
    points = points_for_order(order)
    n = len(points)
    matrix = distance_matrix(points)
    visited = [False] * n
    visited[0] = True
    route = [0]
    cur = 0
    for _ in range(n - 1):
        best_j, best_d = -1, float("inf")
        for j in range(n):
            if visited[j]:
                continue
            if matrix[cur, j] < best_d:
                best_d, best_j = matrix[cur, j], j
        route.append(best_j)
        visited[best_j] = True
        cur = best_j
    route.append(0)
    return RouteResult(
        method="nearest_neighbor",
        route=route,
        distance_m=route_distance(points, route),
        solver_time_sec=time.perf_counter() - t0,
        notes="Greedy nearest-neighbor heuristic",
    )


# --------------------------------------------------------------------------- #
# 3. OR-Tools TSP (pure distance)
# --------------------------------------------------------------------------- #
def or_tools_route(
    order: Order,
    time_limit_sec: int = 10,
    forbidden_node_pairs: List[Tuple[int, int]] = None,
    *,
    method_label: str = "or_tools",
) -> RouteResult:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    t0 = time.perf_counter()
    points = points_for_order(order)
    n = len(points)
    if n <= 1:
        return RouteResult(method_label, [0, 0], 0.0, 0.0, "Trivial (empty)")

    matrix = distance_matrix(points)
    int_matrix = (matrix * 100.0).round().astype(int)

    if forbidden_node_pairs:
        BIG = 10**9
        for a, b in forbidden_node_pairs:
            int_matrix[a, b] = BIG
            int_matrix[b, a] = BIG

    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def cb(i: int, j: int) -> int:
        return int(int_matrix[manager.IndexToNode(i), manager.IndexToNode(j)])

    transit = routing.RegisterTransitCallback(cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(max(1, int(time_limit_sec)))

    solution = routing.SolveWithParameters(params)
    if solution is None:
        nn = nearest_neighbor_route(order)
        nn.method = method_label
        nn.notes = "(OR-Tools failed; fell back to nearest-neighbor)"
        return nn

    route: List[int] = []
    idx = routing.Start(0)
    while not routing.IsEnd(idx):
        route.append(manager.IndexToNode(idx))
        idx = solution.Value(routing.NextVar(idx))
    route.append(manager.IndexToNode(idx))
    return RouteResult(
        method=method_label, route=route,
        distance_m=route_distance(points, route),
        solver_time_sec=time.perf_counter() - t0,
        notes="OR-Tools TSP, GUIDED_LOCAL_SEARCH",
    )


# --------------------------------------------------------------------------- #
# 4. Constrained: zone priority + U-shape + door-time-aware
# --------------------------------------------------------------------------- #
def constrained_route(
    order: Order,
    time_limit_sec: int = 10,
    operator_speed_mps: float = 1.2,
    forbidden_node_pairs: List[Tuple[int, int]] = None,
) -> RouteResult:
    """Zone-ordered TSP with intra-aisle U-shape enforcement.

    Step A: bucket SKU node indices by zone pick priority.
    Step B: in priority order, solve open-TSP for each bucket using a TIME
            matrix (walk-time + door penalty) -- this naturally avoids
            unnecessary door crossings.
    Step C: after the global route is built, reorder consecutive SKUs that
            share the same aisle into U-shape: odd ascending then even
            descending (one continuous pass per aisle, no doubling back).
    """
    t0 = time.perf_counter()
    points = points_for_order(order)
    n = len(points)
    if n <= 1:
        return RouteResult("constrained", [0, 0], 0.0, 0.0, "Trivial")

    # Step A: bucket by zone priority
    buckets: Dict[int, List[int]] = {}
    for i, sku in enumerate(order.skus, start=1):
        buckets.setdefault(sku.pick_priority, []).append(i)

    # Step B: chain buckets via open-TSP
    route: List[int] = [0]
    current = 0
    for prio in sorted(buckets.keys()):
        bucket = buckets[prio]
        sub_nodes = [current] + bucket
        sub_pts = [points[k] for k in sub_nodes]
        if len(bucket) == 1:
            route.append(bucket[0])
            current = bucket[0]
            continue
        sub_route = _open_tsp_time(
            sub_pts, time_limit_sec=max(1, time_limit_sec // 3),
            operator_speed_mps=operator_speed_mps,
        )
        for k in sub_route[1:]:
            route.append(sub_nodes[k])
        current = sub_nodes[sub_route[-1]]

    route.append(0)

    # Step C: U-shape reorder per consecutive-aisle run
    route = _enforce_ushape(order, route)

    return RouteResult(
        method="constrained",
        route=route,
        distance_m=route_distance(points, route),
        solver_time_sec=time.perf_counter() - t0,
        notes="Zone priority + U-shape per aisle + door-time penalty",
    )


def _enforce_ushape(order: Order, route: List[int]) -> List[int]:
    """Within each maximal run of consecutive SKUs from the same aisle,
    re-order them so all ODD positions come first (sorted ascending = walking
    DOWN the left side) then all EVEN positions (sorted descending = walking
    UP the right side back to the cross-aisle).
    """
    out: List[int] = [route[0]]
    i = 1
    n = len(route)
    while i < n:
        node = route[i]
        if node == 0:
            out.append(node)
            i += 1
            continue
        aisle = order.skus[node - 1].aisle
        run = [node]
        j = i + 1
        while j < n - 1 and route[j] != 0 and order.skus[route[j] - 1].aisle == aisle:
            run.append(route[j])
            j += 1

        odd = sorted([k for k in run if order.skus[k - 1].position % 2 == 1],
                     key=lambda k: order.skus[k - 1].position)
        even = sorted([k for k in run if order.skus[k - 1].position % 2 == 0],
                      key=lambda k: order.skus[k - 1].position, reverse=True)
        out.extend(odd + even)
        i = j
    return out


def _open_tsp_time(
    points: Sequence[Tuple[float, float]],
    time_limit_sec: int,
    operator_speed_mps: float,
) -> List[int]:
    """Open TSP starting at node 0. Cost = travel time (seconds * 1000)."""
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    n = len(points)
    if n == 1:
        return [0]
    if n == 2:
        return [0, 1]

    tmat = time_matrix(points, operator_speed_mps)
    int_t = (tmat * 1000.0).round().astype(int)

    manager = pywrapcp.RoutingIndexManager(n + 1, 1, [0], [n])
    routing = pywrapcp.RoutingModel(manager)
    BIG = 10**9

    def cb(i: int, j: int) -> int:
        a = manager.IndexToNode(i); b = manager.IndexToNode(j)
        if a == n or b == n:
            return 0 if b == n else BIG
        return int(int_t[a, b])

    transit = routing.RegisterTransitCallback(cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(max(1, int(time_limit_sec)))

    solution = routing.SolveWithParameters(params)
    if solution is None:
        # Fallback: greedy by time
        visited = [False] * n
        visited[0] = True
        out = [0]
        cur = 0
        for _ in range(n - 1):
            best_j, best_t = -1, float("inf")
            for j in range(n):
                if visited[j]:
                    continue
                if tmat[cur, j] < best_t:
                    best_t, best_j = tmat[cur, j], j
            out.append(best_j)
            visited[best_j] = True
            cur = best_j
        return out

    out: List[int] = []
    idx = routing.Start(0)
    while not routing.IsEnd(idx):
        node = manager.IndexToNode(idx)
        if node != n:
            out.append(node)
        idx = solution.Value(routing.NextVar(idx))
    return out


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def solve_all(
    order: Order,
    or_tools_time_limit_sec: int = 10,
    operator_speed_mps: float = 1.2,
    forbidden_node_pairs: List[Tuple[int, int]] = None,
) -> Dict[str, RouteResult]:
    return {
        "naive": naive_route(order),
        "nearest_neighbor": nearest_neighbor_route(order),
        "or_tools": or_tools_route(
            order, time_limit_sec=or_tools_time_limit_sec,
            forbidden_node_pairs=forbidden_node_pairs,
        ),
        "constrained": constrained_route(
            order, time_limit_sec=or_tools_time_limit_sec,
            operator_speed_mps=operator_speed_mps,
            forbidden_node_pairs=forbidden_node_pairs,
        ),
    }
