"""Shared data types for ticket sources."""
from __future__ import annotations

from dataclasses import asdict, dataclass


class BlockedError(Exception):
    """A ticket source blocked the request or changed format."""


@dataclass(frozen=True)
class Show:
    cinema_id: str
    cinema_name: str
    session_id: str
    show_time: str  # local IST, e.g. "2026-12-17T07:35"
    fmt: str
    language: str
    avail: int
    total: int
    booking_url: str
    source: str = "District"

    @property
    def key(self) -> str:
        return f"{self.source}:{self.cinema_id}:{self.session_id}"

    @property
    def date(self) -> str:
        return self.show_time[:10]

    @property
    def hour(self) -> int:
        return int(self.show_time[11:13])

    def to_dict(self) -> dict:
        return asdict(self)
