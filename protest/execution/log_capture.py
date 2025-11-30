import logging
from dataclasses import dataclass
from logging import LogRecord


@dataclass
class LogCapture:
    _records: list[LogRecord]

    @property
    def records(self) -> list[LogRecord]:
        return self._records

    @property
    def text(self) -> str:
        return "\n".join(
            f"{record.levelname}:{record.name}:{record.getMessage()}"
            for record in self._records
        )

    def at_level(self, level: str | int) -> list[LogRecord]:
        if isinstance(level, str):
            level = getattr(logging, level.upper())
        return [record for record in self._records if record.levelno >= level]

    def clear(self) -> None:
        self._records.clear()
