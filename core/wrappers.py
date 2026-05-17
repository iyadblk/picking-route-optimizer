"""Stretch-wrapper (filmeuse) queue management.

Each completed picking trip becomes one pallet that needs wrapping. We assign
pallets to the least-loaded wrapper in the *destination zone*. Each wrapper
processes 45 pallets/hour.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from data.warehouse_config import WRAPPERS, Wrapper


SECONDS_PER_PALLET: Dict[str, float] = {
    w.label: 3600.0 / w.capacity_pallets_per_hour for w in WRAPPERS
}


@dataclass
class WrapperPallet:
    pallet_id: str
    zone: str
    weight_kg: float
    arrived_at_sec: float


@dataclass
class WrapperState:
    wrapper: Wrapper
    queue: List[WrapperPallet]
    out_of_service: bool = False
    pallets_processed: int = 0
    seconds_busy: float = 0.0

    @property
    def queue_seconds(self) -> float:
        return len(self.queue) * SECONDS_PER_PALLET[self.wrapper.label]

    @property
    def utilization_pct(self) -> float:
        return min(100.0, self.seconds_busy / 3600.0 * 100.0)


@dataclass
class WrapperPlanResult:
    states: List[WrapperState]
    avg_wait_sec: float
    bottleneck: Optional[str]      # wrapper label > 85% util
    out_of_service: List[str]


def _wrappers_in_zone(zone_code: str, disabled: Optional[str]) -> List[Wrapper]:
    return [w for w in WRAPPERS if w.zone_code == zone_code and w.label != disabled]


def assign_pallets(
    pallets: List[WrapperPallet],
    disabled_wrapper: Optional[str] = None,
) -> WrapperPlanResult:
    """Greedy: each new pallet goes to the wrapper with the shortest current queue."""
    states: Dict[str, WrapperState] = {
        w.label: WrapperState(
            wrapper=w, queue=[], out_of_service=(w.label == disabled_wrapper),
        )
        for w in WRAPPERS
    }

    total_wait = 0.0
    n_assigned = 0
    for pallet in sorted(pallets, key=lambda p: p.arrived_at_sec):
        candidates = [
            states[w.label] for w in _wrappers_in_zone(pallet.zone, disabled_wrapper)
        ]
        if not candidates:
            # All wrappers in zone disabled -> fall back to any active wrapper
            candidates = [s for s in states.values() if not s.out_of_service]
        if not candidates:
            continue
        winner = min(candidates, key=lambda s: s.queue_seconds)
        winner.queue.append(pallet)
        winner.pallets_processed += 1
        winner.seconds_busy += SECONDS_PER_PALLET[winner.wrapper.label]
        wait = winner.queue_seconds - SECONDS_PER_PALLET[winner.wrapper.label]
        total_wait += max(wait, 0.0)
        n_assigned += 1

    avg_wait = (total_wait / n_assigned) if n_assigned else 0.0
    bottleneck = next(
        (s.wrapper.label for s in states.values() if s.utilization_pct > 85.0),
        None,
    )
    out_of_service = [s.wrapper.label for s in states.values() if s.out_of_service]
    return WrapperPlanResult(
        states=list(states.values()),
        avg_wait_sec=avg_wait,
        bottleneck=bottleneck,
        out_of_service=out_of_service,
    )


def make_pallets_from_order(order, n_per_zone_factor: int = 3) -> List[WrapperPallet]:
    """Synthesize a realistic daily wrapper workload from an order.

    For each SKU in the order we add `n_per_zone_factor` baseline pallets in
    that zone (so a 25-SKU order produces a ~75-pallet daily workload).
    """
    pallets: List[WrapperPallet] = []
    pid = 1
    arrival = 0.0
    for s in order.skus:
        for _ in range(n_per_zone_factor):
            pallets.append(WrapperPallet(
                pallet_id=f"PAL-{pid:04d}",
                zone=s.zone,
                weight_kg=s.total_weight_kg,
                arrived_at_sec=arrival,
            ))
            pid += 1
            arrival += 45.0   # one new pallet every 45s
    return pallets
