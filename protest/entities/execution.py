import logging
from dataclasses import dataclass, field
from logging import LogRecord


@dataclass
class LogCapture:
    _records: list[LogRecord] = field(default_factory=list)

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
        level_num: int = (
            getattr(logging, level.upper()) if isinstance(level, str) else level
        )
        return [record for record in self._records if record.levelno >= level_num]

    def clear(self) -> None:
        self._records.clear()
