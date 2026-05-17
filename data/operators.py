"""20 named pickers + 4 forklift drivers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Operator:
    op_id: str
    name: str
    speed_mps: float            # walking speed
    preferred_zone: str         # FROZEN | FRESH | AMBIENT | HEAVY
    shift: str                  # 'morning' | 'afternoon' | 'night'
    avg_picks_per_hour: int = 90


PICKERS: List[Operator] = [
    Operator("OP001", "Lucas Bernard",   1.30, "AMBIENT", "morning",   105),
    Operator("OP002", "Emma Dubois",     1.25, "FRESH",   "morning",   100),
    Operator("OP003", "Hugo Martin",     1.35, "AMBIENT", "morning",   115),
    Operator("OP004", "Chloe Lefevre",   1.20, "FROZEN",  "morning",    95),
    Operator("OP005", "Theo Garcia",     1.40, "HEAVY",   "morning",   110),
    Operator("OP006", "Lea Petit",       1.15, "AMBIENT", "morning",    90),
    Operator("OP007", "Nathan Roux",     1.30, "FROZEN",  "morning",   100),
    Operator("OP008", "Manon Fournier",  1.25, "FRESH",   "afternoon", 102),
    Operator("OP009", "Adam Moreau",     1.10, "HEAVY",   "afternoon",  85),
    Operator("OP010", "Sarah Lambert",   1.35, "AMBIENT", "afternoon", 108),
    Operator("OP011", "Louis Bonnet",    1.20, "FROZEN",  "afternoon",  92),
    Operator("OP012", "Camille Girard",  1.30, "FRESH",   "afternoon", 100),
    Operator("OP013", "Raphael Andre",   1.40, "AMBIENT", "afternoon", 113),
    Operator("OP014", "Jade Mercier",    1.15, "HEAVY",   "afternoon",  88),
    Operator("OP015", "Arthur Blanc",    1.25, "AMBIENT", "afternoon", 102),
    Operator("OP016", "Alice Robin",     1.35, "FRESH",   "night",     108),
    Operator("OP017", "Maxime Faure",    1.20, "AMBIENT", "night",      94),
    Operator("OP018", "Eva Riviere",     1.30, "FROZEN",  "night",     100),
    Operator("OP019", "Paul Chevalier",  1.10, "HEAVY",   "night",      85),
    Operator("OP020", "Ines Gauthier",   1.25, "AMBIENT", "night",      98),
]


@dataclass(frozen=True)
class ForkliftDriver:
    fk_id: str
    name: str
    caces: str          # CACES R489 category


FORKLIFT_DRIVERS: List[ForkliftDriver] = [
    ForkliftDriver("FK001", "Bruno Lefranc", "Cat.3"),
    ForkliftDriver("FK002", "David Lopez",   "Cat.5"),
    ForkliftDriver("FK003", "Marc Carpentier","Cat.3"),
    ForkliftDriver("FK004", "Yann Coste",    "Cat.5"),
]


def picker_by_id(op_id: str) -> Operator:
    for p in PICKERS:
        if p.op_id == op_id:
            return p
    raise KeyError(op_id)
