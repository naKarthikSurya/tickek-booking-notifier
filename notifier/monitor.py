"""Filtering, change detection and state for the watcher (no network here)."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

from .district import Show


@dataclass
class Event:
    kind: str  # "theatre_opened" | "new_show" | "seats_back"
    show: Show
    priority: str | None  # label of the priority theatre, or None


def priority_of(show: Show, cfg: dict) -> str | None:
    for p in cfg.get("priority_theatres", []):
        if re.search(p["match"], show.cinema_name, re.I):
            return p["label"]
    return None


def matches(show: Show, cfg: dict) -> bool:
    return (
        show.date in cfg["dates"]
        and show.hour < cfg.get("morning_before_hour", 12)
        and bool(re.search(cfg.get("format_regex", "3D"), show.fmt, re.I))
    )


@dataclass
class State:
    seen_shows: dict = field(default_factory=dict)      # key -> last avail
    seen_cinemas: list = field(default_factory=list)
    seats_alerted_at: dict = field(default_factory=dict)  # key -> epoch
    pending_priority: list = field(default_factory=list)  # [{text, repeats}]
    tg_offset: int = 0
    baseline_done: bool = False
    fail_streak: int = 0
    fail_alerted: bool = False

    @classmethod
    def load(cls, path: str) -> "State":
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self, path: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=1)
        os.replace(tmp, path)


def detect(shows: list[Show], state: State, cfg: dict, now: float | None = None) -> list[Event]:
    """Compare the latest matching shows against state; update state; return alerts."""
    now = now or time.time()
    cooldown = cfg.get("seats_back_cooldown_minutes", 30) * 60
    min_seats = cfg.get("min_seats", 1)
    events: list[Event] = []
    opened: set[str] = set()
    for s in sorted(shows, key=lambda x: x.show_time):
        if not matches(s, cfg):
            continue
        prio = priority_of(s, cfg)
        prev = state.seen_shows.get(s.key)
        if s.cinema_id not in state.seen_cinemas:
            state.seen_cinemas.append(s.cinema_id)
            opened.add(s.cinema_id)
        if prev is None:
            if s.avail >= min_seats:
                kind = "theatre_opened" if s.cinema_id in opened else "new_show"
                events.append(Event(kind, s, prio))
                state.seats_alerted_at[s.key] = now
        elif prev < min_seats <= s.avail:
            last = state.seats_alerted_at.get(s.key)
            if last is None or now - last >= cooldown:
                events.append(Event("seats_back", s, prio))
                state.seats_alerted_at[s.key] = now
        state.seen_shows[s.key] = s.avail
    return events
