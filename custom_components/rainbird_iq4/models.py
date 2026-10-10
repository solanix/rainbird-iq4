"""Integration-level data snapshots for Rain Bird IQ4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyrainbird_iq4.cloud.models import (
    ConnectionStatus,
    Controller,
    Program,
    ScheduledProgram,
    Station,
    StationRuntime,
)


@dataclass(slots=True)
class RainBirdIQ4Data:
    """A complete read-only snapshot for one controller."""

    controller: Controller
    connected: bool
    connection_status: ConnectionStatus | None
    stale: bool
    stations: list[Station]
    programs: list[Program]
    scheduled_programs: list[ScheduledProgram]
    runtime_assignments: list[StationRuntime]
    effective_programs: list[dict[str, Any]]

    @property
    def enabled_stations(self) -> list[Station]:
        """Return stations verified enabled by the cloud station list."""
        return [station for station in self.stations if station.is_enabled is True]

    @property
    def disabled_stations(self) -> list[Station]:
        """Return stations verified disabled by the cloud station list."""
        return [station for station in self.stations if station.is_enabled is False]

    @property
    def unknown_state_stations(self) -> list[Station]:
        """Return stations without a verified enabled state."""
        return [station for station in self.stations if station.is_enabled is None]

    @property
    def known_programs(self) -> list[dict[str, Any]]:
        """Return effective programs plus unscheduled programs still assigned to stations.

        Referenced-only programs are real controller configuration, not effective schedules.
        """
        known = list(self.effective_programs)
        seen = {program["id"] for program in known}
        for runtime in self.runtime_assignments:
            for assignment in runtime.assignments:
                if assignment.program_id in seen:
                    continue
                seen.add(assignment.program_id)
                short_name = assignment.program_short_name.strip()
                known.append(
                    {
                        "source": "reference",
                        "id": assignment.program_id,
                        "name": (
                            short_name
                            if short_name.casefold().startswith("program")
                            else f"Program {short_name or assignment.program_id}"
                        ),
                        "scheduled_times": [],
                    }
                )
        return known
