"""Domain model: SKU, Warehouse, Order.

All picks happen at floor level (z = 0). Position numbering encodes side:
    ODD  -> left side of the aisle
    EVEN -> right side of the aisle
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd

from data.warehouse_config import (
    AISLES,
    PRIMARY_DOCK,
    ZONE_OF_AISLE,
    ZONES,
    position_side,
    position_xy,
)


@dataclass(frozen=True)
class SKU:
    sku_id: str                # e.g. "SKU-FRZ-EPI-F2-23"
    code: str                  # catalog code, e.g. "FRZ-EPI"
    brand: str
    name: str                  # full product name
    aisle: str
    position: int
    quantity: int = 1
    weight_kg: float = 1.0     # per unit
    volume_l: float = 1.0
    fragile: bool = False
    priority: str = "normal"   # 'normal' | 'urgent'

    @property
    def coord(self) -> Tuple[float, float]:
        return position_xy(self.aisle, self.position)

    @property
    def zone(self) -> str:
        return ZONE_OF_AISLE[self.aisle]

    @property
    def side(self) -> str:
        return position_side(self.position)

    @property
    def temperature_c(self) -> float:
        return ZONES[self.zone].temperature_c

    @property
    def total_weight_kg(self) -> float:
        return self.weight_kg * self.quantity

    @property
    def total_volume_l(self) -> float:
        return self.volume_l * self.quantity

    @property
    def pick_priority(self) -> int:
        """Lower = pick earlier. Fragile bumps a SKU to the end of its zone bucket."""
        base = ZONES[self.zone].pick_priority * 10
        if self.fragile:
            base += 1
        return base

    @property
    def display_label(self) -> str:
        return f"{self.brand} - {self.name}"


@dataclass
class Order:
    order_id: str
    operator_id: str
    operator_name: str
    created_at: str
    skus: List[SKU]
    deadline_minutes: Optional[int] = None

    @property
    def size(self) -> int:
        return len(self.skus)

    @property
    def total_weight_kg(self) -> float:
        return sum(s.total_weight_kg for s in self.skus)

    @property
    def total_volume_l(self) -> float:
        return sum(s.total_volume_l for s in self.skus)

    @property
    def zones_covered(self) -> List[str]:
        ordering = ["HEAVY", "AMBIENT", "FRESH", "FROZEN"]
        zones = {s.zone for s in self.skus}
        return [z for z in ordering if z in zones]

    @property
    def aisles_covered(self) -> List[str]:
        return sorted({s.aisle for s in self.skus}, key=lambda a: AISLES.index(a))

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "sku_id": s.sku_id,
                "brand": s.brand,
                "product": s.name,
                "zone": s.zone,
                "aisle": s.aisle,
                "position": s.position,
                "side": s.side,
                "quantity": s.quantity,
                "weight_total_kg": round(s.total_weight_kg, 2),
                "volume_total_l": round(s.total_volume_l, 2),
                "fragile": s.fragile,
                "priority": s.priority,
                "temperature_c": s.temperature_c,
                "x": round(s.coord[0], 2),
                "y": round(s.coord[1], 2),
            }
            for s in self.skus
        ])


def order_from_dataframe(
    df: pd.DataFrame,
    order_id: str = "ORDER-CUSTOM",
    operator_id: str = "OP001",
    operator_name: str = "Operator",
    created_at: Optional[str] = None,
) -> Order:
    required = {"sku_id", "aisle", "position"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {sorted(missing)}")

    skus: List[SKU] = []
    for _, row in df.iterrows():
        aisle = str(row["aisle"]).strip().upper()
        if aisle not in AISLES:
            raise ValueError(f"unknown aisle '{aisle}'")
        position = int(row["position"])
        zone = ZONES[ZONE_OF_AISLE[aisle]]
        if not 1 <= position <= zone.positions_per_aisle:
            raise ValueError(f"position {position} out of range for {aisle}")
        skus.append(SKU(
            sku_id=str(row["sku_id"]).strip(),
            code=str(row.get("code", "GEN") or "GEN"),
            brand=str(row.get("brand", "Generic") or "Generic"),
            name=str(row.get("product", row.get("name", "Item")) or "Item"),
            aisle=aisle,
            position=position,
            quantity=int(row.get("quantity", 1) or 1),
            weight_kg=float(row.get("weight_kg", 1.0) or 1.0),
            volume_l=float(row.get("volume_l", 1.0) or 1.0),
            fragile=bool(row.get("fragile", False)),
            priority=str(row.get("priority", "normal") or "normal"),
        ))

    if created_at is None:
        created_at = datetime.now().strftime("%d %b %Y %H:%M")
    return Order(
        order_id=order_id,
        operator_id=operator_id,
        operator_name=operator_name,
        created_at=created_at,
        skus=skus,
    )


def points_for_order(order: Order) -> List[Tuple[float, float]]:
    """[primary dock, sku_1, ..., sku_n] (no trailing dock)."""
    pts: List[Tuple[float, float]] = [(PRIMARY_DOCK.x, PRIMARY_DOCK.y)]
    pts.extend(s.coord for s in order.skus)
    return pts


def labels_for_order(order: Order) -> List[str]:
    return [PRIMARY_DOCK.label] + [s.sku_id for s in order.skus]
