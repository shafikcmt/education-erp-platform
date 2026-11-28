"""The one place where attendance reads its Studio settings (plan §3; ADR-076, CLAUDE.md §4).

Values resolve Core defaults -> the institution's preset -> tenant -> institution -> campus
(ADR-057). Code branches on these values, never on the institution type.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.customization.resolver import effective_config
from apps.customization.scopes import ConfigScope


@dataclass(frozen=True)
class AttendanceConfig:
    mode: str
    default_status: str
    edit_window_days: int
    lock_after_days: int
    threshold_percent: int
    alert_guardians: bool
    alert_email: bool
    leave_workflow: str

    @property
    def takes_daily(self) -> bool:
        return self.mode in ("daily", "both")

    @property
    def takes_period(self) -> bool:
        return self.mode in ("period", "both")


def config_for(institution_id: uuid.UUID, campus_id: uuid.UUID | None = None) -> AttendanceConfig:
    values = effective_config(ConfigScope(institution_id, campus_id))
    return AttendanceConfig(
        mode=values["attendance.mode"],
        default_status=values["attendance.default_status"],
        edit_window_days=int(values["attendance.edit_window_days"]),
        lock_after_days=int(values["attendance.lock_after_days"]),
        threshold_percent=int(values["attendance.threshold_percent"]),
        alert_guardians=bool(values["attendance.alert_guardians"]),
        alert_email=bool(values["attendance.alert_email"]),
        leave_workflow=str(values["attendance.leave_workflow"] or ""),
    )
