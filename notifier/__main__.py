"""Entry point: python -m notifier [--once] [--max-minutes N] [--dry-run]

Runs anywhere Python 3.10+ runs (GitHub Actions, a PC, Termux on Android).
Needs env vars TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID unless --dry-run.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
from datetime import datetime

from . import district, pvr
from .models import BlockedError, Show
from .monitor import Event, State, detect, matches, priority_of
from .telegram import Telegram

KIND_TITLE = {
    "theatre_opened": "🎬 Theatre just OPENED bookings",
    "new_show": "🆕 New show added",
    "seats_back": "💺 Seats available again",
}


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def fmt_time(show: Show) -> str:
    dt = datetime.fromisoformat(show.show_time)
    return dt.strftime("%a %d %b, %I:%M %p")


def show_line(s: Show) -> str:
    seats = f"{s.avail}/{s.total} seats" if s.total > 0 else "Seats available"
    return (f"• <b>{html.escape(s.cinema_name)}</b>\n"
            f"  {fmt_time(s)} · {html.escape(s.fmt)} · {seats}\n"
            f"  <a href=\"{html.escape(s.booking_url)}\">Book on {html.escape(s.source)}</a>")


def event_text(e: Event, movie: str) -> str:
    head = f"🚨🚨 PRIORITY · {html.escape(e.priority)} 🚨🚨\n" if e.priority else ""
    return (f"{head}{KIND_TITLE[e.kind]}\n<b>{html.escape(movie)}</b> ({html.escape(e.show.language)})\n"
            f"{show_line(e.show)}")


def summary_text(shows: list[Show], cfg: dict, title: str) -> str:
    good = sorted((s for s in shows if matches(s, cfg) and s.avail >= cfg.get("min_seats", 1)),
                  key=lambda s: (priority_of(s, cfg) is None, s.show_time))
    lines = [f"<b>{title}</b>", f"{html.escape(cfg['movie']['name'])} · English · 3D/premium · morning"]
    for p in cfg.get("priority_theatres", []):
        listed = any(priority_of(s, cfg) == p["label"] for s in shows if matches(s, cfg))
        lines.append(f"{'✅' if listed else '⏳'} {html.escape(p['label'])}: "
                     f"{'shows listed' if listed else 'not open yet'}")
    lines.append("")
    lines.append(f"<b>Bookable now ({len(good)}):</b>" if good else "No bookable matching shows right now.")
    lines += [show_line(s) for s in good[:25]]
    if len(good) > 25:
        lines.append(f"…and {len(good) - 25} more")
    return "\n".join(lines)


class Notifier:
    def __init__(self, dry_run: bool):
        self.tg = None
        if not dry_run:
            token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
            if not token or not chat:
                sys.exit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (or use --dry-run).")
            self.tg = Telegram(token, chat)

    def send(self, text: str) -> None:
        if self.tg is None:
            print("---- TELEGRAM (dry run) ----\n" + text + "\n----------------------------", flush=True)
            return
        try:
            self.tg.send(text)
        except Exception as e:
            log(f"Telegram send failed: {e!r}")

    def inbox(self, state: State) -> list[str]:
        if self.tg is None:
            return []
        try:
            texts, state.tg_offset = self.tg.new_messages(state.tg_offset)
            return texts
        except Exception as e:
            log(f"Telegram getUpdates failed: {e!r}")
            return []


def cycle(cfg: dict, state: State, notifier: Notifier, last_shows: list[Show]) -> list[Show]:
    movie = cfg["movie"]["name"]

    # 1. Commands from the user (any reply acknowledges priority alerts).
    for text in notifier.inbox(state):
        if text.strip().lower().startswith("/status"):
            notifier.send(summary_text(last_shows, cfg, "📋 Status"))
        elif state.pending_priority:
            state.pending_priority = []
            notifier.send("✅ Got it — priority alert repeats stopped.")

    # 2. Fetch from every enabled source independently.
    delay = cfg.get("request_delay_seconds", 2)
    m = cfg["movie"]
    sources = [
        ("District", lambda: district.fetch_all_shows(
            m["district_url"], m["content_id"], cfg["languages"], cfg["dates"], delay)),
    ]
    if m.get("pvr_movie_id") or m.get("pvr_name_regex"):
        sources.append(("PVR/INOX", lambda: pvr.fetch_all_shows(
            m.get("pvr_city", "Chennai"), m.get("pvr_movie_id", ""),
            m.get("pvr_name_regex", m["name"]), cfg["languages"], cfg["dates"], min(delay, 1.5))))

    shows: list[Show] = []
    ok_sources: set[str] = set()
    for name, fetcher in sources:
        fstate = state.source_fails.setdefault(name, {"streak": 0, "alerted": False})
        try:
            got = fetcher()
            shows.extend(got)
            ok_sources.add(name)
            if fstate.get("alerted"):
                notifier.send(f"✅ Ticket watcher is reading {html.escape(name)} again.")
            fstate["streak"], fstate["alerted"] = 0, False
        except BlockedError as e:
            fstate["streak"] = fstate.get("streak", 0) + 1
            log(f"{name} fetch failed ({fstate['streak']}x): {e}")
            if fstate["streak"] >= 3 and not fstate.get("alerted"):
                notifier.send(f"⚠️ Ticket watcher can't read {html.escape(name)} right now "
                              f"({html.escape(str(e))}). Will keep retrying.")
                fstate["alerted"] = True

    if not ok_sources:
        return last_shows
    n_match = sum(matches(s, cfg) for s in shows)
    counts = ", ".join(f"{n}: {sum(s.source == n for s in shows)}" for n in sorted(ok_sources))
    log(f"Fetched {len(shows)} English shows ({counts}), {n_match} match filters.")

    # 3. First run: one digest instead of a flood of alerts.
    events = detect(shows, state, cfg, active_sources=ok_sources)
    if not state.baseline_done:
        state.baseline_done = True
        notifier.send(summary_text(shows, cfg, "🟢 Ticket watcher started"))
        return shows

    # 4. Alerts.
    min_seats = cfg.get("min_seats", 1)
    live_keys = {s.key for s in shows if matches(s, cfg) and s.avail >= min_seats}
    resend = [p for p in state.pending_priority
              if p.get("key", "").split(":", 1)[0] not in ok_sources or p.get("key") in live_keys]
    state.pending_priority = list(resend)
    normal = []
    for e in events:
        if e.priority:
            text = event_text(e, movie) + "\n\n<i>Reply anything to stop repeats.</i>"
            notifier.send(text)
            state.pending_priority.append({"key": e.show.key, "text": text,
                                           "repeats": cfg.get("priority_max_repeats", 10)})
        else:
            normal.append(event_text(e, movie))
    if normal:
        notifier.send("\n\n".join(normal))

    # 5. Repeat unacknowledged priority alerts.
    for p in resend:
        notifier.send("🔁 " + p["text"])
        p["repeats"] -= 1
    state.pending_priority = [p for p in state.pending_priority if p["repeats"] > 0]
    return shows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--state", default=os.environ.get("STATE_FILE", "state/state.json"))
    ap.add_argument("--once", action="store_true", help="run a single check and exit")
    ap.add_argument("--max-minutes", type=float, default=0, help="stop after N minutes (0 = forever)")
    ap.add_argument("--dry-run", action="store_true", help="print alerts instead of sending")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    os.makedirs(os.path.dirname(args.state) or ".", exist_ok=True)
    state = State.load(args.state)
    notifier = Notifier(args.dry_run)
    interval = cfg.get("check_interval_seconds", 180)
    deadline = time.time() + args.max_minutes * 60 if args.max_minutes else None
    last: list[Show] = []

    while True:
        started = time.time()
        try:
            last = cycle(cfg, state, notifier, last)
        except Exception as e:  # never die on one bad cycle
            log(f"Cycle error: {e!r}")
        state.save(args.state)
        if args.once:
            break
        sleep_for = max(10, interval - (time.time() - started))
        if deadline and time.time() + sleep_for > deadline:
            log("Reached max runtime; exiting so the next run can take over.")
            break
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
