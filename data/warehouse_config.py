"""V3 warehouse configuration — 300m × 200m, 4 thermal zones.

Layout (cartesian, origin at bottom-left, units = meters):

    y=200 ┌──────────────────────┬──────────────────────────────────────────┐
          │  FROZEN  -18 C       │                                          │
    y=140 │  100 × 60   5 aisles │                                          │
          ├──[anti-cold door]────┤                                          │
          │  FRESH   0..4 C      │     AMBIENT  20 C                        │
          │  100 × 80            │     200 × 200      10 aisles            │
    y=60  │  5 aisles            │                                          │
          ├──[anti-cold door]────┤                                          │
          │  HEAVY   ambient     │                                          │
          │  100 × 60   4 aisles │                                          │
     y=0  └──────────────────────┴──────────────────────────────────────────┘
         x=0                  x=100                                     x=300

Each aisle = vertical corridor; ODD positions on its LEFT side, EVEN positions
on its RIGHT side; picker walks DOWN the odd column then UP the even column.

Anti-cold doors:
  * frozen door:  horizontal segment at y=140, x in [30,55]   +12 s per pass
  * fresh door:   horizontal segment at y=60,  x in [30,55]   +8  s per pass
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ----------------------------------------------------------------------- #
# Outer envelope
# ----------------------------------------------------------------------- #
WAREHOUSE_WIDTH: float = 300.0
WAREHOUSE_HEIGHT: float = 200.0


# ----------------------------------------------------------------------- #
# Zones
# ----------------------------------------------------------------------- #
@dataclass(frozen=True)
class Zone:
    code: str
    label: str
    color: str
    temperature_c: float
    pick_priority: int               # lower = picked first
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    aisles: Tuple[str, ...]
    positions_per_aisle: int

    def contains(self, x: float, y: float) -> bool:
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max


ZONES: Dict[str, Zone] = {
    "FROZEN": Zone(
        code="FROZEN", label="Frozen -18 C", color="#00BFFF",
        temperature_c=-18.0, pick_priority=4,
        x_min=0.0, x_max=100.0, y_min=140.0, y_max=200.0,
        aisles=("F1", "F2", "F3", "F4", "F5"),
        positions_per_aisle=40,
    ),
    "FRESH": Zone(
        code="FRESH", label="Fresh 0-4 C", color="#90EE90",
        temperature_c=4.0, pick_priority=3,
        x_min=0.0, x_max=100.0, y_min=60.0, y_max=140.0,
        aisles=("R1", "R2", "R3", "R4", "R5"),
        positions_per_aisle=40,
    ),
    "HEAVY": Zone(
        code="HEAVY", label="Heavy (ambient)", color="#FF6347",
        temperature_c=20.0, pick_priority=1,
        x_min=0.0, x_max=100.0, y_min=0.0, y_max=60.0,
        aisles=("H1", "H2", "H3", "H4"),
        positions_per_aisle=30,
    ),
    "AMBIENT": Zone(
        code="AMBIENT", label="Ambient 20 C", color="#FFD700",
        temperature_c=20.0, pick_priority=2,
        x_min=100.0, x_max=300.0, y_min=0.0, y_max=200.0,
        aisles=("AMB1", "AMB2", "AMB3", "AMB4", "AMB5",
                "AMB6", "AMB7", "AMB8", "AMB9", "AMB10"),
        positions_per_aisle=50,
    ),
}

# Flat list of every aisle (24 total)
AISLES: List[str] = [a for z in ZONES.values() for a in z.aisles]

ZONE_OF_AISLE: Dict[str, str] = {
    a: z.code for z in ZONES.values() for a in z.aisles
}

ZONE_COLORS: Dict[str, str] = {z.code: z.color for z in ZONES.values()}
ZONE_LABELS: Dict[str, str] = {z.code: z.label for z in ZONES.values()}
ZONE_PICK_PRIORITY: Dict[str, int] = {z.code: z.pick_priority for z in ZONES.values()}
ZONE_TEMPERATURE: Dict[str, float] = {z.code: z.temperature_c for z in ZONES.values()}


# ----------------------------------------------------------------------- #
# Aisle geometry
# ----------------------------------------------------------------------- #
AISLE_HALF_WIDTH: float = 1.25                  # picker corridor half-width
POSITION_PITCH: float = 1.2                     # m between consecutive same-side SKUs
AISLE_END_MARGIN: float = 4.0                   # cross-aisle space at top & bottom


def _zone_aisle_x(zone: Zone) -> Dict[str, float]:
    """Evenly space aisles inside a zone (x-coordinates of aisle centers)."""
    n = len(zone.aisles)
    span = zone.x_max - zone.x_min
    pitch = span / (n + 1)
    return {a: zone.x_min + (i + 1) * pitch for i, a in enumerate(zone.aisles)}


_AISLE_X_BY_ZONE: Dict[str, Dict[str, float]] = {z.code: _zone_aisle_x(z) for z in ZONES.values()}
AISLE_X: Dict[str, float] = {a: x for d in _AISLE_X_BY_ZONE.values() for a, x in d.items()}


def position_xy(aisle: str, position: int) -> Tuple[float, float]:
    """Cartesian coordinates of a slot.

    ODD position -> left side of the aisle, picked walking DOWN (decreasing y)
    EVEN position -> right side of the aisle, picked walking UP (increasing y)
    """
    zone = ZONES[ZONE_OF_AISLE[aisle]]
    if not 1 <= position <= zone.positions_per_aisle:
        raise ValueError(f"position {position} out of range for {aisle}")
    cx = AISLE_X[aisle]
    side_x = cx - AISLE_HALF_WIDTH if position % 2 == 1 else cx + AISLE_HALF_WIDTH

    # y-coordinate: positions 1&2 share the lowest y (zone bottom + margin),
    # 3&4 next, etc.
    pair = (position - 1) // 2          # 0-based pair index
    y = zone.y_min + AISLE_END_MARGIN + pair * POSITION_PITCH
    return side_x, y


def position_side(position: int) -> str:
    return "L" if position % 2 == 1 else "R"


# ----------------------------------------------------------------------- #
# Cross-aisles (horizontal corridors that let pickers skip ahead)
# ----------------------------------------------------------------------- #
@dataclass(frozen=True)
class CrossAisle:
    label: str
    zone_code: str
    y: float
    x_min: float
    x_max: float


CROSS_AISLES: List[CrossAisle] = [
    CrossAisle("FROZEN-mid", "FROZEN", 170.0, 0.0, 100.0),
    CrossAisle("FRESH-mid",  "FRESH",  100.0, 0.0, 100.0),
    CrossAisle("HEAVY-mid",  "HEAVY",  30.0,  0.0, 100.0),
    CrossAisle("AMBIENT-mid","AMBIENT",100.0, 100.0, 300.0),
]


# ----------------------------------------------------------------------- #
# Anti-cold doors  (segments + per-pass time penalty)
# ----------------------------------------------------------------------- #
@dataclass(frozen=True)
class Door:
    label: str
    zone_in: str            # zone you enter when crossing inward
    y: float
    x_min: float
    x_max: float
    delay_seconds: float
    color: str = "#FF0033"


DOORS: List[Door] = [
    Door("Door FROZEN", zone_in="FROZEN", y=140.0, x_min=30.0, x_max=55.0, delay_seconds=12.0),
    Door("Door FRESH",  zone_in="FRESH",  y=60.0,  x_min=30.0, x_max=55.0, delay_seconds=8.0),
]


# ----------------------------------------------------------------------- #
# Docks  (start / end of every picking trip)
# ----------------------------------------------------------------------- #
@dataclass(frozen=True)
class Dock:
    label: str
    x: float
    y: float
    kind: str               # 'dispatch' | 'heavy'


DOCKS: List[Dock] = [
    Dock("DOCK-D1", x=300.0, y=40.0,  kind="dispatch"),
    Dock("DOCK-D2", x=300.0, y=100.0, kind="dispatch"),
    Dock("DOCK-D3", x=300.0, y=160.0, kind="dispatch"),
    Dock("DOCK-H",  x=50.0,  y=0.0,   kind="heavy"),
]
PRIMARY_DOCK: Dock = DOCKS[1]  # DOCK-D2, central dispatch dock


# ----------------------------------------------------------------------- #
# Stretch wrappers (filmeuses) — 2 per zone = 8 total
# ----------------------------------------------------------------------- #
@dataclass(frozen=True)
class Wrapper:
    label: str
    zone_code: str
    x: float
    y: float
    capacity_pallets_per_hour: int = 45


WRAPPERS: List[Wrapper] = [
    # Frozen (2)
    Wrapper("FILM-FRZ-1", "FROZEN", x=8.0,  y=148.0),
    Wrapper("FILM-FRZ-2", "FROZEN", x=92.0, y=148.0),
    # Fresh (2)
    Wrapper("FILM-FRH-1", "FRESH", x=8.0,  y=132.0),
    Wrapper("FILM-FRH-2", "FRESH", x=92.0, y=132.0),
    # Heavy (2)
    Wrapper("FILM-HVY-1", "HEAVY", x=8.0,  y=52.0),
    Wrapper("FILM-HVY-2", "HEAVY", x=92.0, y=52.0),
    # Ambient (2)
    Wrapper("FILM-AMB-1", "AMBIENT", x=110.0, y=192.0),
    Wrapper("FILM-AMB-2", "AMBIENT", x=290.0, y=192.0),
]


# ----------------------------------------------------------------------- #
# Forklift configuration (separate system from pickers)
# ----------------------------------------------------------------------- #
FORKLIFT_IDS: List[str] = ["FK001", "FK002", "FK003", "FK004"]
FORKLIFT_SPEED_LADEN_MPS: float = 0.8
FORKLIFT_SPEED_UNLADEN_MPS: float = 1.2
FORKLIFT_RACK_LEVELS: int = 5
FORKLIFT_RACK_LEVEL_HEIGHT_M: float = 1.4
RESERVE_STOCK_REPLENISH_THRESHOLD: int = 3      # < this => trigger forklift


# ----------------------------------------------------------------------- #
# Operator / cart defaults
# ----------------------------------------------------------------------- #
DEFAULT_OPERATOR_SPEED_MPS: float = 1.2
DEFAULT_HOURLY_COST_EUR: float = 18.0
DEFAULT_PICK_TIME_SEC: float = 9.0      # uniform pick handling time at floor level
DEFAULT_SOLVER_TIME_LIMIT_SEC: int = 10

CART_MAX_WEIGHT_KG: float = 250.0
CART_MAX_VOLUME_M3: float = 1.5

ORDERS_PER_DAY: int = 60
WORKING_DAYS_PER_YEAR: int = 250

MAX_COLD_EXPOSURE_SEC: float = 8 * 60.0  # 8 minutes


# ----------------------------------------------------------------------- #
# Algorithm styling
# ----------------------------------------------------------------------- #
METHOD_COLORS: Dict[str, str] = {
    "naive": "#FF4B4B",
    "nearest_neighbor": "#FFB347",
    "or_tools": "#00C896",
    "constrained": "#BF7FFF",
    "forklift": "#FF8C00",
}

METHOD_LABELS: Dict[str, str] = {
    "naive": "Naive",
    "nearest_neighbor": "Nearest Neighbor",
    "or_tools": "OR-Tools TSP",
    "constrained": "OR-Tools + constraints",
    "forklift": "Forklift",
}


# ----------------------------------------------------------------------- #
# Immutable runtime config
# ----------------------------------------------------------------------- #
@dataclass(frozen=True)
class WarehouseConfig:
    width: float = WAREHOUSE_WIDTH
    height: float = WAREHOUSE_HEIGHT
    operator_speed_mps: float = DEFAULT_OPERATOR_SPEED_MPS
    hourly_cost_eur: float = DEFAULT_HOURLY_COST_EUR
    pick_time_sec: float = DEFAULT_PICK_TIME_SEC
    solver_time_limit_sec: int = DEFAULT_SOLVER_TIME_LIMIT_SEC
    cart_max_weight_kg: float = CART_MAX_WEIGHT_KG
    cart_max_volume_m3: float = CART_MAX_VOLUME_M3
    orders_per_day: int = ORDERS_PER_DAY
    working_days_per_year: int = WORKING_DAYS_PER_YEAR
    primary_dock_id: str = PRIMARY_DOCK.label
