"""Sample order generators using the real French catalog."""
from __future__ import annotations

import random
from datetime import datetime
from typing import Dict, List, Optional

from core.warehouse import SKU, Order
from data.catalog import CATALOG_BY_ZONE, CatalogItem
from data.operators import PICKERS, picker_by_id
from data.warehouse_config import ZONES


def _gen_sku(item: CatalogItem, rng: random.Random, sku_seq: int) -> SKU:
    aisles = ZONES[item.zone].aisles
    aisle = rng.choice(aisles)
    pos = rng.randint(1, ZONES[item.zone].positions_per_aisle)
    qty = rng.randint(1, 3)
    priority = "urgent" if rng.random() < 0.07 else "normal"
    return SKU(
        sku_id=f"SKU-{item.code}-{sku_seq:04d}",
        code=item.code,
        brand=item.brand,
        name=item.name,
        aisle=aisle,
        position=pos,
        quantity=qty,
        weight_kg=item.weight_kg,
        volume_l=item.volume_l,
        fragile=item.fragile,
        priority=priority,
    )


def _dedupe(skus: List[SKU]) -> List[SKU]:
    seen = set()
    out: List[SKU] = []
    for s in skus:
        key = (s.aisle, s.position)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def random_order(
    n_skus: int,
    seed: Optional[int] = None,
    order_id: Optional[str] = None,
    operator_id: str = "OP001",
    deadline_minutes: Optional[int] = None,
    zone_weights: Optional[Dict[str, float]] = None,
) -> Order:
    rng = random.Random(seed)
    weights = zone_weights or {"FROZEN": 1.0, "FRESH": 1.5, "AMBIENT": 3.0, "HEAVY": 1.0}

    pool: List[CatalogItem] = []
    for zone, items in CATALOG_BY_ZONE.items():
        w = weights.get(zone, 1.0)
        for it in items:
            pool.extend([it] * max(1, int(w * 5)))

    skus: List[SKU] = []
    seq = 0
    attempts = 0
    while len(skus) < n_skus and attempts < n_skus * 10:
        attempts += 1
        item = rng.choice(pool)
        seq += 1
        sku = _gen_sku(item, rng, seq)
        if any((s.aisle, s.position) == (sku.aisle, sku.position) for s in skus):
            continue
        skus.append(sku)

    if order_id is None:
        order_id = f"ORD-{datetime.now().strftime('%Y%m')}-{rng.randint(1000, 9999):04d}"

    op = picker_by_id(operator_id)
    return Order(
        order_id=order_id,
        operator_id=op.op_id,
        operator_name=op.name,
        created_at=datetime.now().strftime("%d %b %Y %H:%M"),
        skus=_dedupe(skus),
        deadline_minutes=deadline_minutes,
    )


# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #
def preset_express() -> Order:
    return random_order(
        n_skus=10, seed=11,
        order_id="ORD-EXPRESS-001",
        operator_id="OP003",
        deadline_minutes=20,
        zone_weights={"FROZEN": 0.0, "FRESH": 0.5, "AMBIENT": 5.0, "HEAVY": 0.0},
    )


def preset_standard() -> Order:
    return random_order(
        n_skus=25, seed=42,
        order_id="ORD-STANDARD-002",
        operator_id="OP007",
        deadline_minutes=45,
    )


def preset_cold_chain() -> Order:
    return random_order(
        n_skus=40, seed=777,
        order_id="ORD-COLDCHAIN-003",
        operator_id="OP004",
        deadline_minutes=35,
        zone_weights={"FROZEN": 4.0, "FRESH": 4.0, "AMBIENT": 1.0, "HEAVY": 0.5},
    )


def preset_mega_wave() -> Order:
    return random_order(
        n_skus=80, seed=1234,
        order_id="ORD-MEGAWAVE-004",
        operator_id="OP010",
        deadline_minutes=60,
    )


PRESETS = {
    "Express (10 SKUs, ambient only)": preset_express,
    "Standard (25 SKUs, all zones)": preset_standard,
    "Cold chain (40 SKUs, mostly fresh + frozen)": preset_cold_chain,
    "Mega wave (80 SKUs, multi-operator)": preset_mega_wave,
}
