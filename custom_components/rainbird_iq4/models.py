"""Integration-level data snapshots for Rain Bird IQ4."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pyrainbird_iq4.cloud.models import (
    ConnectionStatus,
    Controller,
    Program,
    ScheduledProgram,
    Station,
    StationRuntime,
)

from .const import DISCOVERY_STALE_SECONDS


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

    def station(self, station_id: int) -> Station | None:
        """Return the station with this cloud ID, if it still exists."""
        return next((station for station in self.stations if station.id == station_id), None)

    def program_references(self, station_id: int) -> list[dict[str, Any]]:
        """Return the programs assigned to one station, with their schedule status."""
        assignments = next(
            (
                runtime.assignments
                for runtime in self.runtime_assignments
                if runtime.station_id == station_id
            ),
            (),
        )
        effective_by_id = {program["id"]: program for program in self.effective_programs}
        references = []
        for assignment in assignments:
            program = effective_by_id.get(assignment.program_id)
            references.append(
                {
                    "program_id": assignment.program_id,
                    "program_name": assignment.program_short_name,
                    "adjusted_runtime": assignment.adjusted_run_time,
                    "base_runtime": assignment.base_run_time,
                    "reference_source": "station_runtime_assignment",
                    "effective": program is not None,
                    "scheduled": bool(program.get("scheduled_times")) if program else False,
                }
            )
        return references

    def program_reference(self, station_id: int, program_id: int) -> dict[str, Any] | None:
        """Return one station's assignment of one program, if it still exists."""
        return next(
            (
                reference
                for reference in self.program_references(station_id)
                if reference["program_id"] == program_id
            ),
            None,
        )

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


def _observed_scheduled_program_number(name: str) -> int | None:
    """Map only scheduled program labels confirmed by local protocol evidence."""
    normalized = name.strip().casefold()
    return {"a": 1, "program a": 1, "b": 2, "program b": 2}.get(normalized)


def is_stale(connection_status: Any | None, *, now: datetime | None = None) -> bool:
    """Return whether a controller is stale based on the connection timestamp."""
    if connection_status is None:
        return True
    if not connection_status.timestamp:
        return True
    try:
        timestamp = datetime.fromisoformat(connection_status.timestamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return ((now or datetime.now(UTC)) - timestamp).total_seconds() > DISCOVERY_STALE_SECONDS


def build_effective_programs(
    programs: Iterable[Any],
    scheduled_programs: Iterable[Any],
) -> list[dict[str, Any]]:
    """Build effective programs while respecting MQTT-derived schedules."""
    direct = list(programs)
    if direct:
        return [
            {
                "source": "direct",
                "id": program.id,
                "name": program.name,
                "short_name": program.short_name,
                "protocol_program_number": program.number,
            }
            for program in direct
        ]

    effective: list[dict[str, Any]] = []
    for item in scheduled_programs:
        if getattr(item, "program_name", None):
            effective.append(
                {
                    "source": "scheduled",
                    "id": item.program_id,
                    "name": item.program_name,
                    "protocol_program_number": _observed_scheduled_program_number(
                        item.program_name
                    ),
                    "scheduled_times": [
                        {
                            "time_of_day": start.time_of_day.isoformat(),
                            "start_time_index": start.start_time_index,
                        }
                        for start in item.scheduled_times
                    ],
                }
            )
    return effective
