"""Persist the last good IQ4 cloud snapshot so local control survives a cloud outage at startup."""

from __future__ import annotations

from dataclasses import asdict
from datetime import time
from typing import Any

from pyrainbird_iq4.cloud.models import (
    ConnectionStatus,
    Controller,
    Program,
    RuntimeAssignment,
    ScheduledProgram,
    ScheduledTime,
    Station,
    StationRuntime,
)

from .models import RainBirdIQ4Data

STORAGE_VERSION = 1


def storage_key(entry_id: str) -> str:
    """Return the per-entry storage key for the cached cloud snapshot."""
    return f"rainbird_iq4.{entry_id}.cloud"


def serialize(data: RainBirdIQ4Data) -> dict[str, Any]:
    """Convert a cloud snapshot to JSON-safe primitives."""
    return {
        "controller": asdict(data.controller),
        "connected": data.connected,
        "connection_status": (
            asdict(data.connection_status) if data.connection_status is not None else None
        ),
        "stale": data.stale,
        "stations": [asdict(station) for station in data.stations],
        "programs": [asdict(program) for program in data.programs],
        "scheduled_programs": [
            {
                "program_id": program.program_id,
                "program_name": program.program_name,
                "scheduled_times": [
                    {
                        "time_of_day": start.time_of_day.isoformat(),
                        "start_time_index": start.start_time_index,
                        "raw_start_time": start.raw_start_time,
                    }
                    for start in program.scheduled_times
                ],
            }
            for program in data.scheduled_programs
        ],
        "runtime_assignments": [asdict(runtime) for runtime in data.runtime_assignments],
        "effective_programs": data.effective_programs,
    }


def deserialize(raw: dict[str, Any]) -> RainBirdIQ4Data:
    """Rebuild a cloud snapshot saved by serialize()."""
    return RainBirdIQ4Data(
        controller=Controller(**raw["controller"]),
        connected=raw["connected"],
        connection_status=(
            ConnectionStatus(**raw["connection_status"])
            if raw["connection_status"] is not None
            else None
        ),
        stale=raw["stale"],
        stations=[Station(**station) for station in raw["stations"]],
        programs=[Program(**program) for program in raw["programs"]],
        scheduled_programs=[
            ScheduledProgram(
                program_id=program["program_id"],
                program_name=program["program_name"],
                scheduled_times=tuple(
                    ScheduledTime(
                        time.fromisoformat(start["time_of_day"]),
                        start["start_time_index"],
                        start["raw_start_time"],
                    )
                    for start in program["scheduled_times"]
                ),
            )
            for program in raw["scheduled_programs"]
        ],
        runtime_assignments=[
            StationRuntime(
                station_id=runtime["station_id"],
                assignments=tuple(
                    RuntimeAssignment(**assignment) for assignment in runtime["assignments"]
                ),
            )
            for runtime in raw["runtime_assignments"]
        ],
        effective_programs=raw["effective_programs"],
    )
