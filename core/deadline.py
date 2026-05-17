"""SLA / deadline check + operator-count recommendation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class DeadlineCheck:
    has_deadline: bool
    deadline_at: Optional[datetime]
    finish_at: Optional[datetime]
    slack_minutes: float
    is_met: bool
    severity: str   # 'ok' | 'tight' | 'breach'
    suggestion: str


def check_deadline(
    start_at: datetime,
    total_time_sec: float,
    deadline_minutes: Optional[int],
) -> DeadlineCheck:
    finish_at = start_at + timedelta(seconds=total_time_sec)
    if deadline_minutes is None:
        return DeadlineCheck(False, None, finish_at, 0.0, True, "ok",
                             "No deadline configured.")
    deadline_at = start_at + timedelta(minutes=deadline_minutes)
    slack = (deadline_at - finish_at).total_seconds() / 60.0
    if slack < 0:
        return DeadlineCheck(True, deadline_at, finish_at, slack, False, "breach",
                             "Picking time exceeds deadline. Use wave picking.")
    if slack < 5:
        return DeadlineCheck(True, deadline_at, finish_at, slack, True, "tight",
                             "On track but no buffer.")
    return DeadlineCheck(True, deadline_at, finish_at, slack, True, "ok",
                         "Comfortable margin -- single operator sufficient.")


def suggest_operators(
    total_time_sec: float,
    deadline_minutes: int,
    handover_seconds: float = 60.0,
    safety_margin: float = 0.85,
) -> int:
    budget = deadline_minutes * 60.0 - handover_seconds
    if budget <= 0:
        return 4
    needed = total_time_sec / (budget * safety_margin)
    if needed <= 1.0:
        return 1
    return max(2, min(8, int(needed) + 1))
