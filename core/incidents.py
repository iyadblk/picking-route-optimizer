"""Incident simulation: blocked aisle, missing SKU, wrapper down, forklift down."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.warehouse import Order, SKU
from data.warehouse_config import AISLES, WRAPPERS, ZONE_OF_AISLE, ZONES


@dataclass
class IncidentScenario:
    blocked_aisle: Optional[str] = None
    missing_sku_id: Optional[str] = None
    wrapper_down: Optional[str] = None
    forklift_unavailable: bool = False

    @property
    def active(self) -> bool:
        return bool(
            self.blocked_aisle or self.missing_sku_id
            or self.wrapper_down or self.forklift_unavailable
        )


@dataclass
class IncidentEffect:
    notes: List[str] = field(default_factory=list)
    forbidden_node_pairs: List[Tuple[int, int]] = field(default_factory=list)
    removed_sku_id: Optional[str] = None
    substitute_sku_id: Optional[str] = None
    disabled_wrapper: Optional[str] = None
    forklift_unavailable: bool = False


def _find_substitute(missing: SKU, order: Order) -> Optional[SKU]:
    used = {(s.aisle, s.position) for s in order.skus}
    zone = ZONES[missing.zone]
    for aisle in zone.aisles:
        for pos in range(1, zone.positions_per_aisle + 1):
            if (aisle, pos) in used:
                continue
            return SKU(
                sku_id=f"{missing.sku_id}-SUB",
                code=missing.code,
                brand=missing.brand,
                name=missing.name + " (substitute)",
                aisle=aisle,
                position=pos,
                quantity=missing.quantity,
                weight_kg=missing.weight_kg,
                volume_l=missing.volume_l,
                fragile=missing.fragile,
                priority=missing.priority,
            )
    return None


def apply_incidents(order: Order, scenario: IncidentScenario) -> Tuple[Order, IncidentEffect]:
    effect = IncidentEffect(forklift_unavailable=scenario.forklift_unavailable)
    new_skus: List[SKU] = list(order.skus)

    if scenario.missing_sku_id:
        target = next((s for s in new_skus if s.sku_id == scenario.missing_sku_id), None)
        if target is None:
            effect.notes.append(f"Missing SKU '{scenario.missing_sku_id}' not in order.")
        else:
            effect.removed_sku_id = target.sku_id
            new_skus = [s for s in new_skus if s.sku_id != target.sku_id]
            sub = _find_substitute(target, order)
            if sub is not None:
                effect.substitute_sku_id = sub.sku_id
                new_skus.append(sub)
                effect.notes.append(
                    f"SKU {target.sku_id} unavailable -> substitute {sub.sku_id} "
                    f"({sub.brand} {sub.name})"
                )
            else:
                effect.notes.append(
                    f"SKU {target.sku_id} unavailable; no substitute found, dropped."
                )

    new_order = Order(
        order_id=order.order_id,
        operator_id=order.operator_id,
        operator_name=order.operator_name,
        created_at=order.created_at,
        skus=new_skus,
        deadline_minutes=order.deadline_minutes,
    )

    if scenario.blocked_aisle:
        if scenario.blocked_aisle not in AISLES:
            effect.notes.append(f"Unknown aisle '{scenario.blocked_aisle}'.")
        else:
            blocked = scenario.blocked_aisle
            in_aisle = [
                i for i, s in enumerate(new_order.skus, start=1) if s.aisle == blocked
            ]
            other = [
                i for i, s in enumerate(new_order.skus, start=1) if s.aisle != blocked
            ] + [0]
            pairs: List[Tuple[int, int]] = []
            for a in other:
                for b in in_aisle:
                    pairs.append((a, b))
                    pairs.append((b, a))
            effect.forbidden_node_pairs = pairs
            if in_aisle:
                effect.notes.append(
                    f"Aisle {blocked} BLOCKED: {len(in_aisle)} SKU(s) affected. "
                    "OR-Tools will avoid the aisle."
                )
            else:
                effect.notes.append(
                    f"Aisle {blocked} blocked but no SKUs affected."
                )

    if scenario.wrapper_down:
        valid = {w.label for w in WRAPPERS}
        if scenario.wrapper_down in valid:
            effect.disabled_wrapper = scenario.wrapper_down
            effect.notes.append(
                f"Wrapper {scenario.wrapper_down} OUT OF SERVICE -- queue will be redistributed."
            )
        else:
            effect.notes.append(f"Unknown wrapper '{scenario.wrapper_down}'.")

    if scenario.forklift_unavailable:
        effect.notes.append("All forklifts unavailable -- replenishment paused.")

    return new_order, effect
