"""JSON-persisted history of solved orders (last 50)."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

HISTORY_DIR = Path(__file__).resolve().parent.parent / ".history"
HISTORY_FILE = HISTORY_DIR / "orders.json"
MAX_HISTORY = 50


@dataclass
class HistoryRecord:
    order_id: str
    operator_id: str
    operator_name: str
    timestamp: str
    n_skus: int
    zones: List[str]
    naive_distance_m: float
    or_tools_distance_m: float
    constrained_distance_m: float
    chosen_method: str
    chosen_distance_m: float
    chosen_time_min: float
    chosen_cost_eur: float
    cold_chain_seconds: float
    door_crossings: int
    savings_vs_naive_eur: float
    savings_vs_naive_pct: float
    sku_visits: Dict[str, int]


def _ensure() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def load_history() -> List[HistoryRecord]:
    _ensure()
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text())
        return [HistoryRecord(**rec) for rec in data]
    except Exception:
        return []


def save_record(record: HistoryRecord) -> None:
    _ensure()
    records = load_history()
    records = [r for r in records if r.order_id != record.order_id]
    records.insert(0, record)
    records = records[:MAX_HISTORY]
    HISTORY_FILE.write_text(json.dumps([asdict(r) for r in records], indent=2))


def clear_history() -> None:
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()


def aggregate_pick_heatmap(records: List[HistoryRecord]) -> Dict[str, int]:
    agg: Dict[str, int] = {}
    for rec in records:
        for k, v in rec.sku_visits.items():
            agg[k] = agg.get(k, 0) + v
    return agg


def per_operator_summary(records: List[HistoryRecord]) -> List[Dict]:
    by_op: Dict[str, Dict] = {}
    for rec in records:
        s = by_op.setdefault(rec.operator_id, {
            "operator_id": rec.operator_id,
            "operator_name": rec.operator_name,
            "orders": 0,
            "total_distance_m": 0.0,
            "total_time_min": 0.0,
            "total_savings_eur": 0.0,
            "constrained_runs": 0,
        })
        s["orders"] += 1
        s["total_distance_m"] += rec.chosen_distance_m
        s["total_time_min"] += rec.chosen_time_min
        s["total_savings_eur"] += rec.savings_vs_naive_eur
        if rec.chosen_method in ("or_tools", "constrained"):
            s["constrained_runs"] += 1
    out = []
    for s in by_op.values():
        s["adoption_pct"] = round(100.0 * s["constrained_runs"] / max(s["orders"], 1), 1)
        s["total_distance_km"] = round(s["total_distance_m"] / 1000.0, 2)
        s["total_time_h"] = round(s["total_time_min"] / 60.0, 2)
        s["total_savings_eur"] = round(s["total_savings_eur"], 2)
        out.append(s)
    return sorted(out, key=lambda r: -r["total_savings_eur"])


def cumulative_savings_eur(records: List[HistoryRecord]) -> float:
    return round(sum(r.savings_vs_naive_eur for r in records), 2)


def make_record(order, metrics, chosen_method: str) -> HistoryRecord:
    chosen = metrics[chosen_method]
    base = metrics["naive"]
    saved = base.cost_eur - chosen.cost_eur
    pct = (saved / base.cost_eur * 100.0) if base.cost_eur else 0.0
    visits: Dict[str, int] = {}
    for s in order.skus:
        key = f"{s.aisle}-{s.position:02d}"
        visits[key] = visits.get(key, 0) + 1
    return HistoryRecord(
        order_id=order.order_id,
        operator_id=order.operator_id,
        operator_name=order.operator_name,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        n_skus=order.size,
        zones=order.zones_covered,
        naive_distance_m=round(base.distance_m, 1),
        or_tools_distance_m=round(metrics["or_tools"].distance_m, 1),
        constrained_distance_m=round(metrics["constrained"].distance_m, 1),
        chosen_method=chosen_method,
        chosen_distance_m=round(chosen.distance_m, 1),
        chosen_time_min=round(chosen.total_time_sec / 60.0, 2),
        chosen_cost_eur=round(chosen.cost_eur, 3),
        cold_chain_seconds=round(chosen.cold_chain_seconds, 1),
        door_crossings=int(chosen.door_crossings),
        savings_vs_naive_eur=round(saved, 3),
        savings_vs_naive_pct=round(pct, 2),
        sku_visits=visits,
    )
