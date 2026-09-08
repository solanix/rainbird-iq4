"""Minimal selectors used by config-flow tests."""

from dataclasses import dataclass
from enum import StrEnum


class TextSelectorType(StrEnum):
    """Text input display types."""

    PASSWORD = "password"


@dataclass
class TextSelectorConfig:
    """Text selector configuration."""

    type: TextSelectorType


class TextSelector:
    """Minimal callable selector validator."""

    def __init__(self, config: TextSelectorConfig) -> None:
        self.config = config

    def __call__(self, value: str) -> str:
        return value
