from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .clock import hms, rfc3339, utcnow


@dataclass(frozen=True)
class Window:
    """The measured interval. One object rather than two loose datetimes
    threaded through export, guard evaluation and the point record — every
    one of those needs both ends and they must agree."""

    start: datetime
    end: datetime

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError(f"window ends before it starts: {self.start} .. {self.end}")

    @classmethod
    def ending_now(cls, start: datetime) -> Window:
        return cls(start, utcnow())

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    @property
    def hms(self) -> str:
        return hms(self.seconds)

    @property
    def rfc3339(self) -> tuple[str, str]:
        return rfc3339(self.start), rfc3339(self.end)

    def to_dict(self) -> dict:
        start, end = self.rfc3339
        return {"start": start, "end": end, "seconds": round(self.seconds, 1)}

    def __str__(self) -> str:
        start, end = self.rfc3339
        return f"{start} .. {end} ({self.hms})"
